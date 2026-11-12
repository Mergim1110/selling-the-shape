"""Cross check the primary SMARD exports against independent public pulls of the same series.

Usage: python crosscheck.py <raw dir> <ref dir> <mirrors dir> <out file>
The mirrors are third party GitHub repositories (see report appendix); this script only
documents the comparison and is not needed to reproduce the report.
"""
import sys
from pathlib import Path

import pandas as pd

from smardio import load_all

raw, ref, mir, outf = map(Path, sys.argv[1:5])
df = load_all(raw, "2022-01-01", "2026-11-01", ref / "clock_change_fill.csv")
pu = df["price"].copy()
pu.index = pu.index.tz_convert("UTC")
ph = pu.groupby(pu.index.floor("h")).mean()
lines = []


def cmp(name, a, x, tol):
    j = pd.concat([a, x], axis=1, join="inner").dropna()
    j.columns = ["a", "x"]
    d = (j.a - j.x).abs()
    lines.append(f"{name}: n={len(j)} from {j.index.min()} to {j.index.max()} | max abs diff {d.max():.4f} | "
                 f"n diff > {tol}: {(d > tol).sum()} | dates with diff: {sorted(set(d[d > tol].index.date))[:5]}")


b = pd.read_parquet(mir / "sutheimernico_grid-scout/data/price_day_ahead.parquet")
b.index = pd.to_datetime(b.timestamp_ms, unit="ms", utc=True)
cmp("hourly price vs grid-scout (SMARD API)", ph, b["value"], 0.0101)
d = pd.read_csv(mir / "AZFARHAD24511_germany-electricity-price-forecast/data/raw/germany_electricity_hourly.csv",
                index_col=0, parse_dates=True).iloc[:, 0]
cmp("hourly price vs AZFARHAD24511 pull", ph, d, 0.0101)
c = pd.read_csv(mir / "DataWithSyed_de-day-ahead-price-forecasting/data/de_lu_hourly.csv.gz",
                index_col=0, parse_dates=True)["price"]
cmp("hourly price vs Energy-Charts pull", ph, c, 0.0101)
q = pd.read_csv(mir / "DataWithSyed_de-bess-reserve-revenue-stacking/data/de_lu_da_15min.csv.gz",
                index_col=0, parse_dates=True)["price"]
cmp("quarter hour price vs Energy-Charts pull", pu, q, 0.0101)
for col, f in [("solar", "gen_solar"), ("load", "load")]:
    g = pd.read_parquet(mir / f"sutheimernico_grid-scout/data/{f}.parquet")
    g.index = pd.to_datetime(g.timestamp_ms, unit="ms", utc=True)
    a = df[col].copy()
    a.index = a.index.tz_convert("UTC")
    ah = a.groupby(a.index.floor("h")).sum()
    j = pd.concat([ah, g["value"]], axis=1, join="inner").dropna()
    j.columns = ["a", "x"]
    j = j[j.index < "2026-11-01"]
    mm = j[j.index >= "2026-01-01"]
    ratio_m = (mm.a.groupby(mm.index.strftime("%Y-%m")).sum() / mm.x.groupby(mm.index.strftime("%Y-%m")).sum())
    lines.append(f"{col} 2026 by month (UTC months), archive / grid-scout: {ratio_m.round(4).to_dict()}")
    lines.append(f"{col} hourly sum vs grid-scout: n={len(j)} from {j.index.min()} | ratio of totals {j.a.sum() / j.x.sum():.5f}"
                 f" | by year {(j.a.groupby(j.index.year).sum() / j.x.groupby(j.index.year).sum()).round(5).to_dict()}")
outf.write_text("\n".join(lines) + "\n")
print("\n".join(lines))
