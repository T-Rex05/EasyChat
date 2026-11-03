"""
知识库服务层 — 文档上传 / 解析 / 切分 / 查询 / 删除 / 重新解析

职责：
- 文件落盘 data/kb/{user_id}/{uuid}{ext}
- 调用 kb_parsers 提取文本（带页码 + 扫描版检测）
- RecursiveCharacterTextSplitter 切分为 chunk，持久化到 kb_chunks 表
- 所有查询按用户隔离（kb.manage 权限可查看全部）

数据流：
    上传 → 落盘 → INSERT kb_documents(status=parsing)
         → to_thread: parse → chunk → 批量 INSERT kb_chunks
         → UPDATE kb_documents(status/统计字段)
"""
import asyncio
import hashlib
import re
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from backend.db.schema import get_conn
from backend.service.kb.kb_parsers import (
    ALLOWED_EXTS,
    parse_with_fallback,
)
from backend.utils.log_utils import log, rag

logger = log

# ── 常量 ──
_MAX_FILE_BYTES = 50 * 1024 * 1024      # 单文件 50MB 上限
_MAX_CHUNKS = 10000                     # 单文档 chunk 上限（防 DB 爆炸）
_DEFAULT_CHUNK_SIZE = 2000   # 父片默认大小（子片固定600，检索最优）
_DEFAULT_CHUNK_OVERLAP = 200
_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


# ── 异常 ──

class KbError(Exception):
    """知识库业务异常基类"""


class KbNotFound(KbError):
    """文档不存在（或不属于当前用户）→ 404"""


class KbInvalidFile(KbError):
    """文件不合法（扩展名/大小/损坏）→ 400"""


# ── 路径与名称工具 ──

def kb_root() -> Path:
    """知识库文件根目录 docker/volumes/kb/"""
    from backend.config.paths import DATA_ROOT
    root = DATA_ROOT / "kb"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sanitize_name(name: str) -> str:
    """净化原始文件名：去路径、替换非法字符、限制长度。"""
    name = Path(name or "unnamed").name.strip()
    name = _ILLEGAL_CHARS.sub("_", name)
    return (name[:200] or "unnamed")


def _normalize_chunk_params(chunk_size, chunk_overlap) -> tuple:
    try:
        size = int(chunk_size) if chunk_size else _DEFAULT_CHUNK_SIZE
    except (TypeError, ValueError):
        size = _DEFAULT_CHUNK_SIZE
    try:
        overlap = int(chunk_overlap) if chunk_overlap else _DEFAULT_CHUNK_OVERLAP
    except (TypeError, ValueError):
        overlap = _DEFAULT_CHUNK_OVERLAP
    size = max(100, min(size, 8000))
    overlap = max(0, min(overlap, size - 1))
    return size, overlap


# ── 内部：解析 + 切分 ──

def _make_splitter(chunk_size: int, chunk_overlap: int):
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", "。", ".", "；", ";", " ", ""],
    )


def _chunk_pages(pages: List, chunk_size: int, chunk_overlap: int) -> List[dict]:
    """
    将解析出的页面切分为基础 chunk（带页码元数据）。

    每页独立切分（长页按 chunk_size 再分），保证 page_start/page_end 精确；
    无页码文档（md/txt）页码为 NULL。
    """
    splitter = _make_splitter(chunk_size, chunk_overlap)

    chunks: List[dict] = []
    for page in pages:
        text = (page.text or "").strip()
        if not text:
            continue
        pieces = [text] if len(text) <= chunk_size else splitter.split_text(text)
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            chunks.append({
                "content": piece,
                "char_count": len(piece),
                "page_start": page.page_no,
                "page_end": page.page_no,
                "kind": "base",
                "topic_index": None,
            })
    return chunks


def _chunk_document(
    pages: List,
    chunk_size: int,
    chunk_overlap: int,
    strategy: str,
    sections: Optional[List] = None,
    doc_name: str = "",
) -> tuple:
    """
    按策略生成 (chunks, 主题节点块)。

    统一使用父子分片策略（parent_child）：
        - 主题章节即父片（≤parent_chunk_size 字符整段；超长主题按 ### 三级标题 → 段落 → 字符三级降级）
        - 章回体小说（第X回）每回一个父片，不受 parent_chunk_size 限制
        - 无结构 → 回退【主题】标记 / ## 标题 / 字符切分
        - 子片 600 字符用于检索，命中子片返回父片完整内容
        - 父片用于 GraphRAG 实体提取（保留上下文完整性）
    """
    from backend.service.kb.kb_parent_child_splitter import build_parent_child_chunks
    
    # 父片大小使用前端传入的 chunk_size，默认 2000
    # 子片大小固定 600（检索最优），子片重叠使用 chunk_overlap 的 20%
    parent_size = chunk_size if chunk_size and chunk_size > 0 else 2000
    child_size = 600  # 子片大小固定（实测 Recall@5 最优）
    child_over = chunk_overlap if chunk_overlap and chunk_overlap > 0 else 120
    
    result = build_parent_child_chunks(
        pages,
        parent_chunk_size=parent_size,  # 使用前端传入的父片大小
        child_chunk_size=child_size,    # 子片 600 字符（检索最优）
        child_overlap=child_over,       # 子片重叠
        sections=sections or None,      # 主题结构感知（detect_topic_sections 结果）
        doc_name=doc_name,              # 文档名称（用于来源路径前缀）
    )
    # 返回 (parents + children, []) 格式
    all_chunks = result["parents"] + result["children"]
    return all_chunks, []


def _parse_and_chunk(
    file_path: str,
    parser_pref: str,
    chunk_size: int,
    chunk_overlap: int,
    chunk_strategy: str = "parent_child",
    doc_name: str = "",
) -> dict:
    """解析文件并切分（同步，运行在线程池中）。
    
    统一使用父子分片策略，自动识别主题结构。
    """
    doc = parse_with_fallback(file_path, parser_pref)

    sections: List = []
    try:
        from backend.service.kb.kb_topic_splitter import detect_topic_sections
        sections, topic_warnings = detect_topic_sections(
            Path(file_path).suffix.lower(), file_path, doc.text, doc.pages
        )
        for w in topic_warnings:
            doc.append_warning(w)
    except Exception as e:  # noqa: BLE001 — 主题识别失败降级字符切分
        doc.append_warning(f"主题识别失败，将按字符边界切分父片: {e}")
        sections = []

    base_chunks, topic_chunks = _chunk_document(
        doc.pages, chunk_size, chunk_overlap, chunk_strategy, sections, doc_name
    )
    chunks = base_chunks + topic_chunks

    truncated = False
    if len(chunks) > _MAX_CHUNKS:
        chunks = chunks[:_MAX_CHUNKS]
        truncated = True
        doc.append_warning(f"chunk 数超过上限 {_MAX_CHUNKS}，已截断")

    return {
        "text": doc.text,
        "page_count": len(doc.pages),
        "char_count": len(doc.text),
        "base_chunks": [c for c in chunks if c.get("kind") == "base"],
        "topic_chunks": [c for c in chunks if c.get("kind") == "topic"],
        "chunks": chunks,
        "sections": sections,
        "warnings": doc.warnings,
        "scanned": doc.scanned,
        "parser": doc.parser,
        "truncated": truncated,
    }


def _insert_topics(conn, document_id: int, sections: List) -> Dict[int, int]:
    """主题章节入库，返回 {section_index: topic_db_id}。"""
    id_map: Dict[int, int] = {}
    for i, s in enumerate(sections):
        cur = conn.execute(
            "INSERT INTO kb_topics (document_id, title, source, page_start, page_end, char_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (document_id, (s.title or "")[:255], s.source or "structure",
             s.page_start, s.page_end, len(s.text or "")),
        )
        id_map[i] = cur.lastrowid
    conn.commit()
    return id_map


def _chunk_metadata(chunk: dict) -> Optional[str]:
    """序列化 chunk 的扩展 metadata（table_refs 等），无扩展信息返回 None。"""
    meta: Dict = {}
    if chunk.get("table_refs"):
        meta["table_refs"] = chunk["table_refs"]
    if chunk.get("topic_title"):
        meta["topic_title"] = chunk["topic_title"]
    if chunk.get("heading_path"):
        meta["heading_path"] = chunk["heading_path"]
    if not meta:
        return None
    import json
    return json.dumps(meta, ensure_ascii=False)


def _insert_chunks(
    conn,
    document_id: int,
    chunks: List[dict],
    strategy: str,
    topic_id_map: Optional[Dict[int, int]] = None,
    kb_id: Optional[int] = None,
) -> None:
    """
    批量插入 chunks。支持父子分片：如果 chunk 有 parent_index，
    先插入父片建立 id_map，再插入子片时设置 parent_chunk_id。
    """
    topic_id_map = topic_id_map or {}

    # 分离父片和子片
    parents = [c for c in chunks if c.get("kind") == "parent"]
    children = [c for c in chunks if c.get("kind") == "child"]
    others = [c for c in chunks if c.get("kind") not in ("parent", "child")]

    # 先插入父片，建立 parent_index → db_id 映射
    parent_id_map: Dict[int, int] = {}  # parent_index → chunk_db_id
    if parents:
        for i, chunk in enumerate(parents):
            topic_id = None
            if chunk.get("topic_index") is not None:
                topic_id = topic_id_map.get(chunk["topic_index"])
            metadata = _chunk_metadata(chunk)
            cur = conn.execute(
                "INSERT INTO kb_chunks (kb_id, document_id, chunk_index, content, char_count, "
                "page_start, page_end, strategy, kind, topic_id, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (kb_id, document_id, i, chunk["content"], chunk["char_count"],
                 chunk["page_start"], chunk["page_end"], strategy,
                 "parent", topic_id, metadata),
            )
            # 获取刚插入的 chunk id（使用 lastrowid 兼容 MySQL 和 SQLite）
            parent_id_map[i] = cur.lastrowid

    # 插入子片，设置 parent_chunk_id
    if children:
        for i, chunk in enumerate(children):
            topic_id = None
            if chunk.get("topic_index") is not None:
                topic_id = topic_id_map.get(chunk["topic_index"])
            parent_chunk_id = parent_id_map.get(chunk.get("parent_index"))
            metadata = _chunk_metadata(chunk)
            conn.execute(
                "INSERT INTO kb_chunks (kb_id, document_id, chunk_index, content, char_count, "
                "page_start, page_end, strategy, kind, topic_id, parent_chunk_id, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (kb_id, document_id, len(parents) + i, chunk["content"], chunk["char_count"],
                 chunk["page_start"], chunk["page_end"], strategy,
                 "child", topic_id, parent_chunk_id, metadata),
            )

    # 插入其他类型的 chunks（base / topic）
    for i, chunk in enumerate(others):
        topic_id = None
        if chunk.get("topic_index") is not None:
            topic_id = topic_id_map.get(chunk["topic_index"])
        metadata = _chunk_metadata(chunk)
        conn.execute(
            "INSERT INTO kb_chunks (kb_id, document_id, chunk_index, content, char_count, "
            "page_start, page_end, strategy, kind, topic_id, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kb_id, document_id, len(parents) + len(children) + i, chunk["content"], chunk["char_count"],
             chunk["page_start"], chunk["page_end"], strategy,
             chunk.get("kind", "base"), topic_id, metadata),
        )
    conn.commit()


# ── 业务方法 ──

async def create_document(
    user_id: int,
    filename: str,
    content: bytes,
    chunk_size=None,
    chunk_overlap=None,
    parser_pref: str = "",
    chunk_strategy: str = "fixed",
    kb_id: Optional[int] = None,
) -> dict:
    """
    上传文档：落盘 → 解析 → 切分 → 入库。返回文档摘要。

    Args:
        chunk_strategy: fixed（固定窗口连续切分）| parent_child（父子分片·主题结构感知）
        kb_id: 所属知识库ID，None表示默认知识库

    Raises:
        KbInvalidFile: 扩展名/大小不合法
    """
    original_name = _sanitize_name(filename)
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise KbInvalidFile(
            f"不支持的文件类型 {ext or '(无扩展名)'}。"
            f"支持: {', '.join(sorted(ALLOWED_EXTS))}"
        )
    if not content:
        raise KbInvalidFile("文件内容为空")
    if len(content) > _MAX_FILE_BYTES:
        raise KbInvalidFile(f"文件超过 {_MAX_FILE_BYTES // 1024 // 1024}MB 限制")

    chunk_size, chunk_overlap = _normalize_chunk_params(chunk_size, chunk_overlap)
    # 统一使用父子切分策略（parent_child）：旧策略名 topic / fixed 已废弃，
    # 传入任何值都落到 parent_child（保留形参是为了兼容既有调用方与 DB 列）。
    chunk_strategy = "parent_child"
    stored_name = f"{uuid.uuid4().hex}{ext}"
    user_dir = kb_root() / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    stored_path = user_dir / stored_name
    stored_path.write_bytes(content)
    sha256 = hashlib.sha256(content).hexdigest()

    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO kb_documents "
            "(kb_id, user_id, original_name, stored_name, ext, size_bytes, sha256, status, chunk_size, chunk_overlap, chunk_strategy) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'parsing', ?, ?, ?)",
            (kb_id, user_id, original_name, stored_name, ext, len(content), sha256,
             chunk_size, chunk_overlap, chunk_strategy),
        )
        conn.commit()
        document_id = cur.lastrowid
    finally:
        conn.close()

    try:
        result = await asyncio.to_thread(
            _parse_and_chunk, str(stored_path), parser_pref,
            chunk_size, chunk_overlap, chunk_strategy, original_name,
        )
        status = "needs_ocr" if result["scanned"] else "parsed"
        conn = get_conn()
        try:
            topic_id_map = _insert_topics(conn, document_id, result["sections"]) if result["sections"] else {}
            _insert_chunks(conn, document_id, result["chunks"], chunk_strategy, topic_id_map, kb_id)
            conn.execute(
                "UPDATE kb_documents SET status = ?, parser = ?, page_count = ?, "
                "char_count = ?, chunk_count = ?, content_text = ?, error_message = '' WHERE id = ?",
                (status, result["parser"], result["page_count"],
                 result["char_count"], len(result["chunks"]), result["text"], document_id),
            )
            conn.commit()
        finally:
            conn.close()
        failed = False
    except Exception as e:  # noqa: BLE001 — 解析失败标记状态，不抛给用户 500
        rag.error(f"文档解析失败 doc_id={document_id}: {e}")
        failed = True
        try:
            conn = get_conn()
            try:
                conn.execute(
                    "UPDATE kb_documents SET status = 'failed', error_message = ? WHERE id = ?",
                    (str(e)[:1000], document_id),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass
        result = {
            "chunks": [], "sections": [], "page_count": 0, "char_count": 0,
            "warnings": [f"解析失败: {e}"], "scanned": False,
            "parser": "", "truncated": False,
        }

    # 自动向量化（如果 embedding 配置存在）
    if not failed:
        try:
            from backend.service.kb.kb_retriever import vectorize_document
            vectorize_document(user_id, document_id)
            rag.kb_vectorize(document_id, 0)  # 向量化计数在 retriever 层记录
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[KB] 上传后自动向量化跳过 doc_id={document_id}: {e}")
        
        # GraphRAG 实体提取（如果 Neo4j 可用）
        # 提取父片内容，保留上下文完整性
        try:
            from backend.service.kb.kb_graphrag_service import extract_document_entities_async
            extract_document_entities_async(user_id, document_id)
            rag.info(f"🕸️ [KB-GraphRAG] 上传后自动提取启动 doc_id={document_id}")
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[KB-GraphRAG] 上传后自动提取跳过 doc_id={document_id}: {e}")

    return {
        "id": document_id,
        "original_name": original_name,
        "ext": ext,
        "size_bytes": len(content),
        "sha256": sha256,
        "status": "failed" if failed else ("needs_ocr" if result["scanned"] else "parsed"),
        "parser": result["parser"],
        "page_count": result["page_count"],
        "char_count": result["char_count"],
        "chunk_count": len(result["chunks"]),
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "chunk_strategy": chunk_strategy,
        "topic_count": len(result["sections"]),
        "warnings": result["warnings"],
    }


def list_documents(
    user_id: int,
    permissions: set,
    keyword: str = "",
    page: int = 1,
    page_size: int = 20,
    kb_id: Optional[int] = None,
) -> dict:
    """文档列表（kb.manage 看全部，否则仅自己的）。"""
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    offset = (page - 1) * page_size

    where = []
    params: List = []
    if "kb.manage" not in permissions:
        where.append("user_id = ?")
        params.append(user_id)
    if keyword:
        where.append("original_name LIKE ?")
        params.append(f"%{keyword}%")
    if kb_id is not None:
        where.append("kb_id = ?")
        params.append(kb_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    conn = get_conn()
    try:
        cur = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM kb_documents {where_sql}", params
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        total = rows[0]["cnt"] if rows else 0

        # 列表显式列（排除 content_text LONGTEXT，避免大文本随列表传输）
        cols = (
            "id, kb_id, user_id, original_name, ext, size_bytes, sha256, page_count, "
            "char_count, chunk_count, status, parser, chunk_size, chunk_overlap, chunk_strategy, "
            "error_message, vectorized, created_at, updated_at"
        )
        cur = conn.execute(
            f"SELECT {cols} FROM kb_documents {where_sql} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        )
        items = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_serialize_doc(d) for d in items],
    }


def get_document(user_id: int, doc_id: int, permissions: set) -> dict:
    """文档详情（含 ownership 校验）。"""
    doc = _fetch_owned_doc(user_id, doc_id, permissions)
    return _serialize_doc(doc)


def get_document_text(user_id: int, doc_id: int, permissions: set) -> dict:
    """获取文档解析出的完整原文（「查看原文内容」）。"""
    doc = _fetch_owned_doc(user_id, doc_id, permissions)

    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT content_text FROM kb_documents WHERE id = ?", (doc_id,)
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()

    text = (rows[0].get("content_text") or "") if rows else ""
    return {
        "id": doc_id,
        "original_name": doc["original_name"],
        "text": text,
        "char_count": len(text),
        # 旧数据（本次功能上线前上传）没有存原文 → 提示重新解析
        "needs_reprocess": not text,
    }


def list_chunks(
    user_id: int,
    doc_id: int,
    permissions: set,
    page: int = 1,
    page_size: int = 50,
    kind: str = "all",
) -> dict:
    """chunk 分页列表（按 chunk_index 升序；kind: all/base/topic/child/parent）。"""
    _fetch_owned_doc(user_id, doc_id, permissions)  # 校验存在与归属

    page = max(1, int(page or 1))
    page_size = min(200, max(1, int(page_size or 50)))
    offset = (page - 1) * page_size
    kind = (kind or "all").strip()
    if kind not in ("all", "base", "topic", "child", "parent"):
        kind = "all"
    kind_sql = "" if kind == "all" else " AND c.kind = %s"

    conn = get_conn()
    try:
        cur = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM kb_chunks c WHERE c.document_id = %s{kind_sql}",
            (doc_id,) if kind == "all" else (doc_id, kind),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        total = rows[0]["cnt"] if rows else 0

        cur = conn.execute(
            "SELECT c.id, c.chunk_index, c.char_count, c.page_start, c.page_end, c.content, "
            "c.strategy, c.kind, c.topic_id, c.parent_chunk_id, t.title AS topic_title "
            "FROM kb_chunks c LEFT JOIN kb_topics t ON t.id = c.topic_id "
            f"WHERE c.document_id = %s{kind_sql} ORDER BY c.chunk_index ASC LIMIT %s OFFSET %s",
            ((doc_id,) if kind == "all" else (doc_id, kind)) + (page_size, offset),
        )
        items = cur.fetchall() if hasattr(cur, "fetchall") else []
        
        # 为父子分片添加关系信息
        if items:
            # 查询父片包含的子片数量
            parent_ids = [item["id"] for item in items if item.get("kind") == "parent"]
            if parent_ids:
                cur2 = conn.execute(
                    f"SELECT parent_chunk_id, COUNT(*) as child_count FROM kb_chunks "
                    f"WHERE parent_chunk_id IN ({','.join(['%s'] * len(parent_ids))}) "
                    f"GROUP BY parent_chunk_id",
                    parent_ids
                )
                child_counts = {row["parent_chunk_id"]: row["child_count"] for row in cur2.fetchall()}
                for item in items:
                    if item.get("kind") == "parent":
                        item["child_count"] = child_counts.get(item["id"], 0)
    finally:
        conn.close()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


def resolve_download(user_id: int, doc_id: int, permissions: set):
    """校验归属并返回 (本地文件路径, 原始文件名)，供下载端点使用。"""
    doc = _fetch_owned_doc(user_id, doc_id, permissions)
    path = kb_root() / str(doc["user_id"]) / doc["stored_name"]
    if not path.exists():
        raise KbNotFound("源文件已丢失")
    return path, doc["original_name"]


def delete_document(user_id: int, doc_id: int, permissions: set) -> dict:
    """删除文档：文件 + chunks + 文档行 + 向量 + 图谱实体。"""
    doc = _fetch_owned_doc(user_id, doc_id, permissions)

    # 清理向量（无条件尝试；不依赖 vectorized 标记 —— 标记曾因吞异常被误置 0，
    # 会导致向量库残留正文继续被检索。失败不阻断删除，但必须留痕）
    try:
        from backend.service.kb.kb_retriever import unvectorize_document
        unvectorize_document(user_id, doc_id)
    except Exception as e:  # noqa: BLE001
        logger.opt(exception=True).warning(
            f"[KB] 删除时清理向量失败 doc_id={doc_id}（向量可能残留，需人工/对账清理）: {e}"
        )

    # 清理 GraphRAG 实体（失败不阻断删除）
    if doc.get("graph_extracted"):
        try:
            from backend.service.kb.kb_graphrag_service import clear_document_entities
            result = clear_document_entities(doc_id)
            rag.info(f"🕸️ [KB-GraphRAG] 删除文档时清理图谱实体 doc_id={doc_id}: {result}")
        except Exception as e:  # noqa: BLE001
            rag.warning(f"[KB-GraphRAG] 删除时清理图谱实体失败 doc_id={doc_id}: {e}")

    conn = get_conn()
    try:
        conn.execute("DELETE FROM kb_chunks WHERE document_id = %s", (doc_id,))
        conn.execute("DELETE FROM kb_topics WHERE document_id = %s", (doc_id,))
        conn.execute("DELETE FROM kb_documents WHERE id = %s", (doc_id,))
        conn.commit()
    finally:
        conn.close()

    # BM25 内存索引失效
    try:
        from backend.service.kb.kb_retriever import invalidate_bm25_cache
        invalidate_bm25_cache(user_id)
    except Exception:  # noqa: BLE001
        pass

    stored = kb_root() / str(doc["user_id"]) / doc["stored_name"]
    try:
        stored.unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[KB] 删除文件失败 {stored}: {e}")

    rag.info(f"✅ [KB] 文档已删除 id={doc_id} user={doc['user_id']}")
    return {"id": doc_id, "deleted": True}


def move_document_kb(doc_id: int, target_kb_id: int) -> bool:
    """把文档移动到其他知识库（级联更新文档和 chunks 的 kb_id）。

    这同时就是"把文档移到另一个部门"的操作（部门挂在 KB 上，见 kb_data_layers）。
    移动后**不需要**去改知识图谱里的实体属性 —— KG 的可见性是每次实时算的
    （`data_layer_service.get_visible_document_ids`），下次查询自动按新部门过滤。
    需要做的只有两件事：

    1. **清掉 chunk 级层级钉子**：`_filter_by_scope_layer` 与 `get_visible_document_ids`
       都以 `chunk.scope_layer_id` **优先于** KB 层级。若某个 chunk 带着旧部门的
       scope_layer_id，移动后它仍然只对**旧部门**可见 —— 也就是"移动静默不生效"。
       因此这里把该文档所有 chunk 的 scope_layer_id 置回 NULL，让文档的部门
       完全由目标 KB 决定（这也是用户点"移动到 X 库"时的预期）。
       ⚠️ 目前没有任何代码会写入 scope_layer_id（只有人工 SQL），所以正常情况下
       这里影响行数为 0；保留它是为了杜绝"哪天有人手工钉了层级 → 移动不生效"的坑。
    2. **刷新可见性缓存**（BM25 索引、KG 时间线缓存），否则最长到缓存失效前仍按旧部门返回。

    注意：KG 实体上**不存**层级，所以这里不会、也不应该去改任何实体属性。
    """
    conn = get_conn()
    try:
        row = conn.execute("SELECT user_id, kb_id FROM kb_documents WHERE id = %s", (doc_id,)).fetchone()
        owner_id = (row or {}).get("user_id") if row else None
        source_kb_id = (row or {}).get("kb_id") if row else None

        # 1. 清掉会覆盖目标 KB 部门的 chunk 级层级钉子
        pinned = conn.execute(
            "SELECT COUNT(*) AS n FROM kb_chunks "
            "WHERE document_id = %s AND scope_layer_id IS NOT NULL",
            (doc_id,),
        ).fetchone()
        pinned_n = int((pinned or {}).get("n") or 0)
        if pinned_n:
            conn.execute(
                "UPDATE kb_chunks SET scope_layer_id = NULL "
                "WHERE document_id = %s AND scope_layer_id IS NOT NULL",
                (doc_id,),
            )

        # 2. 迁移文档与 chunks 的 kb_id
        conn.execute("UPDATE kb_documents SET kb_id = %s WHERE id = %s", (target_kb_id, doc_id))
        conn.execute("UPDATE kb_chunks SET kb_id = %s WHERE document_id = %s", (target_kb_id, doc_id))
        conn.commit()

        if pinned_n:
            rag.info(
                f"📦 [KB] 文档已移动 id={doc_id} → kb_id={target_kb_id}；"
                f"同时清掉 {pinned_n} 个 chunk 级层级钉子（使其部门完全跟随目标 KB）"
            )
        else:
            rag.info(f"📦 [KB] 文档已移动 id={doc_id} → kb_id={target_kb_id}")
    except Exception as e:  # noqa: BLE001
        rag.error(f"[KB] 移动文档失败 id={doc_id}: {e}")
        return False
    finally:
        conn.close()

    # 3. 刷新派生缓存（可见性变了两处都受影响）
    try:
        from backend.service.auth.data_layer_service import notify_visibility_changed

        notify_visibility_changed(
            reason=f"文档 {doc_id} 从 kb {source_kb_id} 移动到 kb {target_kb_id}（owner={owner_id}）"
        )
    except Exception as e:  # noqa: BLE001
        # 只影响缓存新鲜度，不影响正确性（安全性由返回前的实时层级过滤兜底）
        rag.warning(f"[KB] 移动后刷新可见性缓存失败（不阻断）: {e}")
    return True


async def reprocess_document(
    user_id: int,
    doc_id: int,
    permissions: set,
    parser_pref: str = "",
    chunk_size=None,
    chunk_overlap=None,
    chunk_strategy: Optional[str] = None,
) -> dict:
    """重新解析/切分：清空旧 chunks/topics，按新参数重建（strategy 缺省沿用文档现有策略）。"""
    doc = _fetch_owned_doc(user_id, doc_id, permissions)

    chunk_size, chunk_overlap = _normalize_chunk_params(
        chunk_size or doc.get("chunk_size"), chunk_overlap or doc.get("chunk_overlap")
    )
    strategy = chunk_strategy or doc.get("chunk_strategy") or "fixed"
    if strategy not in ("fixed", "topic", "parent_child"):
        strategy = "fixed"
    if strategy == "topic":
        strategy = "parent_child"  # 旧策略名统一到父子切片（主题结构感知）
    stored_path = kb_root() / str(doc["user_id"]) / doc["stored_name"]
    if not stored_path.exists():
        raise KbNotFound("源文件已丢失，无法重新解析")

    # 旧 chunk 即将被替换 → 无条件清理对应向量
    # （不依赖 vectorized 标记：该标记可能因吞异常被误置 0，导致旧向量残留被检索到）
    try:
        from backend.service.kb.kb_retriever import unvectorize_document
        unvectorize_document(user_id, doc_id)
    except Exception as e:  # noqa: BLE001
        logger.opt(exception=True).warning(
            f"[KB] 重解析时清理向量失败 doc_id={doc_id}（旧向量可能残留）: {e}"
        )

    conn = get_conn()
    try:
        conn.execute("UPDATE kb_documents SET status = 'parsing', vectorized = 0 WHERE id = %s", (doc_id,))
        conn.commit()
    finally:
        conn.close()

    try:
        result = await asyncio.to_thread(
            _parse_and_chunk, str(stored_path), parser_pref,
            chunk_size, chunk_overlap, strategy, doc.get("original_name", ""),
        )
        status = "needs_ocr" if result["scanned"] else "parsed"
        conn = get_conn()
        try:
            conn.execute("DELETE FROM kb_chunks WHERE document_id = %s", (doc_id,))
            conn.execute("DELETE FROM kb_topics WHERE document_id = %s", (doc_id,))
            topic_id_map = _insert_topics(conn, doc_id, result["sections"]) if result["sections"] else {}
            _insert_chunks(conn, doc_id, result["chunks"], strategy, topic_id_map)
            conn.execute(
                "UPDATE kb_documents SET status = %s, parser = %s, page_count = %s, "
                "char_count = %s, chunk_count = %s, chunk_size = %s, chunk_overlap = %s, "
                "chunk_strategy = %s, content_text = %s, error_message = '' WHERE id = %s",
                (status, result["parser"], result["page_count"], result["char_count"],
                 len(result["chunks"]), chunk_size, chunk_overlap, strategy,
                 result["text"], doc_id),
            )
            conn.commit()
        finally:
            conn.close()

        # BM25 内存索引失效
        try:
            from backend.service.kb.kb_retriever import invalidate_bm25_cache
            invalidate_bm25_cache(user_id)
        except Exception:  # noqa: BLE001
            pass

        # 重新解析后自动向量化（如果 embedding 配置存在）
        try:
            from backend.service.kb.kb_retriever import vectorize_document
            vectorize_document(user_id, doc_id)
            logger.info(f"[KB] 重新解析后自动向量化完成 doc_id={doc_id}")
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[KB] 重新解析后自动向量化跳过 doc_id={doc_id}: {e}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"[KB] 重新解析失败 doc_id={doc_id}: {e}")
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE kb_documents SET status = 'failed', error_message = ? WHERE id = ?",
                (str(e)[:1000], doc_id),
            )
            conn.commit()
        finally:
            conn.close()
        raise KbInvalidFile(f"重新解析失败: {e}")

    return get_document(user_id, doc_id, permissions)


# ── 内部工具 ──

def _fetch_owned_doc(user_id: int, doc_id: int, permissions: set) -> dict:
    """按 id 查文档并校验归属（非本人且无 kb.manage → 404 语义）。"""
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM kb_documents WHERE id = %s", (doc_id,))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()
    if not rows:
        raise KbNotFound(f"文档不存在: id={doc_id}")
    doc = rows[0]
    if doc["user_id"] != user_id and "kb.manage" not in permissions:
        raise KbNotFound(f"文档不存在: id={doc_id}")
    return doc


def _serialize_doc(doc: dict) -> dict:
    """行 → API 输出（去掉存储内部名，加回 sha256 摘要）。"""
    return {
        "id": doc["id"],
        "kb_id": doc.get("kb_id"),
        "user_id": doc["user_id"],
        "original_name": doc["original_name"],
        "ext": doc["ext"],
        "size_bytes": doc["size_bytes"],
        "sha256": doc.get("sha256", ""),
        "page_count": doc.get("page_count", 0),
        "char_count": doc.get("char_count", 0),
        "chunk_count": doc.get("chunk_count", 0),
        "status": doc.get("status", "parsed"),
        "parser": doc.get("parser", "builtin"),
        "chunk_size": doc.get("chunk_size", _DEFAULT_CHUNK_SIZE),
        "chunk_overlap": doc.get("chunk_overlap", _DEFAULT_CHUNK_OVERLAP),
        "chunk_strategy": doc.get("chunk_strategy", "fixed"),
        "error_message": doc.get("error_message", ""),
        "vectorized": bool(doc.get("vectorized", 0)),
        "created_at": str(doc.get("created_at") or ""),
        "updated_at": str(doc.get("updated_at") or ""),
    }
