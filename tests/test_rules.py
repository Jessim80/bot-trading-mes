import pandas as pd

from src.calendar_eco import day_verdict

F = {"vix_half_size": 25, "vix_no_trade": 30}


def ev(hm, title, impact="High"):
    return {"time": pd.Timestamp(f"2026-10-26 {hm}", tz="America/New_York"), "title": title, "impact": impact}


def test_rules():
    assert day_verdict([ev("14:00", "Federal Funds Rate")], 15, F)["status"] == "PAS DE TRADE"
    assert day_verdict([ev("10:00", "ISM Manufacturing PMI")], 15, F)["status"] == "PAS DE TRADE"
    v = day_verdict([ev("08:30", "CPI m/m")], 15, F)
    assert v["status"] == "PRUDENCE" and v["factor"] == 0.5
    assert day_verdict([], 31, F)["status"] == "PAS DE TRADE"
    assert day_verdict([], 26, F)["factor"] == 0.5
    assert day_verdict([ev("10:00", "Pending Home Sales", "Medium")], 15, F)["status"] == "GO"
    assert day_verdict(None, 15, F)["status"] == "PRUDENCE"
