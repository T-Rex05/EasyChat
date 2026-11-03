"""Single-host durable originals, explicit grants and bounded recovery.

SQLite serializes publication, quota accounting and cleanup across store instances.
Payload files are published atomically before their ready row is committed. Startup
reconciliation handles the file/SQLite crash gap. Quotas cover retained UTF-8 data
and views; SQLite indexes and filesystem allocation have additional overhead.
"""

import base64
from bisect import bisect_right
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Callable
import uuid

from .types import ResultScope
from .json_locations import JsonLocations, MAX_CHARS as JSON_SEARCH_CHARS, MAX_NODES as JSON_SEARCH_NODES


_ARTIFACT_ID = re.compile(r"ar_[0-9a-f]{32}\Z")
_MAX_PAGE_CHARS = 64_000
_MAX_METADATA_BYTES = 16_384
_MAX_RECORDS = 100_000
_MAX_USER_RECORDS = 10_000
_MAX_VIEWS = 64
_MAX_GRANTS = 128
_TOMBSTONE_SECONDS = 7 * 24 * 60 * 60


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _line_layout(content: str) -> tuple[list[str], list[int]]:
    """Share Python's line boundaries without normalizing the original text."""
    lines = content.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    return lines, offsets


def _metadata(value) -> str:
    encoded = json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > _MAX_METADATA_BYTES:
        raise ValueError("metadata exceeds 16384 bytes")
    return encoded


class ResultStore:
    def __init__(
        self,
        root: Path,
        *,
        max_artifact_bytes: int = 8 * 1024 * 1024,
        max_user_bytes: int = 256 * 1024 * 1024,
        max_total_bytes: int = 1024 * 1024 * 1024,
        ttl_seconds: float = 86400,
        clock: Callable[[], float] | None = None,
    ):
        limits = (max_artifact_bytes, max_user_bytes, max_total_bytes)
        if any(type(limit) is not int or limit <= 0 for limit in limits):
            raise ValueError("byte quotas must be positive integers")
        if not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be finite and positive")
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._files = self.root / "artifacts"
        self._files.mkdir(exist_ok=True)
        self._db_path = self.root / "results.sqlite3"
        self.max_artifact_bytes = max_artifact_bytes
        self.max_user_bytes = max_user_bytes
        self.max_total_bytes = max_total_bytes
        self.ttl_seconds = ttl_seconds
        self._clock = clock or time.time
        with self._transaction() as db:
            for statement in (
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
                """CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, thread_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL, session_id TEXT NOT NULL, run_id TEXT NOT NULL,
                    tool_call_id TEXT NOT NULL, attempt_id TEXT NOT NULL, tool_name TEXT NOT NULL,
                    source_hash TEXT NOT NULL, original_bytes INTEGER NOT NULL, captured_bytes INTEGER NOT NULL,
                    raw_complete INTEGER NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
                    state TEXT NOT NULL, metadata TEXT NOT NULL)""",
                "CREATE INDEX IF NOT EXISTS artifact_scope ON artifacts(user_id, thread_id, agent_id)",
                """CREATE TABLE IF NOT EXISTS grants (
                    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
                    agent_id TEXT NOT NULL, PRIMARY KEY(artifact_id, agent_id))""",
                """CREATE TABLE IF NOT EXISTS views (
                    view_id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
                    content TEXT NOT NULL, content_hash TEXT NOT NULL, metadata TEXT NOT NULL,
                    stored_bytes INTEGER NOT NULL, created_at REAL NOT NULL)""",
                "CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(artifact_id UNINDEXED, content)",
            ):
                db.execute(statement)
            db.execute("INSERT OR IGNORE INTO settings VALUES ('cursor_key', ?)", (secrets.token_hex(32),))
            self._cursor_key = bytes.fromhex(db.execute("SELECT value FROM settings WHERE key='cursor_key'").fetchone()[0])
            self._sweep(db, reconcile=True)

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self._db_path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _path(self, artifact_id: str) -> Path:
        # This is only called with generated IDs or IDs already validated by _record.
        return self._files / f"{artifact_id}.txt"

    def _retire(self, db, row, state):
        self._path(row["artifact_id"]).unlink(missing_ok=True)
        db.execute("DELETE FROM search_index WHERE artifact_id=?", (row["artifact_id"],))
        db.execute("DELETE FROM views WHERE artifact_id=?", (row["artifact_id"],))
        db.execute("UPDATE artifacts SET state=? WHERE artifact_id=?", (state, row["artifact_id"]))

    def _sweep(self, db, *, reconcile=False):
        now = self._clock()
        for row in db.execute("SELECT * FROM artifacts WHERE state='ready' AND expires_at<=?", (now,)).fetchall():
            self._retire(db, row, "expired")
        db.execute("DELETE FROM artifacts WHERE state!='ready' AND expires_at<?", (now - _TOMBSTONE_SECONDS,))
        if reconcile:
            ready = db.execute("SELECT * FROM artifacts WHERE state='ready'").fetchall()
            for row in ready:
                if not self._path(row["artifact_id"]).is_file():
                    self._retire(db, row, "unavailable")
            retained = {row[0] for row in db.execute("SELECT artifact_id FROM artifacts WHERE state='ready'")}
            for path in self._files.iterdir():
                if (path.suffix == ".txt" and _ARTIFACT_ID.fullmatch(path.stem) and path.stem not in retained) or (
                    path.name.startswith(".ar_") and path.suffix == ".tmp"
                ):
                    path.unlink(missing_ok=True)

    def _remaining(self, db, user_id):
        raw = db.execute(
            "SELECT COALESCE(SUM(captured_bytes),0), COALESCE(SUM(CASE WHEN user_id=? THEN captured_bytes ELSE 0 END),0) "
            "FROM artifacts WHERE state='ready'", (user_id,),
        ).fetchone()
        views = db.execute(
            "SELECT COALESCE(SUM(v.stored_bytes),0), "
            "COALESCE(SUM(CASE WHEN a.user_id=? THEN v.stored_bytes ELSE 0 END),0) "
            "FROM views v JOIN artifacts a USING(artifact_id)", (user_id,),
        ).fetchone()
        return max(0, min(self.max_total_bytes - raw[0] - views[0], self.max_user_bytes - raw[1] - views[1]))

    @staticmethod
    def _info(row):
        return {
            "artifact_id": row["artifact_id"], "source_hash": row["source_hash"],
            "raw_complete": bool(row["raw_complete"]), "captured_bytes": row["captured_bytes"],
            "original_bytes": row["original_bytes"], "expires_at": row["expires_at"],
        }

    def _record(self, db, scope, artifact_id, *, owner_only=False):
        if not isinstance(artifact_id, str) or not _ARTIFACT_ID.fullmatch(artifact_id):
            return None, "not_found"
        row = db.execute("SELECT * FROM artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
        if row is None:
            return None, "not_found"
        same_thread = row["user_id"] == scope.user_id and row["thread_id"] == scope.thread_id
        granted = not owner_only and db.execute(
            "SELECT 1 FROM grants WHERE artifact_id=? AND agent_id=?", (artifact_id, scope.agent_id),
        ).fetchone()
        if not same_thread or not (row["agent_id"] == scope.agent_id or granted):
            return None, "forbidden"
        return row, "ok" if row["state"] == "ready" else row["state"]

    def put(self, scope: ResultScope, content: str, tool_name="", raw_complete=True, metadata=None) -> dict:
        if not isinstance(content, str) or not isinstance(tool_name, str) or len(tool_name) > 256:
            raise ValueError("content and tool_name must be strings; tool_name is limited to 256 characters")
        encoded = content.encode("utf-8")
        metadata_json = _metadata(metadata)
        artifact_id = "ar_" + uuid.uuid4().hex
        path = self._path(artifact_id)
        temporary = path.with_name("." + path.name + ".tmp")
        published = False
        try:
            with self._transaction() as db:
                self._sweep(db)
                counts = db.execute(
                    "SELECT COUNT(*), COALESCE(SUM(user_id=?),0) FROM artifacts", (scope.user_id,),
                ).fetchone()
                available = min(self.max_artifact_bytes, self._remaining(db, scope.user_id))
                if counts[0] >= _MAX_RECORDS or counts[1] >= _MAX_USER_RECORDS or (encoded and not available):
                    return {"status": "quota_exceeded", "raw_complete": False}
                captured = encoded[:available].decode("utf-8", errors="ignore")
                captured_bytes = len(captured.encode("utf-8"))
                complete = bool(raw_complete) and captured_bytes == len(encoded)
                now = self._clock()
                with temporary.open("xb") as output:
                    output.write(captured.encode("utf-8"))
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, path)
                published = True
                db.execute(
                    "INSERT INTO artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (artifact_id, *asdict(scope).values(), tool_name, _hash(captured), len(encoded), captured_bytes,
                     int(complete), now, now + self.ttl_seconds, "ready", metadata_json),
                )
                db.execute("INSERT INTO search_index(artifact_id,content) VALUES (?,?)", (artifact_id, captured))
                row = db.execute("SELECT * FROM artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
                result = {"status": "ok", **self._info(row), "dropped_bytes": len(encoded) - captured_bytes}
            return result
        except BaseException:
            if published:
                path.unlink(missing_ok=True)
            raise
        finally:
            temporary.unlink(missing_ok=True)

    def _content(self, db, row):
        try:
            content = self._path(row["artifact_id"]).read_bytes().decode("utf-8")
            if _hash(content) == row["source_hash"]:
                return content
        except (OSError, UnicodeError):
            pass
        self._retire(db, row, "unavailable")
        return None

    def _encode_cursor(self, value):
        payload = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode()
        signature = hmac.new(self._cursor_key, payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(signature + payload).decode("ascii")

    def _decode_cursor(self, cursor, artifact_id, source_hash):
        if not isinstance(cursor, str) or len(cursor) > 16384:
            raise ValueError("invalid cursor")
        decoded = base64.b64decode(cursor, altchars=b"-_", validate=True)
        signature, payload = decoded[:32], decoded[32:]
        if not hmac.compare_digest(signature, hmac.new(self._cursor_key, payload, hashlib.sha256).digest()):
            raise ValueError("invalid signature")
        value = json.loads(payload)
        if value["id"] != artifact_id or value["hash"] != source_hash:
            raise ValueError("cursor belongs to another artifact")
        return value

    @staticmethod
    def _select(content, start_line, end_line, json_pointer):
        if json_pointer is not None:
            if (
                not isinstance(json_pointer, str)
                or len(json_pointer.encode("utf-8")) > 2048
                or (json_pointer and not json_pointer.startswith("/"))
            ):
                raise ValueError("invalid JSON Pointer")
            value = json.loads(content)
            for segment in json_pointer.split("/")[1:]:
                if re.search(r"~(?![01])", segment):
                    raise ValueError("invalid JSON Pointer escape")
                segment = segment.replace("~1", "/").replace("~0", "~")
                if isinstance(value, list):
                    if not re.fullmatch(r"0|[1-9][0-9]*", segment):
                        raise ValueError("invalid array index")
                    value = value[int(segment)]
                elif isinstance(value, dict):
                    value = value[segment]
                else:
                    raise ValueError("pointer does not identify a value")
            return json.dumps(value, ensure_ascii=False, separators=(",", ":")), {"json_pointer": json_pointer}
        if type(start_line) is not int or start_line < 1 or (
            end_line is not None and (type(end_line) is not int or end_line < start_line)
        ):
            raise ValueError("invalid line interval")
        lines, offsets = _line_layout(content)
        start_char = offsets[min(start_line - 1, len(lines))]
        return "".join(lines[start_line - 1 : end_line]), {
            "start_line": start_line, "end_line": min(end_line or len(lines), len(lines)), "start_char": start_char,
        }

    def read(self, scope, artifact_id, start_line=1, end_line=None, json_pointer=None, max_chars=8000, cursor=None):
        with self._transaction() as db:
            self._sweep(db)
            row, status = self._record(db, scope, artifact_id)
            if status != "ok":
                return {"status": status, "content": "", "next_cursor": None, **(self._info(row) if row else {})}
            content = self._content(db, row)
            if content is None:
                return {"status": "unavailable", "content": "", "next_cursor": None, **self._info(row)}
            offset = 0
            if cursor is not None:
                try:
                    position = self._decode_cursor(cursor, artifact_id, row["source_hash"])
                    start_line, end_line, json_pointer, offset = (
                        position["start"], position["end"], position["pointer"], position["offset"],
                    )
                except (ValueError, KeyError, TypeError, UnicodeError):
                    return {"status": "invalid_cursor", "content": "", "next_cursor": None}
            try:
                if type(max_chars) is not int or max_chars < 1:
                    raise ValueError("invalid page budget")
                selected, span = self._select(content, start_line, end_line, json_pointer)
            except (ValueError, KeyError, IndexError, TypeError, RecursionError):
                return {"status": "invalid_selector", "content": "", "next_cursor": None}
            end_offset = min(len(selected), offset + min(max_chars, _MAX_PAGE_CHARS))
            page = selected[offset:end_offset]
            next_cursor = None
            if end_offset < len(selected):
                next_cursor = self._encode_cursor({
                    "id": artifact_id, "hash": row["source_hash"], "start": start_line, "end": end_line,
                    "pointer": json_pointer, "offset": end_offset,
                })
            span.update({"selection_start_char": offset, "selection_end_char": end_offset})
            return {
                "status": "ok", "content": page, "next_cursor": next_cursor, **self._info(row),
                "selection_complete": next_cursor is None, "span": span,
            }

    def search(self, scope, query, artifact_ids=None, max_chars=8000, *, max_structure_chars=None):
        if not isinstance(query, str) or not query or len(query) > 1024 or type(max_chars) is not int or max_chars < 1:
            return {"status": "invalid_query", "content": "", "matches": [], "truncated": False}
        if artifact_ids is not None and (
            not isinstance(artifact_ids, (list, tuple))
            or len(artifact_ids) > 1000
            or any(not isinstance(value, str) for value in artifact_ids)
        ):
            return {"status": "invalid_query", "content": "", "matches": [], "truncated": False}
        budget = min(max_chars, _MAX_PAGE_CHARS)
        if max_structure_chars is not None and (type(max_structure_chars) is not int or max_structure_chars < 0):
            return {"status": "invalid_query", "content": "", "matches": [], "truncated": False}
        structure_budget = min(max_chars if max_structure_chars is None else max_structure_chars, 4096)
        parse_chars, parse_nodes = JSON_SEARCH_CHARS, JSON_SEARCH_NODES
        matches, snippets = [], []
        truncated = False
        with self._transaction() as db:
            self._sweep(db)
            # FTS phrase lookup accelerates word queries; instr also finds literal
            # punctuation, paths, identifiers and substrings without FTS token loss.
            phrase = '"' + query.replace("\x00", " ").replace('"', '""') + '"'
            sql = (
                "SELECT a.* FROM artifacts a WHERE a.state='ready' AND a.user_id=? AND a.thread_id=? "
                "AND (a.agent_id=? OR EXISTS(SELECT 1 FROM grants g WHERE g.artifact_id=a.artifact_id AND g.agent_id=?)) "
                "AND a.artifact_id IN (SELECT artifact_id FROM search_index WHERE search_index MATCH ? "
                "UNION SELECT artifact_id FROM search_index WHERE instr(content,?)>0)"
            )
            parameters = [scope.user_id, scope.thread_id, scope.agent_id, scope.agent_id, phrase, query]
            if artifact_ids is not None:
                sql += " AND a.artifact_id IN (" + ",".join("?" for _ in artifact_ids) + ")"
                parameters.extend(artifact_ids)
            candidates = db.execute(sql + " ORDER BY a.created_at,a.artifact_id", parameters).fetchall()
            for candidate in candidates:
                if len(matches) >= 100 or budget <= int(bool(snippets)):
                    truncated = True
                    break
                row = candidate
                content = self._content(db, row)
                if content is None:
                    continue
                offset = content.find(query)
                if offset < 0:
                    continue
                lines, line_offsets = _line_layout(content)
                locations = None
                location_status = "budget_omitted"
                if structure_budget >= 128:
                    location_status = "limit_exceeded"
                    if len(content) <= parse_chars and parse_nodes > 0:
                        locations = JsonLocations(content, max_nodes=parse_nodes)
                        parse_chars -= len(content)
                        parse_nodes -= locations.nodes_scanned
                while offset >= 0:
                    separator = int(bool(snippets))
                    if budget <= separator or len(matches) >= 100:
                        truncated = True
                        break
                    last_query_line = bisect_right(line_offsets, offset + len(query) - 1) - 1
                    # Exclude the final separator from the snippet unless it is
                    # part of the query itself; read() still returns exact lines.
                    line_end = line_offsets[last_query_line] + len(lines[last_query_line].splitlines()[0])
                    line_end = max(line_end, offset + len(query))
                    end = min(line_end, offset + 240, offset + budget - separator)
                    snippet = content[offset:end]
                    location = locations.locate(offset, offset + len(query), structure_budget) if locations else {
                        "json_location_status": location_status,
                    }
                    structure_budget = max(0, structure_budget - len(json.dumps(
                        location, ensure_ascii=False, separators=(",", ":"))))
                    matches.append({
                        **self._info(row), "content": snippet, "start_char": offset, "end_char": end,
                        "start_line": bisect_right(line_offsets, offset),
                        "end_line": bisect_right(line_offsets, end - 1),
                        **location,
                    })
                    snippets.append(snippet)
                    budget -= len(snippet) + separator
                    truncated = truncated or end < min(line_end, offset + len(query))
                    offset = content.find(query, offset + max(1, len(query)))
                if budget == 0:
                    # Remaining candidates/occurrences might contain more evidence.
                    truncated = truncated or offset >= 0 or candidate != candidates[-1]
                    break
        return {"status": "ok", "content": "\n".join(snippets), "matches": matches, "truncated": truncated}

    def grant(self, scope, artifact_id, target_agent_id):
        if not isinstance(target_agent_id, str) or not target_agent_id or len(target_agent_id.encode()) > 512:
            raise ValueError("target_agent_id must be a nonempty string of at most 512 bytes")
        with self._transaction() as db:
            self._sweep(db)
            _, status = self._record(db, scope, artifact_id, owner_only=True)
            if status != "ok":
                raise PermissionError(f"artifact is {status}")
            if db.execute(
                "SELECT 1 FROM grants WHERE artifact_id=? AND agent_id=?", (artifact_id, target_agent_id),
            ).fetchone():
                return
            if db.execute("SELECT COUNT(*) FROM grants WHERE artifact_id=?", (artifact_id,)).fetchone()[0] >= _MAX_GRANTS:
                raise ValueError("grant storage quota exceeded")
            db.execute("INSERT OR IGNORE INTO grants VALUES (?,?)", (artifact_id, target_agent_id))

    def persist_view(self, scope, artifact_id, view_id, content, metadata):
        if not isinstance(view_id, str) or not view_id or len(view_id) > 256 or not isinstance(content, str):
            raise ValueError("view_id and content must be strings; view_id is limited to 256 characters")
        metadata_json = _metadata(metadata)
        stored_bytes = len(content.encode("utf-8")) + len(metadata_json.encode("utf-8"))
        with self._transaction() as db:
            self._sweep(db)
            _, status = self._record(db, scope, artifact_id, owner_only=True)
            if status != "ok":
                raise PermissionError(f"artifact is {status}")
            previous = db.execute("SELECT * FROM views WHERE view_id=?", (view_id,)).fetchone()
            if previous:
                if (previous["artifact_id"], previous["content"], previous["metadata"]) != (artifact_id, content, metadata_json):
                    raise ValueError("published view is immutable")
                return
            count = db.execute("SELECT COUNT(*) FROM views WHERE artifact_id=?", (artifact_id,)).fetchone()[0]
            if count >= _MAX_VIEWS or stored_bytes > min(self.max_artifact_bytes, self._remaining(db, scope.user_id)):
                raise ValueError("view storage quota exceeded")
            db.execute(
                "INSERT INTO views VALUES (?,?,?,?,?,?,?)",
                (view_id, artifact_id, content, _hash(content), metadata_json, stored_bytes, self._clock()),
            )
