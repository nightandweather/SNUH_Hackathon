/* Original source-evidence body schematic. Decorative SVG mirrors the native
 * region controls; supplied evidence flags never imply normality or diagnosis.
 */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.SICUObservationVisuals = api;
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';
  const regions = Object.freeze([
    Object.freeze({id:'brain',number:1,ko:'뇌',en:'Brain',anchor:[150,44],pin:[26,43],leader:'M38 43h72l23 1'}),
    Object.freeze({id:'lungs',number:2,ko:'폐',en:'Lungs',anchor:[176,135],pin:[274,118],leader:'M262 118h-54l-28 17'}),
    Object.freeze({id:'heart',number:3,ko:'심장',en:'Heart',anchor:[155,158],pin:[26,154],leader:'M38 154h73l29 4'}),
    Object.freeze({id:'liver',number:4,ko:'간',en:'Liver',anchor:[139,198],pin:[26,209],leader:'M38 209h61l21-10'}),
    Object.freeze({id:'kidneys',number:5,ko:'신장',en:'Kidneys',anchor:[175,230],pin:[274,231],leader:'M262 231h-54l-25-1'}),
    Object.freeze({id:'abdomen',number:6,ko:'복부·장',en:'Abdomen',anchor:[150,249],pin:[274,287],leader:'M262 287h-58l-36-35'}),
  ]);
  const paths = {
    brain: '<path d="M148 29c-5-4-11-1-11 3-5-1-9 3-8 7-5 3-5 8-1 11-1 6 4 10 10 9 3 4 9 3 12 0 3 3 9 4 12 0 6 1 11-3 10-9 4-3 4-8-1-11 1-4-3-8-8-7 0-4-6-7-11-3Z"/>' +
      '<path class="observation-organ-detail" d="M150 30v28m-10-24c-5-1-7 3-4 6m-2 5c4-3 8-1 8 3m-8 3c2 4 5 5 9 2m17-19c5-1 7 3 4 6m2 5c-4-3-8-1-8 3m8 3c-2 4-5 5-9 2M140 41c4-2 7 0 7 3m13-3c-4-2-7 0-7 3"/>',
    lungs: '<path d="M141 106c-10-4-18 3-22 13-5 12-8 26-7 39 1 15 14 20 27 15 5-2 7-6 7-12v-42c0-7-1-11-5-13Z"/>' +
      '<path d="M159 106c10-4 18 3 22 13 5 12 8 26 7 39-1 15-12 20-24 15-3-2-4-5-3-9 1-9-1-14-6-19v-26c0-7 0-11 4-13Z"/>' +
      '<path class="observation-organ-detail" d="M150 96v20m0-4-16 12m16-12 17 12m-33 0-5 19m5-19 7 13m26-13 6 20m-6-20-7 11M116 150c9 4 18 1 27-7m18 12c7 2 16 1 24-4"/>',
    heart: '<path d="M149 141c-6-5-13 0-12 10 0 11 8 23 19 30 6-9 17-17 18-28 1-10-6-16-13-11-2-5-9-6-12-1Z"/>' +
      '<path class="observation-organ-detail" d="M151 142v-10q4-4 8 0v12m-17 0-4-9m26 8 4-8m-14 12c-5 6-4 15 2 25m0-16 9-6m-15 10-7-5"/>',
    liver: '<path d="M117 187c15-7 37-7 54 1l8 8c-8 3-15 2-22 6-9 7-21 13-35 10-8-2-10-14-5-25Z"/>' +
      '<path class="observation-organ-detail" d="M150 184c1 6 1 10-2 15m-30-7c11-2 19-2 28 0m12 10c4-4 9-6 15-6"/>',
    kidneys: '<path d="M127 214c-8-5-14 1-14 11 0 12 6 20 13 17 6-2 6-8 1-12-5-4-4-7 0-9 3-2 3-5 0-7Z"/>' +
      '<path d="M173 214c8-5 14 1 14 11 0 12-6 20-13 17-6-2-6-8-1-12 5-4 4-7 0-9-3-2-3-5 0-7Z"/>' +
      '<path class="observation-organ-detail" d="M123 222c-4 4-4 10 0 14m54-14c4 4 4 10 0 14m-47-6 6 3v24m34-27-6 3v24"/>',
    abdomen: '<path d="M134 217h32q8 0 8 9v31q0 10-10 10h-28q-10 0-10-10v-31q0-9 8-9Z"/>' +
      '<path class="observation-organ-detail" d="M136 225h23q6 0 6 5t-6 5h-19q-6 0-6 5t6 5h19q6 0 6 5t-6 5h-19m-9-31v31q0 7 8 7h23q7 0 7-7v-31"/>',
  };
  function escape(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (character) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character];
    });
  }
  function silhouette() {
    return '<g class="observation-body-silhouette" fill="#F0F5FA" stroke="#9CB3C8" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M130 42c0-15 7-24 20-24s20 9 20 24l-2 17q-3 14-18 17-15-3-18-17Z"/>' +
      '<path d="M130 44c-5-3-6 2-4 8l5 5m39-13c5-3 6 2 4 8l-5 5" fill="#EDF4F9"/>' +
      '<path d="M139 75v10l-24 9q-10 5-14 18L79 191l-9 33q-5 17 1 23 6 4 11-9l15-37 21-55-2 55q-2 21-1 38l-3 21 6 54-1 70-7 12q-2 6 4 7h17q5 0 5-7l5-65 9-48 9 48 5 65q0 7 5 7h17q6-1 4-7l-7-12-1-70 6-54-3-21q1-17-1-38l-2-55 21 55 15 37q5 13 11 9 6-6 1-23l-9-33-22-79q-4-13-14-18l-24-9V75"/>' +
      '<path d="M122 100q13 8 28 3 15 5 28-3M137 85q13 8 26 0M150 277v23M117 261q16 10 33 9 17 1 33-9M121 382h14m30 0h14" fill="none" stroke="#D0DDE8" stroke-width="1"/>' +
      '<path d="M150 108v163" fill="none" stroke="#D6E2EC" stroke-width=".8" stroke-dasharray="2 5"/>' +
      '</g>';
  }
  function body(data, options) {
    data = data || {}; options = options || {};
    const ko = options.language !== 'en';
    const values = {};
    (Array.isArray(data.regions) ? data.regions : []).forEach(function (region) {
      if (region && regions.some(function (definition) { return definition.id === region.id; })) values[region.id] = region;
    });
    const selected = regions.some(function (region) { return region.id === data.selected; }) ? data.selected : 'all';
    const evidenceCount = regions.filter(function (region) { return values[region.id] && values[region.id].hasEvidence === true; }).length;
    let markup = '<svg xmlns="http://www.w3.org/2000/svg" class="observation-body-svg" viewBox="0 0 300 420" width="300" height="420" fill="none" aria-hidden="true" focusable="false" data-selected-region="'+escape(selected)+'" data-evidence-count="'+evidenceCount+'" style="display:block;width:100%;height:auto;max-width:100%;overflow:visible;letter-spacing:normal">' +
      '<title>'+(ko?'주요 장기 위치와 기록 근거를 연결하는 인체 도식':'Body schematic connecting major organs to recorded evidence')+'</title>' + silhouette();
    regions.forEach(function (definition) {
      const source = values[definition.id] || {};
      const label = source.label || definition[ko ? 'ko' : 'en'];
      const diagramLabel = !ko && definition.id === 'abdomen' ? 'Abdomen' : label;
      const evidence = source.hasEvidence === true;
      const active = selected === definition.id;
      const organFill = evidence ? '#F3B7AA' : '#D5E5EF';
      const organStroke = active ? '#0160BA' : evidence ? '#C57668' : '#7E9DB7';
      const lineColor = active ? '#0160BA' : evidence ? '#CB8B7E' : '#ABC0D2';
      const pinFill = active ? '#0160BA' : evidence ? '#FBE9E4' : '#FFFFFF';
      const pinInk = active ? '#FFFFFF' : evidence ? '#A55A4C' : '#355C7F';
      const x = definition.pin[0], y = definition.pin[1];
      const labelX = !ko && definition.id === 'abdomen' ? x - 5 : x;
      const organTransform = definition.id === 'brain' ? ' transform="translate(150 44) scale(.79 .8) translate(-150 -44)"' : definition.id === 'lungs' ? ' transform="translate(150 140) scale(.82 1) translate(-150 -140)"' : definition.id === 'kidneys' ? ' transform="translate(150 230) scale(.9 1) translate(-150 -230)"' : '';
      const evidenceLabel = evidence ? (ko?'기록 근거 있음':'Recorded evidence') : (ko?'연결된 위치 근거 없음':'No mapped location evidence');
      markup += '<g class="observation-region-target'+(evidence?' has-evidence':'')+(active?' is-selected':'')+'" data-observation-region="'+definition.id+'" data-region-number="'+definition.number+'" data-has-evidence="'+evidence+'" data-selected="'+active+'" style="cursor:pointer">' +
        '<title>'+escape(label+' · '+evidenceLabel)+'</title>' +
        '<g class="observation-organ"'+organTransform+' data-has-evidence="'+evidence+'" data-selected="'+active+'" fill="'+organFill+'" fill-opacity="'+(evidence?'.82':'.76')+'" stroke="'+organStroke+'" stroke-width="'+(active?'2':'1.15')+'" stroke-linecap="round" stroke-linejoin="round" color="'+organStroke+'">'+paths[definition.id]+'</g>' +
        '<path class="observation-leader" d="'+definition.leader+'" fill="none" stroke="'+lineColor+'" stroke-width="'+(active?'1.5':'1')+'" stroke-linecap="round" stroke-linejoin="round"/>' +
        '<g class="observation-region-pin"><rect class="observation-region-hit" x="'+(x-24)+'" y="'+(y-20)+'" width="48" height="52" rx="10" fill="transparent" pointer-events="all"/>' +
        '<circle cx="'+x+'" cy="'+y+'" r="11" fill="'+pinFill+'" stroke="'+lineColor+'" stroke-width="'+(active?'1.6':'1')+'"/>' +
        '<text class="observation-region-number" x="'+x+'" y="'+(y+4.2)+'" text-anchor="middle" fill="'+pinInk+'" font-family="inherit" font-size="12" font-weight="650" stroke="none" style="letter-spacing:normal">'+definition.number+'</text>' +
        '<text class="observation-region-label" x="'+labelX+'" y="'+(y+27)+'" text-anchor="middle" fill="'+(active?'#0160BA':'#35556F')+'" font-family="inherit" font-size="12.5" font-weight="'+(active?'650':'500')+'" stroke="none" style="letter-spacing:normal">'+escape(diagramLabel)+'</text>' +
        (evidence?'<circle class="observation-evidence-dot" cx="'+(x+9.2)+'" cy="'+(y-8.6)+'" r="3.1" fill="#D98677" stroke="#FFFFFF" stroke-width="1.1"/>':'') +
        '</g></g>';
    });
    // Organ contour detail stays light; region color is carried by the outer shape.
    markup += '<style>.observation-body-svg .observation-organ-detail{fill:none;stroke:currentColor;stroke-width:.9;opacity:.64}.observation-body-svg .observation-region-target:hover .observation-region-pin circle:first-of-type{stroke:#0160BA;stroke-width:1.8}</style></svg>';
    return markup;
  }
  return Object.freeze({version:1,width:300,height:420,regions:regions,body:body});
});
