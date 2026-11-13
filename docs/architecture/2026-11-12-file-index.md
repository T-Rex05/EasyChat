# EasyChat 全量目录与文件职责索引

日期为 2026-11-12，按本地磁盘生成。每项包含职责说明、推断依据及可提取的文件头或公开符号。该索引提供逐文件定位，入口可达性与运行架构见同目录 architecture 文档。（方法说明）

覆盖 2170 个文件、487 个目录。源码、配置、脚本、文档与资源含 Git 忽略但仍在磁盘的项目文件。依赖、缓存、运行数据及生成产物按架构文档说明用途，输出文档自身单独列于交付说明。（扫描范围）

文件名推断表示尚未逐行验证的职责，文件头为源码原文摘要。历史代码、运维脚本和上游可选技能的存在只说明文件在磁盘中。（证据口径）

## 全目录索引

- `.github/` — 仓库CI配置，子树 1 个文件。（目录位置推断）
- `.github/workflows/` — 仓库CI配置，子树 1 个文件。（目录位置推断）
- `.planning/` — 历史阶段计划、研究与验证记录，子树 63 个文件。（目录位置推断）
- `.planning/2026-11-03-easychat-design/` — 历史阶段计划、研究与验证记录，子树 5 个文件。（目录位置推断）
- `.planning/2026-11-09-project-review/` — 历史阶段计划、研究与验证记录，子树 7 个文件。（目录位置推断）
- `.planning/2026-11-09-ui-repair/` — 历史阶段计划、研究与验证记录，子树 51 个文件。（目录位置推断）
- `.planning/2026-11-09-ui-repair/backend-before/` — 历史阶段计划、研究与验证记录，子树 7 个文件。（目录位置推断）
- `.planning/2026-11-09-ui-repair/backend-before/backend/` — 历史阶段计划、研究与验证记录，子树 7 个文件。（目录位置推断）
- `.planning/2026-11-09-ui-repair/backend-before/backend/modules/` — 历史阶段计划、研究与验证记录，子树 4 个文件。（目录位置推断）
- `.planning/2026-11-09-ui-repair/backend-before/backend/modules/assistant/` — 历史阶段计划、研究与验证记录，子树 2 个文件。（目录位置推断）
- `.planning/2026-11-09-ui-repair/backend-before/backend/modules/files/` — 历史阶段计划、研究与验证记录，子树 1 个文件。（目录位置推断）
- `.planning/2026-11-09-ui-repair/backend-before/backend/modules/models/` — 历史阶段计划、研究与验证记录，子树 1 个文件。（目录位置推断）
- `.planning/2026-11-09-ui-repair/backend-before/backend/runtime/` — 历史阶段计划、研究与验证记录，子树 2 个文件。（目录位置推断）
- `.planning/2026-11-09-ui-repair/backend-before/backend/runtime/hermes/` — 历史阶段计划、研究与验证记录，子树 2 个文件。（目录位置推断）
- `.planning/2026-11-09-ui-repair/static-before/` — 历史阶段计划、研究与验证记录，子树 28 个文件。（目录位置推断）
- `.planning/2026-11-09-ui-repair/static-before/assets/` — 历史阶段计划、研究与验证记录，子树 27 个文件。（目录位置推断）
- `agent_frontend/` — Vue/Vite Web客户端，子树 64 个文件。（目录位置推断）
- `agent_frontend/src/` — Vue/Vite Web客户端，子树 50 个文件。（目录位置推断）
- `agent_frontend/src/api/` — 后端HTTP接口客户端，子树 11 个文件。（目录位置推断）
- `agent_frontend/src/components/` — Web可复用交互组件，子树 5 个文件。（目录位置推断）
- `agent_frontend/src/components/chat/` — Web可复用交互组件，子树 3 个文件。（目录位置推断）
- `agent_frontend/src/composables/` — 组合式交互和请求逻辑，子树 2 个文件。（目录位置推断）
- `agent_frontend/src/router/` — Vue/Vite Web客户端，子树 1 个文件。（目录位置推断）
- `agent_frontend/src/stores/` — 前端共享状态，子树 3 个文件。（目录位置推断）
- `agent_frontend/src/styles/` — 全局视觉样式与布局，子树 1 个文件。（目录位置推断）
- `agent_frontend/src/types/` — Vue/Vite Web客户端，子树 2 个文件。（目录位置推断）
- `agent_frontend/src/utils/` — 前端纯逻辑辅助，子树 7 个文件。（目录位置推断）
- `agent_frontend/src/views/` — Web业务页面，子树 16 个文件。（目录位置推断）
- `agent_frontend/src/views/admin/` — Web业务页面，子树 5 个文件。（目录位置推断）
- `agent_frontend/tests/` — Vue/Vite Web客户端，子树 4 个文件。（目录位置推断）
- `android_client/` — Kotlin/Compose Android客户端，子树 68 个文件。（目录位置推断）
- `android_client/app/` — Kotlin/Compose Android客户端，子树 58 个文件。（目录位置推断）
- `android_client/app/src/` — Kotlin/Compose Android客户端，子树 56 个文件。（目录位置推断）
- `android_client/app/src/debug/` — Kotlin/Compose Android客户端，子树 1 个文件。（目录位置推断）
- `android_client/app/src/main/` — Kotlin/Compose Android客户端，子树 52 个文件。（目录位置推断）
- `android_client/app/src/main/java/` — Kotlin/Compose Android客户端，子树 31 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/` — Kotlin/Compose Android客户端，子树 31 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/easychat/` — Kotlin/Compose Android客户端，子树 31 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/easychat/family/` — Kotlin/Compose Android客户端，子树 31 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/easychat/family/app/` — Kotlin/Compose Android客户端，子树 4 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/easychat/family/core/` — Kotlin/Compose Android客户端，子树 18 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/easychat/family/core/designsystem/` — Kotlin/Compose Android客户端，子树 5 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/easychat/family/core/model/` — Kotlin/Compose Android客户端，子树 1 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/easychat/family/core/network/` — Kotlin/Compose Android客户端，子树 9 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/easychat/family/core/storage/` — Kotlin/Compose Android客户端，子树 2 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/easychat/family/core/util/` — Kotlin/Compose Android客户端，子树 1 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/easychat/family/feature/` — Kotlin/Compose Android客户端，子树 9 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/easychat/family/feature/chat/` — Kotlin/Compose Android客户端，子树 2 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/easychat/family/feature/life/` — Kotlin/Compose Android客户端，子树 2 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/easychat/family/feature/onboarding/` — Kotlin/Compose Android客户端，子树 2 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/easychat/family/feature/profile/` — Kotlin/Compose Android客户端，子树 1 个文件。（目录位置推断）
- `android_client/app/src/main/java/com/easychat/family/feature/today/` — Kotlin/Compose Android客户端，子树 2 个文件。（目录位置推断）
- `android_client/app/src/main/res/` — Kotlin/Compose Android客户端，子树 20 个文件。（目录位置推断）
- `android_client/app/src/main/res/drawable/` — Kotlin/Compose Android客户端，子树 14 个文件。（目录位置推断）
- `android_client/app/src/main/res/mipmap-anydpi-v26/` — Kotlin/Compose Android客户端，子树 2 个文件。（目录位置推断）
- `android_client/app/src/main/res/values/` — Kotlin/Compose Android客户端，子树 3 个文件。（目录位置推断）
- `android_client/app/src/main/res/values-night/` — Kotlin/Compose Android客户端，子树 1 个文件。（目录位置推断）
- `android_client/app/src/test/` — Kotlin/Compose Android客户端，子树 3 个文件。（目录位置推断）
- `android_client/app/src/test/java/` — Kotlin/Compose Android客户端，子树 3 个文件。（目录位置推断）
- `android_client/app/src/test/java/com/` — Kotlin/Compose Android客户端，子树 3 个文件。（目录位置推断）
- `android_client/app/src/test/java/com/easychat/` — Kotlin/Compose Android客户端，子树 3 个文件。（目录位置推断）
- `android_client/app/src/test/java/com/easychat/family/` — Kotlin/Compose Android客户端，子树 3 个文件。（目录位置推断）
- `android_client/app/src/test/java/com/easychat/family/designsystem/` — Kotlin/Compose Android客户端，子树 2 个文件。（目录位置推断）
- `android_client/app/src/test/java/com/easychat/family/util/` — Kotlin/Compose Android客户端，子树 1 个文件。（目录位置推断）
- `android_client/gradle/` — Kotlin/Compose Android客户端，子树 3 个文件。（目录位置推断）
- `android_client/gradle/wrapper/` — Kotlin/Compose Android客户端，子树 2 个文件。（目录位置推断）
- `backend/` — 仓库根目录的配置、入口或辅助文件，子树 1490 个文件。（目录位置推断）
- `backend/config/` — 路径与模型目录等配置资料，子树 3 个文件。（目录位置推断）
- `backend/context/` — 上下文策略、任务证据与工具结果管理，子树 22 个文件。（目录位置推断）
- `backend/context/strategies/` — 上下文策略、任务证据与工具结果管理，子树 3 个文件。（目录位置推断）
- `backend/context/tool_results/` — 上下文策略、任务证据与工具结果管理，子树 13 个文件。（目录位置推断）
- `backend/hermes/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1200 个文件。（目录位置推断）
- `backend/hermes/acp_adapter/` — 内嵌 Hermes 上游源码及项目适配内容，子树 11 个文件。（目录位置推断）
- `backend/hermes/agent/` — 内嵌 Hermes 上游源码及项目适配内容，子树 168 个文件。（目录位置推断）
- `backend/hermes/agent/lsp/` — 内嵌 Hermes 上游源码及项目适配内容，子树 11 个文件。（目录位置推断）
- `backend/hermes/agent/pet/` — 内嵌 Hermes 上游源码及项目适配内容，子树 11 个文件。（目录位置推断）
- `backend/hermes/agent/pet/generate/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/agent/proxy_sources/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/agent/secret_sources/` — 内嵌 Hermes 上游源码及项目适配内容，子树 7 个文件。（目录位置推断）
- `backend/hermes/agent/transports/` — 内嵌 Hermes 上游源码及项目适配内容，子树 11 个文件。（目录位置推断）
- `backend/hermes/cron/` — 内嵌 Hermes 上游源码及项目适配内容，子树 11 个文件。（目录位置推断）
- `backend/hermes/cron/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/gateway/` — 内嵌 Hermes 上游源码及项目适配内容，子树 85 个文件。（目录位置推断）
- `backend/hermes/gateway/assets/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/gateway/builtin_hooks/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/gateway/platforms/` — 内嵌 Hermes 上游源码及项目适配内容，子树 28 个文件。（目录位置推断）
- `backend/hermes/gateway/platforms/qqbot/` — 内嵌 Hermes 上游源码及项目适配内容，子树 8 个文件。（目录位置推断）
- `backend/hermes/gateway/relay/` — 内嵌 Hermes 上游源码及项目适配内容，子树 8 个文件。（目录位置推断）
- `backend/hermes/hermes_cli/` — 内嵌 Hermes 上游源码及项目适配内容，子树 185 个文件。（目录位置推断）
- `backend/hermes/hermes_cli/dashboard_auth/` — 内嵌 Hermes 上游源码及项目适配内容，子树 13 个文件。（目录位置推断）
- `backend/hermes/hermes_cli/observability/` — 内嵌 Hermes 上游源码及项目适配内容，子树 7 个文件。（目录位置推断）
- `backend/hermes/hermes_cli/observability/schemas/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/hermes_cli/proxy/` — 内嵌 Hermes 上游源码及项目适配内容，子树 7 个文件。（目录位置推断）
- `backend/hermes/hermes_cli/proxy/adapters/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/locales/` — 内嵌 Hermes 上游源码及项目适配内容，子树 17 个文件。（目录位置推断）
- `backend/hermes/optional-mcps/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-mcps/blender/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-mcps/linear/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-mcps/n8n/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-mcps/unreal-engine/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/` — 内嵌 Hermes 上游源码及项目适配内容，子树 516 个文件。（目录位置推断）
- `backend/hermes/optional-skills/autonomous-ai-agents/` — 内嵌 Hermes 上游源码及项目适配内容，子树 7 个文件。（目录位置推断）
- `backend/hermes/optional-skills/autonomous-ai-agents/antigravity-cli/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/autonomous-ai-agents/antigravity-cli/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/autonomous-ai-agents/blackbox/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/autonomous-ai-agents/grok/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/autonomous-ai-agents/honcho/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/autonomous-ai-agents/openhands/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/blockchain/` — 内嵌 Hermes 上游源码及项目适配内容，子树 6 个文件。（目录位置推断）
- `backend/hermes/optional-skills/blockchain/evm/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/blockchain/evm/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/blockchain/hyperliquid/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/blockchain/hyperliquid/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/blockchain/solana/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/blockchain/solana/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/communication/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/communication/one-three-one-rule/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/` — 内嵌 Hermes 上游源码及项目适配内容，子树 155 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/audiocraft-audio-generation/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/audiocraft-audio-generation/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/baoyu-article-illustrator/` — 内嵌 Hermes 上游源码及项目适配内容，子树 35 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/baoyu-article-illustrator/prompts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 32 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/palettes/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/` — 内嵌 Hermes 上游源码及项目适配内容，子树 23 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/baoyu-comic/` — 内嵌 Hermes 上游源码及项目适配内容，子树 35 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/baoyu-comic/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 33 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/baoyu-comic/references/art-styles/` — 内嵌 Hermes 上游源码及项目适配内容，子树 6 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/baoyu-comic/references/layouts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 7 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/baoyu-comic/references/presets/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/baoyu-comic/references/tones/` — 内嵌 Hermes 上游源码及项目适配内容，子树 7 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/blender-mcp/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/blender-mcp/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/concept-diagrams/` — 内嵌 Hermes 上游源码及项目适配内容，子树 20 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/concept-diagrams/examples/` — 内嵌 Hermes 上游源码及项目适配内容，子树 15 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/concept-diagrams/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/concept-diagrams/templates/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/creative-ideation/` — 内嵌 Hermes 上游源码及项目适配内容，子树 28 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/creative-ideation/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 27 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/creative-ideation/references/methods/` — 内嵌 Hermes 上游源码及项目适配内容，子树 22 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/heartmula/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/hyperframes/` — 内嵌 Hermes 上游源码及项目适配内容，子树 8 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/hyperframes/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 6 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/hyperframes/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/meme-generation/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/meme-generation/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/pixel-art/` — 内嵌 Hermes 上游源码及项目适配内容，子树 7 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/pixel-art/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/pixel-art/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/tldraw-offline/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/tldraw-offline/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/unreal-mcp/` — 内嵌 Hermes 上游源码及项目适配内容，子树 6 个文件。（目录位置推断）
- `backend/hermes/optional-skills/creative/unreal-mcp/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/optional-skills/data-science/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/data-science/jupyter-notebook/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/devops/` — 内嵌 Hermes 上游源码及项目适配内容，子树 13 个文件。（目录位置推断）
- `backend/hermes/optional-skills/devops/cli/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/optional-skills/devops/cli/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/devops/docker-management/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/devops/hermes-s6-container-supervision/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/devops/pinggy-tunnel/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/devops/watchers/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/optional-skills/devops/watchers/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/dogfood/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/dogfood/adversarial-ux-test/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/email/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/email/agentmail/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/finance/` — 内嵌 Hermes 上游源码及项目适配内容，子树 16 个文件。（目录位置推断）
- `backend/hermes/optional-skills/finance/3-statement-model/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/finance/3-statement-model/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/finance/comps-analysis/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/finance/dcf-model/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/finance/dcf-model/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/finance/excel-author/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/finance/excel-author/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/finance/lbo-model/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/finance/merger-model/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/finance/pptx-author/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/finance/stocks/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/finance/stocks/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/gaming/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/gaming/minecraft-modpack-server/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/gaming/pokemon-player/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/health/` — 内嵌 Hermes 上游源码及项目适配内容，子树 9 个文件。（目录位置推断）
- `backend/hermes/optional-skills/health/fitness-nutrition/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/health/fitness-nutrition/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/health/fitness-nutrition/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/health/neuroskill-bci/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/health/neuroskill-bci/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mcp/` — 内嵌 Hermes 上游源码及项目适配内容，子树 11 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mcp/fastmcp/` — 内嵌 Hermes 上游源码及项目适配内容，子树 6 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mcp/fastmcp/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mcp/fastmcp/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mcp/fastmcp/templates/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mcp/mcp-oauth-remote-gateway/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mcp/mcp-oauth-remote-gateway/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mcp/mcp-oauth-remote-gateway/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mcp/mcporter/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/migration/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/migration/openclaw-migration/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/migration/openclaw-migration/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/` — 内嵌 Hermes 上游源码及项目适配内容，子树 112 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/accelerate/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/accelerate/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/chroma/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/chroma/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/clip/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/clip/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/faiss/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/faiss/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/flash-attention/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/flash-attention/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/guidance/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/guidance/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/huggingface-tokenizers/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/huggingface-tokenizers/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/inference/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/inference/outlines/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/inference/outlines/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/instructor/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/instructor/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/lambda-labs/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/lambda-labs/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/llava/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/llava/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/modal/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/modal/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/models/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/models/segment-anything-model/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/models/segment-anything-model/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/nemo-curator/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/nemo-curator/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/obliteratus/` — 内嵌 Hermes 上游源码及项目适配内容，子树 6 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/obliteratus/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/obliteratus/templates/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/peft/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/peft/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/pinecone/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/pinecone/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/pytorch-fsdp/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/pytorch-fsdp/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/pytorch-lightning/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/pytorch-lightning/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/qdrant/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/qdrant/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/research/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/research/dspy/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/research/dspy/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/saelens/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/saelens/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/simpo/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/simpo/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/slime/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/slime/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/stable-diffusion/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/stable-diffusion/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/tensorrt-llm/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/tensorrt-llm/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/torchtitan/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/torchtitan/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/training/` — 内嵌 Hermes 上游源码及项目适配内容，子树 17 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/training/axolotl/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/training/axolotl/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/training/trl-fine-tuning/` — 内嵌 Hermes 上游源码及项目适配内容，子树 7 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/training/trl-fine-tuning/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/training/trl-fine-tuning/templates/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/training/unsloth/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/training/unsloth/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/whisper/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/mlops/whisper/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/payments/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/payments/mpp-agent/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/payments/stripe-link-cli/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/payments/stripe-projects/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/productivity/` — 内嵌 Hermes 上游源码及项目适配内容，子树 17 个文件。（目录位置推断）
- `backend/hermes/optional-skills/productivity/canvas/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/productivity/canvas/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/productivity/here-now/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/productivity/here-now/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/productivity/memento-flashcards/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/productivity/memento-flashcards/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/productivity/shop/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/optional-skills/productivity/shop/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/productivity/shopify/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/productivity/siyuan/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/productivity/telephony/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/productivity/telephony/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/` — 内嵌 Hermes 上游源码及项目适配内容，子树 52 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/bioinformatics/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/darwinian-evolver/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/darwinian-evolver/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/darwinian-evolver/templates/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/domain-intel/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/domain-intel/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/drug-discovery/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/drug-discovery/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/drug-discovery/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/duckduckgo-search/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/duckduckgo-search/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/gitnexus-explorer/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/gitnexus-explorer/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/osint-investigation/` — 内嵌 Hermes 上游源码及项目适配内容，子树 29 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/osint-investigation/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 11 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/osint-investigation/references/sources/` — 内嵌 Hermes 上游源码及项目适配内容，子树 11 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/osint-investigation/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 16 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/osint-investigation/templates/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/parallel-cli/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/pinecone-research/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/pinecone-research/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/qmd/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/scrapling/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/searxng-search/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/research/searxng-search/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/` — 内嵌 Hermes 上游源码及项目适配内容，子树 87 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/1password/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/1password/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/godmode/` — 内嵌 Hermes 上游源码及项目适配内容，子树 9 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/godmode/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/godmode/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/godmode/templates/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/oss-forensics/` — 内嵌 Hermes 上游源码及项目适配内容，子树 8 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/oss-forensics/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/oss-forensics/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/oss-forensics/templates/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/sherlock/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/unbroker/` — 内嵌 Hermes 上游源码及项目适配内容，子树 56 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/unbroker/assets/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/unbroker/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 28 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/unbroker/references/brokers/` — 内嵌 Hermes 上游源码及项目适配内容，子树 22 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/unbroker/references/legal/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/unbroker/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 19 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/unbroker/templates/` — 内嵌 Hermes 上游源码及项目适配内容，子树 6 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/unbroker/templates/consent/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/unbroker/templates/emails/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/web-pentest/` — 内嵌 Hermes 上游源码及项目适配内容，子树 9 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/web-pentest/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/web-pentest/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/security/web-pentest/templates/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/software-development/` — 内嵌 Hermes 上游源码及项目适配内容，子树 9 个文件。（目录位置推断）
- `backend/hermes/optional-skills/software-development/code-wiki/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/optional-skills/software-development/code-wiki/templates/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/software-development/rest-graphql-debug/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/software-development/subagent-driven-development/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/optional-skills/software-development/subagent-driven-development/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/web-development/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/optional-skills/web-development/cloudflare-temporary-deploy/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/optional-skills/web-development/cloudflare-temporary-deploy/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/web-development/page-agent/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/optional-skills/yuanbao/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/plugins/` — 内嵌 Hermes 上游源码及项目适配内容，子树 21 个文件。（目录位置推断）
- `backend/hermes/plugins/browser/` — 内嵌 Hermes 上游源码及项目适配内容，子树 7 个文件。（目录位置推断）
- `backend/hermes/plugins/browser/browser_use/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/plugins/browser/browserbase/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/plugins/browser/firecrawl/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/plugins/memory/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/plugins/web/` — 内嵌 Hermes 上游源码及项目适配内容，子树 12 个文件。（目录位置推断）
- `backend/hermes/plugins/web/ddgs/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/plugins/web/exa/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/plugins/web/firecrawl/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/plugins/web/parallel/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/plugins/web/tavily/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/providers/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/skills/` — 内嵌 Hermes 上游源码及项目适配内容，子树 57 个文件。（目录位置推断）
- `backend/hermes/skills/ai-generated/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/skills/ai-generated/code-stats-report/` — 内嵌 Hermes 上游源码及项目适配内容，子树 2 个文件。（目录位置推断）
- `backend/hermes/skills/ai-generated/code-stats-report/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/automation/` — 内嵌 Hermes 上游源码及项目适配内容，子树 6 个文件。（目录位置推断）
- `backend/hermes/skills/automation/send-email/` — 内嵌 Hermes 上游源码及项目适配内容，子树 6 个文件。（目录位置推断）
- `backend/hermes/skills/automation/send-email/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/automation/send-email/scripts/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/automation/send-email/templates/` — 内嵌 Hermes 上游源码及项目适配内容，子树 3 个文件。（目录位置推断）
- `backend/hermes/skills/code-review/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/engineering/` — 内嵌 Hermes 上游源码及项目适配内容，子树 34 个文件。（目录位置推断）
- `backend/hermes/skills/engineering/agentforge-dev/` — 内嵌 Hermes 上游源码及项目适配内容，子树 18 个文件。（目录位置推断）
- `backend/hermes/skills/engineering/agentforge-dev/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 17 个文件。（目录位置推断）
- `backend/hermes/skills/engineering/agentforge-development/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/skills/engineering/agentforge-development/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/skills/engineering/event-driven-state-debugging/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/skills/engineering/event-driven-state-debugging/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/skills/engineering/legacy-code-removal/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/engineering/mysql-backend-extension/` — 内嵌 Hermes 上游源码及项目适配内容，子树 5 个文件。（目录位置推断）
- `backend/hermes/skills/engineering/mysql-backend-extension/references/` — 内嵌 Hermes 上游源码及项目适配内容，子树 4 个文件。（目录位置推断）
- `backend/hermes/skills/git-workflow/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/paper-reproduction/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/remu-assistant/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/report-writer/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/requesting-code-review/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/shell-scripting/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/skill-creator/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/system-hardening/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/systematic-debugging/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/test-driven-development/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/test-report/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/travel-planner/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/verification-before-completion/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/skills/web-research/` — 内嵌 Hermes 上游源码及项目适配内容，子树 1 个文件。（目录位置推断）
- `backend/hermes/tools/` — 内嵌 Hermes 上游源码及项目适配内容，子树 99 个文件。（目录位置推断）
- `backend/hermes/tools/environments/` — 内嵌 Hermes 上游源码及项目适配内容，子树 11 个文件。（目录位置推断）
- `backend/integrations/` — 模型、MCP、搜索、语音等外部能力适配，子树 8 个文件。（目录位置推断）
- `backend/modules/` — 按业务领域组织的公开服务与路由，子树 140 个文件。（目录位置推断）
- `backend/modules/access/` — 按业务领域组织的公开服务与路由，子树 6 个文件。（目录位置推断）
- `backend/modules/assistant/` — 按业务领域组织的公开服务与路由，子树 9 个文件。（目录位置推断）
- `backend/modules/briefing/` — 按业务领域组织的公开服务与路由，子树 4 个文件。（目录位置推断）
- `backend/modules/channels/` — 按业务领域组织的公开服务与路由，子树 13 个文件。（目录位置推断）
- `backend/modules/channels/wechat/` — 按业务领域组织的公开服务与路由，子树 6 个文件。（目录位置推断）
- `backend/modules/delivery/` — 按业务领域组织的公开服务与路由，子树 9 个文件。（目录位置推断）
- `backend/modules/evolution/` — 按业务领域组织的公开服务与路由，子树 12 个文件。（目录位置推断）
- `backend/modules/files/` — 按业务领域组织的公开服务与路由，子树 9 个文件。（目录位置推断）
- `backend/modules/inbox/` — 按业务领域组织的公开服务与路由，子树 7 个文件。（目录位置推断）
- `backend/modules/ledger/` — 按业务领域组织的公开服务与路由，子树 19 个文件。（目录位置推断）
- `backend/modules/ledger/parsers/` — 按业务领域组织的公开服务与路由，子树 5 个文件。（目录位置推断）
- `backend/modules/memory/` — 按业务领域组织的公开服务与路由，子树 9 个文件。（目录位置推断）
- `backend/modules/models/` — 按业务领域组织的公开服务与路由，子树 5 个文件。（目录位置推断）
- `backend/modules/profiles/` — 按业务领域组织的公开服务与路由，子树 6 个文件。（目录位置推断）
- `backend/modules/scheduling/` — 按业务领域组织的公开服务与路由，子树 6 个文件。（目录位置推断）
- `backend/modules/skills/` — 按业务领域组织的公开服务与路由，子树 6 个文件。（目录位置推断）
- `backend/modules/superagent/` — 按业务领域组织的公开服务与路由，子树 14 个文件。（目录位置推断）
- `backend/modules/usage/` — 按业务领域组织的公开服务与路由，子树 5 个文件。（目录位置推断）
- `backend/platform/` — SQLite、迁移、设置、持久队列和备份，子树 31 个文件。（目录位置推断）
- `backend/platform/migrations/` — SQLite、迁移、设置、持久队列和备份，子树 26 个文件。（目录位置推断）
- `backend/runtime/` — 执行引擎接口与 Hermes 适配，子树 11 个文件。（目录位置推断）
- `backend/runtime/hermes/` — 执行引擎接口与 Hermes 适配，子树 9 个文件。（目录位置推断）
- `backend/shared/` — 跨模块身份上下文、错误、加密与文本基础设施，子树 8 个文件。（目录位置推断）
- `backend/templates/` — 报告等输出模板，子树 1 个文件。（目录位置推断）
- `backend/tools/` — 模型可调用业务工具和保留的历史工具，子树 43 个文件。（目录位置推断）
- `backend/tools/business/` — 模型可调用业务工具和保留的历史工具，子树 5 个文件。（目录位置推断）
- `backend/tools/paper_reproduction/` — 模型可调用业务工具和保留的历史工具，子树 28 个文件。（目录位置推断）
- `backend/utils/` — 公共辅助实现和保留的历史工具，子树 17 个文件。（目录位置推断）
- `docker/` — 容器镜像、部署与运维脚本，子树 10 个文件。（目录位置推断）
- `docker/volumes/` — 容器镜像、部署与运维脚本，子树 1 个文件。（目录位置推断）
- `docker/volumes/hermes/` — 容器镜像、部署与运维脚本，子树 1 个文件。（目录位置推断）
- `docs/` — 设计、实施、交接与验证资料，子树 89 个文件。（目录位置推断）
- `docs/research/` — 设计、实施、交接与验证资料，子树 1 个文件。（目录位置推断）
- `docs/reviews/` — 设计、实施、交接与验证资料，子树 25 个文件。（目录位置推断）
- `docs/reviews/2026-11-10/` — 设计、实施、交接与验证资料，子树 22 个文件。（目录位置推断）
- `docs/reviews/2026-11-11/` — 设计、实施、交接与验证资料，子树 3 个文件。（目录位置推断）
- `docs/superpowers/` — 设计、实施、交接与验证资料，子树 52 个文件。（目录位置推断）
- `docs/superpowers/plans/` — 设计、实施、交接与验证资料，子树 15 个文件。（目录位置推断）
- `docs/superpowers/specs/` — 设计、实施、交接与验证资料，子树 37 个文件。（目录位置推断）
- `docs/superpowers/specs/assets/` — 设计、实施、交接与验证资料，子树 25 个文件。（目录位置推断）
- `docs/superpowers/specs/assets/android-wp1/` — 设计、实施、交接与验证资料，子树 12 个文件。（目录位置推断）
- `docs/superpowers/specs/assets/android-wp2/` — 设计、实施、交接与验证资料，子树 6 个文件。（目录位置推断）
- `docs/superpowers/specs/assets/android-wp34/` — 设计、实施、交接与验证资料，子树 6 个文件。（目录位置推断）
- `docs/论文复现/` — 设计、实施、交接与验证资料，子树 11 个文件。（目录位置推断）
- `eval/` — 离线评测、基准与结果分析，子树 17 个文件。（目录位置推断）
- `eval/context_budget/` — 离线评测、基准与结果分析，子树 11 个文件。（目录位置推断）
- `eval/dataset/` — 离线评测、基准与结果分析，子树 1 个文件。（目录位置推断）
- `scripts/` — 人工运维、诊断、数据修复及历史实验脚本，子树 121 个文件。（目录位置推断）
- `scripts/kb/` — 人工运维、诊断、数据修复及历史实验脚本，子树 28 个文件。（目录位置推断）
- `scripts/kb/eval/` — 人工运维、诊断、数据修复及历史实验脚本，子树 5 个文件。（目录位置推断）
- `scripts/kb/migrate/` — 人工运维、诊断、数据修复及历史实验脚本，子树 5 个文件。（目录位置推断）
- `scripts/kb/test/` — 人工运维、诊断、数据修复及历史实验脚本，子树 15 个文件。（目录位置推断）
- `sql/` — 历史SQL和结构资料，子树 2 个文件。（目录位置推断）
- `tests/` — 自动化测试、fixture和临时SQLite测试支撑，子树 217 个文件。（目录位置推断）
- `tests/access/` — 自动化测试、fixture和临时SQLite测试支撑，子树 7 个文件。（目录位置推断）
- `tests/architecture/` — 自动化测试、fixture和临时SQLite测试支撑，子树 3 个文件。（目录位置推断）
- `tests/assistant/` — 自动化测试、fixture和临时SQLite测试支撑，子树 5 个文件。（目录位置推断）
- `tests/briefing/` — 自动化测试、fixture和临时SQLite测试支撑，子树 3 个文件。（目录位置推断）
- `tests/channels/` — 自动化测试、fixture和临时SQLite测试支撑，子树 6 个文件。（目录位置推断）
- `tests/context_results/` — 自动化测试、fixture和临时SQLite测试支撑，子树 18 个文件。（目录位置推断）
- `tests/contracts/` — 自动化测试、fixture和临时SQLite测试支撑，子树 16 个文件。（目录位置推断）
- `tests/delivery/` — 自动化测试、fixture和临时SQLite测试支撑，子树 7 个文件。（目录位置推断）
- `tests/evolution/` — 自动化测试、fixture和临时SQLite测试支撑，子树 6 个文件。（目录位置推断）
- `tests/files/` — 自动化测试、fixture和临时SQLite测试支撑，子树 6 个文件。（目录位置推断）
- `tests/fixtures/` — 自动化测试、fixture和临时SQLite测试支撑，子树 11 个文件。（目录位置推断）
- `tests/fixtures/contracts/` — 自动化测试、fixture和临时SQLite测试支撑，子树 2 个文件。（目录位置推断）
- `tests/fixtures/evolution/` — 自动化测试、fixture和临时SQLite测试支撑，子树 1 个文件。（目录位置推断）
- `tests/fixtures/kb_eval/` — 自动化测试、fixture和临时SQLite测试支撑，子树 5 个文件。（目录位置推断）
- `tests/fixtures/kg_eval/` — 自动化测试、fixture和临时SQLite测试支撑，子树 1 个文件。（目录位置推断）
- `tests/fixtures/ledger/` — 自动化测试、fixture和临时SQLite测试支撑，子树 1 个文件。（目录位置推断）
- `tests/fixtures/memory/` — 自动化测试、fixture和临时SQLite测试支撑，子树 1 个文件。（目录位置推断）
- `tests/inbox/` — 自动化测试、fixture和临时SQLite测试支撑，子树 1 个文件。（目录位置推断）
- `tests/integration/` — 自动化测试、fixture和临时SQLite测试支撑，子树 1 个文件。（目录位置推断）
- `tests/ledger/` — 自动化测试、fixture和临时SQLite测试支撑，子树 11 个文件。（目录位置推断）
- `tests/memory/` — 自动化测试、fixture和临时SQLite测试支撑，子树 7 个文件。（目录位置推断）
- `tests/models/` — 自动化测试、fixture和临时SQLite测试支撑，子树 3 个文件。（目录位置推断）
- `tests/profiles/` — 自动化测试、fixture和临时SQLite测试支撑，子树 8 个文件。（目录位置推断）
- `tests/resources/` — 自动化测试、fixture和临时SQLite测试支撑，子树 2 个文件。（目录位置推断）
- `tests/scheduling/` — 自动化测试、fixture和临时SQLite测试支撑，子树 2 个文件。（目录位置推断）
- `tests/security/` — 自动化测试、fixture和临时SQLite测试支撑，子树 2 个文件。（目录位置推断）
- `tests/services/` — 自动化测试、fixture和临时SQLite测试支撑，子树 1 个文件。（目录位置推断）
- `tests/skills/` — 自动化测试、fixture和临时SQLite测试支撑，子树 4 个文件。（目录位置推断）
- `tests/storage/` — 自动化测试、fixture和临时SQLite测试支撑，子树 6 个文件。（目录位置推断）
- `tests/superagent/` — 自动化测试、fixture和临时SQLite测试支撑，子树 9 个文件。（目录位置推断）
- `tests/support/` — 自动化测试、fixture和临时SQLite测试支撑，子树 5 个文件。（目录位置推断）
- `tests/tools/` — 自动化测试、fixture和临时SQLite测试支撑，子树 4 个文件。（目录位置推断）
- `tests/usage/` — 自动化测试、fixture和临时SQLite测试支撑，子树 3 个文件。（目录位置推断）

## 文件职责


### ./

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [.coveragerc](<E:/PythonCode/EasyChat/.coveragerc>) | 仓库根目录的配置、入口或辅助文件中的.coveragerc 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [.dockerignore](<E:/PythonCode/EasyChat/.dockerignore>) | 仓库根目录的配置、入口或辅助文件中的.dockerignore 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [.gitignore](<E:/PythonCode/EasyChat/.gitignore>) | 仓库根目录的配置、入口或辅助文件中的.gitignore 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [=1.2.2](<E:/PythonCode/EasyChat/=1.2.2>) | 仓库根目录的配置、入口或辅助文件中的=1.2 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [=2.13.4](<E:/PythonCode/EasyChat/=2.13.4>) | 仓库根目录的配置、入口或辅助文件中的=2.13 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [=2.24.0](<E:/PythonCode/EasyChat/=2.24.0>) | 仓库根目录的配置、入口或辅助文件中的=2.24 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [AGENTS.md](<E:/PythonCode/EasyChat/AGENTS.md>) | 编码代理仓库规则与保护路径（路径与入口核查） | AGENTS.md — 编码代理仓库须知 |
| [CLAUDE.md](<E:/PythonCode/EasyChat/CLAUDE.md>) | 当前开发指南与架构约束（路径与入口核查） | EasyChat 开发指南（以本文件与磁盘代码为准） |
| [EASYCHAT_HANDOFF.md](<E:/PythonCode/EasyChat/EASYCHAT_HANDOFF.md>) | 项目交接与已实现能力记录（路径与入口核查） | Files & Ledger 增量执行日志（F0–F11） |
| [EASYCHAT_PROGRESS.md](<E:/PythonCode/EasyChat/EASYCHAT_PROGRESS.md>) | 阶段实施进展记录（路径与入口核查） | EasyChat 实施进度交接（2026-11-03） |
| [README.md](<E:/PythonCode/EasyChat/README.md>) | 仓库说明与使用入口（路径与入口核查） | EasyChat（原 AgentForge） |
| [check_env.py](<E:/PythonCode/EasyChat/check_env.py>) | 环境和依赖检查入口（路径与入口核查） | 检查后端服务的 Python 环境 |
| [coverage.xml](<E:/PythonCode/EasyChat/coverage.xml>) | 仓库根目录的配置、入口或辅助文件的XML资源（目录与文件名推断） | 按目录和文件类型定位 |
| [main.py](<E:/PythonCode/EasyChat/main.py>) | Python服务命令行启动入口（路径与入口核查） | EasyChat 启动入口（新架构）。 / 符号 main |
| [pyproject.toml](<E:/PythonCode/EasyChat/pyproject.toml>) | Python项目及测试/静态检查配置（路径与入口核查） | 按目录和文件类型定位 |
| [requirements.txt](<E:/PythonCode/EasyChat/requirements.txt>) | 后端依赖安装清单（路径与入口核查） | 按目录和文件类型定位 |
| [restart-all.bat](<E:/PythonCode/EasyChat/restart-all.bat>) | 启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |
| [restart-full.bat](<E:/PythonCode/EasyChat/restart-full.bat>) | 启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |
| [restart-paper-repro.bat](<E:/PythonCode/EasyChat/restart-paper-repro.bat>) | 论文相关启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |
| [restart.bat](<E:/PythonCode/EasyChat/restart.bat>) | 启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |
| [rubric_result.json](<E:/PythonCode/EasyChat/rubric_result.json>) | 仓库根目录的配置、入口或辅助文件的配置或结构化资源，主题 rubric_result（目录与文件名推断） | 按目录和文件类型定位 |
| [start-local.bat](<E:/PythonCode/EasyChat/start-local.bat>) | 启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |
| [stop-all.bat](<E:/PythonCode/EasyChat/stop-all.bat>) | 启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |
| [stop.bat](<E:/PythonCode/EasyChat/stop.bat>) | 启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |
| [test_paper_full.py](<E:/PythonCode/EasyChat/test_paper_full.py>) | 验证 paper_full 相关行为与回归（测试文件名推断） | 论文复现系统完整测试 |
| [test_paper_parse.py](<E:/PythonCode/EasyChat/test_paper_parse.py>) | 验证 paper_parse 相关行为与回归（测试文件名推断） | 论文复现系统完整测试 |
| [test_pdf_libs.bat](<E:/PythonCode/EasyChat/test_pdf_libs.bat>) | 验证 pdf_libs 相关行为与回归（测试文件名推断） | 按目录和文件类型定位 |
| [代码审查报告-日志系统.md](<E:/PythonCode/EasyChat/代码审查报告-日志系统.md>) | 仓库根目录的配置、入口或辅助文件的说明、设计或验证文档，主题 代码审查报告-日志系统（目录与文件名推断） | AgentForge 代码审查报告 - 日志系统 |

### .github/workflows/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [ci.yml](<E:/PythonCode/EasyChat/.github/workflows/ci.yml>) | 仓库CI配置的配置或结构化资源，主题 ci（目录与文件名推断） | 按目录和文件类型定位 |

### .planning/2026-11-03-easychat-design/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [copy-manifest.json](<E:/PythonCode/EasyChat/.planning/2026-11-03-easychat-design/copy-manifest.json>) | 历史阶段计划、研究与验证记录的配置或结构化资源，主题 copy-manifest（目录与文件名推断） | 按目录和文件类型定位 |
| [current-code-baseline.json](<E:/PythonCode/EasyChat/.planning/2026-11-03-easychat-design/current-code-baseline.json>) | 历史阶段计划、研究与验证记录的配置或结构化资源，主题 current-code-baseline（目录与文件名推断） | 按目录和文件类型定位 |
| [findings.md](<E:/PythonCode/EasyChat/.planning/2026-11-03-easychat-design/findings.md>) | 历史阶段计划、研究与验证记录的说明、设计或验证文档，主题 findings（目录与文件名推断） | 调研发现 |
| [progress.md](<E:/PythonCode/EasyChat/.planning/2026-11-03-easychat-design/progress.md>) | 历史阶段计划、研究与验证记录的说明、设计或验证文档，主题 progress（目录与文件名推断） | 进度 |
| [task_plan.md](<E:/PythonCode/EasyChat/.planning/2026-11-03-easychat-design/task_plan.md>) | 历史阶段计划、研究与验证记录的说明、设计或验证文档，主题 task_plan（目录与文件名推断） | EasyChat 准备与方案讨论 |

### .planning/2026-11-09-project-review/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [backend-tests.txt](<E:/PythonCode/EasyChat/.planning/2026-11-09-project-review/backend-tests.txt>) | 历史阶段计划、研究与验证记录中的backend-tests 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [findings.md](<E:/PythonCode/EasyChat/.planning/2026-11-09-project-review/findings.md>) | 历史阶段计划、研究与验证记录的说明、设计或验证文档，主题 findings（目录与文件名推断） | 检查发现 |
| [frontend-build.txt](<E:/PythonCode/EasyChat/.planning/2026-11-09-project-review/frontend-build.txt>) | 历史阶段计划、研究与验证记录中的frontend-build 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [frontend-typecheck.txt](<E:/PythonCode/EasyChat/.planning/2026-11-09-project-review/frontend-typecheck.txt>) | 历史阶段计划、研究与验证记录中的frontend-typecheck 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [full-tests.txt](<E:/PythonCode/EasyChat/.planning/2026-11-09-project-review/full-tests.txt>) | 历史阶段计划、研究与验证记录中的full-tests 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [progress.md](<E:/PythonCode/EasyChat/.planning/2026-11-09-project-review/progress.md>) | 历史阶段计划、研究与验证记录的说明、设计或验证文档，主题 progress（目录与文件名推断） | 进展 |
| [task_plan.md](<E:/PythonCode/EasyChat/.planning/2026-11-09-project-review/task_plan.md>) | 历史阶段计划、研究与验证记录的说明、设计或验证文档，主题 task_plan（目录与文件名推断） | 项目审视与微信编码代理方案 |

### .planning/2026-11-09-ui-repair/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [baseline.txt](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/baseline.txt>) | 历史阶段计划、研究与验证记录中的baseline 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [build.txt](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/build.txt>) | 历史阶段计划、研究与验证记录中的build 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [chat-after.png](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/chat-after.png>) | 历史阶段计划、研究与验证记录使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [final-tests.txt](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/final-tests.txt>) | 历史阶段计划、研究与验证记录中的final-tests 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [final-verified-tests.txt](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/final-verified-tests.txt>) | 历史阶段计划、研究与验证记录中的final-verified-tests 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [findings.md](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/findings.md>) | 历史阶段计划、研究与验证记录的说明、设计或验证文档，主题 findings（目录与文件名推断） | 发现 |
| [first-failure.txt](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/first-failure.txt>) | 历史阶段计划、研究与验证记录中的first-failure 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [frontend-tests.txt](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/frontend-tests.txt>) | 历史阶段计划、研究与验证记录中的frontend-tests 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [permission-usages.txt](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/permission-usages.txt>) | 历史阶段计划、研究与验证记录中的permission-usages 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [progress.md](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/progress.md>) | 历史阶段计划、研究与验证记录的说明、设计或验证文档，主题 progress（目录与文件名推断） | 进展 |
| [role-after.png](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/role-after.png>) | 历史阶段计划、研究与验证记录使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [superagent-after.png](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/superagent-after.png>) | 历史阶段计划、研究与验证记录使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [task_plan.md](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/task_plan.md>) | 历史阶段计划、研究与验证记录的说明、设计或验证文档，主题 task_plan（目录与文件名推断） | UI 与功能回归修复 |
| [tests.txt](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/tests.txt>) | 历史阶段计划、研究与验证记录中的tests 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [typecheck.txt](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/typecheck.txt>) | 历史阶段计划、研究与验证记录中的typecheck 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [verified-tests.txt](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/verified-tests.txt>) | 历史阶段计划、研究与验证记录中的verified-tests 实现（目录与文件名推断） | 按目录和文件类型定位 |

### .planning/2026-11-09-ui-repair/backend-before/backend/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [app.py](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/backend-before/backend/app.py>) | 历史阶段计划、研究与验证记录中的app 实现（目录与文件名推断） | FastAPI 应用工厂（架构 §12.2：import 与 create_app 无副作用）。 / 符号 SPAStaticFiles, _LazyModule, _authenticate, _authenticate_ticket, _register_explicit_routers, error_to_response, create_app |

### .planning/2026-11-09-ui-repair/backend-before/backend/modules/assistant/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [compat.py](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/backend-before/backend/modules/assistant/compat.py>) | 历史阶段计划、研究与验证记录中的compat 实现（目录与文件名推断） | assistant 旧 HTTP 兼容（Task 15）：上传/反馈/执行审批在新架构未实现或已移除。 / 符号 build_assistant_compat_router |
| [routes.py](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/backend-before/backend/modules/assistant/routes.py>) | 历史阶段计划、研究与验证记录中的routes 实现（目录与文件名推断） | Web 兼容路由：旧 /chat/stream SSE 契约 → 统一 Assistant（A09）。 / 符号 StreamPostBody, _sse_frame, build_web_chat_router, _make_command, _resume_from |

### .planning/2026-11-09-ui-repair/backend-before/backend/modules/files/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [api.py](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/backend-before/backend/modules/files/api.py>) | 历史阶段计划、研究与验证记录中的api 实现（目录与文件名推断） | files 模块唯一公开入口：保存 / 读取 / 引用 / 删除影响 / 对账 / 提取记录。 / 符号 FileService, _safe_display_name |

### .planning/2026-11-09-ui-repair/backend-before/backend/modules/models/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [api.py](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/backend-before/backend/modules/models/api.py>) | 历史阶段计划、研究与验证记录中的api 实现（目录与文件名推断） | models 模块公开接口：模型配置管理与 run 模型选择。 / 符号 ModelsService |

### .planning/2026-11-09-ui-repair/backend-before/backend/runtime/hermes/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [adapter.py](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/backend-before/backend/runtime/hermes/adapter.py>) | 历史阶段计划、研究与验证记录中的adapter 实现（目录与文件名推断） | Hermes Runtime Adapter：ExecutionRuntime 的唯一 Hermes 整合入口（架构 §4.1）。 / 符号 _AgentHandle, HermesRuntimeAdapter, _safe_result, _safe_tools |
| [agent_factory.py](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/backend-before/backend/runtime/hermes/agent_factory.py>) | 历史阶段计划、研究与验证记录中的代理相关实现（目录与文件名推断） | 真实 Hermes AIAgent 构建工厂。 / 符号 build_agent, _normalize_base_url, _strip_model_suffix, _reasoning_effort, _resolve_api_key, _fallback_profile |

### .planning/2026-11-09-ui-repair/static-before/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [index.html](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/index.html>) | 历史阶段计划、研究与验证记录中的index 实现（目录与文件名推断） | 按目录和文件类型定位 |

### .planning/2026-11-09-ui-repair/static-before/assets/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [AdminView-BkAdutsM.js](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/AdminView-BkAdutsM.js>) | 历史阶段计划、研究与验证记录中的AdminView-BkAdutsM 实现（目录与文件名推断） | 符号 ce, ve, fe, _e, ye, ge, te |
| [AdminView-CyLv_NO2.css](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/AdminView-CyLv_NO2.css>) | 历史阶段计划、研究与验证记录中的AdminView-CyLv_NO2 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [ChatView-CwCuBwEb.js](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/ChatView-CwCuBwEb.js>) | 历史阶段计划、研究与验证记录中的聊天相关实现（目录与文件名推断） | 符号 ut, n, y, z, T, _, B |
| [ChatView-DU3v2IHO.css](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/ChatView-DU3v2IHO.css>) | 历史阶段计划、研究与验证记录中的聊天相关实现（目录与文件名推断） | 按目录和文件类型定位 |
| [ConfigView-C2c6YBwd.css](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/ConfigView-C2c6YBwd.css>) | 历史阶段计划、研究与验证记录中的配置相关实现（目录与文件名推断） | 按目录和文件类型定位 |
| [ConfigView-CLXeCKt2.js](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/ConfigView-CLXeCKt2.js>) | 历史阶段计划、研究与验证记录中的配置相关实现（目录与文件名推断） | 符号 ra, g, ua, ca, _, pa, va |
| [LedgerView-CiFdijA7.css](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/LedgerView-CiFdijA7.css>) | 历史阶段计划、研究与验证记录中的LedgerView-CiFdijA7 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [LedgerView-DQtikawg.js](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/LedgerView-DQtikawg.js>) | 历史阶段计划、研究与验证记录中的LedgerView-DQtikawg 实现（目录与文件名推断） | 符号 O, u, dt, pt, vt, _t, yt |
| [LoginView-Bw45LFL4.js](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/LoginView-Bw45LFL4.js>) | 历史阶段计划、研究与验证记录中的LoginView-Bw45LFL4 实现（目录与文件名推断） | 符号 A, b, k, w |
| [LoginView-e2bk0psm.css](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/LoginView-e2bk0psm.css>) | 历史阶段计划、研究与验证记录中的LoginView-e2bk0psm 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [MemoryView-DPR7EGK8.js](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/MemoryView-DPR7EGK8.js>) | 历史阶段计划、研究与验证记录中的记忆相关实现（目录与文件名推断） | 符号 j, _, m, s, w, C, U |
| [MemoryView-eMoUgmBd.css](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/MemoryView-eMoUgmBd.css>) | 历史阶段计划、研究与验证记录中的记忆相关实现（目录与文件名推断） | 按目录和文件类型定位 |
| [SchedulesView-CvYxK94h.css](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/SchedulesView-CvYxK94h.css>) | 历史阶段计划、研究与验证记录中的SchedulesView-CvYxK94h 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [SchedulesView-GXLnp06x.js](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/SchedulesView-GXLnp06x.js>) | 历史阶段计划、研究与验证记录中的SchedulesView-GXLnp06x 实现（目录与文件名推断） | 符号 O, g, V, I, f, S, k |
| [SkillsView-uYz7qMrv.js](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/SkillsView-uYz7qMrv.js>) | 历史阶段计划、研究与验证记录中的技能相关实现（目录与文件名推断） | 符号 P, h, m, l, k, e, z |
| [SkillsView-zujm8zyV.css](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/SkillsView-zujm8zyV.css>) | 历史阶段计划、研究与验证记录中的技能相关实现（目录与文件名推断） | 按目录和文件类型定位 |
| [SuperagentView-CriqVkID.css](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/SuperagentView-CriqVkID.css>) | 历史阶段计划、研究与验证记录中的SuperagentView-CriqVkID 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [SuperagentView-DnP6EBS-.js](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/SuperagentView-DnP6EBS-.js>) | 历史阶段计划、研究与验证记录中的SuperagentView-DnP6EBS- 实现（目录与文件名推断） | 符号 ye, ke, we, he, xe, x, Se |
| [UsageView-D-275J2v.css](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/UsageView-D-275J2v.css>) | 历史阶段计划、研究与验证记录中的用量相关实现（目录与文件名推断） | 按目录和文件类型定位 |
| [UsageView-gwBdbmF1.js](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/UsageView-gwBdbmF1.js>) | 历史阶段计划、研究与验证记录中的用量相关实现（目录与文件名推断） | 符号 w, i, k, u, m |
| [WeChatSettingsView-DQJARYi4.js](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/WeChatSettingsView-DQJARYi4.js>) | 历史阶段计划、研究与验证记录中的聊天相关实现（目录与文件名推断） | 符号 Y, B, Z, ee, te, oe, ae |
| [WeChatSettingsView-DlVsENT0.css](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/WeChatSettingsView-DlVsENT0.css>) | 历史阶段计划、研究与验证记录中的聊天相关实现（目录与文件名推断） | 按目录和文件类型定位 |
| [config-DeChIB-n.js](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/config-DeChIB-n.js>) | 历史阶段计划、研究与验证记录中的配置相关实现（目录与文件名推断） | 符号 o, r, c, l, u, d, f |
| [index-CG6aCj9T.css](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/index-CG6aCj9T.css>) | 历史阶段计划、研究与验证记录中的index-CG6aCj9T 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [index-DtNPnh7R.js](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/index-DtNPnh7R.js>) | 历史阶段计划、研究与验证记录中的index-DtNPnh7R 实现（目录与文件名推断） | 符号 __vite__mapDeps, t, o, l, s, n, a |
| [markdown-BZFRgdvi.js](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/markdown-BZFRgdvi.js>) | 历史阶段计划、研究与验证记录中的markdown-BZFRgdvi 实现（目录与文件名推断） | 符号 St, Ei, i, Ze, t, s, l |
| [vendor-DTO69s6y.js](<E:/PythonCode/EasyChat/.planning/2026-11-09-ui-repair/static-before/assets/vendor-DTO69s6y.js>) | 历史阶段计划、研究与验证记录中的vendor-DTO69s6y 实现（目录与文件名推断） | 符号 er, t, n, oe, rs, is, s |

### agent_frontend/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [.gitignore](<E:/PythonCode/EasyChat/agent_frontend/.gitignore>) | Vue/Vite Web客户端中的.gitignore 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [env.d.ts](<E:/PythonCode/EasyChat/agent_frontend/env.d.ts>) | Vue/Vite Web客户端中的env.d 实现（目录与文件名推断） | 符号 component, ImportMetaEnv, ImportMeta |
| [index.html](<E:/PythonCode/EasyChat/agent_frontend/index.html>) | Vue/Vite Web客户端中的index 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [package-lock.json](<E:/PythonCode/EasyChat/agent_frontend/package-lock.json>) | 依赖解析或构建工具版本锁定（文件约定） | 按目录和文件类型定位 |
| [package.json](<E:/PythonCode/EasyChat/agent_frontend/package.json>) | Web依赖与开发/测试/构建脚本（路径与入口核查） | 按目录和文件类型定位 |
| [pnpm-lock.yaml](<E:/PythonCode/EasyChat/agent_frontend/pnpm-lock.yaml>) | 依赖解析或构建工具版本锁定（文件约定） | 按目录和文件类型定位 |
| [pnpm-workspace.yaml](<E:/PythonCode/EasyChat/agent_frontend/pnpm-workspace.yaml>) | Vue/Vite Web客户端的配置或结构化资源，主题 pnpm-workspace（目录与文件名推断） | 按目录和文件类型定位 |
| [tsconfig.json](<E:/PythonCode/EasyChat/agent_frontend/tsconfig.json>) | Vue/Vite Web客户端的配置或结构化资源，主题 tsconfig（目录与文件名推断） | 按目录和文件类型定位 |
| [tsconfig.node.json](<E:/PythonCode/EasyChat/agent_frontend/tsconfig.node.json>) | Vue/Vite Web客户端的配置或结构化资源，主题 tsconfig.node（目录与文件名推断） | 按目录和文件类型定位 |
| [vite.config.js](<E:/PythonCode/EasyChat/agent_frontend/vite.config.js>) | Vite构建、开发端口与API代理（路径与入口核查） | 按目录和文件类型定位 |

### agent_frontend/src/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [App.vue](<E:/PythonCode/EasyChat/agent_frontend/src/App.vue>) | Web根组件、壳层与全局交互（路径与入口核查） | 符号 route, authStore, showSidebar, refreshed |
| [main.ts](<E:/PythonCode/EasyChat/agent_frontend/src/main.ts>) | Web启动、插件和应用挂载入口（路径与入口核查） | 符号 app, pinia, auth |

### agent_frontend/src/api/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [admin.ts](<E:/PythonCode/EasyChat/agent_frontend/src/api/admin.ts>) | 后端HTTP接口客户端中的admin 实现（目录与文件名推断） | 符号 User, Role, getUsers, response, updateUserRole, updateUserStatus, PermissionDefinition |
| [auth.ts](<E:/PythonCode/EasyChat/agent_frontend/src/api/auth.ts>) | 后端HTTP接口客户端中的认证相关实现（目录与文件名推断） | 符号 login, response, register, verifyToken, refreshToken |
| [chat.ts](<E:/PythonCode/EasyChat/agent_frontend/src/api/chat.ts>) | 后端HTTP接口客户端中的聊天相关实现（目录与文件名推断） | 符号 API_BASE, UploadedFile, uploadChatImages, form, f, token, resp |
| [config.ts](<E:/PythonCode/EasyChat/agent_frontend/src/api/config.ts>) | 后端HTTP接口客户端中的配置相关实现（目录与文件名推断） | 符号 ModelConfig, getModelConfigs, res, createModelConfig, setActiveModelConfig, deleteModelConfig, updateModelConfig |
| [ledger.ts](<E:/PythonCode/EasyChat/agent_frontend/src/api/ledger.ts>) | 后端HTTP接口客户端中的ledger 实现（目录与文件名推断） | 符号 FileRecord, ImportView, normalizeImport, ImportSummary, TransactionView, Category, RefundSuggestion |
| [permissions.ts](<E:/PythonCode/EasyChat/agent_frontend/src/api/permissions.ts>) | 后端HTTP接口客户端中的permissions 实现（目录与文件名推断） | 符号 ModuleCapability, UserCapabilities, getMyCapabilities, res, EffectivePermItem, UserEffectiveDetail, getUserEffectivePerms |
| [platform.ts](<E:/PythonCode/EasyChat/agent_frontend/src/api/platform.ts>) | 后端HTTP接口客户端中的platform 实现（目录与文件名推断） | 符号 PlatformConfig, getPlatformConfig, res, account, savePlatformConfig, cfg, getPlatformBindings |
| [request.ts](<E:/PythonCode/EasyChat/agent_frontend/src/api/request.ts>) | 后端HTTP接口客户端中的request 实现（目录与文件名推断） | 符号 API_BASE, request, authStore, newToken, loc, text |
| [session.ts](<E:/PythonCode/EasyChat/agent_frontend/src/api/session.ts>) | 后端HTTP接口客户端中的会话相关实现（目录与文件名推断） | 符号 getUserSessions, response, sessions, deleteSession, renameSession |
| [superagent.ts](<E:/PythonCode/EasyChat/agent_frontend/src/api/superagent.ts>) | 后端HTTP接口客户端中的superagent 实现（目录与文件名推断） | 符号 SuperagentCapabilities, SuperagentSettings, SuperagentTask, SuperagentEvent, SuperagentReport, TaskPage, getSuperagentCapabilities |
| [wechat.ts](<E:/PythonCode/EasyChat/agent_frontend/src/api/wechat.ts>) | 后端HTTP接口客户端中的wechat 实现（目录与文件名推断） | 符号 AssistantProfile, MoodEntry, InboxItem, getProfile, res, updateProfile, listMood |

### agent_frontend/src/components/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [AppSidebar.vue](<E:/PythonCode/EasyChat/agent_frontend/src/components/AppSidebar.vue>) | Web可复用交互组件中的AppSidebar 实现（目录与文件名推断） | 符号 router, authStore, collapsed, NAV_WIDTH_KEY, persistedNavWidth, raw, panelWidth |
| [PanelResizeHandle.vue](<E:/PythonCode/EasyChat/agent_frontend/src/components/PanelResizeHandle.vue>) | Web可复用交互组件中的PanelResizeHandle 实现（目录与文件名推断） | 符号 props, emit, resize, move, stopDrag, startDrag |

### agent_frontend/src/components/chat/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [ChatSidebar.vue](<E:/PythonCode/EasyChat/agent_frontend/src/components/chat/ChatSidebar.vue>) | Web可复用交互组件中的聊天相关实现（目录与文件名推断） | 符号 HISTORY_WIDTH_KEY, persistedHistoryWidth, raw, panelWidth, onPanelResize, sidebarStore, chatStore |
| [MessageBubble.vue](<E:/PythonCode/EasyChat/agent_frontend/src/components/chat/MessageBubble.vue>) | Web可复用交互组件中的MessageBubble 实现（目录与文件名推断） | 符号 props, sourceLabel, map, typeLabel, formatCitationTime, d, now |
| [SubagentPanel.vue](<E:/PythonCode/EasyChat/agent_frontend/src/components/chat/SubagentPanel.vue>) | Web可复用交互组件中的SubagentPanel 实现（目录与文件名推断） | 符号 props, isExpanded, runningCount, statusIcon, formatTokens, total, formatOutputLength |

### agent_frontend/src/composables/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [useAutoScroll.ts](<E:/PythonCode/EasyChat/agent_frontend/src/composables/useAutoScroll.ts>) | 组合式交互和请求逻辑中的useAutoScroll 实现（目录与文件名推断） | 符号 useAutoScroll, chatStore, isUserScrolling, isNearBottom, scrollToBottom, handleScroll, nearBottom |
| [useChat.ts](<E:/PythonCode/EasyChat/agent_frontend/src/composables/useChat.ts>) | 组合式交互和请求逻辑中的聊天相关实现（目录与文件名推断） | 符号 parseProcessLog, items, truncate, str, mergeThinkingSteps, seen, merged |

### agent_frontend/src/router/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [index.ts](<E:/PythonCode/EasyChat/agent_frontend/src/router/index.ts>) | 路由、页面加载和访问守卫（路径与入口核查） | 符号 routes, router, token, userRole, parsed, existingUid, resp |

### agent_frontend/src/stores/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [auth.ts](<E:/PythonCode/EasyChat/agent_frontend/src/stores/auth.ts>) | 前端共享状态中的认证相关实现（目录与文件名推断） | 符号 useAuthStore, readStoredPermissions, raw, parsed, token, user, userRole |
| [chat.ts](<E:/PythonCode/EasyChat/agent_frontend/src/stores/chat.ts>) | 前端共享状态中的聊天相关实现（目录与文件名推断） | 符号 MAX_CACHED_SESSIONS, useChatStore, currentChatId, messagesByChat, streamingSessions, pendingUserMessages, autoScroll |
| [sidebar.ts](<E:/PythonCode/EasyChat/agent_frontend/src/stores/sidebar.ts>) | 前端共享状态中的sidebar 实现（目录与文件名推断） | 符号 useSidebarStore, chatHistory, historyFilter, hasMore, offset, loading, currentOffset |

### agent_frontend/src/styles/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [design-system.css](<E:/PythonCode/EasyChat/agent_frontend/src/styles/design-system.css>) | 全局视觉样式与布局中的design-system 实现（目录与文件名推断） | 按目录和文件类型定位 |

### agent_frontend/src/types/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [auth.ts](<E:/PythonCode/EasyChat/agent_frontend/src/types/auth.ts>) | Vue/Vite Web客户端中的认证相关实现（目录与文件名推断） | 符号 User, LoginRequest, LoginResponse, AuthState, ModuleCapability, UserCapabilities |
| [chat.ts](<E:/PythonCode/EasyChat/agent_frontend/src/types/chat.ts>) | Vue/Vite Web客户端中的聊天相关实现（目录与文件名推断） | 符号 ThinkingProcess, SubagentToolCall, SubagentTask, ChatImage, MemoryCitation, ChatFile, Message |

### agent_frontend/src/utils/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [downloadFile.ts](<E:/PythonCode/EasyChat/agent_frontend/src/utils/downloadFile.ts>) | 前端纯逻辑辅助中的下载、文件相关实现（目录与文件名推断） | 符号 downloadFile, response, url, link |
| [err.ts](<E:/PythonCode/EasyChat/agent_frontend/src/utils/err.ts>) | 前端纯逻辑辅助中的err 实现（目录与文件名推断） | 符号 errMsg, err, detail, loc, msg |
| [markdown.ts](<E:/PythonCode/EasyChat/agent_frontend/src/utils/markdown.ts>) | 前端纯逻辑辅助中的markdown 实现（目录与文件名推断） | 符号 md, defaultCodeRender, content, defaultLinkRender, hrefIndex, href, renderMarkdown |
| [panelWidth.ts](<E:/PythonCode/EasyChat/agent_frontend/src/utils/panelWidth.ts>) | 前端纯逻辑辅助中的panelWidth 实现（目录与文件名推断） | 符号 clampPanelWidth |
| [permissionGroups.ts](<E:/PythonCode/EasyChat/agent_frontend/src/utils/permissionGroups.ts>) | 前端纯逻辑辅助中的permissionGroups 实现（目录与文件名推断） | 符号 PermissionItem, PermissionGroup, groupPermissions, groups, item, name |
| [token.ts](<E:/PythonCode/EasyChat/agent_frontend/src/utils/token.ts>) | 前端纯逻辑辅助中的令牌/Token相关实现（目录与文件名推断） | 符号 decodeJwtPayload, parts, base64, padded, getTokenRemainingSeconds, payload, isTokenExpired |
| [uuid.ts](<E:/PythonCode/EasyChat/agent_frontend/src/utils/uuid.ts>) | 前端纯逻辑辅助中的uuid 实现（目录与文件名推断） | 符号 generateUUID, r, v |

### agent_frontend/src/views/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [AdminView.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/AdminView.vue>) | Web业务页面中的AdminView 实现（目录与文件名推断） | 符号 auth, activeTab, roleListRef, visibleTabs, tabs, showRoleEdit, editingRole |
| [ChatView.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/ChatView.vue>) | Web业务页面中的聊天相关实现（目录与文件名推断） | 符号 chatStore, auth, canAccessHosts, showServerList, accessibleHosts, serverListLoading, authMethodLabel |
| [ConfigView.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/ConfigView.vue>) | Web业务页面中的配置相关实现（目录与文件名推断） | 符号 id, cfg, authStore, isSuperAdmin, hasSystemConfig, allTabs, tabs |
| [LedgerView.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/LedgerView.vue>) | Web业务页面中的LedgerView 实现（目录与文件名推断） | 符号 CandidateField, ImageCandidate, fileInput, imageInput, uploading, committing, recognizing |
| [LoginView.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/LoginView.vue>) | Web业务页面中的LoginView 实现（目录与文件名推断） | 符号 router, authStore, username, password, isRegister, loading, error |
| [MemoryView.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/MemoryView.vue>) | Web业务页面中的记忆相关实现（目录与文件名推断） | 符号 MemoryItem, items, loading, error, query, showAdd, editing |
| [SchedulesView.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/SchedulesView.vue>) | Web业务页面中的SchedulesView 实现（目录与文件名推断） | 符号 Schedule, Occurrence, schedules, occurrences, expanded, loading, saving |
| [SkillsView.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/SkillsView.vue>) | Web业务页面中的技能相关实现（目录与文件名推断） | 符号 Skill, Version, skills, selected, versions, content, loading |
| [SuperagentView.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/SuperagentView.vue>) | Web业务页面中的SuperagentView 实现（目录与文件名推断） | 符号 caps, settings, settingsDraft, showSettings, showOps, opsMetrics, savingSettings |
| [UsageView.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/UsageView.vue>) | Web业务页面中的用量相关实现（目录与文件名推断） | 符号 Daily, RankRow, Call, days, daily, ranking, calls |
| [WeChatSettingsView.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/WeChatSettingsView.vue>) | Web业务页面中的聊天相关实现（目录与文件名推断） | 符号 presets, tabs, form, mood, items, tabValue, newUrl |

### agent_frontend/src/views/admin/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [AdminLayout.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/admin/AdminLayout.vue>) | Web业务页面中的AdminLayout 实现（目录与文件名推断） | 符号 Tab |
| [RoleEditDialog.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/admin/RoleEditDialog.vue>) | Web业务页面中的RoleEditDialog 实现（目录与文件名推断） | 符号 props, emit, saving, showAdvanced, toolOptions, modeChangeNote, form |
| [RoleListPanel.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/admin/RoleListPanel.vue>) | Web业务页面中的RoleListPanel 实现（目录与文件名推断） | 符号 roles, loading, loadRoles |
| [UpgradePreviewPanel.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/admin/UpgradePreviewPanel.vue>) | Web业务页面中的UpgradePreviewPanel 实现（目录与文件名推断） | 符号 auth, open, loading, preview, applying, message, canApply |
| [UserListPanel.vue](<E:/PythonCode/EasyChat/agent_frontend/src/views/admin/UserListPanel.vue>) | Web业务页面中的UserListPanel 实现（目录与文件名推断） | 符号 users, roles, loading, permUser, permDetail, permLoading, showEffectivePerms |

### agent_frontend/tests/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [api-config.test.cjs](<E:/PythonCode/EasyChat/agent_frontend/tests/api-config.test.cjs>) | 验证 api-config 相关行为与回归（测试文件名推断） | 符号 assert, fs, path, test, ts, calls, request |
| [feature-contracts.test.mjs](<E:/PythonCode/EasyChat/agent_frontend/tests/feature-contracts.test.mjs>) | 验证 feature-contracts 相关行为与回归（测试文件名推断） | 符号 readSource, evaluate, script, parsed, statement, view, memory |
| [role-modes.test.mjs](<E:/PythonCode/EasyChat/agent_frontend/tests/role-modes.test.mjs>) | 验证 role-modes 相关行为与回归（测试文件名推断） | 符号 ledgerUse, openRole, source, script, listeners, emitted, bindings |
| [ui-contracts.test.mjs](<E:/PythonCode/EasyChat/agent_frontend/tests/ui-contracts.test.mjs>) | 验证 ui-contracts 相关行为与回归（测试文件名推断） | 符号 loadUtility, source, groups, input, calls, link, request |

### android_client/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [.gitignore](<E:/PythonCode/EasyChat/android_client/.gitignore>) | Kotlin/Compose Android客户端中的.gitignore 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [build.gradle.kts](<E:/PythonCode/EasyChat/android_client/build.gradle.kts>) | Kotlin/Compose Android客户端中的build.gradle 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [gradle.properties](<E:/PythonCode/EasyChat/android_client/gradle.properties>) | Kotlin/Compose Android客户端的配置或结构化资源，主题 gradle（目录与文件名推断） | 按目录和文件类型定位 |
| [gradlew](<E:/PythonCode/EasyChat/android_client/gradlew>) | Kotlin/Compose Android客户端中的gradlew 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [gradlew.bat](<E:/PythonCode/EasyChat/android_client/gradlew.bat>) | 启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |
| [local.properties](<E:/PythonCode/EasyChat/android_client/local.properties>) | 本地环境/认证配置，仅说明路径职责，内容未展开（路径类型） | 按目录和文件类型定位 |
| [settings.gradle.kts](<E:/PythonCode/EasyChat/android_client/settings.gradle.kts>) | Kotlin/Compose Android客户端中的settings.gradle 实现（目录与文件名推断） | 按目录和文件类型定位 |

### android_client/app/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [build.gradle.kts](<E:/PythonCode/EasyChat/android_client/app/build.gradle.kts>) | Kotlin/Compose Android客户端中的build.gradle 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [proguard-rules.pro](<E:/PythonCode/EasyChat/android_client/app/proguard-rules.pro>) | Kotlin/Compose Android客户端中的proguard-rules 实现（目录与文件名推断） | 按目录和文件类型定位 |

### android_client/app/src/debug/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [AndroidManifest.xml](<E:/PythonCode/EasyChat/android_client/app/src/debug/AndroidManifest.xml>) | Android清单/界面资源/平台配置，主题 AndroidManifest（目录与文件名推断） | 按目录和文件类型定位 |

### android_client/app/src/main/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [AndroidManifest.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/AndroidManifest.xml>) | Android清单/界面资源/平台配置，主题 AndroidManifest（目录与文件名推断） | 按目录和文件类型定位 |

### android_client/app/src/main/java/com/easychat/family/app/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [AppContainer.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/app/AppContainer.kt>) | Kotlin/Compose Android客户端中的AppContainer 实现（目录与文件名推断） | 符号 AppContainer, clearSessionExpiredFlag |
| [MainActivity.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/app/MainActivity.kt>) | Kotlin/Compose Android客户端中的主入口相关实现（目录与文件名推断） | 符号 MainActivity, onCreate |
| [XiaoNuanApp.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/app/XiaoNuanApp.kt>) | Kotlin/Compose Android客户端中的XiaoNuanApp 实现（目录与文件名推断） | 符号 val, chatDetail, TabSpec, XiaoNuanApp |
| [XiaoNuanApplication.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/app/XiaoNuanApplication.kt>) | Kotlin/Compose Android客户端中的XiaoNuanApplication 实现（目录与文件名推断） | 符号 XiaoNuanApplication, onCreate |

### android_client/app/src/main/java/com/easychat/family/core/designsystem/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [Components.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/designsystem/Components.kt>) | Kotlin/Compose Android客户端中的Components 实现（目录与文件名推断） | 符号 XnCard, XnPrimaryButton, XnSageButton, XnSectionHeader, XnSourceChip, XnMockBadge, XnEmptyState |
| [Dimens.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/designsystem/Dimens.kt>) | Kotlin/Compose Android客户端中的Dimens 实现（目录与文件名推断） | 符号 val |
| [Theme.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/designsystem/Theme.kt>) | Kotlin/Compose Android客户端中的Theme 实现（目录与文件名推断） | 符号 c, XnTheme |
| [Type.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/designsystem/Type.kt>) | Kotlin/Compose Android客户端中的Type 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [XnPalette.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/designsystem/XnPalette.kt>) | Kotlin/Compose Android客户端中的XnPalette 实现（目录与文件名推断） | 符号 val, relativeLuminance, contrastRatio, channelLuminance |

### android_client/app/src/main/java/com/easychat/family/core/model/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [Dto.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/model/Dto.kt>) | Kotlin/Compose Android客户端中的Dto 实现（目录与文件名推断） | 符号 ApiErrorBody, LoginRequest, LoginResponse, MeResponse, RefreshResponse, Capabilities, ModuleCap |

### android_client/app/src/main/java/com/easychat/family/core/network/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [ApiClient.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/network/ApiClient.kt>) | Kotlin/Compose Android客户端中的ApiClient 实现（目录与文件名推断） | 符号 interface, onUnauthorized, ApiClient, rawCall, buildRequest, refreshSync, handleUnauthorized |
| [ApiError.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/network/ApiError.kt>) | Kotlin/Compose Android客户端中的ApiError 实现（目录与文件名推断） | 符号 ApiError, displayText, codeText, defaultText, parse, RequestFailure, Http |
| [AuthRepository.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/network/AuthRepository.kt>) | Kotlin/Compose Android客户端中的认证相关实现（目录与文件名推断） | 符号 AuthRepository, checkConnection, checkPath, login, me, logout, ConnectionCheck |
| [ChatRepository.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/network/ChatRepository.kt>) | Kotlin/Compose Android客户端中的聊天相关实现（目录与文件名推断） | 符号 ChatRepository, listSessions, messages, rename, delete, stream, cancel |
| [ChatStream.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/network/ChatStream.kt>) | Kotlin/Compose Android客户端中的聊天、流式事件相关实现（目录与文件名推断） | 符号 SseData, ChatEvent, Start, Token, Thinking, Complete, Failed |
| [ChatStreamClient.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/network/ChatStreamClient.kt>) | Kotlin/Compose Android客户端中的聊天、流式事件相关实现（目录与文件名推断） | 符号 ChatStreamClient, consumedSeq, open |
| [LifeRepository.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/network/LifeRepository.kt>) | Kotlin/Compose Android客户端中的LifeRepository 实现（目录与文件名推断） | 符号 LifeRepository, schedules, memories, inbox, wechatSessions, bindings, SessionListResponseContainer |
| [SchedulesRepository.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/network/SchedulesRepository.kt>) | Kotlin/Compose Android客户端中的SchedulesRepository 实现（目录与文件名推断） | 符号 SchedulesRepository, list, create, setEnabled, delete, occurrences, ScheduleCreateBody |
| [SseFrameParser.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/network/SseFrameParser.kt>) | Kotlin/Compose Android客户端中的SseFrameParser 实现（目录与文件名推断） | 符号 SseFrameParser, feedLine, flush, dispatch |

### android_client/app/src/main/java/com/easychat/family/core/storage/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [Stores.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/storage/Stores.kt>) | Kotlin/Compose Android客户端中的Stores 实现（目录与文件名推断） | 符号 TokenStore, store, load, token, tokenCached, clear, ConnectionStore |
| [XnKeystore.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/storage/XnKeystore.kt>) | Kotlin/Compose Android客户端中的XnKeystore 实现（目录与文件名推断） | 符号 val, key, encrypt, decrypt |

### android_client/app/src/main/java/com/easychat/family/core/util/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [XnTime.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/core/util/XnTime.kt>) | Kotlin/Compose Android客户端中的XnTime 实现（目录与文件名推断） | 符号 fromEpochSeconds, formatNextRun, formatIso, normalizeIso, greeting, weekdayCn |

### android_client/app/src/main/java/com/easychat/family/feature/chat/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [ChatScreens.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/feature/chat/ChatScreens.kt>) | Kotlin/Compose Android客户端中的聊天相关实现（目录与文件名推断） | 符号 ChatListScreen, FilterChips, ChatDetailScreen, TextButtonLabel, XnAvatarSmall, UserBubble, AssistantBubble |
| [ChatViewModel.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/feature/chat/ChatViewModel.kt>) | Kotlin/Compose Android客户端中的聊天、模型相关实现（目录与文件名推断） | 符号 UiMessage, ChatPhase, ChatDetailState, ChatViewModel, loadSessions, openExisting, openNew |

### android_client/app/src/main/java/com/easychat/family/feature/life/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [LifeScreen.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/feature/life/LifeScreen.kt>) | Kotlin/Compose Android客户端中的LifeScreen 实现（目录与文件名推断） | 符号 LifeScreen, ScheduleSection, ScheduleRow, repeatText, MemorySection, MemoryRow, kindText |
| [LifeViewModel.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/feature/life/LifeViewModel.kt>) | Kotlin/Compose Android客户端中的模型相关实现（目录与文件名推断） | 符号 LifeUiState, ScheduleDetailState, LifeViewModel, refresh, loadSchedules, loadMemories, loadBookmarks |

### android_client/app/src/main/java/com/easychat/family/feature/onboarding/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [OnboardingScreens.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/feature/onboarding/OnboardingScreens.kt>) | Kotlin/Compose Android客户端中的OnboardingScreens 实现（目录与文件名推断） | 符号 WelcomeScreen, ServerConfigScreen, ConnectionRow, LoginScreen |
| [OnboardingViewModel.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/feature/onboarding/OnboardingViewModel.kt>) | Kotlin/Compose Android客户端中的模型相关实现（目录与文件名推断） | 符号 OnboardingUiState, MeSnapshot, OnboardingViewModel, onServerUrlChange, onUsernameChange, onPasswordChange, checkConnection |

### android_client/app/src/main/java/com/easychat/family/feature/profile/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [ProfileScreen.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/feature/profile/ProfileScreen.kt>) | Kotlin/Compose Android客户端中的ProfileScreen 实现（目录与文件名推断） | 符号 ProfileScreen, SettingRow |

### android_client/app/src/main/java/com/easychat/family/feature/today/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [TodayScreen.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/feature/today/TodayScreen.kt>) | Kotlin/Compose Android客户端中的TodayScreen 实现（目录与文件名推断） | 符号 TodayScreen, ErrorCard, LoadingCard, hm |
| [TodayViewModel.kt](<E:/PythonCode/EasyChat/android_client/app/src/main/java/com/easychat/family/feature/today/TodayViewModel.kt>) | Kotlin/Compose Android客户端中的模型相关实现（目录与文件名推断） | 符号 BlockState, Ready, Error, TodayUiState, ScheduleUi, MemoryUi, TodayViewModel |

### android_client/app/src/main/res/drawable/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [ic_back.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/drawable/ic_back.xml>) | Android清单/界面资源/平台配置，主题 ic_back（目录与文件名推断） | 按目录和文件类型定位 |
| [ic_bookmark.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/drawable/ic_bookmark.xml>) | Android清单/界面资源/平台配置，主题 ic_bookmark（目录与文件名推断） | 按目录和文件类型定位 |
| [ic_calendar.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/drawable/ic_calendar.xml>) | Android清单/界面资源/平台配置，主题 ic_calendar（目录与文件名推断） | 按目录和文件类型定位 |
| [ic_chevron_right.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/drawable/ic_chevron_right.xml>) | Android清单/界面资源/平台配置，主题 ic_chevron_right（目录与文件名推断） | 按目录和文件类型定位 |
| [ic_kitchen.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/drawable/ic_kitchen.xml>) | Android清单/界面资源/平台配置，主题 ic_kitchen（目录与文件名推断） | 按目录和文件类型定位 |
| [ic_launcher_foreground.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/drawable/ic_launcher_foreground.xml>) | Android清单/界面资源/平台配置，主题 ic_launcher_foreground（目录与文件名推断） | 按目录和文件类型定位 |
| [ic_nav_chat.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/drawable/ic_nav_chat.xml>) | Android清单/界面资源/平台配置，主题 ic_nav_chat（目录与文件名推断） | 按目录和文件类型定位 |
| [ic_nav_life.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/drawable/ic_nav_life.xml>) | Android清单/界面资源/平台配置，主题 ic_nav_life（目录与文件名推断） | 按目录和文件类型定位 |
| [ic_nav_me.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/drawable/ic_nav_me.xml>) | Android清单/界面资源/平台配置，主题 ic_nav_me（目录与文件名推断） | 按目录和文件类型定位 |
| [ic_nav_today.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/drawable/ic_nav_today.xml>) | Android清单/界面资源/平台配置，主题 ic_nav_today（目录与文件名推断） | 按目录和文件类型定位 |
| [ic_note.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/drawable/ic_note.xml>) | Android清单/界面资源/平台配置，主题 ic_note（目录与文件名推断） | 按目录和文件类型定位 |
| [ic_plus.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/drawable/ic_plus.xml>) | Android清单/界面资源/平台配置，主题 ic_plus（目录与文件名推断） | 按目录和文件类型定位 |
| [ic_send.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/drawable/ic_send.xml>) | Android清单/界面资源/平台配置，主题 ic_send（目录与文件名推断） | 按目录和文件类型定位 |
| [ic_stop.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/drawable/ic_stop.xml>) | Android清单/界面资源/平台配置，主题 ic_stop（目录与文件名推断） | 按目录和文件类型定位 |

### android_client/app/src/main/res/mipmap-anydpi-v26/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [ic_launcher.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml>) | Android清单/界面资源/平台配置，主题 ic_launcher（目录与文件名推断） | 按目录和文件类型定位 |
| [ic_launcher_round.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/mipmap-anydpi-v26/ic_launcher_round.xml>) | Android清单/界面资源/平台配置，主题 ic_launcher_round（目录与文件名推断） | 按目录和文件类型定位 |

### android_client/app/src/main/res/values/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [colors.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/values/colors.xml>) | Android清单/界面资源/平台配置，主题 colors（目录与文件名推断） | 按目录和文件类型定位 |
| [strings.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/values/strings.xml>) | Android清单/界面资源/平台配置，主题 strings（目录与文件名推断） | 按目录和文件类型定位 |
| [themes.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/values/themes.xml>) | Android清单/界面资源/平台配置，主题 themes（目录与文件名推断） | 按目录和文件类型定位 |

### android_client/app/src/main/res/values-night/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [colors.xml](<E:/PythonCode/EasyChat/android_client/app/src/main/res/values-night/colors.xml>) | Android清单/界面资源/平台配置，主题 colors（目录与文件名推断） | 按目录和文件类型定位 |

### android_client/app/src/test/java/com/easychat/family/designsystem/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [ContrastTest.kt](<E:/PythonCode/EasyChat/android_client/app/src/test/java/com/easychat/family/designsystem/ContrastTest.kt>) | Kotlin/Compose Android客户端中的测试相关实现（目录与文件名推断） | 符号 ContrastTest, assertAtLeast |
| [TypeScaleTest.kt](<E:/PythonCode/EasyChat/android_client/app/src/test/java/com/easychat/family/designsystem/TypeScaleTest.kt>) | Kotlin/Compose Android客户端中的测试相关实现（目录与文件名推断） | 符号 TypeScaleTest |

### android_client/app/src/test/java/com/easychat/family/util/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [XnTimeTest.kt](<E:/PythonCode/EasyChat/android_client/app/src/test/java/com/easychat/family/util/XnTimeTest.kt>) | Kotlin/Compose Android客户端中的测试相关实现（目录与文件名推断） | 符号 XnTimeTest |

### android_client/gradle/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [libs.versions.toml](<E:/PythonCode/EasyChat/android_client/gradle/libs.versions.toml>) | Kotlin/Compose Android客户端的配置或结构化资源，主题 libs.versions（目录与文件名推断） | 按目录和文件类型定位 |

### android_client/gradle/wrapper/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [gradle-wrapper.jar](<E:/PythonCode/EasyChat/android_client/gradle/wrapper/gradle-wrapper.jar>) | Kotlin/Compose Android客户端使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [gradle-wrapper.properties](<E:/PythonCode/EasyChat/android_client/gradle/wrapper/gradle-wrapper.properties>) | 依赖解析或构建工具版本锁定（文件约定） | 按目录和文件类型定位 |

### backend/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/__init__.py>) | 仓库根目录的配置、入口或辅助文件的包入口或导出（包结构） | 按目录和文件类型定位 |
| [app.py](<E:/PythonCode/EasyChat/backend/app.py>) | 应用工厂、生命周期、异常与路由注册（路径与入口核查） | FastAPI 应用工厂（架构 §12.2：import 与 create_app 无副作用）。 / 符号 SPAStaticFiles, _LazyModule, _authenticate, _authenticate_ticket, _register_explicit_routers, error_to_response, create_app |
| [bootstrap.py](<E:/PythonCode/EasyChat/backend/bootstrap.py>) | 模块依赖装配、启动与关闭顺序（路径与入口核查） | 显式装配与启动顺序（架构 §2/A01、§10）。 / 符号 ModuleRegistry, run_startup, _make_superagent_intake, _make_care_canceller, _make_delivery_sent, _make_run_finished, run_shutdown |
| [bootstrap_tools.py](<E:/PythonCode/EasyChat/backend/bootstrap_tools.py>) | 仓库根目录的配置、入口或辅助文件中的工具相关实现（目录与文件名推断） | bootstrap 注入的业务工具集合。 / 符号 extra_tools |
| [build_info.py](<E:/PythonCode/EasyChat/backend/build_info.py>) | 仓库根目录的配置、入口或辅助文件中的build_info 实现（目录与文件名推断） | 构建指纹。开发环境为占位值；发布构建时由 backend/scripts/gen_build_info.sh 覆写。 |
| [server.py](<E:/PythonCode/EasyChat/backend/server.py>) | 供Uvicorn导入的ASGI应用入口（路径与入口核查） | 新架构启动入口：显式读取环境配置 → create_app（import 不连库/不迁移）。 |

### backend/config/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [database_schema_reference.md](<E:/PythonCode/EasyChat/backend/config/database_schema_reference.md>) | 路径与模型目录等配置资料的说明、设计或验证文档，主题 database_schema_reference（目录与文件名推断） | AgentForge 数据库表结构参考 |
| [models_dev.json](<E:/PythonCode/EasyChat/backend/config/models_dev.json>) | 路径与模型目录等配置资料的配置或结构化资源，主题 models_dev（目录与文件名推断） | 按目录和文件类型定位 |
| [paths.py](<E:/PythonCode/EasyChat/backend/config/paths.py>) | 路径与模型目录等配置资料中的paths 实现（目录与文件名推断） | AgentForge 路径配置模块 / 符号 get_data_root, _ensure_dir, get_uploads_dir, get_chat_uploads_dir, get_cron_reports_dir, get_kb_dir, get_kb_sources_dir |

### backend/context/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [TASK_EVIDENCE.md](<E:/PythonCode/EasyChat/backend/context/TASK_EVIDENCE.md>) | 上下文策略、任务证据与工具结果管理的说明、设计或验证文档，主题 TASK_EVIDENCE（目录与文件名推断） | TaskState 同步工具证据 |
| [__init__.py](<E:/PythonCode/EasyChat/backend/context/__init__.py>) | 上下文策略、任务证据与工具结果管理的包入口或导出（包结构） | 上下文压缩策略包 |
| [config.py](<E:/PythonCode/EasyChat/backend/context/config.py>) | 上下文策略、任务证据与工具结果管理中的配置相关实现（目录与文件名推断） | 上下文压缩策略配置 / 符号 get_context_strategy, get_fact_anchor_max_facts, get_fact_anchor_enabled |
| [factory.py](<E:/PythonCode/EasyChat/backend/context/factory.py>) | 上下文策略、任务证据与工具结果管理中的factory 实现（目录与文件名推断） | 上下文压缩策略工厂 / 符号 create_engine |
| [task_evidence.py](<E:/PythonCode/EasyChat/backend/context/task_evidence.py>) | 上下文策略、任务证据与工具结果管理中的任务相关实现（目录与文件名推断） | Bounded synchronous evidence ledger. Semantic/LLM updates never write this table. / 符号 _encode, EvidenceLedger, _Transaction |
| [task_state.py](<E:/PythonCode/EasyChat/backend/context/task_state.py>) | 上下文策略、任务证据与工具结果管理中的任务、状态相关实现（目录与文件名推断） | task_state —— 会话级任务状态主动维护 / 符号 TaskStateMaintainer, get_task_state_maintainer |

### backend/context/strategies/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/context/strategies/__init__.py>) | 上下文策略、任务证据与工具结果管理的包入口或导出（包结构） | 上下文压缩策略实现包 |
| [default.py](<E:/PythonCode/EasyChat/backend/context/strategies/default.py>) | 上下文策略、任务证据与工具结果管理中的default 实现（目录与文件名推断） | default 策略 —— 直接使用 Hermes 自带的 ContextCompressor / 符号 build |
| [fact_anchor.py](<E:/PythonCode/EasyChat/backend/context/strategies/fact_anchor.py>) | 上下文策略、任务证据与工具结果管理中的fact_anchor 实现（目录与文件名推断） | fact_anchor 策略 —— 压缩前先抽关键事实作为只读片段注入 / 符号 build, FactAnchorCompressor |

### backend/context/tool_results/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [README.md](<E:/PythonCode/EasyChat/backend/context/tool_results/README.md>) | 上下文策略、任务证据与工具结果管理的说明、设计或验证文档，主题 README（目录与文件名推断） | Tool result management — deterministic foundation |
| [__init__.py](<E:/PythonCode/EasyChat/backend/context/tool_results/__init__.py>) | 上下文策略、任务证据与工具结果管理的包入口或导出（包结构） | Scoped, deterministic tool-result management. Importing has no I/O side effects. |
| [capture.py](<E:/PythonCode/EasyChat/backend/context/tool_results/capture.py>) | 上下文策略、任务证据与工具结果管理中的capture 实现（目录与文件名推断） | Trusted, bounded CodeMode output sidecars, independent of application services. / 符号 CapturedOutput, OutputSink, CaptureSession, get_capture_session, capture_context |
| [compression.py](<E:/PythonCode/EasyChat/backend/context/tool_results/compression.py>) | 上下文策略、任务证据与工具结果管理中的上下文压缩相关实现（目录与文件名推断） | Protect managed results from legacy pruning; no active history-folding policy. / 符号 _metadata, _manifest, ManagedResultsCompressor, install_compression_guard |
| [json_locations.py](<E:/PythonCode/EasyChat/backend/context/tool_results/json_locations.py>) | 上下文策略、任务证据与工具结果管理中的json_locations 实现（目录与文件名推断） | Bounded JSON token locations for literal search; no inferred or rewritten paths. / 符号 _size, _Unavailable, _Node, JsonLocations |
| [manager.py](<E:/PythonCode/EasyChat/backend/context/tool_results/manager.py>) | 上下文策略、任务证据与工具结果管理中的manager 实现（目录与文件名推断） | Choose bounded model views while retaining exact source values and originals. / 符号 _dump, _protected_key, extract_protected, PreparedResult, ResultManager |
| [options.py](<E:/PythonCode/EasyChat/backend/context/tool_results/options.py>) | 上下文策略、任务证据与工具结果管理中的options 实现（目录与文件名推断） | Validated, frozen per-run policy choices shared with offline experiment profiles. / 符号 validate_options, runtime_options |
| [projection.py](<E:/PythonCode/EasyChat/backend/context/tool_results/projection.py>) | 上下文策略、任务证据与工具结果管理中的projection 实现（目录与文件名推断） | History-anchored evidence projections; no hidden cursor survives compaction. / 符号 _encode, _chain, evidence_message |
| [runtime.py](<E:/PythonCode/EasyChat/backend/context/tool_results/runtime.py>) | 上下文策略、任务证据与工具结果管理中的执行运行时相关实现（目录与文件名推断） | Authenticated per-run binding and per-tool scopes, inherited through copy_context. / 符号 context_results_enabled, default_store_root, is_result_store_path, ActiveTool, active_tool, managed_results_active, HostResultRuntime |
| [selection.py](<E:/PythonCode/EasyChat/backend/context/tool_results/selection.py>) | 上下文策略、任务证据与工具结果管理中的selection 实现（目录与文件名推断） | Key-agnostic, bounded candidates; these are observations, not relevance judgments. / 符号 other_fields |
| [store.py](<E:/PythonCode/EasyChat/backend/context/tool_results/store.py>) | 上下文策略、任务证据与工具结果管理中的store 实现（目录与文件名推断） | Single-host durable originals, explicit grants and bounded recovery. / 符号 _hash, _line_layout, _metadata, ResultStore |
| [tools.py](<E:/PythonCode/EasyChat/backend/context/tool_results/tools.py>) | 上下文策略、任务证据与工具结果管理中的工具相关实现（目录与文件名推断） | Model-visible recovery tools; identity and budgets are never model arguments. / 符号 _encode, _compact_search_structure, _bounded_call, context_read, context_search |
| [types.py](<E:/PythonCode/EasyChat/backend/context/tool_results/types.py>) | 上下文策略、任务证据与工具结果管理中的types 实现（目录与文件名推断） | Trusted identity for stored tool results; physical sessions are audit data. / 符号 ResultScope |

### backend/hermes/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [.dockerignore](<E:/PythonCode/EasyChat/backend/hermes/.dockerignore>) | 内嵌 Hermes 上游源码及项目适配内容中的.dockerignore 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [.env.example](<E:/PythonCode/EasyChat/backend/hermes/.env.example>) | 本地环境/认证配置，仅说明路径职责，内容未展开（路径类型） | 按目录和文件类型定位 |
| [.envrc](<E:/PythonCode/EasyChat/backend/hermes/.envrc>) | 本地环境/认证配置，仅说明路径职责，内容未展开（路径类型） | 按目录和文件类型定位 |
| [.gitattributes](<E:/PythonCode/EasyChat/backend/hermes/.gitattributes>) | 内嵌 Hermes 上游源码及项目适配内容中的.gitattributes 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [.hadolint.yaml](<E:/PythonCode/EasyChat/backend/hermes/.hadolint.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 .hadolint（目录与文件名推断） | 按目录和文件类型定位 |
| [.mailmap](<E:/PythonCode/EasyChat/backend/hermes/.mailmap>) | 内嵌 Hermes 上游源码及项目适配内容中的.mailmap 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [.prettierignore](<E:/PythonCode/EasyChat/backend/hermes/.prettierignore>) | 内嵌 Hermes 上游源码及项目适配内容中的.prettierignore 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [.prettierrc](<E:/PythonCode/EasyChat/backend/hermes/.prettierrc>) | 内嵌 Hermes 上游源码及项目适配内容中的.prettierrc 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Hermes 完整源码 |
| [hermes_bootstrap.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_bootstrap.py>) | 内嵌 Hermes 上游源码及项目适配内容中的hermes_bootstrap 实现（目录与文件名推断） | Windows UTF-8 bootstrap for Hermes entry points. / 符号 apply_windows_utf8_bootstrap, suppress_platform_ver_console, harden_import_path, activate_durable_lazy_target |
| [hermes_constants.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_constants.py>) | 内嵌 Hermes 上游源码及项目适配内容中的hermes_constants 实现（目录与文件名推断） | Shared constants for Hermes Agent. / 符号 set_hermes_home_override, reset_hermes_home_override, get_hermes_home_override, _get_platform_default_hermes_home, _hermes_home_from_env, _warn_profile_fallback_once, get_hermes_home |
| [hermes_logging.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_logging.py>) | 内嵌 Hermes 上游源码及项目适配内容中的hermes_logging 实现（目录与文件名推断） | Centralized logging setup for Hermes Agent. / 符号 _safe_stderr, _is_windows_concurrent_log_lock_timeout, set_session_context, clear_session_context, _install_session_record_factory, _ComponentFilter, setup_logging |
| [hermes_state.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_state.py>) | 内嵌 Hermes 上游源码及项目适配内容中的状态相关实现（目录与文件名推断） | SQLite State Store for Hermes Agent. / 符号 _compression_lock_holder_process_is_dead, _scrub_surrogates, workspace_key, _delegate_from_json, _cwd_prefix_clause, _workspace_key_clause, _collect_delegate_child_ids |
| [hermes_state_common.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_state_common.py>) | 内嵌 Hermes 上游源码及项目适配内容中的状态相关实现（目录与文件名推断） | Shared module-level constants for the SessionDB family of modules. / 符号 _shape_preview, _ephemeral_child_sql |
| [hermes_state_portability.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_state_portability.py>) | 内嵌 Hermes 上游源码及项目适配内容中的状态相关实现（目录与文件名推断） | Session listing/rich rows, export, and import (portability) for SessionDB. / 符号 SessionPortabilityMixin |
| [hermes_state_schema.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_state_schema.py>) | 内嵌 Hermes 上游源码及项目适配内容中的状态相关实现（目录与文件名推断） | Schema creation, column reconciliation, and FTS DDL management for SessionDB. / 符号 SessionSchemaMixin |
| [hermes_state_search.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_state_search.py>) | 内嵌 Hermes 上游源码及项目适配内容中的状态、搜索相关实现（目录与文件名推断） | Full-text / trigram / CJK message search and FTS maintenance for SessionDB. / 符号 SessionSearchMixin |
| [hermes_time.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_time.py>) | 内嵌 Hermes 上游源码及项目适配内容中的hermes_time 实现（目录与文件名推断） | Timezone-aware clock for Hermes. / 符号 _resolve_timezone_name, _get_zoneinfo, get_timezone, reset_cache, now |
| [model_tools.py](<E:/PythonCode/EasyChat/backend/hermes/model_tools.py>) | 内嵌 Hermes 上游源码及项目适配内容中的模型、工具相关实现（目录与文件名推断） | Model Tools Module / 符号 _is_delegated_child_context, _get_tool_loop, _get_worker_loop, _run_async, _clear_tool_defs_cache, get_tool_definitions, _compute_tool_definitions |
| [run_agent.py](<E:/PythonCode/EasyChat/backend/hermes/run_agent.py>) | 内嵌 Hermes 上游源码及项目适配内容中的代理相关实现（目录与文件名推断） | Hermes AI Agent 运行器 / 符号 _launch_cwd_for_session, _session_source_for_agent, _is_ephemeral_scaffolding, _routermint_headers, _pool_may_recover_from_rate_limit, _qwen_portal_headers, _safe_session_filename_component |
| [toolset_distributions.py](<E:/PythonCode/EasyChat/backend/hermes/toolset_distributions.py>) | 内嵌 Hermes 上游源码及项目适配内容中的toolset_distributions 实现（目录与文件名推断） | Toolset Distributions Module / 符号 get_distribution, list_distributions, sample_toolsets_from_distribution, validate_distribution, print_distribution_info |
| [toolsets.py](<E:/PythonCode/EasyChat/backend/hermes/toolsets.py>) | 内嵌 Hermes 上游源码及项目适配内容中的toolsets 实现（目录与文件名推断） | Toolsets Module / 符号 get_toolset, bundle_non_core_tools, resolve_toolset, resolve_multiple_toolsets, _get_plugin_toolset_names, _get_registry_toolset_aliases, get_all_toolsets |
| [utils.py](<E:/PythonCode/EasyChat/backend/hermes/utils.py>) | 内嵌 Hermes 上游源码及项目适配内容中的utils 实现（目录与文件名推断） | Shared utility functions for hermes-agent. / 符号 is_truthy_value, env_var_enabled, _preserve_file_mode, _preserve_file_owner, _restore_file_owner, _restore_file_mode, atomic_replace |

### backend/hermes/acp_adapter/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/acp_adapter/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | ACP (Agent Communication Protocol) adapter for hermes-agent. |
| [__main__.py](<E:/PythonCode/EasyChat/backend/hermes/acp_adapter/__main__.py>) | 内嵌 Hermes 上游源码及项目适配内容中的主入口相关实现（目录与文件名推断） | Allow running the ACP adapter as ''python -m acp_adapter''. |
| [auth.py](<E:/PythonCode/EasyChat/backend/hermes/acp_adapter/auth.py>) | 内嵌 Hermes 上游源码及项目适配内容中的认证相关实现（目录与文件名推断） | ACP auth helpers — detect and advertise Hermes authentication methods. / 符号 detect_provider, has_provider, build_auth_methods |
| [edit_approval.py](<E:/PythonCode/EasyChat/backend/hermes/acp_adapter/edit_approval.py>) | 内嵌 Hermes 上游源码及项目适配内容中的审批相关实现（目录与文件名推断） | Pre-execution ACP edit approval helpers. / 符号 EditProposal, set_edit_approval_requester, reset_edit_approval_requester, clear_edit_approval_requester, get_edit_approval_requester, _read_text_if_exists, _proposal_for_write_file |
| [entry.py](<E:/PythonCode/EasyChat/backend/hermes/acp_adapter/entry.py>) | 内嵌 Hermes 上游源码及项目适配内容中的entry 实现（目录与文件名推断） | CLI entry point for the hermes-agent ACP adapter. / 符号 _BenignProbeMethodFilter, _setup_logging, _load_env, _parse_args, _print_version, _run_check, _run_setup |
| [events.py](<E:/PythonCode/EasyChat/backend/hermes/acp_adapter/events.py>) | 内嵌 Hermes 上游源码及项目适配内容中的events 实现（目录与文件名推断） | Callback factories for bridging AIAgent events to ACP notifications. / 符号 _json_loads_maybe_prefix, _build_plan_update_from_todo_result, _send_update, make_tool_progress_cb, make_thinking_cb, make_step_cb, make_message_cb |
| [permissions.py](<E:/PythonCode/EasyChat/backend/hermes/acp_adapter/permissions.py>) | 内嵌 Hermes 上游源码及项目适配内容中的permissions 实现（目录与文件名推断） | ACP permission bridging for Hermes dangerous-command approvals. / 符号 _permission_option_supports_kind, _build_permission_options, _build_permission_tool_call, _map_outcome_to_hermes, make_approval_callback |
| [provenance.py](<E:/PythonCode/EasyChat/backend/hermes/acp_adapter/provenance.py>) | 内嵌 Hermes 上游源码及项目适配内容中的provenance 实现（目录与文件名推断） | Derive ACP session-provenance metadata from the existing compression chain. / 符号 build_session_provenance, session_provenance_meta |
| [server.py](<E:/PythonCode/EasyChat/backend/hermes/acp_adapter/server.py>) | 内嵌 Hermes 上游源码及项目适配内容中的server 实现（目录与文件名推断） | ACP agent server — exposes Hermes Agent via the Agent Client Protocol. / 符号 _named_custom_provider_catalogs, _resource_display_name, _is_text_resource, _is_image_resource, _guess_image_mime_from_path, _image_data_url, _path_from_file_uri |
| [session.py](<E:/PythonCode/EasyChat/backend/hermes/acp_adapter/session.py>) | 内嵌 Hermes 上游源码及项目适配内容中的会话相关实现（目录与文件名推断） | ACP session manager — maps ACP sessions to Hermes AIAgent instances. / 符号 _translate_acp_cwd, _normalize_cwd_for_compare, _build_session_title, _format_updated_at, _updated_at_sort_key, _acp_stderr_print, _register_task_cwd |
| [tools.py](<E:/PythonCode/EasyChat/backend/hermes/acp_adapter/tools.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | ACP tool-call helpers for mapping hermes tools to ACP ToolKind and building content. / 符号 get_tool_kind, make_tool_call_id, build_tool_title, _text, _json_loads_maybe, _tool_result_failed, _truncate_text |

### backend/hermes/agent/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/agent/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Agent internals -- extracted modules from run_agent.py. |
| [account_usage.py](<E:/PythonCode/EasyChat/backend/hermes/agent/account_usage.py>) | 内嵌 Hermes 上游源码及项目适配内容中的用量相关实现（目录与文件名推断） | 符号 _utc_now, AccountUsageWindow, AccountUsageSnapshot, _title_case_slug, _parse_dt, _format_reset, render_account_usage_lines |
| [agent_init.py](<E:/PythonCode/EasyChat/backend/hermes/agent/agent_init.py>) | 内嵌 Hermes 上游源码及项目适配内容中的代理相关实现（目录与文件名推断） | Implementation of :meth:'AIAgent.__init__' — extracted as a module function. / 符号 _ra, _moa_reference_output_allowed, _relay_moa_reference_event, _normalize_route_base_url, _provider_default_routes, _context_route_mismatch, _normalize_custom_provider_name |
| [agent_runtime_helpers.py](<E:/PythonCode/EasyChat/backend/hermes/agent/agent_runtime_helpers.py>) | 内嵌 Hermes 上游源码及项目适配内容中的代理、执行运行时相关实现（目录与文件名推断） | Assorted AIAgent runtime helpers — moved out of run_agent.py for clarity. / 符号 _ra, agent_runtime_owns_post_tool_hook, convert_to_trajectory_format, sanitize_tool_call_arguments, note_turn_start, note_turn_persisted, repair_message_sequence |
| [anthropic_adapter.py](<E:/PythonCode/EasyChat/backend/hermes/agent/anthropic_adapter.py>) | 内嵌 Hermes 上游源码及项目适配内容中的anthropic_adapter 实现（目录与文件名推断） | Anthropic Messages API adapter for Hermes Agent. / 符号 _get_anthropic_sdk, _is_claude_model, _get_anthropic_max_output, _resolve_positive_anthropic_max_tokens, _resolve_anthropic_messages_max_tokens, _supports_adaptive_thinking, _supports_xhigh_effort |
| [async_utils.py](<E:/PythonCode/EasyChat/backend/hermes/agent/async_utils.py>) | 内嵌 Hermes 上游源码及项目适配内容中的async_utils 实现（目录与文件名推断） | Async/sync bridging helpers. / 符号 safe_schedule_threadsafe, consume_detached_task_result |
| [aux_accounting.py](<E:/PythonCode/EasyChat/backend/hermes/agent/aux_accounting.py>) | 内嵌 Hermes 上游源码及项目适配内容中的aux_accounting 实现（目录与文件名推断） | Ambient session-accounting context for auxiliary LLM calls. / 符号 set_accounting_context, reset_accounting_context, get_accounting_context, record_aux_usage |
| [auxiliary_client.py](<E:/PythonCode/EasyChat/backend/hermes/agent/auxiliary_client.py>) | 内嵌 Hermes 上游源码及项目适配内容中的auxiliary_client 实现（目录与文件名推断） | Shared auxiliary client router for side tasks. / 符号 _load_openai_cls, _OpenAIProxy, _resolve_aux_verify, _openai_http_client_kwargs, _create_openai_client, _aux_interrupt_protected, aux_interrupt_protection |
| [azure_identity_adapter.py](<E:/PythonCode/EasyChat/backend/hermes/agent/azure_identity_adapter.py>) | 内嵌 Hermes 上游源码及项目适配内容中的azure_identity_adapter 实现（目录与文件名推断） | Microsoft Entra ID adapter for Microsoft Foundry. / 符号 has_azure_identity_installed, _require_azure_identity, reset_credential_cache, EntraIdentityConfig, _build_default_credential, build_credential, build_token_provider |
| [backend_identity.py](<E:/PythonCode/EasyChat/backend/hermes/agent/backend_identity.py>) | 内嵌 Hermes 上游源码及项目适配内容中的backend_identity 实现（目录与文件名推断） | Single owner for backend identity and failure-scoped skip decisions. / 符号 FailureScope, classify_failure_scope, _norm_provider, _norm_model, _norm_base_url, BackendIdentity, _both_first_class |
| [background_review.py](<E:/PythonCode/EasyChat/backend/hermes/agent/background_review.py>) | 内嵌 Hermes 上游源码及项目适配内容中的background_review 实现（目录与文件名推断） | Background memory/skill review — fork the agent to evaluate the turn. / 符号 _resolve_review_runtime, _msg_text, _digest_history, summarize_background_review_actions, build_memory_write_metadata, _run_review_in_thread, spawn_background_review_thread |
| [battery.py](<E:/PythonCode/EasyChat/backend/hermes/agent/battery.py>) | 内嵌 Hermes 上游源码及项目适配内容中的battery 实现（目录与文件名推断） | System-battery read-out for the CLI/TUI status bar. / 符号 BatteryStatus, _read_battery_uncached, read_battery, clear_cache, battery_category, battery_glyph, format_battery |
| [bedrock_adapter.py](<E:/PythonCode/EasyChat/backend/hermes/agent/bedrock_adapter.py>) | 内嵌 Hermes 上游源码及项目适配内容中的bedrock_adapter 实现（目录与文件名推断） | AWS Bedrock Converse API adapter for Hermes Agent. / 符号 _require_boto3, _get_bedrock_runtime_client, _get_bedrock_control_client, reset_client_cache, invalidate_runtime_client, _traceback_frames_modules, is_stale_connection_error |
| [billing_links.py](<E:/PythonCode/EasyChat/backend/hermes/agent/billing_links.py>) | 内嵌 Hermes 上游源码及项目适配内容中的billing_links 实现（目录与文件名推断） | Provider-agnostic billing/credit recovery links. / 符号 BillingBlock, _Provider, is_nous_inference_route, _nous_billing_url, _resolve_provider_link, build_billing_block |
| [billing_usage.py](<E:/PythonCode/EasyChat/backend/hermes/agent/billing_usage.py>) | 内嵌 Hermes 上游源码及项目适配内容中的用量相关实现（目录与文件名推断） | Shared dollar-denominated usage model for the billing/subscription surfaces. / 符号 _finite, _fmt_usd, format_renews, UsageBar, UsageModel, usage_model_from_account, build_usage_model |
| [billing_view.py](<E:/PythonCode/EasyChat/backend/hermes/agent/billing_view.py>) | 内嵌 Hermes 上游源码及项目适配内容中的billing_view 实现（目录与文件名推断） | Surface-agnostic core for the Phase 2b Remote Spending screens. / 符号 parse_money, format_money, CardInfo, PaymentMethodInfo, MonthlyCap, AutoReloadCard, AutoReload |
| [bounded_response.py](<E:/PythonCode/EasyChat/backend/hermes/agent/bounded_response.py>) | 内嵌 Hermes 上游源码及项目适配内容中的bounded_response 实现（目录与文件名推断） | Bounded reads of HTTP error response bodies. / 符号 read_streaming_error_body, _safe_close, read_error_body_or_default |
| [browser_provider.py](<E:/PythonCode/EasyChat/backend/hermes/agent/browser_provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的浏览器、供应商相关实现（目录与文件名推断） | Browser Provider ABC / 符号 BrowserProvider |
| [browser_registry.py](<E:/PythonCode/EasyChat/backend/hermes/agent/browser_registry.py>) | 内嵌 Hermes 上游源码及项目适配内容中的浏览器、注册表相关实现（目录与文件名推断） | Browser Provider Registry / 符号 register_provider, list_providers, get_provider, _resolve, _reset_for_tests |
| [chat_completion_helpers.py](<E:/PythonCode/EasyChat/backend/hermes/agent/chat_completion_helpers.py>) | 内嵌 Hermes 上游源码及项目适配内容中的聊天相关实现（目录与文件名推断） | Helper functions for the chat-completions code path. / 符号 _context_thread_target, _ra, estimate_request_context_tokens, _is_openai_codex_backend, openai_codex_stale_timeout_floor, _validated_openrouter_provider_sort, _provider_preferences_for_agent |
| [codex_responses_adapter.py](<E:/PythonCode/EasyChat/backend/hermes/agent/codex_responses_adapter.py>) | 内嵌 Hermes 上游源码及项目适配内容中的codex_responses_adapter 实现（目录与文件名推断） | Codex Responses API adapter. / 符号 _classify_responses_issuer, _chat_content_to_responses_parts, _summarize_user_message_for_log, _deterministic_call_id, _clamp_responses_call_id, _split_responses_tool_id, _derive_responses_function_call_id |
| [codex_runtime.py](<E:/PythonCode/EasyChat/backend/hermes/agent/codex_runtime.py>) | 内嵌 Hermes 上游源码及项目适配内容中的执行运行时相关实现（目录与文件名推断） | Codex API runtime — App Server and Responses-API streaming paths. / 符号 _coerce_usage_int, _record_codex_app_server_usage, _record_codex_app_server_compaction, _codex_item_to_tool_name, _codex_item_to_args, _codex_item_to_preview, _codex_item_completion_payload |
| [coding_context.py](<E:/PythonCode/EasyChat/backend/hermes/agent/coding_context.py>) | 内嵌 Hermes 上游源码及项目适配内容中的上下文相关实现（目录与文件名推断） | Coding-context awareness — base Hermes, every interactive surface. / 符号 _has_code_files, _model_family, _edit_format_line, ContextProfile, get_profile, _coding_mode, _coding_instructions |
| [context_breakdown.py](<E:/PythonCode/EasyChat/backend/hermes/agent/context_breakdown.py>) | 内嵌 Hermes 上游源码及项目适配内容中的上下文相关实现（目录与文件名推断） | Live session context-window breakdown for UI surfaces. / 符号 _chars_to_tokens, _json_tokens, _tool_name, _split_tools, _memory_blocks, _strip_blocks, compute_session_context_breakdown |
| [context_compressor.py](<E:/PythonCode/EasyChat/backend/hermes/agent/context_compressor.py>) | 内嵌 Hermes 上游源码及项目适配内容中的上下文相关实现（目录与文件名推断） | Automatic context window compression for long conversations. / 符号 _safe_int, _is_summary_access_or_quota_error, _fresh_compaction_message_copy, _strip_persistence_markers, _skill_pruned_marker, _extract_pruned_skill_names, _collect_ghosted_skill_names |
| [context_engine.py](<E:/PythonCode/EasyChat/backend/hermes/agent/context_engine.py>) | 内嵌 Hermes 上游源码及项目适配内容中的上下文相关实现（目录与文件名推断） | Abstract base class for pluggable context engines. / 符号 sanitize_memory_context, automatic_compaction_status_message, ContextEngine |
| [context_references.py](<E:/PythonCode/EasyChat/backend/hermes/agent/context_references.py>) | 内嵌 Hermes 上游源码及项目适配内容中的上下文相关实现（目录与文件名推断） | 符号 ContextReference, ContextReferenceResult, format_reference_value, parse_context_references, preprocess_context_references, preprocess_context_references_async, _expand_reference |
| [conversation_compression.py](<E:/PythonCode/EasyChat/backend/hermes/agent/conversation_compression.py>) | 内嵌 Hermes 上游源码及项目适配内容中的上下文压缩相关实现（目录与文件名推断） | Context compression — extract the AIAgent methods that drive summarisation. / 符号 _emit_compaction_done, _builtin_memory_prompt_snapshot, _cached_prompt_reflects_builtin_memory, CompressionCommitFence, _lock_api_is_absent_on_session_db, _refresh_persisted_compression_guards, _session_was_rotated_by_c |
| [conversation_loop.py](<E:/PythonCode/EasyChat/backend/hermes/agent/conversation_loop.py>) | 内嵌 Hermes 上游源码及项目适配内容中的conversation_loop 实现（目录与文件名推断） | The agent conversation loop — extracted from ''run_agent.AIAgent''. / 符号 _apply_active_turn_redirect, _image_error_max_dimension, _ollama_context_limit_error, _ra, _nous_entitlement_message, _print_nous_entitlement_guidance, _is_nous_inference_route |
| [copilot_acp_client.py](<E:/PythonCode/EasyChat/backend/hermes/agent/copilot_acp_client.py>) | 内嵌 Hermes 上游源码及项目适配内容中的copilot_acp_client 实现（目录与文件名推断） | OpenAI-compatible shim that forwards Hermes requests to 'copilot --acp'. / 符号 _is_gh_copilot_deprecation_message, _resolve_command, _resolve_args, _resolve_home_dir, _build_subprocess_env, _jsonrpc_error, _permission_denied |
| [credential_persistence.py](<E:/PythonCode/EasyChat/backend/hermes/agent/credential_persistence.py>) | 内嵌 Hermes 上游源码及项目适配内容中的credential_persistence 实现（目录与文件名推断） | Credential-pool disk-boundary sanitization helpers. / 符号 _normalize_key, is_borrowed_credential_source, _is_secret_payload_key, _fingerprint_value, _credential_secret_fingerprint, sanitize_borrowed_credential_payload |
| [credential_pool.py](<E:/PythonCode/EasyChat/backend/hermes/agent/credential_pool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的credential_pool 实现（目录与文件名推断） | Persistent multi-credential pool for same-provider failover. / 符号 _load_config_safe, _normalize_pool_auth_type, PooledCredential, label_from_token, _next_priority, _is_manual_source, _exhausted_ttl |
| [credential_sources.py](<E:/PythonCode/EasyChat/backend/hermes/agent/credential_sources.py>) | 内嵌 Hermes 上游源码及项目适配内容中的credential_sources 实现（目录与文件名推断） | Unified removal contract for every credential source Hermes reads from. / 符号 RemovalResult, RemovalStep, register, find_removal_step, _remove_env_source, _remove_claude_code, _remove_hermes_pkce |
| [credits_tracker.py](<E:/PythonCode/EasyChat/backend/hermes/agent/credits_tracker.py>) | 内嵌 Hermes 上游源码及项目适配内容中的credits_tracker 实现（目录与文件名推断） | Credits tracking for Nous inference API responses. / 符号 _safe_int, _validate_usd, CreditsState, new_credits_latch, AgentNotice, is_free_tier_model, evaluate_credits_notices |
| [curator.py](<E:/PythonCode/EasyChat/backend/hermes/agent/curator.py>) | 内嵌 Hermes 上游源码及项目适配内容中的curator 实现（目录与文件名推断） | Curator — background skill maintenance orchestrator. / 符号 _strip_aux_credential, _ReviewRuntimeBinding, _merge_request_overrides, _state_file, _default_state, load_state, save_state |
| [curator_backup.py](<E:/PythonCode/EasyChat/backend/hermes/agent/curator_backup.py>) | 内嵌 Hermes 上游源码及项目适配内容中的备份相关实现（目录与文件名推断） | Curator snapshot + rollback. / 符号 _backups_dir, _skills_dir, _cron_jobs_file, _backup_cron_jobs_into, _utc_id, _load_config, is_enabled |
| [delegation_context.py](<E:/PythonCode/EasyChat/backend/hermes/agent/delegation_context.py>) | 内嵌 Hermes 上游源码及项目适配内容中的上下文相关实现（目录与文件名推断） | Context-local state for delegate_task child execution. / 符号 delegated_child_context, is_delegated_child_context, is_delegated_child_process_context, scrub_kanban_env, delegated_child_subprocess_env |
| [display.py](<E:/PythonCode/EasyChat/backend/hermes/agent/display.py>) | 内嵌 Hermes 上游源码及项目适配内容中的display 实现（目录与文件名推断） | CLI presentation -- spinner, kawaii faces, tool preview formatting. / 符号 _display_url, _diff_ansi, _diff_dim, _diff_file, _diff_hunk, _diff_minus, _diff_plus |
| [error_classifier.py](<E:/PythonCode/EasyChat/backend/hermes/agent/error_classifier.py>) | 内嵌 Hermes 上游源码及项目适配内容中的error_classifier 实现（目录与文件名推断） | API error classification for smart failover and recovery. / 符号 FailoverReason, ClassifiedError, classify_api_error, _classify_by_status, _classify_402, _classify_400, _classify_by_error_code |
| [errors.py](<E:/PythonCode/EasyChat/backend/hermes/agent/errors.py>) | 内嵌 Hermes 上游源码及项目适配内容中的errors 实现（目录与文件名推断） | 符号 SSLConfigurationError, EmptyStreamError, MoAPresetNotFoundError |
| [file_safety.py](<E:/PythonCode/EasyChat/backend/hermes/agent/file_safety.py>) | 内嵌 Hermes 上游源码及项目适配内容中的文件相关实现（目录与文件名推断） | Shared file safety rules used by both tools and ACP shims. / 符号 _hermes_home_path, _hermes_root_path, build_write_denied_paths, build_write_denied_prefixes, get_safe_write_roots, _classify_write_denial, is_write_denied |
| [gemini_native_adapter.py](<E:/PythonCode/EasyChat/backend/hermes/agent/gemini_native_adapter.py>) | 内嵌 Hermes 上游源码及项目适配内容中的gemini_native_adapter 实现（目录与文件名推断） | OpenAI-compatible facade over Google AI Studio's native Gemini API. / 符号 bare_gemini_model_id, is_native_gemini_base_url, probe_gemini_tier, is_free_tier_quota_error, is_standard_key_auth_error, GeminiAPIError, _coerce_content_to_text |
| [gemini_schema.py](<E:/PythonCode/EasyChat/backend/hermes/agent/gemini_schema.py>) | 内嵌 Hermes 上游源码及项目适配内容中的gemini_schema 实现（目录与文件名推断） | Helpers for translating OpenAI-style tool schemas to Gemini's schema subset. / 符号 sanitize_gemini_schema, sanitize_gemini_tool_parameters |
| [i18n.py](<E:/PythonCode/EasyChat/backend/hermes/agent/i18n.py>) | 内嵌 Hermes 上游源码及项目适配内容中的i18n 实现（目录与文件名推断） | Lightweight internationalization (i18n) for Hermes static user-facing messages. / 符号 _locales_dir, _normalize_lang, _load_catalog, _flatten_into, _config_language_cached, reset_language_cache, get_language |
| [image_gen_provider.py](<E:/PythonCode/EasyChat/backend/hermes/agent/image_gen_provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的供应商相关实现（目录与文件名推断） | Image Generation Provider ABC / 符号 ImageGenProvider, resolve_aspect_ratio, normalize_reference_images, _images_cache_dir, save_b64_image, save_url_image, success_response |
| [image_gen_registry.py](<E:/PythonCode/EasyChat/backend/hermes/agent/image_gen_registry.py>) | 内嵌 Hermes 上游源码及项目适配内容中的注册表相关实现（目录与文件名推断） | Image Generation Provider Registry / 符号 register_provider, list_providers, get_provider, get_active_provider, _reset_for_tests |
| [image_routing.py](<E:/PythonCode/EasyChat/backend/hermes/agent/image_routing.py>) | 内嵌 Hermes 上游源码及项目适配内容中的image_routing 实现（目录与文件名推断） | Routing helpers for inbound user-attached images. / 符号 extract_image_refs, _coerce_capability_bool, _supports_vision_override, _resolve_inference_base_url, _should_probe_ollama_vision, _coerce_mode, _explicit_aux_vision_override |
| [insights.py](<E:/PythonCode/EasyChat/backend/hermes/agent/insights.py>) | 内嵌 Hermes 上游源码及项目适配内容中的insights 实现（目录与文件名推断） | Session Insights Engine for Hermes Agent. / 符号 _estimate_cost, _bar_chart, InsightsEngine |
| [iteration_budget.py](<E:/PythonCode/EasyChat/backend/hermes/agent/iteration_budget.py>) | 内嵌 Hermes 上游源码及项目适配内容中的iteration_budget 实现（目录与文件名推断） | Per-agent iteration budget — thread-safe consume/refund counter. / 符号 IterationBudget |
| [jiter_preload.py](<E:/PythonCode/EasyChat/backend/hermes/agent/jiter_preload.py>) | 内嵌 Hermes 上游源码及项目适配内容中的jiter_preload 实现（目录与文件名推断） | Best-effort early import for the OpenAI SDK's native streaming parser. / 符号 preload_jiter_native_extension |
| [learn_prompt.py](<E:/PythonCode/EasyChat/backend/hermes/agent/learn_prompt.py>) | 内嵌 Hermes 上游源码及项目适配内容中的提示词相关实现（目录与文件名推断） | ''/learn'' — build the standards-guided prompt that turns whatever the user / 符号 build_learn_prompt |
| [learning_graph.py](<E:/PythonCode/EasyChat/backend/hermes/agent/learning_graph.py>) | 内嵌 Hermes 上游源码及项目适配内容中的图数据相关实现（目录与文件名推断） | Assemble the "learning made visible" graph for desktop. / 符号 SkillNode, _frontmatter, _hermes_meta, _related, _category, _iter_skill_files, _load_usage |
| [learning_graph_render.py](<E:/PythonCode/EasyChat/backend/hermes/agent/learning_graph_render.py>) | 内嵌 Hermes 上游源码及项目适配内容中的图数据相关实现（目录与文件名推断） | Terminal renderer for the learning timeline (learned skills + memories). / 符号 _to_ts, _clamp, _smoothstep, recency_ink, format_date, compute_recency, _date_at |
| [learning_mutations.py](<E:/PythonCode/EasyChat/backend/hermes/agent/learning_mutations.py>) | 内嵌 Hermes 上游源码及项目适配内容中的learning_mutations 实现（目录与文件名推断） | User-initiated edit/delete for journey nodes (learned skills + memories). / 符号 parse_node_kind, _memories_dir, _parse_memory_id, _memory_local_index, _locate_memory, node_detail, _node_detail |
| [lmstudio_reasoning.py](<E:/PythonCode/EasyChat/backend/hermes/agent/lmstudio_reasoning.py>) | 内嵌 Hermes 上游源码及项目适配内容中的lmstudio_reasoning 实现（目录与文件名推断） | LM Studio reasoning-effort resolution shared by the chat-completions / 符号 resolve_lmstudio_effort |
| [manual_compression_feedback.py](<E:/PythonCode/EasyChat/backend/hermes/agent/manual_compression_feedback.py>) | 内嵌 Hermes 上游源码及项目适配内容中的上下文压缩、反馈相关实现（目录与文件名推断） | User-facing summaries for manual compression commands. / 符号 describe_compression_lock_skip, summarize_manual_compression |
| [markdown_tables.py](<E:/PythonCode/EasyChat/backend/hermes/agent/markdown_tables.py>) | 内嵌 Hermes 上游源码及项目适配内容中的markdown_tables 实现（目录与文件名推断） | CJK/wide-character-aware re-alignment of model-emitted markdown tables. / 符号 _disp_width, _pad_to_width, split_table_row, is_table_divider, looks_like_table_row, _render_block, _wrap_to_width |
| [memory_manager.py](<E:/PythonCode/EasyChat/backend/hermes/agent/memory_manager.py>) | 内嵌 Hermes 上游源码及项目适配内容中的记忆相关实现（目录与文件名推断） | MemoryManager — orchestrates memory providers for the agent. / 符号 normalize_tool_schema, memory_provider_tools_enabled, inject_memory_provider_tools, sanitize_context, StreamingContextScrubber, build_memory_context_block, MemoryManager |
| [memory_provider.py](<E:/PythonCode/EasyChat/backend/hermes/agent/memory_provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的记忆、供应商相关实现（目录与文件名推断） | Abstract base class for pluggable memory providers. / 符号 MemoryProvider |
| [message_content.py](<E:/PythonCode/EasyChat/backend/hermes/agent/message_content.py>) | 内嵌 Hermes 上游源码及项目适配内容中的message_content 实现（目录与文件名推断） | 符号 _field, _text_from_part, flatten_message_text |
| [message_sanitization.py](<E:/PythonCode/EasyChat/backend/hermes/agent/message_sanitization.py>) | 内嵌 Hermes 上游源码及项目适配内容中的message_sanitization 实现（目录与文件名推断） | Message and tool-payload sanitization helpers. / 符号 _sanitize_surrogates, _sanitize_structure_surrogates, _sanitize_messages_surrogates, _escape_invalid_chars_in_json_strings, _repair_tool_call_arguments, close_interrupted_tool_sequence, _strip_non_ascii |
| [moa_loop.py](<E:/PythonCode/EasyChat/backend/hermes/agent/moa_loop.py>) | 内嵌 Hermes 上游源码及项目适配内容中的moa_loop 实现（目录与文件名推断） | Mixture-of-Agents runtime helpers for /moa turns. / 符号 _redact_reference_text, _moa_privacy_mode, _redact_reference_outputs, _redact_trace_messages, _redact_trace_accounting, _RefAccounting, _slot_label |
| [moa_trace.py](<E:/PythonCode/EasyChat/backend/hermes/agent/moa_trace.py>) | 内嵌 Hermes 上游源码及项目适配内容中的moa_trace 实现（目录与文件名推断） | Full MoA turn trace persistence (opt-in via config ''moa.save_traces''). / 符号 _traces_enabled_and_dir, _sanitize_session_id, _slot_trace, save_moa_turn |
| [model_metadata.py](<E:/PythonCode/EasyChat/backend/hermes/agent/model_metadata.py>) | 内嵌 Hermes 上游源码及项目适配内容中的模型相关实现（目录与文件名推断） | Model metadata, context lengths, and token estimation utilities. / 符号 _resolve_requests_verify, _strip_provider_prefix, _get_model_metadata_cache_path, _model_metadata_disk_cache_age_seconds, _load_model_metadata_disk_cache, _save_model_metadata_disk_cache, grok_supports_reasoning_effort |
| [models_dev.py](<E:/PythonCode/EasyChat/backend/hermes/agent/models_dev.py>) | 内嵌 Hermes 上游源码及项目适配内容中的模型相关实现（目录与文件名推断） | Models.dev registry integration — primary database for providers and models. / 符号 ModelInfo, ProviderInfo, _get_cache_path, _static_models_dev_path, _load_disk_cache, _disk_cache_age_seconds, _save_disk_cache |
| [moonshot_schema.py](<E:/PythonCode/EasyChat/backend/hermes/agent/moonshot_schema.py>) | 内嵌 Hermes 上游源码及项目适配内容中的moonshot_schema 实现（目录与文件名推断） | Helpers for translating OpenAI-style tool schemas to Moonshot's schema subset. / 符号 _repair_schema, _ensure_required_array, _fill_missing_type, sanitize_moonshot_tool_parameters, sanitize_moonshot_tools, is_moonshot_model |
| [nous_rate_guard.py](<E:/PythonCode/EasyChat/backend/hermes/agent/nous_rate_guard.py>) | 内嵌 Hermes 上游源码及项目适配内容中的nous_rate_guard 实现（目录与文件名推断） | Cross-session rate limit guard for Nous Portal. / 符号 _state_path, _parse_reset_seconds, record_nous_rate_limit, nous_rate_limit_remaining, clear_nous_rate_limit, format_remaining, is_genuine_nous_rate_limit |
| [onboarding.py](<E:/PythonCode/EasyChat/backend/hermes/agent/onboarding.py>) | 内嵌 Hermes 上游源码及项目适配内容中的onboarding 实现（目录与文件名推断） | Contextual first-touch onboarding hints. / 符号 busy_input_hint_gateway, busy_input_hint_cli, tool_progress_hint_gateway, tool_progress_hint_cli, openclaw_residue_hint_cli, detect_openclaw_residue, profile_build_mode |
| [oneshot.py](<E:/PythonCode/EasyChat/backend/hermes/agent/oneshot.py>) | 内嵌 Hermes 上游源码及项目适配内容中的oneshot 实现（目录与文件名推断） | Shared one-off LLM requests for non-conversational helpers. / 符号 _truncate, _commit_message_template, render_template, run_oneshot, _strip_code_fence |
| [plugin_llm.py](<E:/PythonCode/EasyChat/backend/hermes/agent/plugin_llm.py>) | 内嵌 Hermes 上游源码及项目适配内容中的plugin_llm 实现（目录与文件名推断） | Plugin LLM facade — host-owned LLM access for trusted plugins. / 符号 PluginLlmTextInput, PluginLlmImageInput, PluginLlmUsage, PluginLlmCompleteResult, PluginLlmStructuredResult, _TrustPolicy, _normalize_ref |
| [portal_tags.py](<E:/PythonCode/EasyChat/backend/hermes/agent/portal_tags.py>) | 内嵌 Hermes 上游源码及项目适配内容中的portal_tags 实现（目录与文件名推断） | Centralized Nous Portal request tags. / 符号 set_conversation_context, reset_conversation_context, get_conversation_context, _hermes_version, hermes_client_tag, conversation_tag, nous_portal_tags |
| [process_bootstrap.py](<E:/PythonCode/EasyChat/backend/hermes/agent/process_bootstrap.py>) | 内嵌 Hermes 上游源码及项目适配内容中的process_bootstrap 实现（目录与文件名推断） | Process-level bootstrap helpers for ''run_agent''. / 符号 _load_openai_cls, _OpenAIProxy, _SafeWriter, _get_proxy_from_env, _get_proxy_for_base_url, build_keepalive_http_client, _install_safe_stdio |
| [prompt_builder.py](<E:/PythonCode/EasyChat/backend/hermes/agent/prompt_builder.py>) | 内嵌 Hermes 上游源码及项目适配内容中的提示词相关实现（目录与文件名推断） | System prompt assembly -- identity, platform hints, skills index, context files. / 符号 _scan_context_content, _find_git_root, _find_hermes_md, _strip_yaml_frontmatter, computer_use_guidance, format_steer_marker, _probe_remote_backend |
| [prompt_caching.py](<E:/PythonCode/EasyChat/backend/hermes/agent/prompt_caching.py>) | 内嵌 Hermes 上游源码及项目适配内容中的提示词相关实现（目录与文件名推断） | Anthropic prompt caching strategy. / 符号 _apply_cache_marker, _can_carry_marker, _build_marker, _apply_system_cache_markers, strip_anthropic_cache_control, apply_anthropic_cache_control |
| [rate_limit_tracker.py](<E:/PythonCode/EasyChat/backend/hermes/agent/rate_limit_tracker.py>) | 内嵌 Hermes 上游源码及项目适配内容中的rate_limit_tracker 实现（目录与文件名推断） | Rate limit tracking for inference API responses. / 符号 RateLimitBucket, RateLimitState, _safe_int, _safe_float, parse_rate_limit_headers, _fmt_count, _fmt_seconds |
| [reactions.py](<E:/PythonCode/EasyChat/backend/hermes/agent/reactions.py>) | 内嵌 Hermes 上游源码及项目适配内容中的reactions 实现（目录与文件名推断） | Token-free detection of user *reactions* to the agent. / 符号 detect_reaction |
| [reasoning_timeouts.py](<E:/PythonCode/EasyChat/backend/hermes/agent/reasoning_timeouts.py>) | 内嵌 Hermes 上游源码及项目适配内容中的reasoning_timeouts 实现（目录与文件名推断） | Per-reasoning-model stale-timeout floor for known reasoning models. / 符号 _match_any, get_reasoning_stale_timeout_floor |
| [redact.py](<E:/PythonCode/EasyChat/backend/hermes/agent/redact.py>) | 内嵌 Hermes 上游源码及项目适配内容中的redact 实现（目录与文件名推断） | Regex-based secret redaction for logs and tool output. / 符号 _is_word_start, _is_word_end, _key_has_secret_keyword, mask_secret, _mask_token, _redact_query_string, _redact_url_query_params |
| [relay_llm.py](<E:/PythonCode/EasyChat/backend/hermes/agent/relay_llm.py>) | 内嵌 Hermes 上游源码及项目适配内容中的relay_llm 实现（目录与文件名推断） | Core NeMo Relay adapters for physical Hermes provider attempts. / 符号 execute, execute_async, execute_current, execute_current_async, stream_current, stream, ManagedLlmStream |
| [relay_runtime.py](<E:/PythonCode/EasyChat/backend/hermes/agent/relay_runtime.py>) | 内嵌 Hermes 上游源码及项目适配内容中的执行运行时相关实现（目录与文件名推断） | Profile-scoped NeMo Relay runtimes owned by the Hermes agent core. / 符号 RelaySession, RelayRuntime, NoopRelayRuntime, RelayHostRegistry, ConversationLease, RelayTurnContext, RelaySessionCoordinator |
| [relay_tools.py](<E:/PythonCode/EasyChat/backend/hermes/agent/relay_tools.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Core NeMo Relay adapter for Hermes tool execution. / 符号 execute, _jsonable, _json_equal, _run_awaitable |
| [replay_cleanup.py](<E:/PythonCode/EasyChat/backend/hermes/agent/replay_cleanup.py>) | 内嵌 Hermes 上游源码及项目适配内容中的replay_cleanup 实现（目录与文件名推断） | Replay-history sanitization shared across resume code paths. / 符号 is_interrupted_tool_result, strip_interrupted_tool_tails, strip_dangling_tool_call_tail, sanitize_replay_history, is_dangerous_confirmation, strip_stale_dangerous_confirmations |
| [result_finalizer.py](<E:/PythonCode/EasyChat/backend/hermes/agent/result_finalizer.py>) | 内嵌 Hermes 上游源码及项目适配内容中的结果相关实现（目录与文件名推断） | Optional host callbacks at the canonical tool-message boundary. / 符号 _Batch, _runtime, managed_batch, tool_context, apply_pending_steer, sync_task_snapshot, drain_pre_api_steer |
| [retry_utils.py](<E:/PythonCode/EasyChat/backend/hermes/agent/retry_utils.py>) | 内嵌 Hermes 上游源码及项目适配内容中的retry_utils 实现（目录与文件名推断） | Retry utilities — jittered backoff for decorrelated retries. / 符号 jittered_backoff, _error_text, is_zai_coding_overload_error, adaptive_rate_limit_backoff, zai_coding_overload_retry_ceiling |
| [runtime_cwd.py](<E:/PythonCode/EasyChat/backend/hermes/agent/runtime_cwd.py>) | 内嵌 Hermes 上游源码及项目适配内容中的执行运行时相关实现（目录与文件名推断） | Single source of truth for the agent working directory. / 符号 _is_install_tree, set_session_cwd, clear_session_cwd, _session_cwd_override, resolve_agent_cwd, resolve_context_cwd |
| [secret_scope.py](<E:/PythonCode/EasyChat/backend/hermes/agent/secret_scope.py>) | 内嵌 Hermes 上游源码及项目适配内容中的secret_scope 实现（目录与文件名推断） | Profile-scoped credential resolution for multi-profile gateway multiplexing. / 符号 set_multiplex_active, is_multiplex_active, UnscopedSecretError, set_secret_scope, reset_secret_scope, current_secret_scope, _is_global_env |
| [shell_hooks.py](<E:/PythonCode/EasyChat/backend/hermes/agent/shell_hooks.py>) | 内嵌 Hermes 上游源码及项目适配内容中的shell_hooks 实现（目录与文件名推断） | Shell-script hooks bridge. / 符号 ShellHookSpec, register_from_config, iter_configured_hooks, reset_for_tests, _parse_hooks_block, _parse_single_entry, _spawn |
| [skill_bundles.py](<E:/PythonCode/EasyChat/backend/hermes/agent/skill_bundles.py>) | 内嵌 Hermes 上游源码及项目适配内容中的技能相关实现（目录与文件名推断） | Skill bundles — aliases that load multiple skills under one slash command. / 符号 _bundles_dir, _slugify, _iter_bundle_files, _max_mtime, _load_bundle_file, scan_bundles, get_skill_bundles |
| [skill_commands.py](<E:/PythonCode/EasyChat/backend/hermes/agent/skill_commands.py>) | 内嵌 Hermes 上游源码及项目适配内容中的技能相关实现（目录与文件名推断） | Shared slash command helpers for skills. / 符号 extract_user_instruction_from_skill_message, describe_skill_invocation, _extract_single_skill_user_instruction, _extract_bundle_user_instruction, _resolve_skill_commands_platform, _load_skill_payload, _inject_skill_config |
| [skill_preprocessing.py](<E:/PythonCode/EasyChat/backend/hermes/agent/skill_preprocessing.py>) | 内嵌 Hermes 上游源码及项目适配内容中的技能相关实现（目录与文件名推断） | Shared SKILL.md preprocessing helpers. / 符号 load_skills_config, substitute_template_vars, run_inline_shell, expand_inline_shell, preprocess_skill_content |
| [skill_utils.py](<E:/PythonCode/EasyChat/backend/hermes/agent/skill_utils.py>) | 内嵌 Hermes 上游源码及项目适配内容中的技能相关实现（目录与文件名推断） | Lightweight skill metadata utilities shared by prompt_builder and skills_tool. / 符号 is_excluded_skill_path, is_skill_support_path, yaml_load, parse_frontmatter, skill_matches_platform_list, skill_matches_platform, _detect_environment |
| [ssl_guard.py](<E:/PythonCode/EasyChat/backend/hermes/agent/ssl_guard.py>) | 内嵌 Hermes 上游源码及项目适配内容中的ssl_guard 实现（目录与文件名推断） | Preventive SSL CA certificate checks for Hermes Agent. / 符号 _skip_ssl_guard_enabled, _repair_hint, _ssl_err, _validate_bundle_path, verify_ca_bundle, verify_ca_bundle_with_fallback |
| [ssl_verify.py](<E:/PythonCode/EasyChat/backend/hermes/agent/ssl_verify.py>) | 内嵌 Hermes 上游源码及项目适配内容中的ssl_verify 实现（目录与文件名推断） | TLS verify resolution for httpx/OpenAI provider clients. / 符号 _coerce_insecure, resolve_httpx_verify |
| [stream_diag.py](<E:/PythonCode/EasyChat/backend/hermes/agent/stream_diag.py>) | 内嵌 Hermes 上游源码及项目适配内容中的流式事件相关实现（目录与文件名推断） | Stream diagnostics — per-attempt counters, exception chains, retry logging. / 符号 stream_diag_init, stream_diag_capture_response, flatten_exception_chain, log_stream_retry, emit_stream_drop |
| [stream_single_writer.py](<E:/PythonCode/EasyChat/backend/hermes/agent/stream_single_writer.py>) | 内嵌 Hermes 上游源码及项目适配内容中的流式事件相关实现（目录与文件名推断） | Best-effort accessors for the single-writer stream fence (#65991). / 符号 claim_stream_writer, stream_writer_is_current |
| [subagent_lifecycle.py](<E:/PythonCode/EasyChat/backend/hermes/agent/subagent_lifecycle.py>) | 内嵌 Hermes 上游源码及项目适配内容中的subagent_lifecycle 实现（目录与文件名推断） | Public, plugin-safe lifecycle API for delegated Hermes subagents. / 符号 SubagentLifecycleError, SubagentState, SubagentLaunchRequest, SubagentHandle, SubagentStatus, SubagentTerminalState, SubagentCancelResult |
| [subdirectory_hints.py](<E:/PythonCode/EasyChat/backend/hermes/agent/subdirectory_hints.py>) | 内嵌 Hermes 上游源码及项目适配内容中的subdirectory_hints 实现（目录与文件名推断） | Progressive subdirectory hint discovery. / 符号 _is_ancestor_or_same, SubdirectoryHintTracker |
| [subscription_view.py](<E:/PythonCode/EasyChat/backend/hermes/agent/subscription_view.py>) | 内嵌 Hermes 上游源码及项目适配内容中的subscription_view 实现（目录与文件名推断） | Surface-agnostic core for the ''/subscription'' TUI screen. / 符号 CurrentSubscription, SubscriptionTier, SubscriptionChangePreview, SubscriptionState, _parse_current, _coalesce, _parse_tier |
| [system_prompt.py](<E:/PythonCode/EasyChat/backend/hermes/agent/system_prompt.py>) | 内嵌 Hermes 上游源码及项目适配内容中的提示词相关实现（目录与文件名推断） | System-prompt assembly for :class:'AIAgent'. / 符号 _ra, _resolve_platform_hint, _tui_embedded_pane_clarifier, build_system_prompt_parts, build_system_prompt, invalidate_system_prompt, reconstruct_static_prefix |
| [think_scrubber.py](<E:/PythonCode/EasyChat/backend/hermes/agent/think_scrubber.py>) | 内嵌 Hermes 上游源码及项目适配内容中的think_scrubber 实现（目录与文件名推断） | Stateful scrubber for reasoning/thinking blocks in streamed assistant text. / 符号 StreamingThinkScrubber |
| [thinking_timeout_guidance.py](<E:/PythonCode/EasyChat/backend/hermes/agent/thinking_timeout_guidance.py>) | 内嵌 Hermes 上游源码及项目适配内容中的thinking_timeout_guidance 实现（目录与文件名推断） | Thinking-timeout detection and user-facing guidance for reasoning models. / 符号 is_thinking_timeout, build_thinking_timeout_guidance |
| [thread_scoped_output.py](<E:/PythonCode/EasyChat/backend/hermes/agent/thread_scoped_output.py>) | 内嵌 Hermes 上游源码及项目适配内容中的thread_scoped_output 实现（目录与文件名推断） | Thread-scoped stdout/stderr silencing for background worker threads. / 符号 _ThreadRoutingStream, _ensure_installed, thread_scoped_silence |
| [title_generator.py](<E:/PythonCode/EasyChat/backend/hermes/agent/title_generator.py>) | 内嵌 Hermes 上游源码及项目适配内容中的title_generator 实现（目录与文件名推断） | Auto-generate short session titles from the first user/assistant exchange. / 符号 _title_language, _auto_title_enabled, _summarize_user_message, generate_title, _persist_session_title, auto_title_session, _auto_title_session |
| [tool_dispatch_helpers.py](<E:/PythonCode/EasyChat/backend/hermes/agent/tool_dispatch_helpers.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Tool-dispatch helpers — parallelism gating, multimodal envelopes, mutation tracking. / 符号 _is_destructive_command, _is_mcp_tool_parallel_safe, _plan_tool_batch_segments, _should_parallelize_tool_batch, _canonical_path, _extract_parallel_scope_path, _paths_overlap |
| [tool_executor.py](<E:/PythonCode/EasyChat/backend/hermes/agent/tool_executor.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具、执行相关实现（目录与文件名推断） | Tool-call execution — sequential and concurrent dispatch. / 符号 _ensure_file_checkpoint, _budget_for_agent, _parse_tool_arguments, _resolve_concurrent_tool_timeout, _flush_session_db_after_tool_progress, _ra, _is_interpreter_shutdown_submit_error |
| [tool_guardrails.py](<E:/PythonCode/EasyChat/backend/hermes/agent/tool_guardrails.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Pure tool-call loop guardrail primitives. / 符号 ToolCallGuardrailConfig, LoopCapConfig, ToolCallSignature, ToolGuardrailDecision, canonical_tool_args, classify_tool_failure, ToolCallGuardrailController |
| [tool_result_classification.py](<E:/PythonCode/EasyChat/backend/hermes/agent/tool_result_classification.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具、结果相关实现（目录与文件名推断） | Shared helpers for classifying tool result payloads. / 符号 tool_may_have_side_effect, file_mutation_result_landed |
| [trace_upload.py](<E:/PythonCode/EasyChat/backend/hermes/agent/trace_upload.py>) | 内嵌 Hermes 上游源码及项目适配内容中的上传相关实现（目录与文件名推断） | Upload a Hermes session transcript to Hugging Face as an agent trace. / 符号 TraceRedactionError, _now_iso, _redact, _content_to_blocks, _tool_calls_to_blocks, build_trace_jsonl, _resolve_hf_token |
| [trajectory.py](<E:/PythonCode/EasyChat/backend/hermes/agent/trajectory.py>) | 内嵌 Hermes 上游源码及项目适配内容中的trajectory 实现（目录与文件名推断） | Trajectory saving utilities and static helpers. / 符号 convert_scratchpad_to_think, has_incomplete_scratchpad, save_trajectory |
| [transcription_provider.py](<E:/PythonCode/EasyChat/backend/hermes/agent/transcription_provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的供应商相关实现（目录与文件名推断） | Transcription Provider ABC / 符号 TranscriptionProvider |
| [transcription_registry.py](<E:/PythonCode/EasyChat/backend/hermes/agent/transcription_registry.py>) | 内嵌 Hermes 上游源码及项目适配内容中的注册表相关实现（目录与文件名推断） | Transcription Provider Registry / 符号 register_provider, list_providers, get_provider, _reset_for_tests |
| [tts_provider.py](<E:/PythonCode/EasyChat/backend/hermes/agent/tts_provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的供应商相关实现（目录与文件名推断） | Text-to-Speech Provider ABC / 符号 TTSProvider, resolve_output_format |
| [tts_registry.py](<E:/PythonCode/EasyChat/backend/hermes/agent/tts_registry.py>) | 内嵌 Hermes 上游源码及项目适配内容中的注册表相关实现（目录与文件名推断） | TTS Provider Registry / 符号 register_provider, list_providers, get_provider, _reset_for_tests |
| [turn_context.py](<E:/PythonCode/EasyChat/backend/hermes/agent/turn_context.py>) | 内嵌 Hermes 上游源码及项目适配内容中的上下文相关实现（目录与文件名推断） | Per-turn setup for ''run_conversation'' (the turn prologue). / 符号 compose_user_api_content, substitute_api_content, drop_stale_api_content, extract_api_content_sidecar, consume_gateway_turn_context_notes, append_notes_to_multimodal_content, reanchor_current_turn_user_idx |
| [turn_finalizer.py](<E:/PythonCode/EasyChat/backend/hermes/agent/turn_finalizer.py>) | 内嵌 Hermes 上游源码及项目适配内容中的turn_finalizer 实现（目录与文件名推断） | Post-loop turn finalization for ''run_conversation''. / 符号 _is_pure_tool_call_tail, _drop_verification_continuation_scaffolding, finalize_turn |
| [turn_retry_state.py](<E:/PythonCode/EasyChat/backend/hermes/agent/turn_retry_state.py>) | 内嵌 Hermes 上游源码及项目适配内容中的状态相关实现（目录与文件名推断） | Per-attempt recovery bookkeeping for the conversation turn loop. / 符号 TurnRetryState |
| [turn_summary.py](<E:/PythonCode/EasyChat/backend/hermes/agent/turn_summary.py>) | 内嵌 Hermes 上游源码及项目适配内容中的turn_summary 实现（目录与文件名推断） | Per-turn accounting for the interactive CLI. / 符号 TurnTally, _count_diff_lines, _extract_line_deltas, TurnSummaryCollector, format_elapsed, _pluralize, _ordered_verbs |
| [usage_pricing.py](<E:/PythonCode/EasyChat/backend/hermes/agent/usage_pricing.py>) | 内嵌 Hermes 上游源码及项目适配内容中的用量相关实现（目录与文件名推断） | 符号 CanonicalUsage, BillingRoute, PricingEntry, CostResult, _to_decimal, _to_int, resolve_billing_route |
| [verification_evidence.py](<E:/PythonCode/EasyChat/backend/hermes/agent/verification_evidence.py>) | 内嵌 Hermes 上游源码及项目适配内容中的verification_evidence 实现（目录与文件名推断） | Coding verification evidence ledger. / 符号 VerificationEvidence, _utc_now, _retention_cutoff, _db_path, _connect, _transaction, _ensure_schema |
| [verification_stop.py](<E:/PythonCode/EasyChat/backend/hermes/agent/verification_stop.py>) | 内嵌 Hermes 上游源码及项目适配内容中的verification_stop 实现（目录与文件名推断） | Turn-end verification guard for coding edits. / 符号 _is_non_code_path, _filter_verifiable_paths, _session_is_messaging_surface, verify_on_stop_enabled, _candidate_cwds, _verification_snapshot, _format_changed_paths |
| [verify_hooks.py](<E:/PythonCode/EasyChat/backend/hermes/agent/verify_hooks.py>) | 内嵌 Hermes 上游源码及项目适配内容中的verify_hooks 实现（目录与文件名推断） | Verification-loop helpers for the ''pre_verify'' round-end gate. / 符号 max_verify_nudges, coding_verify_guidance, _agent_cfg |
| [vertex_adapter.py](<E:/PythonCode/EasyChat/backend/hermes/agent/vertex_adapter.py>) | 内嵌 Hermes 上游源码及项目适配内容中的vertex_adapter 实现（目录与文件名推断） | Vertex AI (Google Cloud) adapter for Hermes Agent. / 符号 _vertex_config, _resolve_region, _resolve_project_override, _resolve_credentials_path, _refresh_credentials, get_vertex_credentials, build_vertex_base_url |
| [video_gen_provider.py](<E:/PythonCode/EasyChat/backend/hermes/agent/video_gen_provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的供应商相关实现（目录与文件名推断） | Video Generation Provider ABC / 符号 VideoGenProvider, _videos_cache_dir, save_b64_video, save_bytes_video, save_url_video, success_response, error_response |
| [video_gen_registry.py](<E:/PythonCode/EasyChat/backend/hermes/agent/video_gen_registry.py>) | 内嵌 Hermes 上游源码及项目适配内容中的注册表相关实现（目录与文件名推断） | Video Generation Provider Registry / 符号 register_provider, list_providers, get_provider, get_active_provider, _reset_for_tests |
| [web_search_provider.py](<E:/PythonCode/EasyChat/backend/hermes/agent/web_search_provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的搜索、供应商相关实现（目录与文件名推断） | Web Search Provider ABC / 符号 get_provider_env, WebSearchProvider |
| [web_search_registry.py](<E:/PythonCode/EasyChat/backend/hermes/agent/web_search_registry.py>) | 内嵌 Hermes 上游源码及项目适配内容中的搜索、注册表相关实现（目录与文件名推断） | Web Search Provider Registry / 符号 register_provider, list_providers, get_provider, _read_config_key, _resolve, _disabled_web_plugin_for, get_active_search_provider |

### backend/hermes/agent/lsp/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/agent/lsp/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Language Server Protocol (LSP) integration for Hermes Agent. / 符号 get_service, shutdown_service, _atexit_shutdown |
| [cli.py](<E:/PythonCode/EasyChat/backend/hermes/agent/lsp/cli.py>) | 内嵌 Hermes 上游源码及项目适配内容中的cli 实现（目录与文件名推断） | ''hermes lsp'' CLI subcommand. / 符号 register_subparser, run_lsp_command, _cmd_status, _cmd_list, _cmd_install, _cmd_install_all, _cmd_restart |
| [client.py](<E:/PythonCode/EasyChat/backend/hermes/agent/lsp/client.py>) | 内嵌 Hermes 上游源码及项目适配内容中的client 实现（目录与文件名推断） | Async LSP client over stdin/stdout. / 符号 file_uri, uri_to_path, _end_position, _DocState, LSPClient, _dedupe, _diagnostic_key |
| [eventlog.py](<E:/PythonCode/EasyChat/backend/hermes/agent/lsp/eventlog.py>) | 内嵌 Hermes 上游源码及项目适配内容中的eventlog 实现（目录与文件名推断） | Structured logging with steady-state silence for the LSP layer. / 符号 _short_path, _emit, _announce_once, log_clean, log_disabled, log_active, log_diagnostics |
| [install.py](<E:/PythonCode/EasyChat/backend/hermes/agent/lsp/install.py>) | 内嵌 Hermes 上游源码及项目适配内容中的install 实现（目录与文件名推断） | Auto-installation of LSP server binaries. / 符号 _is_windows, hermes_lsp_bin_dir, _native_binary_candidates, _existing_binary, _get_lock, try_install, _do_install |
| [manager.py](<E:/PythonCode/EasyChat/backend/hermes/agent/lsp/manager.py>) | 内嵌 Hermes 上游源码及项目适配内容中的manager 实现（目录与文件名推断） | Service-level orchestration for LSP clients. / 符号 _BackgroundLoop, LSPService, _diag_key |
| [protocol.py](<E:/PythonCode/EasyChat/backend/hermes/agent/lsp/protocol.py>) | 内嵌 Hermes 上游源码及项目适配内容中的protocol 实现（目录与文件名推断） | Minimal LSP JSON-RPC 2.0 framer over async streams. / 符号 LSPProtocolError, LSPRequestError, encode_message, read_message, make_request, make_notification, make_response |
| [range_shift.py](<E:/PythonCode/EasyChat/backend/hermes/agent/lsp/range_shift.py>) | 内嵌 Hermes 上游源码及项目适配内容中的range_shift 实现（目录与文件名推断） | Diff-aware line-shift map for cross-edit LSP delta filtering. / 符号 build_line_shift, shift_diagnostic_range, shift_baseline |
| [reporter.py](<E:/PythonCode/EasyChat/backend/hermes/agent/lsp/reporter.py>) | 内嵌 Hermes 上游源码及项目适配内容中的reporter 实现（目录与文件名推断） | Format LSP diagnostics for inclusion in tool output. / 符号 _sanitize_field, format_diagnostic, report_for_file, truncate |
| [servers.py](<E:/PythonCode/EasyChat/backend/hermes/agent/lsp/servers.py>) | 内嵌 Hermes 上游源码及项目适配内容中的servers 实现（目录与文件名推断） | Server registry — per-language LSP server definitions. / 符号 SpawnSpec, ServerDef, ServerContext, _file_ext_or_basename, _which, _root_or_workspace, _spawn_pyright |
| [workspace.py](<E:/PythonCode/EasyChat/backend/hermes/agent/lsp/workspace.py>) | 内嵌 Hermes 上游源码及项目适配内容中的workspace 实现（目录与文件名推断） | Workspace and project-root resolution for LSP. / 符号 normalize_path, find_git_worktree, is_inside_workspace, nearest_root, resolve_workspace_for_file, clear_cache |

### backend/hermes/agent/pet/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/agent/pet/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Petdex pet engine — shared core for the CLI, TUI, and desktop surfaces. |
| [constants.py](<E:/PythonCode/EasyChat/backend/hermes/agent/pet/constants.py>) | 内嵌 Hermes 上游源码及项目适配内容中的constants 实现（目录与文件名推断） | Pet sprite geometry + animation-state taxonomy. / 符号 clamp_scale, cols_for_scale, resolve_cols, PetState, state_aliases_for, state_rows_for_grid, state_row_index |
| [manifest.py](<E:/PythonCode/EasyChat/backend/hermes/agent/pet/manifest.py>) | 内嵌 Hermes 上游源码及项目适配内容中的manifest 实现（目录与文件名推断） | Fetch the public petdex manifest. / 符号 clear_cache, _cache_is_warm, prefetch, ManifestEntry, ManifestError, fetch_manifest, find_entry |
| [render.py](<E:/PythonCode/EasyChat/backend/hermes/agent/pet/render.py>) | 内嵌 Hermes 上游源码及项目适配内容中的render 实现（目录与文件名推断） | Decode a pet spritesheet and encode frames for a terminal. / 符号 detect_terminal_graphics, resolve_mode, _open_sheet, _frame_is_blank, _raw_frames, _frames_for, state_frame_counts |
| [state.py](<E:/PythonCode/EasyChat/backend/hermes/agent/pet/state.py>) | 内嵌 Hermes 上游源码及项目适配内容中的状态相关实现（目录与文件名推断） | Map agent activity → a :class:'PetState'. / 符号 todos_all_done, derive_pet_state |
| [store.py](<E:/PythonCode/EasyChat/backend/hermes/agent/pet/store.py>) | 内嵌 Hermes 上游源码及项目适配内容中的store 实现（目录与文件名推断） | On-disk pet store — install / list / resolve pets. / 符号 PetStoreError, InstalledPet, pets_dir, _read_pet_json, _resolve_spritesheet, _safe_slug, load_pet |

### backend/hermes/agent/pet/generate/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/agent/pet/generate/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Pet generation — base-draft → hatch pipeline. |
| [atlas.py](<E:/PythonCode/EasyChat/backend/hermes/agent/pet/generate/atlas.py>) | 内嵌 Hermes 上游源码及项目适配内容中的atlas 实现（目录与文件名推断） | Deterministic spritesheet assembly — generated row strips → Hermes atlas. / 符号 _color_distance, _has_transparency, _dominant_corner_color, _near_key_mask, _defringe, remove_background, _repair_internal_alpha_holes |
| [imagegen.py](<E:/PythonCode/EasyChat/backend/hermes/agent/pet/generate/imagegen.py>) | 内嵌 Hermes 上游源码及项目适配内容中的imagegen 实现（目录与文件名推断） | Thin image-generation layer for pet sprites. / 符号 _forced_provider_from_env, GenerationError, SpriteProvider, _discover, resolve_provider, list_sprite_providers, _save_local |
| [orchestrate.py](<E:/PythonCode/EasyChat/backend/hermes/agent/pet/generate/orchestrate.py>) | 内嵌 Hermes 上游源码及项目适配内容中的orchestrate 实现（目录与文件名推断） | Pet generation orchestration — the base-draft → hatch flow. / 符号 HatchResult, _harden_transparency, generate_base_drafts, _drafts_failed_reason, _humanize_image_error, hatch_pet |
| [prompts.py](<E:/PythonCode/EasyChat/backend/hermes/agent/pet/generate/prompts.py>) | 内嵌 Hermes 上游源码及项目适配内容中的prompts 实现（目录与文件名推断） | Prompt builders for pet generation. / 符号 style_hint, _spacing_spec, build_base_prompt, build_row_prompt |

### backend/hermes/agent/proxy_sources/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/agent/proxy_sources/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Egress proxy integrations. |
| [iron_proxy.py](<E:/PythonCode/EasyChat/backend/hermes/agent/proxy_sources/iron_proxy.py>) | 内嵌 Hermes 上游源码及项目适配内容中的iron_proxy 实现（目录与文件名推断） | iron-proxy ('ironsh/iron-proxy') integration for credential-injecting egress control. / 符号 ProxyStatus, TokenMapping, _hermes_bin_dir, _proxy_state_dir_ro, _proxy_state_dir, _platform_binary_name, _platform_asset_name |

### backend/hermes/agent/secret_sources/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/agent/secret_sources/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | External secret source integrations. |
| [_cache.py](<E:/PythonCode/EasyChat/backend/hermes/agent/secret_sources/_cache.py>) | 内嵌 Hermes 上游源码及项目适配内容中的缓存相关实现（目录与文件名推断） | Shared substrate for external secret-source backends. / 符号 CachedFetch, resolve_cache_home, DiskCache |
| [base.py](<E:/PythonCode/EasyChat/backend/hermes/agent/secret_sources/base.py>) | 内嵌 Hermes 上游源码及项目适配内容中的base 实现（目录与文件名推断） | Secret-source contract: the ABC every secret backend implements. / 符号 ErrorKind, FetchResult, SecretSource, is_valid_env_name, scrub_ansi, run_secret_cli |
| [bitwarden.py](<E:/PythonCode/EasyChat/backend/hermes/agent/secret_sources/bitwarden.py>) | 内嵌 Hermes 上游源码及项目适配内容中的bitwarden 实现（目录与文件名推断） | Bitwarden Secrets Manager ('bws' CLI) integration. / 符号 _cache_key_str, _disk_cache_path, _encrypted_disk_cache_path, _hermes_bin_dir, find_bws, _platform_binary_name, _platform_asset_name |
| [command.py](<E:/PythonCode/EasyChat/backend/hermes/agent/secret_sources/command.py>) | 内嵌 Hermes 上游源码及项目适配内容中的command 实现（目录与文件名推断） | ''command'' secret source — resolve secrets via a user-configured helper. / 符号 _is_windows, unquote_dotenv_value, parse_secret_output, _run_helper, _parse_dotenv_map, get_command_secret, list_command_secrets |
| [onepassword.py](<E:/PythonCode/EasyChat/backend/hermes/agent/secret_sources/onepassword.py>) | 内嵌 Hermes 上游源码及项目适配内容中的onepassword 实现（目录与文件名推断） | 1Password ('op' CLI) secret source. / 符号 _disk_key_str, _disk_cache_path, _validate_references, _auth_fingerprint, _refs_fingerprint, find_op, _scrub |
| [registry.py](<E:/PythonCode/EasyChat/backend/hermes/agent/secret_sources/registry.py>) | 内嵌 Hermes 上游源码及项目适配内容中的注册表相关实现（目录与文件名推断） | Secret-source registry + apply orchestrator. / 符号 AppliedVar, SourceReport, ApplyReport, register_source, get_source, list_sources, _ensure_builtin_sources |

### backend/hermes/agent/transports/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/agent/transports/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Transport layer types and registry for provider response normalization. / 符号 register_transport, get_transport, _discover_transports |
| [anthropic.py](<E:/PythonCode/EasyChat/backend/hermes/agent/transports/anthropic.py>) | 内嵌 Hermes 上游源码及项目适配内容中的anthropic 实现（目录与文件名推断） | Anthropic Messages API transport. / 符号 AnthropicTransport |
| [base.py](<E:/PythonCode/EasyChat/backend/hermes/agent/transports/base.py>) | 内嵌 Hermes 上游源码及项目适配内容中的base 实现（目录与文件名推断） | Abstract base for provider transports. / 符号 ProviderTransport |
| [bedrock.py](<E:/PythonCode/EasyChat/backend/hermes/agent/transports/bedrock.py>) | 内嵌 Hermes 上游源码及项目适配内容中的bedrock 实现（目录与文件名推断） | AWS Bedrock Converse API transport. / 符号 BedrockTransport |
| [chat_completions.py](<E:/PythonCode/EasyChat/backend/hermes/agent/transports/chat_completions.py>) | 内嵌 Hermes 上游源码及项目适配内容中的聊天相关实现（目录与文件名推断） | OpenAI Chat Completions transport. / 符号 _reasoning_config_for_model, _build_gemini_thinking_config, _snake_case_gemini_thinking_config, _is_gemini_openai_compat_base_url, _model_consumes_thought_signature, ChatCompletionsTransport |
| [codex.py](<E:/PythonCode/EasyChat/backend/hermes/agent/transports/codex.py>) | 内嵌 Hermes 上游源码及项目适配内容中的codex 实现（目录与文件名推断） | OpenAI Responses API (Codex) transport. / 符号 _bounded_prompt_cache_key, _default_prompt_cache_retention_for_request, _content_cache_key, ResponsesApiTransport |
| [codex_app_server.py](<E:/PythonCode/EasyChat/backend/hermes/agent/transports/codex_app_server.py>) | 内嵌 Hermes 上游源码及项目适配内容中的codex_app_server 实现（目录与文件名推断） | Codex app-server JSON-RPC client. / 符号 CodexAppServerError, _Pending, CodexAppServerClient, parse_codex_version, check_codex_binary |
| [codex_app_server_session.py](<E:/PythonCode/EasyChat/backend/hermes/agent/transports/codex_app_server_session.py>) | 内嵌 Hermes 上游源码及项目适配内容中的会话相关实现（目录与文件名推断） | Session adapter for codex app-server runtime. / 符号 TurnResult, _notification_scope_ids, _notification_belongs_to_turn, _coerce_turn_input_text, _classify_oauth_failure, _ServerRequestRouting, CodexAppServerSession |
| [codex_event_projector.py](<E:/PythonCode/EasyChat/backend/hermes/agent/transports/codex_event_projector.py>) | 内嵌 Hermes 上游源码及项目适配内容中的codex_event_projector 实现（目录与文件名推断） | Projects codex app-server events into Hermes' messages list. / 符号 _deterministic_call_id, _format_tool_args, ProjectionResult, CodexEventProjector |
| [hermes_tools_mcp_server.py](<E:/PythonCode/EasyChat/backend/hermes/agent/transports/hermes_tools_mcp_server.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具、MCP相关实现（目录与文件名推断） | Hermes-tools-as-MCP server for the codex_app_server runtime. / 符号 _signature_from_schema, _build_server, main |
| [types.py](<E:/PythonCode/EasyChat/backend/hermes/agent/transports/types.py>) | 内嵌 Hermes 上游源码及项目适配内容中的types 实现（目录与文件名推断） | Shared types for normalized provider responses. / 符号 ToolCall, Usage, NormalizedResponse, build_tool_call, map_finish_reason |

### backend/hermes/cron/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/cron/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Cron job scheduling system for Hermes Agent. |
| [blueprint_catalog.py](<E:/PythonCode/EasyChat/backend/hermes/cron/blueprint_catalog.py>) | 内嵌 Hermes 上游源码及项目适配内容中的blueprint_catalog 实现（目录与文件名推断） | Automation Blueprints — parameterized automation blueprints with typed slots. / 符号 BlueprintFillError, BlueprintSlot, AutomationBlueprint, get_blueprint, blueprint_form_schema, blueprint_slash_command, blueprint_deeplink |
| [executions.py](<E:/PythonCode/EasyChat/backend/hermes/cron/executions.py>) | 内嵌 Hermes 上游源码及项目适配内容中的executions 实现（目录与文件名推断） | Profile-local durable audit ledger for cron execution attempts. / 符号 _connect, _initialize_schema, _transaction, _record, _process_start_time, _owner_is_live, _prune_unlocked |
| [jobs.py](<E:/PythonCode/EasyChat/backend/hermes/cron/jobs.py>) | 内嵌 Hermes 上游源码及项目适配内容中的jobs 实现（目录与文件名推断） | Cron job storage and management. / 符号 _CronStorePaths, _current_cron_store, use_cron_store, get_cron_output_dir, _oneshot_run_claim_ttl_seconds, _job_running_in_this_process, _jobs_lock_file |
| [lifecycle_guard.py](<E:/PythonCode/EasyChat/backend/hermes/cron/lifecycle_guard.py>) | 内嵌 Hermes 上游源码及项目适配内容中的lifecycle_guard 实现（目录与文件名推断） | Gateway lifecycle guard for cron job creation (#30719). / 符号 GatewayLifecycleBlocked, contains_gateway_lifecycle_command, _resolve_script_path, _read_script_for_scanning, check_gateway_lifecycle |
| [scheduler.py](<E:/PythonCode/EasyChat/backend/hermes/cron/scheduler.py>) | 内嵌 Hermes 上游源码及项目适配内容中的scheduler 实现（目录与文件名推断） | Cron job scheduler - executes due jobs. / 符号 _set_cron_session_title, _summarize_cron_failure_for_delivery, CronPromptInjectionBlocked, _resolve_cron_disabled_toolsets, _merge_mcp_into_per_job_toolsets, _resolve_cron_enabled_toolsets, _is_cron_silence_response |
| [scheduler_provider.py](<E:/PythonCode/EasyChat/backend/hermes/cron/scheduler_provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的供应商相关实现（目录与文件名推断） | CronScheduler provider interface (Axis B — the trigger). / 符号 CronScheduler, resolve_cron_scheduler, InProcessCronScheduler |
| [suggestion_catalog.py](<E:/PythonCode/EasyChat/backend/hermes/cron/suggestion_catalog.py>) | 内嵌 Hermes 上游源码及项目适配内容中的suggestion_catalog 实现（目录与文件名推断） | Curated catalog of starter cron-job suggestions. / 符号 classify_items_script_path, CatalogEntry, seed_catalog_suggestions |
| [suggestions.py](<E:/PythonCode/EasyChat/backend/hermes/cron/suggestions.py>) | 内嵌 Hermes 上游源码及项目适配内容中的suggestions 实现（目录与文件名推断） | Suggested cron jobs — proposed automations the user accepts with one tap. / 符号 _secure_file, _ensure_dir, _load_raw, _save_raw, load_suggestions, list_pending, add_suggestion |

### backend/hermes/cron/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/cron/scripts/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Scripts shipped with the cron subsystem (runnable via ''python3 -m cron.scripts.<name>''). |
| [classify_items.py](<E:/PythonCode/EasyChat/backend/hermes/cron/scripts/classify_items.py>) | 内嵌 Hermes 上游源码及项目适配内容中的classify_items 实现（目录与文件名推断） | Classify candidate items by urgency/importance and emit only the urgent ones. / 符号 _eprint, _load_items, _item_id, _build_prompt, _parse_scores, main |

### backend/hermes/gateway/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Hermes Gateway - Multi-platform messaging integration. |
| [authz_mixin.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/authz_mixin.py>) | 内嵌 Hermes 上游源码及项目适配内容中的authz_mixin 实现（目录与文件名推断） | User-authorization methods for ''GatewayRunner''. / 符号 _auth_env, _coerce_allow_set, GatewayAuthorizationMixin |
| [cgroup_cleanup.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/cgroup_cleanup.py>) | 内嵌 Hermes 上游源码及项目适配内容中的cgroup_cleanup 实现（目录与文件名推断） | SIGKILL any process left in this systemd unit's cgroup. / 符号 _own_cgroup_path, _read_cgroup_pids, reap_cgroup, main |
| [channel_directory.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/channel_directory.py>) | 内嵌 Hermes 上游源码及项目适配内容中的channel_directory 实现（目录与文件名推断） | Channel directory -- cached map of reachable channels/contacts per platform. / 符号 _load_channel_aliases, _apply_channel_aliases, _normalize_channel_query, _channel_target_name, _session_entry_id, _session_entry_name, _warn_slack_directory |
| [code_skew.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/code_skew.py>) | 内嵌 Hermes 上游源码及项目适配内容中的code_skew 实现（目录与文件名推断） | Detect when the gateway is running stale code after a hot ''git pull''. / 符号 _fingerprint, record_boot_fingerprint, _short, detect_code_skew |
| [config.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/config.py>) | 内嵌 Hermes 上游源码及项目适配内容中的配置相关实现（目录与文件名推断） | Gateway configuration management. / 符号 _coerce_bool, _env_multiplex_profiles_override, _normalize_transport_token, _coerce_float, _coerce_int, _coerce_optional_positive_int, coerce_systemd_watchdog_seconds |
| [cwd_placeholder.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/cwd_placeholder.py>) | 内嵌 Hermes 上游源码及项目适配内容中的cwd_placeholder 实现（目录与文件名推断） | Resolve gateway ''terminal.cwd'' placeholder values to ''TERMINAL_CWD''. / 符号 _truthy_env, resolve_placeholder_terminal_cwd |
| [dead_targets.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/dead_targets.py>) | 内嵌 Hermes 上游源码及项目适配内容中的dead_targets 实现（目录与文件名推断） | Persistent registry of delivery targets that are confirmed unreachable. / 符号 _normalize, DeadTargetRegistry |
| [delivery.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/delivery.py>) | 内嵌 Hermes 上游源码及项目适配内容中的delivery 实现（目录与文件名推断） | Delivery routing for cron job outputs and agent responses. / 符号 _is_silence_narration, DeliveryTransport, resolve_delivery_transport, looks_like_telegram_private_chat_id, _looks_like_int, _send_result_failed, _send_result_error |
| [delivery_ledger.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/delivery_ledger.py>) | 内嵌 Hermes 上游源码及项目适配内容中的delivery_ledger 实现（目录与文件名推断） | Durable delivery-obligation ledger for gateway final responses. / 符号 _db_path, _connect, _initialize_schema, _transaction, _owner_stamp, _owner_alive, compute_obligation_id |
| [display_config.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/display_config.py>) | 内嵌 Hermes 上游源码及项目适配内容中的配置相关实现（目录与文件名推断） | Per-platform display/verbosity configuration resolver. / 符号 resolve_display_setting, _normalise |
| [drain_control.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/drain_control.py>) | 内嵌 Hermes 上游源码及项目适配内容中的drain_control 实现（目录与文件名推断） | External drain-control marker contract (dashboard → gateway). / 符号 current_instantiation_epoch, drain_request_path, write_drain_request, clear_drain_request, _marker_epoch_is_stale, drain_requested, drain_notification_suppressed |
| [hooks.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/hooks.py>) | 内嵌 Hermes 上游源码及项目适配内容中的hooks 实现（目录与文件名推断） | Event Hook System / 符号 HookRegistry |
| [lifecycle_ledger.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/lifecycle_ledger.py>) | 内嵌 Hermes 上游源码及项目适配内容中的lifecycle_ledger 实现（目录与文件名推断） | Gateway lifecycle ledger — durable termination-reason evidence (NS-608). / 符号 _process_hermes_home, get_lifecycle_sentinel_path, sample_memory, _read_json, _write_sentinel, _append_exit_diag, _pid_alive_with_start_time |
| [memory_monitor.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/memory_monitor.py>) | 内嵌 Hermes 上游源码及项目适配内容中的记忆相关实现（目录与文件名推断） | Periodic process memory usage logging for the gateway. / 符号 _get_rss_mb, log_memory_usage, _monitor_loop, start_memory_monitoring, stop_memory_monitoring, is_running |
| [message_timestamps.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/message_timestamps.py>) | 内嵌 Hermes 上游源码及项目适配内容中的message_timestamps 实现（目录与文件名推断） | Helpers for rendering gateway message timestamps exactly once. / 符号 coerce_message_timestamp, format_message_timestamp, strip_leading_message_timestamps, render_user_content_with_timestamp, _parse_timestamp_prefix, _parse_timestamp_match |
| [mirror.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/mirror.py>) | 内嵌 Hermes 上游源码及项目适配内容中的mirror 实现（目录与文件名推断） | Session mirroring for cross-platform message delivery. / 符号 mirror_to_session, _find_session_id, _append_to_sqlite |
| [pairing.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/pairing.py>) | 内嵌 Hermes 上游源码及项目适配内容中的pairing 实现（目录与文件名推断） | DM Pairing System / 符号 _allowlist_env_for_platform, _split_allowlist, _sync_allowlist_add, _sync_allowlist_remove, _load_json_file, _merge_pairing_dir, _migrate_split_pairing_dirs |
| [platform_registry.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platform_registry.py>) | 内嵌 Hermes 上游源码及项目适配内容中的注册表相关实现（目录与文件名推断） | Platform Adapter Registry / 符号 PlatformEntry, PlatformRegistry |
| [profile_routing.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/profile_routing.py>) | 内嵌 Hermes 上游源码及项目适配内容中的profile_routing 实现（目录与文件名推断） | Profile-based routing for the gateway with hierarchical matching. / 符号 ProfileRoute, parse_profile_routes, match_profile_route |
| [readiness.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/readiness.py>) | 内嵌 Hermes 上游源码及项目适配内容中的readiness 实现（目录与文件名推断） | Bounded, non-destructive readiness probes for authenticated health surfaces. / 符号 _check, _probe_state_db, _probe_config, _probe_disk, _probe_gateway, collect_runtime_readiness |
| [response_filters.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/response_filters.py>) | 内嵌 Hermes 上游源码及项目适配内容中的response_filters 实现（目录与文件名推断） | Gateway response filtering helpers. / 符号 _canonical_silence_candidate, _strip_edge_silence_punctuation, _canonical_silence_candidates, is_intentional_silence_response, is_autonomous_silence_response, is_intentional_silence_agent_result, is_partial_silence_marker |
| [restart.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/restart.py>) | 内嵌 Hermes 上游源码及项目适配内容中的restart 实现（目录与文件名推断） | Shared gateway restart constants and supervisor detection helpers. / 符号 is_gateway_supervisor_process, parse_restart_drain_timeout |
| [restart_loop_guard.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/restart_loop_guard.py>) | 内嵌 Hermes 上游源码及项目适配内容中的restart_loop_guard 实现（目录与文件名推断） | Auto-resume restart-loop breaker (#30719, defense-3). / 符号 _state_path, _load_boots, _save_boots, record_restart_interrupted_boot, is_restart_loop_tripped, clear, check_and_record |
| [rich_sent_store.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/rich_sent_store.py>) | 内嵌 Hermes 上游源码及项目适配内容中的rich_sent_store 实现（目录与文件名推断） | Local index of text we've sent via ''sendRichMessage'' (Bot API 10.1). / 符号 _store_path, _key, record, lookup |
| [run.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/run.py>) | 内嵌 Hermes 上游源码及项目适配内容中的run 实现（目录与文件名推断） | Gateway runner - entry point for messaging platform integrations. / 符号 _status_template_to_regex, _gateway_compression_progress_notices_enabled, _gateway_surface_passes_raw_text, _ensure_windows_gateway_venv_imports, _gateway_platform_value, _non_conversational_metadata, _seed_hygiene_system_prompt |
| [runtime_footer.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/runtime_footer.py>) | 内嵌 Hermes 上游源码及项目适配内容中的执行运行时相关实现（目录与文件名推断） | Gateway runtime-metadata footer. / 符号 _home_relative_cwd, _model_short, resolve_footer_config, format_runtime_footer, build_footer_line |
| [scale_to_zero.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/scale_to_zero.py>) | 内嵌 Hermes 上游源码及项目适配内容中的scale_to_zero 实现（目录与文件名推断） | Scale-to-zero idle detection + dormant-quiesce for the gateway (Phase 0). / 符号 scale_to_zero_enabled, parse_idle_timeout_seconds, messaging_is_relay_only_or_absent, _platform_name, should_arm, is_idle |
| [session.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/session.py>) | 内嵌 Hermes 上游源码及项目适配内容中的会话相关实现（目录与文件名推断） | Session management for the gateway. / 符号 _now, auto_continue_freshness_window, _hash_id, _hash_sender_id, _hash_chat_id, _is_path_unsafe, _is_session_key_unsafe |
| [session_context.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/session_context.py>) | 内嵌 Hermes 上游源码及项目适配内容中的会话、上下文相关实现（目录与文件名推断） | Session-scoped context variables for the Hermes gateway. / 符号 session_context_engaged, set_current_session_id, set_session_vars, clear_session_vars, reset_session_vars, get_session_env, declare_stateless_channel |
| [shutdown_flush.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/shutdown_flush.py>) | 内嵌 Hermes 上游源码及项目适配内容中的shutdown_flush 实现（目录与文件名推断） | Flush pending messages and agent transcripts to disk before shutdown to prevent data loss. / 符号 _get_flush_dir, _fsync_directory, _write_payload, flush_pending_to_file, _serialise_value, recover_pending_to_db, flush_agent_history_to_file |
| [shutdown_forensics.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/shutdown_forensics.py>) | 内嵌 Hermes 上游源码及项目适配内容中的shutdown_forensics 实现（目录与文件名推断） | Shutdown forensics — capture context when the gateway receives SIGTERM/SIGINT. / 符号 _signal_name, _read_proc_field, _read_proc_cmdline, _proc_summary, snapshot_shutdown_context, spawn_async_diagnostic, format_context_for_log |
| [shutdown_watchdog.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/shutdown_watchdog.py>) | 内嵌 Hermes 上游源码及项目适配内容中的shutdown_watchdog 实现（目录与文件名推断） | Out-of-loop shutdown and event-loop liveness backstops (#66892, #69089). / 符号 _LoopFloorTimerHandle, _LoopLivenessWatchdogHandle, _arm_loop_floor_timer, start_loop_liveness_watchdog, _process_hermes_home, get_loop_heartbeat_path, get_shutdown_watchdog_dump_path |
| [slash_access.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/slash_access.py>) | 内嵌 Hermes 上游源码及项目适配内容中的slash_access 实现（目录与文件名推断） | Per-platform slash command access control. / 符号 SlashAccessPolicy, _coerce_id_list, _coerce_command_list, _scope_for_chat_type, _platform_extra, _keys_for_scope, policy_from_extra |
| [slash_commands.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/slash_commands.py>) | 内嵌 Hermes 上游源码及项目适配内容中的slash_commands 实现（目录与文件名推断） | Gateway slash-command handlers for GatewayRunner. / 符号 _clean_str, _int_value, _model_switch_skew_guard, GatewaySlashCommandsMixin |
| [status.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/status.py>) | 内嵌 Hermes 上游源码及项目适配内容中的status 实现（目录与文件名推断） | Gateway runtime status helpers. / 符号 StormInfo, _get_starts_log_path, record_start_and_check_storm, _get_process_hermes_home, _canonical_hermes_home, _same_hermes_home, _get_pid_path |
| [status_phrases.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/status_phrases.py>) | 内嵌 Hermes 上游源码及项目适配内容中的status_phrases 实现（目录与文件名推断） | Human-friendly generic gateway status phrases. / 符号 _clean_phrase_list, _merge_phrase_mapping, _merge_phrase_file, _relative_path_under, _iter_phrase_files, _merge_phrase_paths, _load_builtin_catalog |
| [sticker_cache.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/sticker_cache.py>) | 内嵌 Hermes 上游源码及项目适配内容中的缓存相关实现（目录与文件名推断） | Sticker description cache for Telegram. / 符号 _load_cache, _save_cache, get_cached_description, cache_sticker_description, build_sticker_injection, build_animated_sticker_injection |
| [stream_consumer.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/stream_consumer.py>) | 内嵌 Hermes 上游源码及项目适配内容中的流式事件相关实现（目录与文件名推断） | Gateway streaming consumer — bridges sync agent callbacks to async platform delivery. / 符号 escape_code_fences_for_display, ensure_closed_code_fences, StreamConsumerConfig, GatewayStreamConsumer |
| [stream_dispatch.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/stream_dispatch.py>) | 内嵌 Hermes 上游源码及项目适配内容中的流式事件相关实现（目录与文件名推断） | Adapter-driven dispatch of structured stream events to a delivery sink. / 符号 GatewayEventDispatcher |
| [stream_events.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/stream_events.py>) | 内嵌 Hermes 上游源码及项目适配内容中的流式事件相关实现（目录与文件名推断） | Structured streaming events — the agent→gateway delivery contract. / 符号 MessageChunk, MessageStop, Commentary, ToolCallChunk, ToolCallFinished, LongToolHint, GatewayNotice |
| [streaming_tts_consumer.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/streaming_tts_consumer.py>) | 内嵌 Hermes 上游源码及项目适配内容中的streaming_tts_consumer 实现（目录与文件名推断） | Gateway streaming-TTS consumer — LLM deltas to adapter PCM audio sink. / 符号 StreamingTTSConsumer |
| [systemd_notify.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/systemd_notify.py>) | 内嵌 Hermes 上游源码及项目适配内容中的systemd_notify 实现（目录与文件名推断） | Minimal, optional systemd ''sd_notify'' support for the gateway. / 符号 _notify_address, notify, watchdog_interval_seconds, SystemdWatchdog |
| [turn_lease.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/turn_lease.py>) | 内嵌 Hermes 上游源码及项目适配内容中的turn_lease 实现（目录与文件名推断） | Per-session turn lease — serializes the [load history → run → flush] region. / 符号 TurnLeaseToken, _SessionLease, SessionTurnLeaseRegistry |
| [wake.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/wake.py>) | 内嵌 Hermes 上游源码及项目适配内容中的wake 实现（目录与文件名推断） | Wake an existing agent session from a background completion event. / 符号 adapter_supports_push, deliver_wake, _self_post_chat_completion |
| [whatsapp_identity.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/whatsapp_identity.py>) | 内嵌 Hermes 上游源码及项目适配内容中的whatsapp_identity 实现（目录与文件名推断） | Shared helpers for canonicalising WhatsApp sender identity. / 符号 normalize_whatsapp_identifier, to_whatsapp_jid, expand_whatsapp_aliases, canonical_whatsapp_identifier |

### backend/hermes/gateway/assets/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [status_phrases.yaml](<E:/PythonCode/EasyChat/backend/hermes/gateway/assets/status_phrases.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 status_phrases（目录与文件名推断） | 按目录和文件类型定位 |
| [telegram-botfather-threads-settings.jpg](<E:/PythonCode/EasyChat/backend/hermes/gateway/assets/telegram-botfather-threads-settings.jpg>) | 内嵌 Hermes 上游源码及项目适配内容使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |

### backend/hermes/gateway/builtin_hooks/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/builtin_hooks/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Built-in gateway hooks that are always registered. |

### backend/hermes/gateway/platforms/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [ADDING_A_PLATFORM.md](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/ADDING_A_PLATFORM.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 ADDING_A_PLATFORM（目录与文件名推断） | Adding a New Messaging Platform |
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Platform adapters for messaging integrations. / 符号 __getattr__, __dir__ |
| [_http_client_limits.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/_http_client_limits.py>) | 内嵌 Hermes 上游源码及项目适配内容中的_http_client_limits 实现（目录与文件名推断） | Shared HTTP client factory for long-lived platform adapters. / 符号 platform_httpx_limits |
| [api_server.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/api_server.py>) | 内嵌 Hermes 上游源码及项目适配内容中的api_server 实现（目录与文件名推断） | OpenAI-compatible API server platform adapter. / 符号 _approval_event_choices, _hermes_version, _coerce_port, _coerce_request_bool, _clean_request_string, _request_reasoning_config, _request_service_tier |
| [base.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/base.py>) | 内嵌 Hermes 上游源码及项目适配内容中的base 实现（目录与文件名推断） | Base platform adapter interface. / 符号 _platform_name, _float_env, _thread_metadata_for_source, _mark_notify_metadata, _reply_anchor_for_event, should_send_media_as_audio, build_auto_tts_output_path |
| [bluebubbles.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/bluebubbles.py>) | 内嵌 Hermes 上游源码及项目适配内容中的bluebubbles 实现（目录与文件名推断） | BlueBubbles iMessage platform adapter. / 符号 _redact, check_bluebubbles_requirements, _normalize_server_url, BlueBubblesAdapter |
| [helpers.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/helpers.py>) | 内嵌 Hermes 上游源码及项目适配内容中的helpers 实现（目录与文件名推断） | Shared helper classes for gateway platform adapters. / 符号 MessageDeduplicator, TextBatchAggregator, strip_markdown, ThreadParticipationTracker, redact_phone, is_table_row, split_markdown_table_row |
| [msgraph_webhook.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/msgraph_webhook.py>) | 内嵌 Hermes 上游源码及项目适配内容中的msgraph_webhook 实现（目录与文件名推断） | Microsoft Graph webhook adapter for change-notification ingress. / 符号 check_msgraph_webhook_requirements, MSGraphWebhookAdapter |
| [signal.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/signal.py>) | 内嵌 Hermes 上游源码及项目适配内容中的signal 实现（目录与文件名推断） | Signal messenger platform adapter. / 符号 _parse_comma_list, _guess_extension, _is_image_ext, _is_audio_ext, _ext_to_mime, _remux_aac_to_m4a, _render_mentions |
| [signal_format.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/signal_format.py>) | 内嵌 Hermes 上游源码及项目适配内容中的signal_format 实现（目录与文件名推断） | Shared Signal formatting helpers. / 符号 markdown_to_signal |
| [signal_rate_limit.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/signal_rate_limit.py>) | 内嵌 Hermes 上游源码及项目适配内容中的signal_rate_limit 实现（目录与文件名推断） | Signal attachment rate-limit scheduler. / 符号 SignalRateLimitError, SignalSchedulerError, _extract_retry_after_seconds, _is_signal_rate_limit_error, _format_wait, _signal_send_timeout, SignalAttachmentScheduler |
| [webhook.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/webhook.py>) | 内嵌 Hermes 上游源码及项目适配内容中的webhook 实现（目录与文件名推断） | Generic webhook platform adapter. / 符号 _is_webhook_silence_response, _is_loopback_host, _hmac_str_equal, check_webhook_requirements, WebhookAdapter |
| [webhook_filters.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/webhook_filters.py>) | 内嵌 Hermes 上游源码及项目适配内容中的webhook_filters 实现（目录与文件名推断） | Route-local filters and script transforms for the webhook adapter. / 符号 _stringify_filter_value, _resolve_profile_path, _resolve_script_path, _load_filter_file_values, WebhookRouteProcessor |
| [weixin.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/weixin.py>) | 内嵌 Hermes 上游源码及项目适配内容中的weixin 实现（目录与文件名推断） | Weixin platform adapter. / 符号 _is_stale_session_ret, _make_ssl_connector, check_weixin_requirements, _safe_id, _json_dumps, _pkcs7_pad, _aes128_ecb_encrypt |
| [whatsapp_cloud.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/whatsapp_cloud.py>) | 内嵌 Hermes 上游源码及项目适配内容中的whatsapp_cloud 实现（目录与文件名推断） | WhatsApp Cloud API adapter — official Meta WhatsApp Business Platform. / 符号 _read_limited_request_body, _ext_for_mime, check_whatsapp_cloud_requirements, WhatsAppCloudAdapter |
| [whatsapp_common.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/whatsapp_common.py>) | 内嵌 Hermes 上游源码及项目适配内容中的whatsapp_common 实现（目录与文件名推断） | Transport-agnostic WhatsApp behavior shared by the Baileys bridge adapter / 符号 WhatsAppBehaviorMixin, resolve_whatsapp_bridge_dir |
| [yuanbao.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/yuanbao.py>) | 内嵌 Hermes 上游源码及项目适配内容中的yuanbao 实现（目录与文件名推断） | Yuanbao platform adapter. / 符号 MarkdownProcessor, SignManager, InboundContext, InboundMiddleware, InboundPipeline, DecodeMiddleware, ExtractFieldsMiddleware |
| [yuanbao_media.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/yuanbao_media.py>) | 内嵌 Hermes 上游源码及项目适配内容中的yuanbao_media 实现（目录与文件名推断） | yuanbao_media.py — 元宝平台媒体处理模块 / 符号 guess_mime_type, is_image, get_image_format, md5_hex, generate_file_id, parse_image_size, _parse_png_size |
| [yuanbao_proto.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/yuanbao_proto.py>) | 内嵌 Hermes 上游源码及项目适配内容中的yuanbao_proto 实现（目录与文件名推断） | yuanbao_proto.py - Yuanbao WebSocket 协议编解码（纯 Python 实现） / 符号 _dbg, next_seq_no, _encode_varint, _decode_varint, _encode_field, _encode_string, _encode_bytes |
| [yuanbao_sticker.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/yuanbao_sticker.py>) | 内嵌 Hermes 上游源码及项目适配内容中的yuanbao_sticker 实现（目录与文件名推断） | Yuanbao sticker (TIMFaceElem) support. / 符号 get_sticker_by_name, get_random_sticker, get_sticker_by_id, _normalize_text, _compact_text, _multiset_char_hit_ratio, _bigram_jaccard |

### backend/hermes/gateway/platforms/qqbot/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/qqbot/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | QQBot platform package. |
| [adapter.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/qqbot/adapter.py>) | 内嵌 Hermes 上游源码及项目适配内容中的adapter 实现（目录与文件名推断） | QQ Bot platform adapter using the Official QQ Bot API (v2). / 符号 QQCloseError, check_qq_requirements, _coerce_list, QQAdapter |
| [chunked_upload.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/qqbot/chunked_upload.py>) | 内嵌 Hermes 上游源码及项目适配内容中的上传相关实现（目录与文件名推断） | QQ Bot chunked upload flow. / 符号 UploadDailyLimitExceededError, UploadFileTooLargeError, _UploadProgress, _PreparePart, _PrepareResult, _parse_prepare_response, ChunkedUploader |
| [constants.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/qqbot/constants.py>) | 内嵌 Hermes 上游源码及项目适配内容中的constants 实现（目录与文件名推断） | QQBot package-level constants shared across adapter, onboard, and other modules. |
| [crypto.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/qqbot/crypto.py>) | 内嵌 Hermes 上游源码及项目适配内容中的crypto 实现（目录与文件名推断） | AES-256-GCM utilities for QQBot scan-to-configure credential decryption. / 符号 generate_bind_key, decrypt_secret |
| [keyboards.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/qqbot/keyboards.py>) | 内嵌 Hermes 上游源码及项目适配内容中的keyboards 实现（目录与文件名推断） | QQ Bot inline keyboards + approval / update-prompt senders. / 符号 KeyboardButtonPermission, KeyboardButtonAction, KeyboardButtonRenderData, KeyboardButton, KeyboardRow, KeyboardContent, InlineKeyboard |
| [onboard.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/qqbot/onboard.py>) | 内嵌 Hermes 上游源码及项目适配内容中的onboard 实现（目录与文件名推断） | QQBot scan-to-configure (QR code onboard) module. / 符号 BindStatus, _render_qr, _create_bind_task, _poll_bind_result, build_connect_url, qr_register |
| [utils.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/platforms/qqbot/utils.py>) | 内嵌 Hermes 上游源码及项目适配内容中的utils 实现（目录与文件名推断） | QQBot shared utilities — User-Agent, HTTP helpers, config coercion. / 符号 _get_hermes_version, build_user_agent, get_api_headers, coerce_list |

### backend/hermes/gateway/relay/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/relay/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Relay/connector support package for the Hermes gateway. / 符号 relay_url, relay_platform_identities, _relay_bot_ids_map, relay_bot_username, relay_platform_identity, relay_connection_auth, relay_endpoint |
| [adapter.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/relay/adapter.py>) | 内嵌 Hermes 上游源码及项目适配内容中的adapter 实现（目录与文件名推断） | RelayAdapter — one generic gateway adapter fronted by the connector. EXPERIMENTAL. / 符号 _utf16_len, RelayAdapter |
| [auth.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/relay/auth.py>) | 内嵌 Hermes 上游源码及项目适配内容中的认证相关实现（目录与文件名推断） | Gateway-side relay authentication primitives. EXPERIMENTAL. / 符号 _hmac_hex, sign, verify_signature, make_token, make_upgrade_token, verify_token, _delivery_payload |
| [command_manifest.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/relay/command_manifest.py>) | 内嵌 Hermes 上游源码及项目适配内容中的command_manifest 实现（目录与文件名推断） | Gateway-declared slash-command manifest for the relay lane (Phase 4). / 符号 _opt, build_relay_command_manifest |
| [descriptor.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/relay/descriptor.py>) | 内嵌 Hermes 上游源码及项目适配内容中的descriptor 实现（目录与文件名推断） | CapabilityDescriptor — the relay handshake payload. EXPERIMENTAL. / 符号 CapabilityDescriptor |
| [media.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/relay/media.py>) | 内嵌 Hermes 上游源码及项目适配内容中的media 实现（目录与文件名推断） | Relay media client — gateway↔connector media plane (Phase 2). EXPERIMENTAL. / 符号 media_base_url, RelayMediaClient |
| [transport.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/relay/transport.py>) | 内嵌 Hermes 上游源码及项目适配内容中的transport 实现（目录与文件名推断） | Relay transport protocol — the gateway<->connector wire contract. EXPERIMENTAL. / 符号 RelayTransport |
| [ws_transport.py](<E:/PythonCode/EasyChat/backend/hermes/gateway/relay/ws_transport.py>) | 内嵌 Hermes 上游源码及项目适配内容中的ws_transport 实现（目录与文件名推断） | Production WebSocket RelayTransport — the gateway's live link to the connector. / 符号 _ws_dial_url, _render_relay_context, _normalize_slack_parent_command, _event_from_wire, PassthroughForward, _passthrough_from_wire, WebSocketRelayTransport |

### backend/hermes/hermes_cli/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Hermes CLI - Unified command-line interface for Hermes Agent. / 符号 _ensure_utf8 |
| [_early_recovery.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/_early_recovery.py>) | 内嵌 Hermes 上游源码及项目适配内容中的_early_recovery 实现（目录与文件名推断） | Dependency-light venv recovery that runs BEFORE hermes_cli.main's imports. / 符号 _project_root, _pinned_specs, _certifi_bundle_broken, _probe_broken_packages, _run_repair_install, recover_if_needed |
| [_parser.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/_parser.py>) | 内嵌 Hermes 上游源码及项目适配内容中的_parser 实现（目录与文件名推断） | Top-level argparse construction for the hermes CLI. / 符号 _inherited_flag, build_top_level_parser |
| [_scan_venv_blockers.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/_scan_venv_blockers.py>) | 内嵌 Hermes 上游源码及项目适配内容中的_scan_venv_blockers 实现（目录与文件名推断） | ''hermes_cli/_scan_venv_blockers.py'' — Standalone venv-process scan for JSON consumption. / 符号 _probe_fail_json, _emit_probe_fail, _find_flag, _redact_sensitive_cmdline, main |
| [_subprocess_compat.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/_subprocess_compat.py>) | 内嵌 Hermes 上游源码及项目适配内容中的_subprocess_compat 实现（目录与文件名推断） | Windows subprocess compatibility helpers. / 符号 resolve_node_command, windows_detach_flags, windows_detach_flags_without_breakaway, windows_hide_flags, suppress_platform_ver_console, windows_detach_popen_kwargs, noninteractive_git_env |
| [active_sessions.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/active_sessions.py>) | 内嵌 Hermes 上游源码及项目适配内容中的会话相关实现（目录与文件名推断） | Cross-process active chat session leases. / 符号 coerce_max_concurrent_sessions, resolve_max_concurrent_sessions, format_age, summarize_holders, active_session_limit_message, _state_dir, _state_path |
| [agent_import.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/agent_import.py>) | 内嵌 Hermes 上游源码及项目适配内容中的代理相关实现（目录与文件名推断） | hermes import-agent — import Claude Code / Codex CLI setups into Hermes. / 符号 is_secret_key, normalize_text, read_text, load_yaml_file, dump_yaml_file, extract_markdown_entries, parse_existing_memory_entries |
| [approval_mode.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/approval_mode.py>) | 内嵌 Hermes 上游源码及项目适配内容中的审批相关实现（目录与文件名推断） | Shared persistent approval-mode command logic. / 符号 ApprovalModeResult, _effective_mode, run_approval_mode_command |
| [approvals_suggest.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/approvals_suggest.py>) | 内嵌 Hermes 上游源码及项目适配内容中的approvals_suggest 实现（目录与文件名推断） | ''hermes approvals suggest'' — mine approval history into allowlist proposals. / 符号 Proposal, default_db_path, _connect_readonly, _iter_terminal_calls, _blocked_tool_call_ids, scan_approval_history, normalize_command |
| [auth.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/auth.py>) | 内嵌 Hermes 上游源码及项目适配内容中的认证相关实现（目录与文件名推断） | Multi-provider authentication system for Hermes Agent. / 符号 ProviderConfig, get_anthropic_key, _resolve_kimi_base_url, has_usable_secret, _resolve_api_key_provider_secret, detect_zai_endpoint, _resolve_zai_base_url |
| [auth_commands.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/auth_commands.py>) | 内嵌 Hermes 上游源码及项目适配内容中的认证相关实现（目录与文件名推断） | Credential-pool auth subcommands. / 符号 _get_custom_provider_names, _resolve_custom_provider_input, _normalize_provider, _provider_base_url, _oauth_default_label, _api_key_default_label, _display_source |
| [azure_detect.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/azure_detect.py>) | 内嵌 Hermes 上游源码及项目适配内容中的azure_detect 实现（目录与文件名推断） | Azure Foundry endpoint auto-detection. / 符号 DetectionResult, _resolve_credential, _apply_auth_headers, _http_get_json, _strip_trailing_v1, _looks_like_anthropic_path, _extract_model_ids |
| [backup.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/backup.py>) | 内嵌 Hermes 上游源码及项目适配内容中的备份相关实现（目录与文件名推断） | Backup and import commands for hermes CLI. / 符号 _collect_memory_provider_external_paths, _iter_external_files, _should_exclude, _should_skip_backup_file, _safe_copy_db, is_zeroed_sqlite_file, verify_sqlite_integrity |
| [banner.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/banner.py>) | 内嵌 Hermes 上游源码及项目适配内容中的banner 实现（目录与文件名推断） | Welcome banner, ASCII art, skills summary, and update check for the CLI. / 符号 cprint, _skin_color, get_available_skills, _canonical_github_remote, _is_ssh_remote, _is_official_ssh_remote, _git_stdout |
| [blueprint_cmd.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/blueprint_cmd.py>) | 内嵌 Hermes 上游源码及项目适配内容中的blueprint_cmd 实现（目录与文件名推断） | Shared ''/blueprint'' command logic for CLI, TUI, and gateway. / 符号 BlueprintCommandResult, _resolve_origin, _parse_kv, match_blueprint, _humanize_schedule, build_blueprint_seed, _fmt_catalog |
| [browser_connect.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/browser_connect.py>) | 内嵌 Hermes 上游源码及项目适配内容中的浏览器相关实现（目录与文件名推断） | Shared helpers for attaching Hermes to a local Chromium-family CDP port. / 符号 get_chrome_debug_candidates, chrome_debug_data_dir, _chrome_debug_args, is_browser_debug_ready, discover_local_cdp_url, local_port_in_use, find_free_debug_port |
| [build_info.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/build_info.py>) | 内嵌 Hermes 上游源码及项目适配内容中的build_info 实现（目录与文件名推断） | Baked-in build metadata for Hermes Agent. / 符号 get_build_sha |
| [bundles.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/bundles.py>) | 内嵌 Hermes 上游源码及项目适配内容中的bundles 实现（目录与文件名推断） | Implementation of the ''hermes bundles'' CLI subcommand. / 符号 _console, _cmd_list, _cmd_show, _cmd_create, _cmd_delete, _cmd_reload, register_cli |
| [callbacks.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/callbacks.py>) | 内嵌 Hermes 上游源码及项目适配内容中的callbacks 实现（目录与文件名推断） | Interactive prompt callbacks for terminal_tool integration. / 符号 clarify_callback, prompt_for_secret, approval_callback |
| [checkpoints.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/checkpoints.py>) | 内嵌 Hermes 上游源码及项目适配内容中的checkpoints 实现（目录与文件名推断） | 'hermes checkpoints' CLI subcommand. / 符号 _fmt_bytes, _fmt_ts, _fmt_age, cmd_status, cmd_list, cmd_prune, _confirm |
| [claw.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/claw.py>) | 内嵌 Hermes 上游源码及项目适配内容中的claw 实现（目录与文件名推断） | hermes claw — OpenClaw migration commands. / 符号 _detect_openclaw_processes, _warn_if_openclaw_running, _warn_if_gateway_running, _find_migration_script, _load_migration_module, _find_openclaw_dirs, _scan_workspace_state |
| [cli_agent_setup_mixin.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/cli_agent_setup_mixin.py>) | 内嵌 Hermes 上游源码及项目适配内容中的代理相关实现（目录与文件名推断） | Agent-construction and session-resume display methods for ''HermesCLI''. / 符号 CLIAgentSetupMixin |
| [cli_billing_mixin.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/cli_billing_mixin.py>) | 内嵌 Hermes 上游源码及项目适配内容中的cli_billing_mixin 实现（目录与文件名推断） | Billing and subscription handlers for the interactive CLI (god-file decomposition). / 符号 CLIBillingMixin |
| [cli_commands_mixin.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/cli_commands_mixin.py>) | 内嵌 Hermes 上游源码及项目适配内容中的cli_commands_mixin 实现（目录与文件名推断） | Slash-command handlers for the interactive CLI (god-file decomposition Phase 4). / 符号 CLICommandsMixin |
| [cli_output.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/cli_output.py>) | 内嵌 Hermes 上游源码及项目适配内容中的cli_output 实现（目录与文件名推断） | Shared CLI output helpers for Hermes CLI modules. / 符号 print_info, print_success, print_warning, print_error, print_header, prompt, prompt_yes_no |
| [clipboard.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/clipboard.py>) | 内嵌 Hermes 上游源码及项目适配内容中的clipboard 实现（目录与文件名推断） | Clipboard image extraction for macOS, Windows, Linux, and WSL2. / 符号 save_clipboard_image, has_clipboard_image, _powershell_write_script, _write_clipboard_commands, write_clipboard_text, _macos_save, _macos_has_image |
| [codex_models.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/codex_models.py>) | 内嵌 Hermes 上游源码及项目适配内容中的模型相关实现（目录与文件名推断） | Codex model discovery from API, local cache, and config. / 符号 _add_forward_compat_models, _extract_chatgpt_account_id, _fetch_models_from_api, _read_default_model, _read_cache_models, get_codex_model_ids |
| [codex_runtime_plugin_migration.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/codex_runtime_plugin_migration.py>) | 内嵌 Hermes 上游源码及项目适配内容中的执行运行时相关实现（目录与文件名推断） | Migrate Hermes' MCP server config and Codex's installed curated plugins / 符号 MigrationReport, _translate_one_server, _format_toml_value, _quote_key, render_codex_toml_section, _insert_managed_block_at_top_level, _strip_unmanaged_plugin_tables |
| [codex_runtime_switch.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/codex_runtime_switch.py>) | 内嵌 Hermes 上游源码及项目适配内容中的执行运行时相关实现（目录与文件名推断） | Shared logic for the /codex-runtime slash command. / 符号 CodexRuntimeStatus, parse_args, get_current_runtime, set_runtime, check_codex_binary_ok, apply |
| [colors.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/colors.py>) | 内嵌 Hermes 上游源码及项目适配内容中的colors 实现（目录与文件名推断） | Shared ANSI color utilities for Hermes CLI modules. / 符号 should_use_color, Colors, color |
| [commands.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/commands.py>) | 内嵌 Hermes 上游源码及项目适配内容中的commands 实现（目录与文件名推断） | Slash command definitions and autocomplete for the Hermes CLI. / 符号 CommandDef, _build_command_lookup, resolve_command, _build_description, is_gateway_known_command, should_bypass_active_session, _resolve_config_gates |
| [completion.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/completion.py>) | 内嵌 Hermes 上游源码及项目适配内容中的completion 实现（目录与文件名推断） | Shell completion script generation for hermes CLI. / 符号 _walk, _clean, generate_bash, generate_zsh, generate_fish |
| [config.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/config.py>) | 内嵌 Hermes 上游源码及项目适配内容中的配置相关实现（目录与文件名推断） | Configuration management for Hermes Agent. / 符号 _backup_corrupt_config, _warn_config_parse_failure, _reject_denylisted_env_var, get_managed_system, is_managed, get_managed_update_command, _install_method_project_root |
| [console_engine.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/console_engine.py>) | 内嵌 Hermes 上游源码及项目适配内容中的console_engine 实现（目录与文件名推断） | Safe Hermes Console command engine. / 符号 ConsoleCommandError, ConsoleResult, ConsoleCommand, _ArgumentParser, _capture_output, _is_status_footer_rule, _strip_console_status_footer |
| [container_boot.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/container_boot.py>) | 内嵌 Hermes 上游源码及项目适配内容中的container_boot 实现（目录与文件名推断） | Container-boot reconciliation of per-profile gateway s6 services. / 符号 ReconcileAction, reconcile_profile_gateways, _maybe_migrate_legacy_gateway_run_state, _read_container_argv, _strip_container_argv_prefix, _is_legacy_gateway_run_request, _is_dashboard_container |
| [context_switch_guard.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/context_switch_guard.py>) | 内嵌 Hermes 上游源码及项目适配内容中的上下文相关实现（目录与文件名推断） | Warn when an in-session model switch will trigger preflight compression on the next turn. / 符号 _append_warning, _threshold_tokens, _estimate_tokens, merge_preflight_compression_warning, enrich_model_switch_warnings_for_gateway |
| [copilot_auth.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/copilot_auth.py>) | 内嵌 Hermes 上游源码及项目适配内容中的认证相关实现（目录与文件名推断） | GitHub Copilot authentication utilities. / 符号 validate_copilot_token, resolve_copilot_token, _gh_cli_candidates, _try_gh_cli_token, copilot_device_code_login, _token_fingerprint, exchange_copilot_token |
| [credential_lifecycle.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/credential_lifecycle.py>) | 内嵌 Hermes 上游源码及项目适配内容中的credential_lifecycle 实现（目录与文件名推断） | Unified provider-credential lifecycle across every store Hermes reads. / 符号 _providers_for_env_var, _prune_env_pool_entries, _scrub_config_yaml_mirrors, purge_env_credential_references, save_provider_env_credential, remove_provider_env_credential |
| [cron.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/cron.py>) | 内嵌 Hermes 上游源码及项目适配内容中的定时触发相关实现（目录与文件名推断） | Cron subcommand for hermes CLI. / 符号 _normalize_skills, _cron_api, _active_cron_provider_name, _warn_if_gateway_not_running, cron_list, cron_tick, cron_runs |
| [curator.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/curator.py>) | 内嵌 Hermes 上游源码及项目适配内容中的curator 实现（目录与文件名推断） | CLI subcommand: 'hermes curator <subcommand>'. / 符号 _fmt_ts, _print_unmanaged_summary, _cmd_status, _cmd_run, _cmd_pause, _cmd_resume, _cmd_pin |
| [curses_ui.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/curses_ui.py>) | 内嵌 Hermes 上游源码及项目适配内容中的curses_ui 实现（目录与文件名推断） | Shared curses-based UI components for Hermes CLI. / 符号 radio_item_plain, _curses_style_attr, _draw_description_line, _draw_radio_item, _query_matches, _is_boundary, _token_score |
| [dashboard_register.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dashboard_register.py>) | 内嵌 Hermes 上游源码及项目适配内容中的dashboard_register 实现（目录与文件名推断） | ''hermes dashboard register'' — register a self-hosted dashboard OAuth client. / 符号 _generate_dashboard_name, _resolve_portal_base_url, _register_self_hosted_client, _print_post_register_hint, cmd_dashboard_register |
| [debug.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/debug.py>) | 内嵌 Hermes 上游源码及项目适配内容中的debug 实现（目录与文件名推断） | ''hermes debug'' debug tools for Hermes Agent. / 符号 _pending_file, _load_pending, _save_pending, _record_pending, _sweep_expired_pastes, _best_effort_sweep_expired_pastes, _extract_paste_id |
| [default_soul.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/default_soul.py>) | 内嵌 Hermes 上游源码及项目适配内容中的default_soul 实现（目录与文件名推断） | Default SOUL.md template seeded into HERMES_HOME on first run. / 符号 _normalize_soul, is_legacy_template_soul |
| [dep_ensure.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dep_ensure.py>) | 内嵌 Hermes 上游源码及项目适配内容中的dep_ensure 实现（目录与文件名推断） | Lazy dependency bootstrapper for non-Python runtime deps. / 符号 _has_system_browser, _has_hermes_agent_browser, _find_install_script, ensure_dependency |
| [diagnostics_upload.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/diagnostics_upload.py>) | 内嵌 Hermes 上游源码及项目适配内容中的上传相关实现（目录与文件名推断） | Client for uploading ''hermes debug share'' bundles to Nous-internal S3. / 符号 request_upload_url, put_bundle, share_to_nous |
| [dingtalk_auth.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dingtalk_auth.py>) | 内嵌 Hermes 上游源码及项目适配内容中的认证相关实现（目录与文件名推断） | DingTalk Device Flow authorization. / 符号 RegistrationError, _api_post, begin_registration, poll_registration, wait_for_registration_success, _ensure_qrcode_installed, render_qr_to_terminal |
| [doctor.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/doctor.py>) | 内嵌 Hermes 上游源码及项目适配内容中的doctor 实现（目录与文件名推断） | Doctor command for hermes CLI. / 符号 _python_install_cmd, _system_package_install_cmd, _sqlite_upgrade_hint, _safe_which, _termux_browser_setup_steps, _termux_install_all_fallback_notes, _has_provider_env_config |
| [dump.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dump.py>) | 内嵌 Hermes 上游源码及项目适配内容中的dump 实现（目录与文件名推断） | Dump command for hermes CLI. / 符号 _dotenv_key_names, _get_git_commit, _get_git_commit_date, _redact, _gateway_status, _count_skills, _count_mcp_servers |
| [env_loader.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/env_loader.py>) | 内嵌 Hermes 上游源码及项目适配内容中的env_loader 实现（目录与文件名推断） | Helpers for loading Hermes .env files consistently across entrypoints. / 符号 get_secret_source, get_secret_source_values, reset_secret_source_cache, format_secret_source_suffix, _format_offending_chars, _sanitize_loaded_credentials, _load_dotenv_with_fallback |
| [fallback_cmd.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/fallback_cmd.py>) | 内嵌 Hermes 上游源码及项目适配内容中的fallback_cmd 实现（目录与文件名推断） | hermes fallback — manage the fallback provider chain. / 符号 _read_chain, _write_chain, _format_entry, _extract_fallback_from_model_cfg, _snapshot_auth_active_provider, _restore_auth_active_provider, cmd_fallback_list |
| [fallback_config.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/fallback_config.py>) | 内嵌 Hermes 上游源码及项目适配内容中的配置相关实现（目录与文件名推断） | Helpers for reading the effective fallback provider chain from config. / 符号 _normalized_base_url, resolve_entry_api_key, _iter_fallback_entries, _entry_identity, get_fallback_chain |
| [focus_view.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/focus_view.py>) | 内嵌 Hermes 上游源码及项目适配内容中的focus_view 实现（目录与文件名推断） | Focus view — a display-only reduced-output mode. / 符号 normalize_tool_progress_mode, resolve_focus_arg, effective_tool_progress_mode, would_display_tool_line, format_hidden_line, focus_statusbar_segment, format_focus_status |
| [gateway.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/gateway.py>) | 内嵌 Hermes 上游源码及项目适配内容中的gateway 实现（目录与文件名推断） | Gateway subcommand for hermes CLI. / 符号 GatewayRuntimeSnapshot, ProfileGatewayProcess, _get_service_pids, _get_parent_pid, _is_pid_ancestor_of_current_process, _request_gateway_self_restart, _graceful_restart_via_sigusr1 |
| [gateway_enroll.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/gateway_enroll.py>) | 内嵌 Hermes 上游源码及项目适配内容中的gateway_enroll 实现（目录与文件名推断） | ''hermes gateway enroll'' — enroll a self-hosted gateway with a relay connector. / 符号 _default_gateway_id, _resolve_connector_url, _resolve_identity_token, _post_enroll, cmd_gateway_enroll |
| [gateway_windows.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/gateway_windows.py>) | 内嵌 Hermes 上游源码及项目适配内容中的gateway_windows 实现（目录与文件名推断） | Windows gateway service backend (Scheduled Task + Startup-folder fallback). / 符号 _schtasks_encoding, _assert_windows, _preserve_hermes_home_path, _quote_cmd_script_arg, _quote_schtasks_arg, _exec_schtasks, _should_fall_back |
| [goals.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/goals.py>) | 内嵌 Hermes 上游源码及项目适配内容中的goals 实现（目录与文件名推断） | Persistent session goals — the Ralph loop for Hermes. / 符号 GoalContract, parse_contract, GoalState, _meta_key, _get_session_db, load_goal, save_goal |
| [gui_uninstall.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/gui_uninstall.py>) | 内嵌 Hermes 上游源码及项目适配内容中的gui_uninstall 实现（目录与文件名推断） | Hermes Desktop (Chat GUI) uninstaller. / 符号 log_info, log_success, log_warn, _agent_root, desktop_userdata_dir, source_built_gui_artifacts, packaged_gui_app_paths |
| [hooks.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/hooks.py>) | 内嵌 Hermes 上游源码及项目适配内容中的hooks 实现（目录与文件名推断） | hermes hooks — inspect and manage shell-script hooks. / 符号 hooks_command, _cmd_list, _cmd_test, _print_run_result, _truncate, _cmd_revoke, _cmd_doctor |
| [init_command.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/init_command.py>) | 内嵌 Hermes 上游源码及项目适配内容中的init_command 实现（目录与文件名推断） | ''/init'' — build the prompt that generates or updates a project AGENTS.md. / 符号 build_init_prompt, build_init_prompt_for_cwd |
| [input_sanitize.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/input_sanitize.py>) | 内嵌 Hermes 上游源码及项目适配内容中的input_sanitize 实现（目录与文件名推断） | Sanitize user prompt text leaked from terminal / paste control sequences. / 符号 strip_leaked_bracketed_paste_wrappers, collapse_repeated_input_artifacts, sanitize_user_prompt_text |
| [inventory.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/inventory.py>) | 内嵌 Hermes 上游源码及项目适配内容中的inventory 实现（目录与文件名推断） | Provider/model inventory context — shared substrate for the dashboard / 符号 ConfigContext, load_picker_context, build_models_payload, build_model_options_payload, build_aux_picker_rows, format_aux_picker_entries, _apply_capabilities |
| [journey.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/journey.py>) | 内嵌 Hermes 上游源码及项目适配内容中的journey 实现（目录与文件名推断） | ''hermes journey'' — what Hermes has learned, on a timeline. / 符号 _build_payload, _primary_hex, _palette, _fade, _resolve, _row_to_text, _term_size |
| [lifecycle.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/lifecycle.py>) | 内嵌 Hermes 上游源码及项目适配内容中的lifecycle 实现（目录与文件名推断） | Hermes lifecycle dispatch for first-party observers and plugins. / 符号 invoke_hook, has_hook, finalize_session |
| [logs.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/logs.py>) | 内嵌 Hermes 上游源码及项目适配内容中的logs 实现（目录与文件名推断） | ''hermes logs'' — view and filter Hermes log files. / 符号 _parse_since, _parse_line_timestamp, _extract_level, _extract_logger_name, _line_matches_component, _matches_filters, tail_log |
| [main.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/main.py>) | 内嵌 Hermes 上游源码及项目适配内容中的主入口相关实现（目录与文件名推断） | Hermes CLI - Main entry point. / 符号 _exit_after_oneshot, _cleanup_oneshot_runtime, _run_and_exit_oneshot, _set_process_title, _config_default_interface_early, _wants_tui_early, _suppress_mouse_residue_early |
| [managed_scope.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/managed_scope.py>) | 内嵌 Hermes 上游源码及项目适配内容中的managed_scope 实现（目录与文件名推断） | Managed scope — IT-pushed, user-immutable config & env layer. / 符号 _under_pytest, get_managed_dir, invalidate_managed_cache, _cached_read, load_managed_config, load_managed_env, apply_managed_overlay |
| [managed_uv.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/managed_uv.py>) | 内嵌 Hermes 上游源码及项目适配内容中的managed_uv 实现（目录与文件名推断） | Hermes-managed uv and Python runtime repair. / 符号 managed_uv_path, resolve_uv, managed_python_install_dir, managed_python_env, RuntimeRepairResult, _RepairLock, _report_runtime_repair_failure |
| [mcp_catalog.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/mcp_catalog.py>) | 内嵌 Hermes 上游源码及项目适配内容中的MCP相关实现（目录与文件名推断） | MCP catalog — curated, Nous-approved MCP servers shipped with the repo. / 符号 EnvVarSpec, AuthSpec, TransportSpec, InstallSpec, ToolsSpec, CatalogEntry, CatalogError |
| [mcp_config.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/mcp_config.py>) | 内嵌 Hermes 上游源码及项目适配内容中的MCP、配置相关实现（目录与文件名推断） | MCP Server Management CLI — ''hermes mcp'' subcommand. / 符号 _info, _success, _warning, _error, _confirm, _prompt, _get_mcp_servers |
| [mcp_picker.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/mcp_picker.py>) | 内嵌 Hermes 上游源码及项目适配内容中的MCP相关实现（目录与文件名推断） | MCP picker — interactive 'hermes mcp picker' (also the default 'hermes mcp'). / 符号 _Row, _build_rows, _format_row, _enable_disable, _configure_tools, _remove_custom, _handle_row |
| [mcp_security.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/mcp_security.py>) | 内嵌 Hermes 上游源码及项目适配内容中的MCP相关实现（目录与文件名推断） | Security checks for user-configured MCP server entries. / 符号 _command_basename, _inline_script, _entry_text, validate_mcp_server_entry, is_mcp_server_entry_suspicious |
| [mcp_startup.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/mcp_startup.py>) | 内嵌 Hermes 上游源码及项目适配内容中的MCP相关实现（目录与文件名推断） | Shared CLI/TUI-safe helpers for background MCP discovery. / 符号 _has_configured_mcp_servers, start_background_mcp_discovery, _resolve_discovery_timeout, _discover_mcp_tools_without_interactive_oauth, wait_for_mcp_discovery, mcp_discovery_in_flight, join_mcp_discovery |
| [memory_oauth.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/memory_oauth.py>) | 内嵌 Hermes 上游源码及项目适配内容中的记忆相关实现（目录与文件名推断） | HTTP routes for memory-provider OAuth connect, mounted by ''web_server''. / 符号 _resolve_flow, _scope_to_profile, start_memory_oauth, memory_oauth_status |
| [memory_setup.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/memory_setup.py>) | 内嵌 Hermes 上游源码及项目适配内容中的记忆相关实现（目录与文件名推断） | hermes memory setup/status — configure memory provider plugins. / 符号 _provider_pip_dependencies, _curses_select, _print_cancelled_setup, _clear_interactive_transition, _prompt, _install_dependencies, _get_available_providers |
| [middleware.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/middleware.py>) | 内嵌 Hermes 上游源码及项目适配内容中的middleware 实现（目录与文件名推断） | Hermes middleware contract helpers. / 符号 RequestMiddlewareResult, observer_payload, middleware_payload, _safe_copy, apply_llm_request_middleware, apply_tool_request_middleware, apply_api_request_middleware |
| [migrate.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/migrate.py>) | 内嵌 Hermes 上游源码及项目适配内容中的migrate 实现（目录与文件名推断） | CLI handlers for ''hermes migrate ...''. / 符号 cmd_migrate, cmd_migrate_xai, _resolve_config_path |
| [moa_cmd.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/moa_cmd.py>) | 内嵌 Hermes 上游源码及项目适配内容中的moa_cmd 实现（目录与文件名推断） | CLI helpers for configuring Mixture of Agents. / 符号 _prompt_choice, _model_options, _pick_slot, _format_slot, _print_config, cmd_moa |
| [moa_config.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/moa_config.py>) | 内嵌 Hermes 上游源码及项目适配内容中的配置相关实现（目录与文件名推断） | Mixture-of-Agents configuration and slash-command helpers. / 符号 _default_reference_models, _coerce_float_or_none, _coerce_reference_timeout, _coerce_degraded_reference_policy, _coerce_int, _coerce_int_or_none, _coerce_fanout |
| [model_catalog.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/model_catalog.py>) | 内嵌 Hermes 上游源码及项目适配内容中的模型相关实现（目录与文件名推断） | Remote model catalog fetcher. / 符号 _load_catalog_config, _cache_path, _fetch_manifest, _fetch_manifest_with_fallback, _validate_manifest, _read_disk_cache, _write_disk_cache |
| [model_cost_guard.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/model_cost_guard.py>) | 内嵌 Hermes 上游源码及项目适配内容中的模型相关实现（目录与文件名推断） | Expensive-model confirmation helpers for model selection surfaces. / 符号 ExpensiveModelWarning, _to_decimal, _format_money, _pricing_from_model_info, expensive_model_warning |
| [model_normalize.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/model_normalize.py>) | 内嵌 Hermes 上游源码及项目适配内容中的模型相关实现（目录与文件名推断） | Per-provider model name normalization. / 符号 _normalize_for_deepseek, _strip_vendor_prefix, _dots_to_hyphens, _normalize_provider_alias, _strip_matching_provider_prefix, detect_vendor, _prepend_vendor |
| [model_search.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/model_search.py>) | 内嵌 Hermes 上游源码及项目适配内容中的模型、搜索相关实现（目录与文件名推断） | Picker-only search aliases for model ids. / 符号 model_alias_canonical, model_search_text |
| [model_setup_flows.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/model_setup_flows.py>) | 内嵌 Hermes 上游源码及项目适配内容中的模型相关实现（目录与文件名推断） | Per-provider model-selection wizard flows for ''hermes setup'' / ''hermes model''. / 符号 bedrock_region_geo_prefix, bedrock_model_routable_from_region, _existing_api_key_for_model_flow, _prune_replaced_custom_model_config_credentials, _prompt_auth_credentials_choice, _model_flow_openrouter, _print_mo |
| [model_switch.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/model_switch.py>) | 内嵌 Hermes 上游源码及项目适配内容中的模型相关实现（目录与文件名推断） | Shared model-switching logic for CLI and gateway /model commands. / 符号 _declared_model_ids, _save_discovered_models_to_config, _bare_custom_provider_def, format_model_for_display, is_nous_hermes_non_agentic, _check_hermes_model_warning, ModelIdentity |
| [models.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/models.py>) | 内嵌 Hermes 上游源码及项目适配内容中的模型相关实现（目录与文件名推断） | Canonical model catalogs and lightweight validation helpers. / 符号 _urlopen_model_catalog_request, _codex_curated_models, _xai_promote_top, _xai_merge_curated_extras, _xai_curated_models, _is_model_free, is_nous_free_tier |
| [nous_account.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/nous_account.py>) | 内嵌 Hermes 上游源码及项目适配内容中的nous_account 实现（目录与文件名推断） | Normalized Nous Portal account entitlement helpers. / 符号 NousPortalSubscriptionInfo, NousPaidServiceAccessInfo, NousToolAccessInfo, NousPortalAccountInfo, nous_portal_billing_url, nous_portal_topup_url, format_nous_portal_entitlement_message |
| [nous_auth_keepalive.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/nous_auth_keepalive.py>) | 内嵌 Hermes 上游源码及项目适配内容中的认证相关实现（目录与文件名推断） | Background keepalive for long-lived Nous Portal sessions. / 符号 _timeout_seconds, _entry_state, _refresh_selected_pool_entry, refresh_nous_auth_keepalive_once, _keepalive_loop, start_nous_auth_keepalive, stop_nous_auth_keepalive |
| [nous_billing.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/nous_billing.py>) | 内嵌 Hermes 上游源码及项目适配内容中的nous_billing 实现（目录与文件名推断） | Nous Portal Remote Spending HTTP client (Phase 2b). / 符号 BillingError, BillingScopeRequired, BillingAuthError, BillingRemoteSpendingRevoked, BillingSessionRevoked, BillingTransient, BillingRateLimited |
| [nous_subscription.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/nous_subscription.py>) | 内嵌 Hermes 上游源码及项目适配内容中的nous_subscription 实现（目录与文件名推断） | Helpers for Nous subscription managed-tool capabilities. / 符号 _uses_gateway, NousFeatureState, NousSubscriptionFeatures, _model_config_dict, _toolset_enabled, _has_agent_browser, _local_browser_runnable |
| [onepassword_secrets_cli.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/onepassword_secrets_cli.py>) | 内嵌 Hermes 上游源码及项目适配内容中的onepassword_secrets_cli 实现（目录与文件名推断） | CLI handlers for ''hermes secrets onepassword ...''. / 符号 register_cli, cmd_setup, cmd_status, cmd_set, cmd_remove, cmd_token, cmd_sync |
| [oneshot.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/oneshot.py>) | 内嵌 Hermes 上游源码及项目适配内容中的oneshot 实现（目录与文件名推断） | Oneshot (-z) mode: send a prompt, get the final content block, exit. / 符号 _normalize_toolsets, _validate_explicit_toolsets, _write_usage_file, run_oneshot, _create_session_db_for_oneshot, _run_agent, _oneshot_clarify_callback |
| [pairing.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/pairing.py>) | 内嵌 Hermes 上游源码及项目适配内容中的pairing 实现（目录与文件名推断） | CLI commands for the DM pairing system. / 符号 pairing_command, _cmd_list, _cmd_approve, _cmd_revoke, _cmd_clear_pending |
| [partial_compress.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/partial_compress.py>) | 内嵌 Hermes 上游源码及项目适配内容中的partial_compress 实现（目录与文件名推断） | Boundary-aware partial compression — "summarize up to here". / 符号 parse_partial_compress_args, extract_compress_flags, summarize_compress_preview, _coerce_keep, split_history_for_partial_compress, rejoin_compressed_head_and_tail |
| [pets.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/pets.py>) | 内嵌 Hermes 上游源码及项目适配内容中的pets 实现（目录与文件名推断） | CLI subcommand: ''hermes pets <subcommand>''. / 符号 _print, _err, _cmd_list, _cmd_install, _cmd_remove, _cmd_select, _cmd_off |
| [platforms.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/platforms.py>) | 内嵌 Hermes 上游源码及项目适配内容中的platforms 实现（目录与文件名推断） | Shared platform registry for Hermes Agent. / 符号 PlatformInfo, platform_label, get_all_platforms |
| [plugins.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/plugins.py>) | 内嵌 Hermes 上游源码及项目适配内容中的plugins 实现（目录与文件名推断） | Hermes Plugin System / 符号 get_bundled_plugins_dir, PluginToolOverrideError, _install_plugin_debug_handler, _env_enabled, _get_disabled_plugins, _get_enabled_plugins, PluginManifest |
| [plugins_cmd.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/plugins_cmd.py>) | 内嵌 Hermes 上游源码及项目适配内容中的plugins_cmd 实现（目录与文件名推断） | ''hermes plugins'' CLI subcommand — install, update, remove, and list plugins. / 符号 _resolve_git_executable, PluginOperationError, _plugins_dir, _sanitize_plugin_name, _resolve_git_url, _resolve_subdir_within, _repo_name_from_url |
| [portal_cli.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/portal_cli.py>) | 内嵌 Hermes 上游源码及项目适配内容中的portal_cli 实现（目录与文件名推断） | ''hermes portal'' — the human-readable entry point for Nous Portal. / 符号 _cmd_status, _cmd_open, _cmd_tools, _cmd_login, portal_command, add_parser |
| [profile_describer.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/profile_describer.py>) | 内嵌 Hermes 上游源码及项目适配内容中的profile_describer 实现（目录与文件名推断） | Profile describer — auto-generate ''description'' for a profile. / 符号 DescribeOutcome, _collect_skills, _extract_json_blob, describe_profile, list_describable_profiles |
| [profile_distribution.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/profile_distribution.py>) | 内嵌 Hermes 上游源码及项目适配内容中的profile_distribution 实现（目录与文件名推断） | Profile distributions — shareable, packaged Hermes profiles via git. / 符号 DistributionError, EnvRequirement, DistributionManifest, _load_yaml, _dump_yaml, read_manifest, write_manifest |
| [profiles.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/profiles.py>) | 内嵌 Hermes 上游源码及项目适配内容中的profiles 实现（目录与文件名推断） | Profile management for multiple isolated Hermes instances. / 符号 has_bundled_skills_opt_out, _clone_all_copytree_ignore, _get_profiles_root, _get_default_hermes_home, _get_active_profile_path, _get_wrapper_dir, normalize_profile_name |
| [projects_cmd.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/projects_cmd.py>) | 内嵌 Hermes 上游源码及项目适配内容中的projects_cmd 实现（目录与文件名推断） | ''hermes project'' CLI — manage first-class, multi-folder Projects. / 符号 build_parser, projects_command, _resolve, _with_project, _print_project, _cmd_create, _cmd_list |
| [projects_db.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/projects_db.py>) | 内嵌 Hermes 上游源码及项目适配内容中的projects_db 实现（目录与文件名推断） | Per-profile first-class Project store. / 符号 projects_db_path, _slugify, normalize_slug, _new_project_id, _now, _normalize_path, connect |
| [prompt_size.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/prompt_size.py>) | 内嵌 Hermes 上游源码及项目适配内容中的提示词相关实现（目录与文件名推断） | Prompt-size diagnostic: ''hermes prompt-size''. / 符号 _bytes, _tool_name, _build_inspection_agent, _skill_md_paths_by_name, _compute_skills_breakdown, _compute_toolsets_breakdown, compute_prompt_breakdown |
| [provider_catalog.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/provider_catalog.py>) | 内嵌 Hermes 上游源码及项目适配内容中的供应商相关实现（目录与文件名推断） | Unified provider catalog — one source of truth for the provider universe. / 符号 ProviderDescriptor, tab_for_auth_type, _split_env_vars, provider_catalog, provider_catalog_by_slug |
| [providers.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/providers.py>) | 内嵌 Hermes 上游源码及项目适配内容中的供应商相关实现（目录与文件名推断） | Single source of truth for provider identity in Hermes Agent. / 符号 HermesOverlay, ProviderDef, normalize_provider, get_provider, get_label, is_aggregator, is_routing_aggregator |
| [proxy_cli.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/proxy_cli.py>) | 内嵌 Hermes 上游源码及项目适配内容中的proxy_cli 实现（目录与文件名推断） | CLI handlers for ''hermes egress ...''. / 符号 register_cli, cmd_install, cmd_setup, cmd_start, cmd_stop, cmd_restart, cmd_reload |
| [psutil_android.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/psutil_android.py>) | 内嵌 Hermes 上游源码及项目适配内容中的Android相关实现（目录与文件名推断） | Helpers for the temporary psutil-on-Android compatibility installer. / 符号 PsutilAndroidInstallError, _normalize_member_parts, _safe_extract_tar_gz, prepare_patched_psutil_sdist |
| [pt_input_extras.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/pt_input_extras.py>) | 内嵌 Hermes 上游源码及项目适配内容中的pt_input_extras 实现（目录与文件名推断） | Augmentations to prompt_toolkit's input-parsing tables. / 符号 install_shift_enter_alias, install_ctrl_enter_alias, install_ignored_terminal_sequences |
| [pty_bridge.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/pty_bridge.py>) | 内嵌 Hermes 上游源码及项目适配内容中的pty_bridge 实现（目录与文件名推断） | PTY bridge for 'hermes dashboard' chat tab. / 符号 _clamp_dimension, PtyUnavailableError, PtyBridge |
| [pty_session.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/pty_session.py>) | 内嵌 Hermes 上游源码及项目适配内容中的会话相关实现（目录与文件名推断） | Keep-alive PTY sessions for dashboard terminals. / 符号 RingBuffer, PtySession, RegistryFull, run_reaper, PtySessionRegistry |
| [relaunch.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/relaunch.py>) | 内嵌 Hermes 上游源码及项目适配内容中的relaunch 实现（目录与文件名推断） | Unified self-relaunch for Hermes CLI. / 符号 _build_inherited_flag_table, _extract_inherited_flags, resolve_hermes_bin, build_relaunch_argv, relaunch |
| [route_identity.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/route_identity.py>) | 内嵌 Hermes 上游源码及项目适配内容中的route_identity 实现（目录与文件名推断） | Fail-closed URL identity normalization for model/provider routes. / 符号 normalize_route_base_url, should_clear_context_pin, should_clear_context_pin_async |
| [runtime_provider.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/runtime_provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的执行运行时、供应商相关实现（目录与文件名推断） | Shared runtime provider resolution for CLI, gateway, cron, and helpers. / 符号 _getenv, _normalize_custom_provider_name, _loopback_hostname, _config_base_url_trustworthy_for_bare_custom, _detect_api_mode_for_url, _resolve_plain_custom_api_mode, _host_derived_api_key |
| [secret_prompt.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/secret_prompt.py>) | 内嵌 Hermes 上游源码及项目适配内容中的提示词相关实现（目录与文件名推断） | Secret input prompts with masked typing feedback. / 符号 _collect_masked_input, masked_secret_prompt, _stream_is_tty, _masked_secret_prompt_windows, _masked_secret_prompt_posix |
| [secrets_cli.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/secrets_cli.py>) | 内嵌 Hermes 上游源码及项目适配内容中的secrets_cli 实现（目录与文件名推断） | CLI handlers for ''hermes secrets bitwarden ...''. / 符号 register_cli, cmd_setup, cmd_status, cmd_token, cmd_sync, cmd_disable, cmd_install |
| [security_advisories.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/security_advisories.py>) | 内嵌 Hermes 上游源码及项目适配内容中的security_advisories 实现（目录与文件名推断） | Security advisory checker for Hermes Agent. / 符号 Advisory, AdvisoryHit, _installed_version, detect_compromised, get_acked_ids, ack_advisory, filter_unacked |
| [security_audit.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/security_audit.py>) | 内嵌 Hermes 上游源码及项目适配内容中的security_audit 实现（目录与文件名推断） | On-demand supply-chain audit for Hermes Agent installs. / 符号 Component, Vulnerability, Finding, _discover_venv, _parse_requirements, _parse_pyproject_pins, _discover_plugins |
| [security_audit_startup.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/security_audit_startup.py>) | 内嵌 Hermes 上游源码及项目适配内容中的security_audit_startup 实现（目录与文件名推断） | Startup security posture audit (warn-on-load, never blocks). / 符号 _is_root, _running_as_root, _iter_sshd_config_lines, _ssh_password_auth_enabled, _in_container, _path_is_mounted, _container_no_volume_mount |
| [send_cmd.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/send_cmd.py>) | 内嵌 Hermes 上游源码及项目适配内容中的send_cmd 实现（目录与文件名推断） | CLI subcommand: ''hermes send'' — pipe text from shell scripts to any / 符号 _read_message_body, _resolve_target, _emit_result, _list_targets, _load_hermes_env, cmd_send, register_send_subparser |
| [service_manager.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/service_manager.py>) | 内嵌 Hermes 上游源码及项目适配内容中的service_manager 实现（目录与文件名推断） | Abstract service manager interface. / 符号 validate_profile_name, ServiceManager, detect_service_manager, _s6_running, _RegistrationUnsupportedMixin, SystemdServiceManager, LaunchdServiceManager |
| [session_export.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/session_export.py>) | 内嵌 Hermes 上游源码及项目适配内容中的会话相关实现（目录与文件名推断） | Shared renderers for session export commands. / 符号 normalize_export_format, normalize_export_only, render_sessions_export, export_record_count, iter_user_prompt_records, _render_jsonl, _render_markdown |
| [session_export_html.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/session_export_html.py>) | 内嵌 Hermes 上游源码及项目适配内容中的会话相关实现（目录与文件名推断） | HTML Export generator for Hermes sessions. / 符号 _escape_html, _format_timestamp, _generate_messages_html, generate_multi_session_html_export, generate_html_export |
| [session_export_md.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/session_export_md.py>) | 内嵌 Hermes 上游源码及项目适配内容中的会话相关实现（目录与文件名推断） | Markdown/QMD export helpers for Hermes sessions. / 符号 _iso_timestamp, _frontmatter_value, _frontmatter_line, _message_heading, _render_content, _render_tool_calls, _session_id |
| [session_filters.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/session_filters.py>) | 内嵌 Hermes 上游源码及项目适配内容中的会话相关实现（目录与文件名推断） | Shared time/filter parsing for 'hermes sessions prune' / 'archive'. / 符号 parse_duration_seconds, parse_point_in_time, format_epoch, build_prune_filters, describe_filters |
| [session_listing.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/session_listing.py>) | 内嵌 Hermes 上游源码及项目适配内容中的会话相关实现（目录与文件名推断） | Shared session-listing helpers for CLI and gateway slash surfaces. / 符号 parse_session_listing_args, query_session_listing, format_gateway_session_listing |
| [session_recap.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/session_recap.py>) | 内嵌 Hermes 上游源码及项目适配内容中的会话相关实现（目录与文件名推断） | Session recap — summarize what's happened in the current session. / 符号 _coerce_text, _tool_call_name_and_args, _iter_assistant_tool_calls, _count_visible_turns, _latest_user_prompt, _latest_assistant_text, _recent_window |
| [session_recovery.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/session_recovery.py>) | 内嵌 Hermes 上游源码及项目适配内容中的会话相关实现（目录与文件名推断） | Offline, non-destructive recovery for a damaged Hermes session database. / 符号 SessionRecoveryError, SessionRecoverySafetyError, SessionRecoverySourceError, _sidecar_path, _resolved_output_path, _validate_paths, _source_fingerprint |
| [setup.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/setup.py>) | 内嵌 Hermes 上游源码及项目适配内容中的setup 实现（目录与文件名推断） | Interactive setup wizard for Hermes Agent. / 符号 _model_config_dict, _get_credential_pool_strategies, _set_credential_pool_strategy, _supports_same_provider_pool_setup, _current_reasoning_effort, _set_reasoning_effort, print_header |
| [setup_hidden_env.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/setup_hidden_env.py>) | 内嵌 Hermes 上游源码及项目适配内容中的setup_hidden_env 实现（目录与文件名推断） | Which platform env vars the setup surfaces hide. / 符号 is_setup_hidden_env |
| [setup_whatsapp_cloud.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/setup_whatsapp_cloud.py>) | 内嵌 Hermes 上游源码及项目适配内容中的setup_whatsapp_cloud 实现（目录与文件名推断） | Interactive setup wizard for the WhatsApp Cloud API adapter. / 符号 _validate_phone_number_id, _validate_waba_id, _validate_app_id, _validate_app_secret, _validate_access_token, _prompt, _prompt_validated |
| [skills_config.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/skills_config.py>) | 内嵌 Hermes 上游源码及项目适配内容中的技能、配置相关实现（目录与文件名推断） | Skills configuration for Hermes Agent. / 符号 _normalize_skill_names, get_disabled_skills, save_disabled_skills, _list_all_skills, _get_categories, _select_platform, _toggle_by_category |
| [skills_hub.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/skills_hub.py>) | 内嵌 Hermes 上游源码及项目适配内容中的技能相关实现（目录与文件名推断） | Skills Hub CLI — Unified interface for the Hermes Skills Hub. / 符号 _display_source, _resolve_short_name, _format_extra_metadata_lines, _resolve_source_meta_and_bundle, _derive_category_from_install_path, _is_valid_installed_skill_name, _existing_categories |
| [skin_cmd.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/skin_cmd.py>) | 内嵌 Hermes 上游源码及项目适配内容中的skin_cmd 实现（目录与文件名推断） | ''hermes skin'' — list, switch, and tweak skins from the CLI. / 符号 _skins_dir, _active_skin, _use, _skin_set, _skin_list, skin_command |
| [skin_engine.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/skin_engine.py>) | 内嵌 Hermes 上游源码及项目适配内容中的skin_engine 实现（目录与文件名推断） | Hermes skin/theme engine — the theme SDK for every surface. / 符号 SkinConfig, _skins_dir, _load_skin_from_yaml, _mapping_or_empty, _build_skin_config, list_skins, load_skin |
| [slack_cli.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/slack_cli.py>) | 内嵌 Hermes 上游源码及项目适配内容中的slack_cli 实现（目录与文件名推断） | ''hermes slack ...'' CLI subcommands. / 符号 _build_full_manifest, slack_manifest_command |
| [sqlite_runtime.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/sqlite_runtime.py>) | 内嵌 Hermes 上游源码及项目适配内容中的执行运行时相关实现（目录与文件名推断） | Import-safe helpers for inspecting a Python interpreter's linked SQLite. / 符号 _version_tuple, is_sqlite_wal_reset_vulnerable, SQLiteRuntimeInfo, probe_sqlite_runtime |
| [sqlite_safe_read.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/sqlite_safe_read.py>) | 内嵌 Hermes 上游源码及项目适配内容中的sqlite_safe_read 实现（目录与文件名推断） | Lock-safe inspection of SQLite database files. / 符号 UntrackableConnectionError, _key, _canonical_db_path, track_connection, untrack_connection, has_live_connection, _TrackingMixin |
| [sqlite_util.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/sqlite_util.py>) | 内嵌 Hermes 上游源码及项目适配内容中的sqlite_util 实现（目录与文件名推断） | Shared SQLite primitives for the small per-profile / board stores. / 符号 add_column_if_missing, write_txn |
| [status.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/status.py>) | 内嵌 Hermes 上游源码及项目适配内容中的status 实现（目录与文件名推断） | Status command for hermes CLI. / 符号 check_mark, redact_key, _format_iso_timestamp, _configured_model_label, _effective_provider_label, show_status |
| [stdio.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/stdio.py>) | 内嵌 Hermes 上游源码及项目适配内容中的stdio 实现（目录与文件名推断） | Windows-safe stdio configuration. / 符号 is_windows, _flip_console_code_page_to_utf8, _reconfigure_stream, configure_windows_stdio, _default_windows_editor, _augment_path_with_known_tools |
| [suggestions_cmd.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/suggestions_cmd.py>) | 内嵌 Hermes 上游源码及项目适配内容中的suggestions_cmd 实现（目录与文件名推断） | Shared ''/suggestions'' command logic for CLI and gateway. / 符号 _fmt_pending, _resolve_origin, handle_suggestions_command |
| [telegram_managed_bot.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/telegram_managed_bot.py>) | 内嵌 Hermes 上游源码及项目适配内容中的telegram_managed_bot 实现（目录与文件名推断） | Telegram Managed Bot onboarding client. / 符号 TelegramPairing, TelegramBotSetupResult, _api_url, is_valid_telegram_bot_token, _parse_owner_user_id, render_qr_terminal, print_qr_code |
| [timeouts.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/timeouts.py>) | 内嵌 Hermes 上游源码及项目适配内容中的timeouts 实现（目录与文件名推断） | 符号 _coerce_timeout, get_provider_request_timeout, get_provider_stale_timeout, _get_model_config |
| [tips.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/tips.py>) | 内嵌 Hermes 上游源码及项目适配内容中的tips 实现（目录与文件名推断） | Random tips shown at CLI session start to help users discover features. / 符号 get_random_tip |
| [tools_config.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/tools_config.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具、配置相关实现（目录与文件名推断） | Unified tool configuration for Hermes Agent. / 符号 _post_setup_no_window_flags, gui_toolset_label, _xai_credentials_present, _toolset_allowed_for_platform, _toolset_configuration_platform, _get_effective_configurable_toolsets, _get_plugin_toolset_keys |
| [toolset_validation.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/toolset_validation.py>) | 内嵌 Hermes 上游源码及项目适配内容中的toolset_validation 实现（目录与文件名推断） | Validation for the ''platform_toolsets'' config section. / 符号 validate_platform_toolsets |
| [uninstall.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/uninstall.py>) | 内嵌 Hermes 上游源码及项目适配内容中的uninstall 实现（目录与文件名推断） | Hermes Agent Uninstaller. / 符号 log_info, log_success, log_warn, get_project_root, find_shell_configs, remove_path_from_shell_configs, remove_wrapper_script |
| [urllib_security.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/urllib_security.py>) | 内嵌 Hermes 上游源码及项目适配内容中的urllib_security 实现（目录与文件名推断） | Security policy for credential-bearing stdlib urllib requests. / 符号 url_origin, SafeCredentialRedirectHandler, _CrossOriginRequestSanitizer, _secure_opener_from_installed_policy, open_credentialed_url |
| [voice.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/voice.py>) | 内嵌 Hermes 上游源码及项目适配内容中的语音相关实现（目录与文件名推断） | Process-wide voice recording + TTS API for the TUI gateway. / 符号 voice_record_key_from_config, normalize_voice_record_key_for_prompt_toolkit, format_voice_record_key_for_status, _debug, _beeps_enabled, _play_beep, start_recording |
| [web_git.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/web_git.py>) | 内嵌 Hermes 上游源码及项目适配内容中的web_git 实现（目录与文件名推断） | Backend git operations for the desktop coding rail + Codex-style review pane. / 符号 _git, _git_out, _git_ok, _is_dir, resolve_rename_path, _numstat, _untracked_insertions |
| [web_server.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/web_server.py>) | 内嵌 Hermes 上游源码及项目适配内容中的web_server 实现（目录与文件名推断） | Hermes Agent — Web UI server. / 符号 _start_desktop_cron_ticker, _warm_gateway_module, _resolve_restart_drain_timeout, _lifespan, _get_event_state, _get_chat_argv_lock, _get_pty_active_session_files |
| [webhook.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/webhook.py>) | 内嵌 Hermes 上游源码及项目适配内容中的webhook 实现（目录与文件名推断） | hermes webhook — manage dynamic webhook subscriptions from the CLI. / 符号 _hermes_home, _subscriptions_path, _load_subscriptions, _save_subscriptions, _get_webhook_config, _is_webhook_enabled, _get_webhook_base_url |
| [win_pty_bridge.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/win_pty_bridge.py>) | 内嵌 Hermes 上游源码及项目适配内容中的win_pty_bridge 实现（目录与文件名推断） | Windows ConPTY bridge for the 'hermes dashboard' chat tab. / 符号 _clamp, PtyUnavailableError, WinPtyBridge |
| [windows_ssh_runtime.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/windows_ssh_runtime.py>) | 内嵌 Hermes 上游源码及项目适配内容中的执行运行时相关实现（目录与文件名推断） | Native Windows trust boundary for Desktop SSH backend lifecycle. / 符号 _win32, _ownership, _nonce, _root, _directory, _token_path, _log_path |
| [write_approval_commands.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/write_approval_commands.py>) | 内嵌 Hermes 上游源码及项目适配内容中的审批相关实现（目录与文件名推断） | Shared handlers for the /memory and /skills write-approval subcommands. / 符号 _fmt_state, _fmt_pending_list, handle_pending_subcommand, _resolve_one, _approve, _apply_one, _reject |
| [xai_retirement.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/xai_retirement.py>) | 内嵌 Hermes 上游源码及项目适配内容中的xai_retirement 实现（目录与文件名推断） | Detect xAI models retired on May 15, 2026. / 符号 RetirementIssue, _normalize, _looks_like_xai, find_retired_xai_refs, format_issue, ApplyResult, _walk_to_parent |

### backend/hermes/hermes_cli/dashboard_auth/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dashboard_auth/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Dashboard authentication provider framework. |
| [audit.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dashboard_auth/audit.py>) | 内嵌 Hermes 上游源码及项目适配内容中的audit 实现（目录与文件名推断） | Audit log for dashboard-auth events. / 符号 AuditEvent, _resolve_log_path, audit_log |
| [base.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dashboard_auth/base.py>) | 内嵌 Hermes 上游源码及项目适配内容中的base 实现（目录与文件名推断） | Abstract base + dataclasses + exceptions for dashboard auth providers. / 符号 Session, TokenPrincipal, LoginStart, ProviderError, InvalidCodeError, InvalidCredentialsError, RefreshExpiredError |
| [cookies.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dashboard_auth/cookies.py>) | 内嵌 Hermes 上游源码及项目适配内容中的cookies 实现（目录与文件名推断） | Cookie helpers for dashboard auth. / 符号 _resolved_name, _cookie_path, _common_attrs, set_session_provider_cookie, set_session_cookies, clear_session_cookies, set_pkce_cookie |
| [login_page.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dashboard_auth/login_page.py>) | 内嵌 Hermes 上游源码及项目适配内容中的login_page 实现（目录与文件名推断） | Server-rendered /login page. / 符号 render_login_html, _render_password_form |
| [middleware.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dashboard_auth/middleware.py>) | 内嵌 Hermes 上游源码及项目适配内容中的middleware 实现（目录与文件名推断） | Auth-gate middleware for the dashboard. / 符号 _path_is_public, _client_ip, _ordered_session_providers, _unauth_response, _auto_sso_response, _safe_next_target, _extract_bearer |
| [native_flow.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dashboard_auth/native_flow.py>) | 内嵌 Hermes 上游源码及项目适配内容中的native_flow 实现（目录与文件名推断） | Gateway-brokered RFC 8252 (OAuth 2.0 for Native Apps) authorization store. / 符号 _Pending, _IssuedCode, NativeFlowError, PendingNotFound, CodeInvalid, _b64url_no_pad, _s256 |
| [prefix.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dashboard_auth/prefix.py>) | 内嵌 Hermes 上游源码及项目适配内容中的prefix 实现（目录与文件名推断） | Helpers for X-Forwarded-Prefix support. / 符号 _warn_if_malformed, _warn_if_malformed_prefix, normalise_prefix, prefix_from_request, _normalise_public_url, _load_dashboard_section, resolve_public_url |
| [public_paths.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dashboard_auth/public_paths.py>) | 内嵌 Hermes 上游源码及项目适配内容中的public_paths 实现（目录与文件名推断） | Shared allowlist of ''/api/*'' paths that bypass dashboard auth. |
| [registry.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dashboard_auth/registry.py>) | 内嵌 Hermes 上游源码及项目适配内容中的注册表相关实现（目录与文件名推断） | Module-level registry for DashboardAuthProvider instances. / 符号 register_provider, get_provider, list_providers, list_token_providers, list_session_providers, clear_providers |
| [routes.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dashboard_auth/routes.py>) | 内嵌 Hermes 上游源码及项目适配内容中的routes 实现（目录与文件名推断） | HTTP routes for the dashboard-auth OAuth round trip. / 符号 _redirect_uri, _client_ip, _prefix, login_page, api_auth_providers, auth_login, _validate_loopback_redirect_uri |
| [token_auth.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dashboard_auth/token_auth.py>) | 内嵌 Hermes 上游源码及项目适配内容中的令牌/Token、认证相关实现（目录与文件名推断） | Route-agnostic non-interactive (bearer-token) auth seam for the dashboard. / 符号 register_token_route, is_token_route, clear_token_routes, _client_ip, extract_bearer_token, authenticate_token, token_auth_middleware |
| [ws_tickets.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/dashboard_auth/ws_tickets.py>) | 内嵌 Hermes 上游源码及项目适配内容中的ws_tickets 实现（目录与文件名推断） | WS-upgrade auth credentials for gated mode. / 符号 TicketInvalid, mint_ticket, consume_ticket, _gc_expired_locked, internal_ws_credential, consume_internal_credential, _reset_for_tests |

### backend/hermes/hermes_cli/observability/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/observability/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | First-party Hermes observability integrations. / 符号 observe_lifecycle, handles_hook, _safe_observe |
| [relay_runtime.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/observability/relay_runtime.py>) | 内嵌 Hermes 上游源码及项目适配内容中的执行运行时相关实现（目录与文件名推断） | Compatibility alias for the core Hermes Relay runtime. |
| [relay_shared_metrics.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/observability/relay_shared_metrics.py>) | 内嵌 Hermes 上游源码及项目适配内容中的relay_shared_metrics 实现（目录与文件名推断） | Direct NeMo Relay integration for Hermes shared client metrics. / 符号 _retry_ordinal, _ModelCall, _TaskRun, _MetricsSession, _Runtime, enabled, handles_hook |
| [shared_metrics.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/observability/shared_metrics.py>) | 内嵌 Hermes 上游源码及项目适配内容中的shared_metrics 实现（目录与文件名推断） | Durable aggregation and local export for Hermes shared metrics. / 符号 _utc_now, _isoformat, SharedMetricsStore |
| [shared_metrics_contract.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/observability/shared_metrics_contract.py>) | 内嵌 Hermes 上游源码及项目适配内容中的shared_metrics_contract 实现（目录与文件名推断） | Bounded product contract for the first Hermes shared-metrics slice. / 符号 counter_dimensions_are_valid, model_call_dimensions, task_counter, execution_surface, task_start_fields, task_entrypoint, task_terminal_fields |
| [shared_metrics_subscriber.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/observability/shared_metrics_subscriber.py>) | 内嵌 Hermes 上游源码及项目适配内容中的shared_metrics_subscriber 实现（目录与文件名推断） | Relay subscriber for the persisted Hermes shared-metrics slice. / 符号 SharedMetricsSubscriber |

### backend/hermes/hermes_cli/observability/schemas/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [hermes.shared_metrics.v1.schema.json](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/observability/schemas/hermes.shared_metrics.v1.schema.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 hermes.shared_metrics.v1.schema（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/hermes_cli/proxy/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/proxy/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Local OpenAI-compatible proxy that forwards to OAuth-authenticated upstreams. |
| [cli.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/proxy/cli.py>) | 内嵌 Hermes 上游源码及项目适配内容中的cli 实现（目录与文件名推断） | CLI handlers for the ''hermes proxy'' subcommand. / 符号 _print_aiohttp_missing, cmd_proxy_start, cmd_proxy_status, cmd_proxy_list_providers, cmd_proxy |
| [server.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/proxy/server.py>) | 内嵌 Hermes 上游源码及项目适配内容中的server 实现（目录与文件名推断） | HTTP server that forwards OpenAI-compatible requests to a configured upstream. / 符号 _json_error, _filter_request_headers, _filter_response_headers, create_app, run_server |

### backend/hermes/hermes_cli/proxy/adapters/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/proxy/adapters/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Upstream adapter registry for the local proxy server. / 符号 get_adapter |
| [base.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/proxy/adapters/base.py>) | 内嵌 Hermes 上游源码及项目适配内容中的base 实现（目录与文件名推断） | Abstract base for proxy upstream adapters. / 符号 UpstreamCredential, UpstreamAdapter |
| [nous_portal.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/proxy/adapters/nous_portal.py>) | 内嵌 Hermes 上游源码及项目适配内容中的nous_portal 实现（目录与文件名推断） | Nous Portal upstream adapter. / 符号 NousPortalAdapter |
| [xai.py](<E:/PythonCode/EasyChat/backend/hermes/hermes_cli/proxy/adapters/xai.py>) | 内嵌 Hermes 上游源码及项目适配内容中的xai 实现（目录与文件名推断） | xAI Grok OAuth upstream adapter. / 符号 XAIGrokAdapter |

### backend/hermes/locales/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [af.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/af.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 af（目录与文件名推断） | 按目录和文件类型定位 |
| [ar.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/ar.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 ar（目录与文件名推断） | 按目录和文件类型定位 |
| [de.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/de.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 de（目录与文件名推断） | 按目录和文件类型定位 |
| [en.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/en.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 en（目录与文件名推断） | 按目录和文件类型定位 |
| [es.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/es.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 es（目录与文件名推断） | 按目录和文件类型定位 |
| [fr.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/fr.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 fr（目录与文件名推断） | 按目录和文件类型定位 |
| [ga.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/ga.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 ga（目录与文件名推断） | 按目录和文件类型定位 |
| [hu.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/hu.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 hu（目录与文件名推断） | 按目录和文件类型定位 |
| [it.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/it.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 it（目录与文件名推断） | 按目录和文件类型定位 |
| [ja.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/ja.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 ja（目录与文件名推断） | 按目录和文件类型定位 |
| [ko.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/ko.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 ko（目录与文件名推断） | 按目录和文件类型定位 |
| [pt.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/pt.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 pt（目录与文件名推断） | 按目录和文件类型定位 |
| [ru.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/ru.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 ru（目录与文件名推断） | 按目录和文件类型定位 |
| [tr.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/tr.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 tr（目录与文件名推断） | 按目录和文件类型定位 |
| [uk.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/uk.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 uk（目录与文件名推断） | 按目录和文件类型定位 |
| [zh-hant.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/zh-hant.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 zh-hant（目录与文件名推断） | 按目录和文件类型定位 |
| [zh.yaml](<E:/PythonCode/EasyChat/backend/hermes/locales/zh.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 zh（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-mcps/blender/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [manifest.yaml](<E:/PythonCode/EasyChat/backend/hermes/optional-mcps/blender/manifest.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 manifest（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-mcps/linear/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [manifest.yaml](<E:/PythonCode/EasyChat/backend/hermes/optional-mcps/linear/manifest.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 manifest（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-mcps/n8n/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [manifest.yaml](<E:/PythonCode/EasyChat/backend/hermes/optional-mcps/n8n/manifest.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 manifest（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-mcps/unreal-engine/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [manifest.yaml](<E:/PythonCode/EasyChat/backend/hermes/optional-mcps/unreal-engine/manifest.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 manifest（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [DESCRIPTION.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/DESCRIPTION.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 DESCRIPTION（目录与文件名推断） | Optional Skills |

### backend/hermes/optional-skills/autonomous-ai-agents/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [DESCRIPTION.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/autonomous-ai-agents/DESCRIPTION.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 DESCRIPTION（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/autonomous-ai-agents/antigravity-cli/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/autonomous-ai-agents/antigravity-cli/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Antigravity CLI ('agy') |

### backend/hermes/optional-skills/autonomous-ai-agents/antigravity-cli/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [cli-docs.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/autonomous-ai-agents/antigravity-cli/references/cli-docs.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 cli-docs（目录与文件名推断） | Antigravity CLI docs, condensed |

### backend/hermes/optional-skills/autonomous-ai-agents/blackbox/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/autonomous-ai-agents/blackbox/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Blackbox CLI |

### backend/hermes/optional-skills/autonomous-ai-agents/grok/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/autonomous-ai-agents/grok/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Grok Build CLI — Hermes Orchestration Guide |

### backend/hermes/optional-skills/autonomous-ai-agents/honcho/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/autonomous-ai-agents/honcho/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Honcho Memory for Hermes |

### backend/hermes/optional-skills/autonomous-ai-agents/openhands/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/autonomous-ai-agents/openhands/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | OpenHands CLI |

### backend/hermes/optional-skills/blockchain/evm/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/blockchain/evm/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | EVM Blockchain Skill |

### backend/hermes/optional-skills/blockchain/evm/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [evm_client.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/blockchain/evm/scripts/evm_client.py>) | 内嵌 Hermes 上游源码及项目适配内容中的evm_client 实现（目录与文件名推断） | evm_client.py — EVM blockchain CLI tool for the Hermes Agent project. / 符号 hex_to_int, is_valid_address, is_valid_txhash, require_address, require_txhash, wei_to_native, gwei_from_wei |

### backend/hermes/optional-skills/blockchain/hyperliquid/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/blockchain/hyperliquid/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Hyperliquid Skill |

### backend/hermes/optional-skills/blockchain/hyperliquid/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [hyperliquid_client.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/blockchain/hyperliquid/scripts/hyperliquid_client.py>) | 内嵌 Hermes 上游源码及项目适配内容中的hyperliquid_client 实现（目录与文件名推断） | Hyperliquid CLI Tool for Hermes Agent / 符号 _hermes_home, _dotenv_paths, _load_dotenv_values, _env_lookup, _api_base, _info_url, _resolve_user |

### backend/hermes/optional-skills/blockchain/solana/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/blockchain/solana/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Solana Blockchain Skill |

### backend/hermes/optional-skills/blockchain/solana/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [solana_client.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/blockchain/solana/scripts/solana_client.py>) | 内嵌 Hermes 上游源码及项目适配内容中的solana_client 实现（目录与文件名推断） | Solana Blockchain CLI Tool for Hermes Agent / 符号 _http_get_json, _rpc_call, rpc_batch, lamports_to_sol, print_json, _short_mint, fetch_prices |

### backend/hermes/optional-skills/communication/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [DESCRIPTION.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/communication/DESCRIPTION.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 DESCRIPTION（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/communication/one-three-one-rule/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/communication/one-three-one-rule/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | 1-3-1 Communication Rule |

### backend/hermes/optional-skills/creative/audiocraft-audio-generation/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/audiocraft-audio-generation/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | AudioCraft: Audio Generation |

### backend/hermes/optional-skills/creative/audiocraft-audio-generation/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [advanced-usage.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/audiocraft-audio-generation/references/advanced-usage.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 advanced-usage（目录与文件名推断） | AudioCraft Advanced Usage Guide |
| [troubleshooting.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/audiocraft-audio-generation/references/troubleshooting.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 troubleshooting（目录与文件名推断） | AudioCraft Troubleshooting Guide |

### backend/hermes/optional-skills/creative/baoyu-article-illustrator/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [PORT_NOTES.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/PORT_NOTES.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 PORT_NOTES（目录与文件名推断） | Port Notes — baoyu-article-illustrator |
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Article Illustrator |

### backend/hermes/optional-skills/creative/baoyu-article-illustrator/prompts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [system.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/prompts/system.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 system（目录与文件名推断） | Image Specifications |

### backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [prompt-construction.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/prompt-construction.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 prompt-construction（目录与文件名推断） | Prompt Construction |
| [style-presets.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/style-presets.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 style-presets（目录与文件名推断） | Style Presets |
| [styles.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 styles（目录与文件名推断） | Style Reference |
| [usage.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/usage.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 usage（目录与文件名推断） | Usage |
| [workflow.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/workflow.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 workflow（目录与文件名推断） | Detailed Workflow Procedures |

### backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/palettes/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [macaron.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/palettes/macaron.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 macaron（目录与文件名推断） | macaron |
| [mono-ink.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/palettes/mono-ink.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 mono-ink（目录与文件名推断） | mono-ink |
| [neon.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/palettes/neon.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 neon（目录与文件名推断） | neon |
| [warm.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/palettes/warm.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 warm（目录与文件名推断） | warm |

### backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [blueprint.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/blueprint.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 blueprint（目录与文件名推断） | blueprint |
| [chalkboard.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/chalkboard.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 chalkboard（目录与文件名推断） | chalkboard |
| [editorial.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/editorial.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 editorial（目录与文件名推断） | editorial |
| [elegant.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/elegant.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 elegant（目录与文件名推断） | elegant |
| [fantasy-animation.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/fantasy-animation.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 fantasy-animation（目录与文件名推断） | fantasy-animation |
| [flat-doodle.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/flat-doodle.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 flat-doodle（目录与文件名推断） | flat-doodle |
| [flat.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/flat.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 flat（目录与文件名推断） | flat |
| [ink-notes.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/ink-notes.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 ink-notes（目录与文件名推断） | ink-notes |
| [intuition-machine.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/intuition-machine.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 intuition-machine（目录与文件名推断） | intuition-machine |
| [minimal.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/minimal.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 minimal（目录与文件名推断） | minimal |
| [nature.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/nature.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 nature（目录与文件名推断） | nature |
| [notion.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/notion.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 notion（目录与文件名推断） | notion |
| [pixel-art.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/pixel-art.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 pixel-art（目录与文件名推断） | pixel-art |
| [playful.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/playful.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 playful（目录与文件名推断） | playful |
| [retro.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/retro.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 retro（目录与文件名推断） | retro |
| [scientific.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/scientific.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 scientific（目录与文件名推断） | scientific |
| [screen-print.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/screen-print.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 screen-print（目录与文件名推断） | screen-print |
| [sketch-notes.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/sketch-notes.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 sketch-notes（目录与文件名推断） | sketch-notes |
| [sketch.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/sketch.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 sketch（目录与文件名推断） | sketch |
| [vector-illustration.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/vector-illustration.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 vector-illustration（目录与文件名推断） | vector-illustration |
| [vintage.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/vintage.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 vintage（目录与文件名推断） | vintage |
| [warm.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/warm.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 warm（目录与文件名推断） | warm |
| [watercolor.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-article-illustrator/references/styles/watercolor.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 watercolor（目录与文件名推断） | watercolor |

### backend/hermes/optional-skills/creative/baoyu-comic/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [PORT_NOTES.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/PORT_NOTES.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 PORT_NOTES（目录与文件名推断） | Port Notes — baoyu-comic |
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Knowledge Comic Creator |

### backend/hermes/optional-skills/creative/baoyu-comic/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [analysis-framework.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/analysis-framework.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 analysis-framework（目录与文件名推断） | Comic Content Analysis Framework |
| [auto-selection.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/auto-selection.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 auto-selection（目录与文件名推断） | Auto Selection |
| [base-prompt.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/base-prompt.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 base-prompt（目录与文件名推断） | Image Specifications |
| [character-template.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/character-template.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 character-template（目录与文件名推断） | Character Definition Template |
| [ohmsha-guide.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/ohmsha-guide.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 ohmsha-guide（目录与文件名推断） | Ohmsha Manga Guide Style |
| [partial-workflows.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/partial-workflows.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 partial-workflows（目录与文件名推断） | Partial Workflows |
| [storyboard-template.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/storyboard-template.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 storyboard-template（目录与文件名推断） | Storyboard Template |
| [workflow.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/workflow.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 workflow（目录与文件名推断） | Complete Workflow |

### backend/hermes/optional-skills/creative/baoyu-comic/references/art-styles/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [chalk.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/art-styles/chalk.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 chalk（目录与文件名推断） | chalk |
| [ink-brush.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/art-styles/ink-brush.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 ink-brush（目录与文件名推断） | ink-brush |
| [ligne-claire.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/art-styles/ligne-claire.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 ligne-claire（目录与文件名推断） | ligne-claire |
| [manga.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/art-styles/manga.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 manga（目录与文件名推断） | manga |
| [minimalist.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/art-styles/minimalist.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 minimalist（目录与文件名推断） | minimalist |
| [realistic.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/art-styles/realistic.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 realistic（目录与文件名推断） | realistic |

### backend/hermes/optional-skills/creative/baoyu-comic/references/layouts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [cinematic.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/layouts/cinematic.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 cinematic（目录与文件名推断） | cinematic |
| [dense.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/layouts/dense.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 dense（目录与文件名推断） | dense |
| [four-panel.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/layouts/four-panel.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 four-panel（目录与文件名推断） | four-panel |
| [mixed.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/layouts/mixed.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 mixed（目录与文件名推断） | mixed |
| [splash.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/layouts/splash.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 splash（目录与文件名推断） | splash |
| [standard.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/layouts/standard.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 standard（目录与文件名推断） | standard |
| [webtoon.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/layouts/webtoon.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 webtoon（目录与文件名推断） | webtoon |

### backend/hermes/optional-skills/creative/baoyu-comic/references/presets/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [concept-story.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/presets/concept-story.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 concept-story（目录与文件名推断） | concept-story |
| [four-panel.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/presets/four-panel.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 four-panel（目录与文件名推断） | four-panel |
| [ohmsha.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/presets/ohmsha.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 ohmsha（目录与文件名推断） | ohmsha |
| [shoujo.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/presets/shoujo.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 shoujo（目录与文件名推断） | shoujo |
| [wuxia.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/presets/wuxia.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 wuxia（目录与文件名推断） | wuxia |

### backend/hermes/optional-skills/creative/baoyu-comic/references/tones/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [action.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/tones/action.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 action（目录与文件名推断） | action |
| [dramatic.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/tones/dramatic.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 dramatic（目录与文件名推断） | dramatic |
| [energetic.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/tones/energetic.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 energetic（目录与文件名推断） | energetic |
| [neutral.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/tones/neutral.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 neutral（目录与文件名推断） | neutral |
| [romantic.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/tones/romantic.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 romantic（目录与文件名推断） | romantic |
| [vintage.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/tones/vintage.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 vintage（目录与文件名推断） | vintage |
| [warm.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/baoyu-comic/references/tones/warm.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 warm（目录与文件名推断） | warm |

### backend/hermes/optional-skills/creative/blender-mcp/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/blender-mcp/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Blender MCP Skill |

### backend/hermes/optional-skills/creative/blender-mcp/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [bpy-api.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/blender-mcp/references/bpy-api.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 bpy-api（目录与文件名推断） | Essential bpy API Reference |
| [pitfalls.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/blender-mcp/references/pitfalls.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 pitfalls（目录与文件名推断） | Blender MCP — Pitfalls & Lessons Learned |
| [recipes.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/blender-mcp/references/recipes.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 recipes（目录与文件名推断） | Blender Recipes |

### backend/hermes/optional-skills/creative/concept-diagrams/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Concept Diagrams |

### backend/hermes/optional-skills/creative/concept-diagrams/examples/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [apartment-floor-plan-conversion.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/examples/apartment-floor-plan-conversion.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 apartment-floor-plan-conversion（目录与文件名推断） | Apartment Floor Plan: 3 BHK to 4 BHK Conversion |
| [automated-password-reset-flow.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/examples/automated-password-reset-flow.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 automated-password-reset-flow（目录与文件名推断） | Automated Password Reset Flow |
| [autonomous-llm-research-agent-flow.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/examples/autonomous-llm-research-agent-flow.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 autonomous-llm-research-agent-flow（目录与文件名推断） | Autonomous LLM Research Agent Flow |
| [banana-journey-tree-to-smoothie.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/examples/banana-journey-tree-to-smoothie.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 banana-journey-tree-to-smoothie（目录与文件名推断） | Journey of a Banana: From Tree to Smoothie |
| [commercial-aircraft-structure.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/examples/commercial-aircraft-structure.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 commercial-aircraft-structure（目录与文件名推断） | Commercial Aircraft Structure |
| [cpu-ooo-microarchitecture.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/examples/cpu-ooo-microarchitecture.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 cpu-ooo-microarchitecture（目录与文件名推断） | Out-of-Order CPU Core Microarchitecture |
| [electricity-grid-flow.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/examples/electricity-grid-flow.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 electricity-grid-flow（目录与文件名推断） | Electricity Grid: Generation to Consumption |
| [feature-film-production-pipeline.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/examples/feature-film-production-pipeline.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 feature-film-production-pipeline（目录与文件名推断） | Feature Film Production Pipeline |
| [hospital-emergency-department-flow.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/examples/hospital-emergency-department-flow.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 hospital-emergency-department-flow（目录与文件名推断） | Hospital Emergency Department Flow |
| [ml-benchmark-grouped-bar-chart.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/examples/ml-benchmark-grouped-bar-chart.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 ml-benchmark-grouped-bar-chart（目录与文件名推断） | ML Benchmark Grouped Bar Chart with Dual Axis |
| [place-order-uml-sequence.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/examples/place-order-uml-sequence.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 place-order-uml-sequence（目录与文件名推断） | Place Order — UML Sequence Diagram |
| [smart-city-infrastructure.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/examples/smart-city-infrastructure.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 smart-city-infrastructure（目录与文件名推断） | Smart City Infrastructure |
| [smartphone-layer-anatomy.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/examples/smartphone-layer-anatomy.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 smartphone-layer-anatomy（目录与文件名推断） | Smartphone Layer Anatomy |
| [sn2-reaction-mechanism.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/examples/sn2-reaction-mechanism.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 sn2-reaction-mechanism（目录与文件名推断） | SN2 Reaction Mechanism |
| [wind-turbine-structure.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/examples/wind-turbine-structure.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 wind-turbine-structure（目录与文件名推断） | Modern Onshore Wind Turbine Structure |

### backend/hermes/optional-skills/creative/concept-diagrams/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [dashboard-patterns.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/references/dashboard-patterns.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 dashboard-patterns（目录与文件名推断） | Dashboard Patterns |
| [infrastructure-patterns.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/references/infrastructure-patterns.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 infrastructure-patterns（目录与文件名推断） | Infrastructure Patterns |
| [physical-shape-cookbook.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/references/physical-shape-cookbook.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 physical-shape-cookbook（目录与文件名推断） | Physical Shape Cookbook |

### backend/hermes/optional-skills/creative/concept-diagrams/templates/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [template.html](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/concept-diagrams/templates/template.html>) | 内嵌 Hermes 上游源码及项目适配内容中的template 实现（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/creative/creative-ideation/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Creative Ideation |

### backend/hermes/optional-skills/creative/creative-ideation/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [anti-slop.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/anti-slop.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 anti-slop（目录与文件名推断） | Anti-Slop Rules |
| [exercises.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/exercises.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 exercises（目录与文件名推断） | Time-Boxed Exercises |
| [full-prompt-library.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/full-prompt-library.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 full-prompt-library（目录与文件名推断） | Constraint Library |
| [heuristics.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/heuristics.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 heuristics（目录与文件名推断） | Routing Heuristics |
| [method-catalog.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/method-catalog.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 method-catalog（目录与文件名推断） | Method Catalog |

### backend/hermes/optional-skills/creative/creative-ideation/references/methods/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [affinity-diagrams.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/affinity-diagrams.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 affinity-diagrams（目录与文件名推断） | Affinity Diagrams |
| [analogy-and-blending.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/analogy-and-blending.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 analogy-and-blending（目录与文件名推断） | Analogy and Blending |
| [biomimicry.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/biomimicry.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 biomimicry（目录与文件名推断） | Biomimicry |
| [chance-and-remix.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/chance-and-remix.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 chance-and-remix（目录与文件名推断） | Chance and Remix |
| [compression-progress.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/compression-progress.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 compression-progress（目录与文件名推断） | Compression Progress |
| [creative-discipline.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/creative-discipline.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 creative-discipline（目录与文件名推断） | Creative Discipline |
| [defamiliarization.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/defamiliarization.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 defamiliarization（目录与文件名推断） | Defamiliarization |
| [derive-and-mapping.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/derive-and-mapping.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 derive-and-mapping（目录与文件名推断） | Dérive and Mapping |
| [first-principles.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/first-principles.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 first-principles（目录与文件名推断） | First Principles |
| [jobs-to-be-done.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/jobs-to-be-done.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 jobs-to-be-done（目录与文件名推断） | Jobs to Be Done |
| [lateral-provocations.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/lateral-provocations.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 lateral-provocations（目录与文件名推断） | Lateral Provocations |
| [leverage-points.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/leverage-points.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 leverage-points（目录与文件名推断） | Leverage Points |
| [oblique-strategies.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/oblique-strategies.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 oblique-strategies（目录与文件名推断） | Oblique Strategies |
| [oulipo.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/oulipo.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 oulipo（目录与文件名推断） | OuLiPo |
| [pataphysics.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/pataphysics.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 pataphysics（目录与文件名推断） | Pataphysics |
| [pattern-languages.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/pattern-languages.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 pattern-languages（目录与文件名推断） | Pattern Languages |
| [polya.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/polya.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 polya（目录与文件名推断） | Pólya's Heuristics |
| [premortem-and-inversion.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/premortem-and-inversion.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 premortem-and-inversion（目录与文件名推断） | Premortem and Inversion |
| [scamper.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/scamper.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 scamper（目录与文件名推断） | SCAMPER |
| [story-skeletons.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/story-skeletons.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 story-skeletons（目录与文件名推断） | Story Skeletons |
| [triz-principles.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/triz-principles.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 triz-principles（目录与文件名推断） | TRIZ — Theory of Inventive Problem Solving |
| [volume-generation.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/creative-ideation/references/methods/volume-generation.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 volume-generation（目录与文件名推断） | Volume Generation |

### backend/hermes/optional-skills/creative/heartmula/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/heartmula/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | HeartMuLa - Open-Source Music Generation |

### backend/hermes/optional-skills/creative/hyperframes/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/hyperframes/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | HyperFrames |

### backend/hermes/optional-skills/creative/hyperframes/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [cli.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/hyperframes/references/cli.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 cli（目录与文件名推断） | HyperFrames CLI |
| [composition.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/hyperframes/references/composition.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 composition（目录与文件名推断） | Composition Authoring |
| [features.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/hyperframes/references/features.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 features（目录与文件名推断） | HyperFrames Feature Reference |
| [gsap.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/hyperframes/references/gsap.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 gsap（目录与文件名推断） | GSAP for HyperFrames |
| [troubleshooting.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/hyperframes/references/troubleshooting.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 troubleshooting（目录与文件名推断） | Troubleshooting |
| [website-to-video.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/hyperframes/references/website-to-video.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 website-to-video（目录与文件名推断） | Website to Video |

### backend/hermes/optional-skills/creative/hyperframes/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [setup.sh](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/hyperframes/scripts/setup.sh>) | 启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/creative/meme-generation/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [EXAMPLES.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/meme-generation/EXAMPLES.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 EXAMPLES（目录与文件名推断） | Meme Generation Examples |
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/meme-generation/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Meme Generation |

### backend/hermes/optional-skills/creative/meme-generation/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [generate_meme.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/meme-generation/scripts/generate_meme.py>) | 内嵌 Hermes 上游源码及项目适配内容中的generate_meme 实现（目录与文件名推断） | Generate a meme image by overlaying text on a template. / 符号 _fetch_url, load_curated_templates, _default_fields, fetch_imgflip_templates, _slugify, resolve_template, get_template_image |
| [templates.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/meme-generation/scripts/templates.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 templates（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/creative/pixel-art/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [ATTRIBUTION.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/pixel-art/ATTRIBUTION.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 ATTRIBUTION（目录与文件名推断） | Attribution |
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/pixel-art/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Pixel Art |

### backend/hermes/optional-skills/creative/pixel-art/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [palettes.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/pixel-art/references/palettes.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 palettes（目录与文件名推断） | Named Palettes |

### backend/hermes/optional-skills/creative/pixel-art/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/pixel-art/scripts/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | 按目录和文件类型定位 |
| [palettes.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/pixel-art/scripts/palettes.py>) | 内嵌 Hermes 上游源码及项目适配内容中的palettes 实现（目录与文件名推断） | Named RGB palettes for pixel_art() and pixel_art_video(). / 符号 build_palette_image |
| [pixel_art.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/pixel-art/scripts/pixel_art.py>) | 内嵌 Hermes 上游源码及项目适配内容中的pixel_art 实现（目录与文件名推断） | Pixel art converter — Floyd-Steinberg dithering with preset or named palette. / 符号 pixel_art, main |
| [pixel_art_video.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/pixel-art/scripts/pixel_art_video.py>) | 内嵌 Hermes 上游源码及项目适配内容中的pixel_art_video 实现（目录与文件名推断） | Pixel art video — overlay procedural animations onto a source image. / 符号 _px, _pixel_cross, init_stars, draw_stars, init_fireflies, draw_fireflies, init_leaves |

### backend/hermes/optional-skills/creative/tldraw-offline/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/tldraw-offline/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | tldraw offline Skill |

### backend/hermes/optional-skills/creative/tldraw-offline/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [counter.js](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/tldraw-offline/scripts/counter.js>) | 内嵌 Hermes 上游源码及项目适配内容中的counter 实现（目录与文件名推断） | 符号 IDS, ensure, STEP, displayShape, setCount, d, runAction |
| [main.js](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/tldraw-offline/scripts/main.js>) | 内嵌 Hermes 上游源码及项目适配内容中的主入口相关实现（目录与文件名推断） | 符号 nodes, n, targetId, update, hasArrows, stop |
| [validate_shapes.mjs](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/tldraw-offline/scripts/validate_shapes.mjs>) | 内嵌 Hermes 上游源码及项目适配内容中的validate_shapes 实现（目录与文件名推断） | 符号 schema, shapeRecord, pageId, COMPLETE, makeRecord, cases, validated |

### backend/hermes/optional-skills/creative/unreal-mcp/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/unreal-mcp/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Unreal Engine MCP Skill |

### backend/hermes/optional-skills/creative/unreal-mcp/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [advanced-workflows.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/unreal-mcp/references/advanced-workflows.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 advanced-workflows（目录与文件名推断） | Advanced workflows (live-verified on UE 5.8) |
| [pitfalls.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/unreal-mcp/references/pitfalls.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 pitfalls（目录与文件名推断） | Unreal MCP — Pitfalls & Lessons |
| [recipes.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/unreal-mcp/references/recipes.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 recipes（目录与文件名推断） | Unreal MCP — Worked Recipes |
| [scene-craft.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/unreal-mcp/references/scene-craft.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 scene-craft（目录与文件名推断） | Unreal MCP — Scene-Craft Cheat Sheet |
| [tool-surface.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/creative/unreal-mcp/references/tool-surface.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 tool-surface（目录与文件名推断） | Unreal MCP — Tool Surface Reference |

### backend/hermes/optional-skills/data-science/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [DESCRIPTION.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/data-science/DESCRIPTION.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 DESCRIPTION（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/data-science/jupyter-notebook/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/data-science/jupyter-notebook/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Jupyter Notebook (hamelnb live kernel) |

### backend/hermes/optional-skills/devops/cli/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/devops/cli/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | inference.sh CLI |

### backend/hermes/optional-skills/devops/cli/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [app-discovery.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/devops/cli/references/app-discovery.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 app-discovery（目录与文件名推断） | Discovering Apps |
| [authentication.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/devops/cli/references/authentication.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 authentication（目录与文件名推断） | Authentication & Setup |
| [cli-reference.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/devops/cli/references/cli-reference.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 cli-reference（目录与文件名推断） | CLI Reference |
| [running-apps.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/devops/cli/references/running-apps.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 running-apps（目录与文件名推断） | Running Apps |

### backend/hermes/optional-skills/devops/docker-management/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/devops/docker-management/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Docker Management |

### backend/hermes/optional-skills/devops/hermes-s6-container-supervision/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/devops/hermes-s6-container-supervision/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Hermes s6-overlay Container Supervision |

### backend/hermes/optional-skills/devops/pinggy-tunnel/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/devops/pinggy-tunnel/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Pinggy Tunnel Skill |

### backend/hermes/optional-skills/devops/watchers/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/devops/watchers/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Watchers |

### backend/hermes/optional-skills/devops/watchers/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [_watermark.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/devops/watchers/scripts/_watermark.py>) | 内嵌 Hermes 上游源码及项目适配内容中的_watermark 实现（目录与文件名推断） | Shared watermark helper used by the three watcher scripts. / 符号 _state_dir, Watermark, format_items_as_markdown |
| [watch_github.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/devops/watchers/scripts/watch_github.py>) | 内嵌 Hermes 上游源码及项目适配内容中的watch_github 实现（目录与文件名推断） | Watch GitHub activity — issues, pulls, releases, or commits — with dedup. / 符号 _flatten_commit, _flatten_issue_or_release, main |
| [watch_http_json.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/devops/watchers/scripts/watch_http_json.py>) | 内嵌 Hermes 上游源码及项目适配内容中的watch_http_json 实现（目录与文件名推断） | Watch any JSON endpoint that returns a list of objects; dedup by ID field. / 符号 _dig, _parse_header, main |
| [watch_rss.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/devops/watchers/scripts/watch_rss.py>) | 内嵌 Hermes 上游源码及项目适配内容中的watch_rss 实现（目录与文件名推断） | Watch an RSS 2.0 or Atom feed; print new items to stdout, silent on empty. / 符号 _strip_ns, _parse_feed, main |

### backend/hermes/optional-skills/dogfood/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [DESCRIPTION.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/dogfood/DESCRIPTION.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 DESCRIPTION（目录与文件名推断） | Dogfood — Advanced QA & Testing Skills |

### backend/hermes/optional-skills/dogfood/adversarial-ux-test/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/dogfood/adversarial-ux-test/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Adversarial UX Test |

### backend/hermes/optional-skills/email/agentmail/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/email/agentmail/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | AgentMail — Agent-Owned Email Inboxes |

### backend/hermes/optional-skills/finance/3-statement-model/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/3-statement-model/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Environment |

### backend/hermes/optional-skills/finance/3-statement-model/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [formatting.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/3-statement-model/references/formatting.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 formatting（目录与文件名推断） | Formatting Standards Reference |
| [formulas.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/3-statement-model/references/formulas.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 formulas（目录与文件名推断） | Formula Reference |
| [sec-filings.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/3-statement-model/references/sec-filings.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 sec-filings（目录与文件名推断） | SEC Filings Data Extraction Reference |

### backend/hermes/optional-skills/finance/comps-analysis/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/comps-analysis/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Environment |

### backend/hermes/optional-skills/finance/dcf-model/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/dcf-model/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Environment |
| [TROUBLESHOOTING.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/dcf-model/TROUBLESHOOTING.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 TROUBLESHOOTING（目录与文件名推断） | DCF Model Troubleshooting Guide |
| [requirements.txt](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/dcf-model/requirements.txt>) | 内嵌 Hermes 上游源码及项目适配内容中的requirements 实现（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/finance/dcf-model/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [validate_dcf.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/dcf-model/scripts/validate_dcf.py>) | 内嵌 Hermes 上游源码及项目适配内容中的validate_dcf 实现（目录与文件名推断） | DCF Model Validation Script / 符号 DCFModelValidator, validate_dcf_model, main |

### backend/hermes/optional-skills/finance/excel-author/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/excel-author/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | excel-author |

### backend/hermes/optional-skills/finance/excel-author/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [recalc.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/excel-author/scripts/recalc.py>) | 内嵌 Hermes 上游源码及项目适配内容中的recalc 实现（目录与文件名推断） | Recalculate an .xlsx file's formulas using LibreOffice headless. / 符号 find_libreoffice, recalc, main |

### backend/hermes/optional-skills/finance/lbo-model/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/lbo-model/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Environment |

### backend/hermes/optional-skills/finance/merger-model/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/merger-model/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Environment |

### backend/hermes/optional-skills/finance/pptx-author/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/pptx-author/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | pptx-author |

### backend/hermes/optional-skills/finance/stocks/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/stocks/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Stocks Skill |

### backend/hermes/optional-skills/finance/stocks/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [stocks_client.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/finance/stocks/scripts/stocks_client.py>) | 内嵌 Hermes 上游源码及项目适配内容中的stocks_client 实现（目录与文件名推断） | stocks_client.py - Stock market data CLI tool for the Hermes Agent project. / 符号 print_json, fmt_price, fmt_large, fmt_pct, safe_get, ts_to_date, _build_request |

### backend/hermes/optional-skills/gaming/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [DESCRIPTION.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/gaming/DESCRIPTION.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 DESCRIPTION（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/gaming/minecraft-modpack-server/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/gaming/minecraft-modpack-server/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Minecraft Modpack Server Setup |

### backend/hermes/optional-skills/gaming/pokemon-player/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/gaming/pokemon-player/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Pokemon Player |

### backend/hermes/optional-skills/health/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [DESCRIPTION.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/health/DESCRIPTION.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 DESCRIPTION（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/health/fitness-nutrition/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/health/fitness-nutrition/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Fitness & Nutrition |

### backend/hermes/optional-skills/health/fitness-nutrition/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [FORMULAS.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/health/fitness-nutrition/references/FORMULAS.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 FORMULAS（目录与文件名推断） | Formulas Reference |

### backend/hermes/optional-skills/health/fitness-nutrition/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [body_calc.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/health/fitness-nutrition/scripts/body_calc.py>) | 内嵌 Hermes 上游源码及项目适配内容中的body_calc 实现（目录与文件名推断） | body_calc.py — All-in-one fitness calculator. / 符号 bmi, tdee, one_rep_max, macros, bodyfat, usage, main |
| [nutrition_search.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/health/fitness-nutrition/scripts/nutrition_search.py>) | 内嵌 Hermes 上游源码及项目适配内容中的搜索相关实现（目录与文件名推断） | nutrition_search.py — Search USDA FoodData Central for nutrition info. / 符号 search, display, main |

### backend/hermes/optional-skills/health/neuroskill-bci/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/health/neuroskill-bci/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | NeuroSkill BCI Integration |

### backend/hermes/optional-skills/health/neuroskill-bci/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [api.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/health/neuroskill-bci/references/api.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 api（目录与文件名推断） | NeuroSkill WebSocket & HTTP API Reference |
| [metrics.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/health/neuroskill-bci/references/metrics.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 metrics（目录与文件名推断） | NeuroSkill Metric Definitions & Interpretation Guide |
| [protocols.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/health/neuroskill-bci/references/protocols.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 protocols（目录与文件名推断） | NeuroSkill Guided Protocols |

### backend/hermes/optional-skills/mcp/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [DESCRIPTION.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mcp/DESCRIPTION.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 DESCRIPTION（目录与文件名推断） | MCP |

### backend/hermes/optional-skills/mcp/fastmcp/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mcp/fastmcp/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | FastMCP |

### backend/hermes/optional-skills/mcp/fastmcp/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [fastmcp-cli.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mcp/fastmcp/references/fastmcp-cli.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 fastmcp-cli（目录与文件名推断） | FastMCP CLI Reference |

### backend/hermes/optional-skills/mcp/fastmcp/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [scaffold_fastmcp.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mcp/fastmcp/scripts/scaffold_fastmcp.py>) | 内嵌 Hermes 上游源码及项目适配内容中的scaffold_fastmcp 实现（目录与文件名推断） | Copy a FastMCP starter template into a working file. / 符号 list_templates, render_template, main |

### backend/hermes/optional-skills/mcp/fastmcp/templates/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [api_wrapper.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mcp/fastmcp/templates/api_wrapper.py>) | 内嵌 Hermes 上游源码及项目适配内容中的api_wrapper 实现（目录与文件名推断） | 符号 _headers, _request, health_check, get_resource, search_resources |
| [database_server.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mcp/fastmcp/templates/database_server.py>) | 内嵌 Hermes 上游源码及项目适配内容中的数据库相关实现（目录与文件名推断） | 符号 _connect, _reject_mutation, _validate_table_name, list_tables, describe_table, query |
| [file_processor.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mcp/fastmcp/templates/file_processor.py>) | 内嵌 Hermes 上游源码及项目适配内容中的文件相关实现（目录与文件名推断） | 符号 _read_text, summarize_text_file, search_text_file, read_file_resource |

### backend/hermes/optional-skills/mcp/mcp-oauth-remote-gateway/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mcp/mcp-oauth-remote-gateway/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | MCP OAuth on a Remote Hermes Gateway |

### backend/hermes/optional-skills/mcp/mcp-oauth-remote-gateway/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [stripe-mcp-oauth-revocation.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mcp/mcp-oauth-remote-gateway/references/stripe-mcp-oauth-revocation.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 stripe-mcp-oauth-revocation（目录与文件名推断） | Stripe MCP ('mcp.stripe.com') — recurring OAuth session revocation, fix with a restricted key |

### backend/hermes/optional-skills/mcp/mcp-oauth-remote-gateway/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [diagnose-oauth-mcp.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mcp/mcp-oauth-remote-gateway/scripts/diagnose-oauth-mcp.py>) | 内嵌 Hermes 上游源码及项目适配内容中的MCP相关实现（目录与文件名推断） | Diagnose an OAuth-gated remote MCP server's connection state. / 符号 _hermes_home, _tokens_dir, _post, _get_json, _mcp_initialize, main |

### backend/hermes/optional-skills/mcp/mcporter/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mcp/mcporter/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | mcporter |

### backend/hermes/optional-skills/migration/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [DESCRIPTION.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/migration/DESCRIPTION.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 DESCRIPTION（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/migration/openclaw-migration/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/migration/openclaw-migration/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | OpenClaw -> Hermes Migration |

### backend/hermes/optional-skills/migration/openclaw-migration/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [openclaw_to_hermes.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/migration/openclaw-migration/scripts/openclaw_to_hermes.py>) | 内嵌 Hermes 上游源码及项目适配内容中的openclaw_to_hermes 实现（目录与文件名推断） | OpenClaw -> Hermes migration helper. / 符号 ItemResult, parse_selection_values, resolve_selected_options, sha256_file, read_text, normalize_text, ensure_parent |

### backend/hermes/optional-skills/mlops/accelerate/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/accelerate/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | HuggingFace Accelerate - Unified Distributed Training |

### backend/hermes/optional-skills/mlops/accelerate/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [custom-plugins.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/accelerate/references/custom-plugins.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 custom-plugins（目录与文件名推断） | Custom Plugins for Accelerate |
| [megatron-integration.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/accelerate/references/megatron-integration.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 megatron-integration（目录与文件名推断） | Megatron Integration with Accelerate |
| [performance.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/accelerate/references/performance.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 performance（目录与文件名推断） | Accelerate Performance Tuning |

### backend/hermes/optional-skills/mlops/chroma/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/chroma/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Chroma - Open-Source Embedding Database |

### backend/hermes/optional-skills/mlops/chroma/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [integration.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/chroma/references/integration.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 integration（目录与文件名推断） | Chroma Integration Guide |

### backend/hermes/optional-skills/mlops/clip/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/clip/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | CLIP - Contrastive Language-Image Pre-Training |

### backend/hermes/optional-skills/mlops/clip/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [applications.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/clip/references/applications.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 applications（目录与文件名推断） | CLIP Applications Guide |

### backend/hermes/optional-skills/mlops/faiss/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/faiss/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | FAISS - Efficient Similarity Search |

### backend/hermes/optional-skills/mlops/faiss/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [index_types.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/faiss/references/index_types.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 index_types（目录与文件名推断） | FAISS Index Types Guide |

### backend/hermes/optional-skills/mlops/flash-attention/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/flash-attention/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Flash Attention - Fast Memory-Efficient Attention |

### backend/hermes/optional-skills/mlops/flash-attention/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [benchmarks.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/flash-attention/references/benchmarks.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 benchmarks（目录与文件名推断） | Performance Benchmarks |
| [transformers-integration.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/flash-attention/references/transformers-integration.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 transformers-integration（目录与文件名推断） | HuggingFace Transformers Integration |

### backend/hermes/optional-skills/mlops/guidance/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/guidance/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Guidance: Constrained LLM Generation |

### backend/hermes/optional-skills/mlops/guidance/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [backends.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/guidance/references/backends.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 backends（目录与文件名推断） | Backend Configuration Guide |
| [constraints.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/guidance/references/constraints.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 constraints（目录与文件名推断） | Comprehensive Constraint Patterns |
| [examples.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/guidance/references/examples.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 examples（目录与文件名推断） | Production-Ready Examples |

### backend/hermes/optional-skills/mlops/huggingface-tokenizers/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/huggingface-tokenizers/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | HuggingFace Tokenizers - Fast Tokenization for NLP |

### backend/hermes/optional-skills/mlops/huggingface-tokenizers/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [algorithms.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/huggingface-tokenizers/references/algorithms.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 algorithms（目录与文件名推断） | Tokenization Algorithms Deep Dive |
| [integration.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/huggingface-tokenizers/references/integration.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 integration（目录与文件名推断） | Transformers Integration |
| [pipeline.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/huggingface-tokenizers/references/pipeline.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 pipeline（目录与文件名推断） | Tokenization Pipeline Components |
| [training.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/huggingface-tokenizers/references/training.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 training（目录与文件名推断） | Training Custom Tokenizers |

### backend/hermes/optional-skills/mlops/inference/outlines/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/inference/outlines/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Outlines: Structured Text Generation |

### backend/hermes/optional-skills/mlops/inference/outlines/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [backends.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/inference/outlines/references/backends.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 backends（目录与文件名推断） | Backend Configuration Guide |
| [examples.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/inference/outlines/references/examples.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 examples（目录与文件名推断） | Production-Ready Examples |
| [json_generation.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/inference/outlines/references/json_generation.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 json_generation（目录与文件名推断） | Comprehensive JSON Generation Guide |

### backend/hermes/optional-skills/mlops/instructor/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/instructor/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Instructor: Structured LLM Outputs |

### backend/hermes/optional-skills/mlops/instructor/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [examples.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/instructor/references/examples.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 examples（目录与文件名推断） | Real-World Examples |
| [providers.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/instructor/references/providers.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 providers（目录与文件名推断） | Provider Configuration |
| [validation.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/instructor/references/validation.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 validation（目录与文件名推断） | Advanced Validation Patterns |

### backend/hermes/optional-skills/mlops/lambda-labs/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/lambda-labs/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Lambda Labs GPU Cloud |

### backend/hermes/optional-skills/mlops/lambda-labs/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [advanced-usage.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/lambda-labs/references/advanced-usage.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 advanced-usage（目录与文件名推断） | Lambda Labs Advanced Usage Guide |
| [troubleshooting.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/lambda-labs/references/troubleshooting.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 troubleshooting（目录与文件名推断） | Lambda Labs Troubleshooting Guide |

### backend/hermes/optional-skills/mlops/llava/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/llava/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | LLaVA - Large Language and Vision Assistant |

### backend/hermes/optional-skills/mlops/llava/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [training.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/llava/references/training.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 training（目录与文件名推断） | LLaVA Training Guide |

### backend/hermes/optional-skills/mlops/modal/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/modal/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Modal Serverless GPU |

### backend/hermes/optional-skills/mlops/modal/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [advanced-usage.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/modal/references/advanced-usage.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 advanced-usage（目录与文件名推断） | Modal Advanced Usage Guide |
| [troubleshooting.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/modal/references/troubleshooting.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 troubleshooting（目录与文件名推断） | Modal Troubleshooting Guide |

### backend/hermes/optional-skills/mlops/models/segment-anything-model/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/models/segment-anything-model/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Segment Anything Model (SAM) |

### backend/hermes/optional-skills/mlops/models/segment-anything-model/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [advanced-usage.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/models/segment-anything-model/references/advanced-usage.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 advanced-usage（目录与文件名推断） | Segment Anything Advanced Usage Guide |
| [troubleshooting.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/models/segment-anything-model/references/troubleshooting.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 troubleshooting（目录与文件名推断） | Segment Anything Troubleshooting Guide |

### backend/hermes/optional-skills/mlops/nemo-curator/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/nemo-curator/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | NeMo Curator - GPU-Accelerated Data Curation |

### backend/hermes/optional-skills/mlops/nemo-curator/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [deduplication.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/nemo-curator/references/deduplication.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 deduplication（目录与文件名推断） | Deduplication Guide |
| [filtering.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/nemo-curator/references/filtering.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 filtering（目录与文件名推断） | Quality Filtering Guide |

### backend/hermes/optional-skills/mlops/obliteratus/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/obliteratus/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | OBLITERATUS Skill |

### backend/hermes/optional-skills/mlops/obliteratus/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [analysis-modules.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/obliteratus/references/analysis-modules.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 analysis-modules（目录与文件名推断） | OBLITERATUS Analysis Modules — Reference |
| [methods-guide.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/obliteratus/references/methods-guide.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 methods-guide（目录与文件名推断） | OBLITERATUS Methods — Detailed Guide |

### backend/hermes/optional-skills/mlops/obliteratus/templates/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [abliteration-config.yaml](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/obliteratus/templates/abliteration-config.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 abliteration-config（目录与文件名推断） | 按目录和文件类型定位 |
| [analysis-study.yaml](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/obliteratus/templates/analysis-study.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 analysis-study（目录与文件名推断） | 按目录和文件类型定位 |
| [batch-abliteration.yaml](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/obliteratus/templates/batch-abliteration.yaml>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 batch-abliteration（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/mlops/peft/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/peft/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | PEFT (Parameter-Efficient Fine-Tuning) |

### backend/hermes/optional-skills/mlops/peft/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [advanced-usage.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/peft/references/advanced-usage.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 advanced-usage（目录与文件名推断） | PEFT Advanced Usage Guide |
| [troubleshooting.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/peft/references/troubleshooting.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 troubleshooting（目录与文件名推断） | PEFT Troubleshooting Guide |

### backend/hermes/optional-skills/mlops/pinecone/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/pinecone/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Pinecone - Managed Vector Database |

### backend/hermes/optional-skills/mlops/pinecone/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [deployment.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/pinecone/references/deployment.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 deployment（目录与文件名推断） | Pinecone Deployment Guide |

### backend/hermes/optional-skills/mlops/pytorch-fsdp/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/pytorch-fsdp/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Pytorch-Fsdp Skill |

### backend/hermes/optional-skills/mlops/pytorch-fsdp/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [index.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/pytorch-fsdp/references/index.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 index（目录与文件名推断） | Pytorch-Fsdp Documentation Index |
| [other.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/pytorch-fsdp/references/other.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 other（目录与文件名推断） | Pytorch-Fsdp - Other |

### backend/hermes/optional-skills/mlops/pytorch-lightning/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/pytorch-lightning/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | PyTorch Lightning - High-Level Training Framework |

### backend/hermes/optional-skills/mlops/pytorch-lightning/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [callbacks.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/pytorch-lightning/references/callbacks.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 callbacks（目录与文件名推断） | PyTorch Lightning Callbacks |
| [distributed.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/pytorch-lightning/references/distributed.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 distributed（目录与文件名推断） | PyTorch Lightning Distributed Training |
| [hyperparameter-tuning.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/pytorch-lightning/references/hyperparameter-tuning.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 hyperparameter-tuning（目录与文件名推断） | Hyperparameter Tuning with PyTorch Lightning |

### backend/hermes/optional-skills/mlops/qdrant/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/qdrant/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Qdrant - Vector Similarity Search Engine |

### backend/hermes/optional-skills/mlops/qdrant/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [advanced-usage.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/qdrant/references/advanced-usage.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 advanced-usage（目录与文件名推断） | Qdrant Advanced Usage Guide |
| [troubleshooting.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/qdrant/references/troubleshooting.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 troubleshooting（目录与文件名推断） | Qdrant Troubleshooting Guide |

### backend/hermes/optional-skills/mlops/research/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [DESCRIPTION.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/research/DESCRIPTION.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 DESCRIPTION（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/mlops/research/dspy/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/research/dspy/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | DSPy: Declarative Language Model Programming |

### backend/hermes/optional-skills/mlops/research/dspy/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [examples.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/research/dspy/references/examples.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 examples（目录与文件名推断） | DSPy Real-World Examples |
| [modules.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/research/dspy/references/modules.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 modules（目录与文件名推断） | DSPy Modules |
| [optimizers.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/research/dspy/references/optimizers.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 optimizers（目录与文件名推断） | DSPy Optimizers (Teleprompters) |

### backend/hermes/optional-skills/mlops/saelens/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/saelens/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | SAELens: Sparse Autoencoders for Mechanistic Interpretability |

### backend/hermes/optional-skills/mlops/saelens/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [README.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/saelens/references/README.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 README（目录与文件名推断） | SAELens Reference Documentation |
| [api.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/saelens/references/api.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 api（目录与文件名推断） | SAELens API Reference |
| [tutorials.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/saelens/references/tutorials.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 tutorials（目录与文件名推断） | SAELens Tutorials |

### backend/hermes/optional-skills/mlops/simpo/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/simpo/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | SimPO - Simple Preference Optimization |

### backend/hermes/optional-skills/mlops/simpo/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [datasets.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/simpo/references/datasets.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 datasets（目录与文件名推断） | Datasets |
| [hyperparameters.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/simpo/references/hyperparameters.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 hyperparameters（目录与文件名推断） | Hyperparameters |
| [loss-functions.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/simpo/references/loss-functions.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 loss-functions（目录与文件名推断） | Loss Functions |

### backend/hermes/optional-skills/mlops/slime/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/slime/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | slime: LLM Post-Training Framework for RL Scaling |

### backend/hermes/optional-skills/mlops/slime/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [api-reference.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/slime/references/api-reference.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 api-reference（目录与文件名推断） | slime API Reference |
| [troubleshooting.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/slime/references/troubleshooting.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 troubleshooting（目录与文件名推断） | slime Troubleshooting Guide |

### backend/hermes/optional-skills/mlops/stable-diffusion/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/stable-diffusion/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Stable Diffusion Image Generation |

### backend/hermes/optional-skills/mlops/stable-diffusion/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [advanced-usage.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/stable-diffusion/references/advanced-usage.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 advanced-usage（目录与文件名推断） | Stable Diffusion Advanced Usage Guide |
| [troubleshooting.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/stable-diffusion/references/troubleshooting.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 troubleshooting（目录与文件名推断） | Stable Diffusion Troubleshooting Guide |

### backend/hermes/optional-skills/mlops/tensorrt-llm/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/tensorrt-llm/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | TensorRT-LLM |

### backend/hermes/optional-skills/mlops/tensorrt-llm/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [multi-gpu.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/tensorrt-llm/references/multi-gpu.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 multi-gpu（目录与文件名推断） | Multi-GPU Deployment Guide |
| [optimization.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/tensorrt-llm/references/optimization.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 optimization（目录与文件名推断） | TensorRT-LLM Optimization Guide |
| [serving.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/tensorrt-llm/references/serving.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 serving（目录与文件名推断） | Production Serving Guide |

### backend/hermes/optional-skills/mlops/torchtitan/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/torchtitan/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | TorchTitan - PyTorch Native Distributed LLM Pretraining |

### backend/hermes/optional-skills/mlops/torchtitan/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [checkpoint.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/torchtitan/references/checkpoint.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 checkpoint（目录与文件名推断） | Checkpointing in TorchTitan |
| [custom-models.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/torchtitan/references/custom-models.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 custom-models（目录与文件名推断） | Adding Custom Models to TorchTitan |
| [float8.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/torchtitan/references/float8.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 float8（目录与文件名推断） | Float8 Training in TorchTitan |
| [fsdp.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/torchtitan/references/fsdp.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 fsdp（目录与文件名推断） | FSDP2 in TorchTitan |

### backend/hermes/optional-skills/mlops/training/axolotl/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/axolotl/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Axolotl Skill |

### backend/hermes/optional-skills/mlops/training/axolotl/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [api.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/axolotl/references/api.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 api（目录与文件名推断） | Axolotl - Api |
| [dataset-formats.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/axolotl/references/dataset-formats.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 dataset-formats（目录与文件名推断） | Axolotl - Dataset-Formats |
| [index.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/axolotl/references/index.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 index（目录与文件名推断） | Axolotl Documentation Index |
| [other.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/axolotl/references/other.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 other（目录与文件名推断） | Axolotl - Other |

### backend/hermes/optional-skills/mlops/training/trl-fine-tuning/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/trl-fine-tuning/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | TRL - Transformer Reinforcement Learning |

### backend/hermes/optional-skills/mlops/training/trl-fine-tuning/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [dpo-variants.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/trl-fine-tuning/references/dpo-variants.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 dpo-variants（目录与文件名推断） | DPO Variants |
| [grpo-training.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/trl-fine-tuning/references/grpo-training.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 grpo-training（目录与文件名推断） | GRPO (Group Relative Policy Optimization) — Deep Guide |
| [online-rl.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/trl-fine-tuning/references/online-rl.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 online-rl（目录与文件名推断） | Online RL Methods |
| [reward-modeling.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/trl-fine-tuning/references/reward-modeling.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 reward-modeling（目录与文件名推断） | Reward Modeling |
| [sft-training.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/trl-fine-tuning/references/sft-training.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 sft-training（目录与文件名推断） | SFT Training Guide |

### backend/hermes/optional-skills/mlops/training/trl-fine-tuning/templates/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [basic_grpo_training.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/trl-fine-tuning/templates/basic_grpo_training.py>) | 内嵌 Hermes 上游源码及项目适配内容中的basic_grpo_training 实现（目录与文件名推断） | Basic GRPO Training Template / 符号 get_dataset, extract_xml_tag, extract_answer, correctness_reward_func, format_reward_func, incremental_format_reward_func, setup_model_and_tokenizer |

### backend/hermes/optional-skills/mlops/training/unsloth/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/unsloth/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Unsloth Skill |

### backend/hermes/optional-skills/mlops/training/unsloth/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [index.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/unsloth/references/index.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 index（目录与文件名推断） | Unsloth Documentation Index |
| [llms-full.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/unsloth/references/llms-full.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 llms-full（目录与文件名推断） | Unsloth Docs |
| [llms-txt.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/unsloth/references/llms-txt.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 llms-txt（目录与文件名推断） | Unsloth - Llms-Txt |
| [llms.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/training/unsloth/references/llms.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 llms（目录与文件名推断） | Unsloth Documentation |

### backend/hermes/optional-skills/mlops/whisper/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/whisper/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Whisper - Robust Speech Recognition |

### backend/hermes/optional-skills/mlops/whisper/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [languages.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/mlops/whisper/references/languages.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 languages（目录与文件名推断） | Whisper Language Support Guide |

### backend/hermes/optional-skills/payments/mpp-agent/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/payments/mpp-agent/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | MPP Agent Skill |

### backend/hermes/optional-skills/payments/stripe-link-cli/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/payments/stripe-link-cli/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Stripe Link CLI Skill |

### backend/hermes/optional-skills/payments/stripe-projects/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/payments/stripe-projects/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Stripe Projects Skill |

### backend/hermes/optional-skills/productivity/canvas/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/canvas/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Canvas LMS — Course & Assignment Access |

### backend/hermes/optional-skills/productivity/canvas/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [canvas_api.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/canvas/scripts/canvas_api.py>) | 内嵌 Hermes 上游源码及项目适配内容中的canvas_api 实现（目录与文件名推断） | Canvas LMS API CLI for Hermes Agent. / 符号 _check_config, _headers, _paginated_get, list_courses, list_assignments, main |

### backend/hermes/optional-skills/productivity/here-now/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/here-now/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | here.now |

### backend/hermes/optional-skills/productivity/here-now/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [drive.sh](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/here-now/scripts/drive.sh>) | 启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |
| [publish.sh](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/here-now/scripts/publish.sh>) | 启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/productivity/memento-flashcards/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/memento-flashcards/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Memento Flashcards — Spaced-Repetition Flashcard Skill |

### backend/hermes/optional-skills/productivity/memento-flashcards/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [memento_cards.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/memento-flashcards/scripts/memento_cards.py>) | 内嵌 Hermes 上游源码及项目适配内容中的memento_cards 实现（目录与文件名推断） | Memento card storage, spaced-repetition engine, and CSV I/O. / 符号 _now, _iso, _parse_iso, _empty_store, _load, _save, _out |
| [youtube_quiz.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/memento-flashcards/scripts/youtube_quiz.py>) | 内嵌 Hermes 上游源码及项目适配内容中的youtube_quiz 实现（目录与文件名推断） | Fetch YouTube transcripts for Memento quiz generation. / 符号 _out, _normalize_segments, cmd_fetch, main |

### backend/hermes/optional-skills/productivity/shop/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/shop/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Shop CLI Skill |

### backend/hermes/optional-skills/productivity/shop/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [catalog-mcp.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/shop/references/catalog-mcp.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 catalog-mcp（目录与文件名推断） | Direct Global Catalog MCP |
| [direct-api.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/shop/references/direct-api.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 direct-api（目录与文件名推断） | Direct Auth, Checkout, And Orders API |
| [legal.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/shop/references/legal.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 legal（目录与文件名推断） | Legal |
| [safety.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/shop/references/safety.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 safety（目录与文件名推断） | Safety, Security, And Legal |

### backend/hermes/optional-skills/productivity/shopify/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/shopify/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Shopify — Admin & Storefront GraphQL APIs |

### backend/hermes/optional-skills/productivity/siyuan/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/siyuan/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | SiYuan Note API |

### backend/hermes/optional-skills/productivity/telephony/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/telephony/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Telephony — Numbers, Calls, and Texts without Core Tool Changes |

### backend/hermes/optional-skills/productivity/telephony/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [telephony.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/productivity/telephony/scripts/telephony.py>) | 内嵌 Hermes 上游源码及项目适配内容中的telephony 实现（目录与文件名推断） | Telephony helper for the Hermes optional telephony skill. / 符号 TelephonyError, OwnedTwilioNumber, _hermes_home, _env_path, _config_path, _state_path, _load_root_config |

### backend/hermes/optional-skills/research/bioinformatics/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/bioinformatics/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Bioinformatics Skills Gateway |

### backend/hermes/optional-skills/research/darwinian-evolver/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/darwinian-evolver/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Darwinian Evolver |

### backend/hermes/optional-skills/research/darwinian-evolver/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [parrot_openrouter.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/darwinian-evolver/scripts/parrot_openrouter.py>) | 内嵌 Hermes 上游源码及项目适配内容中的parrot_openrouter 实现（目录与文件名推断） | parrot_openrouter: same as the upstream 'parrot' example but the LLM call goes / 符号 _client, _prompt_llm, ParrotOrganism, ParrotEvaluationFailureCase, ImproveParrotMutator, ParrotEvaluator, make_problem |
| [show_snapshot.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/darwinian-evolver/scripts/show_snapshot.py>) | 内嵌 Hermes 上游源码及项目适配内容中的show_snapshot 实现（目录与文件名推断） | show_snapshot.py — Dump the population from a darwinian-evolver snapshot pickle. / 符号 main |

### backend/hermes/optional-skills/research/darwinian-evolver/templates/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [custom_problem_template.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/darwinian-evolver/templates/custom_problem_template.py>) | 内嵌 Hermes 上游源码及项目适配内容中的custom_problem_template 实现（目录与文件名推断） | Template: a custom darwinian-evolver problem. / 符号 _client, _prompt_llm, MyOrganism, MyFailureCase, MyEvaluator, MyMutator, make_problem |

### backend/hermes/optional-skills/research/domain-intel/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/domain-intel/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Domain Intelligence — Passive OSINT |

### backend/hermes/optional-skills/research/domain-intel/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [domain_intel.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/domain-intel/scripts/domain_intel.py>) | 内嵌 Hermes 上游源码及项目适配内容中的domain_intel 实现（目录与文件名推断） | Domain Intelligence — Passive OSINT via Python stdlib. / 符号 subdomains, check_ssl, whois_lookup, dns_records, check_available, bulk_check, main |

### backend/hermes/optional-skills/research/drug-discovery/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/drug-discovery/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Drug Discovery & Pharmaceutical Research |

### backend/hermes/optional-skills/research/drug-discovery/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [ADMET_REFERENCE.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/drug-discovery/references/ADMET_REFERENCE.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 ADMET_REFERENCE（目录与文件名推断） | ADMET Reference Guide |

### backend/hermes/optional-skills/research/drug-discovery/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [chembl_target.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/drug-discovery/scripts/chembl_target.py>) | 内嵌 Hermes 上游源码及项目适配内容中的chembl_target 实现（目录与文件名推断） | chembl_target.py — Search ChEMBL for a target and retrieve top active compounds. / 符号 get, main |
| [ro5_screen.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/drug-discovery/scripts/ro5_screen.py>) | 内嵌 Hermes 上游源码及项目适配内容中的ro5_screen 实现（目录与文件名推断） | ro5_screen.py — Batch Lipinski Ro5 + Veber screening via PubChem API. / 符号 fetch, check, report, main |

### backend/hermes/optional-skills/research/duckduckgo-search/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/duckduckgo-search/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | DuckDuckGo Search |

### backend/hermes/optional-skills/research/duckduckgo-search/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [duckduckgo.sh](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/duckduckgo-search/scripts/duckduckgo.sh>) | 启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/research/gitnexus-explorer/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/gitnexus-explorer/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | GitNexus Explorer |

### backend/hermes/optional-skills/research/gitnexus-explorer/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [proxy.mjs](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/gitnexus-explorer/scripts/proxy.mjs>) | 内嵌 Hermes 上游源码及项目适配内容中的proxy 实现（目录与文件名推断） | 符号 API_PORT, DIST_DIR, PORT, MIME, proxyToApi, opts, proxy |

### backend/hermes/optional-skills/research/osint-investigation/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | OSINT Investigation — Public Records Cross-Reference |

### backend/hermes/optional-skills/research/osint-investigation/references/sources/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [courtlistener.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/references/sources/courtlistener.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 courtlistener（目录与文件名推断） | CourtListener — Free Law Project |
| [gdelt.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/references/sources/gdelt.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 gdelt（目录与文件名推断） | GDELT — Global News Monitoring |
| [icij-offshore.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/references/sources/icij-offshore.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 icij-offshore（目录与文件名推断） | ICIJ Offshore Leaks Database |
| [nyc-acris.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/references/sources/nyc-acris.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 nyc-acris（目录与文件名推断） | NYC ACRIS — NYC Real Property Records |
| [ofac-sdn.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/references/sources/ofac-sdn.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 ofac-sdn（目录与文件名推断） | OFAC SDN — Specially Designated Nationals List |
| [opencorporates.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/references/sources/opencorporates.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 opencorporates（目录与文件名推断） | OpenCorporates — Global Corporate Registry |
| [sec-edgar.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/references/sources/sec-edgar.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 sec-edgar（目录与文件名推断） | SEC EDGAR — Corporate Filings |
| [senate-ld.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/references/sources/senate-ld.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 senate-ld（目录与文件名推断） | Senate LD — Lobbying Disclosure (LD-1 / LD-2) |
| [usaspending.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/references/sources/usaspending.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 usaspending（目录与文件名推断） | USAspending — Federal Government Contracts and Grants |
| [wayback.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/references/sources/wayback.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 wayback（目录与文件名推断） | Wayback Machine — Internet Archive CDX |
| [wikipedia.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/references/sources/wikipedia.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 wikipedia（目录与文件名推断） | Wikipedia + Wikidata |

### backend/hermes/optional-skills/research/osint-investigation/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [_http.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/_http.py>) | 内嵌 Hermes 上游源码及项目适配内容中的_http 实现（目录与文件名推断） | Tiny stdlib HTTP helper used by fetch_*.py scripts. / 符号 get, get_json |
| [_normalize.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/_normalize.py>) | 内嵌 Hermes 上游源码及项目适配内容中的_normalize 实现（目录与文件名推断） | Shared entity-name normalization helpers (stdlib-only). / 符号 normalize_name, normalize_aggressive, name_tokens, token_overlap_ratio |
| [build_findings.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/build_findings.py>) | 内嵌 Hermes 上游源码及项目适配内容中的build_findings 实现（目录与文件名推断） | Build a structured findings.json with evidence chains (stdlib-only). / 符号 _read_cross_links, build_findings, main |
| [entity_resolution.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/entity_resolution.py>) | 内嵌 Hermes 上游源码及项目适配内容中的entity_resolution 实现（目录与文件名推断） | Cross-source entity resolution (stdlib-only). / 符号 _read_csv, _build_index, _emit, resolve, main |
| [fetch_courtlistener.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/fetch_courtlistener.py>) | 内嵌 Hermes 上游源码及项目适配内容中的fetch_courtlistener 实现（目录与文件名推断） | Search court records via CourtListener (Free Law Project). / 符号 fetch, main |
| [fetch_gdelt.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/fetch_gdelt.py>) | 内嵌 Hermes 上游源码及项目适配内容中的fetch_gdelt 实现（目录与文件名推断） | Search the GDELT 2.0 DOC API for news mentions. / 符号 fetch, main |
| [fetch_icij_offshore.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/fetch_icij_offshore.py>) | 内嵌 Hermes 上游源码及项目适配内容中的fetch_icij_offshore 实现（目录与文件名推断） | Search ICIJ Offshore Leaks via the bulk CSV database. / 符号 _cache_dir, _download, _open_csv, _match, _normalize_query, fetch, main |
| [fetch_nyc_acris.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/fetch_nyc_acris.py>) | 内嵌 Hermes 上游源码及项目适配内容中的fetch_nyc_acris 实现（目录与文件名推断） | Search NYC property records via ACRIS (Automated City Register Information System). / 符号 _filing_url, fetch, main |
| [fetch_ofac_sdn.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/fetch_ofac_sdn.py>) | 内嵌 Hermes 上游源码及项目适配内容中的fetch_ofac_sdn 实现（目录与文件名推断） | Fetch OFAC SDN list (CSV format) and normalize. / 符号 _read_csv, _strip_quotes, fetch, main |
| [fetch_opencorporates.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/fetch_opencorporates.py>) | 内嵌 Hermes 上游源码及项目适配内容中的fetch_opencorporates 实现（目录与文件名推断） | Search OpenCorporates company registry data. / 符号 _via_api, _via_html, fetch, main |
| [fetch_sec_edgar.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/fetch_sec_edgar.py>) | 内嵌 Hermes 上游源码及项目适配内容中的fetch_sec_edgar 实现（目录与文件名推断） | Fetch SEC EDGAR filings index for a given CIK or company name. / 符号 _ua, _resolve_cik, fetch, main |
| [fetch_senate_ld.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/fetch_senate_ld.py>) | 内嵌 Hermes 上游源码及项目适配内容中的fetch_senate_ld 实现（目录与文件名推断） | Fetch Senate Lobbying Disclosure (LD-1 / LD-2) filings. / 符号 fetch, main |
| [fetch_usaspending.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/fetch_usaspending.py>) | 内嵌 Hermes 上游源码及项目适配内容中的fetch_usaspending 实现（目录与文件名推断） | Fetch federal contracts/awards from USAspending.gov API v2. / 符号 _post, fetch, main |
| [fetch_wayback.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/fetch_wayback.py>) | 内嵌 Hermes 上游源码及项目适配内容中的fetch_wayback 实现（目录与文件名推断） | Search the Internet Archive Wayback Machine via the CDX server. / 符号 fetch, main |
| [fetch_wikipedia.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/fetch_wikipedia.py>) | 内嵌 Hermes 上游源码及项目适配内容中的fetch_wikipedia 实现（目录与文件名推断） | Search Wikipedia + Wikidata for an entity (person, company, place, concept). / 符号 _wp_search, _wp_summary, _wd_lookup_by_qid, _wd_qid_for_title, fetch, main |
| [timing_analysis.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/scripts/timing_analysis.py>) | 内嵌 Hermes 上游源码及项目适配内容中的timing_analysis 实现（目录与文件名推断） | Permutation test for donation/contract timing correlation (stdlib-only). / 符号 parse_date, _read, _nearest_distance, _permute, analyze, main |

### backend/hermes/optional-skills/research/osint-investigation/templates/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [source-template.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/osint-investigation/templates/source-template.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 source-template（目录与文件名推断） | <Source Name> |

### backend/hermes/optional-skills/research/parallel-cli/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/parallel-cli/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Parallel CLI |

### backend/hermes/optional-skills/research/pinecone-research/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/pinecone-research/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Pinecone Research — Agent RAG & Long-Term Memory |

### backend/hermes/optional-skills/research/pinecone-research/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [memory_manager.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/pinecone-research/scripts/memory_manager.py>) | 内嵌 Hermes 上游源码及项目适配内容中的记忆相关实现（目录与文件名推断） | Pinecone memory manager — namespace-based session memory for agents. / 符号 get_pinecone_client, get_embeddings, store_memory, recall_memories, cleanup_session, show_stats, main |
| [rag_pipeline.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/pinecone-research/scripts/rag_pipeline.py>) | 内嵌 Hermes 上游源码及项目适配内容中的rag_pipeline 实现（目录与文件名推断） | Pinecone RAG pipeline — index documents and query with retrieval-augmented generation. / 符号 get_pinecone_client, ensure_index, load_documents, index_documents, query_index, main |

### backend/hermes/optional-skills/research/qmd/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/qmd/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | QMD — Query Markup Documents |

### backend/hermes/optional-skills/research/scrapling/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/scrapling/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Scrapling |

### backend/hermes/optional-skills/research/searxng-search/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/searxng-search/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | SearXNG Search |

### backend/hermes/optional-skills/research/searxng-search/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [searxng.sh](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/research/searxng-search/scripts/searxng.sh>) | 启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/security/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [DESCRIPTION.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/DESCRIPTION.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 DESCRIPTION（目录与文件名推断） | Security |

### backend/hermes/optional-skills/security/1password/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/1password/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | 1Password CLI |

### backend/hermes/optional-skills/security/1password/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [cli-examples.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/1password/references/cli-examples.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 cli-examples（目录与文件名推断） | op CLI examples |
| [get-started.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/1password/references/get-started.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 get-started（目录与文件名推断） | 1Password CLI get-started (summary) |

### backend/hermes/optional-skills/security/godmode/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/godmode/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | G0DM0D3 Jailbreaking Skill |

### backend/hermes/optional-skills/security/godmode/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [jailbreak-templates.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/godmode/references/jailbreak-templates.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 jailbreak-templates（目录与文件名推断） | GODMODE CLASSIC — Jailbreak System Prompt Templates |
| [refusal-detection.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/godmode/references/refusal-detection.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 refusal-detection（目录与文件名推断） | Refusal Detection & Response Scoring |

### backend/hermes/optional-skills/security/godmode/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [auto_jailbreak.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/godmode/scripts/auto_jailbreak.py>) | 内嵌 Hermes 上游源码及项目适配内容中的auto_jailbreak 实现（目录与文件名推断） | Auto-Jailbreak Pipeline / 符号 _detect_model_family, _get_current_model, _get_api_key, _test_query, _build_messages, _write_config, _write_prefill |
| [godmode_race.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/godmode/scripts/godmode_race.py>) | 内嵌 Hermes 上游源码及项目适配内容中的godmode_race 实现（目录与文件名推断） | ULTRAPLINIAN Multi-Model Racing Engine / 符号 is_refusal, count_hedges, score_response, _query_model, race_models, race_godmode_classic |
| [load_godmode.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/godmode/scripts/load_godmode.py>) | 内嵌 Hermes 上游源码及项目适配内容中的load_godmode 实现（目录与文件名推断） | Loader for G0DM0D3 scripts. Handles the exec-scoping issues. / 符号 _gm_load |
| [parseltongue.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/godmode/scripts/parseltongue.py>) | 内嵌 Hermes 上游源码及项目适配内容中的parseltongue 实现（目录与文件名推断） | Parseltongue v4 — Input Obfuscation Engine / 符号 _apply_raw, _apply_leetspeak, _apply_unicode, _apply_bubble, _apply_spaced, _apply_fullwidth, _apply_zwj |

### backend/hermes/optional-skills/security/godmode/templates/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [prefill-subtle.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/godmode/templates/prefill-subtle.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 prefill-subtle（目录与文件名推断） | 按目录和文件类型定位 |
| [prefill.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/godmode/templates/prefill.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 prefill（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/security/oss-forensics/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/oss-forensics/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | OSS Security Forensics Skill |

### backend/hermes/optional-skills/security/oss-forensics/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [evidence-types.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/oss-forensics/references/evidence-types.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 evidence-types（目录与文件名推断） | Evidence Types Reference |
| [github-archive-guide.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/oss-forensics/references/github-archive-guide.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 github-archive-guide（目录与文件名推断） | GitHub Archive Query Guide (BigQuery) |
| [investigation-templates.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/oss-forensics/references/investigation-templates.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 investigation-templates（目录与文件名推断） | Investigation Templates |
| [recovery-techniques.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/oss-forensics/references/recovery-techniques.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 recovery-techniques（目录与文件名推断） | Deleted Content Recovery Techniques |

### backend/hermes/optional-skills/security/oss-forensics/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [evidence-store.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/oss-forensics/scripts/evidence-store.py>) | 内嵌 Hermes 上游源码及项目适配内容中的evidence-store 实现（目录与文件名推断） | OSS Forensics Evidence Store Manager / 符号 _now_iso, _sha256, EvidenceStore, main |

### backend/hermes/optional-skills/security/oss-forensics/templates/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [forensic-report.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/oss-forensics/templates/forensic-report.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 forensic-report（目录与文件名推断） | Forensic Investigation Report |
| [malicious-package-report.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/oss-forensics/templates/malicious-package-report.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 malicious-package-report（目录与文件名推断） | Malicious Package Investigation Report |

### backend/hermes/optional-skills/security/sherlock/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/sherlock/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Sherlock OSINT Username Search |

### backend/hermes/optional-skills/security/unbroker/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [README.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/README.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 README（目录与文件名推断） | unbroker |
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | unbroker |

### backend/hermes/optional-skills/security/unbroker/assets/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [unbroker.png](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/assets/unbroker.png>) | 内嵌 Hermes 上游源码及项目适配内容使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/security/unbroker/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [methods.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/methods.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 methods（目录与文件名推断） | Opt-out method playbooks |
| [site-playbooks.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/site-playbooks.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 site-playbooks（目录与文件名推断） | Per-site playbooks (pre-recorded game plans) |
| [state-machine.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/state-machine.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 state-machine（目录与文件名推断） | Case state machine |

### backend/hermes/optional-skills/security/unbroker/references/brokers/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [addresses.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/addresses.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 addresses（目录与文件名推断） | 按目录和文件类型定位 |
| [advancedbackgroundchecks.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/advancedbackgroundchecks.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 advancedbackgroundchecks（目录与文件名推断） | 按目录和文件类型定位 |
| [beenverified.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/beenverified.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 beenverified（目录与文件名推断） | 按目录和文件类型定位 |
| [clustal.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/clustal.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 clustal（目录与文件名推断） | 按目录和文件类型定位 |
| [clustrmaps.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/clustrmaps.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 clustrmaps（目录与文件名推断） | 按目录和文件类型定位 |
| [cyberbackgroundchecks.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/cyberbackgroundchecks.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 cyberbackgroundchecks（目录与文件名推断） | 按目录和文件类型定位 |
| [familytreenow.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/familytreenow.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 familytreenow（目录与文件名推断） | 按目录和文件类型定位 |
| [fastpeoplesearch.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/fastpeoplesearch.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 fastpeoplesearch（目录与文件名推断） | 按目录和文件类型定位 |
| [intelius.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/intelius.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 intelius（目录与文件名推断） | 按目录和文件类型定位 |
| [mylife.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/mylife.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 mylife（目录与文件名推断） | 按目录和文件类型定位 |
| [nuwber.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/nuwber.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 nuwber（目录与文件名推断） | 按目录和文件类型定位 |
| [peekyou.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/peekyou.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 peekyou（目录与文件名推断） | 按目录和文件类型定位 |
| [peoplefinders.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/peoplefinders.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 peoplefinders（目录与文件名推断） | 按目录和文件类型定位 |
| [radaris.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/radaris.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 radaris（目录与文件名推断） | 按目录和文件类型定位 |
| [rehold.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/rehold.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 rehold（目录与文件名推断） | 按目录和文件类型定位 |
| [searchpeoplefree.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/searchpeoplefree.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 searchpeoplefree（目录与文件名推断） | 按目录和文件类型定位 |
| [socialcatfish.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/socialcatfish.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 socialcatfish（目录与文件名推断） | 按目录和文件类型定位 |
| [spokeo.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/spokeo.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 spokeo（目录与文件名推断） | 按目录和文件类型定位 |
| [thatsthem.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/thatsthem.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 thatsthem（目录与文件名推断） | 按目录和文件类型定位 |
| [truepeoplesearch.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/truepeoplesearch.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 truepeoplesearch（目录与文件名推断） | 按目录和文件类型定位 |
| [usphonebook.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/usphonebook.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 usphonebook（目录与文件名推断） | 按目录和文件类型定位 |
| [whitepages.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/brokers/whitepages.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 whitepages（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/security/unbroker/references/legal/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [ccpa.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/legal/ccpa.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 ccpa（目录与文件名推断） | CCPA / CPRA (California) |
| [drop.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/legal/drop.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 drop（目录与文件名推断） | California DROP portal (highest-leverage lever) |
| [gdpr.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/references/legal/gdpr.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 gdpr（目录与文件名推断） | GDPR / UK-GDPR (roadmap - Phase 3) |

### backend/hermes/optional-skills/security/unbroker/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [autopilot.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/autopilot.py>) | 内嵌 Hermes 上游源码及项目适配内容中的autopilot 实现（目录与文件名推断） | Autonomous action queue: what should the agent do RIGHT NOW for this subject? / 符号 cache_age_days, _now_iso, _min_future_recheck, _digest, request_kind, _email_lane, _optout_action |
| [badbool.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/badbool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的badbool 实现（目录与文件名推断） | Pull and parse the Big-Ass Data Broker Opt-Out List (BADBOOL) into broker records. / 符号 slug, _heading_flags, _priority, _pick, _clean, _build, parse |
| [brokers.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/brokers.py>) | 内嵌 Hermes 上游源码及项目适配内容中的brokers 实现（目录与文件名推断） | Load and query the broker database (references/brokers/*.json). / 符号 _load_curated, load_live_cache, load_registry_cache, load_all, get, by_priority, clusters |
| [cdp.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/cdp.py>) | 内嵌 Hermes 上游源码及项目适配内容中的cdp 实现（目录与文件名推断） | Launch (or detect) the operator's local Chrome/Chromium over the DevTools Protocol (CDP). / 符号 default_profile, _mac_candidates, _windows_candidates, find_browser, launch_command, _http_get, endpoint_status |
| [config.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/config.py>) | 内嵌 Hermes 上游源码及项目适配内容中的配置相关实现（目录与文件名推断） | Install-wide configuration with easiest-first defaults. / 符号 load_config, save_config, dotenv_env, detect_capabilities, auto_configure, browser_clears_captcha |
| [crypto.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/crypto.py>) | 内嵌 Hermes 上游源码及项目适配内容中的crypto 实现（目录与文件名推断） | At-rest encryption for sensitive files via the 'age' binary (optional). / 符号 age_available, encryption_setting, identity_path, ensure_identity, recipient, is_engaged, encrypt |
| [dossier.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/dossier.py>) | 内嵌 Hermes 上游源码及项目适配内容中的dossier 实现（目录与文件名推断） | Subject dossier management + consent gate + least-disclosure field selection. / 符号 now, new_subject_id, create, load, save, is_authorized, require_authorized |
| [email_modes.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/email_modes.py>) | 内嵌 Hermes 上游源码及项目适配内容中的email_modes 实现（目录与文件名推断） | Email modes A/B/C helpers + anti-phishing verification-link extraction. / 符号 render_draft, render_request_draft, extract_verification_link |
| [emailer.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/emailer.py>) | 内嵌 Hermes 上游源码及项目适配内容中的emailer 实现（目录与文件名推断） | Programmatic email (Mode B) via stdlib smtplib/imaplib - no human in the loop. / 符号 _domain, smtp_settings, imap_settings, available, broker_addresses, _split_subject_body, browser_send_payload |
| [ledger.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/ledger.py>) | 内嵌 Hermes 上游源码及项目适配内容中的ledger 实现（目录与文件名推断） | Case ledger: opt-out state machine + append-only audit log. / 符号 now, load, save, new_case, get_case, can_transition, transition |
| [legal.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/legal.py>) | 内嵌 Hermes 上游源码及项目适配内容中的legal 实现（目录与文件名推断） | Render opt-out / legal request text from templates/ with safe substitution. / 符号 _SafeDict, template_path, render, _join_listings, _join_identifiers, render_optout_email, render_request |
| [paths.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/paths.py>) | 内嵌 Hermes 上游源码及项目适配内容中的paths 实现（目录与文件名推断） | Filesystem paths for the unbroker skill (stdlib only). / 符号 hermes_home, data_dir, config_path, subjects_dir, subject_dir, dossier_path, ledger_path |
| [pdd.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/pdd.py>) | 内嵌 Hermes 上游源码及项目适配内容中的pdd 实现（目录与文件名推断） | unbroker - deterministic CLI helper. / 符号 _out, _require_subject, cmd_setup, _migrate_subjects, _check_writable, cmd_doctor, cmd_cdp |
| [registry.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/registry.py>) | 内嵌 Hermes 上游源码及项目适配内容中的注册表相关实现（目录与文件名推断） | Ingest the California Data Broker Registry into broker records (coverage breadth). / 符号 ca_candidate_urls, portals, _norm, slug, _domain, _find_colmap, _get |
| [report.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/report.py>) | 内嵌 Hermes 上游源码及项目适配内容中的报告相关实现（目录与文件名推断） | Status dashboards, Markdown reports, human-task digest, and Google Sheets row export. / 符号 status_counts, metrics, render_markdown, human_tasks_markdown, sheets_rows |
| [scan.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/scan.py>) | 内嵌 Hermes 上游源码及项目适配内容中的scan 实现（目录与文件名推断） | Stdlib fetch helper for simple url_pattern brokers (osint-style). / 符号 fetch, looks_listed |
| [storage.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/storage.py>) | 内嵌 Hermes 上游源码及项目适配内容中的storage 实现（目录与文件名推断） | Storage helpers (stdlib only): atomic JSON, append-only JSONL, strict perms. / 符号 locked, _secure, ensure_dir, _is_sensitive, _age_path, _atomic_write, write_json |
| [tiers.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/tiers.py>) | 内嵌 Hermes 上游源码及项目适配内容中的tiers 实现（目录与文件名推断） | Automation-tier selection and per-subject action planning. / 符号 select_tier, plan, fanout, batch_plan, synthesize_steps, _parent_playbook, _batch_next |
| [vectors.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/scripts/vectors.py>) | 内嵌 Hermes 上游源码及项目适配内容中的vectors 实现（目录与文件名推断） | Enumerate the search queries to run per broker, across ALL of a subject's identifiers. / 符号 supported_by, search_vectors |

### backend/hermes/optional-skills/security/unbroker/templates/consent/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [authorization.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/templates/consent/authorization.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 authorization（目录与文件名推断） | Authorization to act on my behalf (data removal) |

### backend/hermes/optional-skills/security/unbroker/templates/emails/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [ccpa-authorized-agent.txt](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/templates/emails/ccpa-authorized-agent.txt>) | 内嵌 Hermes 上游源码及项目适配内容中的代理相关实现（目录与文件名推断） | 按目录和文件类型定位 |
| [ccpa-deletion.txt](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/templates/emails/ccpa-deletion.txt>) | 内嵌 Hermes 上游源码及项目适配内容中的ccpa-deletion 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [ccpa-indirect-deletion.txt](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/templates/emails/ccpa-indirect-deletion.txt>) | 内嵌 Hermes 上游源码及项目适配内容中的ccpa-indirect-deletion 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [gdpr-erasure.txt](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/templates/emails/gdpr-erasure.txt>) | 内嵌 Hermes 上游源码及项目适配内容中的gdpr-erasure 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [generic-optout.txt](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/unbroker/templates/emails/generic-optout.txt>) | 内嵌 Hermes 上游源码及项目适配内容中的generic-optout 实现（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/security/web-pentest/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/web-pentest/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Web Application Penetration Testing |

### backend/hermes/optional-skills/security/web-pentest/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [bypass-techniques.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/web-pentest/references/bypass-techniques.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 bypass-techniques（目录与文件名推断） | Bypass Techniques |
| [exploitation-techniques.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/web-pentest/references/exploitation-techniques.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 exploitation-techniques（目录与文件名推断） | Exploitation Techniques |
| [scope-enforcement.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/web-pentest/references/scope-enforcement.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 scope-enforcement（目录与文件名推断） | Scope Enforcement |
| [vuln-taxonomy.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/web-pentest/references/vuln-taxonomy.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 vuln-taxonomy（目录与文件名推断） | Vulnerability Taxonomy |

### backend/hermes/optional-skills/security/web-pentest/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [recon-scan.sh](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/web-pentest/scripts/recon-scan.sh>) | 启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |

### backend/hermes/optional-skills/security/web-pentest/templates/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [authorization.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/web-pentest/templates/authorization.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 authorization（目录与文件名推断） | Engagement Authorization |
| [exploitation-queue.json](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/web-pentest/templates/exploitation-queue.json>) | 内嵌 Hermes 上游源码及项目适配内容的配置或结构化资源，主题 exploitation-queue（目录与文件名推断） | 按目录和文件类型定位 |
| [pentest-report.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/security/web-pentest/templates/pentest-report.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 pentest-report（目录与文件名推断） | Penetration Test Report |

### backend/hermes/optional-skills/software-development/code-wiki/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/software-development/code-wiki/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Code Wiki Skill |

### backend/hermes/optional-skills/software-development/code-wiki/templates/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [README.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/software-development/code-wiki/templates/README.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 README（目录与文件名推断） | {{PROJECT_NAME}} |
| [architecture.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/software-development/code-wiki/templates/architecture.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 architecture（目录与文件名推断） | Architecture |
| [getting-started.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/software-development/code-wiki/templates/getting-started.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 getting-started（目录与文件名推断） | Getting Started |
| [module.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/software-development/code-wiki/templates/module.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 module（目录与文件名推断） | Module: '{{MODULE_NAME}}' |

### backend/hermes/optional-skills/software-development/rest-graphql-debug/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/software-development/rest-graphql-debug/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | API Testing & Debugging |

### backend/hermes/optional-skills/software-development/subagent-driven-development/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/software-development/subagent-driven-development/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Subagent-Driven Development |

### backend/hermes/optional-skills/software-development/subagent-driven-development/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [context-budget-discipline.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/software-development/subagent-driven-development/references/context-budget-discipline.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 context-budget-discipline（目录与文件名推断） | Context Budget Discipline |
| [gates-taxonomy.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/software-development/subagent-driven-development/references/gates-taxonomy.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 gates-taxonomy（目录与文件名推断） | Gates Taxonomy |

### backend/hermes/optional-skills/web-development/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [DESCRIPTION.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/web-development/DESCRIPTION.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 DESCRIPTION（目录与文件名推断） | Web Development |

### backend/hermes/optional-skills/web-development/cloudflare-temporary-deploy/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/web-development/cloudflare-temporary-deploy/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Cloudflare Temporary Deploy Skill |

### backend/hermes/optional-skills/web-development/cloudflare-temporary-deploy/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [parse_deploy_output.py](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/web-development/cloudflare-temporary-deploy/scripts/parse_deploy_output.py>) | 内嵌 Hermes 上游源码及项目适配内容中的parse_deploy_output 实现（目录与文件名推断） | Parse 'wrangler deploy --temporary' output into structured JSON. / 符号 _first, parse, _selftest, main |

### backend/hermes/optional-skills/web-development/page-agent/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/web-development/page-agent/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | page-agent |

### backend/hermes/optional-skills/yuanbao/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/optional-skills/yuanbao/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Yuanbao Group Interaction |

### backend/hermes/plugins/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | 按目录和文件类型定位 |

### backend/hermes/plugins/browser/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/browser/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | 按目录和文件类型定位 |

### backend/hermes/plugins/browser/browser_use/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/browser/browser_use/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | 按目录和文件类型定位 |
| [provider.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/browser/browser_use/provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的供应商相关实现（目录与文件名推断） | 符号 BrowserUseBrowserProvider |

### backend/hermes/plugins/browser/browserbase/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/browser/browserbase/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | 按目录和文件类型定位 |
| [provider.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/browser/browserbase/provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的供应商相关实现（目录与文件名推断） | 符号 BrowserbaseBrowserProvider |

### backend/hermes/plugins/browser/firecrawl/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/browser/firecrawl/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | 按目录和文件类型定位 |
| [provider.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/browser/firecrawl/provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的供应商相关实现（目录与文件名推断） | 符号 FirecrawlBrowserProvider |

### backend/hermes/plugins/memory/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/memory/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Hermes Memory Provider Plugin - AgentForge Integration / 符号 discover_memory_providers, load_memory_provider, list_memory_provider_names, _get_active_memory_provider, _is_memory_provider_dir |

### backend/hermes/plugins/web/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/web/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | 按目录和文件类型定位 |

### backend/hermes/plugins/web/ddgs/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/web/ddgs/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | DuckDuckGo search plugin — bundled, auto-loaded. / 符号 register |
| [_search_worker.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/web/ddgs/_search_worker.py>) | 内嵌 Hermes 上游源码及项目适配内容中的搜索相关实现（目录与文件名推断） | DDGS search child-process entrypoint (#68096). / 符号 _hold_gil, _run_test_hook, _write_envelope, main |
| [provider.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/web/ddgs/provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的供应商相关实现（目录与文件名推断） | DuckDuckGo search — plugin form (via the ''ddgs'' package). / 符号 _SearchInterrupted, _run_ddgs_search, _plugins_path_entry, _terminate_and_reap, _run_ddgs_search_bounded, DDGSWebSearchProvider |

### backend/hermes/plugins/web/exa/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/web/exa/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | 符号 _get_exa_client |
| [provider.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/web/exa/provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的供应商相关实现（目录与文件名推断） | 符号 _get_exa_client |

### backend/hermes/plugins/web/firecrawl/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/web/firecrawl/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | 符号 _firecrawl_backend_help_suffix, _get_firecrawl_client |
| [provider.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/web/firecrawl/provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的供应商相关实现（目录与文件名推断） | 符号 _firecrawl_backend_help_suffix, _get_firecrawl_client, _get_firecrawl_gateway_url, _is_tool_gateway_ready, check_firecrawl_api_key |

### backend/hermes/plugins/web/parallel/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/web/parallel/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | 符号 _get_async_parallel_client, _get_parallel_client |
| [provider.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/web/parallel/provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的供应商相关实现（目录与文件名推断） | 符号 _get_async_parallel_client, _get_parallel_client |

### backend/hermes/plugins/web/tavily/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/web/tavily/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | 符号 _normalize_tavily_documents, _normalize_tavily_search_results |
| [provider.py](<E:/PythonCode/EasyChat/backend/hermes/plugins/web/tavily/provider.py>) | 内嵌 Hermes 上游源码及项目适配内容中的供应商相关实现（目录与文件名推断） | 符号 _normalize_tavily_documents, _normalize_tavily_search_results, _tavily_request |

### backend/hermes/providers/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [README.md](<E:/PythonCode/EasyChat/backend/hermes/providers/README.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 README（目录与文件名推断） | providers/ |
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/providers/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Provider module registry. / 符号 register_provider, get_provider_profile, list_providers, _user_plugins_dir, _import_plugin_dir, _discover_providers |
| [base.py](<E:/PythonCode/EasyChat/backend/hermes/providers/base.py>) | 内嵌 Hermes 上游源码及项目适配内容中的base 实现（目录与文件名推断） | Provider profile base class. / 符号 _profile_user_agent, ProviderProfile |

### backend/hermes/skills/ai-generated/code-stats-report/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/ai-generated/code-stats-report/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | /code-stats-report — AgentForge 代码量统计报告 |

### backend/hermes/skills/ai-generated/code-stats-report/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [generate_report.py](<E:/PythonCode/EasyChat/backend/hermes/skills/ai-generated/code-stats-report/scripts/generate_report.py>) | 内嵌 Hermes 上游源码及项目适配内容中的报告相关实现（目录与文件名推断） | AgentForge 项目代码量统计报告生成器 / 符号 count_lines, is_code_file, get_language, walk_and_count, get_top_level_stats, generate_ascii_bar, generate_ascii_chart |

### backend/hermes/skills/automation/send-email/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/automation/send-email/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | /send-email — 邮件发送技能 |

### backend/hermes/skills/automation/send-email/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [smtp-setup.md](<E:/PythonCode/EasyChat/backend/hermes/skills/automation/send-email/references/smtp-setup.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 smtp-setup（目录与文件名推断） | SMTP 邮箱配置指南 |

### backend/hermes/skills/automation/send-email/scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [send_email.py](<E:/PythonCode/EasyChat/backend/hermes/skills/automation/send-email/scripts/send_email.py>) | 内嵌 Hermes 上游源码及项目适配内容中的send_email 实现（目录与文件名推断） | 邮件发送脚本 — 支持纯文本/HTML/附件/内嵌图片/多收件人 / 符号 EmailSender, main |

### backend/hermes/skills/automation/send-email/templates/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [notification.html](<E:/PythonCode/EasyChat/backend/hermes/skills/automation/send-email/templates/notification.html>) | 内嵌 Hermes 上游源码及项目适配内容中的通知相关实现（目录与文件名推断） | 按目录和文件类型定位 |
| [report.html](<E:/PythonCode/EasyChat/backend/hermes/skills/automation/send-email/templates/report.html>) | 内嵌 Hermes 上游源码及项目适配内容中的报告相关实现（目录与文件名推断） | 按目录和文件类型定位 |
| [weekly-summary.html](<E:/PythonCode/EasyChat/backend/hermes/skills/automation/send-email/templates/weekly-summary.html>) | 内嵌 Hermes 上游源码及项目适配内容中的weekly-summary 实现（目录与文件名推断） | 按目录和文件类型定位 |

### backend/hermes/skills/code-review/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/code-review/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | 代码审查 |

### backend/hermes/skills/engineering/agentforge-dev/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | AgentForge 开发指南 |

### backend/hermes/skills/engineering/agentforge-dev/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [api-and-db.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/api-and-db.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 api-and-db（目录与文件名推断） | AgentForge 数据库 & API 参考 |
| [chat-user-id-mismatch.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/chat-user-id-mismatch.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 chat-user-id-mismatch（目录与文件名推断） | chatUserId 存储位置导致的 user_id=0 会话丢失 |
| [chatUserId-router-sync.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/chatUserId-router-sync.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 chatUserId-router-sync（目录与文件名推断） | chatUserId 同步陷阱 — router 兜底方案 |
| [concurrency-architecture.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/concurrency-architecture.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 concurrency-architecture（目录与文件名推断） | AgentForge 并发架构分析 |
| [ide-mode-patterns.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/ide-mode-patterns.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 ide-mode-patterns（目录与文件名推断） | IDE 模式全栈开发模式 |
| [model-config-multimodal.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/model-config-multimodal.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 model-config-multimodal（目录与文件名推断） | 模型配置三层多模态检测 |
| [multi-channel-architecture.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/multi-channel-architecture.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 multi-channel-architecture（目录与文件名推断） | 多渠道消息架构（微信/飞书/Web） |
| [multimodal-image-support.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/multimodal-image-support.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 multimodal-image-support（目录与文件名推断） | 多模态图片问答 — 全栈实现参考 |
| [platform-integration.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/platform-integration.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 platform-integration（目录与文件名推断） | 多渠道（微信/飞书）集成模式 |
| [skill-categories.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/skill-categories.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 skill-categories（目录与文件名推断） | 技能分类功能实现细节 |
| [skill-permission.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/skill-permission.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 skill-permission（目录与文件名推断） | Skill Permission Architecture |
| [skill-review-pipeline.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/skill-review-pipeline.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 skill-review-pipeline（目录与文件名推断） | 技能审核流程 (Review Pipeline) |
| [skill-view-frontmatter-fix.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/skill-view-frontmatter-fix.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 skill-view-frontmatter-fix（目录与文件名推断） | Skill 详情页 YAML frontmatter 渲染修复模式 |
| [wechat-commands.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/wechat-commands.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 wechat-commands（目录与文件名推断） | 微信聊天命令系统 |
| [wechat-ilink-integration.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/wechat-ilink-integration.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 wechat-ilink-integration（目录与文件名推断） | 微信 iLink Bot 集成 |
| [wechat-listener-architecture.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/wechat-listener-architecture.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 wechat-listener-architecture（目录与文件名推断） | 微信消息后台监听器架构 |
| [wechat-markdown-strip.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-dev/references/wechat-markdown-strip.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 wechat-markdown-strip（目录与文件名推断） | 微信 ClawBot MD 兼容转换 |

### backend/hermes/skills/engineering/agentforge-development/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-development/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | AgentForge 项目开发 |

### backend/hermes/skills/engineering/agentforge-development/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [model-config-api.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-development/references/model-config-api.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 model-config-api（目录与文件名推断） | 模型配置 API — 完整模式参考 |
| [skill-category-system.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-development/references/skill-category-system.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 skill-category-system（目录与文件名推断） | 技能分类管理系统 |
| [skill-manager-tool-guard.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-development/references/skill-manager-tool-guard.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 skill-manager-tool-guard（目录与文件名推断） | skill_manager_tool.py — Auto-Inject & Tool-Docstring Enforcement |
| [skill-provenance.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/agentforge-development/references/skill-provenance.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 skill-provenance（目录与文件名推断） | Skill Provenance — 前台 vs 后台区分 |

### backend/hermes/skills/engineering/event-driven-state-debugging/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/event-driven-state-debugging/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | 事件驱动 UI 状态守卫型 Bug 调试 |

### backend/hermes/skills/engineering/event-driven-state-debugging/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [chat-history-click-session.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/event-driven-state-debugging/references/chat-history-click-session.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 chat-history-click-session（目录与文件名推断） | 会话记录:聊天历史点击"只有第一个能跳转"排查 |
| [controlled-details-collapse.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/event-driven-state-debugging/references/controlled-details-collapse.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 controlled-details-collapse（目录与文件名推断） | Vue 受控组件坑:手动展开被下一轮状态更新强制折叠 |
| [selectchat-dedup-mismatch.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/event-driven-state-debugging/references/selectchat-dedup-mismatch.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 selectchat-dedup-mismatch（目录与文件名推断） | selectChat 去重判断与高亮判断用不同状态源 → 首次点击第一条无反应 |
| [sidebar-collapse-overflow.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/event-driven-state-debugging/references/sidebar-collapse-overflow.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 sidebar-collapse-overflow（目录与文件名推断） | 折叠侧边栏：收起后展开按钮被裁掉的布局坑 |

### backend/hermes/skills/engineering/legacy-code-removal/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/legacy-code-removal/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | 旧代码 / 旧前端安全移除 |

### backend/hermes/skills/engineering/mysql-backend-extension/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/mysql-backend-extension/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | FastAPI + MySQL 后端功能扩展与深坑 |

### backend/hermes/skills/engineering/mysql-backend-extension/references/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [ide-web-api-pattern.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/mysql-backend-extension/references/ide-web-api-pattern.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 ide-web-api-pattern（目录与文件名推断） | IDE Web 模式：后端文件树与文件读写 API |
| [model-config-controller-pattern.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/mysql-backend-extension/references/model-config-controller-pattern.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 model-config-controller-pattern（目录与文件名推断） | 模型配置控制器：从零建表到前端列表+编辑+测试 |
| [model-config-test-endpoint.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/mysql-backend-extension/references/model-config-test-endpoint.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 model-config-test-endpoint（目录与文件名推断） | 模型配置"测试连接"端点的多轮迭代模式 |
| [session-rename-recipes.md](<E:/PythonCode/EasyChat/backend/hermes/skills/engineering/mysql-backend-extension/references/session-rename-recipes.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 session-rename-recipes（目录与文件名推断） | 会话记录：给历史会话加"重命名标题"功能（端到端） |

### backend/hermes/skills/git-workflow/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/git-workflow/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Git 工作流 |

### backend/hermes/skills/paper-reproduction/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [skill.md](<E:/PythonCode/EasyChat/backend/hermes/skills/paper-reproduction/skill.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 skill（目录与文件名推断） | 论文复现助手 |

### backend/hermes/skills/remu-assistant/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/remu-assistant/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | /remu-assistant — 蕾姆助手 |

### backend/hermes/skills/report-writer/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/report-writer/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | /report-writer — 通用报告生成器 |

### backend/hermes/skills/requesting-code-review/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/requesting-code-review/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | 请求代码审查 |

### backend/hermes/skills/shell-scripting/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/shell-scripting/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | Shell 脚本编写 |

### backend/hermes/skills/skill-creator/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/skill-creator/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | /skill-creator — 技能工厂 |

### backend/hermes/skills/system-hardening/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/system-hardening/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | 系统安全加固 |

### backend/hermes/skills/systematic-debugging/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/systematic-debugging/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | 系统化调试 |

### backend/hermes/skills/test-driven-development/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/test-driven-development/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | 测试驱动开发（TDD） |

### backend/hermes/skills/test-report/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/test-report/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | /test-report — 测试报告生成 |

### backend/hermes/skills/travel-planner/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/travel-planner/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | /travel-planner — 旅游路线规划 |

### backend/hermes/skills/verification-before-completion/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/verification-before-completion/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | 完成前验证 |

### backend/hermes/skills/web-research/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SKILL.md](<E:/PythonCode/EasyChat/backend/hermes/skills/web-research/SKILL.md>) | 内嵌 Hermes 上游源码及项目适配内容的说明、设计或验证文档，主题 SKILL（目录与文件名推断） | 网络调研 |

### backend/hermes/tools/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/tools/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Tools package namespace. / 符号 check_file_requirements |
| [ansi_strip.py](<E:/PythonCode/EasyChat/backend/hermes/tools/ansi_strip.py>) | 内嵌 Hermes 上游源码及项目适配内容中的ansi_strip 实现（目录与文件名推断） | Strip ANSI escape sequences from subprocess output. / 符号 strip_ansi, sanitize_display_text |
| [approval.py](<E:/PythonCode/EasyChat/backend/hermes/tools/approval.py>) | 内嵌 Hermes 上游源码及项目适配内容中的审批相关实现（目录与文件名推断） | Dangerous command approval -- detection, prompting, and per-session state. / 符号 set_hermes_interactive_context, reset_hermes_interactive_context, _is_interactive_cli, _fire_approval_hook, _prepare_smart_approval_observer, _observe_smart_approval_verdict, set_current_session_key |
| [async_delegation.py](<E:/PythonCode/EasyChat/backend/hermes/tools/async_delegation.py>) | 内嵌 Hermes 上游源码及项目适配内容中的async_delegation 实现（目录与文件名推断） | Async (background) delegation registry. / 符号 _db_path, _connect, _initialize_schema, _transaction, _persist_dispatch, _delete_durable_delegation, _prune_durable_records |
| [binary_extensions.py](<E:/PythonCode/EasyChat/backend/hermes/tools/binary_extensions.py>) | 内嵌 Hermes 上游源码及项目适配内容中的binary_extensions 实现（目录与文件名推断） | Binary file extensions to skip for text-based operations. / 符号 has_binary_extension |
| [blueprints.py](<E:/PythonCode/EasyChat/backend/hermes/tools/blueprints.py>) | 内嵌 Hermes 上游源码及项目适配内容中的blueprints 实现（目录与文件名推断） | Blueprints: shareable plain-language automations layered on skills + cron. / 符号 BlueprintError, BlueprintSpec, _split_frontmatter, parse_blueprint, blueprint_spec_for_installed, blueprint_to_job_spec, create_blueprint_job |
| [browser_camofox.py](<E:/PythonCode/EasyChat/backend/hermes/tools/browser_camofox.py>) | 内嵌 Hermes 上游源码及项目适配内容中的浏览器相关实现（目录与文件名推断） | Camofox browser backend — local anti-detection browser via REST API. / 符号 _get_command_timeout, _auth_headers, get_camofox_url, _config_cdp_url, is_camofox_mode, check_camofox_available, get_vnc_url |
| [browser_camofox_state.py](<E:/PythonCode/EasyChat/backend/hermes/tools/browser_camofox_state.py>) | 内嵌 Hermes 上游源码及项目适配内容中的浏览器、状态相关实现（目录与文件名推断） | Hermes-managed Camofox state helpers. / 符号 get_camofox_state_dir, get_camofox_identity |
| [browser_cdp_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/browser_cdp_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的浏览器、工具相关实现（目录与文件名推断） | Raw Chrome DevTools Protocol (CDP) passthrough tool. / 符号 _redact_cdp_output, _run_async, _resolve_cdp_endpoint, _private_page_guard_error, _browser_cdp_private_guard, _cdp_call, _browser_cdp_via_supervisor |
| [browser_dialog_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/browser_dialog_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的浏览器、工具相关实现（目录与文件名推断） | Agent-facing tool: respond to a native JS dialog captured by the CDP supervisor. / 符号 browser_dialog, _browser_dialog_check |
| [browser_supervisor.py](<E:/PythonCode/EasyChat/backend/hermes/tools/browser_supervisor.py>) | 内嵌 Hermes 上游源码及项目适配内容中的浏览器相关实现（目录与文件名推断） | Persistent CDP supervisor for browser dialog + frame detection. / 符号 _redact_cdp_error_text, _redact_supervisor_text, PendingDialog, DialogRecord, FrameInfo, ConsoleEvent, SupervisorSnapshot |
| [browser_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/browser_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的浏览器、工具相关实现（目录与文件名推断） | Browser Tool Module / 符号 _build_browser_env, _discover_homebrew_node_dirs, _browser_candidate_path_dirs, _merge_browser_path, _sanitize_url_for_logs, _get_command_timeout, _safe_command_timeout |
| [budget_config.py](<E:/PythonCode/EasyChat/backend/hermes/tools/budget_config.py>) | 内嵌 Hermes 上游源码及项目适配内容中的配置相关实现（目录与文件名推断） | Configurable budget constants for tool result persistence. / 符号 BudgetConfig, budget_for_context_window |
| [checkpoint_manager.py](<E:/PythonCode/EasyChat/backend/hermes/tools/checkpoint_manager.py>) | 内嵌 Hermes 上游源码及项目适配内容中的checkpoint_manager 实现（目录与文件名推断） | Checkpoint Manager — Transparent filesystem snapshots via a single shared / 符号 _validate_commit_hash, _validate_file_path, _normalize_path, _project_hash, _store_path, _shadow_repo_path, _index_path |
| [clarify_gateway.py](<E:/PythonCode/EasyChat/backend/hermes/tools/clarify_gateway.py>) | 内嵌 Hermes 上游源码及项目适配内容中的clarify_gateway 实现（目录与文件名推断） | Gateway-side clarify primitive (blocking event-based queue). / 符号 _ClarifyEntry, register, wait_for_response, resolve_gateway_clarify, get_pending_for_session, _coerce_text_response, _coerce_multi_select_text |
| [clarify_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/clarify_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Clarify Tool Module - Interactive Clarifying Questions / 符号 _flatten_choice, _invoke_callback, _parse_multi_select_response, clarify_tool, check_clarify_requirements |
| [close_terminal_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/close_terminal_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的终端、工具相关实现（目录与文件名推断） | Close a read-only agent terminal tab in the Hermes desktop GUI. / 符号 close_terminal_tool, check_close_terminal_requirements |
| [code_execution_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/code_execution_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Code Execution Tool -- Programmatic Tool Calling (PTC) / 符号 _assemble_stdout_result, _truncate_stdout_text, _scrub_child_env, check_sandbox_requirements, generate_hermes_tools_module, _rpc_server_loop, _get_or_create_env |
| [computer_use_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/computer_use_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Shim for tool discovery. Registers 'computer_use' with tools.registry. |
| [credential_files.py](<E:/PythonCode/EasyChat/backend/hermes/tools/credential_files.py>) | 内嵌 Hermes 上游源码及项目适配内容中的文件相关实现（目录与文件名推断） | File passthrough registry for remote terminal backends. / 符号 _get_registered, _resolve_hermes_home, register_credential_file, register_credential_files, _load_config_files, get_credential_file_mounts, get_skills_directory_mount |
| [cronjob_tools.py](<E:/PythonCode/EasyChat/backend/hermes/tools/cronjob_tools.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Cron job management tools for Hermes Agent. / 符号 _notify_provider_jobs_changed_safe, _is_emoji_cp, _zwj_has_emoji_neighbour, _strip_legitimate_emoji_zwj, _strip_cron_safe_constructs, _check_invisible_unicode, _strip_invisible_unicode |
| [daemon_pool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/daemon_pool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的daemon_pool 实现（目录与文件名推断） | Shared daemon-thread ThreadPoolExecutor. / 符号 DaemonThreadPoolExecutor |
| [debug_helpers.py](<E:/PythonCode/EasyChat/backend/hermes/tools/debug_helpers.py>) | 内嵌 Hermes 上游源码及项目适配内容中的debug_helpers 实现（目录与文件名推断） | Shared debug session infrastructure for Hermes tools. / 符号 DebugSession |
| [delegate_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/delegate_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的子代理委派、工具相关实现（目录与文件名推断） | Delegate Tool -- Subagent Architecture / 符号 set_context_enricher, _subagent_auto_deny, _subagent_auto_approve, _get_subagent_approval_callback, set_spawn_paused, is_spawn_paused, _register_subagent |
| [delegation_live_log.py](<E:/PythonCode/EasyChat/backend/hermes/tools/delegation_live_log.py>) | 内嵌 Hermes 上游源码及项目适配内容中的delegation_live_log 实现（目录与文件名推断） | Live, tail-able transcripts for delegated subagents. / 符号 live_transcript_root, new_live_delegation_id, _one_line, _redact, LiveTranscriptWriter, wrap_progress_callback, create_live_transcripts |
| [desktop_ui.py](<E:/PythonCode/EasyChat/backend/hermes/tools/desktop_ui.py>) | 内嵌 Hermes 上游源码及项目适配内容中的desktop_ui 实现（目录与文件名推断） | Bridge desktop-only tools to Hermes-desktop renderer events. / 符号 set_emitter, available, emit |
| [env_passthrough.py](<E:/PythonCode/EasyChat/backend/hermes/tools/env_passthrough.py>) | 内嵌 Hermes 上游源码及项目适配内容中的env_passthrough 实现（目录与文件名推断） | Environment variable passthrough registry. / 符号 _get_allowed, _is_hermes_provider_credential, register_env_passthrough, _load_config_passthrough, is_env_passthrough, get_all_passthrough, clear_env_passthrough |
| [env_probe.py](<E:/PythonCode/EasyChat/backend/hermes/tools/env_probe.py>) | 内嵌 Hermes 上游源码及项目适配内容中的env_probe 实现（目录与文件名推断） | Local-environment toolchain probe for the system prompt. / 符号 _run, _python_version_of, _has_pip_module, _detect_pep668, _pip_python_version, _build_probe_line, get_environment_probe_line |
| [fal_common.py](<E:/PythonCode/EasyChat/backend/hermes/tools/fal_common.py>) | 内嵌 Hermes 上游源码及项目适配内容中的fal_common 实现（目录与文件名推断） | Shared FAL.ai SDK plumbing. / 符号 import_fal_client, _normalize_fal_queue_url_format, _extract_http_status, _ManagedFalSyncClient |
| [feishu_doc_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/feishu_doc_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Feishu Document Tool -- read document content via Feishu/Lark API. / 符号 set_client, get_client, _check_feishu, _handle_feishu_doc_read |
| [feishu_drive_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/feishu_drive_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Feishu Drive Tools -- document comment operations via Feishu/Lark API. / 符号 set_client, get_client, _check_feishu, _do_request, _handle_list_comments, _handle_list_replies, _handle_reply_comment |
| [file_operations.py](<E:/PythonCode/EasyChat/backend/hermes/tools/file_operations.py>) | 内嵌 Hermes 上游源码及项目适配内容中的文件相关实现（目录与文件名推断） | File Operations Module / 符号 _strip_terminal_fence_leaks, _detect_line_ending, _normalize_line_endings, _strip_bom, _has_bom, _is_write_denied, ReadResult |
| [file_state.py](<E:/PythonCode/EasyChat/backend/hermes/tools/file_state.py>) | 内嵌 Hermes 上游源码及项目适配内容中的文件、状态相关实现（目录与文件名推断） | Cross-agent file state coordination. / 符号 FileStateRegistry, get_registry, _disabled, _fmt_ts, _cap_dict, record_read, note_write |
| [file_tools.py](<E:/PythonCode/EasyChat/backend/hermes/tools/file_tools.py>) | 内嵌 Hermes 上游源码及项目适配内容中的文件、工具相关实现（目录与文件名推断） | File Tools Module - LLM agent file manipulation tools. / 符号 _expand_tilde, _get_max_read_chars, _truncate_to_char_budget, _resolve_path, _terminal_env_type_for_task, _uses_container_paths, _normalize_without_host_deref |
| [focus_pane_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/focus_pane_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Reveal/focus a pane in the Hermes desktop GUI. / 符号 focus_pane_tool, check_focus_pane_requirements |
| [fuzzy_match.py](<E:/PythonCode/EasyChat/backend/hermes/tools/fuzzy_match.py>) | 内嵌 Hermes 上游源码及项目适配内容中的fuzzy_match 实现（目录与文件名推断） | Fuzzy Matching Module for File Operations / 符号 _unicode_normalize, fuzzy_find_and_replace, _detect_escape_drift, _leading_whitespace, _first_meaningful_line, _reindent_replacement, _maybe_unescape_new_string |
| [hook_output_spill.py](<E:/PythonCode/EasyChat/backend/hermes/tools/hook_output_spill.py>) | 内嵌 Hermes 上游源码及项目适配内容中的hook_output_spill 实现（目录与文件名推断） | Spill oversized hook-injected context to disk with a preview placeholder. / 符号 _coerce_positive_int, _coerce_non_negative_int, get_spill_config, _resolve_spill_dir, _build_preview, spill_if_oversized |
| [image_source.py](<E:/PythonCode/EasyChat/backend/hermes/tools/image_source.py>) | 内嵌 Hermes 上游源码及项目适配内容中的image_source 实现（目录与文件名推断） | Single resolver for every vision_analyze image source -> bytes + mime. / 符号 ImageResolutionError, UnsupportedScheme, SourceUnsafe, SourceTooLarge, SourceNotFound, NotAnImage, ResolveContext |
| [interrupt.py](<E:/PythonCode/EasyChat/backend/hermes/tools/interrupt.py>) | 内嵌 Hermes 上游源码及项目适配内容中的interrupt 实现（目录与文件名推断） | Per-thread interrupt signaling for all tools. / 符号 set_interrupt, is_interrupted, clear_current_thread_interrupt, _ThreadAwareEventProxy |
| [lazy_deps.py](<E:/PythonCode/EasyChat/backend/hermes/tools/lazy_deps.py>) | 内嵌 Hermes 上游源码及项目适配内容中的lazy_deps 实现（目录与文件名推断） | Lazy dependency installer for opt-in Hermes Agent backends. / 符号 FeatureUnavailable, _InstallResult, _python_abi_tag, _lazy_install_target, _ensure_target_ready, _activate_target_on_syspath, activate_durable_lazy_target |
| [managed_tool_gateway.py](<E:/PythonCode/EasyChat/backend/hermes/tools/managed_tool_gateway.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Generic managed-tool gateway helpers for Nous-hosted vendor passthroughs. / 符号 ManagedToolGatewayConfig, auth_json_path, _read_nous_provider_state, _parse_timestamp, _access_token_is_expiring, peek_nous_access_token, read_nous_access_token |
| [mcp_dashboard_oauth.py](<E:/PythonCode/EasyChat/backend/hermes/tools/mcp_dashboard_oauth.py>) | 内嵌 Hermes 上游源码及项目适配内容中的MCP相关实现（目录与文件名推断） | Dashboard-mediated callback bridge for MCP OAuth. / 符号 DashboardOAuthFlow, dashboard_oauth_flow, get_dashboard_oauth_flow |
| [mcp_oauth.py](<E:/PythonCode/EasyChat/backend/hermes/tools/mcp_oauth.py>) | 内嵌 Hermes 上游源码及项目适配内容中的MCP相关实现（目录与文件名推断） | MCP OAuth 2.1 Client Support / 符号 OAuthNonInteractiveError, _get_token_dir, _safe_filename, _find_free_port, _reserve_callback_port, _cached_redirect_port, _cached_redirect_uri |
| [mcp_oauth_manager.py](<E:/PythonCode/EasyChat/backend/hermes/tools/mcp_oauth_manager.py>) | 内嵌 Hermes 上游源码及项目适配内容中的MCP相关实现（目录与文件名推断） | Central manager for per-server MCP OAuth state. / 符号 _same_endpoint, _ProviderEntry, _make_hermes_provider_class, MCPOAuthManager, get_manager, reset_manager_for_tests |
| [mcp_stdio_watchdog.py](<E:/PythonCode/EasyChat/backend/hermes/tools/mcp_stdio_watchdog.py>) | 内嵌 Hermes 上游源码及项目适配内容中的MCP相关实现（目录与文件名推断） | Parent-death watchdog supervisor for stdio MCP subprocesses. / 符号 _is_orphaned, _terminate_process_group, _watchdog_loop, main |
| [mcp_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/mcp_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的MCP、工具相关实现（目录与文件名推断） | MCP (Model Context Protocol) Client Support / 符号 _get_mcp_stderr_log, _write_stderr_log_header, _check_message_handler_support, _check_logging_callback_support, _jittered, _env_ref_name, _build_safe_env |
| [memory_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/memory_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的记忆、工具相关实现（目录与文件名推断） | Memory Tool Module - Persistent Curated Memory / 符号 get_memory_dir, _scan_memory_content, _drift_error, _read_failed_error, MemoryStore, load_on_disk_store, _apply_write_gate |
| [microsoft_graph_auth.py](<E:/PythonCode/EasyChat/backend/hermes/tools/microsoft_graph_auth.py>) | 内嵌 Hermes 上游源码及项目适配内容中的图数据、认证相关实现（目录与文件名推断） | Microsoft Graph app-only authentication helpers. / 符号 MicrosoftGraphAuthError, MicrosoftGraphConfigError, MicrosoftGraphTokenError, GraphCredentials, CachedAccessToken, MicrosoftGraphTokenProvider, _extract_error_detail |
| [microsoft_graph_client.py](<E:/PythonCode/EasyChat/backend/hermes/tools/microsoft_graph_client.py>) | 内嵌 Hermes 上游源码及项目适配内容中的图数据相关实现（目录与文件名推断） | Reusable Microsoft Graph REST client helpers. / 符号 MicrosoftGraphClientError, MicrosoftGraphAPIError, MicrosoftGraphClient |
| [open_preview_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/open_preview_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Open a URL, dev server, or file in the Hermes desktop GUI's preview pane. / 符号 _normalize_target, open_preview_tool, check_open_preview_requirements |
| [openrouter_client.py](<E:/PythonCode/EasyChat/backend/hermes/tools/openrouter_client.py>) | 内嵌 Hermes 上游源码及项目适配内容中的openrouter_client 实现（目录与文件名推断） | Shared OpenRouter API client for Hermes tools. / 符号 get_async_client, check_api_key |
| [osv_check.py](<E:/PythonCode/EasyChat/backend/hermes/tools/osv_check.py>) | 内嵌 Hermes 上游源码及项目适配内容中的检查相关实现（目录与文件名推断） | OSV malware check for MCP extension packages. / 符号 check_package_for_malware, _infer_ecosystem, _parse_package_from_args, _parse_npm_package, _parse_pypi_package, _query_osv |
| [patch_parser.py](<E:/PythonCode/EasyChat/backend/hermes/tools/patch_parser.py>) | 内嵌 Hermes 上游源码及项目适配内容中的patch_parser 实现（目录与文件名推断） | V4A Patch Format Parser / 符号 OperationType, HunkLine, Hunk, PatchOperation, parse_v4a_patch, _count_occurrences, _validate_operations |
| [path_security.py](<E:/PythonCode/EasyChat/backend/hermes/tools/path_security.py>) | 内嵌 Hermes 上游源码及项目适配内容中的path_security 实现（目录与文件名推断） | Shared path validation helpers for tool implementations. / 符号 validate_within_dir, has_traversal_component |
| [process_registry.py](<E:/PythonCode/EasyChat/backend/hermes/tools/process_registry.py>) | 内嵌 Hermes 上游源码及项目适配内容中的注册表相关实现（目录与文件名推断） | Process Registry -- In-memory registry for managed background processes. / 符号 format_uptime_short, ProcessSession, ProcessRegistry, _format_age, _format_async_delegation, format_process_notification, _redact_process_result |
| [project_tools.py](<E:/PythonCode/EasyChat/backend/hermes/tools/project_tools.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Project tools — the agent's INTENTIONAL handle on first-class Projects. / 符号 set_project_workspace_callback, _primary_path, _apply_workspace, _resolve, project_list, project_create, project_switch |
| [read_extract.py](<E:/PythonCode/EasyChat/backend/hermes/tools/read_extract.py>) | 内嵌 Hermes 上游源码及项目适配内容中的read_extract 实现（目录与文件名推断） | Stdlib document-to-text extraction for ''read_file''. / 符号 ExtractionError, _extension, is_extractable_document, extract_document_text, _source_text, _extract_notebook, _zip_xml |
| [read_terminal_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/read_terminal_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的终端、工具相关实现（目录与文件名推断） | Read the in-app terminal pane in the Hermes desktop GUI. / 符号 read_terminal_tool, check_read_terminal_requirements |
| [registry.py](<E:/PythonCode/EasyChat/backend/hermes/tools/registry.py>) | 内嵌 Hermes 上游源码及项目适配内容中的注册表相关实现（目录与文件名推断） | Central registry for all hermes-agent tools. / 符号 _is_registry_register_call, _module_registers_tools, discover_builtin_tools, ToolEntry, _check_fn_cached, invalidate_check_fn_cache, ToolRegistry |
| [schema_sanitizer.py](<E:/PythonCode/EasyChat/backend/hermes/tools/schema_sanitizer.py>) | 内嵌 Hermes 上游源码及项目适配内容中的schema_sanitizer 实现（目录与文件名推断） | Sanitize tool JSON schemas for broad LLM-backend compatibility. / 符号 sanitize_property_key, _rename_property_keys, unrename_tool_args, sanitize_tool_schemas, _sanitize_single_tool, _strip_ref_siblings, _strip_top_level_combinators |
| [send_message_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/send_message_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Send Message Tool -- cross-channel messaging via platform APIs. / 符号 _media_caption_split, _sanitize_error_text, _error, _display_chat_id, _telegram_retry_delay, _send_telegram_message_with_retry, send_message_tool |
| [session_search_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/session_search_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的会话、搜索、工具相关实现（目录与文件名推断） | Session Search Tool - Long-Term Conversation Recall / 符号 _format_timestamp, _is_compaction_summary, _resolve_to_parent, _resolve_lineage, _is_compression_ended, _get_message_storage_state, _is_compacted_message |
| [skill_manager_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/skill_manager_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的技能、工具相关实现（目录与文件名推断） | Skill Manager Tool -- Agent-Managed Skill Creation & Editing / 符号 _guard_agent_created_enabled, _security_scan_skill, _skills_dir, _containing_skills_root, _is_path_redirect, _validate_delete_target, _pinned_guard |
| [skill_provenance.py](<E:/PythonCode/EasyChat/backend/hermes/tools/skill_provenance.py>) | 内嵌 Hermes 上游源码及项目适配内容中的技能相关实现（目录与文件名推断） | Skill write-origin provenance — ContextVar for distinguishing agent-sediment skill writes from foreground user-directed writes. / 符号 set_current_write_origin, reset_current_write_origin, get_current_write_origin, is_background_review |
| [skill_usage.py](<E:/PythonCode/EasyChat/backend/hermes/tools/skill_usage.py>) | 内嵌 Hermes 上游源码及项目适配内容中的技能、用量相关实现（目录与文件名推断） | Skill usage telemetry + provenance tracking for the Curator feature. / 符号 is_protected_builtin, _skills_dir, _usage_file, _usage_file_lock, _archive_dir, _now_iso, _parse_iso_timestamp |
| [skills_ast_audit.py](<E:/PythonCode/EasyChat/backend/hermes/tools/skills_ast_audit.py>) | 内嵌 Hermes 上游源码及项目适配内容中的技能相关实现（目录与文件名推断） | AST-level deep audit for skill Python files — opt-in diagnostic, not a security gate. / 符号 _scan_source, ast_scan_path, format_ast_report |
| [skills_guard.py](<E:/PythonCode/EasyChat/backend/hermes/tools/skills_guard.py>) | 内嵌 Hermes 上游源码及项目适配内容中的技能相关实现（目录与文件名推断） | Skills Guard — Security scanner for externally-sourced skills. / 符号 Finding, ScanResult, scan_file, scan_skill, _content_digest, full_content_hash, _finding_dict |
| [skills_hub.py](<E:/PythonCode/EasyChat/backend/hermes/tools/skills_hub.py>) | 内嵌 Hermes 上游源码及项目适配内容中的技能相关实现（目录与文件名推断） | Skills Hub — Source adapters and hub state management for the Hermes Skills Hub. / 符号 _override, _hermes_home, _skills_dir, _hub_dir, _lock_file, _quarantine_dir, _audit_log |
| [skills_sync.py](<E:/PythonCode/EasyChat/backend/hermes/tools/skills_sync.py>) | 内嵌 Hermes 上游源码及项目适配内容中的技能相关实现（目录与文件名推断） | Skills Sync -- Manifest-based seeding and updating of bundled skills. / 符号 _get_bundled_dir, _get_optional_dir, _build_external_skill_index, _read_manifest, _read_suppressed_names, _write_manifest, _read_skill_name |
| [skills_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/skills_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的技能、工具相关实现（目录与文件名推断） | Skills Tool Module / 符号 _skills_scan_signature, _agentforge_scope_allows, _agentforge_toolset_denied, _skills_dir, _skill_lookup_path_error, load_env, SkillReadinessStatus |
| [slash_confirm.py](<E:/PythonCode/EasyChat/backend/hermes/tools/slash_confirm.py>) | 内嵌 Hermes 上游源码及项目适配内容中的slash_confirm 实现（目录与文件名推断） | Generic slash-command confirmation primitive (gateway-side). / 符号 register, get_pending, clear, clear_if_stale, resolve, resolve_sync_compat |
| [terminal_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/terminal_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的终端、工具相关实现（目录与文件名推断） | Terminal Tool Module / 符号 _safe_parse_import_env, _check_disk_usage_warning, _get_sudo_password_callback, _get_approval_callback, set_sudo_password_callback, set_approval_callback, _get_sudo_password_cache_scope |
| [thread_context.py](<E:/PythonCode/EasyChat/backend/hermes/tools/thread_context.py>) | 内嵌 Hermes 上游源码及项目适配内容中的上下文相关实现（目录与文件名推断） | Propagate agent-turn context into worker threads that dispatch Hermes tools. / 符号 _callback_api, propagate_context_to_thread |
| [threat_patterns.py](<E:/PythonCode/EasyChat/backend/hermes/tools/threat_patterns.py>) | 内嵌 Hermes 上游源码及项目适配内容中的threat_patterns 实现（目录与文件名推断） | Shared threat-pattern library for context window security scanning. / 符号 _compile, scan_for_threats, first_threat_message |
| [tirith_security.py](<E:/PythonCode/EasyChat/backend/hermes/tools/tirith_security.py>) | 内嵌 Hermes 上游源码及项目适配内容中的tirith_security 实现（目录与文件名推断） | Tirith pre-exec security scanning wrapper. / 符号 _env_bool, _env_int, _load_security_config, _record_tirith_crash, _warn_once, _reset_spawn_warning_state, _get_hermes_home |
| [todo_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/todo_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Todo Tool Module - Planning & Task Management / 符号 TodoStore, todo_tool, check_todo_requirements |
| [tool_backend_helpers.py](<E:/PythonCode/EasyChat/backend/hermes/tools/tool_backend_helpers.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Shared helpers for tool backend selection. / 符号 managed_nous_tools_enabled, nous_tool_gateway_unavailable_message, normalize_browser_cloud_provider, coerce_modal_mode, normalize_modal_mode, has_direct_modal_credentials, resolve_modal_backend_state |
| [tool_output_limits.py](<E:/PythonCode/EasyChat/backend/hermes/tools/tool_output_limits.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Configurable tool-output truncation limits. / 符号 _coerce_positive_int, get_tool_output_limits, _reset_tool_output_limits_cache, get_max_bytes, get_max_lines, get_max_line_length |
| [tool_result_storage.py](<E:/PythonCode/EasyChat/backend/hermes/tools/tool_result_storage.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具、结果相关实现（目录与文件名推断） | Tool result persistence -- preserves large outputs instead of truncating. / 符号 _resolve_storage_dir, _safe_result_filename, generate_preview, _heredoc_marker, _write_to_sandbox, _build_persisted_message, maybe_persist_tool_result |
| [tool_search.py](<E:/PythonCode/EasyChat/backend/hermes/tools/tool_search.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具、搜索相关实现（目录与文件名推断） | Progressive tool disclosure ("tool search") for Hermes Agent. / 符号 ToolSearchConfig, _safe_int, _safe_float, load_config, _core_tool_names, is_deferrable_tool_name, classify_tools |
| [url_safety.py](<E:/PythonCode/EasyChat/backend/hermes/tools/url_safety.py>) | 内嵌 Hermes 上游源码及项目适配内容中的url_safety 实现（目录与文件名推断） | URL safety checks — blocks requests to private/internal network addresses. / 符号 _proxy_is_configured, normalize_url_for_request, sensitive_query_param_name, has_sensitive_query_params, _global_allow_private_urls, _resolve_allow_private_urls, _reset_allow_private_cache |
| [vision_tools.py](<E:/PythonCode/EasyChat/backend/hermes/tools/vision_tools.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Vision Tools Module / 符号 _resolve_download_timeout, _detect_host_cpus, _resolve_vision_cpu_workers, _run_encode_on_cpu_executor, _image_url_shape_ok, _validate_image_url, _validate_image_url_async |
| [web_tools.py](<E:/PythonCode/EasyChat/backend/hermes/tools/web_tools.py>) | 内嵌 Hermes 上游源码及项目适配内容中的工具相关实现（目录与文件名推断） | Standalone Web Tools Module / 符号 _web_extract_url, _env_value, _has_env, _load_web_config, _registered_web_provider, _registered_web_provider_available, _list_registered_web_providers |
| [website_policy.py](<E:/PythonCode/EasyChat/backend/hermes/tools/website_policy.py>) | 内嵌 Hermes 上游源码及项目适配内容中的website_policy 实现（目录与文件名推断） | Website access policy helpers for URL-capable tools. / 符号 _get_default_config_path, WebsitePolicyError, _normalize_host, _normalize_rule, _iter_blocklist_file_rules, _load_policy_config, load_website_blocklist |
| [working_diff.py](<E:/PythonCode/EasyChat/backend/hermes/tools/working_diff.py>) | 内嵌 Hermes 上游源码及项目适配内容中的working_diff 实现（目录与文件名推断） | Working-tree git diff collection shared by the CLI and gateway ''/diff''. / 符号 _run, _untracked_files, _untracked_diff, collect_working_diff |
| [write_approval.py](<E:/PythonCode/EasyChat/backend/hermes/tools/write_approval.py>) | 内嵌 Hermes 上游源码及项目适配内容中的审批相关实现（目录与文件名推断） | Write-approval gate + pending store for memory and skill writes. / 符号 write_approval_enabled, _normalize_enabled, _pending_dir, stage_write, list_pending, get_pending, discard_pending |
| [x_search_tool.py](<E:/PythonCode/EasyChat/backend/hermes/tools/x_search_tool.py>) | 内嵌 Hermes 上游源码及项目适配内容中的搜索、工具相关实现（目录与文件名推断） | X Search tool backed by xAI's built-in ''x_search'' Responses API tool. / 符号 _load_x_search_config, _get_x_search_model, _get_x_search_reasoning_effort, _get_x_search_timeout_seconds, _get_x_search_retries, _resolve_xai_bearer, check_x_search_requirements |
| [xai_http.py](<E:/PythonCode/EasyChat/backend/hermes/tools/xai_http.py>) | 内嵌 Hermes 上游源码及项目适配内容中的xai_http 实现（目录与文件名推断） | Shared helpers for direct xAI HTTP integrations. / 符号 has_xai_credentials, get_env_value, hermes_xai_user_agent, hermes_xai_default_headers, _load_config_section, _coerce_bool, _coerce_expires_after |

### backend/hermes/tools/environments/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/hermes/tools/environments/__init__.py>) | 内嵌 Hermes 上游源码及项目适配内容的包入口或导出（包结构） | Hermes execution environment backends. |
| [base.py](<E:/PythonCode/EasyChat/backend/hermes/tools/environments/base.py>) | 内嵌 Hermes 上游源码及项目适配内容中的base 实现（目录与文件名推断） | Base class for all Hermes execution environment backends. / 符号 _BoundedOutputCollector, set_activity_callback, _get_activity_callback, touch_activity_if_due, get_sandbox_dir, _pipe_stdin, _popen_bash |
| [daytona.py](<E:/PythonCode/EasyChat/backend/hermes/tools/environments/daytona.py>) | 内嵌 Hermes 上游源码及项目适配内容中的daytona 实现（目录与文件名推断） | Daytona cloud execution environment. / 符号 DaytonaEnvironment |
| [docker.py](<E:/PythonCode/EasyChat/backend/hermes/tools/environments/docker.py>) | 内嵌 Hermes 上游源码及项目适配内容中的docker 实现（目录与文件名推断） | Docker execution environment for sandboxed command execution. / 符号 _normalize_forward_env_names, _normalize_env_dict, _load_hermes_env_vars, _sanitize_label_value, _get_active_profile_name, reap_orphan_containers, _container_finished_at |
| [file_sync.py](<E:/PythonCode/EasyChat/backend/hermes/tools/environments/file_sync.py>) | 内嵌 Hermes 上游源码及项目适配内容中的文件相关实现（目录与文件名推断） | Shared file sync manager for remote execution backends. / 符号 iter_sync_files, _credential_host_paths, quoted_rm_command, quoted_mkdir_command, unique_parent_dirs, _sha256_file, FileSyncManager |
| [local.py](<E:/PythonCode/EasyChat/backend/hermes/tools/environments/local.py>) | 内嵌 Hermes 上游源码及项目适配内容中的local 实现（目录与文件名推断） | Local execution environment — spawn-per-call with session snapshot. / 符号 _msys_to_windows_path, _resolve_local_initial_cwd, _windows_to_msys_path, _bash_safe_path, _quote_bash_path, _cwd_usable, _resolve_safe_cwd |
| [managed_modal.py](<E:/PythonCode/EasyChat/backend/hermes/tools/environments/managed_modal.py>) | 内嵌 Hermes 上游源码及项目适配内容中的managed_modal 实现（目录与文件名推断） | Managed Modal environment backed by tool-gateway. / 符号 _request_timeout_env, _ManagedModalExecHandle, ManagedModalEnvironment |
| [modal.py](<E:/PythonCode/EasyChat/backend/hermes/tools/environments/modal.py>) | 内嵌 Hermes 上游源码及项目适配内容中的modal 实现（目录与文件名推断） | Modal cloud execution environment using the native Modal SDK directly. / 符号 _load_snapshots, _save_snapshots, _direct_snapshot_key, _get_snapshot_restore_candidate, _store_direct_snapshot, _delete_direct_snapshot, _ensure_modal_sdk |
| [modal_utils.py](<E:/PythonCode/EasyChat/backend/hermes/tools/environments/modal_utils.py>) | 内嵌 Hermes 上游源码及项目适配内容中的modal_utils 实现（目录与文件名推断） | Shared Hermes-side execution flow for Modal transports. / 符号 PreparedModalExec, ModalExecStart, wrap_modal_stdin_heredoc, wrap_modal_sudo_pipe, BaseModalExecutionEnvironment |
| [singularity.py](<E:/PythonCode/EasyChat/backend/hermes/tools/environments/singularity.py>) | 内嵌 Hermes 上游源码及项目适配内容中的singularity 实现（目录与文件名推断） | Singularity/Apptainer persistent container environment. / 符号 _find_singularity_executable, _ensure_singularity_available, _load_snapshots, _save_snapshots, _get_scratch_dir, _get_apptainer_cache_dir, _get_or_build_sif |
| [ssh.py](<E:/PythonCode/EasyChat/backend/hermes/tools/environments/ssh.py>) | 内嵌 Hermes 上游源码及项目适配内容中的ssh 实现（目录与文件名推断） | SSH remote execution environment with ControlMaster connection persistence. / 符号 _ensure_ssh_available, SSHEnvironment |

### backend/integrations/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/integrations/__init__.py>) | 模型、MCP、搜索、语音等外部能力适配的包入口或导出（包结构） | 按目录和文件类型定位 |
| [llm.py](<E:/PythonCode/EasyChat/backend/integrations/llm.py>) | 模型、MCP、搜索、语音等外部能力适配中的llm 实现（目录与文件名推断） | 辅助文本生成（OpenAI 兼容 /chat/completions）。 / 符号 TextGenerator, OpenAICompatibleTextGenerator |
| [mcp.py](<E:/PythonCode/EasyChat/backend/integrations/mcp.py>) | 模型、MCP、搜索、语音等外部能力适配中的MCP相关实现（目录与文件名推断） | WeKnora 等远程 MCP 的窄配置/结果适配（架构 §6、R04）。 / 符号 McpServerConfig, McpServerStatus, McpRegistryState, classify_error, McpAdapter |
| [news.py](<E:/PythonCode/EasyChat/backend/integrations/news.py>) | 模型、MCP、搜索、语音等外部能力适配中的news 实现（目录与文件名推断） | AI 前沿资讯：多源 RSS/Atom 抓取、确定性排序与可选中文摘要。 / 符号 NewsSource, NewsItem, NewsDigest, FeedFetcher, HttpxFeedFetcher, NewsService, parse_feed |
| [pdf.py](<E:/PythonCode/EasyChat/backend/integrations/pdf.py>) | 模型、MCP、搜索、语音等外部能力适配中的PDF相关实现（目录与文件名推断） | PDF 能力 Adapter：默认关闭；未启用/未安装依赖时明确不可用，不 import 渲染栈。 / 符号 PdfRenderer, DisabledPdfRenderer, SubprocessPdfRenderer, build_pdf_renderer |
| [script_runner.py](<E:/PythonCode/EasyChat/backend/integrations/script_runner.py>) | 模型、MCP、搜索、语音等外部能力适配中的script_runner 实现（目录与文件名推断） | 脚本 Runner Adapter：默认关闭；只有显式启用且通过隔离验收才可自动执行。 / 符号 DisabledScriptRunner, _inside, LocalSubprocessRunner, build_default_runner |
| [search.py](<E:/PythonCode/EasyChat/backend/integrations/search.py>) | 模型、MCP、搜索、语音等外部能力适配中的搜索相关实现（目录与文件名推断） | Hermes 可选搜索 Provider 的装配桥。 / 符号 _bing_fallback_result, ensure_ddgs_provider, _bing_search, _unwrap_bing_url |
| [speech.py](<E:/PythonCode/EasyChat/backend/integrations/speech.py>) | 模型、MCP、搜索、语音等外部能力适配中的语音相关实现（目录与文件名推断） | 语音转写适配：云端 OpenAI 兼容优先，本地 faster-whisper 可选。 / 符号 Transcript, SpeechError, SpeechToText, _is_silk, _duration_seconds, _to_wav, OpenAICompatibleSTT |

### backend/modules/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/__init__.py>) | 按业务领域组织的公开服务与路由的包入口或导出（包结构） | 按目录和文件类型定位 |

### backend/modules/access/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/access/__init__.py>) | 用户、角色、权限与能力判定的Python包入口或导出（领域位置与文件名推断） | 按目录和文件类型定位 |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/access/api.py>) | 用户、角色、权限与能力判定的领域公开服务、授权和业务操作（领域位置与文件名推断） | access 模块公开接口：认证、Principal、授权与用户/角色管理。 / 符号 _validate_secret, validate_deployment_secret, _b64url, _b64url_decode, AccessService, principal_role |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/access/contracts.py>) | 用户、角色、权限与能力判定的领域数据结构、协议与共享常量（领域位置与文件名推断） | access 模块公开契约与权限注册数据（权限整改 v2）。 / 符号 _perm, permission_catalog, UserSnapshot, RoleInfo, PermissionOverride |
| [policy.py](<E:/PythonCode/EasyChat/backend/modules/access/policy.py>) | 用户、角色、权限与能力判定的授权或业务策略判定（领域位置与文件名推断） | 纯函数权限规则（架构 §6）：优先级为 revoke > grant > 角色；super_admin 取全集。 / 符号 effective_permissions, effective_toolsets, can_manage_resource |
| [repository.py](<E:/PythonCode/EasyChat/backend/modules/access/repository.py>) | 用户、角色、权限与能力判定的SQL读写、持久化状态与事务操作（领域位置与文件名推断） | access 模块 SQLite 数据访问。 / 符号 hash_password, needs_rehash, verify_password, parse_toolsets, AccessRepository |
| [routes.py](<E:/PythonCode/EasyChat/backend/modules/access/routes.py>) | 用户、角色、权限与能力判定的HTTP接口、请求校验与服务调用（领域位置与文件名推断） | access 模块 HTTP 路由：薄适配层，不执行 SQL、不持有全局状态。 / 符号 RegisterRequest, LoginRequest, SetRoleRequest, SetStatusRequest, SetPermRequest, CreateRoleRequest, UpdateRoleRequest |

### backend/modules/assistant/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/assistant/__init__.py>) | 会话、运行、消息和统一助手调度的Python包入口或导出（领域位置与文件名推断） | 按目录和文件类型定位 |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/assistant/api.py>) | 会话、运行、消息和统一助手调度的领域公开服务、授权和业务操作（领域位置与文件名推断） | Assistant 统一执行入口（架构 §4）：Web/微信/定时任务共用。 / 符号 AssistantService |
| [compat.py](<E:/PythonCode/EasyChat/backend/modules/assistant/compat.py>) | 按业务领域组织的公开服务与路由中的compat 实现（目录与文件名推断） | assistant 旧 HTTP 兼容：上传复用 files；反馈和执行审批返回明确能力状态。 / 符号 build_assistant_compat_router |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/assistant/contracts.py>) | 会话、运行、消息和统一助手调度的领域数据结构、协议与共享常量（领域位置与文件名推断） | Assistant 统一执行入口的公开契约（架构 §4）。 / 符号 RunCommand, RunReceipt, RunEvent |
| [dispatcher.py](<E:/PythonCode/EasyChat/backend/modules/assistant/dispatcher.py>) | 会话、运行、消息和统一助手调度的请求/事件分派与执行调度（领域位置与文件名推断） | run 执行调度器：唯一前台 worker（架构 §10 起始容量：foreground active=1）。 / 符号 RunDispatcher, _safe_attachment_name |
| [events.py](<E:/PythonCode/EasyChat/backend/modules/assistant/events.py>) | 按业务领域组织的公开服务与路由中的events 实现（目录与文件名推断） | run 事件环形缓存与订阅（架构 §4）。 / 符号 _RunBuffer, EventBus |
| [repository.py](<E:/PythonCode/EasyChat/backend/modules/assistant/repository.py>) | 会话、运行、消息和统一助手调度的SQL读写、持久化状态与事务操作（领域位置与文件名推断） | assistant 模块数据访问：sessions/runs/conversations 写入口。 / 符号 normalize_channel_scope, AssistantRepository |
| [routes.py](<E:/PythonCode/EasyChat/backend/modules/assistant/routes.py>) | 会话、运行、消息和统一助手调度的HTTP接口、请求校验与服务调用（领域位置与文件名推断） | Web 兼容路由：旧 /chat/stream SSE 契约 → 统一 Assistant（A09）。 / 符号 StreamPostBody, _sse_frame, build_web_chat_router, _make_command, _resume_from |
| [transcript.py](<E:/PythonCode/EasyChat/backend/modules/assistant/transcript.py>) | 按业务领域组织的公开服务与路由中的transcript 实现（目录与文件名推断） | assistant 的只读消息投影。 / 符号 load_run_messages |

### backend/modules/briefing/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/briefing/__init__.py>) | 简报内容生成与业务编排的Python包入口或导出（领域位置与文件名推断） | 简报模块：确定性数据 → 模板/受控生成 → 投递。 |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/briefing/api.py>) | 简报内容生成与业务编排的领域公开服务、授权和业务操作（领域位置与文件名推断） | 简报生成：数据只来自模块公开接口；模板兜底，模型输出必须过数字护栏。 / 符号 BriefingService, kind_label |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/briefing/contracts.py>) | 简报内容生成与业务编排的领域数据结构、协议与共享常量（领域位置与文件名推断） | 简报公开契约。 / 符号 BriefingData, BriefingResult |
| [worker.py](<E:/PythonCode/EasyChat/backend/modules/briefing/worker.py>) | 简报内容生成与业务编排的后台作业消费和生命周期推进（领域位置与文件名推断） | 简报 worker：认领 briefing.build，生成后按安静时段延迟投递。 / 符号 BriefingWorker |

### backend/modules/channels/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/channels/__init__.py>) | 渠道绑定、微信入站与命令处理的Python包入口或导出（领域位置与文件名推断） | channels 模块：账号绑定、归一化入站消息、iLink 生命周期。 |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/channels/api.py>) | 渠道绑定、微信入站与命令处理的领域公开服务、授权和业务操作（领域位置与文件名推断） | channels 模块公开接口：账号/绑定/扫码生命周期 + 入站归一化处理。 / 符号 ChannelService, _binding_dict, _default_media_text, _iso_from_epoch, _envelope_of, _message_from_envelope |
| [commands.py](<E:/PythonCode/EasyChat/backend/modules/channels/commands.py>) | 渠道绑定、微信入站与命令处理的确定性命令解析与业务路由（领域位置与文件名推断） | 微信命令路由（不经过模型、不产生模型费用）。 / 符号 ProfilesCommands, MemoryCommands, LedgerCommands, InboxCommands, SchedulingCommands, SuperagentIntakeCommands, CommandServices |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/channels/contracts.py>) | 渠道绑定、微信入站与命令处理的领域数据结构、协议与共享常量（领域位置与文件名推断） | channels 模块公开契约（架构 §3.1、§4、§5.2）。 / 符号 ChannelTransportError, ChannelTarget, ChannelAccount, ChannelBinding, MediaRef, InboundMessage, MediaIngestResult |
| [repository.py](<E:/PythonCode/EasyChat/backend/modules/channels/repository.py>) | 渠道绑定、微信入站与命令处理的SQL读写、持久化状态与事务操作（领域位置与文件名推断） | channels 模块数据访问：账号、绑定、接收事件。 / 符号 _account_from_row, _binding_from_row, ChannelRepository, _load_credentials |
| [routes.py](<E:/PythonCode/EasyChat/backend/modules/channels/routes.py>) | 渠道绑定、微信入站与命令处理的HTTP接口、请求校验与服务调用（领域位置与文件名推断） | 渠道 HTTP 路由：账号/扫码/绑定/监听状态。 / 符号 AccountCreateBody, StatusBody, BindingCreateBody, build_channels_router |
| [safety.py](<E:/PythonCode/EasyChat/backend/modules/channels/safety.py>) | 渠道绑定、微信入站与命令处理的渠道消息安全与输入策略（领域位置与文件名推断） | 入站安全兜底：危机表达用固定资源回复，不交给模型自由发挥。 / 符号 detect_crisis |

### backend/modules/channels/wechat/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/channels/wechat/__init__.py>) | 渠道绑定、微信入站与命令处理的Python包入口或导出（领域位置与文件名推断） | 微信 iLink Adapter：传输、扫码、解析、长轮询与媒体引用。 |
| [account.py](<E:/PythonCode/EasyChat/backend/modules/channels/wechat/account.py>) | 渠道绑定、微信入站与命令处理的扫码绑定、认证与渠道HTTP请求（领域位置与文件名推断） | iLink 协议 Adapter：HTTP 传输、扫码登录、文本发送。 / 符号 _monotonic, pause_session, is_session_paused, remaining_pause_seconds, assert_session_active, _reset_session_guard_for_test, classify_channel_error |
| [listener.py](<E:/PythonCode/EasyChat/backend/modules/channels/wechat/listener.py>) | 渠道绑定、微信入站与命令处理的渠道长轮询和入站监听生命周期（领域位置与文件名推断） | 微信长轮询监听器：真实状态机、游标持久化、消息归一化后交给 ChannelService。 / 符号 ListenerThrottled, WeChatListener, StreamLookupError |
| [media.py](<E:/PythonCode/EasyChat/backend/modules/channels/wechat/media.py>) | 渠道绑定、微信入站与命令处理的媒体下载、解密与大小边界（领域位置与文件名推断） | 媒体引用 → 受限本地文件 + 附件元数据的下载/解密 Adapter。 / 符号 MediaFetchError, FetchedMedia, MediaFetcher, _pkcs7_unpad, _parse_aes_key, decrypt_aes128_ecb, _download_url |
| [parser.py](<E:/PythonCode/EasyChat/backend/modules/channels/wechat/parser.py>) | 渠道绑定、微信入站与命令处理的外部消息/文件格式归一化解析（领域位置与文件名推断） | iLink 入站消息 → 统一 InboundMessage。 / 符号 _item_url, _item_aes_key, _media_ref, fingerprint_of, parse_inbound |
| [urlpolicy.py](<E:/PythonCode/EasyChat/backend/modules/channels/wechat/urlpolicy.py>) | 渠道绑定、微信入站与命令处理的下载与跳转URL允许范围（领域位置与文件名推断） | 微信媒体下载的出网白名单（防 SSRF，审计 #6）。 / 符号 is_allowed_media_url |

### backend/modules/delivery/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/delivery/__init__.py>) | 外发队列、微信/邮件投递与重试的Python包入口或导出（领域位置与文件名推断） | delivery 模块：目标/产物/分块/重试与微信文本投递。 |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/delivery/api.py>) | 外发队列、微信/邮件投递与重试的领域公开服务、授权和业务操作（领域位置与文件名推断） | delivery 模块公开接口：把已确定的最终内容可靠地投递到目标渠道。 / 符号 CompositeDeliverySender, DeliveryService, _is_wechat_target, _render_for_target, _view |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/delivery/contracts.py>) | 外发队列、微信/邮件投递与重试的领域数据结构、协议与共享常量（领域位置与文件名推断） | delivery 模块公开契约（架构 §5.2/§5.3、Task 8）。 / 符号 DeliveryTarget, ChannelTargetLike, target_from_channel, SendResult, DeliverySender, DeliveryLease, DeliveryView |
| [reports.py](<E:/PythonCode/EasyChat/backend/modules/delivery/reports.py>) | 按业务领域组织的公开服务与路由中的reports 实现（目录与文件名推断） | 报告生成与投递（Task 14）：先落不可变 artifact，再入投递账本。 / 符号 ReportService |
| [repository.py](<E:/PythonCode/EasyChat/backend/modules/delivery/repository.py>) | 外发队列、微信/邮件投递与重试的SQL读写、持久化状态与事务操作（领域位置与文件名推断） | delivery 模块数据访问：artifacts / deliveries / delivery_parts。 / 符号 _lease_from_row, DeliveryRepository, target_to_json |
| [routes.py](<E:/PythonCode/EasyChat/backend/modules/delivery/routes.py>) | 外发队列、微信/邮件投递与重试的HTTP接口、请求校验与服务调用（领域位置与文件名推断） | 投递状态 HTTP 路由（只读；发送由 worker 完成）。 / 符号 build_delivery_router |
| [smtp.py](<E:/PythonCode/EasyChat/backend/modules/delivery/smtp.py>) | 按业务领域组织的公开服务与路由中的smtp 实现（目录与文件名推断） | SMTP 配置/收件人与邮件发送 Adapter（Task 14）。默认关闭，未启用不建立连接。 / 符号 _token_expiry_iso, validate_single_address, EmailConfigView, EmailConfigBody, EmailRecipientBody, EmailRepository, EmailService |
| [wechat.py](<E:/PythonCode/EasyChat/backend/modules/delivery/wechat.py>) | 按业务领域组织的公开服务与路由中的wechat 实现（目录与文件名推断） | 微信文本发送 Adapter：把 delivery 的目标映射到 Task 7 的 iLink 通道。 / 符号 WeChatErrorClass, classify_wechat_error, DisabledDeliverySender, WeChatTextSender |
| [worker.py](<E:/PythonCode/EasyChat/backend/modules/delivery/worker.py>) | 外发队列、微信/邮件投递与重试的后台作业消费和生命周期推进（领域位置与文件名推断） | 投递 worker：唯一后台循环，按账本认领到期记录并调用发送适配器。 / 符号 DeliveryWorker |

### backend/modules/evolution/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/evolution/__init__.py>) | 反馈驱动的技能/记忆演进的Python包入口或导出（领域位置与文件名推断） | evolution 模块：唯一学习调度、证据、预算与经验（Task 11）。 |
| [adoption.py](<E:/PythonCode/EasyChat/backend/modules/evolution/adoption.py>) | 按业务领域组织的公开服务与路由中的adoption 实现（目录与文件名推断） | 候选采用/回滚：只切 skills 的 active 指针，记录验证与采用证据。 / 符号 AdoptionService |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/evolution/api.py>) | 反馈驱动的技能/记忆演进的领域公开服务、授权和业务操作（领域位置与文件名推断） | evolution 公开接口：唯一学习调度入口、证据、预算与经验写入。 / 符号 EvolutionService |
| [budget.py](<E:/PythonCode/EasyChat/backend/modules/evolution/budget.py>) | 按业务领域组织的公开服务与路由中的budget 实现（目录与文件名推断） | 进化预算：按用户每日/单次上限预留与核销，跨重启持久化。 / 符号 Reservation, BudgetStatus, BudgetManager |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/evolution/contracts.py>) | 反馈驱动的技能/记忆演进的领域数据结构、协议与共享常量（领域位置与文件名推断） | evolution 模块公开契约（Task 11）：学习任务、证据、预算与经验。 / 符号 LearningEvidence, LearningResult, EvolutionTaskView, ExperienceView, Learner |
| [evidence.py](<E:/PythonCode/EasyChat/backend/modules/evolution/evidence.py>) | 按业务领域组织的公开服务与路由中的evidence 实现（目录与文件名推断） | 经验形成（Task 11）：把可追溯反馈整理为经验；Task 12 再生成技能候选。 / 符号 default_learner |
| [proposal.py](<E:/PythonCode/EasyChat/backend/modules/evolution/proposal.py>) | 按业务领域组织的公开服务与路由中的proposal 实现（目录与文件名推断） | 候选生成：只调用 skills.propose，不直接写文件或改验证器。 / 符号 ProposalService |
| [repository.py](<E:/PythonCode/EasyChat/backend/modules/evolution/repository.py>) | 反馈驱动的技能/记忆演进的SQL读写、持久化状态与事务操作（领域位置与文件名推断） | evolution 数据访问：学习任务、经验与暂停开关。 / 符号 _task, _experience, EvolutionRepository |
| [routes.py](<E:/PythonCode/EasyChat/backend/modules/evolution/routes.py>) | 反馈驱动的技能/记忆演进的HTTP接口、请求校验与服务调用（领域位置与文件名推断） | 进化路由：经验查看与显式回滚；验证/采用在服务层由证据驱动。 / 符号 RollbackBody, build_evolution_router |
| [runner_contracts.py](<E:/PythonCode/EasyChat/backend/modules/evolution/runner_contracts.py>) | 按业务领域组织的公开服务与路由中的runner_contracts 实现（目录与文件名推断） | 受限脚本 Runner 契约（Task 13）：输入只含 artifact 引用与显式能力，不传业务凭证。 / 符号 RunnerLimits, RunnerCapabilities, RunnerInput, RunnerResult, ScriptRunner |
| [validation.py](<E:/PythonCode/EasyChat/backend/modules/evolution/validation.py>) | 反馈驱动的技能/记忆演进的输入或文件合法性检查（领域位置与文件名推断） | 候选验证：固定顺序 schema/能力 → baseline+candidate 同环境回放 → 回归判定。 / 符号 RegressionCase, CaseOutcome, ValidationReport, _passes, validate_candidate |
| [worker.py](<E:/PythonCode/EasyChat/backend/modules/evolution/worker.py>) | 反馈驱动的技能/记忆演进的后台作业消费和生命周期推进（领域位置与文件名推断） | 唯一后台学习 worker：单并发认领 evolution.learn，暂停时不再认领。 / 符号 EvolutionWorker |

### backend/modules/files/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/files/__init__.py>) | 文件存储、引用、归属与生命周期的Python包入口或导出（领域位置与文件名推断） | files 模块：唯一文件持久保存/读取/下载/生命周期入口（设计 §3–§5）。 |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/files/api.py>) | 文件存储、引用、归属与生命周期的领域公开服务、授权和业务操作（领域位置与文件名推断） | files 模块唯一公开入口：保存 / 读取 / 引用 / 删除影响 / 对账 / 提取记录。 / 符号 FileService, _safe_display_name |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/files/contracts.py>) | 文件存储、引用、归属与生命周期的领域数据结构、协议与共享常量（领域位置与文件名推断） | files 模块公开契约。 / 符号 SaveMetadata, FileRecord, UploadResult, DeleteImpact, ReconcileReport |
| [lifecycle.py](<E:/PythonCode/EasyChat/backend/modules/files/lifecycle.py>) | 文件存储、引用、归属与生命周期的资源生命周期与清理（领域位置与文件名推断） | 文件生命周期：派生内容过期清理、容量水位、删除范围协调。 / 符号 SweepResult, FileLifecycle |
| [local_store.py](<E:/PythonCode/EasyChat/backend/modules/files/local_store.py>) | 文件存储、引用、归属与生命周期的本地文件对象存储（领域位置与文件名推断） | 本地磁盘文件存储 Adapter（设计 §4）。 / 符号 kind_for, detect_content_mime, verified_extension, LocalFileStore, _aiter_chunks, _SyncChunks, _safe_unlink |
| [reconcile.py](<E:/PythonCode/EasyChat/backend/modules/files/reconcile.py>) | 文件存储、引用、归属与生命周期的持久化记录与实际工件对账（领域位置与文件名推断） | 中断恢复对账（设计 §4）：文件系统与 SQLite 之间没有原子事务。 / 符号 reconcile_files, _file_id_for_key, _find_orphans |
| [repository.py](<E:/PythonCode/EasyChat/backend/modules/files/repository.py>) | 文件存储、引用、归属与生命周期的SQL读写、持久化状态与事务操作（领域位置与文件名推断） | files 模块数据访问：stored_files / upload_receipts / file_references / file_extractions。 / 符号 FileRepository |
| [routes.py](<E:/PythonCode/EasyChat/backend/modules/files/routes.py>) | 文件存储、引用、归属与生命周期的HTTP接口、请求校验与服务调用（领域位置与文件名推断） | files HTTP 路由：薄适配层，授权/保存/引用规则全部在 FileService。 / 符号 file_payload, build_files_router |
| [validation.py](<E:/PythonCode/EasyChat/backend/modules/files/validation.py>) | 文件存储、引用、归属与生命周期的输入或文件合法性检查（领域位置与文件名推断） | 受控内容校验：图片像素上限与压缩容器展开上限（设计 §6）。 / 符号 image_dimensions, _webp_dimensions, _jpeg_dimensions, validate_image_size, ArchiveInfo, inspect_zip |

### backend/modules/inbox/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/inbox/__init__.py>) | 收藏/收件箱内容管理的Python包入口或导出（领域位置与文件名推断） | 稍后读：链接/文件/截图的轻量收件箱。 |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/inbox/api.py>) | 收藏/收件箱内容管理的领域公开服务、授权和业务操作（领域位置与文件名推断） | 收件箱服务：owner 隔离、同 URL 去重更新、链接富化入队。 / 符号 InboxService |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/inbox/contracts.py>) | 收藏/收件箱内容管理的领域数据结构、协议与共享常量（领域位置与文件名推断） | 收件箱公开契约。 / 符号 InboxItem |
| [enrich.py](<E:/PythonCode/EasyChat/backend/modules/inbox/enrich.py>) | 按业务领域组织的公开服务与路由中的enrich 实现（目录与文件名推断） | 链接富化：只抓 http/https 公网页面；拒绝内网/环回/元数据地址与重定向绕过。 / 符号 UnsafeUrl, _default_resolver, is_public_url, _TextParser, parse_html, LinkEnricher |
| [repository.py](<E:/PythonCode/EasyChat/backend/modules/inbox/repository.py>) | 收藏/收件箱内容管理的SQL读写、持久化状态与事务操作（领域位置与文件名推断） | 收件箱 SQL（owner 隔离在每条查询的 WHERE 中）。 / 符号 _view, InboxRepository |
| [routes.py](<E:/PythonCode/EasyChat/backend/modules/inbox/routes.py>) | 收藏/收件箱内容管理的HTTP接口、请求校验与服务调用（领域位置与文件名推断） | 收件箱 HTTP 路由：列表/搜索/保存/归档/删除。 / 符号 SaveBody, item_as_dict, build_inbox_router |
| [worker.py](<E:/PythonCode/EasyChat/backend/modules/inbox/worker.py>) | 收藏/收件箱内容管理的后台作业消费和生命周期推进（领域位置与文件名推断） | 收件箱富化 worker：只抓链接，失败标记 failed，不重试到天荒地老。 / 符号 InboxWorker |

### backend/modules/ledger/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/ledger/__init__.py>) | 账单导入、候选确认、统计与报告的Python包入口或导出（领域位置与文件名推断） | 账本模块公开入口（业务只允许从这里取 LedgerService）。 |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/ledger/api.py>) | 账单导入、候选确认、统计与报告的领域公开服务、授权和业务操作（领域位置与文件名推断） | 账本服务：导入状态机、去重提交、退款核对、受控统计与图片候选。 / 符号 _Control, _import_view, _transaction_view, _parsed_from_row, LedgerService, _refund_candidate_window, _provider_of |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/ledger/contracts.py>) | 账单导入、候选确认、统计与报告的领域数据结构、协议与共享常量（领域位置与文件名推断） | ledger 模块公开契约（设计 §7–§10）。 / 符号 LedgerCommitError, LedgerControlMismatch, LedgerAlreadyCommitted, ColumnMapping, FormatMatch, ParsedRow, ControlTotals |
| [extraction.py](<E:/PythonCode/EasyChat/backend/modules/ledger/extraction.py>) | 按业务领域组织的公开服务与路由中的extraction 实现（目录与文件名推断） | 账单截图识别候选（F6，设计 §7 图片识别）。 / 符号 VisionField, _FieldInput, VisionPort, candidate_from_vision, apply_corrections, is_ready_for_confirmation, candidate_payload |
| [identity.py](<E:/PythonCode/EasyChat/backend/modules/ledger/identity.py>) | 按业务领域组织的公开服务与路由中的identity 实现（目录与文件名推断） | 交易身份、去重、合并与状态机（设计 §8「账本模型、幂等和导入事务」）。 / 符号 _int_or_none, _account_part, _role_part, _direction_part, _iso_text, _minute_bucket, _timestamp_key |
| [intent.py](<E:/PythonCode/EasyChat/backend/modules/ledger/intent.py>) | 按业务领域组织的公开服务与路由中的intent 实现（目录与文件名推断） | 意图路由：自然语言 → 受控动作（导入预览 / 查询 / 修正 / 报告 / 退款核对）。 / 符号 PlannerPort, IntentDecision, _days_in_month, _month_range, _shift_month, plan_from_text, classify |
| [normalization.py](<E:/PythonCode/EasyChat/backend/modules/ledger/normalization.py>) | 按业务领域组织的公开服务与路由中的normalization 实现（目录与文件名推断） | 账本语义标准化：金额、时间、方向、状态、事件角色、稳定指纹。 / 符号 detect_currency, parse_money, format_money, _localize, parse_occurred_at, _from_excel_serial, normalize_direction |
| [query.py](<E:/PythonCode/EasyChat/backend/modules/ledger/query.py>) | 按业务领域组织的公开服务与路由中的query 实现（目录与文件名推断） | QueryPlan 验证与参数化 SQL 编译（files-ledger 设计 §9–§10，增量计划 F8）。 / 符号 CompiledQuery, escape_like, _require_int, _require_bool, _assert_no_nul, _reject_unknown, _require_text |
| [refunds.py](<E:/PythonCode/EasyChat/backend/modules/ledger/refunds.py>) | 按业务领域组织的公开服务与路由中的refunds 实现（目录与文件名推断） | 退款匹配建议与退款额度校验（设计 §8/§9）。 / 符号 _Original, _int_or_none, _moment, _within_days, _note_tokens, _collect_originals, _resolve |
| [reports.py](<E:/PythonCode/EasyChat/backend/modules/ledger/reports.py>) | 按业务领域组织的公开服务与路由中的reports 实现（目录与文件名推断） | 账本报告渲染：只做确定性排版，不做任何金额计算。 / 符号 render_report, render_report_html, _money, _period_text, _render_markdown, _render_csv |
| [repository.py](<E:/PythonCode/EasyChat/backend/modules/ledger/repository.py>) | 账单导入、候选确认、统计与报告的SQL读写、持久化状态与事务操作（领域位置与文件名推断） | ledger 数据访问：只被 LedgerService 使用，不对外暴露。 / 符号 _json, _loads, LedgerRepository, _source_row, _analysis_row, _iter_rows |
| [routes.py](<E:/PythonCode/EasyChat/backend/modules/ledger/routes.py>) | 账单导入、候选确认、统计与报告的HTTP接口、请求校验与服务调用（领域位置与文件名推断） | ledger HTTP 路由：薄适配层，规则/权限/计算全部在 LedgerService。 / 符号 AccountBody, ImportBody, CommitBody, TransactionPatch, CategoryBody, RenameBody, RuleBody |
| [tools.py](<E:/PythonCode/EasyChat/backend/modules/ledger/tools.py>) | 按业务领域组织的公开服务与路由中的工具相关实现（目录与文件名推断） | 账本工具面（给运行时/LLM 调用的受控入口）。 / 符号 LedgerToolbox, handle_message |
| [worker.py](<E:/PythonCode/EasyChat/backend/modules/ledger/worker.py>) | 账单导入、候选确认、统计与报告的后台作业消费和生命周期推进（领域位置与文件名推断） | 账本解析 worker：认领 ledger.parse job，幂等解析后完成/重试。 / 符号 LedgerWorker |

### backend/modules/ledger/parsers/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/ledger/parsers/__init__.py>) | 账单导入、候选确认、统计与报告的Python包入口或导出（领域位置与文件名推断） | 账单解析入口：格式探测 + 按文件类型分发。 / 符号 detect_format, parse_saved_file, _decode_head, _has_wechat_header, _split_any |
| [base.py](<E:/PythonCode/EasyChat/backend/modules/ledger/parsers/base.py>) | 按业务领域组织的公开服务与路由中的base 实现（目录与文件名推断） | 解析器公共构件：表头识别、单行标准化、控制总额与声明区间提取。 / 符号 BillParseError, ParseOptions, normalize_header, match_header, mapping_indexes, build_row, looks_like_data |
| [generic_csv.py](<E:/PythonCode/EasyChat/backend/modules/ledger/parsers/generic_csv.py>) | 按业务领域组织的公开服务与路由中的generic_csv 实现（目录与文件名推断） | 通用 CSV 解析：必须由用户显式提供列映射（模型不得猜列）。 / 符号 parse_generic_csv |
| [wechat_csv.py](<E:/PythonCode/EasyChat/backend/modules/ledger/parsers/wechat_csv.py>) | 按业务领域组织的公开服务与路由中的wechat_csv 实现（目录与文件名推断） | CSV 账单解析：编码/分隔符自适应，表头按内容识别，支持引号内换行。 / 符号 decode_text, detect_delimiter, iter_csv_rows, parse_wechat_csv, parse_csv_text, _has_totals, _append_control_line |
| [wechat_xlsx.py](<E:/PythonCode/EasyChat/backend/modules/ledger/parsers/wechat_xlsx.py>) | 按业务领域组织的公开服务与路由中的wechat_xlsx 实现（目录与文件名推断） | 微信支付 XLSX 账单解析：表头按内容识别，说明/汇总行不计入数据。 / 符号 parse_wechat_xlsx, _has_totals, _parse_sheet, _adopt_header, _consume |

### backend/modules/memory/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/memory/__init__.py>) | 个人记忆、检索、修订和遗忘的Python包入口或导出（领域位置与文件名推断） | memory 模块：事实/偏好、事件、经验及版本、反馈与遗忘。 |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/memory/api.py>) | 个人记忆、检索、修订和遗忘的领域公开服务、授权和业务操作（领域位置与文件名推断） | memory 模块公开接口：recall / remember / revise / forget / feedback。 / 符号 MemoryService |
| [capture.py](<E:/PythonCode/EasyChat/backend/modules/memory/capture.py>) | 按业务领域组织的公开服务与路由中的capture 实现（目录与文件名推断） | 显式记忆捕获：LLM 候选提取 + 无模型时的确定性降级。 / 符号 should_capture, should_extract, extract_content, candidate_from_user_message, candidate_from_model_payload |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/memory/contracts.py>) | 个人记忆、检索、修订和遗忘的领域数据结构、协议与共享常量（领域位置与文件名推断） | memory 模块公开契约（架构 §8、Task 9）。 / 符号 SourceRef, MemoryCandidate, MemoryRecord, RecallItem, RecallResult, ForgetResult, SignalReceipt |
| [extractor.py](<E:/PythonCode/EasyChat/backend/modules/memory/extractor.py>) | 按业务领域组织的公开服务与路由中的extractor 实现（目录与文件名推断） | 记忆候选提取：只做结构化校验与保守过滤，不调用模型编造内容。 / 符号 ExtractionError, validate_candidate, candidate_from_payload |
| [repository.py](<E:/PythonCode/EasyChat/backend/modules/memory/repository.py>) | 个人记忆、检索、修订和遗忘的SQL读写、持久化状态与事务操作（领域位置与文件名推断） | memory 数据访问：单一 SQLite 记忆模型、版本、反馈、遗忘规则与幂等信号。 / 符号 _sources, dump_sources, _memory, MemoryRepository, content_hash, source_hash |
| [retrieval.py](<E:/PythonCode/EasyChat/backend/modules/memory/retrieval.py>) | 按业务领域组织的公开服务与路由中的retrieval 实现（目录与文件名推断） | 记忆召回：有限候选、相关性排序、token 预算与来源。 / 符号 tokenize, expand_terms, wants_old_memories, estimate_tokens, _recency_bonus, recall |
| [routes.py](<E:/PythonCode/EasyChat/backend/modules/memory/routes.py>) | 个人记忆、检索、修订和遗忘的HTTP接口、请求校验与服务调用（领域位置与文件名推断） | memory HTTP 路由：薄适配层，权限/规则在 MemoryService。 / 符号 RecallBody, SourceRefBody, RememberBody, ReviseBody, FeedbackBody, ForgetBody, _record |
| [worker.py](<E:/PythonCode/EasyChat/backend/modules/memory/worker.py>) | 个人记忆、检索、修订和遗忘的后台作业消费和生命周期推进（领域位置与文件名推断） | 记忆提取 worker：认领 memory.extract/memory.signal job，幂等应用后完成/重试。 / 符号 MemoryWorker |

### backend/modules/models/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/models/__init__.py>) | 模型供应商、配置、密钥与路由的Python包入口或导出（领域位置与文件名推断） | 按目录和文件类型定位 |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/models/api.py>) | 模型供应商、配置、密钥与路由的领域公开服务、授权和业务操作（领域位置与文件名推断） | models 模块公开接口：模型配置管理与 run 模型选择。 / 符号 ModelsService |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/models/contracts.py>) | 模型供应商、配置、密钥与路由的领域数据结构、协议与共享常量（领域位置与文件名推断） | models 模块公开契约：模型配置与选择（架构 §6）。 / 符号 ModelProfile, ModelSelection |
| [repository.py](<E:/PythonCode/EasyChat/backend/modules/models/repository.py>) | 模型供应商、配置、密钥与路由的SQL读写、持久化状态与事务操作（领域位置与文件名推断） | models 模块 SQLite 数据访问与密钥保护。 / 符号 ModelsRepository |
| [routes.py](<E:/PythonCode/EasyChat/backend/modules/models/routes.py>) | 模型供应商、配置、密钥与路由的HTTP接口、请求校验与服务调用（领域位置与文件名推断） | models 兼容路由（Task 15）：保留旧 Config 页使用的 HTTP 契约。 / 符号 ModelConfigBody, MultimodalBody, ReasoningBody, FallbackBody, _legacy, build_models_router |

### backend/modules/profiles/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/profiles/__init__.py>) | 个人偏好、时区、静默窗口与情绪关怀的Python包入口或导出（领域位置与文件名推断） | 用户人格、偏好与情绪设置模块。 |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/profiles/api.py>) | 个人偏好、时区、静默窗口与情绪关怀的领域公开服务、授权和业务操作（领域位置与文件名推断） | profiles 公开接口：人格渲染、安静时段、情绪设置与按日情绪条目。 / 符号 ProfilesService, _parse_model_mood, _valid_timezone, _parse_hhmm, _validate_date, _validate_update, profile_as_dict |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/profiles/contracts.py>) | 个人偏好、时区、静默窗口与情绪关怀的领域数据结构、协议与共享常量（领域位置与文件名推断） | profiles 模块公开契约：人格、安静时段与情绪条目。 / 符号 ProfileView, QuietWindow, MoodEntry, MoodWeek, CareDecision, MoodDeleteResult |
| [repository.py](<E:/PythonCode/EasyChat/backend/modules/profiles/repository.py>) | 个人偏好、时区、静默窗口与情绪关怀的SQL读写、持久化状态与事务操作（领域位置与文件名推断） | profiles 数据访问：assistant_profiles 与 mood_entries（模块内唯一 SQL）。 / 符号 _profile, _timestamp_not_before, _mood, ProfilesRepository, _round_div, _consecutive_low |
| [routes.py](<E:/PythonCode/EasyChat/backend/modules/profiles/routes.py>) | 个人偏好、时区、静默窗口与情绪关怀的HTTP接口、请求校验与服务调用（领域位置与文件名推断） | profiles HTTP 路由：人格/安静时段/情绪设置与查看。 / 符号 ProfilePatch, MoodDeleteBody, build_profiles_router |
| [worker.py](<E:/PythonCode/EasyChat/backend/modules/profiles/worker.py>) | 个人偏好、时区、静默窗口与情绪关怀的后台作业消费和生命周期推进（领域位置与文件名推断） | 情绪采样 worker：只有用户显式 opt-in 后才落库；同一 run 幂等。 / 符号 MoodWorker |

### backend/modules/scheduling/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/scheduling/__init__.py>) | 定时任务、调度与无人值守触发的Python包入口或导出（领域位置与文件名推断） | scheduling 模块：提醒计划、到期实例与唯一调度器。 |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/scheduling/api.py>) | 定时任务、调度与无人值守触发的领域公开服务、授权和业务操作（领域位置与文件名推断） | scheduling 模块公开接口：建立提醒、恢复到期实例、生成投递请求。 / 符号 SchedulingService, _validate_timezone, _parse_iso_datetime, _parse_until, _iso_range_bound, _parse_at, _validate_daily |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/scheduling/contracts.py>) | 定时任务、调度与无人值守触发的领域数据结构、协议与共享常量（领域位置与文件名推断） | scheduling 模块公开契约：提醒计划与到期实例。 / 符号 ScheduleSpec, ScheduleView, OccurrenceView |
| [repository.py](<E:/PythonCode/EasyChat/backend/modules/scheduling/repository.py>) | 定时任务、调度与无人值守触发的SQL读写、持久化状态与事务操作（领域位置与文件名推断） | scheduling 数据访问：计划、实例与下次执行时间。 / 符号 _schedule, _occurrence, SchedulingRepository |
| [routes.py](<E:/PythonCode/EasyChat/backend/modules/scheduling/routes.py>) | 定时任务、调度与无人值守触发的HTTP接口、请求校验与服务调用（领域位置与文件名推断） | 提醒 HTTP 路由：薄适配；目标默认取用户有效微信绑定，也可显式邮箱。 / 符号 ScheduleCreateBody, ScheduleStatusBody, _schedule_dict, build_scheduling_router |
| [scheduler.py](<E:/PythonCode/EasyChat/backend/modules/scheduling/scheduler.py>) | 按业务领域组织的公开服务与路由中的scheduler 实现（目录与文件名推断） | 唯一提醒调度器：周期 tick，把到期计划变成实例+投递请求。 / 符号 Scheduler |

### backend/modules/skills/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/skills/__init__.py>) | 技能及版本管理的Python包入口或导出（领域位置与文件名推断） | skills 模块：个人技能资产、不可变版本与激活指针（Task 10）。 |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/skills/api.py>) | 技能及版本管理的领域公开服务、授权和业务操作（领域位置与文件名推断） | skills 模块公开接口：提出候选版本、激活/回滚、pin/归档与运行时快照。 / 符号 validate_skill_name, validate_content, validate_source, SkillService |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/skills/contracts.py>) | 技能及版本管理的领域数据结构、协议与共享常量（领域位置与文件名推断） | skills 模块公开契约（架构 §9、Task 10）。 / 符号 SkillVersionView, SkillView, SkillSnapshot |
| [repository.py](<E:/PythonCode/EasyChat/backend/modules/skills/repository.py>) | 技能及版本管理的SQL读写、持久化状态与事务操作（领域位置与文件名推断） | skills 模块数据访问：技能元数据、不可变版本与激活指针（架构 §5.2/§5.3）。 / 符号 _skill, _version, SkillRepository |
| [routes.py](<E:/PythonCode/EasyChat/backend/modules/skills/routes.py>) | 技能及版本管理的HTTP接口、请求校验与服务调用（领域位置与文件名推断） | skills HTTP 路由：薄适配层，权限/版本规则全部在 SkillService。 / 符号 ProposeBody, ActivateBody, RollbackBody, PatchBody, _version_payload, _skill_payload, build_skills_router |
| [versions.py](<E:/PythonCode/EasyChat/backend/modules/skills/versions.py>) | 按业务领域组织的公开服务与路由中的versions 实现（目录与文件名推断） | 技能版本内容存储：不可变文件、sha256 指纹与越界防护。 / 符号 default_content_root, SkillContentStore |

### backend/modules/superagent/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/superagent/__init__.py>) | 编码任务、工作区、验证、验收与 Draft PR的Python包入口或导出（领域位置与文件名推断） | superagent 模块：微信收需求 → 后台编码代理 → 自动提 PR → 回执微信。 |
| [acceptance.py](<E:/PythonCode/EasyChat/backend/modules/superagent/acceptance.py>) | 编码任务、工作区、验证、验收与 Draft PR的逐项验收、证据与评审反馈（领域位置与文件名推断） | 逐项验收账本（工作包四）：轮次写入、检查项评审决定与返工联动。 / 符号 apply_coverage_gate, summarize, AcceptanceRepository |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/superagent/api.py>) | 编码任务、工作区、验证、验收与 Draft PR的领域公开服务、授权和业务操作（领域位置与文件名推断） | superagent 服务：受理、配置、查询与生命周期控制（T1）。 / 符号 SuperagentService, _now |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/superagent/contracts.py>) | 编码任务、工作区、验证、验收与 Draft PR的领域数据结构、协议与共享常量（领域位置与文件名推断） | superagent 公开契约：状态机、phase、attempt、输入与报告（方案 §5）。 / 符号 SuperagentTask, TaskAttempt, TaskInput, TaskReport, SuperagentSettings |
| [credentials.py](<E:/PythonCode/EasyChat/backend/modules/superagent/credentials.py>) | 编码任务、工作区、验证、验收与 Draft PR的任务凭据注入和脱敏（领域位置与文件名推断） | superagent 凭证与仓库地址（T2，方案 §6 Git 发布）。 / 符号 RepoRef, RepoUrlError, parse_repo_url, sanitize_text, credential_helper_source, credential_helper_gitconfig, git_auth_env |
| [github.py](<E:/PythonCode/EasyChat/backend/modules/superagent/github.py>) | 编码任务、工作区、验证、验收与 Draft PR的GitHub分支/PR接口适配（领域位置与文件名推断） | GitHub REST 客户端（T2/T4）：Draft PR 创建、按 head/base 查询复用。 / 符号 PullRequest, PRClient, HttpxPRClient, _headers |
| [intake.py](<E:/PythonCode/EasyChat/backend/modules/superagent/intake.py>) | 编码任务、工作区、验证、验收与 Draft PR的任务输入受理、命令与归属解析（领域位置与文件名推断） | superagent 微信命令入口（T5，方案 §4 微信交互）。 / 符号 SuperagentIntake, _AmbiguousTask, short_id |
| [repository.py](<E:/PythonCode/EasyChat/backend/modules/superagent/repository.py>) | 编码任务、工作区、验证、验收与 Draft PR的SQL读写、持久化状态与事务操作（领域位置与文件名推断） | superagent 数据访问：任务（CAS 状态机）、attempt、输入、报告与部署级配置。 / 符号 _task, _attempt, _input, _report, SuperagentRepository, load_verify_profile |
| [routes.py](<E:/PythonCode/EasyChat/backend/modules/superagent/routes.py>) | 编码任务、工作区、验证、验收与 Draft PR的HTTP接口、请求校验与服务调用（领域位置与文件名推断） | superagent HTTP 路由：capabilities、配置、任务受理（幂等）、inputs、增量事件。 / 符号 AcceptanceCheckBody, AcceptanceRoundBody, AcceptanceDecisionBody, SettingsBody, TaskCreateBody, TaskInputBody, _task_dict |
| [runner.py](<E:/PythonCode/EasyChat/backend/modules/superagent/runner.py>) | 编码任务、工作区、验证、验收与 Draft PR的执行器调用和结果转换（领域位置与文件名推断） | superagent runner 接缝（T3，方案 §6 工作区和 runner）。 / 符号 RunnerRequest, RunnerOutcome, CodingRunner, HermesCodingRunner |
| [verification.py](<E:/PythonCode/EasyChat/backend/modules/superagent/verification.py>) | 编码任务、工作区、验证、验收与 Draft PR的验证命令、退出码和证据生成（领域位置与文件名推断） | superagent 验证门禁（T4，方案 §6 验证与预算）。 / 符号 VerifyCommand, VerifyResult, load_verify_commands, run_verification, _run_one, _terminate_tree, workspace_within |
| [webhooks.py](<E:/PythonCode/EasyChat/backend/modules/superagent/webhooks.py>) | 编码任务、工作区、验证、验收与 Draft PR的GitHub事件验签、去重与反馈（领域位置与文件名推断） | GitHub webhook 回流（T7，方案 §9）。 / 符号 verify_signature, extract_fields, WebhookService, build_superagent_webhook_router |
| [worker.py](<E:/PythonCode/EasyChat/backend/modules/superagent/worker.py>) | 编码任务、工作区、验证、验收与 Draft PR的后台作业消费和生命周期推进（领域位置与文件名推断） | superagent worker：以 attempt 为单位执行任务（T1–T4）。 / 符号 TaskCancelledError, _TaskBlockedError, _PublishContext, SuperagentWorker, _run_git, _terminate_tree |
| [workspaces.py](<E:/PythonCode/EasyChat/backend/modules/superagent/workspaces.py>) | 编码任务、工作区、验证、验收与 Draft PR的Git工作区路径与生命周期（领域位置与文件名推断） | superagent 工作区（T3，方案 §6 执行与恢复）。 / 符号 WorkspaceError, workspace_key, workspace_path, repo_workspace_key_for_repo |

### backend/modules/usage/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/modules/usage/__init__.py>) | 模型调用用量、成本与统计的Python包入口或导出（领域位置与文件名推断） | 按目录和文件类型定位 |
| [api.py](<E:/PythonCode/EasyChat/backend/modules/usage/api.py>) | 模型调用用量、成本与统计的领域公开服务、授权和业务操作（领域位置与文件名推断） | usage 模块公开接口：唯一计量写入口（架构 §7）。 / 符号 utc_now, UsageService |
| [contracts.py](<E:/PythonCode/EasyChat/backend/modules/usage/contracts.py>) | 模型调用用量、成本与统计的领域数据结构、协议与共享常量（领域位置与文件名推断） | usage 模块公开契约：唯一计量入口的数据结构（架构 §7）。 / 符号 NormalizedUsage, UsageRecord |
| [repository.py](<E:/PythonCode/EasyChat/backend/modules/usage/repository.py>) | 模型调用用量、成本与统计的SQL读写、持久化状态与事务操作（领域位置与文件名推断） | usage 模块 SQLite 数据访问：明细与日汇总同事务写入。 / 符号 stat_date_for, _usage_row, UsageRepository |
| [routes.py](<E:/PythonCode/EasyChat/backend/modules/usage/routes.py>) | 模型调用用量、成本与统计的HTTP接口、请求校验与服务调用（领域位置与文件名推断） | usage 模块 HTTP 路由：排行与明细（保留 trace.view / trace.manage 语义）。 / 符号 build_usage_router |

### backend/platform/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/platform/__init__.py>) | SQLite、迁移、设置、持久队列和备份的包入口或导出（包结构） | 平台层：SQLite、迁移、任务队列与配置。 |
| [backup.py](<E:/PythonCode/EasyChat/backend/platform/backup.py>) | 一致性备份、校验和恢复支撑（路径与入口核查） | 文件 + SQLite 的一致性备份/校验/恢复（部署运维用，非业务代码）。 / 符号 BackupError, BackupInfo, VerifyResult, _sha256, _utc_stamp, _snapshot_sqlite, _ready_files |
| [jobs.py](<E:/PythonCode/EasyChat/backend/platform/jobs.py>) | 持久化后台作业的认领、租约与重试（路径与入口核查） | 小型持久任务队列（架构 §5.3 jobs 状态机、§10）。 / 符号 Lease, JobQueue |
| [settings.py](<E:/PythonCode/EasyChat/backend/platform/settings.py>) | 环境读取、运行目录与能力开关（路径与入口核查） | 强类型配置与能力开关（架构 §3 platform/settings.py）。 / 符号 AppSettings, default_settings, settings_from_environment |
| [sqlite.py](<E:/PythonCode/EasyChat/backend/platform/sqlite.py>) | SQLite连接、事务、版本守卫与迁移执行（路径与入口核查） | SQLite 平台模块：连接、事务、迁移与 PRAGMA（架构 §5.4）。 / 符号 utc_now_iso, Database, _wal_safe_version, MigrationError, load_migrations, _migration_applied, _split_sql_statements |

### backend/platform/migrations/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [0001_core.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0001_core.sql>) | 追加式数据库迁移，主题 0001_core（迁移文件名） | 按目录和文件类型定位 |
| [0002_models_key.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0002_models_key.sql>) | 追加式数据库迁移，主题 0002_models_key（迁移文件名） | 按目录和文件类型定位 |
| [0003_runs_updated_at.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0003_runs_updated_at.sql>) | 追加式数据库迁移，主题 0003_runs_updated_at（迁移文件名） | 按目录和文件类型定位 |
| [0004_channels.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0004_channels.sql>) | 追加式数据库迁移，主题 0004_channels（迁移文件名） | 按目录和文件类型定位 |
| [0005_delivery.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0005_delivery.sql>) | 追加式数据库迁移，主题 0005_delivery（迁移文件名） | 按目录和文件类型定位 |
| [0006_memory.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0006_memory.sql>) | 追加式数据库迁移，主题 0006_memory（迁移文件名） | 按目录和文件类型定位 |
| [0007_skills.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0007_skills.sql>) | 追加式数据库迁移，主题 0007_skills（迁移文件名） | 按目录和文件类型定位 |
| [0008_evolution.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0008_evolution.sql>) | 追加式数据库迁移，主题 0008_evolution（迁移文件名） | 按目录和文件类型定位 |
| [0009_evolution_validation.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0009_evolution_validation.sql>) | 追加式数据库迁移，主题 0009_evolution_validation（迁移文件名） | 按目录和文件类型定位 |
| [0010_delivery_email.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0010_delivery_email.sql>) | 追加式数据库迁移，主题 0010_delivery_email（迁移文件名） | 按目录和文件类型定位 |
| [0011_files.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0011_files.sql>) | 追加式数据库迁移，主题 0011_files（迁移文件名） | 按目录和文件类型定位 |
| [0012_ledger.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0012_ledger.sql>) | 追加式数据库迁移，主题 0012_ledger（迁移文件名） | 按目录和文件类型定位 |
| [0013_ledger_note.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0013_ledger_note.sql>) | 追加式数据库迁移，主题 0013_ledger_note（迁移文件名） | 按目录和文件类型定位 |
| [0014_wechat_ac.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0014_wechat_ac.sql>) | 追加式数据库迁移，主题 0014_wechat_ac（迁移文件名） | 按目录和文件类型定位 |
| [0015_mood_samples.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0015_mood_samples.sql>) | 追加式数据库迁移，主题 0015_mood_samples（迁移文件名） | 按目录和文件类型定位 |
| [0016_mood_care_window.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0016_mood_care_window.sql>) | 追加式数据库迁移，主题 0016_mood_care_window（迁移文件名） | 按目录和文件类型定位 |
| [0017_care_epoch.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0017_care_epoch.sql>) | 追加式数据库迁移，主题 0017_care_epoch（迁移文件名） | 按目录和文件类型定位 |
| [0018_email_recipient_verified.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0018_email_recipient_verified.sql>) | 追加式数据库迁移，主题 0018_email_recipient_verified（迁移文件名） | 按目录和文件类型定位 |
| [0019_superagent.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0019_superagent.sql>) | 追加式数据库迁移，主题 0019_superagent（迁移文件名） | 按目录和文件类型定位 |
| [0020_superagent_v2.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0020_superagent_v2.sql>) | 追加式数据库迁移，主题 0020_superagent_v2（迁移文件名） | 按目录和文件类型定位 |
| [0021_channels_inbox.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0021_channels_inbox.sql>) | 追加式数据库迁移，主题 0021_channels_inbox（迁移文件名） | 按目录和文件类型定位 |
| [0022_superagent_webhooks.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0022_superagent_webhooks.sql>) | 追加式数据库迁移，主题 0022_superagent_webhooks（迁移文件名） | 按目录和文件类型定位 |
| [0023_permission_lifecycle.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0023_permission_lifecycle.sql>) | 追加式数据库迁移，主题 0023_permission_lifecycle（迁移文件名） | 按目录和文件类型定位 |
| [0024_superagent_auto_fix.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0024_superagent_auto_fix.sql>) | 追加式数据库迁移，主题 0024_superagent_auto_fix（迁移文件名） | 按目录和文件类型定位 |
| [0025_superagent_acceptance.sql](<E:/PythonCode/EasyChat/backend/platform/migrations/0025_superagent_acceptance.sql>) | 追加式数据库迁移，主题 0025_superagent_acceptance（迁移文件名） | 按目录和文件类型定位 |
| [__init__.py](<E:/PythonCode/EasyChat/backend/platform/migrations/__init__.py>) | SQLite、迁移、设置、持久队列和备份的包入口或导出（包结构） | 版本化迁移 SQL 目录。每个文件 'NNNN_名称.sql' 是一个原子迁移。 |

### backend/runtime/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/runtime/__init__.py>) | 执行引擎接口与 Hermes 适配的包入口或导出（包结构） | 按目录和文件类型定位 |
| [contracts.py](<E:/PythonCode/EasyChat/backend/runtime/contracts.py>) | 业务可见的执行请求、事件与ExecutionRuntime接口（路径与入口核查） | Runtime Seam 契约（架构 §4.1）。 / 符号 RuntimeRequest, RuntimeEvent, ExecutionRuntime |

### backend/runtime/hermes/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/runtime/hermes/__init__.py>) | 执行引擎接口与 Hermes 适配的包入口或导出（包结构） | 按目录和文件类型定位 |
| [adapter.py](<E:/PythonCode/EasyChat/backend/runtime/hermes/adapter.py>) | 执行引擎接口与 Hermes 适配中的adapter 实现（目录与文件名推断） | Hermes Runtime Adapter：ExecutionRuntime 的唯一 Hermes 整合入口（架构 §4.1）。 / 符号 _AgentHandle, HermesRuntimeAdapter, _safe_result, _safe_tools |
| [agent_factory.py](<E:/PythonCode/EasyChat/backend/runtime/hermes/agent_factory.py>) | 执行引擎接口与 Hermes 适配中的代理相关实现（目录与文件名推断） | 真实 Hermes AIAgent 构建工厂。 / 符号 build_agent, _normalize_base_url, _strip_model_suffix, _reasoning_effort, _resolve_api_key, _fallback_profile |
| [memory_bridge.py](<E:/PythonCode/EasyChat/backend/runtime/hermes/memory_bridge.py>) | 执行引擎接口与 Hermes 适配中的记忆相关实现（目录与文件名推断） | Hermes MemoryProvider 桥接：只调用 memory 公开接口。 / 符号 MemoryBridge |
| [paths.py](<E:/PythonCode/EasyChat/backend/runtime/hermes/paths.py>) | 执行引擎接口与 Hermes 适配中的paths 实现（目录与文件名推断） | Hermes 运行环境引导。 / 符号 ensure_hermes_environment |
| [sessions.py](<E:/PythonCode/EasyChat/backend/runtime/hermes/sessions.py>) | 执行引擎接口与 Hermes 适配中的会话相关实现（目录与文件名推断） | 会话映射与引擎历史恢复（架构 §5.1）。 / 符号 SessionMapper |
| [skills_bridge.py](<E:/PythonCode/EasyChat/backend/runtime/hermes/skills_bridge.py>) | 执行引擎接口与 Hermes 适配中的技能相关实现（目录与文件名推断） | Hermes 技能读写桥接：只调用 skills 模块公开接口。 / 符号 SkillsBridge |
| [tools.py](<E:/PythonCode/EasyChat/backend/runtime/hermes/tools.py>) | 执行引擎接口与 Hermes 适配中的工具相关实现（目录与文件名推断） | Hermes 工具策略：安全项目工具注册与 toolset 解析。 / 符号 register_safe_project_tools, _tool_schema, _json_type, _is_async_tool, _make_handler, _ensure_hermes_loaded |
| [usage_bridge.py](<E:/PythonCode/EasyChat/backend/runtime/hermes/usage_bridge.py>) | 执行引擎接口与 Hermes 适配中的用量相关实现（目录与文件名推断） | usage_bridge：Hermes 真实请求与统一 call_id 关联（架构 §7）。 / 符号 snapshot, diff, begin_for_run, complete_for_run, raw_api_calls |

### backend/shared/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/shared/__init__.py>) | 跨模块身份上下文、错误、加密与文本基础设施的包入口或导出（包结构） | 按目录和文件类型定位 |
| [context.py](<E:/PythonCode/EasyChat/backend/shared/context.py>) | Principal和ExecutionContext等可信运行上下文（路径与入口核查） | 身份与执行上下文值对象。 / 符号 Principal, ExecutionContext |
| [crypto.py](<E:/PythonCode/EasyChat/backend/shared/crypto.py>) | 跨模块身份上下文、错误、加密与文本基础设施中的crypto 实现（目录与文件名推断） | 部署密钥保护的共享加解密（模型密钥与渠道凭证共用）。 / 符号 _derive_key, encrypt_secret, decrypt_secret, mask_secret |
| [errors.py](<E:/PythonCode/EasyChat/backend/shared/errors.py>) | 跨模块身份上下文、错误、加密与文本基础设施中的errors 实现（目录与文件名推断） | 跨模块错误码（架构 §11）。 / 符号 ErrorCode, AppError, UnauthenticatedError, ForbiddenError, NotFoundError, ConflictError, InvalidInputError |
| [identifiers.py](<E:/PythonCode/EasyChat/backend/shared/identifiers.py>) | 跨模块身份上下文、错误、加密与文本基础设施中的identifiers 实现（目录与文件名推断） | run/session/call 等 ID 的构造与校验。 / 符号 _new_id, new_run_id, new_session_id, new_call_id, new_job_id, new_delivery_id, new_part_id |
| [text.py](<E:/PythonCode/EasyChat/backend/shared/text.py>) | 跨模块身份上下文、错误、加密与文本基础设施中的text 实现（目录与文件名推断） | 共享文本切分：渠道发送与投递分块使用同一规则。 / 符号 split_text |
| [tool_context.py](<E:/PythonCode/EasyChat/backend/shared/tool_context.py>) | 工具可信身份、来源与上下文解析（路径与入口核查） | 工具执行身份：contextvar + RunnableConfig 双通道。 / 符号 ToolContext, current, set_current, reset_current, bind, from_config, resolve |
| [wechat_text.py](<E:/PythonCode/EasyChat/backend/shared/wechat_text.py>) | 跨模块身份上下文、错误、加密与文本基础设施中的wechat_text 实现（目录与文件名推断） | 微信纯文本渲染：微信不支持 Markdown，发送前做保守降级。 / 符号 to_wechat_text |

### backend/templates/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [pdf_report.html](<E:/PythonCode/EasyChat/backend/templates/pdf_report.html>) | 报告等输出模板中的PDF、报告相关实现（目录与文件名推断） | 按目录和文件类型定位 |

### backend/tools/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/tools/__init__.py>) | 模型可调用业务工具和保留的历史工具的包入口或导出（包结构） | 按目录和文件类型定位 |
| [code_executor.py](<E:/PythonCode/EasyChat/backend/tools/code_executor.py>) | 模型可调用业务工具和保留的历史工具中的执行相关实现（目录与文件名推断） | Code Mode 执行器 —— 让 Agent 写 Python 代码组合调用工具 / 符号 _load_daemon_executor_cls, _new_executor, _retire_poisoned_executor, _get_project_root, _CodeModeStats, get_code_mode_stats, FileOperationError |
| [data_visualization.py](<E:/PythonCode/EasyChat/backend/tools/data_visualization.py>) | 模型可调用业务工具和保留的历史工具中的data_visualization 实现（目录与文件名推断） | 数据可视化工具（fig_inter） / 符号 _init_fonts, _force_reset_fonts, _lock_font_settings, FigCodeInput, fig_inter, _fig_inter_impl |
| [kg_tools.py](<E:/PythonCode/EasyChat/backend/tools/kg_tools.py>) | 模型可调用业务工具和保留的历史工具中的工具相关实现（目录与文件名推断） | 知识图谱（Neo4j）查询工具集 / 符号 KGStatsInput, KGSearchInput, KGEntityDetailInput, KGCommunitiesInput, KGQualityInput, _get_kg_store, _get_user_id |
| [pdf_generator.py](<E:/PythonCode/EasyChat/backend/tools/pdf_generator.py>) | 模型可调用业务工具和保留的历史工具中的PDF相关实现（目录与文件名推断） | 通用数据分析报告 PDF 生成工具 / 符号 _runtime_project_root, _safe_report_filename, _resolve_base_font, _wrap_canvas_text, _convert_box_drawing, _normalize_text, _inline_markdown |
| [pdf_generator_weasyprint.py](<E:/PythonCode/EasyChat/backend/tools/pdf_generator_weasyprint.py>) | 模型可调用业务工具和保留的历史工具中的PDF相关实现（目录与文件名推断） | 现代化 PDF 报告生成器 - WeasyPrint + HTML/CSS / 符号 _init_gtk_dll_path, _convert_box_drawing, _markdown_to_html, _get_template_path, generate_report_pdf_weasyprint, generate_report_pdf |
| [table_scope.py](<E:/PythonCode/EasyChat/backend/tools/table_scope.py>) | 模型可调用业务工具和保留的历史工具中的table_scope 实现（目录与文件名推断） | Text2SQL 可查询表白名单（默认拒绝）—— 供 text_to_sql 与 database_semantic_index 共用。 / 符号 _queryable_tables, _queryable_tables_hint, _extract_table_refs, _scan_never_allowed_tables, _validate_tables |
| [text_to_sql.py](<E:/PythonCode/EasyChat/backend/tools/text_to_sql.py>) | 模型可调用业务工具和保留的历史工具中的text_to_sql 实现（目录与文件名推断） | Text2SQL 工具 — 基于 AgentForge 系统表的自然语言转 SQL 查询 / 符号 GetSchemaInput, QuerySQLInput, _validate_read_only, LimitValidationError, _ensure_limit, _record_sql_operation, _get_thread_id |
| [tool_output_guard.py](<E:/PythonCode/EasyChat/backend/tools/tool_output_guard.py>) | 模型可调用业务工具和保留的历史工具中的工具相关实现（目录与文件名推断） | 工具输出守卫 —— 即时截断 + 溢出到文件 + Agent 引导 + 溢出文件 TTL 清理 / 符号 should_truncate, truncate_tool_output, _smart_head_tail, _truncate_at_line_boundary, _get_spill_dir, _save_spill_file, _maybe_lazy_cleanup |
| [tools_decorator.py](<E:/PythonCode/EasyChat/backend/tools/tools_decorator.py>) | 模型可调用业务工具和保留的历史工具中的工具相关实现（目录与文件名推断） | AgentForge - 工具定义模板 / 符号 GetCurrentTimeInput, EchoInput, get_current_time, echo_tool, _get_thread_id, _current_user_id, _get_todo_key |

### backend/tools/business/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/backend/tools/business/__init__.py>) | 模型可调用业务工具和保留的历史工具的包入口或导出（包结构） | 按目录和文件类型定位 |
| [inbox_tools.py](<E:/PythonCode/EasyChat/backend/tools/business/inbox_tools.py>) | 模型可调用业务工具和保留的历史工具中的工具相关实现（目录与文件名推断） | 收件箱四工具：URL/附件保存、搜索、列表、归档；owner 只来自 ToolContext。 / 符号 SaveInput, SearchInput, ListInput, ItemInput, _ctx, _line, build_inbox_tools |
| [ledger_tools.py](<E:/PythonCode/EasyChat/backend/tools/business/ledger_tools.py>) | 模型可调用业务工具和保留的历史工具中的工具相关实现（目录与文件名推断） | 账本 5 个受控 LangChain 工具（不暴露提交能力）。 / 符号 ImportPreviewInput, AnalyzeInput, CorrectInput, ReportInput, RefundInput, format_minor, _decorate_amounts |
| [reminder_tools.py](<E:/PythonCode/EasyChat/backend/tools/business/reminder_tools.py>) | 模型可调用业务工具和保留的历史工具中的工具相关实现（目录与文件名推断） | 提醒四工具：身份只来自 ToolContext，目标只来自用户有效绑定。 / 符号 ReminderCreateInput, ReminderListInput, ReminderIdInput, ReminderSnoozeInput, _ctx, _target, _fmt |
| [superagent_tools.py](<E:/PythonCode/EasyChat/backend/tools/business/superagent_tools.py>) | 模型可调用业务工具和保留的历史工具中的工具相关实现（目录与文件名推断） | superagent 业务工具：微信对话里收集需求并受理编码任务（T5）。 / 符号 SubmitTaskInput, build_superagent_tools, _operation_key, _source_target_of |

### backend/tools/paper_reproduction/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [.env.example](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/.env.example>) | 本地环境/认证配置，仅说明路径职责，内容未展开（路径类型） | 按目录和文件类型定位 |
| [ENVIRONMENT_CONFIG.md](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/ENVIRONMENT_CONFIG.md>) | 模型可调用业务工具和保留的历史工具的说明、设计或验证文档，主题 ENVIRONMENT_CONFIG（目录与文件名推断） | 论文复现环境配置指南 |
| [FIX_GUIDE.md](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/FIX_GUIDE.md>) | 模型可调用业务工具和保留的历史工具的说明、设计或验证文档，主题 FIX_GUIDE（目录与文件名推断） | 论文复现系统 - 完整修复指南 |
| [__init__.py](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/__init__.py>) | 模型可调用业务工具和保留的历史工具的包入口或导出（包结构） | 论文复现工具包 / 符号 get_paper_reproduction_tools |
| [build_evidence_graph.py](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/build_evidence_graph.py>) | 模型可调用业务工具和保留的历史工具中的图数据相关实现（目录与文件名推断） | 证据图谱构建工具 / 符号 BuildEvidenceGraphInput, build_evidence_graph, _build_graph, _collect_evidence, _extract_run_evidence, _extract_metric_evidence, _extract_benchmark_evidence |
| [code_review.md](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/code_review.md>) | 模型可调用业务工具和保留的历史工具的说明、设计或验证文档，主题 code_review（目录与文件名推断） | 论文复现系统代码审查报告 |
| [code_review_second.md](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/code_review_second.md>) | 模型可调用业务工具和保留的历史工具的说明、设计或验证文档，主题 code_review_second（目录与文件名推断） | 论文复现系统第二轮修复报告 |
| [common_utils.py](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/common_utils.py>) | 模型可调用业务工具和保留的历史工具中的common_utils 实现（目录与文件名推断） | 论文复现系统公共工具函数 / 符号 PaperReproductionConfig, get_config, get_llm_instance, retry_on_failure, PerformanceMonitor, safe_write_file, safe_read_file |
| [diagnose_flow.py](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/diagnose_flow.py>) | 模型可调用业务工具和保留的历史工具中的diagnose_flow 实现（目录与文件名推断） | 论文复现系统诊断脚本 |
| [discover_repo.py](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/discover_repo.py>) | 模型可调用业务工具和保留的历史工具中的discover_repo 实现（目录与文件名推断） | GitHub 仓库发现工具 / 符号 _get_llm, DiscoverRepoInput, discover_repo, _build_search_queries, _extract_keywords, _search_github, _deduplicate_repos |
| [docker_error_handling_fix.md](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/docker_error_handling_fix.md>) | 模型可调用业务工具和保留的历史工具的说明、设计或验证文档，主题 docker_error_handling_fix（目录与文件名推断） | 论文复现系统 Docker 沙箱与错误处理修复报告 |
| [docker_sandbox.py](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/docker_sandbox.py>) | 模型可调用业务工具和保留的历史工具中的docker_sandbox 实现（目录与文件名推断） | Docker 沙箱执行工具 / 符号 DockerSandboxInput, docker_sandbox, _check_docker_available, _get_default_image, _create_container, _execute_in_container, _destroy_container |
| [environment_detection_design.md](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/environment_detection_design.md>) | 模型可调用业务工具和保留的历史工具的说明、设计或验证文档，主题 environment_detection_design（目录与文件名推断） | 论文复现环境智能检测设计 |
| [environment_selection_design.md](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/environment_selection_design.md>) | 模型可调用业务工具和保留的历史工具的说明、设计或验证文档，主题 environment_selection_design（目录与文件名推断） | 论文复现环境选择机制设计（借鉴 AGI-OpenResearch） |
| [evidence_graph_fix_report.md](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/evidence_graph_fix_report.md>) | 模型可调用业务工具和保留的历史工具的说明、设计或验证文档，主题 evidence_graph_fix_report（目录与文件名推断） | 证据图谱问题修复报告 |
| [extract_claim_rubric.py](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/extract_claim_rubric.py>) | 模型可调用业务工具和保留的历史工具中的extract_claim_rubric 实现（目录与文件名推断） | Claim Rubric 提取工具 / 符号 _get_llm, ClaimRubricInput, extract_claim_rubric, _build_extraction_prompt, _normalize_rubric, _normalize_claim_type, _store_rubric |
| [integration_test.py](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/integration_test.py>) | 模型可调用业务工具和保留的历史工具中的测试相关实现（目录与文件名推断） | 论文复现工具集成测试 |
| [neo4j_port_diagnosis.md](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/neo4j_port_diagnosis.md>) | 模型可调用业务工具和保留的历史工具的说明、设计或验证文档，主题 neo4j_port_diagnosis（目录与文件名推断） | Neo4j 端口映射问题诊断报告 |
| [no_repo_error_fix.md](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/no_repo_error_fix.md>) | 模型可调用业务工具和保留的历史工具的说明、设计或验证文档，主题 no_repo_error_fix（目录与文件名推断） | 论文复现系统"没有找到可用仓库"问题修复报告 |
| [parse_paper.py](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/parse_paper.py>) | 模型可调用业务工具和保留的历史工具中的论文相关实现（目录与文件名推断） | 论文解析工具 / 符号 _get_llm, PaperParseInput, parse_paper, _get_uploaded_file, _download_paper, _extract_text, _extract_pdf_text |
| [pull_images.py](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/pull_images.py>) | 模型可调用业务工具和保留的历史工具中的pull_images 实现（目录与文件名推断） | 论文复现系统镜像预拉取脚本 / 符号 check_docker, pull_image, check_image_exists, main |
| [security_isolation_architecture_fix.md](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/security_isolation_architecture_fix.md>) | 模型可调用业务工具和保留的历史工具的说明、设计或验证文档，主题 security_isolation_architecture_fix（目录与文件名推断） | 论文复现系统第三轮修复报告 — 数据隔离架构优化 |
| [security_isolation_fix.md](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/security_isolation_fix.md>) | 模型可调用业务工具和保留的历史工具的说明、设计或验证文档，主题 security_isolation_fix（目录与文件名推断） | 论文复现系统安全隔离修复报告 |
| [security_utils.py](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/security_utils.py>) | 模型可调用业务工具和保留的历史工具中的security_utils 实现（目录与文件名推断） | 命令注入防护验证函数 / 符号 validate_command, validate_file_id, sanitize_path |
| [test_full_flow.py](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/test_full_flow.py>) | 验证 full_flow 相关行为与回归（测试文件名推断） | 论文复现系统完整测试脚本 |
| [test_report.md](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/test_report.md>) | 验证 report 相关行为与回归（测试文件名推断） | 论文复现系统测试报告 |
| [test_tools.py](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/test_tools.py>) | 验证 tools 相关行为与回归（测试文件名推断） | 论文复现工具测试脚本 / 符号 test_parse_paper, test_extract_claim_rubric, test_discover_repo, test_docker_sandbox, test_debug_paper_code, test_build_evidence_graph, main |
| [zero_claims_diagnosis.md](<E:/PythonCode/EasyChat/backend/tools/paper_reproduction/zero_claims_diagnosis.md>) | 模型可调用业务工具和保留的历史工具的说明、设计或验证文档，主题 zero_claims_diagnosis（目录与文件名推断） | 论文复现系统"主张提取返回 0"问题诊断报告 |

### backend/utils/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [LLM_USAGE.md](<E:/PythonCode/EasyChat/backend/utils/LLM_USAGE.md>) | 公共辅助实现和保留的历史工具的说明、设计或验证文档，主题 LLM_USAGE（目录与文件名推断） | LLM用量和运行归属 |
| [crypto_utils.py](<E:/PythonCode/EasyChat/backend/utils/crypto_utils.py>) | 公共辅助实现和保留的历史工具中的crypto_utils 实现（目录与文件名推断） | API Key 加密工具 — AES-256-GCM，密钥从 JWT_SECRET 派生 / 符号 _derive_key, encrypt, decrypt, encrypt_memory_content, decrypt_memory_content, is_memory_encrypted |
| [encryption_utils.py](<E:/PythonCode/EasyChat/backend/utils/encryption_utils.py>) | 公共辅助实现和保留的历史工具中的encryption_utils 实现（目录与文件名推断） | 加密工具类 / 符号 _get_key, EncryptionUtils, get_encryption_utils |
| [exec_approval_recorder.py](<E:/PythonCode/EasyChat/backend/utils/exec_approval_recorder.py>) | 公共辅助实现和保留的历史工具中的审批相关实现（目录与文件名推断） | exec 审批记录器 — 命令执行审批决议的落库缓冲区（借鉴 Eyes exec_approval_recorder） / 符号 record, drain |
| [image_safety.py](<E:/PythonCode/EasyChat/backend/utils/image_safety.py>) | 公共辅助实现和保留的历史工具中的image_safety 实现（目录与文件名推断） | 图片安全处理模块 / 符号 detect_image_mime_type, validate_image_size, _rasterize_svg_to_png, _reencode_to_png, normalize_image, process_image_safe |
| [llm_usage.py](<E:/PythonCode/EasyChat/backend/utils/llm_usage.py>) | 公共辅助实现和保留的历史工具中的用量相关实现（目录与文件名推断） | Portable provider usage buckets and explicit per-run trace correlation. / 符号 current_trace_context, trace_context, note_api_request, _mapping, trace_usage |
| [log_utils.py](<E:/PythonCode/EasyChat/backend/utils/log_utils.py>) | 公共辅助实现和保留的历史工具中的log_utils 实现（目录与文件名推断） | 日志系统 - loguru 单例封装 / 符号 _get_shanghai_now, _patch_shanghai_time, _retry_on_lock, _append_and_remove, _pre_rotate_if_overdue, _compress_to_date_only, _cleanup_old_logs |
| [model_manager.py](<E:/PythonCode/EasyChat/backend/utils/model_manager.py>) | 公共辅助实现和保留的历史工具中的模型相关实现（目录与文件名推断） | 模型管理器 - 从数据库加载模型配置并构建LLM / 符号 ModelManager, get_model_manager, get_user_specific_model_manager, set_model_manager |
| [multimodal_detect.py](<E:/PythonCode/EasyChat/backend/utils/multimodal_detect.py>) | 公共辅助实现和保留的历史工具中的multimodal_detect 实现（目录与文件名推断） | 多模态模型检测工具 — 三层策略 / 符号 is_multimodal_model, _probe_cache_key, probe_image_support, check_model_multimodal |
| [mysql_db_manager.py](<E:/PythonCode/EasyChat/backend/utils/mysql_db_manager.py>) | 公共辅助实现和保留的历史工具中的历史MySQL相关实现（目录与文件名推断） | MySQL 数据库管理器 / 符号 _get_database_url, _init_engine, MySQLDBManager, get_db_manager |
| [port_killer.py](<E:/PythonCode/EasyChat/backend/utils/port_killer.py>) | 公共辅助实现和保留的历史工具中的port_killer 实现（目录与文件名推断） | 端口杀死工具 - 用于在启动前杀死占用指定端口的进程 / 符号 kill_port, _kill_port_windows, _kill_port_unix |
| [rate_limit.py](<E:/PythonCode/EasyChat/backend/utils/rate_limit.py>) | 公共辅助实现和保留的历史工具中的rate_limit 实现（目录与文件名推断） | 无凭据端点的进程内限流（登录/注册），零外部依赖。 / 符号 AuthRateLimiter, client_key, make_auth_rate_limit_middleware |
| [time_utils.py](<E:/PythonCode/EasyChat/backend/utils/time_utils.py>) | 公共辅助实现和保留的历史工具中的time_utils 实现（目录与文件名推断） | 符号 now_local_naive, now_local_iso, days_start |
| [todo_parser.py](<E:/PythonCode/EasyChat/backend/utils/todo_parser.py>) | 公共辅助实现和保留的历史工具中的todo_parser 实现（目录与文件名推断） | 任务解析工具 - 从工具输出中提取任务清单 / 符号 _normalize_status, _extract_bracket_content, _normalize_todo_items, _extract_todo_list_from_output, parse_todos_from_tool_output |
| [token_counter.py](<E:/PythonCode/EasyChat/backend/utils/token_counter.py>) | 公共辅助实现和保留的历史工具中的令牌/Token相关实现（目录与文件名推断） | Token 计算工具 - 使用 tiktoken 精确计算 token 数 / 符号 get_tokenizer, count_tokens, count_messages_tokens, format_tokens |
| [traced_llm.py](<E:/PythonCode/EasyChat/backend/utils/traced_llm.py>) | 公共辅助实现和保留的历史工具中的traced_llm 实现（目录与文件名推断） | TracedLLMClient — 带 trace 的轻量 LLM 客户端 / 符号 TracedResponse, TracedLLMClient |
| [when_resolver.py](<E:/PythonCode/EasyChat/backend/utils/when_resolver.py>) | 公共辅助实现和保留的历史工具中的when_resolver 实现（目录与文件名推断） | 自然语言时间解析 — 借鉴 Eyes when_resolver 的纯规则引擎（零 LLM 成本、可单测） / 符号 _parse_count, _start_of_day, _start_of_week, _start_of_month, _start_of_quarter, _add_months, resolve_when |

### docker/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [.env.example](<E:/PythonCode/EasyChat/docker/.env.example>) | 本地环境/认证配置，仅说明路径职责，内容未展开（路径类型） | 按目录和文件类型定位 |
| [Dockerfile](<E:/PythonCode/EasyChat/docker/Dockerfile>) | 镜像构建或容器服务编排（文件约定） | 按目录和文件类型定位 |
| [README.md](<E:/PythonCode/EasyChat/docker/README.md>) | 容器镜像、部署与运维脚本的说明、设计或验证文档，主题 README（目录与文件名推断） | EasyChat Docker 部署 |
| [daemon.json](<E:/PythonCode/EasyChat/docker/daemon.json>) | 容器镜像、部署与运维脚本的配置或结构化资源，主题 daemon（目录与文件名推断） | 按目录和文件类型定位 |
| [docker-compose.yml](<E:/PythonCode/EasyChat/docker/docker-compose.yml>) | 镜像构建或容器服务编排（文件约定） | 按目录和文件类型定位 |
| [fix_neo4j_port.ps1](<E:/PythonCode/EasyChat/docker/fix_neo4j_port.ps1>) | 修复相关启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |
| [health_check.sh](<E:/PythonCode/EasyChat/docker/health_check.sh>) | 检查相关启动、维护或诊断命令脚本，运行范围需按调用者核对（文件名推断） | 按目录和文件类型定位 |
| [requirements-core.txt](<E:/PythonCode/EasyChat/docker/requirements-core.txt>) | 容器镜像、部署与运维脚本中的requirements-core 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [requirements-hermes.txt](<E:/PythonCode/EasyChat/docker/requirements-hermes.txt>) | 容器镜像、部署与运维脚本中的requirements-hermes 实现（目录与文件名推断） | 按目录和文件类型定位 |

### docker/volumes/hermes/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [SOUL.md](<E:/PythonCode/EasyChat/docker/volumes/hermes/SOUL.md>) | 容器镜像、部署与运维脚本的说明、设计或验证文档，主题 SOUL（目录与文件名推断） | 按目录和文件类型定位 |

### docs/research/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [2026-11-03-harness2-assessment.md](<E:/PythonCode/EasyChat/docs/research/2026-11-03-harness2-assessment.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-03-harness2-assessment（目录与文件名推断） | Harness² 对 EasyChat 的适用性调研 |

### docs/reviews/2026-11-10/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [P0-takeover-record.md](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/P0-takeover-record.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 P0-takeover-record（目录与文件名推断） | P0 接管记录(2026-11-10) |
| [P1-owner-ruleset-checklist.md](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/P1-owner-ruleset-checklist.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 P1-owner-ruleset-checklist（目录与文件名推断） | P1 GitHub 仓库规则 owner 操作清单(权限不足,移交人类) |
| [P2-access-applied.md](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/P2-access-applied.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 P2-access-applied（目录与文件名推断） | P2 续作记录:access 四项修复已应用(2026-11-10) |
| [P2-entry-matrix.md](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/P2-entry-matrix.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 P2-entry-matrix（目录与文件名推断） | P2 权限入口矩阵(2026-11-10,静态扫描实测) |
| [P3-hermes-governance.md](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/P3-hermes-governance.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 P3-hermes-governance（目录与文件名推断） | P3 记录:Hermes 来源、集成点与遗留导入追踪(2026-11-10) |
| [P4-isolation-record.md](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/P4-isolation-record.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 P4-isolation-record（目录与文件名推断） | P4 记录:执行隔离、取消、进程回收与预算(2026-11-10) |
| [P5-publish-recovery-record.md](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/P5-publish-recovery-record.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 P5-publish-recovery-record（目录与文件名推断） | P5 记录:任务恢复、验证与 Draft PR 发布(2026-11-10) |
| [P6-wechat-intake-record.md](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/P6-wechat-intake-record.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 P6-wechat-intake-record（目录与文件名推断） | P6 记录:微信受理、追问、补充与回执(2026-11-10) |
| [P7-feedback-autofix-record.md](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/P7-feedback-autofix-record.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 P7-feedback-autofix-record（目录与文件名推断） | P7 记录:GitHub 反馈校验与有限自动修复(2026-11-10) |
| [P8-browser-acceptance.md](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/P8-browser-acceptance.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 P8-browser-acceptance（目录与文件名推断） | P8 记录:真实浏览器全功能验收(2026-11-10) |
| [access-fixes.draft.patch](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/access-fixes.draft.patch>) | 设计、实施、交接与验证资料中的access-fixes.draft 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [baseline-red.txt](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/baseline-red.txt>) | 设计、实施、交接与验证资料中的baseline-red 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [baseline-sha256.json](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/baseline-sha256.json>) | 设计、实施、交接与验证资料的配置或结构化资源，主题 baseline-sha256（目录与文件名推断） | 按目录和文件类型定位 |
| [draft-green.txt](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/draft-green.txt>) | 设计、实施、交接与验证资料中的draft-green 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [drill_backup_restore.py](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/drill_backup_restore.py>) | 设计、实施、交接与验证资料中的备份相关实现（目录与文件名推断） | P1 备份/恢复演练:真实数据备份 → 校验 → 隔离恢复 → 可读性核查。不修改任何生产数据。 |
| [escalation-brief.md](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/escalation-brief.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 escalation-brief（目录与文件名推断） | Access 修复草稿升级简报 |
| [exp_intake_natural_language.py](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/exp_intake_natural_language.py>) | 设计、实施、交接与验证资料中的exp_intake_natural_language 实现（目录与文件名推断） | ② 定性实验：同一装配下，两种措辞是否会触发 superagent_submit_task。 / 符号 _Stub |
| [hermes-provenance.json](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/hermes-provenance.json>) | 设计、实施、交接与验证资料的配置或结构化资源，主题 hermes-provenance（目录与文件名推断） | 按目录和文件类型定位 |
| [hermes_provenance.py](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/hermes_provenance.py>) | 设计、实施、交接与验证资料中的hermes_provenance 实现（目录与文件名推断） | P3-1 内核来源记录:AgentForge HEAD ↔ EasyChat 基线复制 ↔ EasyChat 后续补丁 三层比对。 / 符号 ls_tree |
| [perm_matrix.py](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/perm_matrix.py>) | 设计、实施、交接与验证资料中的perm_matrix 实现（目录与文件名推断） | P2 权限入口矩阵:逐键映射 service / HTTP routes / 微信与工具 / 前端 消费点。 / 符号 classify |
| [replay_access_draft.py](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/replay_access_draft.py>) | 设计、实施、交接与验证资料中的replay_access_draft 实现（目录与文件名推断） | Replay the review in an isolated temporary source copy, without editing the checkout. / 符号 main |
| [test_access_draft.py](<E:/PythonCode/EasyChat/docs/reviews/2026-11-10/test_access_draft.py>) | 验证 access_draft 相关行为与回归（测试文件名推断） | Offline regressions for the proposed access fixes. Use replay_access_draft.py. / 符号 access, user, test_concurrent_owner_losses_leave_one_active_owner, test_role_rename_preserves_members_permissions_and_toolsets, test_renaming_to_existing_role_rolls_back_members_and_grants, test_unknown_keys_are_iner |

### docs/reviews/2026-11-11/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [WP3-acceptance-trial.md](<E:/PythonCode/EasyChat/docs/reviews/2026-11-11/WP3-acceptance-trial.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 WP3-acceptance-trial（目录与文件名推断） | WP3 记录:Acceptance 本地试验(2026-11-11) |
| [WP4-backend-acceptance.md](<E:/PythonCode/EasyChat/docs/reviews/2026-11-11/WP4-backend-acceptance.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 WP4-backend-acceptance（目录与文件名推断） | WP4 记录（后端部分）:任务页逐项验收与返工闭环(2026-11-11) |
| [WP5-6-7-and-final.md](<E:/PythonCode/EasyChat/docs/reviews/2026-11-11/WP5-6-7-and-final.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 WP5-6-7-and-final（目录与文件名推断） | WP5/WP6/WP7 记录与最终汇总(2026-11-11) |

### docs/superpowers/plans/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [2026-11-03-easychat-implementation.md](<E:/PythonCode/EasyChat/docs/superpowers/plans/2026-11-03-easychat-implementation.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-03-easychat-implementation（目录与文件名推断） | EasyChat Implementation Plan |
| [2026-11-03-easychat-source-map.md](<E:/PythonCode/EasyChat/docs/superpowers/plans/2026-11-03-easychat-source-map.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-03-easychat-source-map（目录与文件名推断） | EasyChat 当前源码定位与兼容基线 |
| [2026-11-04-files-ledger-implementation.md](<E:/PythonCode/EasyChat/docs/superpowers/plans/2026-11-04-files-ledger-implementation.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-04-files-ledger-implementation（目录与文件名推断） | EasyChat Files and Ledger Implementation Plan |
| [2026-11-04-wechat-a-c-acceptance.md](<E:/PythonCode/EasyChat/docs/superpowers/plans/2026-11-04-wechat-a-c-acceptance.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-04-wechat-a-c-acceptance（目录与文件名推断） | 微信 A+C 验收报告与修复提示词（2026-11-05） |
| [2026-11-04-wechat-a-c-implementation.md](<E:/PythonCode/EasyChat/docs/superpowers/plans/2026-11-04-wechat-a-c-implementation.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-04-wechat-a-c-implementation（目录与文件名推断） | 微信 A+C 能力实施计划 |
| [2026-11-04-wechat-a-c-probes.md](<E:/PythonCode/EasyChat/docs/superpowers/plans/2026-11-04-wechat-a-c-probes.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-04-wechat-a-c-probes（目录与文件名推断） | P0.5 微信 A+C 外部探针记录 |
| [2026-11-09-permission-remediation-delivery.md](<E:/PythonCode/EasyChat/docs/superpowers/plans/2026-11-09-permission-remediation-delivery.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-09-permission-remediation-delivery（目录与文件名推断） | 权限整改交付记录（P0–P3） |
| [2026-11-09-permission-remediation.md](<E:/PythonCode/EasyChat/docs/superpowers/plans/2026-11-09-permission-remediation.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-09-permission-remediation（目录与文件名推断） | EasyChat 权限专项核查与整改方案 |
| [2026-11-09-project-review-and-wechat-superagent.md](<E:/PythonCode/EasyChat/docs/superpowers/plans/2026-11-09-project-review-and-wechat-superagent.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-09-project-review-and-wechat-superagent（目录与文件名推断） | EasyChat 项目检查与微信 Superagent 实施方案 |
| [2026-11-09-ui-repair-verification.md](<E:/PythonCode/EasyChat/docs/superpowers/plans/2026-11-09-ui-repair-verification.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-09-ui-repair-verification（目录与文件名推断） | 界面与功能回归修复记录 |
| [2026-11-10-superagent-production-execution.md](<E:/PythonCode/EasyChat/docs/superpowers/plans/2026-11-10-superagent-production-execution.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-10-superagent-production-execution（目录与文件名推断） | EasyChat 架构选型与整改执行方案 |
| [2026-11-11-wechat-task-acceptance-evolution.md](<E:/PythonCode/EasyChat/docs/superpowers/plans/2026-11-11-wechat-task-acceptance-evolution.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-11-wechat-ta[credential-like text redacted]（目录与文件名推断） | EasyChat 微信接入、任务协作与验收改造执行方案 |
| [2026-11-11-wechat-task-acceptance-executor-prompt.txt](<E:/PythonCode/EasyChat/docs/superpowers/plans/2026-11-11-wechat-task-acceptance-executor-prompt.txt>) | 设计、实施、交接与验证资料中的任务、验收、执行、提示词相关实现（目录与文件名推断） | 按目录和文件类型定位 |
| [easychat-execution-log.md](<E:/PythonCode/EasyChat/docs/superpowers/plans/easychat-execution-log.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 easychat-execution-log（目录与文件名推断） | EasyChat 执行日志 |
| [files-ledger-execution-log.md](<E:/PythonCode/EasyChat/docs/superpowers/plans/files-ledger-execution-log.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 files-ledger-execution-log（目录与文件名推断） | Files & Ledger 增量执行日志（F0–F11） |

### docs/superpowers/specs/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [2026-11-03-easychat-architecture.md](<E:/PythonCode/EasyChat/docs/superpowers/specs/2026-11-03-easychat-architecture.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-03-easychat-architecture（目录与文件名推断） | EasyChat 架构与工程规范 |
| [2026-11-03-easychat-design.md](<E:/PythonCode/EasyChat/docs/superpowers/specs/2026-11-03-easychat-design.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-03-easychat-design（目录与文件名推断） | EasyChat：轻量个人助手、记忆与自进化讨论稿 |
| [2026-11-03-personal-assistant-design.md](<E:/PythonCode/EasyChat/docs/superpowers/specs/2026-11-03-personal-assistant-design.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-03-personal-assistant-design（目录与文件名推断） | AgentForge 个人助手轻量化改造方案 |
| [2026-11-04-files-ledger-design.md](<E:/PythonCode/EasyChat/docs/superpowers/specs/2026-11-04-files-ledger-design.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-04-files-ledger-design（目录与文件名推断） | EasyChat 文件存储与微信账单分析增量设计 |
| [2026-11-04-wechat-a-c-design.md](<E:/PythonCode/EasyChat/docs/superpowers/specs/2026-11-04-wechat-a-c-design.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-04-wechat-a-c-design（目录与文件名推断） | EasyChat 微信「事务外脑 + 人格情绪层」设计（A+C） |
| [2026-11-11-android-family-client-design.md](<E:/PythonCode/EasyChat/docs/superpowers/specs/2026-11-11-android-family-client-design.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-11-android-family-client-design（目录与文件名推断） | EasyChat 家庭 Android 客户端完整设计方案 |
| [2026-11-11-android-family-wp0-foundation.md](<E:/PythonCode/EasyChat/docs/superpowers/specs/2026-11-11-android-family-wp0-foundation.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-11-android-family-wp0-foundation（目录与文件名推断） | WP0 核验记录与实施基线(小暖 Android 家庭客户端) |
| [2026-11-11-android-family-wp1-record.md](<E:/PythonCode/EasyChat/docs/superpowers/specs/2026-11-11-android-family-wp1-record.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-11-android-family-wp1-record（目录与文件名推断） | WP1 记录:视觉壳与导航(小暖 Android 客户端) |
| [2026-11-11-android-family-wp2-record.md](<E:/PythonCode/EasyChat/docs/superpowers/specs/2026-11-11-android-family-wp2-record.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-11-android-family-wp2-record（目录与文件名推断） | WP2 记录:登录与聊天主链(真实服务端联调) |
| [2026-11-11-android-family-wp34-record.md](<E:/PythonCode/EasyChat/docs/superpowers/specs/2026-11-11-android-family-wp34-record.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-11-android-family-wp34-record（目录与文件名推断） | WP3+WP4 记录:生活页真实聚合与提醒管理(真实服务端联调) |
| [2026-11-12-android-family-backend-contract-draft.md](<E:/PythonCode/EasyChat/docs/superpowers/specs/2026-11-12-android-family-backend-contract-draft.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-12-android-family-backend-contract-draft（目录与文件名推断） | 升级简报:小暖客户端所需后端读取契约增强(草稿,等待人工决策) |
| [2026-11-12-android-family-wp5-delivery.md](<E:/PythonCode/EasyChat/docs/superpowers/specs/2026-11-12-android-family-wp5-delivery.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 2026-11-12-android-family-wp5-delivery（目录与文件名推断） | WP5 交付记录:小暖 Android 家庭客户端(安装、连接与升级说明) |

### docs/superpowers/specs/assets/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [2026-11-11-android-family-concept.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/2026-11-11-android-family-concept.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |

### docs/superpowers/specs/assets/android-wp1/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [shot_01_welcome.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp1/shot_01_welcome.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [shot_02_server.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp1/shot_02_server.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [shot_03_login.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp1/shot_03_login.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [shot_04_today.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp1/shot_04_today.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [shot_05_chat.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp1/shot_05_chat.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [shot_06_life.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp1/shot_06_life.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [shot_07_profile.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp1/shot_07_profile.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [shot_08_wechat_detail.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp1/shot_08_wechat_detail.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [shot_09_today_dark.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp1/shot_09_today_dark.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [shot_10_chat_dark.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp1/shot_10_chat_dark.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [shot_11_today_font2.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp1/shot_11_today_font2.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [shot_12_life_360dp.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp1/shot_12_life_360dp.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |

### docs/superpowers/specs/assets/android-wp2/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [wp2_01_connected_login.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp2/wp2_01_connected_login.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [wp2_02_login_error_friendly.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp2/wp2_02_login_error_friendly.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [wp2_03_thinking_stop_button.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp2/wp2_03_thinking_stop_button.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [wp2_04_stream_complete.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp2/wp2_04_stream_complete.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [wp2_05_real_sessions.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp2/wp2_05_real_sessions.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [wp2_06_history_restore.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp2/wp2_06_history_restore.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |

### docs/superpowers/specs/assets/android-wp34/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [wp3_01_today_real.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp34/wp3_01_today_real.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [wp3_02_memories_real.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp34/wp3_02_memories_real.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [wp3_03_schedules_real.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp34/wp3_03_schedules_real.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [wp3_04_bookmarks_real.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp34/wp3_04_bookmarks_real.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [wp4_01_new_reminder_form.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp34/wp4_01_new_reminder_form.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |
| [wp4_02_no_binding_error.png](<E:/PythonCode/EasyChat/docs/superpowers/specs/assets/android-wp34/wp4_02_no_binding_error.png>) | 设计、实施、交接与验证资料使用的图像、媒体或二进制资源（文件类型） | 按目录和文件类型定位 |

### docs/论文复现/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [01-概述与架构.md](<E:/PythonCode/EasyChat/docs/论文复现/01-概述与架构.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 01-概述与架构（目录与文件名推断） | 概述与架构 |
| [02-论文解析与Rubric冻结.md](<E:/PythonCode/EasyChat/docs/论文复现/02-论文解析与Rubric冻结.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 02-论文解析与Rubric冻结（目录与文件名推断） | 论文解析与 Rubric 冻结 |
| [04-论文代码调试.md](<E:/PythonCode/EasyChat/docs/论文复现/04-论文代码调试.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 04-论文代码调试（目录与文件名推断） | 论文代码调试 |
| [06-Claim-Evidence证据图.md](<E:/PythonCode/EasyChat/docs/论文复现/06-Claim-Evidence证据图.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 06-Claim-Evidence证据图（目录与文件名推断） | Claim-Evidence 证据图 |
| [07-ToT消融设计.md](<E:/PythonCode/EasyChat/docs/论文复现/07-ToT消融设计.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 07-ToT消融设计（目录与文件名推断） | ToT 消融设计 |
| [08-执行示例.md](<E:/PythonCode/EasyChat/docs/论文复现/08-执行示例.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 08-执行示例（目录与文件名推断） | 执行示例 |
| [README.md](<E:/PythonCode/EasyChat/docs/论文复现/README.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 README（目录与文件名推断） | 论文复现文档目录 |
| [代码优化报告.md](<E:/PythonCode/EasyChat/docs/论文复现/代码优化报告.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 代码优化报告（目录与文件名推断） | 论文复现系统代码优化报告 |
| [完整实现报告.md](<E:/PythonCode/EasyChat/docs/论文复现/完整实现报告.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 完整实现报告（目录与文件名推断） | 论文复现系统完整实现报告 |
| [实现总结.md](<E:/PythonCode/EasyChat/docs/论文复现/实现总结.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 实现总结（目录与文件名推断） | 论文复现工具实现总结 |
| [迁移可行性评估.md](<E:/PythonCode/EasyChat/docs/论文复现/迁移可行性评估.md>) | 设计、实施、交接与验证资料的说明、设计或验证文档，主题 迁移可行性评估（目录与文件名推断） | 论文复现系统 Python 迁移与 AgentForge 集成可行性评估 |

### eval/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [adaptive_retrieval_ab_test.py](<E:/PythonCode/EasyChat/eval/adaptive_retrieval_ab_test.py>) | 离线评测、基准与结果分析中的测试相关实现（目录与文件名推断） | 自适应检索改进 A/B 测试和性能测试 / 符号 test_intent_classification, test_entity_thresholds, simulate_graph_expansion_performance, run_all_tests |
| [adaptive_retrieval_perf_test.py](<E:/PythonCode/EasyChat/eval/adaptive_retrieval_perf_test.py>) | 离线评测、基准与结果分析中的测试相关实现（目录与文件名推断） | 自适应检索深度性能测试 / 符号 benchmark_intent_classification, test_intent_classification_correctness, test_graph_expand_limit_effect, run_all_perf_tests |
| [adaptive_retrieval_test_report.md](<E:/PythonCode/EasyChat/eval/adaptive_retrieval_test_report.md>) | 离线评测、基准与结果分析的说明、设计或验证文档，主题 adaptive_retrieval_test_report（目录与文件名推断） | 自适应检索改进 A/B 测试和性能测试报告 |
| [agent_benchmark.py](<E:/PythonCode/EasyChat/eval/agent_benchmark.py>) | 离线评测、基准与结果分析中的代理、基准评测相关实现（目录与文件名推断） | Agent 多维度评测框架 / 符号 TestCase, TestResult, DimensionReport, AgentBenchmark, TestBuilder, main |
| [code_mode_eval.py](<E:/PythonCode/EasyChat/eval/code_mode_eval.py>) | 离线评测、基准与结果分析中的评测相关实现（目录与文件名推断） | Code Mode Agent 级评测脚本 / 符号 load_dataset, parse_jwt_user_id, call_chat_api, call_llm_judge, run_case, generate_report, main |

### eval/context_budget/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [README.md](<E:/PythonCode/EasyChat/eval/context_budget/README.md>) | 离线评测、基准与结果分析的说明、设计或验证文档，主题 README（目录与文件名推断） | 上下文策略对照与消融评测 |
| [config.ablation-local.json](<E:/PythonCode/EasyChat/eval/context_budget/config.ablation-local.json>) | 离线评测、基准与结果分析的配置或结构化资源，主题 config.ablation-local（目录与文件名推断） | 按目录和文件类型定位 |
| [config.example.json](<E:/PythonCode/EasyChat/eval/context_budget/config.example.json>) | 离线评测、基准与结果分析的配置或结构化资源，主题 config.example（目录与文件名推断） | 按目录和文件类型定位 |
| [config.qwen-local.json](<E:/PythonCode/EasyChat/eval/context_budget/config.qwen-local.json>) | 离线评测、基准与结果分析的配置或结构化资源，主题 config.qwen-local（目录与文件名推断） | 按目录和文件类型定位 |
| [metrics.py](<E:/PythonCode/EasyChat/eval/context_budget/metrics.py>) | 离线评测、基准与结果分析中的metrics 实现（目录与文件名推断） | Provider usage accounting. Rates are currency units per million tokens. / 符号 normalize_usage, cost, aggregate |
| [pilot.py](<E:/PythonCode/EasyChat/eval/context_budget/pilot.py>) | 离线评测、基准与结果分析中的pilot 实现（目录与文件名推断） | Frozen small end-to-end system comparison; every run is a new process/home/store. / 符号 tasks, parse_answer, main |
| [report.py](<E:/PythonCode/EasyChat/eval/context_budget/report.py>) | 离线评测、基准与结果分析中的报告相关实现（目录与文件名推断） | Summarize recorded runs, including failures, without making model requests. / 符号 summarize, audit, main |
| [upstream.py](<E:/PythonCode/EasyChat/eval/context_budget/upstream.py>) | 离线评测、基准与结果分析中的upstream 实现（目录与文件名推断） | A real pinned MCP subprocess per run, not a local BM25 imitation. / 符号 MCPBridge |
| [validation.py](<E:/PythonCode/EasyChat/eval/context_budget/validation.py>) | 离线评测、基准与结果分析中的validation 实现（目录与文件名推断） | Deterministic factual and formatting checks; no model judge. / 符号 strict_json, validate_answer, same_json |
| [variants.py](<E:/PythonCode/EasyChat/eval/context_budget/variants.py>) | 离线评测、基准与结果分析中的variants 实现（目录与文件名推断） | Pure validation and scheduling; no credentials, providers or MCP imports. / 符号 resolve_profiles, prepare_plan |
| [worker.py](<E:/PythonCode/EasyChat/eval/context_budget/worker.py>) | 离线评测、基准与结果分析中的worker 实现（目录与文件名推断） | One isolated real Hermes run. Never writes credentials to experiment artifacts. / 符号 main |

### eval/dataset/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [dataset_code_mode.jsonl](<E:/PythonCode/EasyChat/eval/dataset/dataset_code_mode.jsonl>) | 离线评测、基准与结果分析中的dataset_code_mode 实现（目录与文件名推断） | 按目录和文件类型定位 |

### scripts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [_check_wechat.py](<E:/PythonCode/EasyChat/scripts/_check_wechat.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查相关实现（目录与文件名推断） | 按目录和文件类型定位 |
| [activate_embedding.py](<E:/PythonCode/EasyChat/scripts/activate_embedding.py>) | 人工运维、诊断、数据修复及历史实验脚本中的向量化相关实现（目录与文件名推断） | 激活 doubao-embedding-vision 模型 |
| [annotate_eval_gt.py](<E:/PythonCode/EasyChat/scripts/annotate_eval_gt.py>) | 人工运维、诊断、数据修复及历史实验脚本中的评测相关实现（目录与文件名推断） | 为 Text2SQL 测评集题目标注 GT chunk_ids / 符号 find_matching_chunks |
| [batch_repair_locations.py](<E:/PythonCode/EasyChat/scripts/batch_repair_locations.py>) | 人工运维、诊断、数据修复及历史实验脚本中的修复相关实现（目录与文件名推断） | 修复 Location/Concept 孤立节点 — 从描述中提取关联人物 / 符号 has_relation, find_person_in_text, add_rel_for_orphan |
| [batch_repair_orphans.py](<E:/PythonCode/EasyChat/scripts/batch_repair_orphans.py>) | 人工运维、诊断、数据修复及历史实验脚本中的修复相关实现（目录与文件名推断） | 批量修复孤立实体关系 / 符号 has_relation, add_rel, batch_add, batch_clique |
| [check_bindings.py](<E:/PythonCode/EasyChat/scripts/check_bindings.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查相关实现（目录与文件名推断） | 检查用户绑定状态 |
| [check_bm25_index.py](<E:/PythonCode/EasyChat/scripts/check_bm25_index.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查相关实现（目录与文件名推断） | 检查 BM25 索引状态 |
| [check_db_tables.py](<E:/PythonCode/EasyChat/scripts/check_db_tables.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查相关实现（目录与文件名推断） | 按目录和文件类型定位 |
| [check_doc_kb.py](<E:/PythonCode/EasyChat/scripts/check_doc_kb.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查相关实现（目录与文件名推断） | 检查文档 kb_id 分布 |
| [check_feedback.py](<E:/PythonCode/EasyChat/scripts/check_feedback.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查、反馈相关实现（目录与文件名推断） | 检查检索日志和反馈 / 符号 safe_print |
| [check_graph_memory.py](<E:/PythonCode/EasyChat/scripts/check_graph_memory.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查、图数据、记忆相关实现（目录与文件名推断） | 检查 Neo4j 图记忆状态 |
| [check_graphrag_status.py](<E:/PythonCode/EasyChat/scripts/check_graphrag_status.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查、历史GraphRAG相关实现（目录与文件名推断） | 检查 GraphRAG 提取状态 |
| [check_kb_files.py](<E:/PythonCode/EasyChat/scripts/check_kb_files.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查、文件相关实现（目录与文件名推断） | 按目录和文件类型定位 |
| [check_kb_status.py](<E:/PythonCode/EasyChat/scripts/check_kb_status.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查相关实现（目录与文件名推断） | 检查知识库状态 |
| [check_kbs.py](<E:/PythonCode/EasyChat/scripts/check_kbs.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查相关实现（目录与文件名推断） | 查看知识库列表数据 |
| [check_model_config.py](<E:/PythonCode/EasyChat/scripts/check_model_config.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查、模型、配置相关实现（目录与文件名推断） | 查看模型配置 |
| [check_parent_child.py](<E:/PythonCode/EasyChat/scripts/check_parent_child.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查相关实现（目录与文件名推断） | 检查父子分片相关数据 |
| [check_progress.py](<E:/PythonCode/EasyChat/scripts/check_progress.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查相关实现（目录与文件名推断） | 按目录和文件类型定位 |
| [check_prompt.py](<E:/PythonCode/EasyChat/scripts/check_prompt.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查、提示词相关实现（目录与文件名推断） | 检查当前系统提示词 |
| [check_prompt_full.py](<E:/PythonCode/EasyChat/scripts/check_prompt_full.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查、提示词相关实现（目录与文件名推断） | 检查当前系统提示词 |
| [check_sanguo.py](<E:/PythonCode/EasyChat/scripts/check_sanguo.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查相关实现（目录与文件名推断） | 查看三国演义的切分情况 |
| [check_sanguo_detail.py](<E:/PythonCode/EasyChat/scripts/check_sanguo_detail.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查相关实现（目录与文件名推断） | 详细查看三国演义的父片切分 |
| [check_sanguo_format.py](<E:/PythonCode/EasyChat/scripts/check_sanguo_format.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查相关实现（目录与文件名推断） | 查看三国演义原文格式 |
| [check_sanguo_parse_status.py](<E:/PythonCode/EasyChat/scripts/check_sanguo_parse_status.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查相关实现（目录与文件名推断） | 检查三国演义文档解析状态 |
| [cleanup_test_data.py](<E:/PythonCode/EasyChat/scripts/cleanup_test_data.py>) | 人工运维、诊断、数据修复及历史实验脚本中的测试相关实现（目录与文件名推断） | 清理测试数据 |
| [clear_memories.py](<E:/PythonCode/EasyChat/scripts/clear_memories.py>) | 人工运维、诊断、数据修复及历史实验脚本中的clear_memories 实现（目录与文件名推断） | 清空所有记忆（MySQL + Neo4j） |
| [create_hongloumeng_eval.py](<E:/PythonCode/EasyChat/scripts/create_hongloumeng_eval.py>) | 人工运维、诊断、数据修复及历史实验脚本中的评测相关实现（目录与文件名推断） | 创建红楼梦评测集 - 简化版 / 符号 main |
| [create_hongloumeng_eval_100.py](<E:/PythonCode/EasyChat/scripts/create_hongloumeng_eval_100.py>) | 人工运维、诊断、数据修复及历史实验脚本中的评测相关实现（目录与文件名推断） | 创建红楼梦评测集 - 100个问题版本 / 符号 main |
| [create_hongloumeng_eval_v2.py](<E:/PythonCode/EasyChat/scripts/create_hongloumeng_eval_v2.py>) | 人工运维、诊断、数据修复及历史实验脚本中的评测相关实现（目录与文件名推断） | 创建红楼梦评测集 V2 - 刁钻但实际存在的问题 / 符号 main |
| [create_hongloumeng_eval_v3.py](<E:/PythonCode/EasyChat/scripts/create_hongloumeng_eval_v3.py>) | 人工运维、诊断、数据修复及历史实验脚本中的评测相关实现（目录与文件名推断） | 创建红楼梦评测集 V3 - 更多刁钻问题 / 符号 main |
| [create_hongloumeng_kb.py](<E:/PythonCode/EasyChat/scripts/create_hongloumeng_kb.py>) | 人工运维、诊断、数据修复及历史实验脚本中的create_hongloumeng_kb 实现（目录与文件名推断） | 创建红楼梦知识库并导入文件 / 符号 main |
| [create_sanguo_eval_100.py](<E:/PythonCode/EasyChat/scripts/create_sanguo_eval_100.py>) | 人工运维、诊断、数据修复及历史实验脚本中的评测相关实现（目录与文件名推断） | 创建三国演义评测集 - 100个问题版本 / 符号 main |
| [create_test_memories.py](<E:/PythonCode/EasyChat/scripts/create_test_memories.py>) | 人工运维、诊断、数据修复及历史实验脚本中的测试相关实现（目录与文件名推断） | 创建测试记忆数据 / 符号 create_test_memories |
| [create_text2sql_eval_set.py](<E:/PythonCode/EasyChat/scripts/create_text2sql_eval_set.py>) | 人工运维、诊断、数据修复及历史实验脚本中的评测相关实现（目录与文件名推断） | 创建 Text2SQL 测评集 |
| [debug_graph_extract.py](<E:/PythonCode/EasyChat/scripts/debug_graph_extract.py>) | 人工运维、诊断、数据修复及历史实验脚本中的图数据相关实现（目录与文件名推断） | GraphRAG 实体提取诊断脚本 / 符号 diagnose |
| [debug_gt_265.py](<E:/PythonCode/EasyChat/scripts/debug_gt_265.py>) | 人工运维、诊断、数据修复及历史实验脚本中的debug_gt_265 实现（目录与文件名推断） | 查找含 kb_knowledge_base 的 chunk |
| [del_cron_manage.py](<E:/PythonCode/EasyChat/scripts/del_cron_manage.py>) | 人工运维、诊断、数据修复及历史实验脚本中的定时触发相关实现（目录与文件名推断） | 按目录和文件类型定位 |
| [deploy_rag_eval.py](<E:/PythonCode/EasyChat/scripts/deploy_rag_eval.py>) | 人工运维、诊断、数据修复及历史实验脚本中的评测相关实现（目录与文件名推断） | 上传 RAG测评完全指南 到知识库，并创建测评集 / 符号 login, upload_document, vectorize_document, create_eval_set, search_chunks, add_eval_item, main |
| [diagnose_milvus.py](<E:/PythonCode/EasyChat/scripts/diagnose_milvus.py>) | 人工运维、诊断、数据修复及历史实验脚本中的diagnose_milvus 实现（目录与文件名推断） | 诊断 Milvus 连接问题 |
| [encrypt_memory_content.py](<E:/PythonCode/EasyChat/scripts/encrypt_memory_content.py>) | 人工运维、诊断、数据修复及历史实验脚本中的记忆相关实现（目录与文件名推断） | 记忆内容加密迁移脚本 / 符号 count_plaintext, encrypt_table, main |
| [export_local_mysql.py](<E:/PythonCode/EasyChat/scripts/export_local_mysql.py>) | 人工运维、诊断、数据修复及历史实验脚本中的历史MySQL相关实现（目录与文件名推断） | Export local MySQL data to SQL file |
| [files_ledger_backup.py](<E:/PythonCode/EasyChat/scripts/files_ledger_backup.py>) | 人工运维、诊断、数据修复及历史实验脚本中的文件、备份相关实现（目录与文件名推断） | 文件 + SQLite 备份/校验/恢复 CLI（运维脚本，非业务入口）。 / 符号 _paths, main |
| [find_sql_session.py](<E:/PythonCode/EasyChat/scripts/find_sql_session.py>) | 人工运维、诊断、数据修复及历史实验脚本中的会话相关实现（目录与文件名推断） | 查找有对话+SQL 的会话 |
| [fix_gt_child_to_parent.py](<E:/PythonCode/EasyChat/scripts/fix_gt_child_to_parent.py>) | 人工运维、诊断、数据修复及历史实验脚本中的修复相关实现（目录与文件名推断） | 修复测评集 GT 中标注了子片的数据，将子片 ID 替换为对应的父片 ID / 符号 fix_gt_child_to_parent |
| [fix_last_gt.py](<E:/PythonCode/EasyChat/scripts/fix_last_gt.py>) | 人工运维、诊断、数据修复及历史实验脚本中的修复相关实现（目录与文件名推断） | 标注题目 265 的 GT |
| [fix_table_comments.py](<E:/PythonCode/EasyChat/scripts/fix_table_comments.py>) | 人工运维、诊断、数据修复及历史实验脚本中的修复相关实现（目录与文件名推断） | 补全数据库表中文注释 |
| [generate_rag_eval_testset.py](<E:/PythonCode/EasyChat/scripts/generate_rag_eval_testset.py>) | 人工运维、诊断、数据修复及历史实验脚本中的评测相关实现（目录与文件名推断） | 为 RAG测评完全指南.md 生成测评集和问题 / 符号 generate_eval_set_json, print_summary |
| [generate_security_report.py](<E:/PythonCode/EasyChat/scripts/generate_security_report.py>) | 人工运维、诊断、数据修复及历史实验脚本中的报告相关实现（目录与文件名推断） | AgentForge 项目漏洞与优化分析报告生成器 / 符号 create_report |
| [generate_token_report.py](<E:/PythonCode/EasyChat/scripts/generate_token_report.py>) | 人工运维、诊断、数据修复及历史实验脚本中的令牌/Token、报告相关实现（目录与文件名推断） | Token 消耗分析报告生成器 / 符号 register_chinese_fonts, query_token_data, create_hourly_chart, create_model_chart, generate_pdf_report, main |
| [import_hongloumeng.py](<E:/PythonCode/EasyChat/scripts/import_hongloumeng.py>) | 人工运维、诊断、数据修复及历史实验脚本中的import_hongloumeng 实现（目录与文件名推断） | 导入红楼梦到知识库 / 符号 main |
| [migrate_add_rel_ids.py](<E:/PythonCode/EasyChat/scripts/migrate_add_rel_ids.py>) | 人工运维、诊断、数据修复及历史实验脚本中的migrate_add_rel_ids 实现（目录与文件名推断） | 迁移脚本：给 Neo4j 中没有 id 属性的关系补上 UUID / 符号 migrate |
| [migrate_memory_consistency.py](<E:/PythonCode/EasyChat/scripts/migrate_memory_consistency.py>) | 人工运维、诊断、数据修复及历史实验脚本中的记忆相关实现（目录与文件名推断） | 记忆架构迁移脚本 / 符号 migrate_memory_items, create_memory_outbox, main |
| [probe_ark.py](<E:/PythonCode/EasyChat/scripts/probe_ark.py>) | 人工运维、诊断、数据修复及历史实验脚本中的probe_ark 实现（目录与文件名推断） | 火山方舟（Ark）Embedding 连通性探测脚本。 / 符号 probe, classify, main |
| [query_hongloumeng.py](<E:/PythonCode/EasyChat/scripts/query_hongloumeng.py>) | 人工运维、诊断、数据修复及历史实验脚本中的query_hongloumeng 实现（目录与文件名推断） | 查询红楼梦数据和父片 / 符号 main |
| [reingest_text2sql.py](<E:/PythonCode/EasyChat/scripts/reingest_text2sql.py>) | 人工运维、诊断、数据修复及历史实验脚本中的reingest_text2sql 实现（目录与文件名推断） | Re-ingest text2sql documents after sanitization (T2.1a Step 2-3). / 符号 main |
| [remove_cron_manage_perm.py](<E:/PythonCode/EasyChat/scripts/remove_cron_manage_perm.py>) | 人工运维、诊断、数据修复及历史实验脚本中的定时触发相关实现（目录与文件名推断） | 数据库迁移脚本：移除 cron.manage 权限 |
| [run_extraction.py](<E:/PythonCode/EasyChat/scripts/run_extraction.py>) | 人工运维、诊断、数据修复及历史实验脚本中的run_extraction 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [run_schema.py](<E:/PythonCode/EasyChat/scripts/run_schema.py>) | 人工运维、诊断、数据修复及历史实验脚本中的run_schema 实现（目录与文件名推断） | Run schema migration |
| [slim_models_dev.py](<E:/PythonCode/EasyChat/scripts/slim_models_dev.py>) | 人工运维、诊断、数据修复及历史实验脚本中的模型相关实现（目录与文件名推断） | 一条龙脚本：从 models.dev 拉取最新数据 → 精简字段 → 写入 models_dev.json。 / 符号 fetch_models_dev, strip_model, strip_provider, main |
| [start_local_embedding.py](<E:/PythonCode/EasyChat/scripts/start_local_embedding.py>) | 人工运维、诊断、数据修复及历史实验脚本中的向量化相关实现（目录与文件名推断） | 启动本地 BGE Embedding 服务（可选依赖 sentence-transformers）。 |
| [sync_item_status.py](<E:/PythonCode/EasyChat/scripts/sync_item_status.py>) | 人工运维、诊断、数据修复及历史实验脚本中的sync_item_status 实现（目录与文件名推断） | 同步技能状态到 item_status 表 |
| [sync_kb_to_graph.py](<E:/PythonCode/EasyChat/scripts/sync_kb_to_graph.py>) | 人工运维、诊断、数据修复及历史实验脚本中的图数据相关实现（目录与文件名推断） | 重新同步知识库文档到 Neo4j 知识图谱 / 符号 get_completed_documents, sync_kb_to_graph |
| [sync_memories_to_graph.py](<E:/PythonCode/EasyChat/scripts/sync_memories_to_graph.py>) | 人工运维、诊断、数据修复及历史实验脚本中的图数据相关实现（目录与文件名推断） | 将现有记忆同步到 Neo4j GraphMemory（包含用户隔离） / 符号 sync_memories_to_graph |
| [test_ab_delay_rounds.py](<E:/PythonCode/EasyChat/scripts/test_ab_delay_rounds.py>) | 验证 ab_delay_rounds 相关行为与回归（测试文件名推断） | 记忆延迟轮次 AB 测试 / 符号 clear_test_memories, simulate_conversation, calculate_recall_score, run_ab_test |
| [test_ab_experiment.py](<E:/PythonCode/EasyChat/scripts/test_ab_experiment.py>) | 验证 ab_experiment 相关行为与回归（测试文件名推断） | AB 实验框架验证脚本 / 符号 test_variant_assignment, test_event_logging, test_statistics, test_delay_rounds_experiment, test_create_experiment, main |
| [test_ab_real.py](<E:/PythonCode/EasyChat/scripts/test_ab_real.py>) | 验证 ab_real 相关行为与回归（测试文件名推断） | 记忆延迟轮次 AB 测试 - 真正对比提取时机 / 符号 test_extraction_at_round, run_real_ab_test |
| [test_chapter_regex.py](<E:/PythonCode/EasyChat/scripts/test_chapter_regex.py>) | 验证 chapter_regex 相关行为与回归（测试文件名推断） | 按目录和文件类型定位 |
| [test_extractor_pool.py](<E:/PythonCode/EasyChat/scripts/test_extractor_pool.py>) | 验证 extractor_pool 相关行为与回归（测试文件名推断） | 测试 GraphRAG 多线程提取 / 符号 get_first_document, main |
| [test_graphrag_kb.py](<E:/PythonCode/EasyChat/scripts/test_graphrag_kb.py>) | 验证 graphrag_kb 相关行为与回归（测试文件名推断） | GraphRAG KB 集成测试 - 语法和逻辑验证 / 符号 test_imports, test_entity_types, test_relation_types, test_extractor_params, test_kg_store_methods, test_hybrid_retriever, test_graph_retriever |
| [test_json_fix.py](<E:/PythonCode/EasyChat/scripts/test_json_fix.py>) | 验证 json_fix 相关行为与回归（测试文件名推断） | 测试 GraphRAG JSON 解析修复 / 符号 test_json_parsing |
| [test_kb_search.py](<E:/PythonCode/EasyChat/scripts/test_kb_search.py>) | 验证 kb_search 相关行为与回归（测试文件名推断） | 测试 knowledge_search 是否能检索到 Text2SQL 示例 |
| [test_memory_e2e.py](<E:/PythonCode/EasyChat/scripts/test_memory_e2e.py>) | 验证 memory_e2e 相关行为与回归（测试文件名推断） | AgentForge Memory System - End-to-End Test |
| [test_memory_eval.py](<E:/PythonCode/EasyChat/scripts/test_memory_eval.py>) | 验证 memory_eval 相关行为与回归（测试文件名推断） | 记忆评估系统验证脚本 / 符号 create_test_memories, check_memory_count, test_f1_calculation, test_memory_search, main |
| [test_memory_extraction.py](<E:/PythonCode/EasyChat/scripts/test_memory_extraction.py>) | 验证 memory_extraction 相关行为与回归（测试文件名推断） | Memory Extraction Test - 10 Rounds / 符号 login, chat, check_memories |
| [test_memory_full.py](<E:/PythonCode/EasyChat/scripts/test_memory_full.py>) | 验证 memory_full 相关行为与回归（测试文件名推断） | 记忆系统完整测试 / 符号 check_milvus_status, test_memory_vectorization, test_memory_search, test_ab_experiment_integration, main |
| [test_memory_simple.py](<E:/PythonCode/EasyChat/scripts/test_memory_simple.py>) | 验证 memory_simple 相关行为与回归（测试文件名推断） | Simple memory extraction test with authentication / 符号 login, chat |
| [test_milvus_clients.py](<E:/PythonCode/EasyChat/scripts/test_milvus_clients.py>) | 验证 milvus_clients 相关行为与回归（测试文件名推断） | 测试 MilvusClient 连接 |
| [test_pool_simple.py](<E:/PythonCode/EasyChat/scripts/test_pool_simple.py>) | 验证 pool_simple 相关行为与回归（测试文件名推断） | 简单测试 GraphRAG 多线程提取 |
| [test_rag_vectorstore.py](<E:/PythonCode/EasyChat/scripts/test_rag_vectorstore.py>) | 验证 rag_vectorstore 相关行为与回归（测试文件名推断） | 测试 RAG 向量库选择 |
| [test_search.py](<E:/PythonCode/EasyChat/scripts/test_search.py>) | 验证 search 相关行为与回归（测试文件名推断） | 测试记忆检索 |
| [test_sql_case_ingest.py](<E:/PythonCode/EasyChat/scripts/test_sql_case_ingest.py>) | 验证 sql_case_ingest 相关行为与回归（测试文件名推断） | 插入测试数据并验证 SQL 案例闭环 / 符号 main |
| [test_vectorstore.py](<E:/PythonCode/EasyChat/scripts/test_vectorstore.py>) | 验证 vectorstore 相关行为与回归（测试文件名推断） | 测试向量库选择逻辑 |
| [token_report.py](<E:/PythonCode/EasyChat/scripts/token_report.py>) | 人工运维、诊断、数据修复及历史实验脚本中的令牌/Token、报告相关实现（目录与文件名推断） | AgentForge Token 消耗分析报告生成器（简化版） / 符号 get_db_connection, convert_decimal, query_token_stats, calculate_cost, generate_pdf_report, main |
| [upload_general_docs.py](<E:/PythonCode/EasyChat/scripts/upload_general_docs.py>) | 人工运维、诊断、数据修复及历史实验脚本中的上传相关实现（目录与文件名推断） | Upload documents to default knowledge base. / 符号 upload_documents |
| [vectorize_hongloumeng.py](<E:/PythonCode/EasyChat/scripts/vectorize_hongloumeng.py>) | 人工运维、诊断、数据修复及历史实验脚本中的vectorize_hongloumeng 实现（目录与文件名推断） | 向量化红楼梦文档 / 符号 main |
| [vectorize_manual.py](<E:/PythonCode/EasyChat/scripts/vectorize_manual.py>) | 人工运维、诊断、数据修复及历史实验脚本中的vectorize_manual 实现（目录与文件名推断） | 向量化产品手册文档 / 符号 main |
| [verify_chunk_mapping.py](<E:/PythonCode/EasyChat/scripts/verify_chunk_mapping.py>) | 人工运维、诊断、数据修复及历史实验脚本中的verify_chunk_mapping 实现（目录与文件名推断） | 验证chunk映射是否正确 |
| [verify_eval.py](<E:/PythonCode/EasyChat/scripts/verify_eval.py>) | 人工运维、诊断、数据修复及历史实验脚本中的评测相关实现（目录与文件名推断） | 验证红楼梦评测集 |
| [verify_graph_extract_fix.py](<E:/PythonCode/EasyChat/scripts/verify_graph_extract_fix.py>) | 人工运维、诊断、数据修复及历史实验脚本中的图数据、修复相关实现（目录与文件名推断） | GraphRAG 修复验证脚本 / 符号 test_1_traced_response_is_error, test_2_extractor_raises_on_llm_error, test_3_extractor_succeeds_on_empty_json, test_4_kgstore_propagates_llm_error, test_5_extract_raises_on_non_json_response, test_6_no_circuit_breaker_precheck |
| [verify_hongloumeng.py](<E:/PythonCode/EasyChat/scripts/verify_hongloumeng.py>) | 人工运维、诊断、数据修复及历史实验脚本中的verify_hongloumeng 实现（目录与文件名推断） | 验证红楼梦导入结果 / 符号 main |
| [verify_keywords.py](<E:/PythonCode/EasyChat/scripts/verify_keywords.py>) | 人工运维、诊断、数据修复及历史实验脚本中的verify_keywords 实现（目录与文件名推断） | 检查chunk完整内容中的关键词 |
| [view_all_chapters.py](<E:/PythonCode/EasyChat/scripts/view_all_chapters.py>) | 人工运维、诊断、数据修复及历史实验脚本中的view_all_chapters 实现（目录与文件名推断） | 查看所有父片的章节分布 |
| [view_ingested_case.py](<E:/PythonCode/EasyChat/scripts/view_ingested_case.py>) | 人工运维、诊断、数据修复及历史实验脚本中的view_ingested_case 实现（目录与文件名推断） | 查看入库的 SQL 案例内容 |

### scripts/kb/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [README.md](<E:/PythonCode/EasyChat/scripts/kb/README.md>) | 人工运维、诊断、数据修复及历史实验脚本的说明、设计或验证文档，主题 README（目录与文件名推断） | 知识库相关脚本（KB Scripts） |
| [reparse_kb.py](<E:/PythonCode/EasyChat/scripts/kb/reparse_kb.py>) | 人工运维、诊断、数据修复及历史实验脚本中的reparse_kb 实现（目录与文件名推断） | 重新解析知识库文档 / 符号 main |
| [run_kg_dedup.py](<E:/PythonCode/EasyChat/scripts/kb/run_kg_dedup.py>) | 人工运维、诊断、数据修复及历史实验脚本中的run_kg_dedup 实现（目录与文件名推断） | 手动执行知识图谱全量去重 / 符号 main |

### scripts/kb/eval/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [chunk_param_sweep.py](<E:/PythonCode/EasyChat/scripts/kb/eval/chunk_param_sweep.py>) | 人工运维、诊断、数据修复及历史实验脚本中的chunk_param_sweep 实现（目录与文件名推断） | 父子切片参数扫描评测 / 符号 load_test_documents, make_pages, detect_sections, chunk_document, build_bm25_index, bm25_retrieve, check_hit |
| [kb_eval_smoke_test.py](<E:/PythonCode/EasyChat/scripts/kb/eval/kb_eval_smoke_test.py>) | 人工运维、诊断、数据修复及历史实验脚本中的评测、测试相关实现（目录与文件名推断） | RAG 测评端到端冒烟测试（针对运行中的服务实例，8002）。 / 符号 main |
| [kb_ragas_verify.py](<E:/PythonCode/EasyChat/scripts/kb/eval/kb_ragas_verify.py>) | 人工运维、诊断、数据修复及历史实验脚本中的kb_ragas_verify 实现（目录与文件名推断） | RAGAS 裁判链路本地验证（真实 DeepSeek 裁判，1 条样本）。 |
| [test_rag_eval.py](<E:/PythonCode/EasyChat/scripts/kb/eval/test_rag_eval.py>) | 验证 rag_eval 相关行为与回归（测试文件名推断） | RAG 测评端到端测试 — 基于产品手册验证父子切分 + table_refs / 符号 get_doc_parent_chunks, main |
| [test_rag_retrieval.py](<E:/PythonCode/EasyChat/scripts/kb/eval/test_rag_retrieval.py>) | 验证 rag_retrieval 相关行为与回归（测试文件名推断） | RAG 检索实测 — BM25 检索 + table_refs 透传验证 / 符号 main |

### scripts/kb/migrate/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [create_history_correct_kb.py](<E:/PythonCode/EasyChat/scripts/kb/migrate/create_history_correct_kb.py>) | 人工运维、诊断、数据修复及历史实验脚本中的create_history_correct_kb 实现（目录与文件名推断） | 创建历史正确案例知识库并导入 text2sql_examples.md / 符号 main |
| [fix_all_kb_id.py](<E:/PythonCode/EasyChat/scripts/kb/migrate/fix_all_kb_id.py>) | 人工运维、诊断、数据修复及历史实验脚本中的修复相关实现（目录与文件名推断） | 完整修复 kb_documents 和 kb_chunks 的 kb_id 字段 / 符号 get_connection, fix_all |
| [fix_chunks_kb_id.py](<E:/PythonCode/EasyChat/scripts/kb/migrate/fix_chunks_kb_id.py>) | 人工运维、诊断、数据修复及历史实验脚本中的修复相关实现（目录与文件名推断） | 修复 kb_chunks.kb_id 字段（从 kb_documents 表回填） / 符号 get_connection, fix_chunks_kb_id |
| [migrate_docs_to_kb.py](<E:/PythonCode/EasyChat/scripts/kb/migrate/migrate_docs_to_kb.py>) | 人工运维、诊断、数据修复及历史实验脚本中的migrate_docs_to_kb 实现（目录与文件名推断） | 迁移旧文档到默认知识库 — 把 kb_id 为 NULL 的文档和分片归入默认知识库 / 符号 main |
| [move_product_manual_to_text2sql.py](<E:/PythonCode/EasyChat/scripts/kb/migrate/move_product_manual_to_text2sql.py>) | 人工运维、诊断、数据修复及历史实验脚本中的move_product_manual_to_text2sql 实现（目录与文件名推断） | 将产品手册从默认知识库移动到新建的 Text2SQL 知识库 / 符号 main |

### scripts/kb/test/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [check_chunk_effect.py](<E:/PythonCode/EasyChat/scripts/kb/test/check_chunk_effect.py>) | 人工运维、诊断、数据修复及历史实验脚本中的检查相关实现（目录与文件名推断） | 查看已上传文档的切片效果 |
| [debug_q1.py](<E:/PythonCode/EasyChat/scripts/kb/test/debug_q1.py>) | 人工运维、诊断、数据修复及历史实验脚本中的debug_q1 实现（目录与文件名推断） | 调试：查询1为什么 miss |
| [kb_bm25_debug.py](<E:/PythonCode/EasyChat/scripts/kb/test/kb_bm25_debug.py>) | 人工运维、诊断、数据修复及历史实验脚本中的kb_bm25_debug 实现（目录与文件名推断） | BM25 调试：验证分词与打分 |
| [kb_cleanup_test_data.py](<E:/PythonCode/EasyChat/scripts/kb/test/kb_cleanup_test_data.py>) | 人工运维、诊断、数据修复及历史实验脚本中的测试相关实现（目录与文件名推断） | 清理知识库测试遗留文档（冒烟测试辅助）。 / 符号 main |
| [kb_model_category_verify.py](<E:/PythonCode/EasyChat/scripts/kb/test/kb_model_category_verify.py>) | 人工运维、诊断、数据修复及历史实验脚本中的模型相关实现（目录与文件名推断） | 模型配置分类端到端验证（8002 + 后端函数直读）。 / 符号 main |
| [kb_pdf_outline_check.py](<E:/PythonCode/EasyChat/scripts/kb/test/kb_pdf_outline_check.py>) | 人工运维、诊断、数据修复及历史实验脚本中的PDF、检查相关实现（目录与文件名推断） | 验证 fpdf2 start_section 生成的书签可被 pypdf 读取（测试夹具可行性）。 |
| [kb_smoke_test.py](<E:/PythonCode/EasyChat/scripts/kb/test/kb_smoke_test.py>) | 人工运维、诊断、数据修复及历史实验脚本中的测试相关实现（目录与文件名推断） | 知识库 API 端到端冒烟测试（针对运行中的服务实例）。 / 符号 make_pdf_bytes, main |
| [kb_topic_cleanup.py](<E:/PythonCode/EasyChat/scripts/kb/test/kb_topic_cleanup.py>) | 人工运维、诊断、数据修复及历史实验脚本中的kb_topic_cleanup 实现（目录与文件名推断） | 清理 topic 冒烟测试遗留数据。 |
| [kb_topic_debug.py](<E:/PythonCode/EasyChat/scripts/kb/test/kb_topic_debug.py>) | 人工运维、诊断、数据修复及历史实验脚本中的kb_topic_debug 实现（目录与文件名推断） | 调试：查看 run 28 的逐条检索结果。 |
| [kb_topic_smoke_test.py](<E:/PythonCode/EasyChat/scripts/kb/test/kb_topic_smoke_test.py>) | 人工运维、诊断、数据修复及历史实验脚本中的测试相关实现（目录与文件名推断） | 主题切分策略端到端冒烟测试（针对运行中的服务实例，8002）。 / 符号 main |
| [test_manual_only_retrieval.py](<E:/PythonCode/EasyChat/scripts/kb/test/test_manual_only_retrieval.py>) | 验证 manual_only_retrieval 相关行为与回归（测试文件名推断） | 验证：仅产品手册文档内检索的效果 / 符号 manual_only_retrieve, main |
| [test_parent_child.py](<E:/PythonCode/EasyChat/scripts/kb/test/test_parent_child.py>) | 验证 parent_child 相关行为与回归（测试文件名推断） | 父子分片功能测试脚本 / 符号 test_parent_child_splitter, test_parent_child_splitter_dict, test_empty_document, test_small_document |
| [test_parent_child_effect.py](<E:/PythonCode/EasyChat/scripts/kb/test/test_parent_child_effect.py>) | 验证 parent_child_effect 相关行为与回归（测试文件名推断） | 父子切分 + 主题标记 效果验证脚本 / 符号 analyze_topic_split, analyze_parent_child, main |
| [test_parent_child_integration.py](<E:/PythonCode/EasyChat/scripts/kb/test/test_parent_child_integration.py>) | 验证 parent_child_integration 相关行为与回归（测试文件名推断） | 父子分片集成测试 / 符号 test_full_pipeline |
| [test_parent_child_meta.py](<E:/PythonCode/EasyChat/scripts/kb/test/test_parent_child_meta.py>) | 验证 parent_child_meta 相关行为与回归（测试文件名推断） | 测试父子切片 metadata 继承 + 超长主题三级降级 |

### sql/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [agentforge_schema.sql](<E:/PythonCode/EasyChat/sql/agentforge_schema.sql>) | 历史SQL和结构资料中的agentforge_schema 实现（目录与文件名推断） | 按目录和文件类型定位 |
| [migrate_memory_mem_key.py](<E:/PythonCode/EasyChat/sql/migrate_memory_mem_key.py>) | 历史SQL和结构资料中的记忆相关实现（目录与文件名推断） | 迁移：给图谱 Memory 节点补上 'mem_key'（= "{layer}:{id}"），并补建被吞掉的同号节点。 / 符号 norm, plain |

### tests/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | 按目录和文件类型定位 |
| [ab_test_recorder.py](<E:/PythonCode/EasyChat/tests/ab_test_recorder.py>) | 自动化测试、fixture和临时SQLite测试支撑中的测试相关实现（目录与文件名推断） | A/B 测试数据收集脚本 / 符号 ABTestRecorder, main |
| [conftest.py](<E:/PythonCode/EasyChat/tests/conftest.py>) | 自动化测试、fixture和临时SQLite测试支撑中的conftest 实现（目录与文件名推断） | pytest 根配置。 / 符号 rig |
| [kb_move_visibility_runner.py](<E:/PythonCode/EasyChat/tests/kb_move_visibility_runner.py>) | 自动化测试、fixture和临时SQLite测试支撑中的kb_move_visibility_runner 实现（目录与文件名推断） | 端到端验证：把文档移动到另一个知识库（=另一个部门）后， / 符号 check, cols, ins, q1, can_see, setup, teardown |
| [kg_dept_isolation_runner.py](<E:/PythonCode/EasyChat/tests/kg_dept_isolation_runner.py>) | 自动化测试、fixture和临时SQLite测试支撑中的kg_dept_isolation_runner 实现（目录与文件名推断） | End-to-end check: knowledge-graph department (data-layer) isolation. / 符号 check, cols, ins, setup, teardown, names, main |
| [memkey_layer_isolation_runner.py](<E:/PythonCode/EasyChat/tests/memkey_layer_isolation_runner.py>) | 自动化测试、fixture和临时SQLite测试支撑中的memkey_layer_isolation_runner 实现（目录与文件名推断） | 验证"层级维度"修复：同一个 mem_id 在不同层级 = 两个独立节点，互不覆盖、互不串门。 / 符号 check |
| [run_a_group_test.py](<E:/PythonCode/EasyChat/tests/run_a_group_test.py>) | 自动化测试、fixture和临时SQLite测试支撑中的测试相关实现（目录与文件名推断） | A 组自动化测试脚本 - 通过审计日志提取工具调用数据 / 符号 get_token, get_log_position, parse_log_since, analyze_batch_operations, run_single_test, main |
| [test_adaptive_retrieval.py](<E:/PythonCode/EasyChat/tests/test_adaptive_retrieval.py>) | 验证 adaptive_retrieval 相关行为与回归（测试文件名推断） | 自适应检索链路测试（知识库 + 记忆） / 符号 TestClassifyRetrievalKind, TestEntityDescription, TestVectorStoreHelpers, _entity_hit, TestKBAdaptiveRetriever, TestForceRetrievalOverride, TestSmartRetrieverUnification |
| [test_auth_service.py](<E:/PythonCode/EasyChat/tests/test_auth_service.py>) | 验证 auth_service 相关行为与回归（测试文件名推断） | 认证服务单元测试 / 符号 TestPasswordHashing, TestTokenManagement, TestTokenPayload |
| [test_cache_hit_rate.py](<E:/PythonCode/EasyChat/tests/test_cache_hit_rate.py>) | 验证 cache_hit_rate 相关行为与回归（测试文件名推断） | cache_hit_rate 计算逻辑单元测试 / 符号 TestCacheHitRateCalculation |
| [test_cache_policy_registry.py](<E:/PythonCode/EasyChat/tests/test_cache_policy_registry.py>) | 验证 cache_policy_registry 相关行为与回归（测试文件名推断） | Provider Cache Policy 注册表单元测试 / 符号 _make_agent, TestCachePolicyRules, TestNativeAnthropic, TestOpenRouter, TestQwen, TestMiniMax, TestFallback |
| [test_code_executor.py](<E:/PythonCode/EasyChat/tests/test_code_executor.py>) | 验证 code_executor 相关行为与回归（测试文件名推断） | Code Mode 执行器单元测试 / 符号 TestASTSafetyCheck, TestSafePrint, TestRestrictedGlobals, TestCodeExecution, TestMultiUserIsolation, TestRunPythonTool, TestErrorClassification |
| [test_code_mode_e2e.py](<E:/PythonCode/EasyChat/tests/test_code_mode_e2e.py>) | 验证 code_mode_e2e 相关行为与回归（测试文件名推断） | Code Mode 文件操作端到端测试 / 符号 test_code_mode_integration, test_performance_comparison, main |
| [test_code_mode_file_ops.py](<E:/PythonCode/EasyChat/tests/test_code_mode_file_ops.py>) | 验证 code_mode_file_ops 相关行为与回归（测试文件名推断） | Code Mode 文件操作工具测试脚本 / 符号 test_read_file_basic, test_search_files_content, test_search_files_name, test_path_traversal, test_blocked_directory, main |
| [test_code_mode_logging.py](<E:/PythonCode/EasyChat/tests/test_code_mode_logging.py>) | 验证 code_mode_logging 相关行为与回归（测试文件名推断） | 测试 Code Mode 日志系统 / 符号 test_log_functions, test_shared_chars_counter, test_execute_code_with_log |
| [test_code_mode_permission_filter.py](<E:/PythonCode/EasyChat/tests/test_code_mode_permission_filter.py>) | 验证 code_mode_permission_filter 相关行为与回归（测试文件名推断） | 测试 Code Mode 权限过滤功能 / 符号 test_tool_toolsets, test_permission_filter, test_role_toolsets, main |
| [test_connection_pool.py](<E:/PythonCode/EasyChat/tests/test_connection_pool.py>) | 验证 connection_pool 相关行为与回归（测试文件名推断） | 连接池单元测试 / 符号 TestConnectionPool, TestConnectionPoolIntegration, TestSchemaGetConn, TestConversationStore |
| [test_context_enrichment.py](<E:/PythonCode/EasyChat/tests/test_context_enrichment.py>) | 验证 context_enrichment 相关行为与回归（测试文件名推断） | 子 Agent 上下文富化 -- 单元测试 / 符号 TestFormatTaskState, TestFormatMemories, TestEnrichContext, TestOutputContract |
| [test_context_strategies.py](<E:/PythonCode/EasyChat/tests/test_context_strategies.py>) | 验证 context_strategies 相关行为与回归（测试文件名推断） | 上下文压缩策略 单元测试 / 符号 TestContextConfig, TestContextFactory, TestFactAnchorHelpers, _build_fake_messages, _FakeInnerCompressor, TestFactAnchorCompress |
| [test_cron_service.py](<E:/PythonCode/EasyChat/tests/test_cron_service.py>) | 验证 cron_service 相关行为与回归（测试文件名推断） | Cron 定时任务服务测试 / 符号 TestBuildTrigger, TestCronDataMapper, TestCronServiceExecution, TestDeliverResult |
| [test_data_layer.py](<E:/PythonCode/EasyChat/tests/test_data_layer.py>) | 验证 data_layer 相关行为与回归（测试文件名推断） | 数据层级（Data Layer）全面测试 / 符号 _check_db, test_list_layers, test_create_layer, test_create_layer_duplicate, test_create_layer_empty_name, test_update_layer, test_update_layer_not_found |
| [test_delegation_bridge.py](<E:/PythonCode/EasyChat/tests/test_delegation_bridge.py>) | 验证 delegation_bridge 相关行为与回归（测试文件名推断） | 多 Agent 委派桥接 —— 真·集成测试 / 符号 FakeChildAgent, FakeParentAgent, _no_real_db, fake_aiagent, clean_enricher, _frame_types, TestRealChildAgentPath |
| [test_delegation_integration.py](<E:/PythonCode/EasyChat/tests/test_delegation_integration.py>) | 验证 delegation_integration 相关行为与回归（测试文件名推断） | 委派上下文富化 -- 集成测试 / 符号 TestEnricherCallbackMechanism, TestSystemPromptSimulation, TestEdgeCases |
| [test_embedding_probe.py](<E:/PythonCode/EasyChat/tests/test_embedding_probe.py>) | 验证 embedding_probe 相关行为与回归（测试文件名推断） | Embedding 连通性探测测试 / 符号 _mysql_available, _MockArkHandler, mock_ark, TestEmbeddingProbeEndpoints, TestEmbeddingProbeE2E |
| [test_host_whitelist.py](<E:/PythonCode/EasyChat/tests/test_host_whitelist.py>) | 验证 host_whitelist 相关行为与回归（测试文件名推断） | 主机白名单 + ssh 目标提取 单元测试 / 符号 TestExtractSshTargets, TestHostAllowedWithPerm, TestHostAllowed |
| [test_kb_eval.py](<E:/PythonCode/EasyChat/tests/test_kb_eval.py>) | 验证 kb_eval 相关行为与回归（测试文件名推断） | RAG 分层评测单元测试 / 符号 _mysql_available, TestRetrievalMetrics, TestTokenizer, TestBM25Retriever, TestEvalService, TestVectorize |
| [test_kb_eval_loop.py](<E:/PythonCode/EasyChat/tests/test_kb_eval_loop.py>) | 验证 kb_eval_loop 相关行为与回归（测试文件名推断） | RAG 评测闭环单元测试 / 符号 _mysql_available, TestClassifyResult, TestAggregateClassifications, TestMetricsImproved, TestSuggestionStateMachine, TestFeedbackSuggestion, TestFeedbackService |
| [test_kb_metadata_global.py](<E:/PythonCode/EasyChat/tests/test_kb_metadata_global.py>) | 验证 kb_metadata_global 相关行为与回归（测试文件名推断） | 测试 Metadata 全局共享方案 / 符号 TestMetadataExtraction, TestMetadataGlobalSharing |
| [test_kb_parent_child.py](<E:/PythonCode/EasyChat/tests/test_kb_parent_child.py>) | 验证 kb_parent_child 相关行为与回归（测试文件名推断） | 父子分片（Parent-Child Chunking）— 主题结构感知版 测试 / 符号 _make_pages, _make_sections, TestDetectStructureBoundaries, TestLongSectionDegradation, TestBasicSplit, TestMetadataInheritance |
| [test_kb_service.py](<E:/PythonCode/EasyChat/tests/test_kb_service.py>) | 验证 kb_service 相关行为与回归（测试文件名推断） | 知识库服务单元测试 / 符号 tmp_pdf, _mysql_available, TestBuiltinParserPdf, TestBuiltinParserText, TestParseWithFallback, TestChunkPages, TestMineruExtractMarkdown |
| [test_kb_topic.py](<E:/PythonCode/EasyChat/tests/test_kb_topic.py>) | 验证 kb_topic 相关行为与回归（测试文件名推断） | 主题切分策略测试 / 符号 _mysql_available, _make_pdf_with_outline, _make_docx_with_headings, _make_pages, TestTopicDetection, TestChunkDocument, TestKbServiceTopic |
| [test_kb_topic_marker.py](<E:/PythonCode/EasyChat/tests/test_kb_topic_marker.py>) | 验证 kb_topic_marker 相关行为与回归（测试文件名推断） | 主题标记切分 + 数据库表关联提取 单元测试 / 符号 TestTopicMarkerSplit, TestDedup, TestSchemaCard |
| [test_llm_gateway.py](<E:/PythonCode/EasyChat/tests/test_llm_gateway.py>) | 验证 llm_gateway 相关行为与回归（测试文件名推断） | LLM 网关（熔断器 + 故障转移）单元测试 / 符号 TestCircuitBreaker, TestModelGateway |
| [test_memory_consistency.py](<E:/PythonCode/EasyChat/tests/test_memory_consistency.py>) | 验证 memory_consistency 相关行为与回归（测试文件名推断） | 测试记忆一致性架构 / 符号 TestOutboxTypes, TestOutboxWriter, TestMemoryServiceOutbox |
| [test_memory_eval_ownership.py](<E:/PythonCode/EasyChat/tests/test_memory_eval_ownership.py>) | 验证 memory_eval_ownership 相关行为与回归（测试文件名推断） | 测试记忆评估接口的归属校验 (T1.3) / 符号 _check_eval_run_permission, TestMemoryEvalOwnership, TestEvalRunOwnershipIntegration |
| [test_model_config_category.py](<E:/PythonCode/EasyChat/tests/test_model_config_category.py>) | 验证 model_config_category 相关行为与回归（测试文件名推断） | 模型配置分类（聊天 / Embedding）测试 / 符号 _mysql_available, TestModelConfigCategory |
| [test_multimodal_embedding.py](<E:/PythonCode/EasyChat/tests/test_multimodal_embedding.py>) | 验证 multimodal_embedding 相关行为与回归（测试文件名推断） | 多模态 Embedding 适配测试（火山方舟 doubao-embedding-vision 等） / 符号 _MockVisionArkHandler, mock_vision, TestVisionEmbeddingDetection, TestVisionProbeEndpoints, TestMultimodalEmbeddings, TestVisionEmbeddingsFactory |
| [test_paper_reproduction.py](<E:/PythonCode/EasyChat/tests/test_paper_reproduction.py>) | 验证 paper_reproduction 相关行为与回归（测试文件名推断） | 论文复现系统单元测试 / 符号 TestConfig, TestSecurity, TestUtilities, TestParsePaper, TestExtractClaimRubric, TestDiscoverRepo, TestDockerSandbox |
| [test_permission.py](<E:/PythonCode/EasyChat/tests/test_permission.py>) | 验证 permission 相关行为与回归（测试文件名推断） | 权限检查器单元测试 / 符号 FakeCache, FakeKeyBuilder, _clear_real_redis_permission_keys, _clear_lru_caches, _assert_user_2_role_not_admin, isolate_permission_cache, TestPermissionChecker |
| [test_report_quality.py](<E:/PythonCode/EasyChat/tests/test_report_quality.py>) | 验证 report_quality 相关行为与回归（测试文件名推断） | 报告质量检查 + 命名规则 单元测试 / 符号 TestReportQuality, TestReportNaming |
| [test_run_registry.py](<E:/PythonCode/EasyChat/tests/test_run_registry.py>) | 验证 run_registry 相关行为与回归（测试文件名推断） | RunRegistry 单元测试 — SSE run 生命周期（事件驱动 subscribe） / 符号 _frames, _expected_frames, TestRunRegistry |
| [test_search_files_smart.py](<E:/PythonCode/EasyChat/tests/test_search_files_smart.py>) | 验证 search_files_smart 相关行为与回归（测试文件名推断） | 测试 search_files 智能搜索功能 / 符号 test_auto_target, test_explicit_target, test_no_result_suggestion, main |
| [test_semantic_ttl.py](<E:/PythonCode/EasyChat/tests/test_semantic_ttl.py>) | 验证 semantic_ttl 相关行为与回归（测试文件名推断） | 语义 TTL 分级单元测试 / 符号 _extract_markers, TestSemanticTTL, _has_marker, _get_ttl |
| [test_session_title.py](<E:/PythonCode/EasyChat/tests/test_session_title.py>) | 验证 session_title 相关行为与回归（测试文件名推断） | 会话自动标题单元测试 / 符号 TestCleanTitle, TestAutoTitleEnabled, TestScheduleAutoTitle, TestAutoTitleTask |
| [test_skill_crud.py](<E:/PythonCode/EasyChat/tests/test_skill_crud.py>) | 验证 skill_crud 相关行为与回归（测试文件名推断） | 技能 CRUD 服务测试 / 符号 TestSkillCRUD |
| [test_skill_scope.py](<E:/PythonCode/EasyChat/tests/test_skill_scope.py>) | 验证 skill_scope 相关行为与回归（测试文件名推断） | 技能按用户隔离（每用户技能视图）单元测试 / 符号 _make_skill, TestPromptBuilderScope, TestSkillsToolScope, TestComputeUserSkillScope |
| [test_skill_service.py](<E:/PythonCode/EasyChat/tests/test_skill_service.py>) | 验证 skill_service 相关行为与回归（测试文件名推断） | 技能服务单元测试 / 符号 TestParseFrontmatter, TestStripFrontmatter, TestValidateName, TestValidateSubpath |
| [test_skill_tool_permissions.py](<E:/PythonCode/EasyChat/tests/test_skill_tool_permissions.py>) | 验证 skill_tool_permissions 相关行为与回归（测试文件名推断） | 技能/工具 归属、发布与审核权限单元测试 / 符号 TestCanAccessSkill, TestCreateSkillPermission, TestPublishToPool, TestPublishSkipReview, TestAdminReviewPermission |
| [test_smart_truncation.py](<E:/PythonCode/EasyChat/tests/test_smart_truncation.py>) | 验证 smart_truncation 相关行为与回归（测试文件名推断） | 结构化截断单元测试 / 符号 TestSmartHeadTail, TestTruncateAtLineBoundary, TestTruncateToolOutput |
| [test_spill_cleanup.py](<E:/PythonCode/EasyChat/tests/test_spill_cleanup.py>) | 验证 spill_cleanup 相关行为与回归（测试文件名推断） | 溢出文件 TTL 清理单元测试 / 符号 temp_spill_dir, TestSpillCleanup |
| [test_sse_contract.py](<E:/PythonCode/EasyChat/tests/test_sse_contract.py>) | 验证 sse_contract 相关行为与回归（测试文件名推断） | SSE 帧契约守卫测试：生产端与消费端的 type 集合必须 ⊆ 契约声明 / 符号 _produced_types, _consumed_types, TestSseContract |
| [test_ssh_auth_inject.py](<E:/PythonCode/EasyChat/tests/test_ssh_auth_inject.py>) | 验证 ssh_auth_inject 相关行为与回归（测试文件名推断） | ssh 凭据注入 单元测试 / 符号 TestInjectSshAuth |
| [test_subagent_sse.py](<E:/PythonCode/EasyChat/tests/test_subagent_sse.py>) | 验证 subagent_sse 相关行为与回归（测试文件名推断） | 子 Agent SSE 可视化 -- 单元测试 / 符号 TestSSEFrameContract, TestPushSubagentSSE |
| [test_task_state.py](<E:/PythonCode/EasyChat/tests/test_task_state.py>) | 验证 task_state 相关行为与回归（测试文件名推断） | task_state 单元测试 / 符号 _disable_task_state_persistence, TestTaskStateConfig, TestTaskStateGC, TestTaskStateFormat, TestTaskStateUpdate, TestTaskStateClear, TestParseJson |
| [test_text_to_sql.py](<E:/PythonCode/EasyChat/tests/test_text_to_sql.py>) | 验证 text_to_sql 相关行为与回归（测试文件名推断） | Text2SQL 工具 单元测试（安全校验 + LIMIT 兜底 + Schema 查询） / 符号 TestValidateReadOnly, TestEnsureLimit, TestGetSchema |
| [test_tool_loader.py](<E:/PythonCode/EasyChat/tests/test_tool_loader.py>) | 验证 tool_loader 相关行为与回归（测试文件名推断） | 用户工具加载器单元测试：可用性隔离 / 编译 / 运行时安全 / 符号 _write_tool, TestToolRecords, TestExecToolCode, TestSafeHandler |
| [test_tool_schema_cache.py](<E:/PythonCode/EasyChat/tests/test_tool_schema_cache.py>) | 验证 tool_schema_cache 相关行为与回归（测试文件名推断） | Tool schema 缓存标记单元测试 / 符号 TestToolSchemaCache |
| [test_toolset_and_session_search.py](<E:/PythonCode/EasyChat/tests/test_toolset_and_session_search.py>) | 验证 toolset_and_session_search 相关行为与回归（测试文件名推断） | 技能 toolset 依赖过滤 + session_search 用户作用域 单元测试 / 符号 _make_skill, TestSkillToolsetFilter, TestSessionSearchScope |
| [test_trace_turns_qna.py](<E:/PythonCode/EasyChat/tests/test_trace_turns_qna.py>) | 验证 trace_turns_qna 相关行为与回归（测试文件名推断） | 可观测性 — 按会话聚合 + 用户问题/AI 回复 测试 / 符号 _mysql_available, TestTraceTurnsQna |
| [test_when_resolver.py](<E:/PythonCode/EasyChat/tests/test_when_resolver.py>) | 验证 when_resolver 相关行为与回归（测试文件名推断） | when_resolver 单元测试 / 符号 TestResolveWhen |

### tests/access/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/access/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | 按目录和文件类型定位 |
| [test_access_draft.py](<E:/PythonCode/EasyChat/tests/access/test_access_draft.py>) | 验证 access_draft 相关行为与回归（测试文件名推断） | Offline regressions for the proposed access fixes. Use replay_access_draft.py. / 符号 access, user, test_concurrent_owner_losses_leave_one_active_owner, test_role_rename_preserves_members_permissions_and_toolsets, test_renaming_to_existing_role_rolls_back_members_and_grants, test_unknown_keys_are_iner |
| [test_cache_invalidation.py](<E:/PythonCode/EasyChat/tests/access/test_cache_invalidation.py>) | 验证 cache_invalidation 相关行为与回归（测试文件名推断） | 缓存失效与即时生效测试：角色变更/禁用用户/授权覆盖立即影响下一次操作。 / 符号 rig, test_role_permission_change_affects_all_role_users_immediately, test_user_role_change_immediate, test_grant_revoke_immediate, test_disable_user_blocks_next_operation_even_with_valid_token, test_validate_principal_revalidates_role_and_revision, test_serv |
| [test_migration_compat.py](<E:/PythonCode/EasyChat/tests/access/test_migration_compat.py>) | 验证 migration_compat 相关行为与回归（测试文件名推断） | P3 受控迁移回归：存量库升级兼容、快照回滚、模板版本语义。 / 符号 test_rollback_restores_snapshot_exactly, test_migration_backfills_legacy_for_existing_roles, test_snapshot_json_records_pre_upgrade_state, test_unseeded_role_is_distinct_from_explicitly_empty, _split_simple, _any_user_of, test_apply_preserves_custom_permissions_an |
| [test_permission_entries.py](<E:/PythonCode/EasyChat/tests/access/test_permission_entries.py>) | 验证 permission_entries 相关行为与回归（测试文件名推断） | 权限入口回归：file.delete / ledger.manage / system.config 的 service 层允许与拒绝。 / 符号 test_file_delete_denied_by_revoke_and_allowed_by_default, test_ledger_manage_denied_by_default_and_allowed_by_grant, test_system_config_denied_by_default_and_allowed_by_grant |
| [test_policy.py](<E:/PythonCode/EasyChat/tests/access/test_policy.py>) | 验证 policy 相关行为与回归（测试文件名推断） | 纯规则测试：有效权限运算 / 工具集过滤 / 资源归属（无 IO）。 / 符号 test_revoke_wins_over_role_and_grant, test_grant_adds_to_role, test_revoke_removes_role_permission, test_super_admin_gets_all_registered_permissions, test_normal_role_cannot_exceed_registered, test_empty_everything_is_empty, test_toolsets_filter_deprecated_and |
| [test_seed_lifecycle.py](<E:/PythonCode/EasyChat/tests/access/test_seed_lifecycle.py>) | 验证 seed_lifecycle 相关行为与回归（测试文件名推断） | 权限整改回归（P1）：模板版本、空权限保持、不自动授予、生命周期、委派边界。 / 符号 _env, _force_legacy_state, _user_id_of, test_builtin_role_with_empty_permissions_stays_empty_after_reseed, test_existing_roles_do_not_gain_new_template_permissions, test_fresh_database_seeds_v2_template, test_deprecated_permissions_do_not_participate_in_ef |

### tests/architecture/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/architecture/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | 按目录和文件类型定位 |
| [test_imports.py](<E:/PythonCode/EasyChat/tests/architecture/test_imports.py>) | 验证 imports 相关行为与回归（测试文件名推断） | 架构机器验证（架构 §12.10）：AST 检查禁用 import、模块私有跨引用、路由SQL与循环依赖。 / 符号 _iter_strict_py_files, _iter_all_backend_py_files, _imports_of, _rel, _parse, test_strict_dirs_forbid_legacy_infra, test_strict_dirs_confine_hermes_imports |
| [test_removed_dependencies.py](<E:/PythonCode/EasyChat/tests/architecture/test_removed_dependencies.py>) | 验证 removed_dependencies 相关行为与回归（测试文件名推断） | 移除依赖的机器验证（Task 15）：新装配路径不得引用已删业务/旧基础设施。 / 符号 _files, test_new_assembly_does_not_import_removed_modules, test_new_app_does_not_mount_removed_prefixes |

### tests/assistant/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/assistant/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | 按目录和文件类型定位 |
| [test_channel_identity.py](<E:/PythonCode/EasyChat/tests/assistant/test_channel_identity.py>) | 验证 channel_identity 相关行为与回归（测试文件名推断） | 渠道身份契约（Task 7）：绑定决定 owner、跨账号不串联、跨端会话独立。 / 符号 _rows, _admin, _user, _register, env, test_binding_owner_decides_not_nickname, test_same_openid_on_two_accounts_routes_to_distinct_owners |
| [test_dispatcher_context.py](<E:/PythonCode/EasyChat/tests/assistant/test_dispatcher_context.py>) | 验证 dispatcher_context 相关行为与回归（测试文件名推断） | RunDispatcher：可信 Principal、人格/时间/附件/记忆上下文与持久 system prompt 隔离。 / 符号 _run_for, test_build_request_uses_snapshot_principal_for_each_role, test_disabled_user_is_rejected_not_defaulted, test_persona_time_attachment_and_memory_prefix, test_memory_recall_failure_does_not_block_request, test_attachment_met |
| [test_engine_history.py](<E:/PythonCode/EasyChat/tests/assistant/test_engine_history.py>) | 验证 engine_history 相关行为与回归（测试文件名推断） | 引擎历史恢复测试：真实临时 state.db，验证归属映射、恢复顺序、压缩容忍。 / 符号 env, _engine_db, test_bind_and_resolve_with_owner_isolation, test_recover_conversation_order_from_state_db, test_compaction_old_session_id_still_resolvable, test_unknown_session_returns_empty_not_error, test_state_db_unavailable_raises_storage_error |
| [test_runs.py](<E:/PythonCode/EasyChat/tests/assistant/test_runs.py>) | 验证 runs 相关行为与回归（测试文件名推断） | Assistant run 生命周期测试：幂等/隔离/串行/busy/取消/重启对账（FakeRuntime）。 / 符号 rig, _cmd, test_duplicate_submit_runs_once, test_final_status_and_projection, _e, test_different_user_cannot_access_run, test_same_session_messages_execute_fifo |

### tests/briefing/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [test_ai_news.py](<E:/PythonCode/EasyChat/tests/briefing/test_ai_news.py>) | 验证 ai_news 相关行为与回归（测试文件名推断） | AI 前沿日报：源抓取、去重排序、LLM 摘要回退与简报接线。 / 符号 _rss, _atom, FakeFetcher, FakeGenerator, _service, test_rss_and_atom_are_parsed_and_ranked_fresh_first, test_duplicate_urls_and_titles_are_removed |
| [test_briefing.py](<E:/PythonCode/EasyChat/tests/briefing/test_briefing.py>) | 验证 briefing 相关行为与回归（测试文件名推断） | 简报：模板事实、数字护栏、情绪跳过/care、安静时段延迟。 / 符号 _ready, FakeScheduling, FakeProfiles, FakeGenerator, _service, _item, test_morning_uses_exact_times_and_counts |
| [test_weekly_occurrences.py](<E:/PythonCode/EasyChat/tests/briefing/test_weekly_occurrences.py>) | 验证 weekly_occurrences 相关行为与回归（测试文件名推断） | 周报“下周”：真实 SchedulingService + SQLite，重复计划必须展开到下一次 occurrence。 / 符号 FakeProfiles, _setup, _target, _at, test_daily_2100_at_2000_moves_to_tomorrow_and_count_is_one, test_weekly_monday_from_thursday_moves_to_next_monday, test_once_tonight_is_not_part_of_next_week |

### tests/channels/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [test_bill_confirm_command.py](<E:/PythonCode/EasyChat/tests/channels/test_bill_confirm_command.py>) | 验证 bill_confirm_command 相关行为与回归（测试文件名推断） | '/账单确认'：完整 ID、owner、权限、控制总额、消息幂等，不经过模型。 / 符号 _msg, _commands, _imported, test_confirm_submits_and_duplicate_message_is_idempotent, test_bare_bill_alias_does_not_trigger_confirmation, test_other_owner_cannot_confirm, test_control_mismatch_requires_explicit_force |
| [test_development_commands.py](<E:/PythonCode/EasyChat/tests/channels/test_development_commands.py>) | 验证 development_commands 相关行为与回归（测试文件名推断） | T5 /开发 命令族：受理幂等、短号解析歧义、补充/取消/重试、回执目标快照。 / 符号 _admin, _user, _msg, _commands, _ask, _rig_with_service, test_dev_command_creates_task_with_source_snapshot |
| [test_durable_intake.py](<E:/PythonCode/EasyChat/tests/channels/test_durable_intake.py>) | 验证 durable_intake 相关行为与回归（测试文件名推断） | T5 持久 inbox：envelope 先落库、内部失败本地重放、毒消息 dead、游标安全。 / 符号 _admin, _user, _register, _bind, _mk_message, test_internal_failure_keeps_event_and_envelope_then_replays, test_poison_message_enters_dead_after_attempts |
| [test_ilink_protocol.py](<E:/PythonCode/EasyChat/tests/channels/test_ilink_protocol.py>) | 验证 ilink_protocol 相关行为与回归（测试文件名推断） | iLink 协议回归：请求头编码、凭据失效分类与账号暂停（工作包二）。 / 符号 test_wechat_uin_encodes_decimal_uint32, test_wechat_uin_is_random_per_call, test_qr_status_polling_sends_app_headers_only, test_post_headers_carry_uin_and_auth, test_classify_channel_error_matches_ret_and_errcode, _reset_guard, test_session_guard_pauses_and_r |
| [test_qr.py](<E:/PythonCode/EasyChat/tests/channels/test_qr.py>) | 验证 qr 相关行为与回归（测试文件名推断） | 微信扫码登录：二维码内容必须渲染成可展示的 PNG data URL。 / 符号 FakeTransport, test_qr_start_returns_png_data_url, PollTimeoutTransport, test_qr_poll_timeout_keeps_waiting_instead_of_500, test_qr_render_failure_returns_empty_fallback |
| [test_voice.py](<E:/PythonCode/EasyChat/tests/channels/test_voice.py>) | 验证 voice 相关行为与回归（测试文件名推断） | 语音链路：纯语音转写失败不得提交 run；混合媒体不阻塞图片。 / 符号 _voice, _voice_with_text, _voice_with_image, FailingSTT, FixedSTT, env, _bound_user |

### tests/context_results/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [test_code_output.py](<E:/PythonCode/EasyChat/tests/context_results/test_code_output.py>) | 验证 code_output 相关行为与回归（测试文件名推断） | Isolated CodeMode capture tests; never initialize application services. / 符号 capture_api, isolated_execution, test_capture_precedes_both_legacy_print_limits, test_internal_tool_values_stay_complete_and_unprinted_locals_are_not_captured, test_hard_limit_counts_utf8_bytes_and_marks_incomplete, test_lo |
| [test_compression.py](<E:/PythonCode/EasyChat/tests/context_results/test_compression.py>) | 验证 compression 相关行为与回归（测试文件名推断） | 符号 managed, AggressiveCompressor, test_generic_pruning_cannot_rewrite_managed_tool_content, test_full_compression_preserves_recoverable_manifest_across_repeated_compaction, test_no_progress_does_not_append_or_mutate_live_history, test_compressor_state_writes_reach_the_same_object_as_usage_updates, t |
| [test_conservative_policy.py](<E:/PythonCode/EasyChat/tests/context_results/test_conservative_policy.py>) | 验证 conservative_policy 相关行为与回归（测试文件名推断） | Candidate-field preservation is explicit, bounded and separate from protected facts. / 符号 parts, view, test_unknown_nested_fields_are_copied_without_becoming_protected, test_other_fields_have_real_array_and_escaped_pointers, test_long_values_are_omitted_without_silent_truncation_and_shallow_fields_w |
| [test_eval_metrics.py](<E:/PythonCode/EasyChat/tests/context_results/test_eval_metrics.py>) | 验证 eval_metrics 相关行为与回归（测试文件名推断） | Provider billable buckets must be complete and not double-count cached input. / 符号 metrics, test_zero_uncached_and_cache_read_are_not_counted_twice, test_missing_usage_is_unknown, test_anthropic_input_does_not_already_include_cache, test_unknown_price_is_not_free, test_aggregate_includes_failed_call |
| [test_eval_profiles.py](<E:/PythonCode/EasyChat/tests/context_results/test_eval_profiles.py>) | 验证 eval_profiles 相关行为与回归（测试文件名推断） | Experiment preparation must be useful without credentials or model execution. / 符号 profiles, config, test_plan_crosses_tasks_repeats_profiles_and_pins_all_modes, test_invalid_profile_is_rejected_before_execution, test_invalid_schedule_limits_are_rejected, test_prepare_only_cli_needs_no_upstream_or_c |
| [test_eval_report.py](<E:/PythonCode/EasyChat/tests/context_results/test_eval_report.py>) | 验证 eval_report 相关行为与回归（测试文件名推断） | 符号 test_report_keeps_failures_and_marks_partial_usage_unknown |
| [test_eval_validation.py](<E:/PythonCode/EasyChat/tests/context_results/test_eval_validation.py>) | 验证 eval_validation 相关行为与回归（测试文件名推断） | 符号 validate, test_fact_accuracy_and_format_are_reported_separately, test_exact_json_or_single_fenced_json_is_valid, test_wrong_first_object_and_missing_values_are_not_rescued_by_answer_search, test_boolean_receipt_cannot_be_replaced_with_numeric_zero |
| [test_executor_integration.py](<E:/PythonCode/EasyChat/tests/context_results/test_executor_integration.py>) | 验证 executor_integration 相关行为与回归（测试文件名推断） | Exercise the real Hermes dispatch paths without providers or production config. / 符号 content_hash, Runtime, harness, call, test_real_dispatch_routes_prepare_then_seal_before_persistence, test_inline_todo_uses_same_boundary, test_managed_steer_does_not_mutate_sealed_view |
| [test_host_adapter.py](<E:/PythonCode/EasyChat/tests/context_results/test_host_adapter.py>) | 验证 host_adapter 相关行为与回归（测试文件名推断） | Execute the real adapter handler without importing its service bootstrapping. / 符号 handler_factory, test_project_handler_preserves_original_until_managed_boundary, test_project_handler_retains_disabled_legacy_guard |
| [test_manager.py](<E:/PythonCode/EasyChat/tests/context_results/test_manager.py>) | 验证 manager 相关行为与回归（测试文件名推断） | Offline contracts for deterministic model views (never load application .env). / 符号 components, test_long_json_protects_middle_fields_and_restores_original, test_small_result_is_unchanged_and_view_hash_is_final_content, test_multimodal_is_not_stringified, test_protected_overflow_is_explicit_and_orig |
| [test_projection_modes.py](<E:/PythonCode/EasyChat/tests/context_results/test_projection_modes.py>) | 验证 projection_modes 相关行为与回归（测试文件名推断） | Projection modes share a ledger; delta correctness depends on retained history. / 符号 observe, project, test_projection_mode_never_disables_the_evidence_ledger, test_delta_only_projects_new_records_and_rebases_after_history_loss, test_full_remains_full_after_each_new_record, test_delta_does_not_treat |
| [test_storage_boundary.py](<E:/PythonCode/EasyChat/tests/context_results/test_storage_boundary.py>) | 验证 storage_boundary 相关行为与回归（测试文件名推断） | 符号 test_default_store_lives_outside_source_workspace, test_configured_store_is_not_readable_through_code_mode_files, test_legacy_workspace_store_remains_blocked, test_sibling_prefix_is_not_a_workspace_child |
| [test_store.py](<E:/PythonCode/EasyChat/tests/context_results/test_store.py>) | 验证 store 相关行为与回归（测试文件名推断） | Isolated, real-filesystem contracts for retained tool results. / 符号 scope, store, test_scope_is_frozen_with_safe_defaults, test_roundtrip_has_content_hash_and_capture_completeness, test_read_and_search_refuse_other_owners, test_grant_is_per_artifact_persisted_and_cannot_be_reshared, test_session_run |
| [test_structured_recovery.py](<E:/PythonCode/EasyChat/tests/context_results/test_structured_recovery.py>) | 验证 structured_recovery 相关行为与回归（测试文件名推断） | Search-to-read contracts using real originals, scoped storage and tool budgets. / 符号 scope, store, search_value, test_nested_alias_key_and_value_recover_without_guessing, test_array_and_escaped_keys_produce_readable_pointers, test_escaped_unicode_source_key_uses_decoded_path, test_root_scalar_has_em |
| [test_subagent_result_events.py](<E:/PythonCode/EasyChat/tests/context_results/test_subagent_result_events.py>) | 验证 subagent_result_events 相关行为与回归（测试文件名推断） | Exercise the real child progress relay without providers or app startup. / 符号 delegate_module, child_callback, test_completed_result_metadata_reaches_real_parent_callback, test_completion_neither_counts_nor_batches_a_second_tool, test_stage_is_derived_from_event_and_completion_without_start_is_not_c |
| [test_task_evidence.py](<E:/PythonCode/EasyChat/tests/context_results/test_task_evidence.py>) | 验证 task_evidence 相关行为与回归（测试文件名推断） | 符号 ledger, event, test_batch_commit_is_atomic_idempotent_and_keeps_conflicts, test_users_threads_children_and_physical_session_rotation, test_parallel_commits_do_not_lose_records_and_restart_restores, test_taskstate_semantic_reset_cannot_delete_evidence, test_retention_and_source_expiry_are_explicit |
| [test_tools.py](<E:/PythonCode/EasyChat/tests/context_results/test_tools.py>) | 验证 tools 相关行为与回归（测试文件名推断） | Trusted tool scope, runtime lifetime and bounded recovery. / 符号 api, test_unbound_tools_cannot_accept_identity_or_read, test_runtime_recovery_and_physical_session_rollover, test_child_does_not_inherit_parent_artifact_permission, test_disabled_binding_preserves_no_runtime, test_disabled_new_agent_sti |
| [test_usage_optimization.py](<E:/PythonCode/EasyChat/tests/context_results/test_usage_optimization.py>) | 验证 usage_optimization 相关行为与回归（测试文件名推断） | 符号 usage, test_normalized_zero_input_is_not_replaced_by_prompt_total, test_raw_chat_usage_subtracts_cache_once, test_anthropic_buckets_are_additive, test_unknown_usage_does_not_become_zero, test_invalid_cache_count_does_not_create_negative_input, test_context_restores_and_distinguishes_runs |

### tests/contracts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/contracts/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | 按目录和文件类型定位 |
| [test_api_compatibility.py](<E:/PythonCode/EasyChat/tests/contracts/test_api_compatibility.py>) | 验证 api_compatibility 相关行为与回归（测试文件名推断） | API 兼容测试（Task 15）：新工厂显式路由、旧前缀不再暴露、未就绪明确 503。 / 符号 _settings, client, test_explicit_routes_and_health, test_removed_module_prefixes_not_mounted, test_register_login_and_memory_ownership, test_assistant_route_reports_unavailable_without_runtime, test_usage_endpoints_match_usage_view_contract |
| [test_app_factory.py](<E:/PythonCode/EasyChat/tests/contracts/test_app_factory.py>) | 验证 app_factory 相关行为与回归（测试文件名推断） | 工厂契约测试（Task 1）。 / 符号 _tmp_settings, test_import_backend_app_is_offline_and_dotenv_free, test_factory_run_is_offline, test_create_app_has_no_side_effects, test_readyz_503_before_lifespan, test_error_mapping_table_complete, test_typed_errors_raise_and_map |
| [test_auth.py](<E:/PythonCode/EasyChat/tests/contracts/test_auth.py>) | 验证 auth 相关行为与回归（测试文件名推断） | 认证与授权契约测试：注册/登录/token 生命周期/HTTP路由/被拒请求不触发Runtime。 / 符号 rig, test_scrypt_hash_and_verify, test_legacy_sha256_hash_verifies_and_needs_rehash, test_legacy_login_upgrades_hash, test_register_login_flow, test_register_validation_and_duplicates, test_login_failures |
| [test_chat_uploads.py](<E:/PythonCode/EasyChat/tests/contracts/test_chat_uploads.py>) | 验证 chat_uploads 相关行为与回归（测试文件名推断） | Offline upload compatibility with managed files and owned run attachments. / 符号 uploads, auth, test_file_upload_is_registered_and_sent_as_owned_attachment, test_image_upload_validates_content_and_preserves_preview |
| [test_file_upload.py](<E:/PythonCode/EasyChat/tests/contracts/test_file_upload.py>) | 验证 file_upload 相关行为与回归（测试文件名推断） | F3：Web 上传/下载 HTTP 契约（显式路由 + 鉴权 + 不暴露内部路径）。 / 符号 _client, _auth, test_upload_download_roundtrip, test_upload_idempotent_request_id, test_upload_requires_token, test_cross_owner_guess_returns_404, test_delete_unlink_keeps_downloadable |
| [test_frontend_compat.py](<E:/PythonCode/EasyChat/tests/contracts/test_frontend_compat.py>) | 验证 frontend_compat 相关行为与回归（测试文件名推断） | 前端移除契约（Task 15）：不得再引用已删 KB/图谱/论文/社区页面或 API。 / 符号 test_frontend_sources_do_not_call_removed_apis, test_router_and_views_removed, test_removed_graph_packages_gone |
| [test_ledger_api.py](<E:/PythonCode/EasyChat/tests/contracts/test_ledger_api.py>) | 验证 ledger_api 相关行为与回归（测试文件名推断） | F6/F8：账本 HTTP 契约（鉴权、导入、提交、统计、图片候选、退款链接）。 / 符号 FakeVision, _client, _LazyLedger, _auth, test_endpoints_require_token, test_permission_denied_without_ledger_view, test_import_commit_analyze_over_http |
| [test_mcp.py](<E:/PythonCode/EasyChat/tests/contracts/test_mcp.py>) | 验证 mcp 相关行为与回归（测试文件名推断） | MCP 适配契约测试：配置归一化、错误分类、目录刷新保留、健康隔离（全部用假registrar）。 / 符号 _cfg, test_config_normalized_to_hermes_entry, test_register_ok_lists_tools, test_empty_catalog_is_explicit_error_kind, test_error_classification, test_failed_registration_does_not_raise_and_records_kind, test_registrar_exception_marks_all_failed |
| [test_runtime.py](<E:/PythonCode/EasyChat/tests/contracts/test_runtime.py>) | 验证 runtime 相关行为与回归（测试文件名推断） | Runtime Seam 契约测试：Protocol 符合性、事件桥接、缓存隔离、ContextVar传播、取消。 / 符号 _ctx, _req, test_fake_runtime_satisfies_protocol, StubAgent, _adapter, test_execute_bridges_events_to_completed, test_execute_failed_runner_yields_failed_event |
| [test_sse.py](<E:/PythonCode/EasyChat/tests/contracts/test_sse.py>) | 验证 sse 相关行为与回归（测试文件名推断） | SSE 契约测试：帧格式/续传/环形缓存失效 resync/取消帧（对照 legacy-sse.json）。 / 符号 _e, rig, _collect_frames, test_frames_id_seq_monotonic_and_resume, _drain, test_token_coalescing_within_window, test_ring_buffer_truncation_signals_resync |
| [test_superagent_api.py](<E:/PythonCode/EasyChat/tests/contracts/test_superagent_api.py>) | 验证 superagent_api 相关行为与回归（测试文件名推断） | superagent HTTP 契约：capabilities、配置、幂等受理、inputs、增量事件、权限。 / 符号 rig, _service, _client, _headers, test_capabilities_reports_gate_and_hides_repo_from_user, test_settings_roundtrip_verify_profile_and_strict_url, test_task_create_idempotency_header_and_isolation |
| [test_tool_context.py](<E:/PythonCode/EasyChat/tests/contracts/test_tool_context.py>) | 验证 tool_context 相关行为与回归（测试文件名推断） | ToolContext 双通道与线程传播。 / 符号 _ctx, test_bind_and_reset_are_scoped, test_config_channel_wins_over_contextvar, test_from_config_rejects_non_tool_context_values, test_contextvar_survives_copy_context_to_worker_thread, test_tool_schema_preserves_non_string_parameter_types, test_tool_config_uses_session_wh |
| [test_toolset_exposure.py](<E:/PythonCode/EasyChat/tests/contracts/test_toolset_exposure.py>) | 验证 toolset_exposure 相关行为与回归（测试文件名推断） | P9 实测缺陷回归：项目业务工具必须可经 toolset 暴露进模型 schema。 / 符号 tool_definitions, test_always_group_resolves_project_tools, test_groups_without_always_do_not_leak_project_tools, test_dispatcher_chat_request_enables_always_group, test_project_tools_survive_tool_search_disclosure |
| [test_web_chat.py](<E:/PythonCode/EasyChat/tests/contracts/test_web_chat.py>) | 验证 web_chat 相关行为与回归（测试文件名推断） | Web 聊天兼容契约测试：旧 /chat/stream 契约 → 统一 Assistant（单循环 httpx ASGI）。 / 符号 _e, rig, _client, _auth_headers, _token, _read_sse, test_stream_legacy_thread_id_full_flow |
| [test_wechat.py](<E:/PythonCode/EasyChat/tests/contracts/test_wechat.py>) | 验证 wechat 相关行为与回归（测试文件名推断） | 渠道契约测试（Task 7）：iLink 归一化、绑定身份、持久去重、扫码与监听生命周期。 / 符号 _completed, _rows, _admin, _user, _register, _bind, _wait_until |

### tests/delivery/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/delivery/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | delivery/scheduling 测试包。 |
| [test_delivery.py](<E:/PythonCode/EasyChat/tests/delivery/test_delivery.py>) | 验证 delivery 相关行为与回归（测试文件名推断） | 投递账本测试（Task 8）：成功、重试、uncertain、分块续发、解绑与 run 完成同事务。 / 符号 _completed, _user, _service, env, test_text_delivery_succeeds_once, test_retry_resumes_only_unsent_chunks, test_uncertain_is_not_auto_resent |
| [test_email.py](<E:/PythonCode/EasyChat/tests/delivery/test_email.py>) | 验证 email 相关行为与回归（测试文件名推断） | 邮件能力测试（Task 14）：配置加密、RBAC、默认关闭、假 SMTP 分类。 / 符号 FakeSMTP, env, _enable, test_config_password_encrypted_and_masked, test_config_requires_system_config, test_disabled_smtp_does_not_connect, test_fake_smtp_sends_text |
| [test_reports.py](<E:/PythonCode/EasyChat/tests/delivery/test_reports.py>) | 验证 reports 相关行为与回归（测试文件名推断） | 报告/PDF 测试（Task 14）：能力关闭明确失败、artifact 不可变、附件投递不重渲染。 / 符号 FakeRenderer, TimeoutRenderer, env, test_pdf_artifact_then_email_delivery_without_rerender, test_disabled_pdf_fails_explicitly_without_artifact, test_render_timeout_fails_explicitly, test_pdf_capability_checks_are_lazy |
| [test_schedule.py](<E:/PythonCode/EasyChat/tests/delivery/test_schedule.py>) | 验证 schedule 相关行为与回归（测试文件名推断） | 持久提醒测试（Task 8）：一次性、间隔、每日、错过收敛、重启不重复。 / 符号 _user, _services, env, test_once_due_exactly_once, test_interval_catches_up_latest_only, test_daily_catches_up_latest_slot, test_disabled_schedule_does_not_fire |
| [test_wechat_error_classification.py](<E:/PythonCode/EasyChat/tests/delivery/test_wechat_error_classification.py>) | 验证 wechat_error_classification 相关行为与回归（测试文件名推断） | 微信发送异常分类：永久失败/可重试/结果未知不得混淆。 / 符号 test_classification, _Channels, test_sender_maps_failure_to_non_retryable, test_sender_maps_timeout_to_uncertain |
| [test_wechat_rendering.py](<E:/PythonCode/EasyChat/tests/delivery/test_wechat_rendering.py>) | 验证 wechat_rendering 相关行为与回归（测试文件名推断） | 微信纯文本渲染与按目标分块。 / 符号 test_markdown_is_degraded_to_plain_text, test_default_chunk_constant_unchanged, test_wechat_uses_500_and_email_1800 |

### tests/evolution/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/evolution/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | evolution 测试包。 |
| [test_adoption.py](<E:/PythonCode/EasyChat/tests/evolution/test_adoption.py>) | 验证 adoption 相关行为与回归（测试文件名推断） | 候选采用测试（Task 12）：CAS 陈旧指针、pin 保护、回滚、证据记录。 / 符号 _replayer, _setup, test_adopt_switches_pointer_and_rollback_restores, test_failed_report_keeps_original, test_pinned_skill_is_not_auto_adopted, test_stale_expected_pointer_conflict |
| [test_budget.py](<E:/PythonCode/EasyChat/tests/evolution/test_budget.py>) | 验证 budget 相关行为与回归（测试文件名推断） | 进化预算测试（Task 11）：预留/核销/未知 usage/每日重置/超预算停止。 / 符号 env, test_reserve_and_settle_known_usage, test_unknown_usage_keeps_reservation, test_daily_and_single_task_limits, test_daily_reset_by_project_timezone, test_new_manager_reads_persisted_budget, test_over_budget_stops_before_learner |
| [test_runner_contract.py](<E:/PythonCode/EasyChat/tests/evolution/test_runner_contract.py>) | 验证 runner_contract 相关行为与回归（测试文件名推断） | Runner 契约测试（Task 13）：默认关闭、能力/路径拒绝、假 Runner 流程。 / 符号 FakeRunner, _input, test_limits_reject_unsafe_values, test_default_runner_is_disabled_and_says_denied, test_fake_runner_flow_carries_only_capabilities, test_local_runner_network_and_path_denied, test_local_runner_disabled_by_default |
| [test_signals.py](<E:/PythonCode/EasyChat/tests/evolution/test_signals.py>) | 验证 signals 相关行为与回归（测试文件名推断） | 学习信号测试（Task 11）：去重、禁用/撤权、暂停、lease 恢复、系统主体。 / 符号 _user, _admin, env, test_duplicate_feedback_learns_once, test_disabled_user_blocks_learning, test_revoked_permission_blocks_learning, test_pause_prevents_claim_until_resumed |
| [test_validation.py](<E:/PythonCode/EasyChat/tests/evolution/test_validation.py>) | 验证 validation 相关行为与回归（测试文件名推断） | 候选验证测试（Task 12）：固定顺序、回归判定、原版更好不采用、无副作用回放。 / 符号 _cases, _replayer, _setup, test_candidate_passes_required_and_improves, test_original_better_is_not_adopted, test_no_improvement_not_adopted, test_new_skill_without_baseline_cannot_prove_no_regression |

### tests/files/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/files/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | 按目录和文件类型定位 |
| [helpers.py](<E:/PythonCode/EasyChat/tests/files/helpers.py>) | 自动化测试、fixture和临时SQLite测试支撑中的helpers 实现（目录与文件名推断） | files 测试公共设施：真实临时 SQLite + 临时磁盘目录，不触碰仓库 data/。 / 符号 make_files_rig, chunks_of, async_chunks_of |
| [test_legacy_bridge.py](<E:/PythonCode/EasyChat/tests/files/test_legacy_bridge.py>) | 验证 legacy_bridge 相关行为与回归（测试文件名推断） | F3：旧 attachment_id/artifact_id 桥接 + 微信媒体走统一文件权威。 / 符号 _rows, _admin, _user, _register, _bind, test_attachment_keeps_legacy_id_and_links_stored_file, test_legacy_attachment_without_stored_file_still_works |
| [test_lifecycle.py](<E:/PythonCode/EasyChat/tests/files/test_lifecycle.py>) | 验证 lifecycle 相关行为与回归（测试文件名推断） | F11：派生内容过期清理、配额与磁盘水位、原件保护。 / 符号 _derived, _backdate, _lifecycle, test_sweep_deletes_only_expired_unreferenced_derived, test_dry_run_reports_without_deleting, test_permanent_original_never_swept, test_quota_refuses_new_save_without_deleting_old |
| [test_metadata.py](<E:/PythonCode/EasyChat/tests/files/test_metadata.py>) | 验证 metadata 相关行为与回归（测试文件名推断） | F1：统一文件模型 + 0011 迁移（元数据、归属隔离、内容去重与引用）。 / 符号 _sqlite_column_names, test_migration_0011_creates_tables_and_legacy_columns, test_save_and_get_roundtrip, test_original_name_sanitized_and_not_used_in_path, test_same_owner_same_content_reuses_file_with_separate_receipts, test_different_owners_do_not_share |
| [test_persistence.py](<E:/PythonCode/EasyChat/tests/files/test_persistence.py>) | 验证 persistence 相关行为与回归（测试文件名推断） | F2：流式保存、受限读取与内容校验（路径穿越/类型/压缩/像素）。 / 符号 test_interrupted_stream_then_retry_succeeds, test_size_limit_rejected_and_partial_removed, test_hash_mismatch_after_move_fails_without_ready, test_only_ready_file_is_readable, test_path_traversal_and_absolute_paths_rejected, test_symlink_escape_rejected, test_o |

### tests/fixtures/contracts/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [legacy-api.json](<E:/PythonCode/EasyChat/tests/fixtures/contracts/legacy-api.json>) | 自动化测试、fixture和临时SQLite测试支撑的配置或结构化资源，主题 legacy-api（目录与文件名推断） | 按目录和文件类型定位 |
| [legacy-sse.json](<E:/PythonCode/EasyChat/tests/fixtures/contracts/legacy-sse.json>) | 自动化测试、fixture和临时SQLite测试支撑的配置或结构化资源，主题 legacy-sse（目录与文件名推断） | 按目录和文件类型定位 |

### tests/fixtures/evolution/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [regression.json](<E:/PythonCode/EasyChat/tests/fixtures/evolution/regression.json>) | 自动化测试、fixture和临时SQLite测试支撑的配置或结构化资源，主题 regression（目录与文件名推断） | 按目录和文件类型定位 |

### tests/fixtures/kb_eval/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [01_数据库表结构参考.md](<E:/PythonCode/EasyChat/tests/fixtures/kb_eval/01_数据库表结构参考.md>) | 自动化测试、fixture和临时SQLite测试支撑的说明、设计或验证文档，主题 01_数据库表结构参考（目录与文件名推断） | 数据库表结构参考 |
| [02_系统运维手册.md](<E:/PythonCode/EasyChat/tests/fixtures/kb_eval/02_系统运维手册.md>) | 自动化测试、fixture和临时SQLite测试支撑的说明、设计或验证文档，主题 02_系统运维手册（目录与文件名推断） | AgentForge 系统运维手册 |
| [03_API接口文档.md](<E:/PythonCode/EasyChat/tests/fixtures/kb_eval/03_API接口文档.md>) | 自动化测试、fixture和临时SQLite测试支撑的说明、设计或验证文档，主题 03_API接口文档（目录与文件名推断） | AgentForge API 接口文档 |
| [04_常见问题FAQ.md](<E:/PythonCode/EasyChat/tests/fixtures/kb_eval/04_常见问题FAQ.md>) | 自动化测试、fixture和临时SQLite测试支撑的说明、设计或验证文档，主题 04_常见问题FAQ（目录与文件名推断） | AgentForge 常见问题 FAQ |
| [README.md](<E:/PythonCode/EasyChat/tests/fixtures/kb_eval/README.md>) | 自动化测试、fixture和临时SQLite测试支撑的说明、设计或验证文档，主题 README（目录与文件名推断） | 知识库评测测试文档（KB Eval Fixtures） |

### tests/fixtures/kg_eval/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [gold_standard.json](<E:/PythonCode/EasyChat/tests/fixtures/kg_eval/gold_standard.json>) | 自动化测试、fixture和临时SQLite测试支撑的配置或结构化资源，主题 gold_standard（目录与文件名推断） | 按目录和文件类型定位 |

### tests/fixtures/ledger/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [README.md](<E:/PythonCode/EasyChat/tests/fixtures/ledger/README.md>) | 自动化测试、fixture和临时SQLite测试支撑的说明、设计或验证文档，主题 README（目录与文件名推断） | 合成账单夹具（F0） |

### tests/fixtures/memory/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [cases.json](<E:/PythonCode/EasyChat/tests/fixtures/memory/cases.json>) | 自动化测试、fixture和临时SQLite测试支撑的配置或结构化资源，主题 cases（目录与文件名推断） | 按目录和文件类型定位 |

### tests/inbox/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [test_inbox.py](<E:/PythonCode/EasyChat/tests/inbox/test_inbox.py>) | 验证 inbox 相关行为与回归（测试文件名推断） | 收件箱：去重更新、owner 隔离、搜索/归档、SSRF 与富化、工具身份。 / 符号 _rig, _service, test_same_url_updates_note_and_tags, test_daily_enrich_limit_saves_but_does_not_fetch_after_twenty, test_owner_isolation_and_not_found, test_search_and_archive, test_enrich_does_not_overwrite_user_title_with_empty_page_title |

### tests/integration/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [test_linux_runner.py](<E:/PythonCode/EasyChat/tests/integration/test_linux_runner.py>) | 验证 linux_runner 相关行为与回归（测试文件名推断） | 真实 Linux Runner 隔离验收（integration，默认排除；未通过前自动执行保持关闭）。 / 符号 test_linux_runner_blocks_path_escape_and_timeout |

### tests/ledger/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/ledger/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | 按目录和文件类型定位 |
| [helpers.py](<E:/PythonCode/EasyChat/tests/ledger/helpers.py>) | 自动化测试、fixture和临时SQLite测试支撑中的helpers 实现（目录与文件名推断） | 账本测试夹具：真实临时 SQLite + 临时文件根 + 合成账单。 / 符号 make_ledger_rig, upload_bill, import_bill |
| [test_extraction.py](<E:/PythonCode/EasyChat/tests/ledger/test_extraction.py>) | 验证 extraction 相关行为与回归（测试文件名推断） | 账单截图识别候选（F6）单测：字段归一、置信度、缺失字段、修正与 Adapter 端口。 / 符号 _candidate, FakeVision, test_default_payload_is_ready_for_confirmation, test_raw_text_is_truncated_to_4000_chars, test_missing_amount_is_none_not_zero, test_unparsable_amount_keeps_none_with_chinese_note, test_missing_direction_becomes_unknown |
| [test_identity.py](<E:/PythonCode/EasyChat/tests/ledger/test_identity.py>) | 验证 identity 相关行为与回归（测试文件名推断） | F5：交易身份/去重/状态合并/退款匹配的纯函数测试。 / 符号 _row, _mapping, test_identity_key_is_stable_and_account_scoped, test_identity_key_preserves_28_digit_external_id, test_float_truncated_external_id_falls_back_to_candidate, test_payment_and_refund_sharing_external_id_have_distinct_keys, test_identity_without_ids_uses_ |
| [test_import_flow.py](<E:/PythonCode/EasyChat/tests/ledger/test_import_flow.py>) | 验证 import_flow 相关行为与回归（测试文件名推断） | F4/F5：导入状态机、控制总额、去重、状态更新、退款与三口径统计的端到端测试。 / 符号 _rows, _plan, _metric, test_migration_0013_upgrades_existing_0012_database, test_migration_0012_creates_ledger_tables, test_standard_xlsx_parse_and_commit, test_control_total_mismatch_blocks_commit_until_confirmed |
| [test_intent.py](<E:/PythonCode/EasyChat/tests/ledger/test_intent.py>) | 验证 intent 相关行为与回归（测试文件名推断） | F9：意图路由与工具面（模型只理解/翻译，金额与 SQL 全由受控代码负责）。 / 符号 test_classify_common_intents, test_classify_unknown_asks_for_clarification, test_plan_from_text_periods_and_basis, test_plan_from_text_defaults_when_no_time_mentioned, FakePlanner, BrokenPlanner, test_planner_output_with_sql_is_rejected_not_executed |
| [test_parsers.py](<E:/PythonCode/EasyChat/tests/ledger/test_parsers.py>) | 验证 parsers 相关行为与回归（测试文件名推断） | F4 解析器测试：表头不定行、编码/分隔符、控制总额、坏行保留、截断、格式探测。 / 符号 _parse, test_header_position_is_detected_by_content, test_long_transaction_id_is_not_truncated, test_extra_sheets_are_parsed_with_sheet_in_locator, test_standard_scenario_roles_and_directions, test_control_totals_are_extracted, test_mismatched_totals_are |
| [test_query.py](<E:/PythonCode/EasyChat/tests/ledger/test_query.py>) | 验证 query 相关行为与回归（测试文件名推断） | ledger QueryPlan 验证与参数化 SQL 编译测试（全部离线，不连数据库）。 / 符号 _raw, _plan, _compiled, test_summary_plan_validates_and_compiles, test_aggregate_has_six_metric_columns, test_month_group_plan_shape, test_two_dimension_group_and_empty_group |
| [test_reports.py](<E:/PythonCode/EasyChat/tests/ledger/test_reports.py>) | 验证 reports 相关行为与回归（测试文件名推断） | F10：账本报告生成（确定性排版 + 落 files + 可下载 + 留痕）。 / 符号 _plan, _ready, test_markdown_report_is_saved_and_downloadable, test_csv_report_contains_details, FakePdfRenderer, test_pdf_report_uses_renderer_and_is_saved, test_pdf_without_renderer_is_explicit_error |
| [test_rules.py](<E:/PythonCode/EasyChat/tests/ledger/test_rules.py>) | 验证 rules 相关行为与回归（测试文件名推断） | F7：分类、规则、手工修正、软删除与审计（真实 SQLite）。 / 符号 _committed, _rows, test_category_crud_and_duplicate_name, test_category_requires_manage_permission, test_rule_applies_only_to_uncategorized_and_respects_priority, test_rule_validation_rejects_unknown_field_and_op, test_update_transaction_writes_audit_change |
| [test_worker.py](<E:/PythonCode/EasyChat/tests/ledger/test_worker.py>) | 验证 worker 相关行为与回归（测试文件名推断） | F4/F5：账本解析 worker 的队列语义（认领、完成、损坏文件不无限重试）。 / 符号 _jobs, test_register_enqueues_and_worker_parses, test_tick_without_jobs_is_noop, test_duplicate_parse_jobs_do_not_duplicate_rows, test_corrupt_file_ends_in_failed_state_without_retry, test_missing_blob_is_retryable_not_permanent_failure |

### tests/memory/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/memory/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | memory 模块测试包。 |
| [helpers.py](<E:/PythonCode/EasyChat/tests/memory/helpers.py>) | 自动化测试、fixture和临时SQLite测试支撑中的helpers 实现（目录与文件名推断） | memory 测试辅助：加载 20 条脱敏用例并在真实临时 SQLite 上播种。 / 符号 load_cases, make_memory_rig, owner_a, owner_b, candidate_from_case, seed_case, seed_all |
| [test_bridge.py](<E:/PythonCode/EasyChat/tests/memory/test_bridge.py>) | 验证 bridge 相关行为与回归（测试文件名推断） | Hermes MemoryProvider 桥接测试：只走公开接口、无结果不编造、来源可见。 / 符号 test_prefetch_without_memory_says_no_result, test_prefetch_includes_content_and_sources, test_bridge_remember_goes_through_service |
| [test_explicit_capture.py](<E:/PythonCode/EasyChat/tests/memory/test_explicit_capture.py>) | 验证 explicit_capture 相关行为与回归（测试文件名推断） | 显式记忆捕获：LLM 候选提取、服务端来源、幂等与确定性降级。 / 符号 test_explicit_remember_writes_user_confirmed_memory, test_plain_message_does_not_enqueue_capture, test_remember_word_inside_sentence_is_not_a_command, test_extract_trigger_covers_natural_explicit_expressions, FakeGenerator, _submit, _enqueue |
| [test_forgetting.py](<E:/PythonCode/EasyChat/tests/memory/test_forgetting.py>) | 验证 forgetting 相关行为与回归（测试文件名推断） | 遗忘测试（Task 9）：墓碑不保留原文、版本清除、按来源/内容阻止重提取。 / 符号 env, _candidate, test_forget_by_memory_id_scrubs_content_and_history, test_forget_by_memory_id_blocks_reextraction, test_forget_by_source_ref_cascades_and_blocks_source, test_forget_by_query_scrubs_matching_content, test_forget_rule_can_precede_extraction |
| [test_retrieval.py](<E:/PythonCode/EasyChat/tests/memory/test_retrieval.py>) | 验证 retrieval 相关行为与回归（测试文件名推断） | 记忆召回测试（Task 9）：20 条脱敏用例、中文短词/同义、预算、来源与权限。 / 符号 env, test_fixture_has_twenty_cases_and_required_categories, test_hit_cases_recall_with_sources, test_similar_events_rank_the_relevant_one_first, test_no_result_cases_are_explicit, test_archived_requires_old_memory_hint, test_missing_source_and_hypotheti |
| [test_revision.py](<E:/PythonCode/EasyChat/tests/memory/test_revision.py>) | 验证 revision 相关行为与回归（测试文件名推断） | 记忆版本/反馈/幂等信号测试（Task 9）。 / 符号 _candidate, env, test_revise_increments_version_and_keeps_history, test_stale_expected_version_rejected, test_empty_revision_rejected, test_feedback_is_idempotent, test_source_type_and_confidence_retained |

### tests/models/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/models/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | 按目录和文件类型定位 |
| [test_configs.py](<E:/PythonCode/EasyChat/tests/models/test_configs.py>) | 验证 configs 相关行为与回归（测试文件名推断） | models 模块行为测试：配置CRUD、密钥保护、选择、fallback链、健康状态。 / 符号 models, test_create_and_masking, test_config_version_bumps_on_update, test_active_pointer_switches_atomically, test_delete_missing_and_invalid_inputs, test_permission_required_for_management, test_select_for_run_with_auxiliary_fallback |
| [test_fallback_contract.py](<E:/PythonCode/EasyChat/tests/models/test_fallback_contract.py>) | 验证 fallback_contract 相关行为与回归（测试文件名推断） | Fallback management preserves order and serializes slotted model profiles. / 符号 test_fallback_chain_route_round_trip, test_runtime_receives_configured_fallback_profile, test_session_cache_rebuilds_for_model_and_fallback_changes |

### tests/profiles/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/profiles/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | 按目录和文件类型定位 |
| [test_care.py](<E:/PythonCode/EasyChat/tests/profiles/test_care.py>) | 验证 care 相关行为与回归（测试文件名推断） | C3 主动关心：连续 3 个低分自然日、7 天间隔、proactivity、安静时段延迟。 / 符号 _setup, _low, test_care_due_requires_three_consecutive_low_days, test_missing_day_breaks_consecutive_streak, test_low_proactivity_disables_care, test_care_respects_seven_day_interval, FakeDelivery |
| [test_care_delivery.py](<E:/PythonCode/EasyChat/tests/profiles/test_care_delivery.py>) | 验证 care_delivery 相关行为与回归（测试文件名推断） | C3 关怀投递：只有实际发送成功才写 last_care_at / mood_care_log。 / 符号 FakeChannels, _care_key, _setup, _enqueue_care, _care_logs, test_failed_delivery_does_not_mark_care_and_failed_dedup_is_not_success, test_delete_mood_cancels_pending_care_and_blocks_late_callback |
| [test_mood_finish.py](<E:/PythonCode/EasyChat/tests/profiles/test_mood_finish.py>) | 验证 mood_finish 相关行为与回归（测试文件名推断） | run 终态 → 情绪采样入队：只 completed、日期用完成时间。 / 符号 _profile, _insert_user_message, _fire, _jobs, test_non_completed_run_does_not_enqueue_mood, test_mood_date_uses_finished_at_local_date, test_completed_run_with_empty_text_is_not_enqueued |
| [test_mood_model.py](<E:/PythonCode/EasyChat/tests/profiles/test_mood_model.py>) | 验证 mood_model 相关行为与回归（测试文件名推断） | 情绪采样的受控模型路径：严格 JSON 校验，失败跳过而不是猜。 / 符号 FakeGenerator, _service, test_model_json_is_validated_and_recorded, test_model_can_wrap_json_in_markdown_fence, test_model_evidence_must_be_original_substring, test_model_rejects_unknown_labels_and_bad_score, test_model_empty_output_skips_day |
| [test_mood_retention.py](<E:/PythonCode/EasyChat/tests/profiles/test_mood_retention.py>) | 验证 mood_retention 相关行为与回归（测试文件名推断） | 情绪保留期：care 日志随 mood_retention_days 回收，删除立即清空。 / 符号 _setup, _care_rows, test_expired_care_log_is_purged_after_retention_even_if_mood_disabled, test_delete_mood_clears_care_logs_immediately |
| [test_mood_sampling.py](<E:/PythonCode/EasyChat/tests/profiles/test_mood_sampling.py>) | 验证 mood_sampling 相关行为与回归（测试文件名推断） | 情绪采样：显式 opt-in、确定性词表、同日多采样平均、run 幂等。 / 符号 _setup, _msg, test_opt_out_never_samples, test_explicit_negative_and_positive_merge_same_day, test_same_run_is_idempotent, test_opt_out_purges_stored_mood_text_from_jobs, test_same_run_is_not_sampled_twice |
| [test_profiles.py](<E:/PythonCode/EasyChat/tests/profiles/test_profiles.py>) | 验证 profiles 相关行为与回归（测试文件名推断） | profiles：默认值、人格渲染、安静时段、情绪平均与删除。 / 符号 _service, test_default_profile_is_warm_and_mood_off, test_render_wechat_has_length_but_web_does_not, test_custom_instruction_limit_and_bad_preset, test_quiet_hours_cross_midnight_and_end_epoch, test_mood_off_writes_nothing, test_same_day_samples_use_arithmetic_av |

### tests/resources/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/resources/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | resources 资源测量测试包。 |
| [test_resource_sample.py](<E:/PythonCode/EasyChat/tests/resources/test_resource_sample.py>) | 验证 resource_sample 相关行为与回归（测试文件名推断） | 资源测量（Task 16，marker=resources，默认排除）。 / 符号 _free_port, test_main_process_rss_under_target |

### tests/scheduling/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/scheduling/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | 按目录和文件类型定位 |
| [test_weekly_briefing.py](<E:/PythonCode/EasyChat/tests/scheduling/test_weekly_briefing.py>) | 验证 weekly_briefing 相关行为与回归（测试文件名推断） | scheduling weekly / briefing：时区日历、任务入队、重复 tick 幂等。 / 符号 _service, _epoch, test_next_weekly_uses_calendar_and_timezone, test_upcoming_can_filter_content_kind, test_ai_news_can_be_created_as_daily_briefing, test_create_weekly_requires_weekday, test_cancelled_schedule_does_not_block_recreate |

### tests/security/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/security/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | 按目录和文件类型定位 |
| [test_audit_fixes.py](<E:/PythonCode/EasyChat/tests/security/test_audit_fixes.py>) | 验证 audit_fixes 相关行为与回归（测试文件名推断） | 安全审计修复回归（audit run-1，findings #1-#10）。 / 符号 _access_service, _seeded_service, jwt_for_probe, test_jwt_placeholder_secret_refused_at_construction, test_deployment_secret_entropy_floor, test_weak_secret_still_allowed_explicitly, test_sse_ticket_single_use_and_expiry |

### tests/services/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [test_speech.py](<E:/PythonCode/EasyChat/tests/services/test_speech.py>) | 验证 speech 相关行为与回归（测试文件名推断） | 语音：SILK/大小降级、云端协议、本地不可用、渠道转写接入。 / 符号 _settings, test_cloud_stt_posts_audio_and_parses_text, test_silk_fails_without_decoder, test_oversize_rejected_before_network, test_auto_falls_back_to_second_provider, test_build_stt_off_returns_none, test_build_stt_default_voice_disabled_does_not_touch_models |

### tests/skills/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/skills/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | skills 模块测试包（Task 10）。 |
| [helpers.py](<E:/PythonCode/EasyChat/tests/skills/helpers.py>) | 自动化测试、fixture和临时SQLite测试支撑中的helpers 实现（目录与文件名推断） | skills 测试辅助：真实临时 SQLite + 独立临时内容根目录（不写仓库 data/）。 / 符号 make_skill_rig, new_service, make_user, version_file |
| [test_hermes_bridge.py](<E:/PythonCode/EasyChat/tests/skills/test_hermes_bridge.py>) | 验证 hermes_bridge 相关行为与回归（测试文件名推断） | Hermes Skills 桥接：只用 skills 公开接口、仅 owner 快照、无 backend.hermes 导入。 / 符号 env, _seed, test_bridge_only_returns_owner_snapshots, test_bridge_propose_and_activate_flow, test_bridge_fails_explicitly_when_active_file_missing, test_bridge_imports_only_public_skills_api |
| [test_versions.py](<E:/PythonCode/EasyChat/tests/skills/test_versions.py>) | 验证 versions 相关行为与回归（测试文件名推断） | 个人技能不可变版本、激活/回滚、pin/权限与重启恢复测试（Task 10）。 / 符号 env, _propose_and_activate, test_version_files_are_immutable_and_activation_is_explicit, test_stale_expected_pointer_conflict_does_not_overwrite, test_rollback_restores_old_content, test_path_traversal_names_rejected, test_content_path_is_derived_from_ids |

### tests/storage/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/storage/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | 按目录和文件类型定位 |
| [test_backup.py](<E:/PythonCode/EasyChat/tests/storage/test_backup.py>) | 验证 backup 相关行为与回归（测试文件名推断） | F11：文件 + SQLite 备份/校验/恢复（真实临时目录，无外部依赖）。 / 符号 _ready, test_backup_copies_db_and_files_with_manifest, test_backup_refuses_missing_referenced_file, test_verify_detects_tampering, test_restore_rebuilds_working_copy, test_restore_preserves_existing_database, test_backup_rejects_non_empty_destination |
| [test_jobs.py](<E:/PythonCode/EasyChat/tests/storage/test_jobs.py>) | 验证 jobs 相关行为与回归（测试文件名推断） | jobs 认领/lease/幂等/重试行为测试。时间用注入clock固定，不sleep。 / 符号 FakeClock, queue, _payload, test_enqueue_dedup_same_key_returns_same_job, test_two_claimers_each_get_distinct_jobs_once, test_claim_empty_queue_returns_none, test_complete_transitions_to_succeeded |
| [test_migration_0014.py](<E:/PythonCode/EasyChat/tests/storage/test_migration_0014.py>) | 验证 migration_0014 相关行为与回归（测试文件名推断） | 0014+ 增量迁移：空库、0013 升级、字段/索引存在、旧 checksum 不变。 / 符号 _columns, _checksums, test_fresh_database_reaches_0014_with_new_schema, test_0013_database_upgrades_without_rewriting_old_checksums, test_partial_url_unique_index_allows_multiple_empty_urls, test_old_migration_files_unchanged_checksums |
| [test_migrations.py](<E:/PythonCode/EasyChat/tests/storage/test_migrations.py>) | 验证 migrations 相关行为与回归（测试文件名推断） | 迁移行为测试：幂等、checksum、失败回滚、外键完整性。 / 符号 _db, _make_migration_dir, test_migrate_twice_idempotent_seed_not_duplicated, test_all_core_tables_present, test_run_unique_including_empty_channel_scope, test_checksum_mismatch_fails, test_failed_migration_rolls_back_and_not_ready |
| [test_sqlite.py](<E:/PythonCode/EasyChat/tests/storage/test_sqlite.py>) | 验证 sqlite 相关行为与回归（测试文件名推断） | platform.sqlite 行为测试：真实临时SQLite，不mock SQL逻辑。 / 符号 test_connect_fresh_per_call_with_pragmas, test_journal_mode_follows_wal_safety_rule, test_wal_safe_version_boundaries, test_foreign_keys_enforced, test_transaction_commit_and_rollback, test_transaction_closes_connection, test_two_worker_threads_write |

### tests/superagent/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/superagent/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | 按目录和文件类型定位 |
| [fakes.py](<E:/PythonCode/EasyChat/tests/superagent/fakes.py>) | 自动化测试、fixture和临时SQLite测试支撑中的fakes 实现（目录与文件名推断） | superagent 测试共享桩：FakeGit / FakeRunner / FakePRClient / FakeCanceller。 / 符号 FakeGit, FakeRunner, CancelMidRunRunner, FakePRClient, FakeCanceller, make_outcome |
| [test_acceptance.py](<E:/PythonCode/EasyChat/tests/superagent/test_acceptance.py>) | 验证 acceptance 相关行为与回归（测试文件名推断） | 工作包四后端回归：验收轮次、覆盖门、打回返工闭环与访问控制。 / 符号 _env, _succeeded_task, test_round_coverage_gate_and_verdict, test_reject_reworks_original_task_and_keeps_history, test_accept_access_control, test_task_brief_aggregates_ledger_facts |
| [test_credentials.py](<E:/PythonCode/EasyChat/tests/superagent/test_credentials.py>) | 验证 credentials 相关行为与回归（测试文件名推断） | T2 凭证与仓库解析回归：严格 parser、脱敏出口、credential helper 无泄漏。 / 符号 test_parse_repo_url_accepts_normalized_https, test_parse_repo_url_rejects_unsafe_forms, test_sanitize_text_strips_userinfo_tokens_and_auth_headers, test_credential_helper_source_contains_no_token_and_responds_by_host, test_git_auth_args_never_c |
| [test_git_process_tree.py](<E:/PythonCode/EasyChat/tests/superagent/test_git_process_tree.py>) | 验证 git_process_tree 相关行为与回归（测试文件名推断） | P4 回归：git 进程树回收原语的真实行为 + 超时路径（集成）。 / 符号 test_terminate_tree_stops_process_and_blocks_late_side_effect, test_run_git_timeout_raises_after_terminating |
| [test_superagent_service.py](<E:/PythonCode/EasyChat/tests/superagent/test_superagent_service.py>) | 验证 superagent_service 相关行为与回归（测试文件名推断） | superagent 服务与 worker 回归（T1–T4）。 / 符号 _rig_with_worker, _wire, test_create_task_snapshots_repo_and_is_idempotent, test_settings_change_after_creation_does_not_affect_accepted_task, test_claim_creates_attempt_and_late_result_is_rejected, test_permission_revoked_blocks_execution, test_legacy_task_with |
| [test_verification.py](<E:/PythonCode/EasyChat/tests/superagent/test_verification.py>) | 验证 verification 相关行为与回归（测试文件名推断） | T3/T4 验证门禁与进程限时回归（真实子进程，离线快速）。 / 符号 test_load_verify_commands_parses_and_validates, test_verification_passes_and_writes_artifacts, test_verification_failure_stops_on_required, test_verification_timeout_kills_process, test_run_git_missing_binary_raises |
| [test_webhooks.py](<E:/PythonCode/EasyChat/tests/superagent/test_webhooks.py>) | 验证 webhooks 相关行为与回归（测试文件名推断） | T7 GitHub webhook 回归：验签、去重、allowlist、任务关联、乱序与机器人防护。 / 符号 _sign, _admin, _user, _env, _pr_payload, _ingest, test_signature_verification |
| [test_workspaces.py](<E:/PythonCode/EasyChat/tests/superagent/test_workspaces.py>) | 验证 workspaces 相关行为与回归（测试文件名推断） | T3 工作区隔离回归：路径由服务生成、包含 host/repo/task、拒绝逃逸。 / 符号 test_workspace_key_is_hosted_per_repo_and_task, test_workspace_key_rejects_bad_task_id, test_workspace_path_resolves_inside_root, test_workspace_path_rejects_escape |

### tests/support/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/support/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | 按目录和文件类型定位 |
| [delivery.py](<E:/PythonCode/EasyChat/tests/support/delivery.py>) | 自动化测试、fixture和临时SQLite测试支撑中的delivery 实现（目录与文件名推断） | 投递/提醒测试替身：FakeSender 脚本化返回 sent/retry/uncertain/failed。 / 符号 FakeSender |
| [ledger_fixtures.py](<E:/PythonCode/EasyChat/tests/support/ledger_fixtures.py>) | 自动化测试、fixture和临时SQLite测试支撑中的ledger_fixtures 实现（目录与文件名推断） | 人工合成账单/截图夹具生成器（F0）。 / 符号 BillRow, SyntheticBill, _to_minor, standard_scenario, full_refund_scenario, same_id_refund_scenario, overlap_export_scenario |
| [rig.py](<E:/PythonCode/EasyChat/tests/support/rig.py>) | 自动化测试、fixture和临时SQLite测试支撑中的rig 实现（目录与文件名推断） | 公共测试设施（实施计划：公共测试设施与命令约定）。 / 符号 FakeClock, FakeRuntime, TestRig, make_rig |
| [wechat.py](<E:/PythonCode/EasyChat/tests/support/wechat.py>) | 自动化测试、fixture和临时SQLite测试支撑中的wechat 实现（目录与文件名推断） | Task 7 测试替身：FakeTransport/FakeMediaFetcher + 渠道消息构造器。 / 符号 FakeTransport, FakeMediaFetcher, make_channel_rig, text_message, image_message, inbound |

### tests/tools/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [test_ddgs_search_bridge.py](<E:/PythonCode/EasyChat/tests/tools/test_ddgs_search_bridge.py>) | 验证 ddgs_search_bridge 相关行为与回归（测试文件名推断） | DDGS 搜索桥：安装 ddgs 包后必须真正注册为 Hermes Provider。 / 符号 test_ensure_ddgs_provider_registers_hermes_provider, test_bing_html_parser_returns_normalized_results |
| [test_ledger_tools.py](<E:/PythonCode/EasyChat/tests/tools/test_ledger_tools.py>) | 验证 ledger_tools 相关行为与回归（测试文件名推断） | 账本工具：金额格式化、权限、无提交工具、async handler 与 owner 隔离。 / 符号 _tools, test_amount_format_without_model_math, test_no_commit_tool_exposed, test_preview_returns_full_import_id_and_amount_text, test_permission_denied_is_readable, test_async_handler_awaits_and_has_tool_context_in_config_only, test_contextvar_fallb |
| [test_reminder_tools.py](<E:/PythonCode/EasyChat/tests/tools/test_reminder_tools.py>) | 验证 reminder_tools 相关行为与回归（测试文件名推断） | 提醒工具：ToolContext 身份、无绑定拒绝、创建/列表/取消/稍后。 / 符号 _Channels, _Profiles, _setup, _invoke, test_create_uses_context_and_returns_readable_id, test_no_binding_does_not_create_orphan, test_missing_identity_is_rejected |
| [test_superagent_tools.py](<E:/PythonCode/EasyChat/tests/tools/test_superagent_tools.py>) | 验证 superagent_tools 相关行为与回归（测试文件名推断） | T5 superagent 工具：服务端操作键幂等、来源固定回执、身份与权限。 / 符号 _service, _ctx, test_tool_creates_task_with_source_target, test_tool_same_session_same_requirement_is_idempotent, test_tool_rejects_missing_identity_and_web_source_has_no_target, test_tool_gate_error_is_stable_message, test_tool_paraphrase_boundary_and_re |

### tests/usage/

| 文件 | 职责与依据 | 文件头或公开符号 |
|---|---|---|
| [__init__.py](<E:/PythonCode/EasyChat/tests/usage/__init__.py>) | 自动化测试、fixture和临时SQLite测试支撑的包入口或导出（包结构） | 按目录和文件类型定位 |
| [test_calls.py](<E:/PythonCode/EasyChat/tests/usage/test_calls.py>) | 验证 calls 相关行为与回归（测试文件名推断） | 唯一计量入口行为测试（架构 §7 / Task 4 清单）。时间用注入clock固定。 / 符号 usage, _u, test_same_callback_twice_counts_once, test_late_usage_delta_applied_once, test_real_retry_is_two_calls, test_system_task_not_attributed_to_user1, test_shanghai_date_boundary |
| [test_ranking.py](<E:/PythonCode/EasyChat/tests/usage/test_ranking.py>) | 验证 ranking 相关行为与回归（测试文件名推断） | 排行榜行为测试：聚合、来源分布、旧字段兼容、权限。 / 符号 env, _u, test_ranking_order_and_legacy_fields, test_ranking_days_window, test_ranking_exposes_input_output_and_legacy_aliases, test_ranking_requires_trace_view, test_ranking_shows_trace_manage_holder_all |
