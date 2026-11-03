"""构建指纹。开发环境为占位值；发布构建时由 backend/scripts/gen_build_info.sh 覆写。

版本取证只认指纹（重构蓝图 v1.9 不变量 B-4）：/version 端点读取本文件，
部署机源码 grep 不作为运行版本证据。
"""

BUILD_INFO = {
    "commit": "dev",
    "branch": "dev",
    "build_time": None,
    "dirty": None,
}
