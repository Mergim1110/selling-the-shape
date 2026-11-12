official_reference.csv
  Annual base price and negative hours: Bundesnetzagentur press releases on electricity market data
  of 4 Jan 2023, 3 Jan 2024, 3 Jan 2025 and 5 Jan 2026 (bundesnetzagentur.de).
  Annual market value solar (Jahresmarktwert Solar): transmission system operators, netztransparenz.de.
  2026 monthly rows: netztransparenz.de monthly values, see next file. Negative quarter hour counts for
  August and September 2026 as reported by pv magazine on 9 Sep and 9 Oct 2026.
official_monthly_market_values.csv
  Monthly market value solar and monthly spot price in ct/kWh, Jan 2023 to Oct 2026, published by the
  transmission system operators at netztransparenz.de. Two decimals as tabulated at
  https://www.green-2-market.de/marktwert-solar/ (retrieved there 21 Oct 2026). Three decimals where a
  report of the published value was available: Apr 2026 (1.317, solarserver.de 11 May 2026), May 2026
  (3.296), Aug to Oct 2026 (pv magazine 9 Sep, 9 Oct, 10 Nov 2026).
  May 2026 was first published as 3.163 ct/kWh (solarserver.de 8 Jun 2026) and later corrected to 3.296
  according to green-2-market.de. The corrected value is used.
clock_change_fill.csv
  Day ahead price for the first occurrence of the repeated 02:00 hour on autumn clock change days,
  which is absent from the archived exports. Values from independent pulls of the same SMARD series.
smard_hourly_price_from_oct2025.csv
  SMARD day ahead price in hourly resolution (SMARD interface, filter 4169, region DE-LU) from
  delivery day 1 Oct 2025, as pulled by https://github.com/sutheimernico/grid-scout (commit da185da).
  Used only to count negative hours the way SMARD and the Bundesnetzagentur do once prices are
  quarter hourly: an hour counts when its hourly resolution price is below zero.
smard_monthly_totals_2026-11-11.csv
  SMARD monthly totals of realised photovoltaic generation (filter 4068) and grid load (filter 410),
  region DE, read from the SMARD chart data interface on 11 Nov 2026, for example
  https://www.smard.de/app/chart_data/4068/DE/4068_DE_month_1767222000000.json (2026).
  Used to check the vintage of the archived exports and to rescale load for May to Sep 2026.
smard_solar_hourly_2026-04-27_2026-10-04.csv  (and live/w_<week start in ms>.txt, the raw weekly lists)
  SMARD hourly realised photovoltaic generation, weekly files
  https://www.smard.de/app/chart_data/4068/DE/4068_DE_hour_<week start in ms>.json, read 11 Nov 2026.
  Checks: the days of 27 to 30 Apr and 1 to 4 Oct equal the archived exports to the MWh, and the monthly
  sums for May, Jun, Jul and Sep equal SMARD's monthly totals within 0.2 MWh.
smard_solar_daily_2026-08.csv
  SMARD daily totals for August 2026 (4068_DE_day_1767222000000.json), read 11 Nov 2026. On 16 days
  (1 to 9 and 24 to 30 Aug) SMARD's hourly files still showed the first published values although the
  daily and monthly totals had been revised; for those days the hourly values are scaled to the daily total.
