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
 *     items: [ {id,label,color}, ... ],         // optional sub-toggles w/ swatches
 *     create({ chart, candleSeries }) -> {      // called when toggled on
 *       update(data, tf),                       // (re)draw from candle data
 *       setItemVisible(itemId, visible),        // optional, if `items` present
 *       destroy(),                              // remove everything it added
 *     }
 *   }
 */
(function () {
  const defs = [];
  window.IndicatorRegistry = {
    register(def) { defs.push(def); },
    list() { return defs.slice(); },
  };
})();
