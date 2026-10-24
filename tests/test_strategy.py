from src.strategy import Market, Params, levels, position_size, simulate_day
from tests.synth import day_bars

P, M = Params(range_minutes=15, stop_mode="opposite", target_r=1.5, exit_time="11:30"), Market()
RANGE = [(100, 104, 99, 102), (102, 105, 100, 103), (103, 104, 98, 101)]  # haut 105, bas 98


def test_levels_and_size():
    lv = levels(105, 98, P, M)
    assert lv["long_entry"] == 105.25 and lv["long_stop"] == 97.75
    assert lv["long_target"] == 105.25 + 1.5 * 7.5
    n, per = position_size(200, 105.25, 97.75, M, 5)
    assert per == 7.5 * 5 + M.cost_per_contract() and n == 4


def test_long_hits_target():
    r = simulate_day(day_bars(RANGE + [(101, 106, 101, 105.5), (105.5, 117, 105, 116.5)]), "2026-10-26", P, M, 200, 5)
    assert r["status"] == "trade" and r["dir"] == "LONG" and r["exit_reason"] == "objectif" and r["pnl"] > 0


def test_short_stopped():
    r = simulate_day(day_bars(RANGE + [(99, 99.5, 97, 97.5), (97.5, 106, 97, 105)]), "2026-10-26", P, M, 200, 5)
    assert r["dir"] == "SHORT" and r["exit_reason"] == "stop" and r["pnl"] < 0 and -1.05 < r["r"] < -0.95


def test_no_breakout_and_atr_filter():
    assert simulate_day(day_bars(RANGE + [(101, 104, 99, 102)] * 5), "2026-10-26", P, M, 200, 5)["reason"] == "pas de cassure"
    assert simulate_day(day_bars(RANGE + [(101, 106, 101, 105)]), "2026-10-26", P, M, 200, 5, atr=10)["reason"] == "range trop large vs ATR"


def test_time_exit():
    bars = day_bars(RANGE + [(101, 106, 101, 105.5)] + [(105.5, 106, 104, 105)] * 30)
    r = simulate_day(bars, "2026-10-26", P, M, 200, 5)
    assert r["exit_reason"] == "sortie horaire" and r["exit_time"].hour == 11
