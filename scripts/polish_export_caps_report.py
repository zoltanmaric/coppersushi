"""Render the local, price-derived Polish export-cap explainer."""
from datetime import date, timedelta
from html import escape
from pathlib import Path
from shutil import copyfile

import pandas as pd
import plotly.graph_objects as go
from coppersushi.pipelines.market_day import MarketDay
from coppersushi.pipelines.cnec.attribution import POSITION_TOLERANCE_MW

ASSETS = Path(__file__).with_name('polish_export_caps_assets')
NAMES = {'DE': 'Germany–Luxembourg', 'CZ': 'Czechia', 'SK': 'Slovakia', 'all': 'All three together'}


def figure_html(fig: go.Figure, title: str) -> str:
    fig.update_layout(template='plotly_dark', paper_bgcolor='#222222', plot_bgcolor='#222222',
                      font=dict(family='Arial, sans-serif', color='#eeeeee'), height=340,
                      margin=dict(l=55, r=20, t=30, b=55), title=None,
                      legend=dict(orientation='h', y=1.15), hovermode='x unified')
    return '<div class="chart" aria-label="' + title + '">' + fig.to_html(
        full_html=False, include_plotlyjs=False, config={'displaylogo': False, 'responsive': True}) + '</div>'


def cap_status(frame: pd.DataFrame) -> pd.Series:
    """Classify published cap levels separately from their inferred binding effects."""
    status = pd.Series('No published cap', index=frame.index)
    for level, mask in (('Zero cap', frame.zero_export_cap),
                        ('Positive cap', frame.export_limit.gt(0.001)),
                        ('Negative cap', frame.export_limit.lt(-0.001))):
        selected = frame.cap_published & mask
        status.loc[selected] = level + ' · binding unknown'
        status.loc[selected & frame.binding_known & ~frame.binding_export] = level + ' · not binding'
        status.loc[selected & frame.binding_export] = level + ' · binding'
    return status


STATUS_COLORS = {'No published cap': '#adb3ba',
                 'Zero cap · not binding': '#00bc8c', 'Zero cap · binding': '#e9b65d',
                 'Positive cap · not binding': '#62a9ef', 'Positive cap · binding': '#f37887',
                 'Negative cap · not binding': '#b59cdb', 'Negative cap · binding': '#e7a3db'}
UNKNOWN_STATUSES = ('Zero cap · binding unknown', 'Positive cap · binding unknown',
                    'Negative cap · binding unknown')


def render(frame: pd.DataFrame, output: Path, start: date, end: date, effect_threshold: float) -> None:
    for cohort, filename in (("zero_export_cap", "report.html"), ("binding_export", "binding.html"), ("cap_published", "all-caps.html")):
        render_cohort(frame, output, start, end, effect_threshold, cohort, filename)
    render_cases(frame, output, start, end)


def render_cohort(frame: pd.DataFrame, output: Path, start: date, end: date,
                  effect_threshold: float, cohort: str, filename: str) -> None:
    zero = cohort == "zero_export_cap"
    published = cohort == "cap_published"
    label = {"zero_export_cap": "Zero export cap", "binding_export": "Binding export cap", "cap_published": "Published export cap"}[cohort]
    known = frame.binding_known if cohort == "binding_export" else frame.cap_published
    active = frame[frame[cohort]]
    total, count = len(frame), len(active)
    expected = sum(len(MarketDay.on(start + timedelta(days=i)).market_time_units()) for i in range((end-start).days+1))
    unknown = int((~known).sum())
    overlap = int((frame.zero_export_cap & frame.binding_export).sum())
    zero_unknown = int((frame.zero_export_cap & ~frame.binding_known).sum())
    def number(n: float) -> str:
        return f'{n:,.0f}' if pd.notna(n) else 'unavailable'
    def percent(n: float, d: float) -> str:
        return f'{n/d:.1%}' if d else 'unavailable'
    statuses = cap_status(frame)
    published_count = int(frame.cap_published.sum())
    distribution = ''
    for category in (*STATUS_COLORS, *UNKNOWN_STATUSES):
        if category.startswith('Negative cap') and not statuses.eq(category).any():
            continue
        subset = frame[statuses.eq(category)]
        difference = subset.required_mw - subset.procured_mw
        share_published = percent(len(subset), published_count) if category != 'No published cap' else 'Not applicable'
        distribution += (f'<tr><th>{category}</th><td>{len(subset):,}</td><td>{share_published}</td>'
                         f'<td>{percent(len(subset),total)}</td><td>{int((difference.notna() & difference.ne(0)).sum()):,}</td></tr>')
    distribution = ('<h3>Cap status across the entire observed period</h3>'
                    f'<p>Published caps cover <b>{published_count:,} / {total:,} observed MTUs ({percent(published_count,total)})</b>.'
                    f' The observed data cover {total:,} / {expected:,} expected MTUs ({percent(total,expected)}).</p>'
                    '<div class="scroll"><table><thead><tr><th>Cap status</th><th>MTUs</th><th>Share of published-cap MTUs</th>'
                    '<th>Share of all observed MTUs</th><th>Nonzero comparable MTUs</th></tr></thead><tbody>'
                    + distribution + '</tbody></table></div>'
                    '<p class="note">Counts include zero differences and missing reserve comparisons; they are not shares of plotted dots. '
                    'Unknown binding status stays separate and is omitted from the scatter. '
                    'No published cap means unavailable publication, not proof that no cap was set. This table covers the whole period regardless of the selected view.</p>')
    limits = frame.export_limit
    buckets = [("0 MW", limits.eq(0)),
               (">0–500 MW", limits.gt(0) & limits.le(500)),
               (">500–1,000 MW", limits.gt(500) & limits.le(1000)),
               (">1,000–2,000 MW", limits.gt(1000) & limits.le(2000)),
               (">2,000–4,000 MW", limits.gt(2000) & limits.le(4000)),
               (">4,000 MW", limits.gt(4000))]
    if limits.lt(0).any():
        buckets.append(("Negative cap", limits.lt(0)))
    if limits.isna().any():
        buckets.append(("Unavailable", limits.isna()))
    distribution += ('<h3>How restrictive was the published export limit?</h3>'
                     '<p>Zero permits no net exports. Positive caps are grouped more finely near zero, '
                     'then into wider bands for the upper tail. These are descriptive bands, not security thresholds.</p>'
                     '<div class="scroll"><table><thead><tr><th>Export cap</th><th>MTUs</th>'
                     '<th>Share of all observed MTUs</th><th>Binding MTUs</th><th>Binding share within bucket</th></tr></thead><tbody>'
                     + ''.join(f'<tr><th>{name}</th><td>{int(mask.sum()):,}</td><td>{percent(int(mask.sum()),total)}</td><td>{int((mask & frame.binding_export).sum()):,}</td><td>{percent(int((mask & frame.binding_export).sum()),int(mask.sum()))}</td></tr>'
                               for name, mask in buckets)
                     + '</tbody></table></div><p class="note">Lower bounds are exclusive and upper bounds inclusive. '
                     'Binding share uses all MTUs in that bucket as its denominator. Cap magnitude is separate from whether the cap bound. All views use the whole-period denominator.</p>')
    rows = ''
    for zone, name in NAMES.items():
        values = active[f'lower_{zone}'].dropna()
        lower = int(values.sum())
        rows += f'<tr><th>{name}</th><td>{number(lower)} / {number(len(values))}</td><td><meter min="0" max="{max(1,len(values))}" value="{lower}"></meter> {percent(lower,len(values))}</td></tr>'
    monthly = frame.assign(selected=frame[cohort], known=known, month=frame.interval.dt.tz_convert('Europe/Warsaw').dt.strftime('%Y-%m')).groupby('month').agg(
        total=('binding_export','size'), active=('selected','sum'), known=('known','sum'))
    bars = go.Figure()
    for chart_label, values, color in [(label, monthly.active, '#00bc8c'),
                                 ('Nonzero cap' if zero else 'Outside selected cohort', monthly.known-monthly.active, '#626773'),
                                 ('Unresolved', monthly.total-monthly.known, '#e9b65d')]:
        bars.add_bar(x=monthly.index.tolist(), y=values, name=chart_label, marker_color=color)
    bars.update_layout(barmode='stack')
    bars.update_yaxes(title='15-minute intervals')
    procurement = '<p class="pending">Morning procurement is being collected. The previous report’s afternoon forecasts are not used here.</p>'
    if 'procured_mw' in active:
        observed = active.dropna(subset=['procured_mw'])
        compared = observed.dropna(subset=['required_mw'])
        met = int(compared.procured_mw.ge(compared.required_mw).sum())
        if len(observed):
            procurement = f'''<div class="metrics"><div><strong>{number(observed.procured_mw.median())} <small>MW</small></strong><span>Median upward capacity purchased</span></div>
            <div><strong>{number(observed.procured_mw.min())}–{number(observed.procured_mw.max())} <small>MW</small></strong><span>Range across selected intervals</span></div>
            <div><strong>{number(met)} / {number(len(compared))}</strong><span>Purchased total ≥ required total</span></div></div>
            <p>Morning purchases are available for <b>{number(len(observed))} of {number(count)}</b> selected MTUs.
            Requirements are comparable for {number(len(compared))}. These are capacity levels in MW, not energy volumes to add across intervals.</p>
            <p><b>{number(met)}</b> selected MTUs meet or exceed the published total requirement; <b>{number(len(compared)-met)}</b> fall short;
            <b>{number(count-len(compared))}</b> have no eligible purchase/requirement pair. The published requirement has median <b>{number(compared.required_mw.median())} MW</b>
            and range <b>{number(compared.required_mw.min())}–{number(compared.required_mw.max())} MW</b> across comparable MTUs.</p>'''
            chart = go.Figure()
            plot_frame = frame if published else active
            differences = plot_frame.assign(shortfall=plot_frame.required_mw - plot_frame.procured_mw,
                                            cap_status=statuses.loc[plot_frame.index])
            comparable = differences.shortfall.notna()
            nonzero = comparable & differences.shortfall.ne(0)
            for category, color in STATUS_COLORS.items():
                if category.startswith('Negative cap') and not statuses.eq(category).any():
                    continue
                points = differences[nonzero & differences.cap_status.eq(category)]
                chart.add_scatter(x=points.interval, y=points.shortfall, mode='markers',
                                  name=category, marker=dict(size=5, color=color, symbol='diamond' if category.startswith('Positive') else 'circle'),
                                  customdata=points[['required_mw', 'procured_mw']].assign(
                                      cap=points.export_limit.map(lambda value: str(value) + ' MW' if pd.notna(value) else 'Unavailable'),
                                      position=points.polish_position.map(lambda value: str(value) + ' MW' if pd.notna(value) else 'Unavailable')).to_numpy(),
                                  hovertemplate='Required − purchased: %{y:,.0f} MW<br>'
                                                'Required: %{customdata[0]:,.0f} MW<br>'
                                                'Purchased: %{customdata[1]:,.0f} MW<br>'
                                                'Export cap: %{customdata[2]}<br>'
                                                'Net exports: %{customdata[3]}<extra>%{fullData.name}</extra>')
            chart.add_hline(y=0, line_color='#adb3ba', line_dash='dash', line_width=1)
            chart.update_yaxes(title='Required − purchased · MW', rangemode='tozero')
            chart.update_xaxes(title='Delivery interval start · UTC', rangeslider_visible=True,
                               range=[frame.interval.min(), frame.interval.max()])
            procurement += '<h3>Nonzero morning procurement differences</h3>'
            if published:
                procurement += '<p class="note">This scatter covers all observed MTUs, including any without a cap publication. The other views filter to their selected cohort.</p>'
            first = frame.loc[frame.required_mw.notna(), 'interval'].min()
            first_label = first.tz_convert('Europe/Warsaw').strftime('%d %B %Y') if pd.notna(first) else 'unavailable'
            no_record = int(frame.required_published.isna().sum())
            ineligible = int((frame.required_published.notna() & frame.required_mw.isna()).sum())
            procurement += (f'<p class="insight">Requirement coverage starts <b>{first_label}</b> in the retrieved data. '
                            f'Across the whole period, {no_record:,} MTUs have no requirement record and {ineligible:,} have a record '
                            'but no eligible pre-submission total. Missing requirements are not zero requirements or matched purchases.</p>')
            procurement += figure_html(chart, 'Nonzero required minus purchased capacity by cap status')
            procurement += (f'<p class="note">In this view, {int(differences.shortfall.eq(0).sum()):,} exact-zero comparisons are hidden; '
                            f'{int((~comparable).sum()):,} comparisons are unavailable. '
                            f'{int((nonzero & differences.cap_status.isin(UNKNOWN_STATUSES)).sum()):,} nonzero comparisons have unresolved binding status and are not plotted. '
                            'Positive: purchases fell short. Negative: purchases exceeded the requirement. '
                            'This is not proof of an operational reserve shortage. Colours distinguish zero versus positive caps and binding status; positive caps use diamond markers. Hover for the exact published cap, net exports and both reserve values. Use the slider to zoom.</p>')
            table = active[['interval','export_limit','polish_position','fcr_g','afrr_g','mfrrd_g','rr_g','procured_mw','required_mw','procured_published','required_published']].copy()
            table.columns=['Delivery start (UTC)','Export cap MW','Net exports MW','FCR ↑ MW','aFRR ↑ MW','mFRR direct ↑ MW','RR ↑ MW','Purchased MW','Required MW','Purchase publication (UTC)','Requirement publication (UTC)']
            procurement += '<details><summary>Inspect every selected interval and its reserve products</summary><div class="scroll">' + table.to_html(index=False, na_rep='Unavailable', float_format=lambda x:f'{x:,.0f}') + '</div></details>'
        else:
            procurement = '<p class="pending">No qualifying pre-submission procurement observations were recovered for selected MTUs.</p>'
    definition = (
        "A zero export cap prohibits net exports but permits net imports. This view includes every published zero cap, whether or not it bound the market."
        if zero else
        "A binding export cap reaches the export limit and has an inferred positive price effect. This view includes both zero and positive export caps."
    )
    if published:
        definition = "Every MTU with a published export limit, regardless of its value or whether it bound. A published limit is not necessarily restrictive."
    status = (f"{total-count-unknown:,} MTUs have a nonzero cap; {unknown:,} have no published cap."
              if zero else f"{total-count-unknown:,} MTUs are classified as not binding; {unknown:,} remain unresolved. The confirmed binding share is a lower bound.")
    if published:
        status = f"{count:,} MTUs have a published limit; {unknown:,} lack a published limit."
    navigation = ''.join(f'<a href="{path}"' + (' aria-current="page"' if path == filename else '') + f'>{title}</a>'
                         for path, title in (("report.html", "Zero cap · decision"), ("binding.html", "Binding cap · market effect"), ("all-caps.html", "All published caps"), ("cases.html", "Caps with enough purchased reserves")))
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Polish export caps · Critical Elements ⚡️</title><link rel="stylesheet" href="report.css"><script src="plotly.min.js"></script></head>
    <body><main><header><p class="eyebrow">Critical Elements ⚡️ / Market investigation</p><h1>Do Poland’s export limits<br>match its reserve needs?</h1>
    <p class="lede">When PSE sets a restrictive export cap, do reserve needs and available alternatives justify its level? Compare the limit with balancing capacity already purchased and the requirement published before the normal cap-submission target.</p>
    <p class="period">{start:%d %B %Y} — {end:%d %B %Y} · 15-minute market time units (MTUs)</p><nav aria-label="Choose which intervals to analyse">{navigation}</nav>
    <p class="note">The zero-cap and binding-cap groups overlap: {overlap:,} MTUs have both a zero cap and an inferred binding effect. Of the zero-cap MTUs, {zero_unknown:,} have unresolved binding status. Do not add the two group counts.</p></header>
    <aside class="insight"><b>Why the map alone cannot answer this.</b> The map highlights caps with an inferred binding price effect. An export cap tends to bind when Poland would otherwise export, and the restriction can itself lower the Polish price. Cheaper Poland during binding intervals therefore does not independently show selective cap-setting or protectionist intent. Use the zero-cap and all-published-cap views to examine the decision separately from the market outcome.</aside>
    <section><p class="eyebrow">01 / How often?</p><h2>{number(count)} intervals · {label.lower()}</h2>
    <div class="metrics"><div><strong>{number(total)}</strong><span>Observed MTUs / {number(expected)} expected</span></div><div><strong>{percent(count,total)}</strong><span>Selected / all observed MTUs</span></div><div><strong>{number(unknown)}</strong><span>MTUs with unresolved selection</span></div></div>
    <p class="note">Collection coverage: {number(total)} of {number(expected)} expected MTUs. {number(expected-total)} missing from collection.</p>
    <p>{definition}</p>
    <p class="note">{status}</p>
    {distribution}
    {figure_html(bars, 'Monthly export-cap activity and coverage')}
    </section><section><p class="eyebrow">02 / Was Poland cheaper?</p><h2>Was Poland cheaper in the selected intervals?</h2>
    <p>Strictly lower means <b>Polish price &lt; neighbour’s price</b>. Equal prices do not count. Germany–Luxembourg, Czechia and Slovakia are Poland’s adjacent Core bidding zones.</p>
    <table class="comparison"><thead><tr><th>Poland cheaper than…</th><th>MTUs / comparable selected MTUs</th><th>Share</th></tr></thead><tbody>{rows}</tbody></table>
    <p class="note">The joint row requires Poland to be cheaper than all three in the same MTU. Missing prices are excluded from the comparison denominator, not treated as equal.</p></section>
    <section><p class="eyebrow">03 / What had already been purchased?</p><h2>Upward reserves bought in the morning auction</h2>
    <p>For the same {label.lower()} MTUs, use PSE’s primary balancing-capacity procurement results. Only publication versions timestamped before 10:30 Brussels time on the preceding day qualify.</p>
    <details open><summary>Can we separate purchases before and after day-ahead?</summary>
    <p><b>Yes.</b> PSE publishes basic procurement in <code>mbp-tp</code> and supplementary procurement separately in <code>mbu-tu</code>.
    This report uses only the basic process. It does not add later supplementary purchases or activated balancing energy.</p>
    <p>The <a href="https://www.acer.europa.eu/sites/default/files/documents/Media/News/Documents/Explanatory-document-DA-CCM-CCR-2026.pdf#page=5">Core TSOs’ explanatory document, printed page 3</a>
    places basic procurement at <b>08:30 on D−1</b>, and supplementary procurement from the afternoon of D−1 through delivery.
    The <a href="https://api.raporty.pse.pl/EndpointsMap.pdf">PSE endpoint map</a> separately identifies basic and supplementary purchased-capacity reports.</p>
    <p><b>The requirement is published too.</b> PSE’s <code>wmb</code> report gives required balancing capacity by product and direction. We sum the upward requirements and compare them with upward purchases.
    The additional FRR requirement is above aFRR, so it is not a duplicated total. <code>zmb</code> is a separate report of procurement demand in the balancing-capacity market; it is not used as a substitute here.</p>
    <p>Publication timestamps matter: a retrieved revision published at or after the normal submission target cannot establish the requirement known beforehand. Such values remain unavailable here.
    Publication before the normal submission target also does not prove the value was known when PSE originally calculated or submitted the cap.</p></details>
    {procurement}
    <p class="note">Hourly purchases are repeated across their four delivery quarters, including both clock-change hours. The median is weighted by selected MTUs.
    Matching the total requirement does not establish product-by-product sufficiency, physical deliverability, or that the export cap was unnecessary.</p></section>
    <section class="method"><p class="eyebrow">Sources &amp; interpretation</p><h2>What this can—and cannot—answer</h2>
    <p>This measures price separation alongside zero or binding caps and contracted reserves. The unresolved evidence is PSE’s original cap calculation: demand, available generation, adjustments, reserve needs, and the feasibility and cost of alternatives. A filled morning auction alone does not establish the additional exports that could safely have been allowed.</p>
    <details><summary>Dates, classification and source contracts</summary>
    <p><a href="https://www.pse.pl/web/pse-eng/redistribution-of-congestion-income-from-sdac">PSE dates the JAO cross-CCR publication to 6 May 2026</a>. April is the publication handbook’s date. The comparison starts on 14 August 2026, when complete reserve comparisons become available; caps existed earlier.</p>
    <p>The zero-cap view selects published export limits within 0.001 MW of zero; it does not require a net-position or price-effect test.</p>
    <p>JAO Core allocationConstraint and netPos provide limits and positions; cross-CCR DA_PL_AC provides the alternative price. Quarter-hour order is reconstructed from row IDs and accepted only when positions match the independent Core feed. Export position tolerance: {POSITION_TOLERANCE_MW:g} MW; inferred price-effect threshold: €{effect_threshold:g}/MWh. Neighbour price comparisons have no tolerance.</p>
    <p>A position more than {POSITION_TOLERANCE_MW:g} MW below the export limit is classified as not binding even if the alternative price is unavailable. At the limit, missing alternative-price evidence remains unresolved.</p>
    <p><a href="https://api.raporty.pse.pl/api/mbp-tp">PSE mbp-tp</a>: FCR + aFRR + direct mFRR + RR upward purchases. <a href="https://api.raporty.pse.pl/api/wmb">PSE wmb</a>: FCR + aFRR + additional FRR + RR upward requirements. Missing products are not zero-filled; revised publications at or after 10:30 Brussels time on D−1 are excluded. These are retrieved publication versions, not a full revision archive.</p>
    <p>Day-ahead prices: Electricity Maps. Price-derived files remain local. <a href="intervals.csv">Download interval data</a> · <a href="summary.csv">Download comparison counts</a>.</p>
    </details></section><footer>Critical Elements ⚡️ · Public operational sources, local price analysis · Delivery through {end.isoformat()}</footer></main></body></html>'''
    output.mkdir(parents=True, exist_ok=True)
    (output/filename).write_text(html)
    copyfile(ASSETS/'report.css', output/'report.css')
    from plotly.offline import get_plotlyjs
    (output/'plotly.min.js').write_text(get_plotlyjs())


def reserve_satisfied_cases(frame: pd.DataFrame) -> pd.DataFrame:
    """Published-cap MTUs with an eligible purchased upward total >= required total."""
    eligible = frame.cap_published & frame.procured_mw.notna() & frame.required_mw.notna()
    result = frame[eligible & frame.procured_mw.ge(frame.required_mw)].copy()
    result["purchased_above_required_mw"] = result.procured_mw - result.required_mw
    return result.sort_values('interval')


def render_cases(frame: pd.DataFrame, output: Path, start: date, end: date) -> None:
    cases = reserve_satisfied_cases(frame)
    cases["cap_status"] = cap_status(cases)
    cases.to_csv(output / 'reserve-satisfied-caps.csv', index=False)
    zero = int(cases.zero_export_cap.sum())
    binding = int(cases.binding_export.sum())
    published = frame[frame.cap_published]
    comparable = published[['procured_mw', 'required_mw']].notna().all(axis=1)
    missing = int((~comparable).sum())
    first_requirement = frame.loc[frame.required_mw.notna(), "interval"].min()
    first_label = first_requirement.tz_convert("Europe/Warsaw").strftime("%d %B %Y") if pd.notna(first_requirement) else "an unavailable date"
    rows = []
    for _, row in cases.iterrows():
        local = row.interval.tz_convert('Europe/Warsaw').isoformat()
        level = 'zero' if row.zero_export_cap else ('positive' if row.export_limit > 0 else 'negative')
        effect = 'binding' if row.binding_export else ('nonbinding' if row.binding_known else 'unknown')
        values = [local, row.export_limit, row.polish_position, row.cap_status,
                  row.required_mw, row.procured_mw, row.purchased_above_required_mw,
                  row.procured_published, row.required_published]
        cells = ''.join('<td>' + escape(str(value)) + '</td>' for value in values)
        rows.append(f'<tr data-level="{level}" data-effect="{effect}" data-date="{local[:10]}">{cells}</tr>')
    headers = ['Delivery start (Warsaw, UTC offset)', 'Export cap MW', 'Net exports MW', 'Cap status',
               'Required ↑ MW', 'Purchased ↑ MW', 'Purchased − required MW',
               'Purchase publication (UTC)', 'Requirement publication (UTC)']
    heading = ''.join('<th scope="col">' + escape(name) + '</th>' for name in headers)
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Caps with purchased reserves · Critical Elements ⚡️</title><link rel="stylesheet" href="report.css"><script src="cases.js" defer></script></head>
    <body><main><header><p class="eyebrow">Critical Elements ⚡️ / Cases to investigate</p>
    <h1>Export caps with no aggregate<br>morning procurement shortfall</h1>
    <p class="lede">Every published-cap MTU where the upward capacity purchased before the normal cap-submission target met or exceeded PSE’s published upward requirement.</p>
    <p class="period">{start:%d %B %Y} — {end:%d %B %Y} · One row per 15-minute MTU</p>
    <nav><a href="report.html">Zero caps</a><a href="binding.html">Binding caps</a><a href="all-caps.html">All published caps</a><a href="cases.html" aria-current="page">Cases to investigate</a></nav></header>
    <div class="metrics"><div><strong>{len(cases):,}</strong><span>Matching intervals, all listed below</span></div><div><strong>{zero:,}</strong><span>With a zero export cap</span></div><div><strong>{binding:,}</strong><span>With an inferred binding effect</span></div></div>
    <aside class="insight"><b>What fails to explain these cases:</b> an aggregate shortfall in the morning reserve auction.
    The table does not establish that each cap was unjustified: aggregate purchases can meet the total while product-specific requirements or physical delivery constraints remain unsatisfied.
    Nonbinding limits did not restrict the cleared market. Use the binding filter to focus on caps with an inferred market effect.</aside>
    <p>{len(cases):,} of {int(comparable.sum()):,} comparable published-cap MTUs meet the aggregate requirement.
    {int(comparable.sum())-len(cases):,} fall short; {missing:,} lack an eligible comparison. Published caps cover {len(published):,} of {len(frame):,} observed MTUs.</p>
    <p class="note">Basic morning purchases only; later supplementary purchases are excluded. Both publication versions must predate 10:30 Brussels time on D−1.
    This does not establish what was known at the earlier cap-setting deadline. The retrieved eligible requirement coverage starts on {first_label};
    missing earlier requirements cannot be counted as satisfied. <a href="all-caps.html">Sources and method</a>.</p>
    <div class="filters"><label>Cap level <select id="level"><option value="">All caps</option><option value="zero">Zero</option><option value="positive">Above zero</option><option value="negative">Below zero</option></select></label>
    <label>Market effect <select id="effect"><option value="">All statuses</option><option value="binding">Binding</option><option value="nonbinding">Not binding</option><option value="unknown">Unknown</option></select></label>
    <label>Delivery date <input id="case-date" type="date" min="{start}" max="{end}"></label><button id="reset-filters" type="button">Reset filters</button></div>
    <p><output id="case-count" aria-live="polite">{len(cases):,} matching MTUs</output> · <a href="reserve-satisfied-caps.csv" download>Download every case (CSV, all filters)</a></p>
    <div class="scroll case-table"><table id="cases"><thead><tr>{heading}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    <p class="note">Delivery timestamps include the Warsaw UTC offset to distinguish the repeated clock-change hour. Publication timestamps are UTC.
    Positive purchased-minus-required values mean purchases exceeded the aggregate requirement. Hourly procurement repeats across its four delivery MTUs.</p>
    </main></body></html>'''
    (output / 'cases.html').write_text(html)
    copyfile(ASSETS / 'cases.js', output / 'cases.js')
