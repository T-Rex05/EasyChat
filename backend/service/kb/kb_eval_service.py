"""
知识库 RAG 分层评测服务层

- 测评集 / 题目 CRUD（kb.eval 看自己的，kb.manage 看全部）
- 后台运行评测：检索层指标（确定性）+ 生成层指标（RAGAS LLM 裁判）
- run 状态机：running → done/failed，progress {done,total} 供前端轮询
"""
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional, Set

from backend.db.schema import get_conn
from backend.service.kb.kb_eval_metrics import (
    aggregate_metrics,
    compute_retrieval_metrics,
)
from backend.utils.log_utils import log, rag

logger = log

_MAX_ITEMS_PER_RUN = 50

_RETRIEVAL_KEYS = ["recall_at_k", "mrr", "ndcg_at_k", "precision_at_k"]
_JUDGE_KEYS = ["faithfulness", "answer_relevancy", "context_recall", "answer_correctness"]


class EvalError(Exception):
    """评测业务异常基类"""


class EvalNotFound(EvalError):
    """资源不存在或不属于当前用户 → 404"""


class EvalInvalid(EvalError):
    """参数/状态不合法 → 400"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json_loads(raw, default):
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _json_dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _mask_url_params(url: str) -> str:
    """掩码 URL 中的敏感查询参数（如 api_key, token, key 等）"""
    if not url:
        return ""
    try:
        from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

        parsed = urlparse(url)
        if not parsed.query:
            return url
        params = parse_qs(parsed.query, keep_blank_values=True)
        masked = {}
        for k, v in params.items():
            key_lower = k.lower()
            if key_lower in ("api_key", "key", "token", "secret", "password", "apikey"):
                masked[k] = "***"
            else:
                masked[k] = v[0] if v else ""
        new_query = urlencode(masked)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
    except Exception:
        # 解析失败时返回截断的 URL
        return url[:50] + "..." if len(url) > 50 else url


def search_chunks(
    user_id: int, permissions: Set[str], keyword: str,
    page: int = 1, page_size: int = 20, document_id: Optional[int] = None,
) -> dict:
    """跨文档按关键词搜索 chunk（GT 标注辅助；kb.manage 可搜全部用户）。
    
    父子分片策略：始终排除子片（kind='child'），因为 GT 标注应该标注父片，
    检索时也是返回父片。子片只用于向量检索，不应出现在 GT 选择器中。
    """
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    offset = (page - 1) * page_size

    where = ["c.kind != 'child'"]  # 始终排除子片
    params: List = []
    if keyword.strip():
        where.append("c.content LIKE %s")
        params.append(f"%{keyword}%")
    if "kb.manage" not in permissions:
        where.append("d.user_id = %s")
        params.append(user_id)
    if document_id:
        where.append("c.document_id = %s")
        params.append(int(document_id))
    
    where_sql = " AND ".join(where) if where else "1=1"

    conn = get_conn()
    try:
        cur = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id WHERE {where_sql}",
            params,
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        total = rows[0]["cnt"] if rows else 0

        cur = conn.execute(
            f"SELECT c.id, c.document_id, c.chunk_index, c.char_count, c.content, c.kind, d.original_name, d.chunk_strategy "
            f"FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id "
            f"WHERE {where_sql} ORDER BY c.id DESC LIMIT %s OFFSET %s",
            params + [page_size, offset],
        )
        items = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [{
            "id": r["id"],
            "document_id": r["document_id"],
            "chunk_index": r["chunk_index"],
            "char_count": r["char_count"],
            "document_name": r.get("original_name") or "",
            "content": r.get("content") or "",
            "kind": r.get("kind") or "base",
            "chunk_strategy": r.get("chunk_strategy") or "fixed",
        } for r in items],
    }


# ════════════════════════════════════════════════════════════
# 内部工具
# ════════════════════════════════════════════════════════════

def _fetch_owned_set(user_id: int, set_id: int, permissions: Set[str]) -> dict:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM kb_eval_sets WHERE id = %s", (set_id,))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()
    if not rows:
        raise EvalNotFound(f"测评集不存在: id={set_id}")
    row = rows[0]
    if row["user_id"] != user_id and "kb.manage" not in permissions:
        raise EvalNotFound(f"测评集不存在: id={set_id}")
    return row


def _fetch_set_items(set_id: int) -> List[dict]:
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT * FROM kb_eval_items WHERE eval_set_id = %s ORDER BY sort_order ASC, id ASC",
            (set_id,),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()
    return [{
        "id": r["id"],
        "eval_set_id": r["eval_set_id"],
        "question": r["question"],
        "ground_truth_chunk_ids": _json_loads(r.get("ground_truth_chunk_ids"), []),
        "ground_truth_chunk_content": _json_loads(r.get("ground_truth_chunk_content"), []),
        "ground_truth_answer": r.get("ground_truth_answer") or "",
        "sort_order": r.get("sort_order", 0),
    } for r in rows]


def _fetch_owned_item(user_id: int, set_id: int, item_id: int, permissions: Set[str]) -> dict:
    _fetch_owned_set(user_id, set_id, permissions)  # 校验集合归属
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM kb_eval_items WHERE id = %s AND eval_set_id = %s", (item_id, set_id))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()
    if not rows:
        raise EvalNotFound(f"题目不存在: id={item_id}")
    return rows[0]


def _validate_gt_chunks(user_id: int, chunk_ids: List[int], permissions: Set[str]) -> List[dict]:
    """校验 GT chunk 存在且可见（本人文档的 chunk，或 kb.manage），返回 chunk 列表。"""
    chunk_ids = [int(c) for c in chunk_ids]
    if not chunk_ids:
        return []
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT c.id, c.content, c.document_id, d.user_id AS doc_owner "
            "FROM kb_chunks c JOIN kb_documents d ON d.id = c.document_id "
            f"WHERE c.id IN ({','.join('%s' for _ in chunk_ids)})",
            chunk_ids,
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()

    found = {r["id"]: r for r in rows}
    if len(found) != len(set(chunk_ids)):
        missing = [c for c in chunk_ids if c not in found]
        raise EvalInvalid(f"标注的 chunk 不存在: {missing}")
    for r in rows:
        if r["doc_owner"] != user_id and "kb.manage" not in permissions:
            raise EvalInvalid(f"chunk {r['id']} 不属于当前用户，无法标注")
    return [found[c] for c in chunk_ids]


# ════════════════════════════════════════════════════════════
# 测评集 CRUD
# ════════════════════════════════════════════════════════════

def create_eval_set(user_id: int, name: str, description: str = "") -> dict:
    name = (name or "").strip()
    if not name:
        raise EvalInvalid("测评集名称不能为空")
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO kb_eval_sets (user_id, name, description) VALUES (%s, %s, %s)",
            (user_id, name[:255], (description or "")[:512]),
        )
        conn.commit()
        set_id = cur.lastrowid
    finally:
        conn.close()
    rag.info(f"📋 [KB-Eval] 测评集已创建 id={set_id} user={user_id}")
    return {"id": set_id, "name": name, "description": description, "item_count": 0}


def list_eval_sets(user_id: int, permissions: Set[str]) -> dict:
    conn = get_conn()
    try:
        if "kb.manage" in permissions:
            cur = conn.execute("SELECT * FROM kb_eval_sets ORDER BY created_at DESC, id DESC")
        else:
            cur = conn.execute(
                "SELECT * FROM kb_eval_sets WHERE user_id = %s ORDER BY created_at DESC, id DESC",
                (user_id,),
            )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []

        cur = conn.execute(
            "SELECT eval_set_id, COUNT(*) AS cnt FROM kb_eval_items GROUP BY eval_set_id"
        )
        count_rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        counts = {r["eval_set_id"]: r["cnt"] for r in count_rows}
    finally:
        conn.close()

    items = [{
        "id": r["id"],
        "user_id": r["user_id"],
        "name": r["name"],
        "description": r.get("description") or "",
        "item_count": counts.get(r["id"], 0),
        "created_at": str(r.get("created_at") or ""),
        "updated_at": str(r.get("updated_at") or ""),
    } for r in rows]
    return {"total": len(items), "items": items}


def get_eval_set(user_id: int, set_id: int, permissions: Set[str]) -> dict:
    row = _fetch_owned_set(user_id, set_id, permissions)
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "description": row.get("description") or "",
        "items": _fetch_set_items(set_id),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def update_eval_set(user_id: int, set_id: int, permissions: Set[str], name: str = "", description: str = "") -> dict:
    _fetch_owned_set(user_id, set_id, permissions)
    name = (name or "").strip()
    if not name:
        raise EvalInvalid("测评集名称不能为空")
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE kb_eval_sets SET name = %s, description = %s WHERE id = %s",
            (name[:255], (description or "")[:512], set_id),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": set_id, "name": name}


def delete_eval_set(user_id: int, set_id: int, permissions: Set[str]) -> dict:
    _fetch_owned_set(user_id, set_id, permissions)
    conn = get_conn()
    try:
        conn.execute(
            "DELETE r FROM kb_eval_results r JOIN kb_eval_runs run ON run.id = r.run_id WHERE run.eval_set_id = %s",
            (set_id,),
        )
        conn.execute("DELETE FROM kb_eval_runs WHERE eval_set_id = %s", (set_id,))
        conn.execute("DELETE FROM kb_eval_items WHERE eval_set_id = %s", (set_id,))
        conn.execute("DELETE FROM kb_eval_sets WHERE id = %s", (set_id,))
        conn.commit()
    finally:
        conn.close()
    rag.info(f"🗑️ [KB-Eval] 测评集已删除 id={set_id}")
    return {"id": set_id, "deleted": True}


# ════════════════════════════════════════════════════════════
# 题目 CRUD
# ════════════════════════════════════════════════════════════

def add_item(
    user_id: int, set_id: int, permissions: Set[str],
    question: str, ground_truth_chunk_ids: List[int], ground_truth_answer: str = "",
) -> dict:
    _fetch_owned_set(user_id, set_id, permissions)
    question = (question or "").strip()
    if not question:
        raise EvalInvalid("问题不能为空")
    gt_chunks = _validate_gt_chunks(user_id, ground_truth_chunk_ids, permissions)
    # ★ 保存 chunk 内容快照，用于重解析后自动找回新 ID
    gt_content = [c.get("content", "") for c in gt_chunks]

    conn = get_conn()
    try:
        cur = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM kb_eval_items WHERE eval_set_id = %s", (set_id,))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        next_order = rows[0]["next_order"] if rows else 0
        cur = conn.execute(
            "INSERT INTO kb_eval_items (eval_set_id, question, ground_truth_chunk_ids, ground_truth_chunk_content, ground_truth_answer, sort_order) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (set_id, question, _json_dumps(ground_truth_chunk_ids), _json_dumps(gt_content), ground_truth_answer or "", next_order),
        )
        conn.commit()
        item_id = cur.lastrowid
    finally:
        conn.close()
    return {"id": item_id, "eval_set_id": set_id}


def update_item(
    user_id: int, set_id: int, item_id: int, permissions: Set[str],
    question: str = "", ground_truth_chunk_ids: Optional[List[int]] = None,
    ground_truth_answer: Optional[str] = None,
) -> dict:
    _fetch_owned_item(user_id, set_id, item_id, permissions)
    question = (question or "").strip()
    if not question:
        raise EvalInvalid("问题不能为空")
    gt_content_json = None
    if ground_truth_chunk_ids is not None:
        gt_chunks = _validate_gt_chunks(user_id, ground_truth_chunk_ids, permissions)
        gt_content_json = _json_dumps([c.get("content", "") for c in gt_chunks])

    conn = get_conn()
    try:
        if ground_truth_chunk_ids is not None:
            conn.execute(
                "UPDATE kb_eval_items SET question = %s, ground_truth_chunk_ids = %s, ground_truth_chunk_content = %s WHERE id = %s",
                (question, _json_dumps(ground_truth_chunk_ids), gt_content_json, item_id),
            )
        else:
            conn.execute("UPDATE kb_eval_items SET question = %s WHERE id = %s", (question, item_id))
        if ground_truth_answer is not None:
            conn.execute(
                "UPDATE kb_eval_items SET ground_truth_answer = %s WHERE id = %s",
                (ground_truth_answer, item_id),
            )
        conn.commit()
    finally:
        conn.close()
    return {"id": item_id, "updated": True}


def delete_item(user_id: int, set_id: int, item_id: int, permissions: Set[str]) -> dict:
    _fetch_owned_item(user_id, set_id, item_id, permissions)
    conn = get_conn()
    try:
        conn.execute("DELETE FROM kb_eval_items WHERE id = %s", (item_id,))
        conn.commit()
    finally:
        conn.close()
    return {"id": item_id, "deleted": True}


# ════════════════════════════════════════════════════════════
# 运行评测
# ════════════════════════════════════════════════════════════

async def run_eval_set(
    user_id: int, set_id: int, permissions: Set[str],
    top_k: int = 5, generate_answer: bool = True, judge_enabled: bool = True,
    retriever_mode: str = "auto", chunk_kind: str = "all",
    n_runs: int = 1, min_score: float = 0.0, query_rewrite: bool = False,
) -> dict:
    """创建 run 记录并启动后台执行。"""
    _fetch_owned_set(user_id, set_id, permissions)
    items = _fetch_set_items(set_id)
    if not items:
        raise EvalInvalid("测评集没有题目，请先添加问题")
    if len(items) > _MAX_ITEMS_PER_RUN:
        raise EvalInvalid(f"单次运行最多 {_MAX_ITEMS_PER_RUN} 条问题（当前 {len(items)} 条）")

    top_k = max(1, min(int(top_k or 5), 50))
    if chunk_kind not in ("all", "base", "topic", "child", "parent"):
        chunk_kind = "all"
    n_runs = max(1, min(int(n_runs or 1), 5))
    min_score = max(0.0, min(float(min_score or 0.0), 1.0))
    config = {
        "top_k": top_k,
        "generate_answer": bool(generate_answer),
        "judge_enabled": bool(judge_enabled),
        "retriever": retriever_mode,
        "chunk_kind": chunk_kind,
        "n_runs": n_runs,
        "min_score": min_score,
        "query_rewrite": bool(query_rewrite),
    }
    progress = {"done": 0, "total": len(items)}

    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO kb_eval_runs (eval_set_id, user_id, config, status, progress, started_at) "
            "VALUES (%s, %s, %s, 'running', %s, %s)",
            (set_id, user_id, _json_dumps(config), _json_dumps(progress), _now()),
        )
        conn.commit()
        run_id = cur.lastrowid
    finally:
        conn.close()

    rag.eval_start(run_id, set_id, len(items))
    asyncio.get_running_loop().create_task(
        _execute_run(run_id, user_id, set_id, items, config)
    )
    return {"run_id": run_id, "total": len(items)}


async def _execute_run(run_id: int, user_id: int, set_id: int, items: List[dict], config: dict) -> None:
    """后台执行评测（逐条检索 → 检索指标 → 可选生成答案 → 批量 RAGAS 裁判）。"""
    top_k = config["top_k"]
    generate_answer = config["generate_answer"]
    judge_enabled = config["judge_enabled"]
    n_runs = config.get("n_runs", 1)
    min_score = config.get("min_score", 0.0)
    query_rewrite = config.get("query_rewrite", False)

    try:
        # ── 构建检索器（chunk_kind: all/base/topic，用于切分策略对比）──
        from backend.service.kb.kb_retriever import get_retriever
        retriever, warnings = await asyncio.to_thread(
            get_retriever, user_id, config.get("retriever", "auto"), config.get("chunk_kind", "all")
        )

        # ── 查询重写器（可选）──
        rewriter = None
        if query_rewrite:
            try:
                from backend.service.kb.kb_query_rewriter import QueryRewriter
                model_cfg_for_rewrite = _get_model_config(user_id)
                if model_cfg_for_rewrite:
                    rewriter = QueryRewriter(model_cfg_for_rewrite)
                    warnings.append("查询重写已启用（LLM 语义压缩/纠错）")
            except Exception as e:
                warnings.append(f"查询重写初始化失败，已跳过: {e}")

        # ── 预解析 GT chunk 内容 ──
        gt_map: Dict[int, dict] = {}   # item_id -> {"ids": [...], "texts": [...], "valid_ids": [...]}
        items_to_update: List[tuple] = []  # (item_id, new_chunk_ids) — 待回写的新 ID 映射
        items_to_backfill: List[tuple] = []  # (item_id, content_list) — 待回填内容快照
        logger.info(f"[KB-Eval] 预解析 {len(items)} 题 GT chunks...")
        for idx, item in enumerate(items):
            logger.debug(f"[KB-Eval] 处理题目 {idx+1}/{len(items)}: item_id={item['id']}")
            gt_ids = [int(c) for c in item["ground_truth_chunk_ids"]]
            # ★ 子片 GT 映射为父片 GT（父子分片策略下检索返回父片 ID）
            gt_ids = await asyncio.to_thread(_map_child_to_parent, gt_ids)
            gt_contents = item.get("ground_truth_chunk_content") or []
            valid_ids, valid_texts = [], []
            logger.debug(f"[KB-Eval] 加载 GT chunks: gt_ids={gt_ids[:5]}...")
            for chunk in await asyncio.to_thread(_load_chunks, gt_ids):
                valid_ids.append(chunk["id"])
                valid_texts.append(chunk["content"] or "")
            # ★ 自动回填内容快照（老题目没有快照时补上）
            if valid_texts and not gt_contents:
                items_to_backfill.append((item["id"], valid_texts))
            # ★ 内容快照回溯：ID 失效时通过内容匹配找回新 chunk ID
            dropped = len(gt_ids) - len(valid_ids)
            if dropped > 0 and gt_contents:
                remapped = await asyncio.to_thread(
                    _remap_gt_chunks_by_content, gt_ids, gt_contents
                )
                if remapped:
                    new_ids, new_texts = remapped
                    # 合并：保留仍有效的 + 新找回的
                    seen = set(valid_ids)
                    for nid, ntxt in zip(new_ids, new_texts):
                        if nid not in seen:
                            valid_ids.append(nid)
                            valid_texts.append(ntxt)
                            seen.add(nid)
                    items_to_update.append((item["id"], valid_ids))
                    if dropped > 0:
                        warnings.append(
                            f"题目#{item['id']} 有 {dropped} 个 GT chunk 已失效，"
                            f"已通过内容匹配找回 {len(new_ids)} 个"
                        )
            elif dropped > 0 and not gt_contents:
                warnings.append(
                    f"题目#{item['id']} 有 {dropped} 个 GT chunk 已失效，"
                    f"且无内容快照无法回溯，请重新标注（编辑题目重新选择 chunk）"
                )
            gt_map[item["id"]] = {
                "ids": valid_ids,
                "texts": valid_texts,
                "dropped": len(gt_ids) - len(valid_ids),
            }
        logger.info(f"[KB-Eval] 预解析完成，共 {len(gt_map)} 个题目")

        # ★ 回写修复后的 chunk IDs
        if items_to_update:
            logger.info(f"[KB-Eval] 回写 {len(items_to_update)} 个题目的修复 chunk IDs...")
            await asyncio.to_thread(_batch_update_gt_ids, items_to_update)
        # ★ 回填内容快照
        if items_to_backfill:
            logger.info(f"[KB-Eval] 回填 {len(items_to_backfill)} 个题目的内容快照...")
            await asyncio.to_thread(_batch_backfill_gt_content, items_to_backfill)

        logger.debug(f"[KB-Eval] 开始逐条评测: generate_answer={generate_answer}, judge_enabled={judge_enabled}")

        # ─ 逐条执行 ──
        model_cfg = _get_model_config(user_id)
        if (generate_answer or judge_enabled) and model_cfg is None:
            warnings.append("未配置 LLM 模型，生成答案/裁判功能跳过（仅评测检索层）")

        # ★ 预检模型配置：如果 chat key 无效，自动回退到 embedding 配置（保留原模型名）
        if model_cfg and (generate_answer or judge_enabled):
            logger.debug(f"[KB-Eval] 验证模型: {model_cfg.get('model_name')}")
            if not await asyncio.to_thread(_verify_model_config, model_cfg):
                logger.info(f"[KB-Eval] 模型配置验证失败，尝试回退...")
                fallback = await asyncio.to_thread(_get_embedding_model_config)
                if fallback:
                    # ★ 保留原模型名（embedding 网关通常支持同样的模型）
                    fallback["model_name"] = model_cfg["model_name"]
                    # 掩码敏感 URL 参数（如 api_key）
                    _safe_url = _mask_url_params(fallback.get("api_url", ""))
                    logger.info(f"[KB-Eval] Chat 模型 Key 无效，回退到 Embedding 网关 (model={model_cfg['model_name']}, url={_safe_url})")
                    model_cfg = fallback
                    warnings.append(f"⚠️ 聊天模型 API Key 无效，已自动回退到 Embedding 模型网关（模型名 {model_cfg['model_name']} 不变）")
                else:
                    warnings.append("⚠️ 聊天模型 API Key 无效，且无可用 Embedding 配置回退，答案生成和裁判将跳过")
                    model_cfg = None

        samples: List[dict] = []
        result_ids: List[int] = []
        done = 0
        answer_fail_count = 0  # ★ 跟踪答案生成失败次数

        # ★ 2 路并发评测
        semaphore = asyncio.Semaphore(2)

        async def _process_one(item: dict) -> tuple:
            """处理单道题目，返回 (sample, result_id_or_None, error_or_None, is_answer_fail)"""
            async with semaphore:
                nonlocal answer_fail_count
                item_answer_fail = False
                try:
                    query = item["question"]
                    if rewriter is not None:
                        try:
                            rewritten = await asyncio.to_thread(rewriter.rewrite, query)
                            if rewritten and rewritten != query:
                                query = rewritten
                        except Exception:
                            pass

                    retrieved = await asyncio.to_thread(retriever.retrieve, query, top_k)
                    retrieved = _dedup_parent_child_chunks(retrieved)

                    if min_score > 0:
                        retrieved = [
                            r for r in retrieved
                            if (r.get("score") or 0) >= min_score or r.get("score") is None
                        ]

                    refused = False
                    refuse_threshold = config.get("refuse_threshold", 0.0)
                    if refuse_threshold > 0 and retrieved:
                        max_score = max((r.get("score") or 0) for r in retrieved)
                        if max_score < refuse_threshold:
                            refused = True

                    for r in retrieved:
                        r["is_gt"] = bool(r.get("chunk_id") in gt_map[item["id"]]["ids"])
                    metrics = compute_retrieval_metrics(
                        gt_map[item["id"]]["ids"],
                        [r.get("chunk_id") for r in retrieved if r.get("chunk_id") is not None],
                        top_k,
                    )
                    if refused:
                        metrics["refused"] = True

                    answer = ""
                    if not refused and generate_answer and model_cfg is not None:
                        contexts = [r["content"] for r in retrieved if r.get("content")]
                        answer = await asyncio.to_thread(
                            _generate_answer, model_cfg, item["question"], contexts
                        )
                        if not answer:
                            item_answer_fail = True

                    sample = {
                        "question": item["question"],
                        "answer": answer,
                        "contexts": [r["content"] for r in retrieved if r.get("content")],
                        "gt_contexts": gt_map[item["id"]]["texts"],
                        "gt_answer": item["ground_truth_answer"] or "",
                    }

                    conn = get_conn()
                    try:
                        cur = conn.execute(
                            "INSERT INTO kb_eval_results (run_id, item_id, question, retrieved_chunks, metrics, answer) "
                            "VALUES (%s, %s, %s, %s, %s, %s)",
                            (run_id, item["id"], item["question"],
                             _json_dumps(retrieved), _json_dumps(metrics), answer),
                        )
                        conn.commit()
                        rid = cur.lastrowid
                    finally:
                        conn.close()

                    return sample, rid, None, item_answer_fail

                except Exception as e:  # noqa: BLE001
                    logger.error(f"[KB-Eval] 题目 {item['id']} 评测失败: {e}")
                    conn = get_conn()
                    try:
                        cur = conn.execute(
                            "INSERT INTO kb_eval_results (run_id, item_id, question, retrieved_chunks, metrics) "
                            "VALUES (%s, %s, %s, '[]', %s)",
                            (run_id, item["id"], item["question"], _json_dumps({"error": str(e)[:500]})),
                        )
                        conn.commit()
                        rid = cur.lastrowid
                    finally:
                        conn.close()
                    sample = {
                        "question": item["question"], "answer": "",
                        "contexts": [], "gt_contexts": gt_map[item["id"]]["texts"],
                        "gt_answer": item["ground_truth_answer"] or "",
                    }
                    return sample, rid, e, False

        tasks = [_process_one(item) for item in items]
        results = await asyncio.gather(*tasks)

        for sample, rid, err, is_answer_fail in results:
            samples.append(sample)
            if rid is not None:
                result_ids.append(rid)
            if is_answer_fail:
                answer_fail_count += 1
            done += 1
            _update_progress(run_id, done, len(items))

        # ── 批量 RAGAS 裁判 ──
        # ★ 答案生成失败警告
        if generate_answer and answer_fail_count > 0:
            if answer_fail_count >= len(items):
                warnings.append(f"⚠️ 答案生成全部失败（{answer_fail_count}/{len(items)} 题）。请检查「系统配置 → 聊天模型」的 API Key 是否有效")
            else:
                warnings.append(f"⚠️ 答案生成部分失败（{answer_fail_count}/{len(items)} 题），裁判指标可能不完整")
        if generate_answer and model_cfg is None:
            warnings.append("⚠️ 未配置聊天模型，答案生成和裁判跳过。请在「系统配置 → 聊天模型」中配置")

        if judge_enabled and model_cfg is not None and any(s["answer"] for s in samples):
            # ★ 裁判阶段 - 使用 RAGAS
            _update_progress(run_id, done, len(items), stage="judge", message="正在进行 RAGAS 裁判...")

            from backend.service.kb.kb_eval_metrics import compute_ragas_metrics_async
            # 直接 await 异步函数
            judge_results, judge_warnings = await compute_ragas_metrics_async(samples, model_cfg, n_runs)
            warnings.extend(judge_warnings)
            logger.info(f"[KB-Eval] RAGAS评测完成，计算了 {len(judge_results)} 个结果")
            
            # 批量更新 judge_metrics
            conn = get_conn()
            try:
                for rid, jr in zip(result_ids, judge_results):
                    conn.execute(
                        "UPDATE kb_eval_results SET judge_metrics = %s WHERE id = %s",
                        (_json_dumps(jr), rid),
                    )
                conn.commit()
            finally:
                conn.close()

        # ── 六态分类（确定性，覆盖裁判跳过/部分失败的全部路径）──
        await asyncio.to_thread(_classify_run_results, run_id)

        # ── 聚合 + 完成 ──
        agg = await asyncio.to_thread(_aggregate_run, run_id)
        agg["warnings"] = warnings[:20]
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE kb_eval_runs SET status = 'done', metrics = %s, finished_at = %s WHERE id = %s",
                (_json_dumps(agg), _now(), run_id),
            )
            conn.commit()
        finally:
            conn.close()
        rag.eval_complete(run_id, {})

        # ── 结算关联的优化建议（verifying → verified/failed）──
        _settle_linked_suggestions(run_id)

    except Exception as e:  # noqa: BLE001
        rag.error(f"[KB-Eval] 评测运行失败 run_id={run_id}: {e}")
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE kb_eval_runs SET status = 'failed', error = %s, finished_at = %s WHERE id = %s",
                (str(e)[:2000], _now(), run_id),
            )
            conn.commit()
        finally:
            conn.close()
        _settle_linked_suggestions(run_id)


def _settle_linked_suggestions(run_id: int) -> None:
    """run 结束（done/failed）后结算引用了该 run 的优化建议。失败不影响主流程。"""
    try:
        from backend.service.kb.kb_eval_suggestion import settle_verification
        settle_verification(run_id)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[KB-Eval] 建议结算跳过: {e}")


def _load_chunks(chunk_ids: List[int]) -> List[dict]:
    """批量读取 chunk（过滤失效）。"""
    if not chunk_ids:
        return []
    conn = get_conn()
    try:
        cur = conn.execute(
            f"SELECT id, content FROM kb_chunks WHERE id IN ({','.join('%s' for _ in chunk_ids)})",
            chunk_ids,
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    except Exception as e:
        logger.error(f"[KB-Eval] _load_chunks 失败: {e}")
        return []
    finally:
        conn.close()
    by_id = {r["id"]: r for r in rows}
    return [by_id[c] for c in chunk_ids if c in by_id]


def _map_child_to_parent(chunk_ids: List[int]) -> List[int]:
    """
    将子片 ID 映射为父片 ID。
    
    父子分片策略下：
    - 向量库存储子片，检索命中后返回父片 ID
    - GT 应标注父片 ID，但旧数据可能标注了子片 ID
    - 此函数将子片 GT 映射为父片 GT
    """
    if not chunk_ids:
        return chunk_ids
    
    conn = get_conn()
    try:
        # 查询这些 chunk 的类型和父片 ID
        placeholders = ','.join('%s' for _ in chunk_ids)
        cur = conn.execute(
            f"SELECT id, kind, parent_chunk_id FROM kb_chunks WHERE id IN ({placeholders})",
            chunk_ids,
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()
    
    # 构建 ID -> 行 的映射
    by_id = {r["id"]: r for r in rows}
    
    # 映射子片到父片
    result = []
    child_count = 0
    for cid in chunk_ids:
        row = by_id.get(cid)
        if row and row.get("kind") == "child" and row.get("parent_chunk_id"):
            # 子片 -> 父片
            result.append(int(row["parent_chunk_id"]))
            child_count += 1
        else:
            result.append(cid)
    
    if child_count > 0:
        logger.info(f"[KB-Eval] 映射 {child_count} 个子片 GT 为父片 GT")
    
    return result


def _dedup_parent_child_chunks(retrieved: List[dict]) -> List[dict]:
    """父子分片去重：当 parent 和 child 内容前 100 字符相同时，只保留排在前面的（分数更高的）。

    父子分片策略下，同一文档的 parent chunk 和 child chunk 内容高度重叠，
    检索时经常同时命中，导致 top-K 中出现重复内容。
    """
    if not retrieved:
        return retrieved
    seen_prefixes: dict = {}  # content_prefix -> index in result
    deduped = []
    for r in retrieved:
        content = (r.get("content") or "").strip()
        # 用前 100 字符作为指纹（跳过 markdown 标题行的差异）
        prefix = content[:100] if len(content) >= 100 else content
        # 去掉开头的 markdown 标题行（# 开头），只比较正文
        body_lines = [ln for ln in prefix.split("\n") if ln.strip() and not ln.strip().startswith("#")]
        fingerprint = "\n".join(body_lines)[:80] if body_lines else prefix[:80]

        if fingerprint in seen_prefixes:
            # 重复：跳过（保留先出现的，即分数更高的）
            continue
        seen_prefixes[fingerprint] = len(deduped)
        deduped.append(r)
    return deduped


def _remap_gt_chunks_by_content(
    old_ids: List[int], contents: List[str]
) -> Optional[tuple]:
    """通过内容匹配找回因文档重新解析而失效的 GT chunk 新 ID。

    策略：
    1. 先尝试精确匹配前 200 字符
    2. 如果失败，改用模糊匹配（前 80 字符 LIKE 查询）

    Returns:
        (new_ids, new_texts) 或 None（无匹配）
    """
    if not contents:
        return None
    conn = get_conn()
    try:
        new_ids, new_texts = [], []
        for content in contents:
            if not content:
                continue
            # 用内容前 200 字符做精确匹配指纹
            fingerprint = content[:200].strip()
            if not fingerprint:
                continue
            
            # 策略1：精确匹配前 200 字符
            cur = conn.execute(
                "SELECT id, content FROM kb_chunks WHERE LEFT(content, 200) = %s LIMIT 1",
                (fingerprint,),
            )
            row = cur.fetchone()
            
            # 策略2：如果精确匹配失败，用前 80 字符做模糊匹配
            if not row and len(fingerprint) >= 50:
                fuzzy_fingerprint = fingerprint[:80].strip()
                if fuzzy_fingerprint:
                    cur = conn.execute(
                        "SELECT id, content FROM kb_chunks WHERE content LIKE %s LIMIT 1",
                        (f"%{fuzzy_fingerprint}%",),
                    )
                    row = cur.fetchone()
            
            if row:
                new_ids.append(row["id"])
                new_texts.append(row.get("content", "") or "")
        return (new_ids, new_texts) if new_ids else None
    finally:
        conn.close()


def _batch_update_gt_ids(updates: List[tuple]) -> None:
    """批量回写修复后的 GT chunk IDs 到 kb_eval_items。"""
    if not updates:
        return
    conn = get_conn()
    try:
        for item_id, new_ids in updates:
            conn.execute(
                "UPDATE kb_eval_items SET ground_truth_chunk_ids = %s WHERE id = %s",
                (_json_dumps(new_ids), item_id),
            )
        conn.commit()
        logger.info(f"[KB-Eval] 已回写 {len(updates)} 道题目的 GT chunk ID 映射")
    finally:
        conn.close()


def _batch_backfill_gt_content(updates: List[tuple]) -> None:
    """批量回填 GT chunk 内容快照（老题目没有快照时自动补上）。"""
    if not updates:
        return
    conn = get_conn()
    try:
        for item_id, contents in updates:
            conn.execute(
                "UPDATE kb_eval_items SET ground_truth_chunk_content = %s WHERE id = %s",
                (_json_dumps(contents), item_id),
            )
        conn.commit()
        logger.info(f"[KB-Eval] 已回填 {len(updates)} 道题目的 GT chunk 内容快照")
    finally:
        conn.close()


def _update_progress(run_id: int, done: int, total: int, stage: str = "retrieve", message: str = "") -> None:
    """更新评测运行进度。

    Args:
        run_id: 运行 ID
        done: 已完成数量
        total: 总数量
        stage: 当前阶段（retrieve / judge / aggregate）
        message: 进度提示消息
    """
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE kb_eval_runs SET progress = %s WHERE id = %s",
            (_json_dumps({"done": done, "total": total, "stage": stage, "message": message}), run_id),
        )
        conn.commit()
    finally:
        conn.close()


def _classify_run_results(run_id: int, thresholds: Optional[Dict] = None) -> None:
    """对 run 的全部结果做七态分类并落库（幂等，可重复执行）。
    thresholds: 可选分类阈值，不传则从 DB 读取用户配置。
    """
    from backend.service.kb.kb_eval_metrics import classify_result

    # 如果未传入阈值，从 DB 读取用户配置
    if thresholds is None:
        thresholds = get_classify_thresholds()

    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT id, metrics, judge_metrics FROM kb_eval_results WHERE run_id = %s", (run_id,)
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        for r in rows:
            cls = classify_result(
                _json_loads(r.get("metrics"), {}),
                _json_loads(r.get("judge_metrics"), {}),
                thresholds=thresholds,
            )
            conn.execute(
                "UPDATE kb_eval_results SET classification = %s WHERE id = %s", (cls, r["id"])
            )
        conn.commit()
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════
# 分类阈值配置（持久化到 trace_config KV 表）
# ════════════════════════════════════════════════════════════

_EVAL_THRESHOLD_KEYS = {
    "eval_threshold_judge_pass": ("judge_pass", 0.6),
    "eval_threshold_wrong_answer_correctness": ("wrong_answer_correctness", 0.3),
    "eval_threshold_complete_faith": ("complete_faith_threshold", 0.9),
    "eval_threshold_wrong_answer_faith": ("wrong_answer_faith_threshold", 0.7),
}


def get_classify_thresholds() -> Dict:
    """从 DB 读取用户配置的分类阈值，未配置的用默认值。"""
    from backend.service.trace.config import get_config
    from backend.service.kb.kb_eval_metrics import DEFAULT_THRESHOLDS
    result = dict(DEFAULT_THRESHOLDS)
    for db_key, (field, _default) in _EVAL_THRESHOLD_KEYS.items():
        val = get_config(db_key, "")
        if val:
            try:
                result[field] = float(val)
            except (ValueError, TypeError):
                pass
    return result


def set_classify_thresholds(thresholds: Dict) -> Dict:
    """保存分类阈值到 DB，返回实际存储的值。"""
    from backend.service.trace.config import set_config
    saved = {}
    for db_key, (field, default) in _EVAL_THRESHOLD_KEYS.items():
        val = thresholds.get(field, default)
        try:
            val = float(val)
            val = max(0.0, min(1.0, val))  # 限制范围 [0, 1]
        except (ValueError, TypeError):
            val = default
        set_config(db_key, str(val))
        saved[field] = val
    return saved


def reclassify_all_runs(thresholds: Optional[Dict] = None) -> int:
    """用新阈值重新分类所有有裁判分数的 run，返回影响的 run 数量。"""
    if thresholds is None:
        thresholds = get_classify_thresholds()
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT DISTINCT run_id FROM kb_eval_results WHERE judge_metrics IS NOT NULL AND judge_metrics != '{}'"
        )
        run_ids = [r["run_id"] for r in cur.fetchall()]
    finally:
        conn.close()
    for rid in run_ids:
        _classify_run_results(rid, thresholds=thresholds)
    return len(run_ids)


def _aggregate_run(run_id: int) -> dict:
    """从逐条结果聚合检索层 + 生成层指标均值 + 六态计数。"""
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT metrics, judge_metrics, classification FROM kb_eval_results WHERE run_id = %s",
            (run_id,),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()

    retrieval_list, judge_list, classifications = [], [], []
    for r in rows:
        m = _json_loads(r.get("metrics"), {})
        if "error" not in m:
            retrieval_list.append(m)
        j = _json_loads(r.get("judge_metrics"), {})
        if j:
            judge_list.append(j)
        if r.get("classification"):
            classifications.append(r["classification"])

    agg: Dict[str, float] = {}
    if retrieval_list:
        agg.update(aggregate_metrics(retrieval_list))
    if judge_list:
        agg.update(aggregate_metrics(judge_list))
    agg["_count"] = len(retrieval_list)

    from backend.service.kb.kb_eval_metrics import aggregate_classifications
    agg["classifications"] = aggregate_classifications(classifications)  # type: ignore[assignment]
    return agg


# ════════════════════════════════════════════════════════════
# 运行记录查询
# ════════════════════════════════════════════════════════════

def get_run_status(run_id: int) -> str:
    """run 状态（优化建议结算/周期 runner 用）。"""
    conn = get_conn()
    try:
        cur = conn.execute("SELECT status FROM kb_eval_runs WHERE id = %s", (run_id,))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
        return rows[0]["status"] if rows else "unknown"
    finally:
        conn.close()


def get_run_metrics(run_id: int) -> dict:
    """run 聚合指标（优化建议 before/after 对比用）。"""
    return _aggregate_run(run_id)


def list_runs(user_id: int, set_id: int, permissions: Set[str]) -> dict:
    _fetch_owned_set(user_id, set_id, permissions)
    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT id, eval_set_id, config, status, progress, metrics, error, started_at, finished_at, created_at "
            "FROM kb_eval_runs WHERE eval_set_id = %s ORDER BY id DESC LIMIT 50",
            (set_id,),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()
    return {"items": [_serialize_run(r) for r in rows]}


def get_run(user_id: int, run_id: int, permissions: Set[str]) -> dict:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT * FROM kb_eval_runs WHERE id = %s", (run_id,))
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()
    if not rows:
        raise EvalNotFound(f"运行记录不存在: id={run_id}")
    run = rows[0]
    # 归属校验：run 属于用户的测评集，或 kb.manage
    _fetch_owned_set(user_id, run["eval_set_id"], permissions)

    conn = get_conn()
    try:
        cur = conn.execute(
            "SELECT * FROM kb_eval_results WHERE run_id = %s ORDER BY id ASC", (run_id,)
        )
        result_rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()

    results = [{
        "id": r["id"],
        "item_id": r["item_id"],
        "question": r["question"],
        "retrieved_chunks": _json_loads(r.get("retrieved_chunks"), []),
        "metrics": _json_loads(r.get("metrics"), {}),
        "answer": r.get("answer") or "",
        "judge_metrics": _json_loads(r.get("judge_metrics"), {}),
        "classification": r.get("classification") or "",
    } for r in result_rows]

    return {**_serialize_run(run), "results": results}


def delete_run(user_id: int, run_id: int, permissions: Set[str]) -> dict:
    get_run(user_id, run_id, permissions)  # 归属校验
    conn = get_conn()
    try:
        conn.execute("DELETE FROM kb_eval_results WHERE run_id = %s", (run_id,))
        conn.execute("DELETE FROM kb_eval_runs WHERE id = %s", (run_id,))
        conn.commit()
    finally:
        conn.close()
    return {"id": run_id, "deleted": True}


def _serialize_run(r: dict) -> dict:
    return {
        "id": r["id"],
        "eval_set_id": r["eval_set_id"],
        "config": _json_loads(r.get("config"), {}),
        "status": r.get("status", "running"),
        "progress": _json_loads(r.get("progress"), {}),
        "metrics": _json_loads(r.get("metrics"), {}),
        "error": r.get("error") or "",
        "started_at": str(r.get("started_at") or ""),
        "finished_at": str(r.get("finished_at") or ""),
        "created_at": str(r.get("created_at") or ""),
    }


def compare_runs(user_id: int, run_ids: List[int], permissions: Set[str]) -> dict:
    """
    多次 run 指标对比。

    Returns:
        {
            "runs": [{"id", "config", "status", "metrics", "started_at", "finished_at"}, ...],
            "metric_comparison": {
                "recall_at_k": {"values": [0.8, 0.85, 0.9], "delta": +0.1},
                ...
            },
        }
    """
    if not run_ids:
        return {"runs": [], "metric_comparison": {}}

    conn = get_conn()
    try:
        placeholders = ",".join("%s" for _ in run_ids)
        cur = conn.execute(
            f"SELECT * FROM kb_eval_runs WHERE id IN ({placeholders}) ORDER BY id ASC",
            run_ids,
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else []
    finally:
        conn.close()

    runs = []
    all_metric_keys = set()
    for r in rows:
        # 权限校验
        set_row = None
        conn2 = get_conn()
        try:
            cur2 = conn2.execute("SELECT user_id FROM kb_eval_sets WHERE id = %s", (r["eval_set_id"],))
            set_rows = cur2.fetchall() if hasattr(cur2, "fetchall") else []
            if set_rows:
                set_row = set_rows[0]
        finally:
            conn2.close()
        if set_row and set_row["user_id"] != user_id and "kb.manage" not in permissions:
            continue

        run_data = _serialize_run(r)
        runs.append(run_data)
        metrics = run_data.get("metrics") or {}
        for k, v in metrics.items():
            if isinstance(v, (int, float)):
                all_metric_keys.add(k)

    # 指标对比
    comparison = {}
    for key in all_metric_keys:
        values = []
        for run in runs:
            v = (run.get("metrics") or {}).get(key)
            if isinstance(v, (int, float)):
                values.append(v)
        if len(values) >= 2:
            comparison[key] = {
                "values": values,
                "delta": round(values[-1] - values[0], 4),
                "min": round(min(values), 4),
                "max": round(max(values), 4),
            }

    return {"runs": runs, "metric_comparison": comparison}


# ════════════════════════════════════════════════════════════
# LLM 配置 + 答案生成
# ════════════════════════════════════════════════════════════

def _get_model_config(user_id: int, scene: str = "") -> Optional[dict]:
    """获取用户当前模型配置（OpenAI 兼容），供答案生成与 RAGAS 裁判使用。

    Args:
        user_id: 用户 ID
        scene: 场景标识，默认使用 kb_eval 场景
    """
    try:
        from backend.controller.agent_controller import get_current_model_config
        from backend.service.scene_registry import scenes

        # 使用场景路由：kb_eval 场景（默认）
        effective_scene = scene or scenes.KB_EVAL
        cfg = get_current_model_config(user_id, scene=effective_scene)
        if not cfg or not cfg.get("api_url") or not cfg.get("api_key"):
            return None
        model = cfg.get("model_name") or "gpt-4"
        if "[" in model:
            model = model.split("[")[0]  # 模型名后缀剥离
        return {"api_url": cfg["api_url"], "api_key": cfg["api_key"], "model_name": model}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[KB-Eval] 获取模型配置失败: {e}")
        return None


def _get_embedding_model_config() -> Optional[dict]:
    """获取当前激活的 Embedding 模型配置，作为答案生成的回退。

    很多 MaaS 网关（如阿里云 MaaS）同一个 key 同时支持 embedding 和 chat completions，
    当 chat 模型 key 失效时自动回退到 embedding 配置。
    """
    try:
        from backend.rag.embeddings import _get_db_embedding_config
        cfg = _get_db_embedding_config()
        if cfg and cfg.get("base_url") and cfg.get("api_key"):
            return {"api_url": cfg["base_url"], "api_key": cfg["api_key"], "model_name": ""}
    except Exception as e:
        logger.debug(f"[KB-Eval] 获取 embedding 配置失败: {e}")
    return None


def _verify_model_config(model_cfg: dict) -> bool:
    """快速验证模型配置是否可用（发一个最小请求测试认证）。"""
    try:
        import httpx
        url = model_cfg["api_url"].rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {model_cfg['api_key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_cfg.get("model_name", "gpt-3.5-turbo"),
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        logger.debug(f"[KB-Eval] 验证模型: url={url}, model={model_cfg.get('model_name')}")
        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        logger.debug(f"[KB-Eval] 验证响应: status={resp.status_code}")
        if resp.status_code == 200:
            return True
        # 某些 API 即使 key 无效也返回非 401（如模型不存在返回 404），也算通过
        if resp.status_code != 401 and resp.status_code != 403:
            return True
        return False
    except Exception as e:
        logger.warning(f"[KB-Eval] 验证模型配置失败: {e}")
        return False


def _generate_answer(model_cfg: dict, question: str, contexts: List[str],
                     _fallback_tried: bool = False) -> str:
    """仅基于检索上下文生成答案（模拟 RAG 生成阶段）。
    认证失败时自动回退到 Embedding 模型配置（同一网关常共用 key）。
    """
    if not contexts:
        return ""

    numbered = "\n\n".join(f"[{i}] {c}" for i, c in enumerate(contexts, 1))
    prompt = (
        "你是一个知识库问答助手。请仅基于以下参考内容回答用户问题，"
        "不要引入参考内容之外的信息；若参考内容中没有答案，请回答「参考内容中未找到相关信息」。\n\n"
        f"参考内容：\n{numbered}\n\n"
        f"用户问题：{question}\n\n回答："
    )
    try:
        from backend.utils.traced_llm import traced_llm
        
        # 尝试从上下文获取 user_id
        try:
            from backend.hermes_adapter import _CURRENT_USER_ID_CTX
            uid = int(_CURRENT_USER_ID_CTX.get() or 0)
        except Exception:
            uid = 0

        resp = traced_llm.invoke(
            messages=[{"role": "user", "content": prompt}],
            scene="kb_eval",
            user_id=uid,
            source="eval",
            temperature=0,
            max_tokens=4096,
            model_override=model_cfg,
        )
        text = (resp.content or "").strip()
        return text
    except Exception as e:
        err_str = str(e)
        # ★ 认证失败 + 还没尝试过回退 → 用 embedding 配置重试
        is_auth_error = any(kw in err_str for kw in ("401", "invalid_api_key", "AuthenticationError", "Incorrect API key"))
        if is_auth_error and not _fallback_tried:
            fallback_cfg = _get_embedding_model_config()
            if fallback_cfg:
                logger.info(f"[KB-Eval] Chat 模型认证失败，回退到 Embedding 配置重试 (url={_mask_url_params(fallback_cfg.get('api_url', ''))})")
                return _generate_answer(fallback_cfg, question, contexts, _fallback_tried=True)
        logger.warning(f"[KB-Eval] 生成答案失败: {type(e).__name__}: {e}")
        return ""
