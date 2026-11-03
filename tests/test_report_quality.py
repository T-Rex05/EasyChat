"""报告质量检查 + 命名规则 单元测试"""
from datetime import datetime

from backend.service.report.report_quality import check_report
from backend.service.report.report_naming import build_report_filename, safe_task_name


class TestReportQuality:
    def test_empty(self):
        r = check_report("")
        assert r["ok"] is False
        assert any("为空" in i for i in r["issues"])

    def test_too_short(self):
        r = check_report("你好")
        assert r["ok"] is False
        assert any("过短" in i for i in r["issues"])

    def test_unclosed_fence(self):
        r = check_report("```python\nprint(1)\n" + "x" * 100)
        assert any("代码块" in i for i in r["issues"])

    def test_ok_report(self):
        body = "# 日报\n\n" + "正常内容。" * 20
        r = check_report(body)
        assert r["ok"] is True

    def test_repeated_lines(self):
        line = "这条内容重复出现了很多次用来检测重复段落逻辑"
        body = line + "\n" + line + "\n" + line + "\n" + line + "\n" + "x" * 80
        r = check_report(body)
        assert any("重复" in i for i in r["issues"])


class TestReportNaming:
    def test_safe_name(self):
        assert safe_task_name("a/b:c*") == "a_b_c_"
        assert safe_task_name("") == "report"

    def test_filename_with_timestamp(self):
        fn = build_report_filename("日报", datetime(2026, 8, 14, 9, 30, 0), ".md")
        assert fn == "日报_20260814_093000.md"

    def test_ext_normalization(self):
        fn = build_report_filename("t", datetime(2026, 1, 2, 3, 4, 5), "pdf")
        assert fn.endswith(".pdf")