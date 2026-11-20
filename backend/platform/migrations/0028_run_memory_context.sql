-- NULL = 未记录；[] = 已记录且未召回条目。只保留 ID 和版本。
ALTER TABLE runs ADD COLUMN memory_context_refs TEXT;
