-- 0002_models_key: model_configs 密钥列语义明确化——存 AES-GCM 密文（旧列名 api_key_ref 暗示引用，实际沿用旧实现直接存密文）。
ALTER TABLE model_configs RENAME COLUMN api_key_ref TO api_key_encrypted;
