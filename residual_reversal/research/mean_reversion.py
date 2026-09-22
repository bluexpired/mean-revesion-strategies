"""Unvalidated long-only reversal research; not an OU/stat-arb paper reproduction."""
import math
from statistics import mean, stdev
from research.common import clip, digest, dt
from research.sessions import complete, latest_complete, contiguous

VERSION = "mr-v2"


def settings(cfg):
    opts = {"training_sessions": 60, "signal_sessions": 3, "entry_z": -2.0,
            "band_window": 20, "trend_window": 200, "rsi_period": 2, "rsi_entry": 10,
            "max_holding_sessions": 5, "max_factor_correlation": 0.98, "sector_etfs": {}}
    opts.update(cfg.get("mean_reversion", {}))
    for key in ("training_sessions", "signal_sessions", "band_window", "trend_window", "rsi_period", "max_holding_sessions"):
        if not isinstance(opts[key], int) or opts[key] < 1:
            raise ValueError("Invalid mean_reversion setting: " + key)
    if opts["training_sessions"] < max(20, opts["signal_sessions"] + 5) or opts["band_window"] < 2:
        raise ValueError("Insufficient mean-reversion training/band window")
    if not math.isfinite(opts["entry_z"]) or opts["entry_z"] >= 0:
        raise ValueError("entry_z must be finite and negative")
    if not 0 < opts["max_factor_correlation"] < 1 or not 0 < opts["rsi_entry"] < 50:
        raise ValueError("Invalid correlation or RSI threshold")
    return opts


def clean_bars(rows, cutoff):
    result = {}
    for bar in rows:
        try:
            day = dt(bar["t"]).date()
            values = [float(bar[k]) for k in ("o", "h", "l", "c")]
            o, h, l, c = values
            if not complete(day, cutoff) or not all(math.isfinite(x) and x > 0 for x in values):
                continue
            if not l <= min(o, c) <= max(o, c) <= h:
                continue
            if day in result:
                raise ValueError("Duplicate daily bar: " + day.isoformat())
            result[day] = dict(bar, o=o, h=h, l=l, c=c)
        except (KeyError, TypeError):
            continue
    return result


def fit_factors(y, market, sector, max_correlation=0.98):
    """OLS with intercept and two centered factors, no external packages."""
    if not len(y) == len(market) == len(sector) or len(y) < 4:
        raise ValueError("Factor regression needs aligned observations")
    ym, mm, sm = mean(y), mean(market), mean(sector)
    yc, mc, sc = [v-ym for v in y], [v-mm for v in market], [v-sm for v in sector]
    mm2, ss2 = sum(v*v for v in mc), sum(v*v for v in sc)
    ms = sum(a*b for a, b in zip(mc, sc))
    if min(mm2, ss2) < 1e-12:
        raise ValueError("Zero/near-zero factor variance")
    correlation = ms / math.sqrt(mm2 * ss2)
    if abs(correlation) >= max_correlation:
        raise ValueError("Market/sector factors too collinear; no silent fallback")
    my, sy = sum(a*b for a, b in zip(mc, yc)), sum(a*b for a, b in zip(sc, yc))
    determinant = mm2 * ss2 - ms * ms
    bm = (my * ss2 - sy * ms) / determinant
    bs = (sy * mm2 - my * ms) / determinant
    alpha = ym - bm * mm - bs * sm
    residuals = [r-alpha-bm*m-bs*s for r, m, s in zip(y, market, sector)]
    total = sum(v*v for v in yc)
    return {"alpha": alpha, "beta_market": bm, "beta_sector": bs,
            "factor_correlation": correlation, "r_squared": 1-sum(v*v for v in residuals)/total if total > 1e-12 else None,
            "residuals": residuals}


def wilder_rsi(closes, period=2):
    if len(closes) <= period:
        return None
    changes = [b-a for a, b in zip(closes, closes[1:])]
    gain = mean(max(x, 0) for x in changes[:period])
    loss = mean(max(-x, 0) for x in changes[:period])
    for change in changes[period:]:
        gain = (gain*(period-1) + max(change, 0))/period
        loss = (loss*(period-1) + max(-change, 0))/period
    if gain + loss < 1e-12:
        return 50.0
    return 100.0 if loss < 1e-12 else 100 - 100/(1+gain/loss)


def price_baselines(closes, opts):
    w, trend_w = opts["band_window"], opts["trend_window"]
    previous = closes[-w-1:-1]
    sigma = stdev(previous) if len(previous) == w else 0
    band_z = (closes[-1]-mean(previous))/sigma if sigma > 1e-10 else None
    trend_ma = mean(closes[-trend_w-1:-1]) if len(closes) > trend_w else None
    uptrend = closes[-1] > trend_ma if trend_ma is not None else None
    rsi = wilder_rsi(closes, opts["rsi_period"])
    return {"band_z": band_z, "band_trigger": band_z is not None and band_z <= opts["entry_z"],
            "rsi": rsi, "rsi_trigger": rsi is not None and rsi <= opts["rsi_entry"],
            "prior_trend_ma": trend_ma, "uptrend": uptrend,
            "trend_pullback_trigger": bool(uptrend and rsi is not None and rsi <= opts["rsi_entry"]),
            "role": "comparison_only; same-price indicators are not independent confirmations"}


def residual_signal(stock, market, sector, dates, opts):
    n, h = opts["training_sessions"], opts["signal_sessions"]
    def returns(series):
        return [math.log(b/a) for a, b in zip(series, series[1:])]
    y, m, s = returns(stock), returns(market), returns(sector)
    train = slice(-n-h, -h)
    model = fit_factors(y[train], m[train], s[train], opts["max_factor_correlation"])
    residual = model.pop("residuals")
    # Empirical h-session residual sums allow serial dependence in scale estimation.
    # Overlapping training sums are NOT independent statistical test observations.
    sums = [sum(residual[i:i+h]) for i in range(len(residual)-h+1)]
    sigma = stdev(sums)
    if sigma < 1e-7:
        raise ValueError("Residual scale too small; unstable standardized signal")
    recent = [r-model["alpha"]-model["beta_market"]*mr-model["beta_sector"]*sr
              for r, mr, sr in zip(y[-h:], m[-h:], s[-h:])]
    displacement = sum(recent)
    z = (displacement-mean(sums))/sigma
    return dict(model, z=z, residual_log_return=displacement, training_sum_scale=sigma,
                training_start=dates[-n-h].isoformat(), training_end=dates[-h-1].isoformat(),
                signal_start=dates[-h].isoformat(), signal_end=dates[-1].isoformat(),
                training_observations=n, signal_observations=h, triggered=z <= opts["entry_z"],
                score=clip(-z/(2*abs(opts["entry_z"])), 0, 1),
                interpretation="Unusual residual decline, NOT evidence of stationarity or expected profit")


def analyze_mean_reversion(snapshot, cfg, news=None):
    # Compatibility argument deliberately ignored: quantitative output MUST be news-invariant.
    opts = settings(cfg)
    cutoff = dt(snapshot["cutoff"])
    clean = {s: clean_bars(rows, cutoff) for s, rows in snapshot["bars"].items()}
    market = clean.get(cfg["benchmark"], {})
    market_dates = sorted(market)
    members = {m["symbol"]: m for m in snapshot.get("universe", {}).get("members", [])}
    rows = []
    for symbol in cfg["watchlist"]:
        row = {"symbol": symbol, "status": "DATA_BLOCKED", "score": None, "reasons": [], "baseline": None, "residual": None}
        row["company"] = members.get(symbol, {}).get("name", symbol)
        row["industry"] = members.get(symbol, {}).get("industry", "Unknown")
        own = clean.get(symbol, {})
        own_dates = sorted(own)
        if len(own_dates) >= opts["band_window"]+1:
            row["baseline"] = price_baselines([own[d]["c"] for d in own_dates], opts)
        sector_symbol = opts["sector_etfs"].get(symbol)
        row["sector_etf"] = sector_symbol
        sector = clean.get(sector_symbol, {})
        required = opts["training_sessions"]+opts["signal_sessions"]+1
        if not sector:
            row["reasons"].append("Sector ETF missing; recollect with new config (no legacy fallback)")
        elif len(market_dates) < required:
            row["reasons"].append("Insufficient benchmark history")
        else:
            dates = market_dates[-required:]
            if dates[-1] != latest_complete(cutoff) or not contiguous(dates):
                row["reasons"].append("Latest completed session missing or benchmark calendar gap")
            elif (cutoff.date()-dates[-1]).days > cfg["max_bar_age_days"]:
                row["reasons"].append("Stale benchmark bars")
            elif any(d not in own or d not in sector for d in dates):
                row["reasons"].append("Missing aligned session; refusing multi-day returns disguised as daily")
            else:
                try:
                    signal = residual_signal([own[d]["c"] for d in dates], [market[d]["c"] for d in dates],
                                             [sector[d]["c"] for d in dates], dates, opts)
                    row.update(residual=signal, score=signal["score"], last_bar=dates[-1].isoformat(),
                               status="REVIEW_CANDIDATE" if signal["triggered"] else "NO_SIGNAL")
                    row["reasons"].append("Residual threshold reached" if signal["triggered"] else "Residual threshold not reached")
                except ValueError as exc:
                    row["reasons"].append(str(exc))
        if own_dates:
            row["reference_close"] = own[own_dates[-1]]["c"]
            row["observed_daily_dollar_volume20"] = mean(own[d]["c"]*float(own[d].get("v", 0)) for d in own_dates[-20:])
            row["volume_scope"] = snapshot.get("feed", "unknown")
            if row["reference_close"] < cfg.get("pairs", {}).get("min_price", 5):
                row["status"] = "PRICE_FILTERED"
                row["reasons"].append("Price below configured research minimum")
        if own_dates and len(own_dates) >= 15:
            recent = own_dates[-14:]
            prev_dates = own_dates[-15:-1]
            tr = [max(own[d]["h"]-own[d]["l"], abs(own[d]["h"]-own[p]["c"]), abs(own[d]["l"]-own[p]["c"]))
                  for d, p in zip(recent, prev_dates)]
            row["atr_pct"] = mean(tr)/own[own_dates[-1]]["c"]
            row["stop_atr_ratio"] = cfg["risk"]["stop_pct"]/row["atr_pct"] if row["atr_pct"] > 0 else None
            if row["atr_pct"] > cfg["risk"]["stop_pct"]:
                row["reasons"].append("Fixed stop tighter than 1 daily ATR; noise-stop risk")
        row["reasons"].append("Quant-only output; no news input. Execution spreads and corporate actions unverified")
        row["exit_plan"] = {"stop_pct": cfg["risk"]["stop_pct"], "take_profit_pct": cfg["risk"]["take_profit_pct"],
                            "max_holding_sessions": opts["max_holding_sessions"], "execution": "manual paper only; gaps not guaranteed; no averaging down"}
        rows.append(row)
    c = cfg["risk"]["one_way_cost_bps"]/10000
    gain = (1+cfg["risk"]["take_profit_pct"])*(1-c)/(1+c)-1
    loss = 1-(1-cfg["risk"]["stop_pct"])*(1-c)/(1+c)
    return {"version": VERSION, "mode": snapshot["mode"], "cutoff": snapshot["cutoff"], "config_hash": digest(cfg),
            "settings": opts, "results": rows, "news_used": False, "universe": snapshot.get("universe", {}), "fixed_exit_cost_example": {"net_target_return": gain, "net_stop_return": -loss,
            "break_even_win_rate": loss/(gain+loss), "assumption": "Only exact target/stop outcomes, constant costs, no gaps or time exits; NOT predicted win rate"},
            "limitations": ["Long-only screen, not market-neutral statistical arbitrage", "No OU, cointegration or stationarity test implemented",
                             "ETF contains some target stocks; residual signal can be attenuated", "Thresholds are hypotheses, not optimized or validated",
                             "Split-only prices include dividend-date drops; verify ex-dividend events", "IEX feed is not consolidated; no full-market liquidity claim"]}


def markdown_report(result):
    lines = ["# Mean reversion research " + result["version"], "", "Mode: " + result["mode"], "Cutoff UTC: " + result["cutoff"],
             "", "DEMO는 합성 데이터입니다. 모든 점수는 진입 검토용이며 수익확률이 아닙니다.",
             "주 분석: 시장+업종 OLS 잔차 3일 이탈. 밴드/RSI는 비교용이며 결합 점수에 가산하지 않습니다.", "",
             "|종목|상태|업종 ETF|잔차 z|밴드 z|RSI|200일 추세|", "|---|---|---|---:|---:|---:|---|"]
    def fmt(v):
        return "—" if v is None else f"{v:.2f}"
    for row in result["results"]:
        base = row["baseline"] or {}
        lines.append(f"|{row['symbol']}|{row['status']}|{row['sector_etf']}|{fmt((row['residual'] or {}).get('z'))}|{fmt(base.get('band_z'))}|{fmt(base.get('rsi'))}|{base.get('uptrend')}|")
    cost = result["fixed_exit_cost_example"]
    lines += ["", "## 비용과 청산 가정", "", f"정확히 고정 익절/손절만 발생한다고 가정한 비용 후 손익분기 승률: {cost['break_even_win_rate']:.2%}.",
              "예측 승률이 아닙니다. 갭/시간청산/손익 크기 차이가 있으면 달라집니다. 최대 5거래일은 수동 모의운용 규칙입니다.",
              "", "## 후보별 근거", ""]
    for row in result["results"]:
        lines += ["### " + row["symbol"], ""] + ["- " + r for r in row["reasons"]]
        if row["residual"]:
            r = row["residual"]
            lines += [f"- 학습: {r['training_start']} ~ {r['training_end']}; 신호: {r['signal_start']} ~ {r['signal_end']}",
                      f"- 시장 beta={r['beta_market']:.3f}, 업종 beta={r['beta_sector']:.3f}, R²={fmt(r['r_squared'])}",
                      f"- 누적 잔차(log return): {r['residual_log_return']:.3%}; 기준 scale: {r['training_sum_scale']:.3%}"]
        lines.append("")
    lines += ["## 한계", ""] + ["- " + s for s in result["limitations"]]
    return "\n".join(lines)+"\n"
