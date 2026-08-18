/**
 * No published types for this pre-bundled build — react-plotly.js's own
 * factory() typing already treats the Plotly instance as `unknown`
 * (see node_modules/react-plotly.js/dist/factory.d.ts), so this only
 * needs to satisfy the import, not describe Plotly's API.
 */
declare module 'plotly.js-basic-dist-min' {
  const Plotly: unknown
  export default Plotly
}
