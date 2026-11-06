/** Browser-owned Plotly values; Plotly validates its extensible trace schema. */
export interface PlotlyFigure {
  data: Record<string, unknown>[];
  layout: {mapbox: Record<string, unknown>; uirevision: string; [key: string]: unknown};
}

export interface ConstraintOption {
  label: string;
  value: string;
  source: 'constraints' | 'attribution';
}
