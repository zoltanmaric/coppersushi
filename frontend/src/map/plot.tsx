import createPlotlyComponent from 'react-plotly.js/factory';

declare global { interface Window { Plotly: unknown } }

/** The official Mapbox-only Plotly bundle is loaded before the application script. */
export const Plot = createPlotlyComponent(window.Plotly);
