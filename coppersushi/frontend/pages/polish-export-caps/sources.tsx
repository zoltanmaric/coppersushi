import React from 'react';
import type {Investigation} from './data';

const jaoDay = '?FromUtc=2026-11-12T23:00:00.000Z&ToUtc=2026-11-13T23:00:00.000Z&Take=100000';
const pseDay = '?dateFrom=2026-11-13&dateTo=2026-11-13';
const dayMonth = new Intl.DateTimeFormat('en-GB', {day: 'numeric', month: 'long', timeZone: 'UTC'});

export function Sources({study}: {study: Investigation}) {
  const end = new Date(study.end);
  return <details className="study-sources">
    <summary>How I counted</summary>
    <p>I looked at all {study.coverage.expected.toLocaleString('en-GB')} quarter-hours from {dayMonth.format(new Date(study.start))} through {dayMonth.format(end)} {end.getUTCFullYear()}. The source links below open the records for one day, 13 November, so you can see the values that go into the chart.</p>

    <p><strong>When did a limit bind?</strong> For exports, I subtract the Polish day-ahead price, from Electricity Maps, from JAO’s Polish alternative price (<code>border_PL_ALT</code>). That difference is the export limit’s inferred <em>shadow price</em>. I count the limit as binding when the difference exceeds €0.01/MWh and scheduled net exports (<code>hub_PL</code>) reach the export limit (<code>limitUp_PL</code>), allowing 0.11 MW for rounding. For imports, the price difference runs the other way, and I check scheduled net imports against the import limit (<code>limitDown_PL</code>).{' '}
      <a target="_blank" rel="noopener noreferrer" href={'https://publicationtool.jao.eu/core/api/data/allocationConstraint' + jaoDay}>JAO limits</a> ·{' '}
      <a target="_blank" rel="noopener noreferrer" href={'https://publicationtool.jao.eu/core/api/data/netPos' + jaoDay}>Scheduled net positions</a> ·{' '}
      <a target="_blank" rel="noopener noreferrer" href={'https://publicationtool.jao.eu/crossCCR/api/data/DA_PL_AC' + jaoDay}>Polish alternative prices</a>
    </p>

    <p><strong>Was there a reserve shortfall?</strong> When the export limit bound, I compared how much upward reserve PSE said it needed with how much it bought in its basic auction. For imports, I made the same comparison for downward reserve. A shortfall means the total bought was below the total required. These are the field names in PSE’s two reports, all in MW.</p>

    <table>
      <thead><tr>
        <th scope="col">Reserve</th>
        <th scope="col"><a target="_blank" rel="noopener noreferrer" href={'https://raporty.pse.pl/report/wmb' + pseDay}>Required (<code>wmb</code>)</a></th>
        <th scope="col"><a target="_blank" rel="noopener noreferrer" href={'https://raporty.pse.pl/report/mbp-tp' + pseDay}>Bought (<code>mbp-tp</code>)</a></th>
      </tr></thead>
      <tbody>
        <tr><th scope="row">Upward</th><td><code>fcrg + afrrg + frrg + rrg</code></td><td><code>fcr_g + afrr_g + mfrrd_g + rr_g</code></td></tr>
        <tr><th scope="row">Downward</th><td><code>fcrd + afrrd + frrd</code></td><td><code>fcr_d + afrr_d + mfrrd_d</code></td></tr>
      </tbody>
    </table>

    <p>For example, the export limit bound in all four quarter-hours from 16:00 to 17:00 CET on 13 November. PSE required <strong>2,376 MW</strong> of upward reserve and bought <strong>2,376 MW</strong>. PSE required 400 MW of automatic restoration reserve (<code>afrrg</code>) and bought 542 MW (<code>afrr_g</code>). All four quarter-hours therefore count as having no <em>total</em> shortfall. The downward calculation has one fewer term because PSE required zero downward replacement reserve throughout the study.</p>

    <p><strong>Which figures did I use?</strong> I took the latest requirement and purchase figures PSE published before 10:30 local time on the day before delivery, its usual target for submitting the limit. PSE may have set the limit earlier. PSE can buy more reserve through supplementary procurement from that afternoon until delivery, so I leave those later purchases out of the morning comparison. How much reserve it could actually call on, and why it set the limit, are separate questions.</p>
  </details>;
}
