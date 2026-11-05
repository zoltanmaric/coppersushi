import type {MapDiagnostics, ViewRequest} from './contracts';

export interface Issue {code: string; message: string}
export interface HealthInput {
  view: ViewRequest;
  pending: boolean;
  failures: Issue[];
  diagnostics: MapDiagnostics | null;
  attributionComplete: boolean | null;
}
export interface HealthReport extends ViewRequest {status: 'loading' | 'degraded' | 'ok'; issues: Issue[]}

/** Classify current view state without consulting the DOM or doing IO. */
export function assessHealth(input: HealthInput): HealthReport {
  const issues = [...input.failures];
  const coverage = input.diagnostics?.coverage;
  if (coverage && coverage.mapped < coverage.total)
    issues.push({code: 'unmapped_constraints', message: `${coverage.mapped} of ${coverage.total} active rows mapped`});
  if (input.diagnostics?.contribution_unavailable)
    issues.push({code: 'contribution_unavailable', message: input.diagnostics.contribution_unavailable});
  if (input.attributionComplete === false)
    issues.push({code: 'incomplete_attribution', message: 'Some attribution inputs are unavailable.'});
  return {...input.view, status: issues.length ? 'degraded' : input.pending ? 'loading' : 'ok', issues};
}

/** Suppress repeat publications without hiding recovery or a changed interval. */
export function changedReport(previous: string | null, report: HealthReport): string | null {
  const next = JSON.stringify(report);
  return next === previous ? null : next;
}

export interface RuntimeIssue {view: ViewRequest; issue: Issue}
export function currentRuntimeIssues(view: ViewRequest, history: RuntimeIssue[]): Issue[] {
  return history.filter(event => event.view.day === view.day && event.view.interval === view.interval && event.view.selected === view.selected).map(event => event.issue);
}
