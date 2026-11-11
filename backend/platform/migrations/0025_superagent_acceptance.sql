-- 0025_superagent_acceptance: 逐项验收账本（工作包四，执行方案 §7）。
--
-- 设计：验收轮次记录一次对某 attempt 的结构化检查提交（含 requirement、
-- 汇总与 provenance 引用）；检查项记录 plan/case 合并后的逐项结果、证据
-- JSON、人工评审决定。轮次单调递增且不可改写——打回返工后提交新一轮，
-- 旧轮次保留可追溯（计划：历史记录可追溯、保留此前轮次）。
-- 时间文本统一 UTC ISO-8601；迁移只追加。
CREATE TABLE IF NOT EXISTS acceptance_rounds (
    id             TEXT    PRIMARY KEY,
    task_id        TEXT    NOT NULL,
    attempt_id     TEXT    NOT NULL DEFAULT '',
    round_no       INTEGER NOT NULL,
    requirement    TEXT    NOT NULL DEFAULT '',
    verdict        TEXT    NOT NULL,               -- pass | fail | partial
    summary_json   TEXT    NOT NULL DEFAULT '{}',  -- {total,passed,failed,blocked,skipped}
    provenance_json TEXT   NOT NULL DEFAULT '{}',  -- {branch,commit,tree,build,environment,viewport,theme}
    created_by     INTEGER NOT NULL,
    created_at     TEXT    NOT NULL,
    UNIQUE (task_id, round_no)
);
CREATE INDEX IF NOT EXISTS idx_acceptance_rounds_task
    ON acceptance_rounds(task_id, round_no DESC);

CREATE TABLE IF NOT EXISTS acceptance_checks (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id         TEXT    NOT NULL REFERENCES acceptance_rounds(id),
    item_id          TEXT    NOT NULL,             -- 检查项在计划内的标识(如 c1)
    title            TEXT    NOT NULL,
    category         TEXT    NOT NULL DEFAULT '',
    status           TEXT    NOT NULL,             -- pass | fail | blocked | skipped
    required_evidence TEXT   NOT NULL DEFAULT '[]',
    observation      TEXT    NOT NULL DEFAULT '',
    evidence_json    TEXT    NOT NULL DEFAULT '[]',-- [{path,description,type,sha256?,captured_at?,...}]
    decision         TEXT    NOT NULL DEFAULT '',  -- '' | accepted | rejected
    decided_by       INTEGER,
    decided_at       TEXT,
    decision_note    TEXT    NOT NULL DEFAULT '',
    UNIQUE (round_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_acceptance_checks_round
    ON acceptance_checks(round_id, id);
