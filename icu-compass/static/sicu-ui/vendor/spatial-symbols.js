/* Quiet architectural plan symbols. Original SVG artwork, rendered in currentColor. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.SpatialSymbols = api;
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  function svg(width, height, viewBox, drawing) {
    return '<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height + '" viewBox="' + viewBox + '" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + drawing + '</svg>';
  }

  function bed(options) {
    options = options || {};
    const occupied = options.occupied !== false;
    const orientation = options.orientation === 'south' ? 'rotate(180 50 70)' : '';
    const linen = occupied
      ? '<path d="M29 55c12-3 30-3 42 0v47a5 5 0 0 1-5 5H34a5 5 0 0 1-5-5V55Z" fill="var(--bed-blanket, currentColor)" fill-opacity=".085" stroke-opacity=".55" stroke-width="1.4"/><path d="M30 62h40" stroke-opacity=".32" stroke-width="1.1"/>'
      : '<path d="M30 60h40m-40 8h40" stroke-opacity=".18" stroke-width="1.1"/>';
    return svg(100, 140, '0 0 100 140',
      '<g transform="' + orientation + '">' +
      '<path d="M29 17v-3m42 3v-3M29 123v4m42-4v4" stroke-width="2.2" stroke-opacity=".65"/>' +
      '<rect x="22" y="18" width="56" height="105" rx="7" stroke-width="1.8"/>' +
      '<rect x="27" y="24" width="46" height="91" rx="5" fill="var(--bed-mattress, #fff)" stroke-width="1.1" stroke-opacity=".38"/>' +
      '<rect x="31" y="29" width="38" height="20" rx="5" fill="var(--bed-pillow, currentColor)" fill-opacity=".055" stroke-width="1.25" stroke-opacity=".6"/>' +
      linen +
      '<path d="M17 48v39m66-39v39" stroke-width="2.1" stroke-opacity=".7"/>' +
      '<path d="M17 53h5m-5 29h5m56-29h5m-5 29h5" stroke-width="1.1" stroke-opacity=".4"/>' +
      '<path d="M29 119h42" stroke-width="1.6" stroke-opacity=".55"/>' +
      '</g>');
  }

  function door(options) {
    options = options || {};
    const mirrorX = options.hinge === 'right';
    const mirrorY = options.opening === 'down';
    const transform = 'translate(' + (mirrorX ? '24' : '0') + ' ' + (mirrorY ? '24' : '0') + ') scale(' + (mirrorX ? '-1' : '1') + ' ' + (mirrorY ? '-1' : '1') + ')';
    return svg(24, 24, '0 0 24 24',
      '<g transform="' + transform + '">' +
      '<path d="M20 20A16 16 0 0 0 4 4" stroke-width=".9" stroke-opacity=".48"/>' +
      '<path d="M4 20V4" stroke-width="1.6"/>' +
      '<path d="M1 20h3m16 0h3" stroke-width="2.2"/>' +
      '<circle cx="4" cy="20" r="1" fill="currentColor" stroke="none"/>' +
      '</g>');
  }

  function station() {
    return svg(120, 45, '0 0 120 45',
      '<path d="M9 9h102a3 3 0 0 1 3 3v20H6V12a3 3 0 0 1 3-3Z" fill="var(--station-surface, currentColor)" fill-opacity=".035" stroke-width="1.4"/>' +
      '<path d="M6 32h108M11 36h98" stroke-width="1.1" stroke-opacity=".42"/>' +
      '<path d="M44 10v21m32-21v21" stroke-width=".9" stroke-opacity=".24"/>' +
      '<g stroke-width="1.2" stroke-opacity=".68">' +
      '<rect x="20" y="14" width="15" height="9" rx="1.5"/><path d="M27.5 23v3m-4 0h8"/>' +
      '<rect x="53" y="14" width="15" height="9" rx="1.5"/><path d="M60.5 23v3m-4 0h8"/>' +
      '<rect x="86" y="14" width="15" height="9" rx="1.5"/><path d="M93.5 23v3m-4 0h8"/>' +
      '</g>' +
      '<path d="M22 4h10m23 0h10m23 0h10" stroke-width="2" stroke-opacity=".38"/>');
  }

  return Object.freeze({ bed: bed, door: door, station: station });
});
