"""when_resolver 单元测试"""
from datetime import datetime, timedelta

import pytest

from backend.utils.when_resolver import resolve_when

NOW = datetime(2026, 8, 14, 15, 30, 0)


class TestResolveWhen:
    def test_default_today(self):
        start, end = resolve_when(None, now=NOW)
        assert start == datetime(2026, 8, 14, 0, 0, 0)
        assert end == NOW

    def test_today(self):
        start, end = resolve_when("今天", now=NOW)
        assert start == datetime(2026, 8, 14, 0, 0, 0)
        assert end == NOW

    def test_yesterday(self):
        start, end = resolve_when("昨天", now=NOW)
        assert start == datetime(2026, 8, 13, 0, 0, 0)
        assert end == datetime(2026, 8, 14, 0, 0, 0)

    def test_this_week(self):
        # 2026-08-14 是周五，本周一开始于 8-10
        start, end = resolve_when("本周", now=NOW)
        assert start == datetime(2026, 8, 10, 0, 0, 0)
        assert end == NOW

    def test_last_week(self):
        start, end = resolve_when("上周", now=NOW)
        assert start == datetime(2026, 8, 3, 0, 0, 0)
        assert end == datetime(2026, 8, 10, 0, 0, 0)

    def test_this_month(self):
        start, end = resolve_when("本月", now=NOW)
        assert start == datetime(2026, 8, 1, 0, 0, 0)
        assert end == NOW

    def test_last_quarter(self):
        start, end = resolve_when("上季度", now=NOW)
        assert start == datetime(2026, 4, 1, 0, 0, 0)
        assert end == datetime(2026, 7, 1, 0, 0, 0)

    def test_recent_n_days_arabic(self):
        start, end = resolve_when("最近7天", now=NOW)
        assert end == NOW
        assert start == NOW - timedelta(days=7)

    def test_recent_n_days_chinese(self):
        start, end = resolve_when("最近三天", now=NOW)
        assert start == NOW - timedelta(days=3)

    def test_recent_hours(self):
        start, end = resolve_when("过去6小时", now=NOW)
        assert start == NOW - timedelta(hours=6)

    def test_future_days(self):
        start, end = resolve_when("未来2天", now=NOW)
        assert start == NOW
        assert end == NOW + timedelta(days=2)

    def test_last_year(self):
        start, end = resolve_when("去年", now=NOW)
        assert start == datetime(2025, 1, 1, 0, 0, 0)
        assert end == datetime(2026, 1, 1, 0, 0, 0)

    def test_unresolved_raises(self):
        with pytest.raises(ValueError):
            resolve_when("下下下星期八", now=NOW)