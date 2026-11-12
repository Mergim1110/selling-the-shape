"""Figures for the report. Greyscale, black text, one axis per panel."""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams.update({
    "font.family": "Liberation Sans", "font.size": 8.5, "text.color": "black",
    "axes.edgecolor": "black", "axes.labelcolor": "black", "xtick.color": "black",
    "ytick.color": "black", "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": 0.6, "grid.color": "0.85", "grid.linewidth": 0.5,
    "legend.frameon": False, "figure.dpi": 200, "savefig.bbox": "tight",
    "axes.titlesize": 9, "axes.titleweight": "bold", "axes.titlelocation": "left",
})
YEAR_STYLE = {2022: ("0.70", 1.0, (0, (1, 1))), 2023: ("0.55", 1.1, (0, (4, 2))),
              2024: ("0.40", 1.3, (0, (6, 1, 1, 1))), 2025: ("0.20", 1.6, "-"),
              2026: ("0.0", 2.2, "-")}


def main(out: Path, ref: Path):
    res = json.loads((out / "results.json").read_text())
    monthly = pd.read_csv(out / "monthly.csv", index_col=0)
    annual = pd.read_csv(out / "annual.csv", index_col=0)
    prof = pd.read_csv(out / "hour_profile_rel.csv", index_col=0)
    hedge = pd.read_csv(out / "hedge_monthly.csv", index_col=0)
    pf = pd.read_csv(out / "battery_pf_annual.csv", index_col=0)
    ex = pd.read_csv(out / "ex_ante_annual.csv", index_col=0)
    off = pd.read_csv(ref / "official_monthly_market_values.csv", index_col=0)
    fig_dir = out / "figures"
    fig_dir.mkdir(exist_ok=True)

    # ---- Figure 1: capture rate over time and against solar share
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.2, 2.55), gridspec_kw={"width_ratios": [1.25, 1]})
    x = pd.to_datetime(monthly.index + "-15")
    a.plot(x, monthly["capture_rate"] * 100, color="0.6", lw=0.9, label="Monthly")
    roll = (monthly["solar_capture"] * monthly["solar_twh"]).rolling(12).sum() / \
           monthly["solar_twh"].rolling(12).sum() / monthly["base"].rolling(12).apply(
               lambda v: np.average(v, weights=monthly.loc[v.index, "hours"]))
    a.plot(x, roll * 100, color="black", lw=2.0, label="Trailing 12 months")
    a.axhline(100, color="black", lw=0.5)
    a.set_ylabel("Solar capture rate, % of baseload")
    a.set_title("A. Capture rate")
    a.grid(axis="y")
    a.legend(loc="lower left")
    a.set_ylim(0, 115)
    xs, ys = monthly["solar_share_load"] * 100, monthly["capture_rate"] * 100
    mk = {2022: "o", 2023: "s", 2024: "^", 2025: "D", 2026: "x"}
    for y, g in monthly.groupby("year"):
        b.scatter(g["solar_share_load"] * 100, g["capture_rate"] * 100, s=16, marker=mk[y],
                  **({"color": "black"} if y == 2026 else
                     {"facecolors": "none", "edgecolors": "black"}),
                  linewidths=0.8, label=str(y))
    r = res["regression"]["pooled"]
    xx = np.array([xs.min(), xs.max()])
    b.plot(xx, r["intercept"] + r["slope"] * xx, color="black", lw=1.2)
    b.set_xlabel("Solar generation, % of grid load (month)")
    b.set_ylabel("Capture rate, %")
    b.set_title("B. Capture rate against solar share")
    b.grid(True)
    b.legend(loc="lower left", ncol=3, handletextpad=0.1, columnspacing=0.6, borderaxespad=0.2)
    b.set_ylim(0, 115)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig1_capture.png")
    plt.close(fig)

    # ---- Figure 2: intraday shape, April to September
    fig, a = plt.subplots(figsize=(7.2, 2.3))
    for y in prof.columns:
        c, lw, ls = YEAR_STYLE[int(y)]
        a.plot(prof.index + 0.5, prof[y] * 100, color=c, lw=lw, ls=ls, label=str(y))
    a.axhline(100, color="black", lw=0.5)
    a.set_xlim(0, 24)
    a.set_xticks(range(0, 25, 3))
    a.set_xlabel("Hour of day (local time)")
    a.set_ylabel("Mean price, % of period baseload")
    a.set_title("Average day ahead price by hour, April to September of each year")
    a.grid(axis="y")
    a.legend(loc="upper left", ncol=5)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig2_shape.png")
    plt.close(fig)

    # ---- Figure 3: realised capture price minus official market value
    j = monthly.join(off, how="inner")
    gap = j["solar_capture"] - j["official_solar_ct_kwh"] * 10
    fig, a = plt.subplots(figsize=(7.2, 2.4))
    xg = pd.to_datetime(j.index + "-15")
    a.bar(xg, gap, width=22, color="0.35", edgecolor="none")
    a.axhline(0, color="black", lw=0.6)
    a.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
    a.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    a.set_ylabel("EUR/MWh")
    a.set_title("Capture price on realised generation minus official market value solar, by month")
    a.grid(axis="y")
    fig.tight_layout()
    fig.savefig(fig_dir / "fig3_wedge.png")
    plt.close(fig)

    # ---- Figure 4: battery gross margin, perfect foresight against ex ante rule
    fig, a = plt.subplots(figsize=(7.2, 2.6))
    yrs = [str(y) for y in ex.index]
    xpos = np.arange(len(yrs))
    a.bar(xpos - 0.2, ex["perfect"] / 1000, width=0.38, color="0.75", label="Perfect foresight")
    a.bar(xpos + 0.2, ex["trailing7"] / 1000, width=0.38, color="0.15",
          label="Ex ante: schedule from the previous seven days")
    for i, y in enumerate(ex.index):
        a.text(i - 0.2, ex.loc[y, "perfect"] / 1000 + 1.5, f"{ex.loc[y, 'perfect'] / 1000:.0f}",
               ha="center", fontsize=7.5)
        a.text(i + 0.2, ex.loc[y, "trailing7"] / 1000 + 1.5, f"{ex.loc[y, 'trailing7'] / 1000:.0f}",
               ha="center", fontsize=7.5)
    a.set_xticks(xpos)
    a.set_xticklabels([{"2022": "2022 (from 8 Jan)", "2026": "2026 (Jan to Oct)"}.get(y, y) for y in yrs])
    a.set_ylabel("Thousand EUR per MW")
    a.set_title("Day ahead gross margin of a 1 MW, 2 MWh battery")
    a.grid(axis="y")
    a.legend(loc="upper center", ncol=2)
    a.set_ylim(0, 140)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig4_battery.png")
    plt.close(fig)

    # ---- Figure 5: storage as a shape hedge
    h_tr = res["hedge"]["train_2022_2024"]["h"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.2, 3.3))
    tr, te = hedge[hedge["year"] <= 2024], hedge[hedge["year"] >= 2025]
    a.scatter(tr["battery_rev"] / 1000, tr["shape_pnl"] / 1000, s=16, facecolors="none",
              edgecolors="black", linewidths=0.8, label="2022 to 2024 (fit)")
    a.scatter(te["battery_rev"] / 1000, te["shape_pnl"] / 1000, s=16, color="black",
              label="2025 to Oct 2026 (test)")
    xx = np.array([hedge["battery_rev"].min(), hedge["battery_rev"].max()]) / 1000
    icpt = tr["shape_pnl"].mean() / 1000 + h_tr * tr["battery_rev"].mean() / 1000
    a.plot(xx, icpt - h_tr * xx, color="black", lw=1.1)
    a.set_xlabel("Battery margin, thousand EUR per MW, month")
    a.set_ylabel("Shape P&L, thousand EUR per GWh/yr")
    a.set_title("A. Shape P&L against battery margin")
    a.grid(True)
    a.legend(loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=2, columnspacing=1.0)
    xt = pd.to_datetime(te.index + "-15")
    b.plot(xt, te["shape_pnl"] / 1000, color="0.6", lw=1.2, ls=(0, (4, 2)), label="Solar PPA shape P&L")
    b.plot(xt, (te["shape_pnl"] + h_tr * te["battery_rev"]) / 1000, color="black", lw=1.8,
           label=f"With {h_tr:.2f} MW of storage")
    b.axhline(0, color="black", lw=0.5)
    b.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
    b.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    b.set_xlabel("Month")
    b.set_ylabel("Thousand EUR per GWh/yr, month")
    b.set_title("B. Test period, 2025 to Oct 2026")
    b.grid(axis="y")
    b.legend(loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=2, columnspacing=1.0)
    fig.tight_layout()
    fig.savefig(fig_dir / "fig5_hedge.png")
    plt.close(fig)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
