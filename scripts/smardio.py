"""Readers for SMARD.de market data exports (Bundesnetzagentur, CC BY 4.0).

The three input files are standard SMARD "Marktdaten" CSV exports in original
resolution (quarter hour), semicolon separated, German number format,
timestamps in Europe/Berlin local time.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TZ = "Europe/Berlin"


def _num(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    s = s.where(s != "-", np.nan)
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def read_smard(path: Path, rename: dict) -> pd.DataFrame:
    raw = pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str)
    t = pd.to_datetime(raw["Datum von"], format="%d.%m.%Y %H:%M")
    # The export lists the repeated 02:00 hour of each autumn clock change day
    # only once. Comparison with UTC stamped pulls of the same series shows the
    # rows kept are the second occurrence (standard time, CET), so ambiguous
    # stamps are localised as CET; load_all fills the first occurrence.
    # A complete export lists it twice, in which case the order resolves it.
    try:
        idx = pd.DatetimeIndex(t).tz_localize(TZ, ambiguous="infer", nonexistent="raise")
    except ValueError:
        idx = pd.DatetimeIndex(t).tz_localize(
            TZ, ambiguous=np.zeros(len(t), dtype=bool), nonexistent="raise")
    out = pd.DataFrame(index=idx)
    for col in raw.columns[2:]:
        key = next((v for k, v in rename.items() if col.startswith(k + " [")), None)
        if key is not None:          # a full SMARD export has more columns; ignore them
            assert key not in out.columns, f"two columns match {key} in {path.name}"
            out[key] = _num(raw[col]).values
    assert set(out.columns) == set(rename.values()), f"columns missing in {path.name}"
    assert len(out.columns) == len(set(out.columns)), f"ambiguous columns in {path.name}"
    out.index.name = "time_berlin"
    return out


def load_all(raw_dir: Path, start: str, end: str, fill_csv: Path | None = None) -> pd.DataFrame:
    """Return a complete quarter hour panel [start, end) in Europe/Berlin time.

    If the exports lack the repeated hour of the autumn clock change days, the
    price for those quarter hours is taken from fill_csv (independent pulls of
    the same SMARD series) and generation and load are linearly interpolated
    between the neighbouring quarter hours. Both steps are counted in attrs.
    """
    price = read_smard(raw_dir / "DayAhead_Preise_aktuell.csv",
                       {"Deutschland/Luxemburg": "price"})
    gen = read_smard(raw_dir / "Realisierte_Erzeugung_Wind_PV_aktuell.csv",
                     {"Wind Offshore": "wind_off", "Wind Onshore": "wind_on",
                      "Photovoltaik": "solar"})
    # "Netzlast [MWh]" in current exports, "Gesamt (Netzlast) [MWh]" in older ones; the
    # separate column "Netzlast inkl. Pumpspeicher" is deliberately not matched
    load = read_smard(raw_dir / "Realisierter_Stromverbrauch_Netzlast_aktuell.csv",
                      {"Netzlast": "load", "Gesamt (Netzlast)": "load"})
    df = price.join(gen, how="outer").join(load, how="outer")
    s = pd.Timestamp(start, tz=TZ)
    e = pd.Timestamp(end, tz=TZ)
    df = df[(df.index >= s) & (df.index < e)]
    full = pd.date_range(s, e, freq="15min", inclusive="left")
    missing = full.difference(df.index)
    assert df.index.is_unique and df.index.is_monotonic_increasing
    assert len(df.index.difference(full)) == 0
    # only the repeated clock change hours (4 quarter hours per autumn) may be absent
    assert all((m.month == 10 and m.hour == 2) for m in missing), "unexpected gaps"
    df = df.reindex(full)
    df.index.name = "time_berlin"
    if len(missing):
        assert fill_csv is not None, "clock change hours missing and no fill file given"
        fill = pd.read_csv(fill_csv, parse_dates=["utc_start"]).set_index("utc_start")
        fill.index = fill.index.tz_convert(TZ)
        assert set(missing) <= set(fill.index)
        df.loc[missing, "price"] = fill.loc[missing, "price_eur_mwh"].values
        for col in ("wind_off", "wind_on", "solar", "load"):
            df[col] = df[col].interpolate(method="linear", limit=4, limit_area="inside")
    df.attrs["filled_quarter_hours"] = len(missing)
    return df


REV_START, REV_END = "2026-05-01", "2026-10-01"   # local months revised by SMARD after the export


def apply_smard_revisions(df: pd.DataFrame, ref_dir: Path) -> pd.DataFrame:
    """Bring May to September 2026 to SMARD's values as of 11 November 2026.

    The archived exports hold each day as SMARD published it shortly after delivery
    (as of 5 August 2026 for earlier days). SMARD later revised solar generation for
    May to September 2026 and grid load for May to August 2026. This step rescales the
    quarter hour values of those months so that
      * hourly solar totals equal SMARD's current hourly series; on days where that
        series still equals the old export although SMARD's daily total has changed
        (16 days in August 2026), the hourly values are scaled to the daily total;
      * monthly load totals equal SMARD's current monthly series.
    Skip this step when the inputs are a fresh first hand download.
    """
    df = df.copy()
    s, e = pd.Timestamp(REV_START, tz=TZ), pd.Timestamp(REV_END, tz=TZ)
    win = (df.index >= s) & (df.index < e)
    # ---- solar: current hourly values
    hourly = pd.read_csv(ref_dir / "smard_solar_hourly_2026-04-27_2026-10-04.csv",
                         index_col=0, parse_dates=True)["solar_mwh"]
    hourly.index = hourly.index.tz_convert(TZ)
    hourly = hourly[(hourly.index >= s) & (hourly.index < e)].copy()
    daily = pd.read_csv(ref_dir / "smard_solar_daily_2026-08.csv", index_col=0,
                        parse_dates=True)["solar_mwh"]
    daily.index = daily.index.tz_convert(TZ).normalize()
    day_sum = hourly.groupby(hourly.index.normalize()).sum()
    scaled_days = 0
    for day, total in daily.items():
        if abs(day_sum[day] - total) > 1.0:
            sel = hourly.index.normalize() == day
            hourly[sel] *= total / day_sum[day]
            scaled_days += 1
    hour_key = df.index[win].floor("h")
    old = df.loc[win, "solar"]
    old_hour = old.groupby(hour_key).transform("sum")
    target = hourly.reindex(hour_key)
    assert not target.isna().any(), "current hourly solar series does not cover the window"
    factor = np.where(old_hour.values > 0, target.values / np.where(old_hour.values > 0, old_hour.values, 1), 0.0)
    new = old.values * factor
    new = np.where(old_hour.values > 0, new, target.values / 4.0)
    df.loc[win, "solar"] = new
    # ---- load: current monthly totals
    monthly = pd.read_csv(ref_dir / "smard_monthly_totals_2026-11-11.csv", index_col=0)
    ym = df.index.strftime("%Y-%m")
    for m in pd.period_range(REV_START, "2026-09", freq="M").strftime("%Y-%m"):
        sel = ym == m
        df.loc[sel, "load"] *= monthly.loc[m, "load_mwh"] / df.loc[sel, "load"].sum()
        assert abs(df.loc[sel, "solar"].sum() - monthly.loc[m, "solar_mwh"]) < 1.0, m
    df.attrs["revised_window"] = f"{REV_START} to {REV_END} (exclusive)"
    df.attrs["solar_days_scaled_to_daily_total"] = scaled_days
    return df
