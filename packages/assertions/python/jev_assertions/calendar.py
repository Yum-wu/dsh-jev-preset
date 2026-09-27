# -*- coding: utf-8 -*-
"""
JEV 量化断言库 - 跨国时区对齐与夏令时跳跃检测
"""
from datetime import datetime, timezone, timedelta
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

def assert_ny_open_utc(date_str, ny_open_local, expected_utc):
    """
    断言纽约开盘时间对应的 UTC 时间戳 (自动处理 EST/EDT 夏令时)
    """
    ny_tz = zoneinfo.ZoneInfo("America/New_York")
    dt_str = f"{date_str} {ny_open_local}"
    local_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ny_tz)
    utc_dt = local_dt.astimezone(timezone.utc)
    actual_utc = utc_dt.strftime("%H:%M:%S")

    assert actual_utc == expected_utc, f"[夏令时开盘对齐失败] 日期={date_str}, 期望UTC={expected_utc}, 实际={actual_utc}"
    return True

def assert_clock_monotonic(t1_ns, t2_ns, expect_monotonic):
    """
    断言高频时钟单调性 (拦截 NTP 回拨导致的负时延)
    """
    is_mono = (t2_ns >= t1_ns)
    assert is_mono == bool(expect_monotonic), f"[单调时钟异常] t1={t1_ns}, t2={t2_ns}, dt={t2_ns - t1_ns} ns, 期望单调={expect_monotonic}"
    return True
