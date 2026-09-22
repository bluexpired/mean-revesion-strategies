import copy
import math
import random
import unittest
from datetime import date, timedelta

from research.common import config
from research.mean_reversion import analyze_mean_reversion, fit_factors, residual_signal, settings, wilder_rsi


def fixture(shock=0):
    cfg = config()
    cfg["watchlist"] = ["AAPL"]
    cfg["mean_reversion"]["sector_etfs"] = {"AAPL": "XLK"}
    rng = random.Random(902)
    from research.calendar import calendar
    dates = list(calendar().sessions_in_range("2025-01-01", "2026-03-01").date)[:240]
    bars = {s: [] for s in ("AAPL", "SPY", "XLK")}
    prices = {s: 100.0 for s in bars}
    for i, day in enumerate(dates):
        m = rng.gauss(0.0005, 0.01)
        s = 0.5*m + rng.gauss(0, 0.008)
        r = 0.0001 + 0.8*m + 0.6*s + rng.gauss(0, 0.003) + (shock if i >= len(dates)-3 else 0)
        for symbol, ret in (("AAPL", r), ("SPY", m), ("XLK", s)):
            opening = prices[symbol]
            close = opening * math.exp(ret)
            prices[symbol] = close
            bars[symbol].append({"t": day.isoformat()+"T04:00:00Z", "o": opening, "h": max(opening, close)*1.005,
                                 "l": min(opening, close)*0.995, "c": close, "v": 1000000})
    return cfg, {"mode": "demo", "cutoff": (dates[-1]+timedelta(days=1)).isoformat()+"T12:00:00Z",
                 "collected_at": (dates[-1]+timedelta(days=1)).isoformat()+"T12:01:00Z", "config": cfg,
                 "bars": bars, "news": [], "fundamentals": {}, "feed": "synthetic", "limitations": []}


class MeanReversionTests(unittest.TestCase):
    def test_known_factor_coefficients(self):
        rng = random.Random(10)
        m = [rng.gauss(0, .01) for _ in range(60)]
        s = [rng.gauss(0, .01) for _ in range(60)]
        y = [.001 + .8*a + 1.2*b for a, b in zip(m, s)]
        model = fit_factors(y, m, s)
        self.assertAlmostEqual(model["alpha"], .001)
        self.assertAlmostEqual(model["beta_market"], .8)
        self.assertAlmostEqual(model["beta_sector"], 1.2)
        self.assertAlmostEqual(model["r_squared"], 1)

    def test_collinear_factors_rejected(self):
        with self.assertRaisesRegex(ValueError, "collinear"):
            fit_factors([1, 2, 3, 4], [1, 2, 3, 4], [2, 4, 6, 8])

    def test_recent_shock_does_not_change_training_betas(self):
        cfg, normal = fixture()
        _, shocked = fixture(-.025)
        a = analyze_mean_reversion(normal, cfg)["results"][0]["residual"]
        b = analyze_mean_reversion(shocked, cfg)["results"][0]["residual"]
        for key in ("alpha", "beta_market", "beta_sector", "training_sum_scale"):
            self.assertAlmostEqual(a[key], b[key])
        self.assertLess(b["z"], -2)
        self.assertLess(b["training_end"], b["signal_start"])

    def test_shock_is_review_not_automatic_buy(self):
        cfg, snap = fixture(-.025)
        row = analyze_mean_reversion(snap, cfg)["results"][0]
        self.assertEqual(row["status"], "REVIEW_CANDIDATE")
        self.assertEqual(row["exit_plan"]["max_holding_sessions"], 5)

    def test_upward_shock_not_long_reversal(self):
        cfg, snap = fixture(.025)
        self.assertEqual(analyze_mean_reversion(snap, cfg)["results"][0]["status"], "NO_SIGNAL")

    def test_missing_sector_no_fallback(self):
        cfg, snap = fixture(-.025)
        del snap["bars"]["XLK"]
        row = analyze_mean_reversion(snap, cfg)["results"][0]
        self.assertEqual(row["status"], "DATA_BLOCKED")
        self.assertIsNotNone(row["baseline"])

    def test_missing_interior_bar_blocks_alignment(self):
        cfg, snap = fixture(-.025)
        snap["bars"]["AAPL"].pop(-8)
        self.assertEqual(analyze_mean_reversion(snap, cfg)["results"][0]["status"], "DATA_BLOCKED")

    def test_future_bars_cannot_change_result(self):
        cfg, snap = fixture(-.025)
        a = analyze_mean_reversion(snap, cfg)
        extra = dict(snap["bars"]["AAPL"][-1], t="2099-01-01T04:00:00Z", c=1, l=1)
        snap["bars"]["AAPL"].append(extra)
        self.assertEqual(a, analyze_mean_reversion(snap, cfg))

    def test_negative_news_cannot_change_quant_output(self):
        cfg, snap = fixture(-.025)
        news = {"results": [{"symbol": "AAPL", "material_negative_flag": True}]}
        self.assertEqual(analyze_mean_reversion(snap, cfg, news), analyze_mean_reversion(snap, cfg))

    def test_recent_event_cannot_change_quant_output(self):
        cfg, snap = fixture(-.025)
        news = {"results": [{"symbol": "AAPL", "evidence": [{"created_at": snap["cutoff"], "event": "earnings_guidance"}]}]}
        self.assertEqual(analyze_mean_reversion(snap, cfg, news), analyze_mean_reversion(snap, cfg))

    def test_rsi_edges(self):
        self.assertEqual(wilder_rsi([1, 2, 3, 4]), 100)
        self.assertEqual(wilder_rsi([4, 3, 2, 1]), 0)
        self.assertEqual(wilder_rsi([2, 2, 2, 2]), 50)

    def test_cost_break_even_above_half(self):
        cfg, snap = fixture()
        result = analyze_mean_reversion(snap, cfg)["fixed_exit_cost_example"]
        self.assertGreater(result["break_even_win_rate"], .5)
        self.assertLess(result["net_target_return"], cfg["risk"]["take_profit_pct"])



    def test_invalid_window_rejected(self):
        cfg, _ = fixture()
        cfg["mean_reversion"]["signal_sessions"] = 0
        with self.assertRaises(ValueError):
            settings(cfg)


if __name__ == "__main__":
    unittest.main()
