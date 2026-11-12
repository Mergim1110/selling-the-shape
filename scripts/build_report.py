"""Build the PDF report. Every number in the text is read from the analysis output.

Usage: python build_report.py <out dir> <ref dir> <pdf path>
"""
import json
import sys
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

AS_OF = "11 November 2026"
TITLE = "Selling the Shape"
FONT_DIR = Path("/usr/share/fonts/truetype/liberation")
pdfmetrics.registerFont(TTFont("Body", str(FONT_DIR / "LiberationSans-Regular.ttf")))
pdfmetrics.registerFont(TTFont("Body-Bold", str(FONT_DIR / "LiberationSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("Body-Italic", str(FONT_DIR / "LiberationSans-Italic.ttf")))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body-Italic",
                              boldItalic="Body-Bold")
BLACK = colors.black
W = 170 * mm

body = ParagraphStyle("body", fontName="Body", fontSize=9.4, leading=12.6, textColor=BLACK,
                      alignment=TA_LEFT, spaceAfter=5)
small = ParagraphStyle("small", parent=body, fontSize=7.8, leading=10.2, spaceAfter=3)
h1 = ParagraphStyle("h1", parent=body, fontName="Body-Bold", fontSize=12.5, leading=15,
                    spaceBefore=9, spaceAfter=5, keepWithNext=1)
bullet = ParagraphStyle("bullet", parent=body, leftIndent=11, bulletIndent=0, spaceAfter=3.5)
cap = ParagraphStyle("cap", parent=small, fontName="Body-Bold", spaceBefore=4, spaceAfter=2)
cell = ParagraphStyle("cell", parent=body, fontSize=8.2, leading=10, spaceAfter=0)


def P(t, s=body):
    return Paragraph(t, s)


def B(t):
    return Paragraph(t, bullet, bulletText="•")


def n0(x):
    return f"{x:,.0f}"


def n1(x):
    return f"{x:,.1f}"


def n2(x):
    return f"{x:,.2f}"


def pct(x, d=0):
    return f"{100 * x:.{d}f}%"


def table(rows, widths, header_rows=1, align_first="LEFT", font=8.2):
    t = Table(rows, colWidths=widths, repeatRows=header_rows)
    st = [
        ("FONTNAME", (0, 0), (-1, -1), "Body"), ("FONTSIZE", (0, 0), (-1, -1), font),
        ("LEADING", (0, 0), (-1, -1), font + 2.2),
        ("TEXTCOLOR", (0, 0), (-1, -1), BLACK),
        ("FONTNAME", (0, 0), (-1, header_rows - 1), "Body-Bold"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, BLACK),
        ("LINEBELOW", (0, header_rows - 1), (-1, header_rows - 1), 0.5, BLACK),
        ("LINEBELOW", (0, -1), (-1, -1), 0.8, BLACK),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("ALIGN", (0, 0), (0, -1), align_first),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    t.setStyle(TableStyle(st))
    return t


def fig(path, width=W):
    from PIL import Image as PILImage
    with PILImage.open(path) as im:
        w, h = im.size
    return Image(str(path), width=width, height=width * h / w)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Body", 7.5)
    canvas.setFillColor(BLACK)
    if doc.page > 1:
        canvas.drawString(20 * mm, 11 * mm, f"{TITLE}   |   Mergim Manxholli   |   November 2026")
        canvas.drawRightString(190 * mm, 11 * mm, f"Page {doc.page}")
        canvas.setLineWidth(0.4)
        canvas.line(20 * mm, 14.5 * mm, 190 * mm, 14.5 * mm)
    canvas.restoreState()


def main(out: Path, ref: Path, pdf: Path):
    r = json.loads((out / "results.json").read_text())
    a = pd.read_csv(out / "annual.csv", index_col=0)
    jo = pd.read_csv(out / "jan_oct.csv", index_col=0)
    su = pd.read_csv(out / "summer_apr_sep.csv", index_col=0)
    m = pd.read_csv(out / "monthly.csv", index_col=0)
    val = pd.read_csv(out / "validation.csv", index_col=0)
    pfa = pd.read_csv(out / "battery_pf_annual.csv", index_col=0)
    ex = pd.read_csv(out / "ex_ante_annual.csv", index_col=0)
    exd = pd.read_csv(out / "ex_ante_daily.csv", index_col=0, parse_dates=True).iloc[7:]
    pfd = pd.read_csv(out / "battery_pf_daily.csv", index_col=0, parse_dates=True)
    hm = pd.read_csv(out / "hedge_monthly.csv", index_col=0)
    ha = pd.read_csv(out / "hedge_annual.csv", index_col=0)
    prof = pd.read_csv(out / "hour_profile_rel.csv", index_col=0)
    off = pd.read_csv(ref / "official_monthly_market_values.csv", index_col=0)
    ttm = r["ttm_nov25_oct26"]
    bt = r["battery_ttm_nov25_oct26"]
    reg = r["regression"]
    hd = r["hedge"]
    qh = r["quarter_hour"]
    exr = r["ex_ante"]
    oj = r["official_jan_oct"]
    o26 = {"solar_value_official_weighted": oj["2026"]["official_weighted"],
           "solar_value_calc": oj["2026"]["realised"]}
    wg = pd.read_csv(out / "wedge_monthly.csv", index_col=0)
    S = r["sample"]
    vt = r["vintage"]
    figs = out / "figures"

    # ------------------------------------------------------------ derived numbers
    cr = lambda y: a.loc[y, "capture_rate"]
    j = wg
    off_rate_25 = oj["2025"]["official_weighted"] / jo.loc[2025, "base"]
    off_rate_26 = oj["2026"]["official_weighted"] / jo.loc[2026, "base"]
    apr26 = m.loc["2026-04"]
    apr26_off = wg.loc["2026-04", "official_solar"]
    gap_year = r["wedge"]["mean_gap_by_year"]
    hy = hd["h_by_year"]
    curt = a["capture_if_curtailed"] - a["solar_capture"]
    h_tr = hd["train_2022_2024"]["h"]
    h_full = hd["full"]["h"]
    top_n = int(len(exd) * 0.1)
    top_share = exd["perfect"].sort_values(ascending=False).head(top_n).sum() / exd["perfect"].sum()
    best_day = pfd["base"].idxmax()
    ex_ratio = ex.div(ex["perfect"], axis=0)
    neg_months = int((hm["shape_pnl"] < 0).sum())
    seasonal_25 = a.loc[2025, "shape_discount"] + ha.loc[2025, "shape_eur_mwh"]
    base = r["battery_base"]
    assert base == {"power": 1.0, "hours": 2.0, "rte": 0.85, "cycles": 2.0}

    doc = SimpleDocTemplate(str(pdf), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=20 * mm, title=TITLE,
                            author="Mergim Manxholli",
                            subject="German solar capture prices, negative prices and storage as a shape hedge")
    s = []

    # ------------------------------------------------------------ cover
    s += [Spacer(1, 52 * mm),
          P(TITLE, ParagraphStyle("t", parent=body, fontName="Body-Bold", fontSize=30, leading=34)),
          Spacer(1, 4 * mm),
          P("What German solar really earns, what the capture rate hides, and how much of the "
            "exposure a two hour battery hedges",
            ParagraphStyle("st", parent=body, fontSize=14, leading=18)),
          Spacer(1, 3 * mm),
          P("Day ahead market, Germany and Luxembourg bidding zone, 1 January 2022 to 31 October 2026",
            ParagraphStyle("st2", parent=body, fontSize=10.5, leading=14)),
          Spacer(1, 70 * mm),
          P("Mergim Manxholli", ParagraphStyle("n", parent=body, fontName="Body-Bold", fontSize=13, leading=16)),
          P("MSc Sustainable Management and Technology (EPFL, HEC Lausanne, IMD)   |   CFA Level 2 Candidate",
            ParagraphStyle("n2", parent=body, fontSize=9.5)),
          P("November 2026", ParagraphStyle("n3", parent=body, fontSize=10.5)),
          Spacer(1, 30 * mm),
          P(f"Independent analysis based on public information as of {AS_OF}. Not investment advice.",
            ParagraphStyle("d", parent=body, fontSize=9)),
          PageBreak()]

    # ------------------------------------------------------------ summary
    s += [P("Summary", h1),
          P("<b>The question.</b> A desk that buys German solar output pay as produced and hedges it "
            "with baseload is short the shape: most of its volume arrives in the hours the market "
            "values least. This note measures how large that short has become, shows that the commonly "
            "quoted capture rate understates it, and tests how much of the exposure a two hour battery "
            "offsets. Everything is computed from public quarter hour data; prices and negative hour counts "
            "reproduce the official figures, and the code and result tables accompany the note."),
          P("<b>Five findings.</b>"),
          B(f"<b>Solar earns about half of baseload.</b> The capture price was {n2(a.loc[2025,'solar_capture'])} "
            f"EUR/MWh in 2025 against a baseload of {n2(a.loc[2025,'base'])}, a capture rate of {pct(cr(2025))}, "
            f"down from {pct(cr(2022))} in 2022. In January to October 2026 it was {pct(cr(2026))} "
            f"({pct(jo.loc[2025,'capture_rate'])} in the same months of 2025) with solar at "
            f"{pct(a.loc[2026,'solar_share_load'],1)} of grid load. Comparing like calendar months, one more "
            f"percentage point of solar share goes with a capture rate about "
            f"{abs(reg['month_fe_ex2022']['slope']):.1f} to {abs(reg['month_fe']['slope']):.1f} points lower, "
            f"depending on the sample."),
          B(f"<b>The quoted capture rate is probably flattered by curtailment.</b> Generation data leave out "
            f"output that is switched off when prices turn negative. The official market value of the "
            f"transmission system operators is by law computed on uncurtailed output, and since 2025 it has been "
            f"lower: by {n2(val.loc['2025','solar_calc'] - val.loc['2025','solar_official'])} EUR/MWh in 2025 and "
            f"by about {n1(apr26['solar_capture'] - apr26_off)} EUR/MWh in April 2026 "
            f"({n2(apr26['solar_capture'])} realised against {n2(apr26_off)} official)."),
          B(f"<b>Negative prices are structural, and zero is becoming a price level.</b> {n0(a.loc[2025,'neg_hours'])} "
            f"hours were negative in 2025 and {n0(a.loc[2026,'neg_hours'])} in the first ten months of 2026. "
            f"{pct(a.loc[2025,'solar_share_in_neg'])} of 2025 solar output was produced at negative prices. Time "
            f"spent at exactly 0.00 EUR/MWh rose from {n0(a.loc[2022,'zero_hours'])} hours in 2022 to "
            f"{n0(a.loc[2026,'zero_hours'])} hours in January to October 2026."),
          B(f"<b>A two hour battery earned {n0(pfa.loc[2025,'base']/1000)} thousand EUR per MW in 2025 on day ahead "
            f"alone,</b> and {n0(bt['base']/1000)} thousand in the twelve months to October 2026 (perfect foresight, "
            f"before all costs). A rule that needs no forecast, repeating the schedule that was optimal for the "
            f"average of the previous seven days, kept {pct(exr['capture_total']['trailing7'])} of the perfect "
            f"foresight margin over the whole sample. Quarter hour prices added {pct(qh['uplift'],1)} over their "
            f"hourly averages."),
          B(f"<b>Storage hedges the shape.</b> The monthly battery margin and the shape P&amp;L of a baseload hedged "
            f"solar PPA have a correlation of minus {abs(hd['full']['corr']):.2f}. A hedge ratio fitted on 2022 to "
            f"2024, {h_tr:.2f} MW of two hour storage per GWh of annual solar volume, cut the variance of the monthly "
            f"shape P&amp;L by {pct(hd['var_reduction_test_2025_2026'])} out of sample in 2025 to October 2026. "
            f"The ratio itself is not stable: across fitting windows of several years it lies between "
            f"{h_tr:.2f} and {hd['h_test_only']:.2f}, and wider on single years."),
          P("<b>What a desk can do with it.</b>"),
          B(f"Price pay as produced solar without curtailment rights against the official, uncurtailed market value, "
            f"not the realised capture price. In January to October 2026 that is roughly "
            f"{n1(o26['solar_value_official_weighted'])} against {n1(o26['solar_value_calc'])} EUR/MWh."),
          B(f"Treat storage capacity (owned or tolled) as a shape hedge and size it by hedge ratio, not one for one. "
            f"The estimates here run from roughly 0.45 to 0.75 MW of two hour storage per GWh of annual solar volume."),
          B("Run the battery on a transparent rule first. Most of the day ahead value does not depend on a price "
            "forecast, so forecasting effort is better spent on the tail days and on intraday."),
          P("<b>What this note does not do.</b> It covers the day ahead auction only, assumes a price taker, ignores "
            "battery degradation, grid charges, fees and capital cost, and uses the national solar profile rather than "
            "a single plant. Section 6 lists the limits in full. Assumptions are labelled where they are made.", body),
          PageBreak()]

    # ------------------------------------------------------------ 1 data
    s += [P("1. Data and validation", h1),
          P(f"All inputs are public. Day ahead prices for the Germany and Luxembourg bidding zone and realised solar "
            f"generation and grid load for Germany come from SMARD, the market data platform of the "
            f"Bundesnetzagentur (licence CC BY 4.0), in quarter hour resolution. The sample runs from 1 January 2022 to 31 October 2026: "
            f"{n0(S['quarter_hours'])} quarter hours, {n0(S['hours'])} hours, {n0(S['days'])} days. I used the SMARD "
            f"export files as archived daily in a public repository (state of 10 November 2026, Appendix B) and "
            f"checked them in four ways."),
          B(f"<b>Against SMARD directly, on 11 November 2026.</b> Monthly solar and load totals in the files match "
            f"SMARD's current monthly series in every month from January 2022 to April 2026 and in October 2026 "
            f"(solar within {n0(vt['max_abs_solar_diff_mwh_unrevised_months'])} MWh, load within 0.002%). SMARD has "
            f"since revised May to September 2026: monthly solar totals moved by between minus "
            f"{abs(min(vt['solar_rev_pct'].values())):.1f}% and plus {max(vt['solar_rev_pct'].values()):.1f}%, load "
            f"by up to minus {abs(min(vt['load_rev_pct'].values())):.1f}%. I brought these months to SMARD's current "
            f"values (note e)."),
          B("<b>Against independent pulls of the price series by other users.</b> Hourly prices agree to within one "
            "cent in every hour (two pulls cover the full sample, a third covers 2023 onward)."),
          B(f"<b>Against official annual figures</b> (Table 1). Baseload prices and negative hour counts reproduce "
            f"the Bundesnetzagentur numbers exactly in all four full years. Solar volumes for 2024 and 2025 are "
            f"within 0.5% of its latest annual figures ({n1(a.loc[2024,'solar_twh'])} TWh here against 63.2, and "
            f"{n1(a.loc[2025,'solar_twh'])} against 74.1)."),
          B(f"<b>Against official 2026 monthly figures.</b> The computed baseload for August, September and October "
            f"2026 is {n2(m.loc['2026-08','base'])}, {n2(m.loc['2026-09','base'])} and {n2(m.loc['2026-10','base'])} "
            f"EUR/MWh; the transmission system operators publish 126.89, 144.82 and 169.27. Negative quarter hours in "
            f"August and September are {n0(m.loc['2026-08','neg_quarter_hours'])} and "
            f"{n0(m.loc['2026-09','neg_quarter_hours'])} computed against 226 and 143 reported."),
          P("Table 1. Computed against official figures, EUR/MWh and hours", cap)]
    rows = [["Year", "Baseload,\nthis note", "Baseload,\nofficial", "Negative hours,\nthis note",
             "Negative hours,\nofficial", "Solar capture\n(realised)", "Market value\nsolar (official)",
             "Difference"]]
    for y in ("2022", "2023", "2024", "2025"):
        v = val.loc[y]
        d = v["solar_calc"] - v["solar_official"]
        rows.append([y, n2(v["base_calc"]), n2(v["base_official"]), n0(v["neg_hours_calc"]),
                     n0(v["neg_hours_official"]), n2(v["solar_calc"]), n2(v["solar_official"]),
                     ("plus " if d >= 0 else "minus ") + n2(abs(d))])
    s += [table(rows, [13 * mm, 20 * mm, 20 * mm, 25 * mm, 25 * mm, 23 * mm, 25 * mm, 19 * mm], font=7.8),
          P("Sources: Bundesnetzagentur press releases of 4 January 2023, 3 January 2024, 3 January 2025 and "
            "5 January 2026; annual market value solar of the transmission system operators (netztransparenz.de). "
            "The last two columns measure different things, see Section 3. The official annual spot value for 2024 is "
            "79.46 EUR/MWh against 78.51 on SMARD, which is consistent with the official values using the EPEX Spot "
            "prices of the decoupling day 26 June 2024 (note c); the 2024 row therefore compares slightly different "
            "price bases.", small),
          Spacer(1, 2 * mm),
          P("<b>Five data notes.</b> (a) The archived exports list the repeated hour of the five autumn clock change "
            f"days once. I filled the {S['filled_quarter_hours']} missing quarter hours of price from the independent "
            "pulls and interpolated generation and load linearly; it is night, so solar results are unaffected. "
            "(b) For delivery day 13 September 2026 the export carries hourly averages in place of quarter hour "
            "prices; the hourly means agree with the other pulls. (c) For 26 June 2024, when EPEX Spot was partially "
            "decoupled, SMARD shows the prices of the unaffected exchanges Nord Pool and EXAA; I keep that convention. "
            "(d) An hour counts as negative when its hourly price is below zero. From delivery day 1 October 2025 "
            "the auction clears quarter hours, and I take the hourly price from SMARD's own hourly series, because "
            "rounding the average of four quarter hours leaves ties. This reproduces the official counts for 2022 "
            "to 2025. (e) SMARD revises realised generation and load for months after delivery, and the archive "
            "holds each day as first published. For May to September 2026 I rescaled the quarter hour solar values "
            "so that every hourly total equals SMARD's current hourly value, and the load values so that monthly "
            f"totals equal SMARD's current monthly totals. On {S['solar_days_scaled_to_daily_total']} days in "
            "August, for which SMARD's hourly files still showed the old values while its daily totals had changed, "
            "I scaled the hourly values to the daily totals."),
          ]

    # ------------------------------------------------------------ 2 capture
    cols = [2022, 2023, 2024, 2025, 2026]
    hdr = ["", "2022", "2023", "2024", "2025", "2026\nJan to Oct", "12 months\nto Oct 2026"]

    def row(label, key, f):
        return [label] + [f(a.loc[y, key]) for y in cols] + [f(ttm[key])]

    rows = [hdr,
            row("Baseload price, EUR/MWh", "base", n2),
            row("Solar capture price, EUR/MWh", "solar_capture", n2),
            row("Capture rate", "capture_rate", lambda x: pct(x, 1)),
            row("Discount to baseload, EUR/MWh", "shape_discount", n2),
            row("Solar generation, TWh", "solar_twh", n1),
            row("Solar share of grid load", "solar_share_load", lambda x: pct(x, 1)),
            row("Negative hours", "neg_hours", n0),
            row("Share of solar output at negative prices", "solar_share_in_neg", lambda x: pct(x, 1)),
            row("Time at exactly 0.00 EUR/MWh, hours", "zero_hours", n0)]
    s += [P("2. What solar earns", h1),
          P("The capture price is the generation weighted average day ahead price of national solar output; the "
            "capture rate divides it by the time weighted average price (baseload). Table 2 gives both by year."),
          P("Table 2. German solar in the day ahead market", cap),
          table(rows, [58 * mm, 17 * mm, 17 * mm, 17 * mm, 17 * mm, 21 * mm, 23 * mm]),
          P("Source: own calculation from SMARD data. Realised generation; see Section 3 for the official, "
            "uncurtailed measure. The discount is computed from unrounded values. Time at zero is the number of "
            "quarter hours at 0.00 divided by four.", small),
          Spacer(1, 2 * mm),
          P(f"<b>Level.</b> The capture rate fell from {pct(cr(2022))} in 2022 to {pct(cr(2025))} in 2025 while solar "
            f"output rose from {n1(a.loc[2022,'solar_twh'])} to {n1(a.loc[2025,'solar_twh'])} TWh (Figure 1A). The "
            f"discount to baseload widened every year, from {n2(a.loc[2022,'shape_discount'])} to "
            f"{n2(a.loc[2025,'shape_discount'])} EUR/MWh, and to {n2(a.loc[2026,'shape_discount'])} in January to "
            f"October 2026."),
          fig(figs / "fig1_capture.png"),
          P("Figure 1. Solar capture rate by month and on a trailing twelve month basis (A), and monthly capture rate "
            "against solar share of grid load with the pooled regression line (B). Source: own calculation from "
            "SMARD data.", small),
          P(f"<b>How much per point of solar.</b> Across the {reg['n']} months a pooled regression of capture rate on "
            f"solar share of load has a slope of minus {abs(reg['pooled']['slope']):.1f} points per point of share "
            f"(R squared {reg['pooled']['r2']:.2f}, Figure 1B). Sunny months are also low demand months, so I add "
            f"calendar month dummies, which compares each June only with other Junes. The slope steepens to minus "
            f"{abs(reg['month_fe']['slope']):.1f} (Newey West standard error {reg['month_fe']['se']:.1f}), and to "
            f"minus {abs(reg['month_fe_ex2022']['slope']):.1f} when 2022 is left out. With so few observations the "
            f"standard error is approximate, and this is an association, not a structural estimate: gas prices, "
            f"wind, demand and storage are not controlled for."),
          P(f"<b>Season and hour.</b> In April to September the rate was {pct(su.loc[2025,'capture_rate'])} in 2025 "
            f"and {pct(su.loc[2026,'capture_rate'])} in 2026. The weakest month in the sample is April 2026 at "
            f"{pct(apr26['capture_rate'])} ({n2(apr26['solar_capture'])} against {n2(apr26['base'])} EUR/MWh). "
            f"Figure 2 shows why: in April to September 2022 the average price between 13:00 and 14:00 was "
            f"{pct(prof.loc[13,'2022'])} of baseload; in 2025 it was {pct(prof.loc[13,'2025'])} and in 2026 "
            f"{pct(prof.loc[13,'2026'])}. Over the same years the 20:00 to 21:00 price went from "
            f"{pct(prof.loc[20,'2022'])} to {pct(prof.loc[20,'2025'])} and {pct(prof.loc[20,'2026'])} of baseload."),
          fig(figs / "fig2_shape.png"),
          P("Figure 2. Average day ahead price by hour of day in April to September, as a percentage of the average "
            "price of the same period. Source: own calculation from SMARD data.", small),
          P(f"<b>2026.</b> The price level is higher: baseload averaged {n2(jo.loc[2026,'base'])} EUR/MWh in January "
            f"to October against {n2(jo.loc[2025,'base'])} in the same months of 2025. Gas was also expensive: "
            f"the TTF price briefly reached 100 EUR/MWh at the end of October, for the first time since "
            f"December 2022. The capture rate for the same ten months moved from "
            f"{pct(jo.loc[2025,'capture_rate'],1)} to {pct(jo.loc[2026,'capture_rate'],1)} although solar share rose "
            f"from {pct(jo.loc[2025,'solar_share_load'],1)} to {pct(jo.loc[2026,'solar_share_load'],1)}. I do not "
            f"attribute that move here. The next section shows that part of it is a measurement effect.")]

    # ------------------------------------------------------------ 3 curtailment
    s += [P("3. What the capture rate hides", h1),
          P("Section 2 weights prices with realised generation. A plant that switches off when the price is negative "
            "produces nothing in that hour, so its lost volume drops out of the average and the capture price looks "
            "better than the value of the underlying resource. The official market value solar published by the "
            "transmission system operators is defined differently. Under Annex 1 number 5.1 of the Renewable Energy "
            "Sources Act (EEG 2023), the generation estimate behind it must disregard reductions of feed in by the "
            "grid operator or in direct marketing. It is the value of uncurtailed output."),
          P(f"From 2022 to 2024 the two measures differed by less than 1 EUR/MWh in every year, in both directions "
            f"(Table 1). In 2022, a year with almost no negative prices, the official value was "
            f"{n2(val.loc['2022','solar_official'] - val.loc['2022','solar_calc'])} higher, so gaps of that size also "
            f"arise from measurement alone. Since 2025 the realised figure has been higher and the gap has grown "
            f"(Figure 3): the monthly gap averaged {n1(gap_year['2025'])} EUR/MWh in 2025 and {n1(gap_year['2026'])} "
            f"in January to October 2026, with about {n1(j.loc['2026-04','gap'])} in April "
            f"({n2(apr26['solar_capture'])} realised against {n2(apr26_off)} official) and about "
            f"{n1(j.loc['2026-05','gap'])} in May. Weighting the official monthly values for January to October 2026 "
            f"with monthly solar volumes gives about {n1(o26['solar_value_official_weighted'])} EUR/MWh, against "
            f"{n1(o26['solar_value_calc'])} on realised generation. On that basis the capture rate for the ten months "
            f"is about {pct(off_rate_26)} and not {pct(jo.loc[2026,'capture_rate'])}, and its rise from the same "
            f"months of 2025 is smaller (from about {pct(off_rate_25,1)} to {pct(off_rate_26,1)})."),
          fig(figs / "fig3_wedge.png"),
          P("Figure 3. Capture price on realised generation (this note) minus official monthly market value solar "
            "(transmission system operators, two or three decimals in ct/kWh), January 2023 to October 2026. The one large "
            "negative value, June 2024, coincides with the partial decoupling of 26 June 2024, for which SMARD does "
            "not show the EPEX Spot auction prices. The official value for May 2026 was first published as 3.163 "
            f"ct/kWh and later corrected to 3.296; I use the corrected value. With the first value the ten month "
            f"figure would be {n1(oj['2026_with_first_may_value'])} EUR/MWh. Sources: own calculation from SMARD "
            "data; netztransparenz.de.", small),
          P("<b>Reading.</b> I read the widening gap as mostly economic curtailment. Three facts point that way. Since "
            "25 February 2025 newly commissioned plants as a rule receive no support payment for periods of negative "
            "prices, which gives them a reason to stop at zero. Time spent at exactly 0.00 EUR/MWh has multiplied "
            f"(Table 2): {n0(a.loc[2022,'zero_hours'])} hours in 2022, {n0(a.loc[2024,'zero_hours'])} in 2024, "
            f"{n0(a.loc[2025,'zero_hours'])} in 2025 and {n0(a.loc[2026,'zero_hours'])} in ten months of 2026. And "
            f"across the {r['wedge']['n']} months of Figure 3 the gap has a correlation of "
            f"{r['wedge']['corr_gap_neg_share']:.2f} with the share of solar output produced at negative prices. "
            "The attribution remains an interpretation: the two generation series are also measured differently, "
            "and from June to September 2026 the gap stayed near 2 EUR/MWh whatever the negative price exposure, "
            "which curtailment alone does not explain."),
          P(f"<b>Why it matters for pricing.</b> The right benchmark depends on the contract. A pay as produced PPA "
            f"that obliges the buyer to take every MWh is worth the official, uncurtailed value. A contract that lets "
            f"the buyer switch the plant off at negative prices is worth more: flooring each quarter hour price at "
            f"zero lifts the 2025 capture price from {n2(a.loc[2025,'solar_capture'])} to "
            f"{n2(a.loc[2025,'capture_if_curtailed'])} EUR/MWh, a gain of about {n1(curt[2025])}, and the January to "
            f"October 2026 figure by about {n1(curt[2026])}. Because the realised series already misses curtailed volume, these "
            f"gains are lower bounds on the value of the curtailment right.")]

    # ------------------------------------------------------------ 4 battery
    order = [("1h_1c", "1 hour, 1 cycle a day"), ("1h_2c", "1 hour, 2 cycles"),
             ("2h_1c", "2 hours, 1 cycle"), ("2h_2c", "2 hours, 2 cycles (base case)"),
             ("4h_1c", "4 hours, 1 cycle"), ("4h_2c", "4 hours, 2 cycles"),
             ("rte80", "Base case at 80% efficiency"), ("rte90", "Base case at 90% efficiency")]
    rows = [["Storage duration and cycle cap", "2022", "2023", "2024", "2025", "12 months\nto Oct 2026"]]
    for k, lab in order:
        rows.append([lab] + [n1(pfa.loc[y, k] / 1000) for y in (2022, 2023, 2024, 2025)] + [n1(bt[k] / 1000)])
    rows2 = [["Rule", "2022", "2023", "2024", "2025", "2026\nJan to Oct", "All days"]]
    for k, lab in (("yesterday", "Yesterday's optimal schedule"),
                   ("last_week", "Schedule of the same weekday last week"),
                   ("trailing7", "Schedule for the mean of the previous seven days")):
        rows2.append([lab] + [pct(ex_ratio.loc[y, k]) for y in cols] + [pct(exr["capture_total"][k])])
    s += [P("4. What a battery earns from the same shape", h1),
          P("The midday trough and evening peak that hurt solar are what storage is paid for. I value a battery "
            "against the same day ahead prices with a daily dispatch optimisation. <b>Assumptions:</b> 1 MW of power "
            "and 2 MWh of energy; round trip efficiency 85%, split equally between charging and discharging (the "
            "value assumed in the Annual Technology Baseline 2025 of the United States national laboratory NREL, "
            "now NLR); at "
            "most two full cycles a day; every delivery day starts and ends empty, so each schedule could be "
            "submitted in a single auction; price taker; day ahead auction only. Results are gross margins before "
            "degradation, grid charges, fees, operating and capital cost. On days with negative prices the solver "
            "forbids charging and discharging at the same time."),
          P("Table 3. Day ahead gross margin with perfect foresight, thousand EUR per MW of power", cap),
          table(rows, [62 * mm, 21 * mm, 21 * mm, 21 * mm, 21 * mm, 24 * mm]),
          P("Source: own calculation from SMARD data. Calendar years; last column 1 November 2025 to 31 October 2026.",
            small),
          Spacer(1, 2 * mm),
          P(f"<b>Level and sensitivities.</b> The base case earned {n1(pfa.loc[2025,'base']/1000)} thousand EUR per MW "
            f"in 2025 and {n1(bt['base']/1000)} thousand in the twelve months to October 2026. Limiting it to one "
            f"cycle a day costs {pct(1 - pfa.loc[2025,'2h_1c']/pfa.loc[2025,'base'])} of the 2025 margin. Doubling "
            f"the energy to four hours adds {pct(pfa.loc[2025,'4h_2c']/pfa.loc[2025,'base'] - 1)}, well short of "
            f"double. The margin is concentrated: the best tenth of days delivers {pct(top_share)} of it, and the "
            f"best single day, {best_day.day} {best_day.strftime('%B %Y')}, earned {n0(pfd['base'].max())} EUR per MW."),
          P(f"<b>Quarter hour products.</b> Since delivery day 1 October 2025 the auction clears 96 quarter hours "
            f"a day. Over the {qh['days']} days to 31 October 2026 the base case earned {n1(qh['rev_qh']/1000)} "
            f"thousand EUR per MW on quarter hour prices and {n1(qh['rev_hourly']/1000)} thousand on their hourly "
            f"averages, an uplift of {pct(qh['uplift'],1)}. Hourly averages of quarter hour prices are not the prices "
            f"an hourly auction would have produced, so this is an indication, not a counterfactual."),
          P(f"<b>How much needs a forecast.</b> Perfect foresight is an upper bound. As a simple benchmark I test "
            f"three rules that use no forecast at all. Each takes a schedule that was optimal on past prices, which are "
            f"known before bids for the next day are due, and submits it unchanged as volume. Table 4 shows the share "
            f"of the perfect foresight margin each one kept. The best, the schedule for the mean price shape of the "
            f"previous seven days, kept {pct(exr['capture_total']['trailing7'])} overall and lost money on "
            f"{pct(exr['loss_days_share']['trailing7'],1)} of days, the worst day costing "
            f"{n0(abs(exr['worst_day']['trailing7']))} EUR per MW (Figure 4). The share rose from "
            f"{pct(ex_ratio.loc[2022,'trailing7'])} in 2022 to {pct(ex_ratio.loc[2026,'trailing7'])} in 2026, which "
            f"is consistent with a daily shape that solar makes more regular."),
          P("Table 4. Share of the perfect foresight margin kept by rules that use no forecast, base case", cap),
          table(rows2, [62 * mm, 17 * mm, 17 * mm, 17 * mm, 17 * mm, 21 * mm, 19 * mm]),
          P(f"Source: own calculation from SMARD data. Evaluation from 8 January 2022 ({n0(exr['eval_days'])} days). "
            f"The rules stay idle on clock change days; the first two also when their reference day has a "
            f"different length, while the third averages the remaining days ({exr['idle_days']['yesterday']}, "
            f"{exr['idle_days']['last_week']} and {exr['idle_days']['trailing7']} idle days). Before October 2025 "
            f"hourly prices repeat across quarter hours, so optimal schedules are not unique and the first two "
            f"rows can move by about a tenth of a point with the solver.", small),
          Spacer(1, 2 * mm),
          fig(figs / "fig4_battery.png"),
          P("Figure 4. Day ahead gross margin of the base case battery with perfect foresight and under the seven day "
            "rule. Evaluation from 8 January 2022. Source: own calculation from SMARD data.", small)]

    # ------------------------------------------------------------ 5 hedge
    rows = [["", "2022", "2023", "2024", "2025", "2026\nJan to Oct"],
            ["Discount to period baseload, EUR/MWh"] + [n2(a.loc[y, "shape_discount"]) for y in cols],
            ["Within month shape cost, EUR/MWh"] + [n2(-ha.loc[y, "shape_eur_mwh"]) for y in cols],
            ["Shape cost, thousand EUR per GWh/yr"] + [n1(-ha.loc[y, "shape_pnl"] / 1000) for y in cols],
            ["Battery margin, thousand EUR per MW"] + [n1(ha.loc[y, "battery_rev"] / 1000) for y in cols],
            [f"Margin of {h_tr:.3f} MW, thousand EUR"] + [n1(h_tr * ha.loc[y, "battery_rev"] / 1000) for y in cols]]
    s += [P("5. Storage as a shape hedge", h1),
          P("<b>The position.</b> Take a pay as produced solar PPA that follows the national profile and delivers "
            "1 GWh per calendar year. Hedge the price level by selling monthly baseload in the same volume. What "
            "remains is the shape P&amp;L: the sum over all quarter hours of volume times the difference between the "
            f"price and the monthly baseload price. It was negative in {neg_months} of {len(hm)} months. "
            "<b>The instrument</b> is the day ahead gross margin of the base case battery in the same month. Both "
            "are driven by the gap between midday and evening prices, with opposite sign."),
          P("Table 5. Shape cost of the solar PPA and battery margin by year", cap),
          table(rows, [62 * mm, 21 * mm, 21 * mm, 21 * mm, 21 * mm, 24 * mm]),
          P("Source: own calculation from SMARD data. The 2026 volume is scaled with the average January to October "
            f"share of annual solar output in 2022 to 2025 ({pct(r['hedge_scaling']['jan_oct_share_2022_2025'],1)}), "
            "an estimate that affects scale only. The first row repeats Table 2.", small),
          Spacer(1, 2 * mm),
          P(f"<b>Two components of the discount.</b> Of the {n2(a.loc[2025,'shape_discount'])} EUR/MWh discount to "
            f"annual baseload in 2025, {n2(-ha.loc[2025,'shape_eur_mwh'])} is shape within the month. The remaining "
            f"{n2(seasonal_25)} is seasonal, because solar delivers more in months with lower prices, and can be "
            f"hedged with monthly products. The within month part cannot be hedged with baseload at all."),
          P(f"<b>The hedge.</b> Across all {hd['full']['n']} months the correlation between shape P&amp;L and battery "
            f"margin is minus {abs(hd['full']['corr']):.2f}. The variance minimising hedge ratio fitted on 2022 to "
            f"2024 is {h_tr:.2f} MW of two hour storage per GWh of annual solar volume. Applied unchanged to 2025 to "
            f"October 2026, it lowers the standard deviation of the monthly shape P&amp;L from "
            f"{n0(hd['test_std_unhedged'])} to {n0(hd['test_std_hedged'])} EUR per GWh/yr, a variance reduction of "
            f"{pct(hd['var_reduction_test_2025_2026'])} (Figure 5)."),
          P(f"<b>The ratio is a range.</b> Fitted on the full sample it is {h_full:.2f}, on 2025 to October 2026 "
            f"alone {hd['h_test_only']:.2f}, and on single years between {min(hy.values()):.2f} and "
            f"{max(hy.values()):.2f}. In EUR terms it depends on the price regime, and the high battery margins of "
            f"2022 pull the first estimate down. I read it as roughly 0.45 to 0.75 MW per GWh of annual volume. "
            f"As a rule of thumb, 1 GWh a year is about 1 MW of solar capacity in Germany (assumption: about 1,000 "
            f"full load hours), so the hedge is roughly half to three quarters of a MW of two hour storage per MW "
            f"of solar."),
          fig(figs / "fig5_hedge.png"),
          P("Figure 5. Monthly shape P&amp;L of a 1 GWh per year solar PPA against battery margin, with the hedge "
            "line fitted on 2022 to 2024 (A), and the shape P&amp;L in the test period with and without the hedge (B). "
            "Source: own calculation from SMARD data.", small),
          P(f"<b>Robustness.</b> Both series are seasonal and both scale with the price level, which could "
            f"manufacture a correlation. After removing calendar month averages the correlation is minus "
            f"{abs(hd['corr_deseasonalised']):.2f}; after dividing both series by the monthly baseload price it is "
            f"minus {abs(hd['corr_relative']):.2f}; in the test period alone it is minus {abs(hd['corr_test']):.2f}. "
            f"Measured on surprises, that is deviations from the calendar month averages of 2022 to 2024, the same "
            f"{h_tr:.2f} MW cut the variance of the shape P&amp;L in the test period by "
            f"{pct(hd['var_reduction_test_deviations'])}."),
          P(f"<b>What the hedge is and is not.</b> It offsets risk, it is not free money. Table 5 shows that the "
            f"gross margin of {h_tr:.3f} MW was of the same order as the shape cost in every year, but that margin is "
            f"before the cost of owning or tolling the battery, and the battery line in Figure 5 uses perfect "
            f"foresight (Section 4 puts a simple rule at {pct(exr['capture_total']['trailing7'])} of it). The useful "
            f"statement for a desk is narrower: when the shape cost of a solar book rises above its seasonal norm, a "
            f"storage position of this size has earned more in the same month, in sample and out of sample.")]

    # ------------------------------------------------------------ 6 use and limits
    s += [P("6. Use on a desk, and limits", h1),
          B("<b>Quoting solar PPAs.</b> State which capture measure a price refers to. For January to October 2026 the "
            f"realised and the uncurtailed measure differ by about "
            f"{n1(o26['solar_value_calc'] - o26['solar_value_official_weighted'])} EUR/MWh, and by far more in spring."),
          B("<b>Structuring.</b> A curtailment right at negative prices has a measurable floor value "
            f"(about {n1(curt[2025])} EUR/MWh in 2025). With time at zero multiplying, the strike of that right, zero or "
            "slightly below, starts to matter."),
          B("<b>Hedging.</b> Size storage against a solar book by hedge ratio. One for one pairing in MW is above "
            "every estimate found here."),
          B("<b>Monitoring.</b> Three series are cheap to track and carry the story: time at exactly zero, the gap "
            "between realised and official capture, and the 20:00 price relative to baseload."),
          P("<b>Limits.</b>"),
          B("Day ahead only. Intraday and balancing markets, which add to battery value and to solar balancing cost, "
            "are outside the scope."),
          B("Price taker. 1 MW does not move the auction; a fleet does, and more storage will compress the spread it "
            "earns and narrow the solar discount it hedges. History cannot show that."),
          B("National profile, perfect volume. A single plant has its own profile, forecast error and outages; "
            "volume risk and balancing cost are excluded."),
          B("Gross margins. No degradation, grid charges, fees, taxes or capital cost, so nothing here says whether "
            "a battery is a good investment."),
          B(f"Short and unusual sample. {len(hm)} months that include the 2022 crisis and the 2026 rise in gas prices. The "
            f"hedge ratio moved between {h_tr:.2f} and {hd['h_test_only']:.2f} across fitting windows of several "
            f"years ({min(hy.values()):.2f} to {max(hy.values()):.2f} on single years) and should be read as a "
            f"range."),
          B("Realised generation. Capture measures in Sections 2 and 5 inherit the curtailment bias described in "
            "Section 3, so shape costs for a profile that cannot be curtailed are understated.")]

    # ------------------------------------------------------------ appendix
    s += [P("Appendix A. Method", h1),
          P("<b>Time.</b> All series are quarter hourly in local time (Europe/Berlin). Before 1 October 2025 the "
            "hourly auction price is repeated for the four quarter hours of the hour. Years and months are local "
            "calendar periods.", small),
          P("<b>Capture measures.</b> Baseload is the simple average of quarter hour prices. The capture price is the "
            "sum of price times solar generation divided by the sum of solar generation. Solar share is solar "
            "generation divided by grid load. The curtailed variant replaces each price by the larger of the price "
            "and zero and keeps the same denominator. An hour is negative when its hourly price is below zero; from "
            "1 October 2025 the hourly price is SMARD's hourly resolution series.", small),
          P("<b>Regression.</b> Ordinary least squares of the monthly capture rate (percent) on the monthly solar "
            "share of load (percent), with and without eleven calendar month dummies. Standard errors are Newey West "
            "with three lags.", small),
          P("<b>Battery.</b> For each delivery day, choose charge and discharge power per quarter hour to maximise "
            "the sum of price times net discharge, subject to the power limit, the state of charge staying between "
            "zero and the energy capacity, charging and discharging efficiency equal to the square root of the round "
            "trip efficiency, an empty battery at the start and end of the day, and discharge throughput of at most "
            "the cycle cap times the energy capacity. Linear programme solved with HiGHS; days on which the linear "
            "solution charges and discharges at once are solved again as a mixed integer programme with one binary "
            "variable per quarter hour.", small),
          P("<b>Rules without forecast.</b> For day D the rule takes the optimal schedule of day D minus 1, of day "
            "D minus 7, or of the average price vector of days D minus 7 to D minus 1, and settles it at the prices of "
            "day D. All of these are known when bids for D are due.", small),
          P("<b>Hedge.</b> Volume per quarter hour is national solar generation divided by the calendar year total "
            "and multiplied by 1,000 MWh. Shape P&amp;L per month is the sum of volume times (price minus monthly "
            "baseload). The hedge ratio is minus the covariance of shape P&amp;L and battery margin divided by the "
            "variance of battery margin. The variance reduction in the test period is one minus the variance of "
            "shape P&amp;L plus hedge ratio times battery margin, divided by the variance of shape P&amp;L.", small),
          P("Appendix B. Sources", h1),
          P("All sources were accessed on 10 or 11 November 2026.", small)]
    src = [
        "Bundesnetzagentur, SMARD.de market data: day ahead prices for the Germany and Luxembourg bidding zone, "
        "realised generation and realised grid load for Germany; quarter hour resolution; licence CC BY 4.0. "
        "Current monthly, daily and hourly values for the vintage check and the 2026 revisions read from the SMARD "
        "chart data interface (smard.de/app/chart_data) on 11 November 2026. Export files as archived "
        "at https://github.com/henriklinkehl-blip/SMARD_Data, commit 92a2952 of 10 November 2026.",
        "Independent pulls used for cross checks, and the first also for the hourly price series behind the negative "
        "hour counts from October 2025: https://github.com/sutheimernico/grid-scout (SMARD interface, "
        "commit da185da of 10 November 2026); "
        "https://github.com/AZFARHAD24511/germany-electricity-price-forecast (commit 66495bb of 10 November 2026); "
        "https://github.com/DataWithSyed/de-day-ahead-price-forecasting and "
        "https://github.com/DataWithSyed/de-bess-reserve-revenue-stacking (Energy Charts interface of Fraunhofer ISE, "
        "state of 8 November 2026).",
        "Bundesnetzagentur, press releases on electricity market data of 4 January 2023, 3 January 2024, "
        "3 January 2025 and 5 January 2026 (bundesnetzagentur.de): annual average day ahead price and number of "
        "negative hours.",
        "Transmission system operators, netztransparenz.de, market value overview: annual market value solar 2025 "
        "(4.508 ct/kWh) read from the site; 2022 to 2024 (22.306, 7.200 and 4.624 ct/kWh) and the annual spot value "
        "2024 (7.946 ct/kWh) as reproduced by the German Solar Energy Society DGS (dgs.de); monthly values January 2023 to September 2026 as tabulated at "
        "https://www.green-2-market.de/marktwert-solar/ (retrieved there 21 October 2026), which also documents "
        "the correction of the May 2026 value; April 2026 value (1.317 ct/kWh) as reported by solarserver.de on "
        "11 May 2026; August, September and October 2026 values and the negative quarter hour counts for August "
        "and September as reported by pv magazine on 9 September, 9 October and 10 November 2026.",
        "Renewable Energy Sources Act (EEG 2023), Annex 1 number 5.1: reductions of feed in by the grid operator or "
        "in direct marketing are to be disregarded in the online extrapolation of generation.",
        "Act amending energy industry law to avoid temporary generation surpluses (so called Solarspitzengesetz), in "
        "force since 25 February 2025: no support payment at negative prices for newly commissioned plants "
        "(pv magazine, 24 February 2025).",
        "EPEX Spot, press release of 30 September 2025: quarter hour products live in the coupled day ahead auction, "
        "first delivery day 1 October 2025.",
        "SMARD, article on the electricity market in the second quarter of 2024: for delivery day 26 June 2024 the "
        "prices of the exchanges EXAA and Nord Pool are shown.",
        "NREL (now NLR), Annual Technology Baseline 2025, utility scale battery storage (atb.nlr.gov): round trip "
        "efficiency of 85%.",
        "Gas price in 2026: stromauskunft.de, 30 October 2026 (TTF briefly at 100 EUR/MWh, the highest since "
        "December 2022).",
    ]
    for i, t in enumerate(src, 1):
        s.append(P(f"{i}. {t}", small))
    s += [Spacer(1, 3 * mm),
          P("Software: Python with pandas, statsmodels, SciPy and the HiGHS solver; figures with matplotlib. The "
            "accompanying files contain the input data, the code and every table behind the numbers in this note.",
            small)]

    # keep each table with its caption and note, and each figure with its caption
    grouped, i = [], 0
    while i < len(s):
        x = s[i]
        if isinstance(x, Paragraph) and x.style.name == "cap" and i + 2 < len(s) and isinstance(s[i + 1], Table):
            grouped.append(KeepTogether(s[i:i + 3]))
            i += 3
        elif isinstance(x, Image) and i + 1 < len(s) and isinstance(s[i + 1], Paragraph):
            grouped.append(KeepTogether(s[i:i + 2]))
            i += 2
        else:
            grouped.append(x)
            i += 1
    doc.build(grouped, onFirstPage=footer, onLaterPages=footer)
    print("pages:", doc.page)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
