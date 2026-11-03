---
name: shell-scripting
category: 工程
author: admin
description: "Shell 脚本编写最佳实践 — 错误处理、参数解析、跨平台兼容"
version: 1.0.0
metadata:
  hermes:
    tags: [Engineering, DevOps, Scripting]
    platforms: [macos, linux]
    requires_toolsets:
      - terminal
---

# Shell 脚本编写

编写健壮、可维护的 Shell 脚本的最佳实践。

## 何时使用

- 需要自动化重复性任务
- 编写部署/构建脚本
- 批量文件处理
- 系统监控和告警

## 脚本模板

```bash
#!/usr/bin/env bash
set -euo pipefail  # 严格模式

### 配置
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

### 帮助信息
usage() {
    cat <<EOF
用法: $(basename "$0") [选项] <参数>

选项:
    -h, --help      显示帮助
    -o, --output DIR  输出目录（默认: ./output）

示例:
    $(basename "$0") -o /tmp/out input.txt
EOF
}

### 参数解析
OUTPUT_DIR="./output"
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)    usage; exit 0 ;;
        -o|--output)  OUTPUT_DIR="$2"; shift 2 ;;
        *)            break ;;
    esac
done

### 主逻辑
main() {
    mkdir -p "$OUTPUT_DIR"
    echo "处理完成 → $OUTPUT_DIR"
}

main "$@"
```

## 关键原则

1. **严格模式** — `set -euo pipefail` 让错误立即退出
2. **只读变量** — 用 `readonly` 保护常量
3. **双引号变量** — 防止空格分割，始终用 `"$var"`
4. **函数化** — 用函数组织逻辑，`main "$@"` 入口
5. **错误处理** — 关键步骤检查返回值
6. **清理** — 用 `trap cleanup EXIT` 注册清理函数

## 安全注意事项

- 不要用 `eval` 执行用户输入
- 文件路径用变量时检查是否存在
- `rm -rf` 前确认路径不是 `/` 或空
- 敏感信息用环境变量，不硬编码

## 调试技巧

```bash
set -x    # 打印每条执行命令
set +x    # 关闭
bash -n script.sh   # 语法检查（不执行）
shellcheck script.sh # 静态分析
```
