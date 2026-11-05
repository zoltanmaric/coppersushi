import {describe, expect, it} from 'vitest';
import {assessHealth, changedReport, currentRuntimeIssues, type HealthInput} from './health';
const ready: HealthInput = {
  view: {day: '2026-04-17', interval: 14, selected: null}, pending: false, failures: [],
  diagnostics: {coverage: {mapped: 0, total: 0}, contribution_unavailable: null}, attributionComplete: true,
};
describe('browser health from typed state', () => {
  it('accepts a ready interval with no binding physical constraints', () => expect(assessHealth(ready).status).toBe('ok'));
  it('keeps pending inputs distinct from missing source data', () => {
    expect(assessHealth({...ready, pending: true, attributionComplete: null}).status).toBe('loading');
    expect(assessHealth({...ready, attributionComplete: false}).issues[0].code).toBe('incomplete_attribution');
  });
  it('reports the unmapped Creys selection without reading annotation text', () => {
    const report = assessHealth({...ready, view: {...ready.view, selected: 197374}, diagnostics: {
      coverage: {mapped: 0, total: 1}, contribution_unavailable: 'Sending endpoint has no unambiguous Core bidding zone.',
    }});
    expect(report.issues.map(i => i.code)).toEqual(['unmapped_constraints', 'contribution_unavailable']);
  });
  it('preserves request and runtime failures even while other inputs load', () => {
    const failures = [{code: 'request_failed', message: 'Prices: publisher unavailable'}, {code: 'browser_error', message: 'Render failed'}];
    expect(assessHealth({...ready, pending: true, failures})).toMatchObject({status: 'degraded', issues: failures});
  });
  it('deduplicates repeats but publishes recovery and view changes', () => {
    const bad = assessHealth({...ready, failures: [{code: 'request_failed', message: 'Prices unavailable'}]});
    const key = changedReport(null, bad);
    expect(changedReport(key, bad)).toBeNull();
    expect(changedReport(key, assessHealth(ready))).not.toBeNull();
    expect(changedReport(key, {...bad, interval: 15})).not.toBeNull();
  });
});

it('does not blame a new interval for an earlier runtime exception', () => {
  const history = [{view: ready.view, issue: {code: 'browser_error', message: 'Render failed'}}];
  expect(currentRuntimeIssues(ready.view, history)).toHaveLength(1);
  expect(currentRuntimeIssues({...ready.view, interval: 15}, history)).toEqual([]);
  expect(currentRuntimeIssues({...ready.view, day: '2026-11-03'}, history)).toEqual([]);
});
