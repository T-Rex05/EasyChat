# EasyChat 当前源码定位与兼容基线

日期：2026-11-03。只做静态读取，不执行应用或连接旧数据库。行号仅用于导航，执行前以函数名重新定位。本文描述复制基线，不代表已完成目标改造。

## 关键文件

| 文件 | 行数 | 顶层类/函数（部分） |
|---|---:|---|
| `main.py` | 862 | `create_app:56`, `start_server:802` |
| `backend/controller/__init__.py` | 79 | `discover_routers:17`, `register_all_routers:56` |
| `backend/hermes_adapter.py` | 2639 | `_update_hermes_reasoning_effort:69`, `_seed_default_skills:99`, `_seed_default_config:133`, `_compute_user_skill_scope:194`, `_make_project_tool_handler:280`, `_ensure_ddgs_web_search:374`, `_register_project_tools:398`, `_patch_dispatch_for_trace:496`, `_install_delegation_enricher:548`, `_delegation_followup_enabled:578` |
| `backend/controller/chat/stream.py` | 796 | `_fetch_username_sync:39`, `_load_conversations_sync:53`, `_insert_running_conversation_sync:60`, `_persist_conversation_answer_sync:67`, `_flush_audit_sync:74`, `_stream_text_chunks:101`, `token_stream_events:125` |
| `backend/controller/chat/persistence.py` | 83 | `set_conversation_mapper:11`, `_insert_running_conversation:17`, `_persist_conversation_answer:40`, `_mark_conversation_failed:66`, `_mark_conversation_cancelled:76` |
| `backend/controller/wechat/hermes.py` | 135 | `run_wechat_hermes:24`, `persist_wechat_conversation:107` |
| `backend/controller/platform_config_controller.py` | 465 | `_get_conn:29`, `PlatformConfigSave:34`, `_sync_http_get_json:50`, `_http_get_json:65`, `_generate_qr_image:69`, `_background_qr_poll:82`, `get_platform_config:189`, `save_platform_config:218`, `SmtpTestRequest:236`, `test_smtp_connection:246` |
| `backend/controller/user_binding_controller.py` | 116 | `_get_conn:19`, `BindingCreate:24`, `list_bindings:31`, `create_binding:46`, `delete_binding:82` |
| `backend/permission/checker.py` | 260 | `_get_role_permissions_lru:26`, `_get_user_overrides_lru:32`, `_fetch_role_permissions:37`, `_fetch_user_overrides:53`, `_get_role_permissions:68`, `_get_user_overrides:89`, `_invalidate_permission_cache:112`, `get_user_role:140`, `get_user_permissions:166`, `has_permission:189` |
| `backend/permission/registry.py` | 294 | `PermissionDef:14`, `register_perm:27`, `seed_to_db:46`, `get_all_permissions:251`, `get_permission_tree:263` |
| `backend/service/auth/permission_service.py` | 242 | `get_all_permissions:47`, `list_roles:54`, `create_role:76`, `update_role:116`, `delete_role:163`, `set_user_role:189`, `set_user_permission:211`, `get_user_perm_overrides:232` |
| `backend/service/run_registry.py` | 219 | `ThreadBusyError:23`, `Run:29`, `RunRegistry:43` |
| `backend/service/trace/write.py` | 227 | `_conn:14`, `_get_session_source:19`, `record_trace:42`, `update_trace:83`, `mark_trace_error:149`, `sync_trace_texts:166`, `record_span:201` |
| `backend/service/trace/stats.py` | 373 | `_conn:18`, `get_dashboard_stats:23`, `_trace_filters:111`, `_get_daily_trend:129`, `_get_model_usage:159`, `_get_source_distribution:181`, `_get_tool_usage:202`, `get_user_ranking:243`, `cleanup_old_traces:281`, `get_ranking:321` |
| `backend/utils/llm_usage.py` | 68 | `current_trace_context:8`, `trace_context:14`, `note_api_request:22`, `_mapping:28`, `trace_usage:36` |
| `backend/service/cron/cron_service.py` | 448 | `CronService:55` |
| `backend/service/cron/delivery.py` | 403 | `CronDelivery:25` |
| `backend/service/skill_service.py` | 871 | `can_access_skill:37`, `list_skills:53`, `get_skill:121`, `create_skill:202`, `update_skill:257`, `delete_skill:313`, `_query_pool_available:374`, `_get_user_pool_records:404`, `_query_pool_installed_skills:424`, `publish_to_pool:452` |
| `backend/hermes/agent/background_review.py` | 1002 | `_resolve_review_runtime:46`, `_msg_text:113`, `_digest_history:122`, `summarize_background_review_actions:391`, `build_memory_write_metadata:608`, `_run_review_in_thread:635`, `spawn_background_review_thread:967` |
| `backend/hermes/agent/curator.py` | 2019 | `_strip_aux_credential:40`, `_ReviewRuntimeBinding:47`, `_merge_request_overrides:57`, `_state_file:85`, `_default_state:89`, `load_state:101`, `save_state:116`, `set_paused:124`, `is_paused:130`, `_load_config:138` |
| `backend/hermes/tools/skill_manager_tool.py` | 1455 | `_guard_agent_created_enabled:63`, `_security_scan_skill:82`, `_skills_dir:117`, `_containing_skills_root:135`, `_is_path_redirect:157`, `_validate_delete_target:170`, `_pinned_guard:231`, `_validate_name:272`, `_validate_category:286`, `_validate_frontmatter:311` |
| `backend/hermes/tools/skill_usage.py` | 1119 | `is_protected_builtin:71`, `_skills_dir:81`, `_usage_file:85`, `_usage_file_lock:90`, `_archive_dir:125`, `_now_iso:129`, `_parse_iso_timestamp:133`, `latest_activity_at:146`, `activity_count:166`, `_read_bundled_manifest_names:181` |
| `backend/hermes/tools/mcp_tool.py` | 6678 | `_get_mcp_stderr_log:148`, `_write_stderr_log_header:183`, `_check_message_handler_support:277`, `_check_logging_callback_support:296`, `_jittered:348`, `_env_ref_name:422`, `_build_safe_env:439`, `_sanitize_error:472`, `_exc_str:481`, `_is_method_not_found_error:503` |
| `backend/context/task_state.py` | 784 | `TaskStateMaintainer:172`, `get_task_state_maintainer:769` |
| `backend/context/task_evidence.py` | 145 | `_encode:11`, `EvidenceLedger:15`, `_Transaction:133` |
| `backend/context/tool_results/tools.py` | 81 | `_encode:11`, `_compact_search_structure:15`, `_bounded_call:27`, `context_read:52`, `context_search:67` |

## 保留入口的静态路由清单

完整装配仍需在新工厂中导出OpenAPI并核验。装饰器、路径前缀及鉴权依赖分别记录，不靠猜测拼接动态路由。

| 文件 | 路由装饰器 | 处理函数 |
|---|---|---|
| `backend/controller/auth_controller.py` | `router.post('/register')` | `register:42` |
| `backend/controller/auth_controller.py` | `router.post('/login')` | `login:55` |
| `backend/controller/auth_controller.py` | `router.get('/me')` | `get_me:69` |
| `backend/controller/auth_controller.py` | `router.post('/refresh')` | `refresh_token:82` |
| `backend/controller/auth_controller.py` | `router.get('/users')` | `list_users:123` |
| `backend/controller/admin_controller.py` | `router.get('/users')` | `list_users:59` |
| `backend/controller/admin_controller.py` | `router.put('/users/{user_id}/role')` | `update_user_role:75` |
| `backend/controller/admin_controller.py` | `router.get('/users/{user_id}/perms')` | `get_user_perms:92` |
| `backend/controller/admin_controller.py` | `router.put('/users/{user_id}/perms')` | `update_user_perms:109` |
| `backend/controller/admin_controller.py` | `router.put('/users/{user_id}/status')` | `update_user_status:128` |
| `backend/controller/admin_controller.py` | `router.get('/permissions')` | `list_all_permissions:150` |
| `backend/controller/admin_controller.py` | `router.get('/toolsets')` | `list_toolset_definitions:157` |
| `backend/controller/admin_controller.py` | `router.get('/roles')` | `list_roles_handler:182` |
| `backend/controller/admin_controller.py` | `router.post('/roles')` | `create_role_handler:189` |
| `backend/controller/admin_controller.py` | `router.put('/roles/{role_id}')` | `update_role_handler:199` |
| `backend/controller/admin_controller.py` | `router.delete('/roles/{role_id}')` | `delete_role_handler:217` |
| `backend/controller/admin_controller.py` | `router.get('/pool/pending')` | `list_pending_items:265` |
| `backend/controller/admin_controller.py` | `router.post('/pool/{pool_id}/approve')` | `approve_pool_item:285` |
| `backend/controller/admin_controller.py` | `router.post('/pool/{pool_id}/reject')` | `reject_pool_item:314` |
| `backend/controller/admin_controller.py` | `router.post('/pool/force-publish')` | `force_publish:339` |
| `backend/controller/admin_controller.py` | `router.delete('/pool/{pool_name}')` | `remove_from_pool:357` |
| `backend/controller/chat_controller.py` | `app.get('/chat/stream')` | `stream_chat:200` |
| `backend/controller/chat_controller.py` | `app.post('/chat/stream')` | `stream_chat_post:280` |
| `backend/controller/chat_controller.py` | `app.post('/api/chat/upload-images')` | `upload_chat_images:355` |
| `backend/controller/chat_controller.py` | `app.post('/api/chat/upload-files')` | `upload_chat_files:387` |
| `backend/controller/chat_controller.py` | `app.get('/chat/cancel')` | `cancel_chat:431` |
| `backend/controller/chat_controller.py` | `app.post('/chat/cancel')` | `cancel_chat:431` |
| `backend/controller/chat_controller.py` | `app.get('/api/history')` | `get_chat_history_list:486` |
| `backend/controller/chat_controller.py` | `app.put('/api/history/{chat_id}')` | `rename_chat_session:563` |
| `backend/controller/chat_controller.py` | `app.delete('/api/history/{chat_id}')` | `delete_chat_session:604` |
| `backend/controller/chat_controller.py` | `app.get('/api/history/{chat_id}')` | `get_chat_messages:638` |
| `backend/controller/chat_controller.py` | `app.get('/api/todos')` | `get_thread_todos:716` |
| `backend/controller/chat_controller.py` | `app.post('/api/chat/feedback')` | `chat_feedback:730` |
| `backend/controller/chat_controller.py` | `app.get('/chat/exec-approval/pending')` | `get_pending_exec_approval:763` |
| `backend/controller/chat_controller.py` | `app.post('/chat/exec-approval')` | `resolve_exec_approval:775` |
| `backend/controller/chat_controller.py` | `app.get('/favicon.ico', include_in_schema=False)` | `favicon:799` |
| `backend/controller/platform_config_controller.py` | `router.get('/{platform}')` | `get_platform_config:189` |
| `backend/controller/platform_config_controller.py` | `router.put('/{platform}')` | `save_platform_config:218` |
| `backend/controller/platform_config_controller.py` | `router.post('/email/test')` | `test_smtp_connection:246` |
| `backend/controller/platform_config_controller.py` | `router.get('/{platform}/bindings')` | `get_platform_bindings:305` |
| `backend/controller/platform_config_controller.py` | `router.post('/wechat/qr/start')` | `start_wechat_qr:329` |
| `backend/controller/platform_config_controller.py` | `router.get('/wechat/qr/{session_id}/status')` | `check_wechat_qr_status:376` |
| `backend/controller/platform_config_controller.py` | `router.post('/wechat/qr/{session_id}/bind')` | `bind_after_qr:394` |
| `backend/controller/user_binding_controller.py` | `router.get('')` | `list_bindings:31` |
| `backend/controller/user_binding_controller.py` | `router.post('')` | `create_binding:46` |
| `backend/controller/user_binding_controller.py` | `router.delete('/{binding_id}')` | `delete_binding:82` |
| `backend/controller/skill_controller.py` | `router.put('/{name}/toggle')` | `toggle_skill:20` |
| `backend/controller/skill_controller.py` | `router.get('')` | `list_skills:93` |
| `backend/controller/skill_controller.py` | `router.get('/categories')` | `list_categories:103` |
| `backend/controller/skill_controller.py` | `router.post('/categories', status_code=201)` | `create_category:112` |
| `backend/controller/skill_controller.py` | `router.put('/categories/{name}/rename')` | `rename_category:125` |
| `backend/controller/skill_controller.py` | `router.delete('/categories/{name}')` | `delete_category:140` |
| `backend/controller/skill_controller.py` | `router.get('/my-categories')` | `list_my_categories:165` |
| `backend/controller/skill_controller.py` | `router.post('/my-categories', status_code=201)` | `create_my_category:175` |
| `backend/controller/skill_controller.py` | `router.put('/my-categories/{name}/rename')` | `rename_my_category:189` |
| `backend/controller/skill_controller.py` | `router.delete('/my-categories/{name}')` | `delete_my_category:203` |
| `backend/controller/skill_controller.py` | `router.put('/{name}/category')` | `set_skill_category:215` |
| `backend/controller/skill_controller.py` | `router.get('/pool')` | `list_pool:232` |
| `backend/controller/skill_controller.py` | `router.post('/pool/{name}/install')` | `install_from_pool:243` |
| `backend/controller/skill_controller.py` | `router.delete('/pool/{name}/install')` | `uninstall_from_pool:258` |
| `backend/controller/skill_controller.py` | `router.put('/{name}/lock')` | `lock_skill:275` |
| `backend/controller/skill_controller.py` | `router.put('/{name}/unlock')` | `unlock_skill:292` |
| `backend/controller/skill_controller.py` | `router.post('/{name}/publish')` | `publish_skill:309` |
| `backend/controller/skill_controller.py` | `router.get('/{name}', response_model=SkillDetail)` | `get_skill:326` |
| `backend/controller/skill_controller.py` | `router.get('/{name}/files/{file_path:path}')` | `get_skill_file:339` |
| `backend/controller/skill_controller.py` | `router.post('', status_code=201)` | `create_skill:355` |
| `backend/controller/skill_controller.py` | `router.put('/{name}')` | `update_skill:374` |
| `backend/controller/skill_controller.py` | `router.delete('/{name}')` | `delete_skill:392` |
| `backend/controller/skill_controller.py` | `router.put('/{name}/files/{file_path:path}')` | `write_skill_file:407` |
| `backend/controller/skill_controller.py` | `router.delete('/{name}/files/{file_path:path}')` | `delete_skill_file:423` |
| `backend/controller/skill_controller.py` | `router.post('/{name}/files/upload')` | `upload_skill_files:439` |
| `backend/controller/skill_controller.py` | `router.get('/{name}/files/{file_path:path}/raw')` | `download_skill_file_raw:483` |
| `backend/controller/skill_controller.py` | `router.post('/{name}/files/mkdir')` | `create_skill_subdir:501` |
| `backend/controller/trace_controller.py` | `router.get('/dashboard')` | `dashboard:49` |
| `backend/controller/trace_controller.py` | `router.get('')` | `list_traces:66` |
| `backend/controller/trace_controller.py` | `router.get('/all')` | `list_all_traces:95` |
| `backend/controller/trace_controller.py` | `router.get('/ranking')` | `ranking:164` |
| `backend/controller/trace_controller.py` | `router.get('/users/search')` | `search_users:187` |
| `backend/controller/trace_controller.py` | `router.get('/turns/{session_id}')` | `turn_detail:213` |
| `backend/controller/trace_controller.py` | `router.get('/{trace_id}')` | `trace_detail:346` |
| `backend/controller/trace_controller.py` | `router.get('/config/me')` | `get_config:367` |
| `backend/controller/trace_controller.py` | `router.put('/config')` | `update_config:384` |
| `backend/controller/cron_controller.py` | `router.get('/delivery-options', response_model=dict)` | `get_delivery_options:101` |
| `backend/controller/cron_controller.py` | `router.get('', response_model=dict)` | `list_cron_jobs:191` |
| `backend/controller/cron_controller.py` | `router.post('', response_model=dict)` | `create_cron_job:227` |
| `backend/controller/cron_controller.py` | `router.put('/{job_id}', response_model=dict)` | `update_cron_job:269` |
| `backend/controller/cron_controller.py` | `router.delete('/{job_id}', response_model=dict)` | `delete_cron_job:326` |
| `backend/controller/cron_controller.py` | `router.put('/{job_id}/toggle', response_model=dict)` | `toggle_cron_job:354` |
| `backend/controller/cron_controller.py` | `router.post('/{job_id}/run-now', response_model=dict)` | `run_cron_job_now:392` |
| `backend/controller/cron_controller.py` | `router.get('/{job_id}/executions', response_model=dict)` | `list_executions:423` |
| `backend/controller/cron_controller.py` | `router.get('/events/{user_id}', include_in_schema=False)` | `cron_events:449` |
| `backend/controller/email_config_controller.py` | `router.get('')` | `list_email_configs:41` |
| `backend/controller/email_config_controller.py` | `router.post('')` | `create_email_config:58` |
| `backend/controller/email_config_controller.py` | `router.put('/{config_id}')` | `update_email_config:87` |
| `backend/controller/email_config_controller.py` | `router.put('/{config_id}/active')` | `set_active_email_config:119` |
| `backend/controller/email_config_controller.py` | `router.delete('/{config_id}')` | `delete_email_config:136` |
| `backend/controller/email_config_controller.py` | `router.post('/{config_id}/test')` | `test_email_config:148` |
| `backend/controller/personal_email_controller.py` | `router.get('')` | `list_personal_emails:20` |
| `backend/controller/personal_email_controller.py` | `router.post('')` | `add_personal_email:34` |
| `backend/controller/personal_email_controller.py` | `router.put('/{email_id}/active')` | `set_active_personal_email:61` |
| `backend/controller/personal_email_controller.py` | `router.delete('/{email_id}')` | `delete_personal_email:75` |
| `backend/controller/model_config_controller.py` | `router.get('')` | `list_model_configs:65` |
| `backend/controller/model_config_controller.py` | `router.post('')` | `create_model_config:95` |
| `backend/controller/model_config_controller.py` | `router.put('/{config_id}/active')` | `set_active:150` |
| `backend/controller/model_config_controller.py` | `router.delete('/{config_id}')` | `delete_config:187` |
| `backend/controller/model_config_controller.py` | `router.put('/{config_id}/multimodal')` | `toggle_multimodal:215` |
| `backend/controller/model_config_controller.py` | `router.post('/redetect-multimodal')` | `redetect_all_multimodal:242` |
| `backend/controller/model_config_controller.py` | `router.put('/reasoning-effort')` | `update_reasoning_effort:272` |
| `backend/controller/model_config_controller.py` | `router.put('/{config_id}')` | `update_config:301` |
| `backend/controller/model_config_controller.py` | `router.post('/{config_id}/test')` | `test_connection:389` |
| `backend/controller/model_config_controller.py` | `_route_router.get('/fallback-chain')` | `get_fallback_chain:763` |
| `backend/controller/model_config_controller.py` | `_route_router.put('/fallback-chain')` | `save_fallback_chain:771` |
| `backend/controller/model_config_controller.py` | `_route_router.get('/scene-routing')` | `get_scene_routing:803` |
| `backend/controller/model_config_controller.py` | `_route_router.put('/scene-routing')` | `save_scene_routing:829` |
| `backend/controller/model_config_controller.py` | `_route_router.post('/evaluate')` | `evaluate_route:862` |
| `backend/controller/model_config_controller.py` | `_route_router.get('/scenes')` | `list_scenes:874` |
| `backend/controller/config_controller.py` | `router.get('')` | `get_config:25` |
| `backend/controller/config_controller.py` | `router.post('')` | `save_config:48` |
| `backend/controller/memory_items_controller.py` | `router.get('', response_model=List[MemoryItemResponse])` | `list_memories:164` |
| `backend/controller/memory_items_controller.py` | `router.get('/stats', response_model=MemoryStatsResponse)` | `get_memory_stats:189` |
| `backend/controller/memory_items_controller.py` | `router.get('/episodic', response_model=List[EpisodicMemoryResponse])` | `list_episodic_memories:201` |
| `backend/controller/memory_items_controller.py` | `router.get('/semantic', response_model=List[SemanticMemoryResponse])` | `list_semantic_memories:228` |
| `backend/controller/memory_items_controller.py` | `router.get('/episodic/stats')` | `get_episodic_stats:253` |
| `backend/controller/memory_items_controller.py` | `router.get('/semantic/stats')` | `get_semantic_stats:262` |
| `backend/controller/memory_items_controller.py` | `router.get('/dashboard')` | `get_memory_dashboard:273` |
| `backend/controller/memory_items_controller.py` | `router.get('/{memory_id}', response_model=MemoryItemResponse)` | `get_memory:291` |
| `backend/controller/memory_items_controller.py` | `router.post('', response_model=MemoryItemResponse, status_code=201)` | `create_memory:307` |
| `backend/controller/memory_items_controller.py` | `router.put('/{memory_id}', response_model=MemoryItemResponse)` | `update_memory:343` |
| `backend/controller/memory_items_controller.py` | `router.delete('/{memory_id}')` | `delete_memory:383` |
| `backend/controller/memory_items_controller.py` | `router.post('/search')` | `search_memories:409` |
| `backend/controller/memory_items_controller.py` | `router.get('/{memory_id}/graph')` | `get_memory_graph:446` |
| `backend/controller/memory_items_controller.py` | `router.get('/{memory_id}/versions', response_model=VersionHistoryResponse)` | `get_memory_versions:514` |
| `backend/controller/memory_items_controller.py` | `router.get('/{memory_id}/versions/{version}', response_model=MemoryVersionResponse)` | `get_memory_version:555` |
| `backend/controller/memory_items_controller.py` | `router.post('/{memory_id}/restore/{version}', response_model=MemoryItemResponse)` | `restore_memory_version:583` |
| `backend/controller/memory_items_controller.py` | `router.post('/consolidate')` | `trigger_consolidation:650` |
| `backend/controller/memory_items_controller.py` | `router.post('/episodic/{memory_id}/promote', response_model=SemanticMemoryResponse)` | `promote_episodic_to_semantic:749` |
| `backend/controller/memory_items_controller.py` | `router.get('/outbox/list')` | `list_outbox_events:817` |
| `backend/controller/memory_items_controller.py` | `router.post('/outbox/retry')` | `retry_outbox_events:900` |

## 已核实的高风险迁移点

- 权限优先级：super_admin可用权限全集；普通角色默认权限加用户grant，再减用户revoke；工具集读取角色配置。以checker原实现和测试固定语义，角色改名/删除同样验证。
- 当前controller自动发现会import全部控制器，替换为显式装配，防止移除业务仍被扫描导入。
- get_project_tools在授权过滤之前导入SQL和论文业务，删菜单或禁用toolset不足以减运行依赖。
- 微信调用runtime与Web持久化控制器耦合，两端要归入同一个运行入口。
- 双SQLite库：原始引擎消息在Hermes state.db，应用运行/业务投影在app.db；禁止以跨库事务假设掩盖失败。
- traced_llm与Hermes模型调用并非同一个调用入口；统一用量计量必须覆盖两者，同时防止同一调用被两套observer重复累计。
- run_registry带client_msg_id幂等、thread busy和SSE序列，迁移要保留协议及行为。
- 默认后台审查和Curator已有独立触发及写入路径，不能与新evolution调度器同时重复管理相同资产。
- 项目.gitignore忽略docs、scripts、pyproject.toml；执行者在首次基线提交时选择性修正，不能直接强制加入全部忽略文件。

## 执行前补齐的运行基线

- 记录现有前端API路径/响应字段、SSE事件名和取消/重连行为，生成契约夹具。
- 不启动旧main.py去抓OpenAPI：它会初始化MySQL和其他基础设施。先静态清单，待无副作用app工厂完成后再导出。
- 业务数据库不可达时，通过源码权限种子和临时测试数据建立对照，不读取用户真实.env或运行数据。
- 包版本沿用并核验可复现安装，不把pyproject的宽泛版本当作完整锁文件。
