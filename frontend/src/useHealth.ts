import {useEffect, useRef, useState} from 'react';
import {assessHealth, changedReport, currentRuntimeIssues, type RuntimeIssue, type HealthInput, type HealthReport, type Issue} from './health';

declare global {interface Window {cnecHealth?: HealthReport | null}}

export function useHealth(input: HealthInput) {
  const [runtimeErrors, setErrors] = useState<RuntimeIssue[]>([]);
  const previous = useRef<string | null>(null);
  useEffect(() => {
    const record = (issue: Issue) => setErrors(old => [...old.slice(-9), {view: input.view, issue}]);
    const error = (event: ErrorEvent) => record({code: 'browser_error', message: event.message || 'Browser error'});
    const rejection = (event: PromiseRejectionEvent) => record({code: 'unhandled_rejection', message: String(event.reason)});
    window.addEventListener('error', error);
    window.addEventListener('unhandledrejection', rejection);
    return () => {
      window.removeEventListener('error', error);
      window.removeEventListener('unhandledrejection', rejection);
      window.cnecHealth = null;
    };
  }, [input.view.day, input.view.interval, input.view.selected]);
  useEffect(() => {
    const report = assessHealth({...input, failures: [...input.failures, ...currentRuntimeIssues(input.view, runtimeErrors)]});
    const fingerprint = changedReport(previous.current, report);
    if (fingerprint === null) return;
    previous.current = fingerprint;
    window.cnecHealth = report;
    if (report.status === 'degraded') console.warn('[cnec-health]', JSON.stringify(report));
    window.dispatchEvent(new CustomEvent('cnec-health', {detail: report}));
  }, [input, runtimeErrors]);
}
