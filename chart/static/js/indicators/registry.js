/* chart/static/js/indicators/registry.js
 *
 * Tiny global registry so indicators are pluggable: each indicator module
 * calls IndicatorRegistry.register(def) at load time, and the chart builds a
 * toggle button per registered indicator. Indicators never reference each
 * other — they only touch the chart through the definition below.
 *
 * An indicator definition:
 *   {
 *     id:                'sessions',            // unique
 *     label:             'Sessions H/L',        // panel label
 *     description:       '...',                 // tooltip (optional)
 *     enabledByDefault:  true,                  // auto-on at load (optional)
 *     items: [ {id,label,color}, ... ]          // optional sub-toggles w/ swatches
 *            | (config) => [ {id,label,color} ], //   ...or a fn of the config
 *     create({ chart, candleSeries, symbol, config }) -> {  // called when on
 *       update(data, tf),                       // (re)draw from candle data
 *       setItemVisible(itemId, visible),        // optional, if `items` present
 *       destroy(),                              // remove everything it added
 *     }
 *   }
 *
 * `config` is algo_config.yaml (fetched from /api/config) — the source of truth
 * for knobs. Indicators read colors/params from it so editing the YAML changes
 * the chart.
 */
(function () {
  const defs = [];
  window.IndicatorRegistry = {
    register(def) { defs.push(def); },
    list() { return defs.slice(); },
  };
})();
