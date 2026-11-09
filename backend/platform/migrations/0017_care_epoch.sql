-- 0017_care_epoch：删除/关闭/降低主动性时推进 care 代际。
-- 只追加；updated_at 仍表示任意资料变更，不能被当作“care 已失效”的标记。

ALTER TABLE assistant_profiles ADD COLUMN care_epoch_at TEXT NOT NULL DEFAULT '';
