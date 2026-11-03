"""版本化迁移 SQL 目录。每个文件 `NNNN_名称.sql` 是一个原子迁移。"""
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent
