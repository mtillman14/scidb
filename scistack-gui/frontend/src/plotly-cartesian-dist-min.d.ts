/**
 * The Plot Studio needs box, violin and heatmap traces, which the *basic*
 * bundle (used by the sidebar's VariablePlot) does not carry. Same typing
 * situation as that one: react-plotly.js's factory() treats the Plotly
 * instance as `unknown`, so this only needs to satisfy the import.
 */
declare module 'plotly.js-cartesian-dist-min' {
  const Plotly: unknown
  export default Plotly
}
