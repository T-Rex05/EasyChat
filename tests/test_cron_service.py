"""
Cron 定时任务服务测试
"""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock


class TestBuildTrigger:
    """测试 _build_trigger 表达式解析"""

    def test_build_trigger_once(self):
        """测试一次性任务解析"""
        from backend.service.cron.cron_service import CronService

        service = CronService()
        trigger, error = service._build_trigger("once", "2026-08-15 09:00")

        assert trigger is not None
        assert error is None
        assert trigger.__class__.__name__ == "DateTrigger"

    def test_build_trigger_once_with_t(self):
        """测试一次性任务（T 分隔符）"""
        from backend.service.cron.cron_service import CronService

        service = CronService()
        trigger, error = service._build_trigger("once", "2026-08-15T09:00")

        assert trigger is not None
        assert error is None
        assert trigger.__class__.__name__ == "DateTrigger"

    def test_build_trigger_cron(self):
        """测试 cron 表达式解析"""
        from backend.service.cron.cron_service import CronService

        service = CronService()
        # 每天 9:00
        trigger, error = service._build_trigger("cron", "0 9 * * *")

        assert trigger is not None
        assert error is None
        assert trigger.__class__.__name__ == "CronTrigger"

    def test_build_trigger_cron_invalid(self):
        """测试无效 cron 表达式"""
        from backend.service.cron.cron_service import CronService

        service = CronService()
        # 只有 4 个字段，无效
        trigger, error = service._build_trigger("cron", "0 9 * *")

        assert trigger is None

    def test_build_trigger_interval_seconds(self):
        """测试间隔任务（秒）"""
        from backend.service.cron.cron_service import CronService

        service = CronService()
        trigger, error = service._build_trigger("interval", "30s")

        assert trigger is not None
        assert error is None
        assert trigger.__class__.__name__ == "IntervalTrigger"

    def test_build_trigger_interval_minutes(self):
        """测试间隔任务（分钟）"""
        from backend.service.cron.cron_service import CronService

        service = CronService()
        trigger, error = service._build_trigger("interval", "5m")

        assert trigger is not None
        assert error is None
        assert trigger.__class__.__name__ == "IntervalTrigger"

    def test_build_trigger_interval_hours(self):
        """测试间隔任务（小时）"""
        from backend.service.cron.cron_service import CronService

        service = CronService()
        trigger, error = service._build_trigger("interval", "2h")

        assert trigger is not None
        assert error is None
        assert trigger.__class__.__name__ == "IntervalTrigger"

    def test_build_trigger_interval_days(self):
        """测试间隔任务（天）"""
        from backend.service.cron.cron_service import CronService

        service = CronService()
        trigger, error = service._build_trigger("interval", "1d")

        assert trigger is not None
        assert error is None
        assert trigger.__class__.__name__ == "IntervalTrigger"

    def test_build_trigger_interval_invalid(self):
        """测试无效间隔表达式"""
        from backend.service.cron.cron_service import CronService

        service = CronService()
        # 无效格式
        trigger, error = service._build_trigger("interval", "abc")

        assert trigger is None

    def test_build_trigger_daily(self):
        """测试每日任务"""
        from backend.service.cron.cron_service import CronService

        service = CronService()
        trigger, error = service._build_trigger("daily", "09:30")

        assert trigger is not None
        assert error is None
        assert trigger.__class__.__name__ == "CronTrigger"

    def test_build_trigger_daily_invalid(self):
        """测试无效每日表达式"""
        from backend.service.cron.cron_service import CronService

        service = CronService()
        # 缺少分钟
        trigger, error = service._build_trigger("daily", "09")

        assert trigger is None

    def test_build_trigger_unknown_type(self):
        """测试未知调度类型"""
        from backend.service.cron.cron_service import CronService

        service = CronService()
        trigger, error = service._build_trigger("unknown", "value")

        assert trigger is None


class TestCronDataMapper:
    """测试 CronDataMapper 数据访问层"""

    @pytest.fixture
    def mock_db(self):
        """模拟数据库连接"""
        with patch('backend.service.cron.data.get_conn') as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_cursor.fetchone.return_value = None
            mock_conn.return_value.execute.return_value = mock_cursor
            mock_conn.return_value.__enter__ = MagicMock(return_value=mock_conn.return_value)
            mock_conn.return_value.__exit__ = MagicMock(return_value=None)
            yield mock_conn

    def test_list_jobs_empty(self, mock_db):
        """测试空任务列表"""
        from backend.service.cron.cron_service import CronDataMapper
        
        mapper = CronDataMapper()
        jobs = mapper.list_jobs(user_id=1)
        
        assert jobs == []

    def test_list_jobs_with_data(self, mock_db):
        """测试有数据的任务列表"""
        from backend.service.cron.cron_service import CronDataMapper
        
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "任务1", "user_id": 1},
            {"id": 2, "name": "任务2", "user_id": 1},
        ]
        mock_db.return_value.execute.return_value = mock_cursor
        
        mapper = CronDataMapper()
        jobs = mapper.list_jobs(user_id=1)
        
        assert len(jobs) == 2
        assert jobs[0]["name"] == "任务1"

    def test_list_jobs_enabled_only(self, mock_db):
        """测试只获取启用的任务"""
        from backend.service.cron.cron_service import CronDataMapper
        
        mapper = CronDataMapper()
        jobs = mapper.list_jobs(user_id=1, enabled_only=True)
        
        # 验证 SQL 包含 enabled = 1
        call_args = mock_db.return_value.execute.call_args
        assert "enabled = 1" in call_args[0][0]

    def test_get_job_exists(self, mock_db):
        """测试获取存在的任务"""
        from backend.service.cron.cron_service import CronDataMapper
        
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "测试任务", "user_id": 1}
        ]
        mock_db.return_value.execute.return_value = mock_cursor
        
        mapper = CronDataMapper()
        job = mapper.get_job(job_id=1)
        
        assert job is not None
        assert job["name"] == "测试任务"

    def test_get_job_not_exists(self, mock_db):
        """测试获取不存在的任务"""
        from backend.service.cron.cron_service import CronDataMapper
        
        mapper = CronDataMapper()
        job = mapper.get_job(job_id=999)
        
        assert job is None

    def test_create_job(self, mock_db):
        """测试创建任务"""
        from backend.service.cron.cron_service import CronDataMapper
        
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 1
        mock_db.return_value.execute.return_value = mock_cursor
        
        mapper = CronDataMapper()
        job_id = mapper.create_job(
            user_id=1,
            name="新任务",
            prompt="生成报告",
            schedule_type="cron",
            schedule_value="0 9 * * *",
            deliver_to="wechat"
        )
        
        assert job_id == 1
        # 验证 INSERT 语句被调用
        assert mock_db.return_value.execute.called

    def test_update_job(self, mock_db):
        """测试更新任务"""
        from backend.service.cron.cron_service import CronDataMapper
        
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_db.return_value.execute.return_value = mock_cursor
        
        mapper = CronDataMapper()
        result = mapper.update_job(job_id=1, name="更新后的名称")
        
        assert result is True
        # 验证 UPDATE 语句被调用
        call_args = mock_db.return_value.execute.call_args
        assert "UPDATE cron_jobs" in call_args[0][0]

    def test_update_job_invalid_field(self, mock_db):
        """测试更新无效字段"""
        from backend.service.cron.cron_service import CronDataMapper
        
        mapper = CronDataMapper()
        # invalid_field 不在允许列表中
        result = mapper.update_job(job_id=1, invalid_field="value")
        
        assert result is False

    def test_delete_job(self, mock_db):
        """测试删除任务"""
        from backend.service.cron.cron_service import CronDataMapper
        
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_db.return_value.execute.return_value = mock_cursor
        
        mapper = CronDataMapper()
        result = mapper.delete_job(job_id=1)
        
        assert result is True
        # 验证 DELETE 语句被调用
        call_args = mock_db.return_value.execute.call_args
        assert "DELETE FROM cron_jobs" in call_args[0][0]

    def test_create_execution(self, mock_db):
        """测试创建执行记录"""
        from backend.service.cron.cron_service import CronDataMapper
        
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 100
        mock_db.return_value.execute.return_value = mock_cursor
        
        mapper = CronDataMapper()
        exec_id = mapper.create_execution(job_id=1, session_id="test_session")
        
        assert exec_id == 100

    def test_finish_execution_success(self, mock_db):
        """测试完成执行记录（成功）"""
        from backend.service.cron.cron_service import CronDataMapper, STATUS_SUCCESS
        
        mapper = CronDataMapper()
        mapper.finish_execution(
            execution_id=100,
            status=STATUS_SUCCESS,
            result_text="报告内容",
            deliver_status="wechat:ok"
        )
        
        # 验证 UPDATE 语句被调用
        assert mock_db.return_value.execute.called


class TestCronServiceExecution:
    """测试 CronService 任务执行逻辑"""

    @pytest.fixture
    def mock_service(self):
        """创建测试用的 CronService 实例"""
        from backend.service.cron.cron_service import CronService
        # 重置单例
        CronService._instance = None
        CronService._scheduler = None
        service = CronService()
        yield service
        # 清理
        if service._scheduler:
            service._scheduler.shutdown(wait=False)

    def test_execute_job_not_exists(self, mock_service):
        """测试执行不存在的任务"""
        with patch('backend.service.cron.cron_service.CronDataMapper') as MockMapper:
            mock_mapper = MagicMock()
            mock_mapper.get_job.return_value = None
            MockMapper.return_value = mock_mapper
            
            # 不应该抛出异常
            mock_service._execute_job(job_id=999)
            
            # 验证没有创建执行记录
            assert not mock_mapper.create_execution.called

    def test_execute_job_success(self, mock_service):
        """测试任务执行成功"""
        with patch('backend.service.cron.cron_service.CronDataMapper') as MockMapper, \
             patch('backend.hermes_adapter.get_runtime') as mock_get_runtime, \
             patch('backend.controller.agent_controller.get_current_model_config') as mock_config, \
             patch('backend.agents.prompts.get_decision_system_prompt') as mock_prompt, \
             patch('backend.permission.checker.get_user_hermes_tools') as mock_tools:
            
            # 模拟数据
            mock_mapper = MagicMock()
            mock_mapper.get_job.return_value = {
                "id": 1,
                "user_id": 1,
                "name": "测试任务",
                "prompt": "生成报告",
                "deliver_to": "wechat",
                "schedule_type": "cron"
            }
            mock_mapper.create_execution.return_value = 100
            MockMapper.return_value = mock_mapper
            
            # 模拟 LLM 调用
            mock_runtime = MagicMock()
            mock_runtime.run = MagicMock(return_value={
                "final_response": "这是生成的报告内容"
            })
            # 使用 AsyncMock 来模拟异步方法
            import asyncio
            async def mock_run(*args, **kwargs):
                return {"final_response": "这是生成的报告内容"}
            mock_runtime.run = mock_run
            mock_get_runtime.return_value = mock_runtime
            
            mock_config.return_value = {"api_key": "test"}
            mock_prompt.return_value = "系统提示"
            mock_tools.return_value = ["web", "memory"]
            
            # 模拟投递：_deliver_result 的真实契约是 (status, fail_reasons) 二元组
            # （cron_service.py:377 是其唯一 return）。旧 mock 返回裸字符串
            # "wechat:ok" → 解包成 2 个名字时 ValueError → 本用例的断言从未真正跑到。
            with patch.object(mock_service, '_deliver_result', return_value=("sent", [])):
                mock_service._execute_job(job_id=1)
            
            # 验证执行记录被创建
            assert mock_mapper.create_execution.called
            # 验证执行完成被调用
            assert mock_mapper.finish_execution.called

    def test_execute_job_llm_failure(self, mock_service):
        """测试 LLM 调用失败"""
        with patch('backend.service.cron.cron_service.CronDataMapper') as MockMapper, \
             patch('backend.hermes_adapter.get_runtime') as mock_get_runtime, \
             patch('backend.controller.agent_controller.get_current_model_config') as mock_config, \
             patch('backend.agents.prompts.get_decision_system_prompt') as mock_prompt, \
             patch('backend.permission.checker.get_user_hermes_tools') as mock_tools:
            
            # 模拟数据
            mock_mapper = MagicMock()
            mock_mapper.get_job.return_value = {
                "id": 1,
                "user_id": 1,
                "name": "测试任务",
                "prompt": "生成报告",
                "deliver_to": "wechat",
                "schedule_type": "cron"
            }
            mock_mapper.create_execution.return_value = 100
            MockMapper.return_value = mock_mapper
            
            # 模拟 LLM 调用失败
            import asyncio
            async def mock_run(*args, **kwargs):
                raise RuntimeError("LLM 调用失败")
            mock_runtime = MagicMock()
            mock_runtime.run = mock_run
            mock_get_runtime.return_value = mock_runtime
            
            mock_config.return_value = {"api_key": "test"}
            mock_prompt.return_value = "系统提示"
            mock_tools.return_value = ["web", "memory"]
            
            # 不应该抛出异常
            mock_service._execute_job(job_id=1)
            
            # 验证执行记录被标记为失败
            call_args = mock_mapper.finish_execution.call_args
            from backend.service.cron.cron_service import STATUS_FAILED
            assert call_args[0][1] == STATUS_FAILED
            assert "LLM 调用失败" in call_args[0][3]

    def test_execute_job_once_auto_disable(self, mock_service):
        """测试一次性任务执行后自动禁用"""
        with patch('backend.service.cron.cron_service.CronDataMapper') as MockMapper, \
             patch('backend.hermes_adapter.get_runtime') as mock_get_runtime, \
             patch('backend.controller.agent_controller.get_current_model_config') as mock_config, \
             patch('backend.agents.prompts.get_decision_system_prompt') as mock_prompt, \
             patch('backend.permission.checker.get_user_hermes_tools') as mock_tools:
            
            # 模拟一次性任务
            mock_mapper = MagicMock()
            mock_mapper.get_job.return_value = {
                "id": 1,
                "user_id": 1,
                "name": "一次性任务",
                "prompt": "生成报告",
                "deliver_to": "wechat",
                "schedule_type": "once"  # 一次性任务
            }
            mock_mapper.create_execution.return_value = 100
            MockMapper.return_value = mock_mapper
            
            # 模拟 LLM 调用成功
            import asyncio
            async def mock_run(*args, **kwargs):
                return {"final_response": "报告内容"}
            mock_runtime = MagicMock()
            mock_runtime.run = mock_run
            mock_get_runtime.return_value = mock_runtime
            
            mock_config.return_value = {"api_key": "test"}
            mock_prompt.return_value = "系统提示"
            mock_tools.return_value = ["web", "memory"]
            
            # 同上：_deliver_result 必须返回 (status, fail_reasons) 二元组
            with patch.object(mock_service, '_deliver_result', return_value=("sent", [])):
                with patch.object(mock_service, 'remove_job') as mock_remove:
                    mock_service._execute_job(job_id=1)
            
            # 当前契约（cron_service.py:335-339）：一次性任务执行完**只从调度器移除**，
            # 不再置 enabled=0 —— 保留任务记录，用户可查看结果、改时间再执行。
            # 旧断言 update_job(1, enabled=0) 对应的是已被有意改掉的行为。
            mock_remove.assert_called_with(1)
            assert not mock_mapper.update_job.called, (
                "一次性任务不应再被置为 enabled=0"
            )


class TestDeliverResult:
    """测试投递逻辑"""

    @pytest.fixture
    def mock_service(self):
        """创建测试用的 CronService 实例"""
        from backend.service.cron.cron_service import CronService
        CronService._instance = None
        CronService._scheduler = None
        service = CronService()
        yield service
        if service._scheduler:
            service._scheduler.shutdown(wait=False)

    def test_deliver_wechat_only(self, mock_service):
        """测试只投递到微信"""
        task = {
            "user_id": 1,
            "deliver_to": "wechat"
        }
        
        with patch('backend.service.cron.delivery.cron_delivery.deliver_wechat', return_value=(True, "")) as mock_wechat:
            import asyncio
            result = asyncio.run(mock_service._deliver_result(
                task=task,
                subject="测试",
                body="内容",
                session_id="test_session"
            ))
            
            assert mock_wechat.called
            assert "wechat:ok" in result[0]

    def test_deliver_email_only(self, mock_service):
        """测试只投递到邮箱"""
        task = {
            "user_id": 1,
            "deliver_to": "email"
        }
        
        with patch('backend.service.cron.delivery.cron_delivery.deliver_email', return_value=(True, "")) as mock_email:
            import asyncio
            result = asyncio.run(mock_service._deliver_result(
                task=task,
                subject="测试",
                body="内容",
                session_id="test_session"
            ))
            
            assert mock_email.called
            assert "email:ok" in result[0]

    def test_deliver_both(self, mock_service):
        """测试同时投递到微信和邮箱"""
        task = {
            "user_id": 1,
            "deliver_to": "both"
        }
        
        with patch('backend.service.cron.delivery.cron_delivery.deliver_wechat', return_value=(True, "")) as mock_wechat, \
             patch('backend.service.cron.delivery.cron_delivery.deliver_email', return_value=(True, "")) as mock_email:
            import asyncio
            result = asyncio.run(mock_service._deliver_result(
                task=task,
                subject="测试",
                body="内容",
                session_id="test_session"
            ))
            
            assert mock_wechat.called
            assert mock_email.called
            assert "wechat:ok" in result[0]
            assert "email:ok" in result[0]

    def test_deliver_wechat_failed(self, mock_service):
        """测试微信投递失败"""
        task = {
            "user_id": 1,
            "deliver_to": "wechat"
        }
        
        with patch('backend.service.cron.delivery.cron_delivery.deliver_wechat', return_value=(False, "发送失败")):
            import asyncio
            result = asyncio.run(mock_service._deliver_result(
                task=task,
                subject="测试",
                body="内容",
                session_id="test_session"
            ))
            
            assert "wechat:failed" in result[0]

    def test_deliver_no_channel(self, mock_service):
        """测试无投递渠道（空字符串会默认为 wechat）"""
        task = {
            "user_id": 1,
            "deliver_to": ""  # 空字符串会被 or 替换为 "wechat"
        }
        
        with patch('backend.service.cron.delivery.cron_delivery.deliver_wechat', return_value=(True, "")) as mock_wechat:
            import asyncio
            result = asyncio.run(mock_service._deliver_result(
                task=task,
                subject="测试",
                body="内容",
                session_id="test_session"
            ))
            
            # 空字符串会被默认为 wechat
            assert mock_wechat.called
            assert "wechat:ok" in result[0]
