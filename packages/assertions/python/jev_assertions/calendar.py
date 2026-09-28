# -*- coding: utf-8 -*-
"""
JEV 量化断言库 - 跨国时区对齐与夏令时跳跃检测
"""
from datetime import datetime, timezone, timedelta
try:
    import zoneinfo
except ImportError:
    try:
        from backports import zoneinfo
    except ImportError:
        zoneinfo = None  # 无任何 tz 后端时走纯手算降级

def _ny_utc_offset(date_str):
    """手算纽约当日 UTC 偏移(EST=-5/EDT=-4)。DST:3月第2个周日~11月第1个周日。"""
    y, m, d = (int(x) for x in date_str.split("-"))
    from datetime import date
    def nth_weekday(year, month, weekday, n):
        first = date(year, month, 1)
        delta = (weekday - first.weekday()) % 7 + (n - 1) * 7
        return first.day + delta
    dst_start = nth_weekday(y, 3, 6, 2)  # 3月第2个周日
    dst_end = nth_weekday(y, 11, 6, 1)   # 11月第1个周日
    in_dst = (m, d) >= (3, dst_start) and (m, d) < (11, dst_end)
    return -4 if in_dst else -5

def assert_ny_open_utc(date_str, ny_open_local, expected_utc):
    """
    断言纽约开盘时间对应的 UTC 时间戳 (自动处理 EST/EDT 夏令时)
    CI 精简环境缺 tzdata 时降级为手算偏移,零依赖。
    """
    try:
        if zoneinfo is None:
            raise Exception("no tz backend")
        ny_tz = zoneinfo.ZoneInfo("America/New_York")
    except Exception:
        h, mi, s = (int(x) for x in ny_open_local.split(":"))
        utc_h = (h - _ny_utc_offset(date_str)) % 24
        actual_utc = f"{utc_h:02d}:{mi:02d}:{s:02d}"
        assert actual_utc == expected_utc, f"[夏令时开盘对齐失败/降级] 日期={date_str}, 期望UTC={expected_utc}, 实际={actual_utc}"
        return True
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
