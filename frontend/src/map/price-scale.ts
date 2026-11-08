/**
 * Plotly's Tropic palette is available by name in Python, but not in our JS bundle.
 * We intentionally duplicate its stops once here, shared by the TypeScript map and legend.
 */
export const PRICE_COLORSCALE: [number, string][] = [[0.0, "rgb(0, 155, 158)"], [0.16666666666666666, "rgb(66, 183, 185)"], [0.3333333333333333, "rgb(167, 211, 212)"], [0.5, "rgb(241, 241, 241)"], [0.6666666666666666, "rgb(228, 193, 217)"], [0.8333333333333334, "rgb(214, 145, 193)"], [1.0, "rgb(199, 93, 171)"]];
