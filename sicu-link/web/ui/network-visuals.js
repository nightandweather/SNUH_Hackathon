/* Compact fictional ICU plans. This pure factory presents supplied bed states;
 * it never evaluates readiness, derives patient outcomes or creates controls.
 */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.SICUNetworkVisuals = api;
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';
  const WIDTH = 320, HEIGHT = 130;
  function escape(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (character) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character];
    });
  }
  function color(value, kind) {
    const source = String(value || '').trim();
    if (/^#[a-f\d]{3,8}$/i.test(source)) return source;
    if (/^rgba?\([\d\s.,%]+\)$/i.test(source)) return source;
    return ({reserved:'#D2AE4C',turnover:'#BFCCD9',vacant:'#FFFFFF',empty:'#FFFFFF'})[kind] || '#6B91B7';
  }
  const operationalColors={occupied:'#315E85',reserved:'#D2AE4C',turnover:'#BFCCD9',vacant:'#FFFFFF',empty:'#FFFFFF'};
  function bedSymbol(bed, south, operational) {
    const kind = String(bed.kind || (bed.occupied === true ? 'occupied' : 'vacant'));
    const source = operational ? operationalColors[kind]||'#315E85' : color(bed.color, kind);
    const occupied = bed.occupied === true;
    const reserved = kind === 'reserved', turnover = kind === 'turnover';
    const border = occupied ? '#7F9AB4' : reserved ? '#B49A4B' : '#A8BBCD';
    const art = '<rect class="network-mini-bed-frame" x="-10.5" y="-17" width="21" height="34" rx="3" fill="#F5F8FC" stroke="'+border+'" stroke-width=".9"/>' +
      '<rect class="network-mini-bed-linen" x="-8.5" y="-14.7" width="17" height="28.7" rx="2.2" fill="'+(reserved?'#FFF5D6':turnover?'#E2EAF2':'#FFFFFF')+'" stroke="#D2DEEA" stroke-width=".65"/>' +
      '<rect x="-6.6" y="-12.6" width="13.2" height="6.6" rx="1.6" fill="#F4F8FC" stroke="#B4C9DB" stroke-width=".7"/>' +
      '<path d="M-12.2-5.7V7M12.2-5.7V7M-7.2 16.5H7.2" fill="none" stroke="'+border+'" stroke-width=".9" stroke-linecap="round"/>' +
      (occupied ?
        '<g class="network-mini-occupant"><path d="M-4.2-8.5a4.2 4.2 0 1 0 8.4 0 4.2 4.2 0 1 0-8.4 0" fill="#EFF5FA" stroke="#6889A7" stroke-width=".7"/>' +
        '<path d="M-4.1-9.1q.4-3.6 4.1-3.6t4.1 3.6q-4.1-1.4-8.2 0Z" fill="#456E93"/>' +
        '<path d="M-6.5-.8q6.5-1.4 13 0v11.5q0 1.8-1.8 1.8h-9.4q-1.8 0-1.8-1.8Z" fill="'+source+'" fill-opacity=".35" stroke="'+source+'" stroke-width=".7"/>' +
        '<path d="M-5.7 1q5.7-1 11.4 0M-4.4 9.5h8.8" fill="none" stroke="#FFFFFF" stroke-opacity=".8" stroke-width=".8"/></g>' :
        turnover ? '<path class="network-mini-turnover" d="m-5.2-.8 4.8 4.8m0-4.8 4.8 4.8M-5.2 9.2H5.2" fill="none" stroke="#9EB2C6" stroke-width=".8" stroke-linecap="round"/>' :
        reserved ? '<path class="network-mini-reserved" d="m0-1.5 3.4 3.4L0 5.3l-3.4-3.4Z" fill="#D3B259" stroke="#AD903C" stroke-width=".6"/>' :
        '<path class="network-mini-empty" d="M-6.4 8H6.4v4H-6.4Z" fill="#F2F6FB" stroke="#C2D3E3" stroke-width=".7"/>');
    return '<g class="network-mini-bed-art"'+(south?' transform="rotate(180)"':'')+'>'+art+'</g>';
  }
  function station(single) {
    const y = single ? 105 : 66.5;
    return '<g class="network-mini-station" transform="translate(160 '+y+')" aria-hidden="true">' +
      '<rect x="-20" y="-5.1" width="40" height="10.2" rx="2.6" fill="#FFFFFF" stroke="#CAD9E7" stroke-width=".7"/>' +
      '<path d="M-12-2.7h7.5v4H-12Zm8.5 5.5h-9.5M4.5-2.7H12v4H4.5Zm8.5 5.5H3.5" fill="none" stroke="#85A4BF" stroke-width=".65" stroke-linecap="round"/>' +
      '</g>';
  }
  function ward(unit, options) {
    unit = unit || {}; options = options || {};
    const language = options.language === 'ko' ? 'ko' : 'en';
    const operational = options.operational === true;
    const beds = Array.isArray(unit.beds) ? unit.beds : [];
    const single = (unit.facility_layout || unit.layout) === 'single';
    const columns = Math.max(1, single ? beds.length : Math.ceil(beds.length / 2));
    const cell = 288 / columns;
    const name = unit[language === 'ko' ? 'name_ko' : 'name_en'] || unit[language==='ko'?'nameKo':'nameEn'] || unit.name || unit.label || unit.id || '';
    const description = name + ' · ' + beds.length + (language === 'ko' ? '개 병상 · 가상 공간도' : ' beds · fictional schematic');
    const corridorTop = single ? 87 : 58, corridorHeight = single ? 38 : 17;
    let markup = '<svg xmlns="http://www.w3.org/2000/svg" class="network-ward-plan" viewBox="0 0 '+WIDTH+' '+HEIGHT+'" width="'+WIDTH+'" height="'+HEIGHT+'" fill="none" '+(operational?'aria-hidden="true" data-anonymous="true"':'role="img" aria-label="'+escape(description)+'"')+' focusable="false" pointer-events="none" data-no-translate="" data-unit-id="'+escape(unit.id)+'" data-layout="'+(single?'single':'paired')+'" data-bed-count="'+beds.length+'" style="display:block;width:100%;height:auto;max-width:100%;pointer-events:none">' +
      (operational?'':'<title>'+escape(description)+'</title>') +
      '<rect class="network-mini-outline" x="4" y="4" width="312" height="122" rx="5" fill="#F8FAFD" stroke="#C9D8E6" stroke-width=".9"/>' +
      '<rect class="network-mini-corridor" x="4.5" y="'+corridorTop+'" width="311" height="'+corridorHeight+'" fill="#EAF2F8"/>' +
      '<path d="M8 '+corridorTop+'H312'+(single?'':'M8 75H312')+'" stroke="#D4E1EC" stroke-width=".7"/>';
    for (let index = 1; index < columns; index++) {
      const x = 16 + index * cell;
      markup += '<path d="M'+x+' 4.5V'+corridorTop+(single?'':'M'+x+' 75V125.5')+'" stroke="#DCE6EF" stroke-width=".65"/>';
    }
    markup += station(single);
    beds.forEach(function (bed, index) {
      const lower = !single && index >= columns;
      const x = 16 + ((index % columns) + .5) * cell;
      const centerY = single ? 54 : lower ? 95 : 37;
      const numberY = single ? 21 : lower ? 122 : 18;
      const kind = String(bed.kind || (bed.occupied === true ? 'occupied' : 'vacant'));
      const source = operational ? operationalColors[kind]||'#315E85' : color(bed.color, kind);
      const number = bed.number == null ? String(bed.id || '').split('-').pop() : bed.number;
      const status = bed.statusLabel || bed.label || bed.statusKey || '';
      const label = (language === 'ko' ? number+'번 병상' : 'Bed '+number) + (status ? ' · '+status : '');
      const washY = single ? 8 : lower ? 78 : 7;
      const washHeight = single ? 75 : 47;
      markup += '<g class="network-mini-bed" '+(operational?'pointer-events="none" data-slot-index="'+index+'" data-bed-kind="'+escape(kind)+'" data-occupied="'+(bed.occupied===true)+'"':'pointer-events="all" data-bed-id="'+escape(bed.id)+'" data-bed-number="'+escape(number)+'" data-bed-kind="'+escape(kind)+'" data-status-key="'+escape(bed.statusKey)+'" data-occupied="'+(bed.occupied === true)+'" data-source-color="'+escape(bed.color || '')+'" aria-label="'+escape(label)+'"')+'>' +
        (operational?'':'<title>'+escape(label)+'</title>') +
        '<rect class="network-mini-state" x="'+(x-Math.min(23,cell*.43))+'" y="'+washY+'" width="'+Math.min(46,cell*.86)+'" height="'+washHeight+'" rx="4" fill="'+source+'" fill-opacity="'+(kind==='vacant'||kind==='empty'?'0':kind==='reserved'?'.2':'.11')+'"/>' +
        (operational?'':'<text class="network-mini-number" x="'+x+'" y="'+numberY+'" text-anchor="middle" fill="#244B70" font-family="inherit" font-size="15" font-weight="650" style="letter-spacing:normal">'+escape(number)+'</text>') +
        '<g transform="translate('+x+' '+centerY+')'+(single?' scale(1.27)':'')+'">'+bedSymbol(bed, lower, operational)+'</g>' +
        '</g>';
    });
    markup += '</svg>';
    return markup;
  }
  return Object.freeze({version: 1, width: WIDTH, height: HEIGHT, ward: ward});
});
