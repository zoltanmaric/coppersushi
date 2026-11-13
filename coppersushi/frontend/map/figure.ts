/** Browser-owned Plotly values; Plotly validates its extensible trace schema. */
export interface PlotlyFigure {
  data: Record<string, unknown>[];
  layout: {mapbox: Record<string, unknown>; uirevision: string; [key: string]: unknown};
}
