"""Bounded JSON token locations for literal search; no inferred or rewritten paths."""

from bisect import bisect_right
from dataclasses import dataclass, field
import json
import math
import re


MAX_CHARS = 2 * 1024 * 1024
MAX_NODES = 20_000
_MAX_DEPTH = 64
_MAX_POINTER_BYTES = 2048
_MAX_NEIGHBORS = 8
_SPACE = re.compile(r"[ \t\r\n]*")
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


class _Unavailable(ValueError):
    pass


@dataclass
class _Node:
    pointer: str
    kind: str
    parent: int | None
    position: int
    children: list[int] = field(default_factory=list)
    scalar_span: tuple[int, int] | None = None


class JsonLocations:
    """Validate a whole document before exposing exact key/scalar token pointers.

    Duplicate keys invalidate the entire structure: a source occurrence must not
    point at a different value selected by a JSON decoder's last-key-wins policy.
    Only bounded metadata is returned; sibling values never enter this index.
    """

    def __init__(self, content, *, max_nodes=MAX_NODES):
        self._source = content
        self._pos = 0
        self._nodes = []
        self._spans = []
        self._starts = []
        self._decoder = json.JSONDecoder()
        self._node_limit = min(MAX_NODES, max(0, max_nodes))
        self.status = "ok"
        try:
            if len(content) > MAX_CHARS:
                raise _Unavailable("limit_exceeded")
            self._skip()
            if not self._peek() or self._peek() not in '{["-0123456789tfn':
                raise _Unavailable("not_json")
            self._value("", None, 0)
            self._skip()
            if self._pos != len(content):
                raise _Unavailable("invalid_json")
        except _Unavailable as error:
            self.status = str(error)
        except (ValueError, UnicodeError, RecursionError):
            self.status = "invalid_json"
        self.nodes_scanned = len(self._nodes)
        if self.status != "ok":
            self._nodes.clear()
            self._spans.clear()
        self._spans.sort()
        self._starts = [span[0] for span in self._spans]

    def _skip(self):
        self._pos = _SPACE.match(self._source, self._pos).end()

    def _peek(self):
        return self._source[self._pos:self._pos + 1]

    def _expect(self, token):
        if self._peek() != token:
            raise _Unavailable("invalid_json")
        self._pos += 1
        self._skip()

    def _string(self):
        if self._peek() != '"':
            raise _Unavailable("invalid_json")
        value, self._pos = self._decoder.raw_decode(self._source, self._pos)
        return value

    def _value(self, pointer, parent, depth):
        if depth > _MAX_DEPTH or len(self._nodes) >= self._node_limit:
            raise _Unavailable("limit_exceeded")
        if len(pointer.encode("utf-8")) > _MAX_POINTER_BYTES:
            raise _Unavailable("limit_exceeded")
        start, token = self._pos, self._peek()
        index = len(self._nodes)
        position = len(self._nodes[parent].children) if parent is not None else 0
        kind = {"{": "object", "[": "array", '"': "string"}.get(token)
        node = _Node(pointer, kind or "", parent, position)
        self._nodes.append(node)
        if parent is not None:
            self._nodes[parent].children.append(index)
        if token == "{":
            self._expect("{")
            seen = set()
            if self._peek() != "}":
                while True:
                    key_start = self._pos
                    key = self._string()
                    key_end = self._pos
                    if key in seen:
                        raise _Unavailable("ambiguous_keys")
                    seen.add(key)
                    self._skip()
                    self._expect(":")
                    escaped = key.replace("~", "~0").replace("/", "~1")
                    child = self._value(pointer + "/" + escaped, index, depth + 1)
                    self._spans.append((key_start, key_end, child))
                    self._skip()
                    if self._peek() != ",":
                        break
                    self._expect(",")
            self._expect("}")
        elif token == "[":
            self._expect("[")
            if self._peek() != "]":
                while True:
                    child_pointer = pointer + "/" + str(len(node.children))
                    self._value(child_pointer, index, depth + 1)
                    self._skip()
                    if self._peek() != ",":
                        break
                    self._expect(",")
            self._expect("]")
        else:
            if token == '"':
                self._string()
            elif self._source.startswith("true", start) or self._source.startswith("false", start):
                node.kind = "boolean"
                self._pos += 4 if token == "t" else 5
            elif self._source.startswith("null", start):
                node.kind = "null"
                self._pos += 4
            else:
                number = _NUMBER.match(self._source, start)
                if number is None:
                    raise _Unavailable("invalid_json")
                # context_read uses the same decoder on the whole source. Do
                # not advertise selectors when another numeric token makes that
                # read fail (integer digit limit) or serialize to non-JSON Infinity.
                try:
                    decoded, _ = self._decoder.raw_decode(self._source, start)
                except ValueError as error:
                    raise _Unavailable("limit_exceeded") from error
                if isinstance(decoded, float) and not math.isfinite(decoded):
                    raise _Unavailable("limit_exceeded")
                node.kind = "number"
                self._pos = number.end()
            self._spans.append((start, self._pos, index))
            node.scalar_span = (start, self._pos)
        return index

    def scalar_spans(self):
        """Yield exact scalar-token spans in source order after full validation."""
        if self.status == "ok":
            for node in self._nodes:
                if node.scalar_span is not None:
                    yield node.pointer, *node.scalar_span

    def locate(self, start, end, max_chars):
        """Locate a whole literal query inside one source key/scalar token.

        max_chars bounds the entire enrichment (not just neighbor strings). When
        it cannot hold exact pointers, omit them rather than truncate a selector.
        The outer tool continues to enforce its complete encoded envelope budget.
        """
        if self.status != "ok":
            return {"json_location_status": self.status}
        offset = bisect_right(self._starts, start) - 1
        if offset < 0 or not (self._spans[offset][0] <= start < end <= self._spans[offset][1]):
            return {"json_location_status": "cross_node_match"}
        node = self._nodes[self._spans[offset][2]]
        parent = self._nodes[node.parent] if node.parent is not None else None
        count = len(parent.children) - 1 if parent else 0
        metadata = {
            "json_location_status": "ok", "json_pointer": node.pointer,
            "parent_pointer": parent.pointer if parent else None, "json_type": node.kind,
            "neighbors": [], "neighbors_omitted": count,
        }
        if _size(metadata) > max_chars:
            return {"json_location_status": "budget_omitted"}
        if parent:
            stop = min(len(parent.children), max(0, node.position - 4) + _MAX_NEIGHBORS + 1)
            begin = max(0, stop - _MAX_NEIGHBORS - 1)
            for child in parent.children[begin:stop]:
                neighbor = self._nodes[child]
                if neighbor is node:
                    continue
                entry = {"json_pointer": neighbor.pointer, "json_type": neighbor.kind}
                metadata["neighbors"].append(entry)
                metadata["neighbors_omitted"] -= 1
                if _size(metadata) > max_chars:
                    metadata["neighbors"].pop()
                    metadata["neighbors_omitted"] += 1
                    break
        return metadata
