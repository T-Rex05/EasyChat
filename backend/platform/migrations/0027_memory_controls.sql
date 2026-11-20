-- Memory namespace and idempotent correction receipts, without message bodies.
ALTER TABLE memories ADD COLUMN persona_id TEXT;
ALTER TABLE memories ADD COLUMN is_shared INTEGER NOT NULL DEFAULT 0 CHECK (is_shared IN (0, 1));
CREATE INDEX idx_memories_owner_namespace ON memories(owner_id, persona_id, is_shared, status, recorded_at DESC);

CREATE TABLE memory_channel_operations (
    owner_id         INTEGER NOT NULL REFERENCES users(id),
    channel_event_id TEXT NOT NULL,
    action           TEXT NOT NULL,
    memory_id        TEXT NOT NULL REFERENCES memories(id),
    result_version   INTEGER NOT NULL,
    PRIMARY KEY (owner_id, channel_event_id, action)
);

-- Existing tombstones could retain quotes, tags and feedback. Existing forget hashes are retained.
UPDATE memory_signals
SET payload = '{}', error = '',
    state = CASE WHEN state IN ('processed', 'rejected') THEN state ELSE 'rejected' END
WHERE CASE WHEN json_valid(payload) THEN json_extract(payload, '$.memory_id') END IN (
    SELECT id FROM memories WHERE owner_id = memory_signals.owner_id AND status = 'deleted'
);
UPDATE jobs
SET payload = '{}', last_error = NULL
WHERE kind = 'memory.confirm' AND EXISTS (
    SELECT 1
    FROM memories AS m,
         json_each(CASE WHEN json_valid(m.source_refs) THEN m.source_refs ELSE '[]' END) AS ref
    WHERE m.owner_id = jobs.owner_id AND m.status = 'deleted'
      AND CASE WHEN ref.type = 'object' THEN json_extract(ref.value, '$.ref') END = CASE
          WHEN json_valid(jobs.payload) THEN json_extract(jobs.payload, '$.run_id')
      END
);
-- Cancel queued legacy confirmations before their source references are erased.
CREATE TEMP TABLE forgotten_memory_deliveries AS
SELECT DISTINCT d.id
FROM memories AS m
CROSS JOIN json_each(CASE WHEN json_valid(m.source_refs) THEN m.source_refs ELSE '[]' END) AS ref
JOIN deliveries AS d ON d.owner_id = m.owner_id AND d.dedup_key = 'memory-confirm:' || CASE
    WHEN ref.type = 'object' THEN NULLIF(json_extract(ref.value, '$.ref'), '')
END
WHERE m.status = 'deleted' AND d.source = 'memory' AND d.status IN ('pending', 'retry_wait');

UPDATE delivery_parts SET content = '', error = ''
WHERE status IN ('pending', 'failed') AND delivery_id IN (SELECT id FROM forgotten_memory_deliveries);
UPDATE deliveries
SET status = 'cancelled', content_text = '', error = '',
    updated_at = strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')
WHERE id IN (SELECT id FROM forgotten_memory_deliveries);
DROP TABLE temp.forgotten_memory_deliveries;

DELETE FROM memory_revisions WHERE memory_id IN (SELECT id FROM memories WHERE status = 'deleted');
DELETE FROM memory_tags WHERE memory_id IN (SELECT id FROM memories WHERE status = 'deleted');
DELETE FROM memory_feedback WHERE memory_id IN (SELECT id FROM memories WHERE status = 'deleted');
UPDATE memories SET supersedes = NULL
WHERE supersedes IN (SELECT id FROM memories WHERE status = 'deleted');
UPDATE memories
SET content = '', source_refs = '[]', scope = 'user', event_at = NULL, supersedes = NULL
WHERE status = 'deleted';
UPDATE forget_rules SET reason = '' WHERE reason != '';
