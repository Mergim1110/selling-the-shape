"""Selling the Shape: full analysis pipeline.

Usage:  python run_analysis.py <dir with SMARD csv exports> <reference dir> <output dir>

Inputs (SMARD.de market data exports, original resolution, 1 Jan 2022 onward):
  DayAhead_Preise_aktuell.csv                    day ahead price DE/LU
  Realisierte_Erzeugung_Wind_PV_aktuell.csv      realised generation wind and PV
  Realisierter_Stromverbrauch_Netzlast_aktuell.csv  realised grid load
Everything in the report is computed here; nothing is typed in by hand.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

from battery import settle, solve_day
from smardio import apply_smard_revisions, load_all

START, END = "2022-01-01", "2026-11-01"       # [start, end) in Europe/Berlin time
BASE = dict(power=1.0, hours=2.0, rte=0.85, cycles=2.0)   # assumptions, see report
QH_START = pd.Timestamp("2025-10-01", tz="Europe/Berlin")  # first 15 minute delivery day
APPLY_REVISIONS = True   # set False when data_raw holds a fresh first hand SMARD download


def hourly(series: pd.Series, how: str) -> pd.Series:
    u = series.copy()
    u.index = u.index.tz_convert("UTC")
    return getattr(u.groupby(u.index.floor("h")), how)()


HOUR_NEG = None   # UTC hour -> True if the hourly day ahead price is negative (set in main)


def period_stats(g: pd.DataFrame) -> dict:
    hours_utc = g.index.tz_convert("UTC").floor("h").unique()
    solar = g["solar"]
    neg = g["price"] < 0
    base = g["price"].mean()
    cap = (g["price"] * solar).sum() / solar.sum()
    floor0 = (g["price"].clip(lower=0) * solar).sum() / solar.sum()
    return {
        "hours": len(g) / 4,
        "base": base,
        "solar_capture": cap,
        "capture_rate": cap / base,
        "shape_discount": base - cap,
        "neg_hours": int(HOUR_NEG.reindex(hours_utc).sum()),
        "neg_quarter_hours": int(neg.sum()),
        "zero_hours": float((g["price"] == 0).sum() / 4),
        "neg_time_share": neg.mean(),
        "solar_twh": solar.sum() / 1e6,
        "load_twh": g["load"].sum() / 1e6,
        "solar_share_load": solar.sum() / g["load"].sum(),
        "solar_share_in_neg": solar[neg].sum() / solar.sum(),
        "capture_if_curtailed": floor0,
        "min_price": g["price"].min(),
        "max_price": g["price"].max(),
    }


def main(raw_dir: Path, ref_dir: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    raw = load_all(raw_dir, START, END, ref_dir / "clock_change_fill.csv")
    assert not raw.isna().any().any()
    # Data vintage. Compare the exports with SMARD's monthly series as of 11 November 2026,
    # then bring the months SMARD has revised since the export up to date.
    ref_m = pd.read_csv(ref_dir / "smard_monthly_totals_2026-11-11.csv", index_col=0)
    ymr = raw.index.strftime("%Y-%m")
    vint = pd.DataFrame({"solar_export": raw["solar"].groupby(ymr).sum(),
                         "load_export": raw["load"].groupby(ymr).sum()}).join(ref_m)
    vint["solar_rev_pct"] = (vint["solar_mwh"] / vint["solar_export"] - 1) * 100
    vint["load_rev_pct"] = (vint["load_mwh"] / vint["load_export"] - 1) * 100
    df = apply_smard_revisions(raw, ref_dir) if APPLY_REVISIONS else raw
    assert not df.isna().any().any()
    # Negative hours. Until 30 September 2025 an hour has one price. From delivery day
    # 1 October 2025 prices are quarter hourly and the hourly price is taken from SMARD's
    # own hourly resolution series, so that ties in rounding are resolved as SMARD does.
    global HOUR_NEG
    ph = hourly(df["price"], "mean")
    smard_h = pd.read_csv(ref_dir / "smard_hourly_price_from_oct2025.csv", parse_dates=["utc_start"])
    smard_h = smard_h.set_index("utc_start")["price_eur_mwh"]
    post = ph.index >= QH_START.tz_convert("UTC")
    assert ph.index[post].equals(smard_h.index), "hourly reference series does not cover the sample"
    assert (ph[post] - smard_h).abs().max() < 0.0101, "hourly reference series disagrees with exports"
    ph[post] = smard_h.values
    HOUR_NEG = ph < 0
    res = {"sample": {"start": START, "end_exclusive": END, "quarter_hours": len(df),
                      "hours": len(df) / 4, "days": int(len(set(df.index.date))),
                      "filled_quarter_hours": raw.attrs["filled_quarter_hours"],
                      "solar_days_scaled_to_daily_total": df.attrs.get("solar_days_scaled_to_daily_total", 0)}}
    unrev = vint[(vint.index < "2026-05") | (vint.index > "2026-09")]
    res["vintage"] = {
        "max_abs_solar_diff_mwh_unrevised_months": float((unrev["solar_mwh"] - unrev["solar_export"]).abs().max()),
        "max_abs_load_diff_pct_unrevised_months": float(unrev["load_rev_pct"].abs().max()),
        "solar_rev_pct": vint.loc["2026-05":"2026-09", "solar_rev_pct"].to_dict(),
        "load_rev_pct": vint.loc["2026-05":"2026-09", "load_rev_pct"].to_dict(),
    }

    # ---------------------------------------------------------------- 1 annual and monthly
    annual = pd.DataFrame({y: period_stats(g) for y, g in df.groupby(df.index.year)}).T
    annual.index.name = "year"
    ym = df.index.strftime("%Y-%m")
    monthly = pd.DataFrame({m: period_stats(g) for m, g in df.groupby(ym)}).T
    monthly.index.name = "month"
    monthly["year"] = [int(m[:4]) for m in monthly.index]
    monthly["moy"] = [int(m[5:]) for m in monthly.index]
    # official reference values (Bundesnetzagentur, netztransparenz.de)
    ref = pd.read_csv(ref_dir / "official_reference.csv", dtype={"period": str})
    rows = []
    for _, r in ref.iterrows():
        mine = annual.loc[int(r["period"])] if r["kind"] == "annual" else monthly.loc[r["period"]]
        rows.append({"kind": r["kind"], "period": r["period"],
                     "base_calc": mine["base"], "base_official": r["base_eur_mwh"],
                     "neg_hours_calc": mine["neg_hours"], "neg_hours_official": r["neg_hours"],
                     "neg_qh_calc": mine["neg_quarter_hours"], "neg_qh_official": r["neg_quarter_hours"],
                     "solar_calc": mine["solar_capture"], "solar_official": r["solar_market_value_eur_mwh"],
                     "solar_gap_pct": mine["solar_capture"] / r["solar_market_value_eur_mwh"] - 1,
                     "solar_twh_calc": mine["solar_twh"]})
    validation = pd.DataFrame(rows).set_index("period")
    off = pd.read_csv(ref_dir / "official_monthly_market_values.csv", index_col=0)
    wedge = monthly[["year", "moy", "base", "solar_capture", "solar_twh", "solar_share_in_neg"]].join(off, how="inner")
    wedge["official_solar"] = wedge["official_solar_ct_kwh"] * 10
    wedge["gap"] = wedge["solar_capture"] - wedge["official_solar"]

    def weighted(year, col, alt=None):
        g = wedge[(wedge["year"] == year) & (wedge["moy"] <= 10)]
        v = g[col].copy()
        if alt:
            v.loc[alt[0]] = alt[1]
        return float((g["solar_twh"] * v).sum() / g["solar_twh"].sum())

    res["official_jan_oct"] = {
        str(y): {"official_weighted": weighted(y, "official_solar"),
                 "realised": weighted(y, "solar_capture"),
                 "base": float(monthly[(monthly["year"] == y) & (monthly["moy"] <= 10)]
                               .pipe(lambda g: (g["base"] * g["hours"]).sum() / g["hours"].sum()))}
        for y in (2025, 2026)}
    # May 2026 was first published as 3.163 ct/kWh and later corrected to 3.296
    res["official_jan_oct"]["2026_with_first_may_value"] = weighted(2026, "official_solar", ("2026-05", 31.63))
    res["wedge"] = {
        "corr_gap_neg_share": float(np.corrcoef(wedge["gap"], wedge["solar_share_in_neg"])[0, 1]),
        "n": int(len(wedge)),
        "mean_gap_by_year": wedge.groupby("year")["gap"].mean().to_dict(),
    }
    # trailing twelve months to end of sample
    ttm = period_stats(df[df.index >= pd.Timestamp("2025-11-01", tz="Europe/Berlin")])
    res["ttm_nov25_oct26"] = ttm
    # same months comparison (January to October of each year)
    jan_oct = pd.DataFrame({y: period_stats(g[g.index.month <= 10])
                            for y, g in df.groupby(df.index.year)}).T
    # summer half year (April to September)
    summer = pd.DataFrame({y: period_stats(g[(g.index.month >= 4) & (g.index.month <= 9)])
                           for y, g in df.groupby(df.index.year)}).T

    # average price by hour of day, April to September, relative to period baseload
    prof = {}
    for y, g in df.groupby(df.index.year):
        s = g[(g.index.month >= 4) & (g.index.month <= 9)]
        prof[y] = (s["price"].groupby(s.index.hour).mean() / s["price"].mean())
    profile = pd.DataFrame(prof)
    profile.index.name = "hour"
    prof_abs = pd.DataFrame({y: g[(g.index.month >= 4) & (g.index.month <= 9)]["price"]
                             .groupby(g[(g.index.month >= 4) & (g.index.month <= 9)].index.hour).mean()
                             for y, g in df.groupby(df.index.year)})
    prof_abs.index.name = "hour"

    # ---------------------------------------------------------------- 2 cannibalisation regressions
    x = monthly["solar_share_load"].astype(float) * 100      # percentage points
    yv = monthly["capture_rate"].astype(float) * 100
    hac = dict(cov_type="HAC", cov_kwds={"maxlags": 3})
    m1 = sm.OLS(yv, sm.add_constant(x)).fit(**hac)
    dummies = pd.get_dummies(monthly["moy"], prefix="m", drop_first=True).astype(float)
    m2 = sm.OLS(yv, sm.add_constant(pd.concat([x, dummies], axis=1))).fit(**hac)
    keep = monthly["year"] >= 2023
    m3 = sm.OLS(yv[keep], sm.add_constant(pd.concat([x, dummies], axis=1)[keep])).fit(**hac)
    res["regression"] = {
        "month_fe_ex2022": {"slope": m3.params["solar_share_load"], "se": m3.bse["solar_share_load"],
                            "n": int(m3.nobs)},
        "n": int(m1.nobs),
        "pooled": {"slope": m1.params["solar_share_load"], "se": m1.bse["solar_share_load"],
                   "intercept": m1.params["const"], "r2": m1.rsquared},
        "month_fe": {"slope": m2.params["solar_share_load"], "se": m2.bse["solar_share_load"],
                     "r2": m2.rsquared},
    }

    # ---------------------------------------------------------------- 3 battery, perfect foresight
    days = [(d, g["price"].values) for d, g in df.groupby(df.index.date)]
    dates = pd.DatetimeIndex([pd.Timestamp(d) for d, _ in days])
    configs = {"base": BASE}
    for h in (1.0, 2.0, 4.0):
        for c in (1.0, 2.0):
            configs[f"{h:g}h_{c:g}c"] = dict(BASE, hours=h, cycles=c)
    for r in (0.80, 0.90):
        configs[f"rte{int(r * 100)}"] = dict(BASE, rte=r)
    pf = {}
    sched = {}
    for name, cfg in configs.items():
        rev = []
        for d, p in days:
            r, c, dis = solve_day(p, **cfg)
            rev.append(r)
            if name == "base":
                sched[d] = (c, dis)
        pf[name] = pd.Series(rev, index=dates)
    pf = pd.DataFrame(pf)
    pf_annual = pf.groupby(pf.index.year).sum()
    ndays = pf.groupby(pf.index.year).size()
    pf_jan_oct = pf[pf.index.month <= 10].groupby(pf[pf.index.month <= 10].index.year).sum()
    pf_ttm = pf[pf.index >= "2025-11-01"].sum()
    res["battery_ttm_nov25_oct26"] = pf_ttm.to_dict()

    # ---------------------------------------------------------------- 4 ex ante schedules (base case)
    price_by_day = dict(days)
    dlist = [d for d, _ in days]
    ex = {"yesterday": [], "last_week": [], "trailing7": []}
    for i, d in enumerate(dlist):
        p = price_by_day[d]
        # (a) yesterday's optimal schedule, (b) same weekday last week
        for key, lag in (("yesterday", 1), ("last_week", 7)):
            if i >= lag and len(price_by_day[dlist[i - lag]]) == len(p):
                c, dis = sched[dlist[i - lag]]
                ex[key].append(settle(p, c, dis))
            else:
                ex[key].append(0.0 if i >= lag else np.nan)
        # (c) schedule optimal for the mean price shape of the previous seven days
        #     (days of a different length, i.e. around clock changes, are left out)
        same = [price_by_day[dlist[i - k]] for k in range(1, 8)
                if i >= 7 and len(price_by_day[dlist[i - k]]) == len(p)]
        if same and len(p) == 96:
            _, c, dis = solve_day(np.mean(same, axis=0), **BASE)
            ex["trailing7"].append(settle(p, c, dis))
        else:
            ex["trailing7"].append(0.0 if i >= 7 else np.nan)
    ex = pd.DataFrame(ex, index=dates)
    ex["perfect"] = pf["base"]
    ex_eval = ex.iloc[7:]                       # common evaluation window
    ex_annual = ex_eval.groupby(ex_eval.index.year).sum()
    ex_total = ex_eval.sum()
    res["ex_ante"] = {
        "eval_days": len(ex_eval),
        "idle_days": {k: int((ex_eval[k] == 0).sum()) for k in ("yesterday", "last_week", "trailing7")},
        "capture_total": {k: ex_total[k] / ex_total["perfect"]
                          for k in ("yesterday", "last_week", "trailing7")},
        "loss_days_share": {k: float((ex_eval[k] < 0).mean())
                            for k in ("yesterday", "last_week", "trailing7")},
        "worst_day": {k: float(ex_eval[k].min()) for k in ("yesterday", "last_week", "trailing7")},
    }

    # ---------------------------------------------------------------- 5 quarter hour uplift
    qh_days = [(d, p) for d, p in days if pd.Timestamp(d, tz="Europe/Berlin") >= QH_START]
    r_qh = r_h = 0.0
    for d, p in qh_days:
        r_qh += solve_day(p, **BASE)[0]
        ph = np.repeat(p.reshape(-1, 4).mean(axis=1), 4)
        r_h += solve_day(ph, **BASE)[0]
    res["quarter_hour"] = {"days": len(qh_days), "rev_qh": r_qh, "rev_hourly": r_h,
                           "uplift": r_qh / r_h - 1}

    # ---------------------------------------------------------------- 6 storage as a shape hedge
    # Solar PPA scaled to 1 GWh per calendar year, pay as produced, hedged with a
    # volume matched monthly baseload sale. Shape P&L = sum v_t (p_t - monthly base).
    gen_year = df["solar"].groupby(df.index.year).sum()
    share_jan_oct = np.mean([df["solar"][(df.index.year == y) & (df.index.month <= 10)].sum()
                             / gen_year[y] for y in (2022, 2023, 2024, 2025)])
    scale = gen_year.copy().astype(float)
    scale[2026] = gen_year[2026] / share_jan_oct      # estimated full year 2026 output
    res["hedge_scaling"] = {"jan_oct_share_2022_2025": share_jan_oct,
                            "est_full_year_2026_twh": scale[2026] / 1e6}
    vol = df["solar"] / df.index.year.map(scale).values * 1000.0   # MWh, 1000 MWh per year
    base_m = df["price"].groupby(ym).transform("mean")
    shape = (vol * (df["price"] - base_m)).groupby(ym).sum()
    vol_m = vol.groupby(ym).sum()
    batt = pf["base"].groupby(pf.index.strftime("%Y-%m")).sum()
    hedge = pd.DataFrame({"shape_pnl": shape, "ppa_volume_mwh": vol_m, "battery_rev": batt})
    hedge["base"] = monthly["base"].astype(float)
    hedge["year"] = monthly["year"]
    hedge["moy"] = monthly["moy"]
    S, R = hedge["shape_pnl"], hedge["battery_rev"]

    def fit(mask):
        s, r = S[mask], R[mask]
        cov = np.cov(s, r, ddof=1)
        return {"n": int(mask.sum()), "corr": float(np.corrcoef(s, r)[0, 1]),
                "h": float(-cov[0, 1] / cov[1, 1])}

    all_m = pd.Series(True, index=hedge.index)
    train = hedge["year"] <= 2024
    test = hedge["year"] >= 2025
    full = fit(all_m)
    tr = fit(train)

    def var_red(mask, h):
        s, r = S[mask], R[mask]
        return float(1 - np.var(s + h * r, ddof=1) / np.var(s, ddof=1))

    # month of year demeaned (seasonality removed)
    Sd = S - S.groupby(hedge["moy"]).transform("mean")
    Rd = R - R.groupby(hedge["moy"]).transform("mean")
    # relative terms: shape P&L and battery revenue divided by the monthly base price
    Sr, Rr = S / hedge["base"], R / hedge["base"]
    res["hedge"] = {
        "full": full, "train_2022_2024": tr,
        "var_reduction_in_sample": var_red(all_m, full["h"]),
        "var_reduction_test_2025_2026": var_red(test, tr["h"]),
        "test_std_unhedged": float(np.std(S[test], ddof=1)),
        "test_std_hedged": float(np.std(S[test] + tr["h"] * R[test], ddof=1)),
        "corr_deseasonalised": float(np.corrcoef(Sd, Rd)[0, 1]),
        "corr_relative": float(np.corrcoef(Sr, Rr)[0, 1]),
        "corr_test": float(np.corrcoef(S[test], R[test])[0, 1]),
        "h_test_only": fit(test)["h"],
        "h_ex2022": fit(hedge["year"] >= 2023)["h"],
        "h_by_year": {int(y): fit(hedge["year"] == y)["h"] for y in sorted(hedge["year"].unique())},
    }
    # the same out of sample test on surprises: deviations from the calendar month means of 2022 to 2024
    mu_s = S[train].groupby(hedge.loc[train, "moy"]).mean()
    mu_r = R[train].groupby(hedge.loc[train, "moy"]).mean()
    s_dev = S[test] - hedge.loc[test, "moy"].map(mu_s)
    r_dev = R[test] - hedge.loc[test, "moy"].map(mu_r)
    res["hedge"]["var_reduction_test_deviations"] = float(
        1 - np.var(s_dev + tr["h"] * r_dev, ddof=1) / np.var(s_dev, ddof=1))
    hedge_annual = hedge.groupby("year")[["shape_pnl", "ppa_volume_mwh", "battery_rev"]].sum()
    hedge_annual["shape_eur_mwh"] = hedge_annual["shape_pnl"] / hedge_annual["ppa_volume_mwh"]

    # ---------------------------------------------------------------- write
    tables = {
        "annual": annual, "jan_oct": jan_oct, "summer_apr_sep": summer, "monthly": monthly,
        "hour_profile_rel": profile, "hour_profile_abs": prof_abs,
        "validation": validation, "wedge_monthly": wedge, "data_vintage": vint,
        "battery_pf_annual": pf_annual, "battery_pf_jan_oct": pf_jan_oct,
        "battery_days": ndays.to_frame("days"),
        "ex_ante_annual": ex_annual, "hedge_monthly": hedge, "hedge_annual": hedge_annual,
    }
    with pd.ExcelWriter(out / "results_tables.xlsx") as xw:
        for name, t in tables.items():
            t.to_excel(xw, sheet_name=name[:31])
    for name, t in tables.items():
        t.to_csv(out / f"{name}.csv")
    pf.to_csv(out / "battery_pf_daily.csv")
    ex.to_csv(out / "ex_ante_daily.csv")
    res["annual"] = json.loads(annual.to_json(orient="index"))
    res["battery_base"] = BASE
    (out / "results.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({k: v for k, v in res.items() if k != "annual"}, indent=1, default=float))
    pd.set_option("display.width", 250, "display.max_columns", 30)
    for n in ("annual", "jan_oct", "summer_apr_sep", "validation", "battery_pf_annual", "battery_pf_jan_oct",
              "ex_ante_annual", "hedge_annual"):
        print("\n==", n)
        print(tables[n].round(3))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
