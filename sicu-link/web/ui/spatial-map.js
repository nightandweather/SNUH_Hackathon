/* Architectural context for the preserved public ward map.
 * Presentation only: original bed/staff nodes, coordinates and handlers stay intact.
 */
(function (root) {
  'use strict';
  if (root.SpatialMap && root.SpatialMap.version === 1) return;

  const NS = 'http://www.w3.org/2000/svg';
  const palette = {
    room: 'var(--map-room, #ffffff)',
    passage: 'var(--map-passage, #edf3f8)',
    wall: 'var(--map-wall, #b8c9dc)',
    detail: 'var(--map-detail, #6b89a8)',
    line: 'var(--map-fine-line, #dbe4ee)',
    station: 'var(--map-station, #4f759b)',
  };

  function node(tag, attrs, parent) {
    const element = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (key) {
      element.setAttribute(key, String(attrs[key]));
    });
    if (parent) parent.appendChild(element);
    return element;
  }

  function line(d, parent, color, width, extra) {
    return node('path', Object.assign({
      d: d, fill: 'none', stroke: color || palette.wall,
      'stroke-width': width || .065,
      'stroke-linecap': 'round', 'stroke-linejoin': 'round',
    }, extra || {}), parent);
  }

  function bedDrawing(parent, bed, upper) {
    const x = Number(bed.x) + 1.05;
    const y = upper ? .28 : 9.28;
    const drawing = node('g', {
      class: 'spatial-bed-silhouette',
      transform: 'translate(' + x + ' ' + y + ')',
      color: palette.detail,
    }, parent);
    // The hardware is schematic. Linen does not encode patient occupancy.
    const bedFactory = root.SICUVisuals?.topview || root.SICUVisuals?.bed || root.SpatialSymbols?.bed;
    if (typeof bedFactory === 'function') {
      drawing.innerHTML = bedFactory({ occupied: false, orientation: upper ? 'north' : 'south' });
      const svg = drawing.firstElementChild;
      svg.setAttribute('width', '2.45');
      svg.setAttribute('height', '4.42');
      svg.style.width = '2.45px';
      svg.style.height = '4.42px';
      svg.style.overflow = 'visible';
      return;
    }
    // Retain a complete symbol if this optional asset is loaded independently.
    const frame = node('g', { transform: upper ? '' : 'translate(0 4.42) scale(1 -1)' }, drawing);
    node('rect', { x: .52, y: .36, width: 1.4, height: 3.58, rx: .15,
      fill: 'none', stroke: palette.detail, 'stroke-width': .055 }, frame);
    node('rect', { x: .68, y: .62, width: 1.08, height: .64, rx: .12,
      fill: 'none', stroke: palette.detail, 'stroke-width': .045, opacity: .7 }, frame);
    line('M.39 1.5V2.9M2.05 1.5V2.9M.74 3.8h.96', frame, palette.detail, .055);
  }

  function doorDrawing(parent, roomLeft, upper) {
    // A visible gap in the corridor wall, followed by a real quarter swing.
    const hinge = roomLeft + 7.62;
    const boundary = upper ? 5 : 9;
    const direction = upper ? -1 : 1;
    const group = node('g', { class: 'spatial-room-door' }, parent);
    line('M' + hinge + ' ' + boundary + 'v' + (1.18 * direction), group, palette.detail, .065);
    line('M' + (hinge - 1.18) + ' ' + boundary +
      'a1.18 1.18 0 0 ' + (upper ? '1' : '0') + ' 1.18 ' + (1.18 * direction),
    group, palette.detail, .045, { opacity: .64 });
    node('circle', { cx: hinge, cy: boundary, r: .055, fill: palette.detail }, group);
  }

  function layoutKind(unit) {
    if (unit.id === 'C-SICU') return 'community-single-rooms';
    if (unit.id.startsWith('B-')) return 'general-compact-rooms';
    if (/(^|-)NSICU$/.test(unit.id)) return 'neuro-observation-isolation';
    if (/(^|-)CSICU$/.test(unit.id)) return 'cardiac-isolation-recovery';
    if (/(^|-)TSICU$/.test(unit.id)) return 'trauma-mixed-bays';
    return 'surgical-open-upper';
  }
  function isOpenBed(unit, bed) {
    const upper = Number(bed.y) < Number(unit.h) / 2;
    const row = (unit.beds || []).filter(item => (Number(item.y) < Number(unit.h) / 2) === upper);
    const index = row.findIndex(item => item.id === bed.id);
    // Architectural references shape the tertiary A concept. Smaller facilities
    // retain their existing room arrangement with one modest observation bay.
    if (unit.id === 'C-SICU') return upper && index === 2;
    if (unit.id.startsWith('B-')) return upper && index === 0;
    if (/(^|-)NSICU$/.test(unit.id)) return upper && index < 2;
    if (/(^|-)CSICU$/.test(unit.id)) return !upper && index >= Math.max(0,row.length-2);
    if (/(^|-)TSICU$/.test(unit.id)) return upper ? index >= Math.max(0,row.length-2) : index < 2;
    return upper;
  }
  function stationDrawing(parent, unit) {
    const x = Number(unit.x) + Number(unit.w) / 2 - 3.7;
    const y = unit.facility_layout === 'single' ? 7.05 : 6.28;
    const group = node('g', { class: 'spatial-nurse-station',
      transform: 'translate(' + x + ' ' + y + ')', color: palette.station }, parent);
    node('rect', { x: -.25, y: -.16, width: 7.9, height: 1.72, rx: .28,
      fill: 'var(--map-station-surface, #ffffff)', stroke: palette.line, 'stroke-width': .045 }, group);
    if (root.SpatialSymbols && typeof root.SpatialSymbols.station === 'function') {
      group.innerHTML += root.SpatialSymbols.station();
      const svg = group.lastElementChild;
      svg.setAttribute('width', '7.4'); svg.setAttribute('height', '1.46');
      svg.style.width = '7.4px'; svg.style.height = '1.46px';
    } else {
      node('rect', { x: .25, y: .17, width: 6.9, height: .94, rx: .13,
        fill: 'none', stroke: palette.station, 'stroke-width': .05 }, group);
      [1.15, 3.2, 5.25].forEach(function (left) {
        node('rect', { x: left, y: .38, width: .92, height: .39, rx: .06,
          fill: 'none', stroke: palette.station, 'stroke-width': .045 }, group);
        line('M' + (left + .46) + ' .77v.18', group, palette.station, .045);
      });
    }
    const compactPaired=unit.facility_layout!=='single'&&Math.round(Number(unit.w)/8)===3;
    const label = node('text', {class:'spatial-station-label','data-station-label':'true',
      x:compactPaired?9.5:3.7,y:compactPaired?.4:unit.facility_layout === 'single'?1.55:1.94,'text-anchor':'middle','data-no-translate':''}, group);
    if(unit.facility_layout === 'single')label.style.fontSize='.5px';
    label.textContent = document.documentElement.lang.startsWith('ko') ? '간호 스테이션' : 'Nurse station';
  }
  function unitDrawing(unit) {
    const x = Number(unit.x), width = Number(unit.w), height = Number(unit.h);
    const layer = node('g', {
      class: 'spatial-architecture', 'data-spatial-unit': unit.id, 'data-layout-kind':layoutKind(unit),
      'aria-hidden': 'true', 'pointer-events': 'none', focusable: 'false',
    });
    layer.style.pointerEvents = 'none';
    node('rect', { x: x + .04, y: .04, width: width - .08, height: height - .08,
      rx: .48, fill: palette.room }, layer);
    node('rect', { x: x + .06, y: 5, width: width - .12, height: Math.min(4,height-5),
      fill: palette.passage }, layer);
    line('M' + (x + .08) + ' 7H' + (x + width - .08), layer, palette.line, .035,
      { 'stroke-dasharray': '.1 .22', opacity: .7 });
    const walls = new Set();
    (unit.beds || []).forEach(function (bed) {
      const upper = Number(bed.y) < height / 2, left = Number(bed.x) - 4;
      const open = isOpenBed(unit,bed), wallY = upper ? 5 : 9;
      const space = node('g', {class:'spatial-bed-space','data-bed-id':bed.id,
        'data-space-kind':open?'open':'isolated'}, layer);
      if (!open) {
        [left,left+8].forEach(function (vertical) {
          const path='M'+vertical+' '+(upper ? .06 : 9)+'V'+(upper?5:height-.06);
          if(!walls.has(path)){line(path,space,palette.wall,.065);walls.add(path);}
        });
        line('M' + left + ' ' + wallY + 'h6.44m1.18 0h.38', space, palette.wall, .075);
        doorDrawing(space,left,upper);
      }
      bedDrawing(space,bed,upper);
      const serviceY = upper ? .22 : height - .22;
      line('M' + (Number(bed.x) - 2.7) + ' ' + serviceY + 'h5.4', space, palette.line, .055);
    });
    line('M' + (x + .12) + ' .08H' + (x + width - .12) +
      'M' + (x + .12) + ' ' + (height - .08) + 'H' + (x + width - .12), layer, palette.wall, .075);
    stationDrawing(layer, unit);
    return layer;
  }

  function elevatorDrawing(svg, model) {
    const corridor = svg.querySelector('rect.corr');
    if (!corridor) return;
    const x = Number(model.elevator_x);
    const layer = node('g', { class: 'spatial-elevator-context',
      'aria-hidden': 'true', 'pointer-events': 'none', focusable: 'false' });
    layer.style.pointerEvents = 'none';
    node('rect', { x: x - 2.1, y: 5.08, width: 4.2, height: 3.84, rx: .22,
      fill: 'var(--map-elevator-surface, #f9fbfe)', stroke: palette.wall, 'stroke-width': .055 }, layer);
    line('M' + (x - .83) + ' 5.42h1.66m-1.66 3.16h1.66', layer, palette.detail, .05);
    line('M' + (x - 2.7) + ' 5.08V8.92M' + (x + 2.7) + ' 5.08V8.92', layer, palette.line, .05);
    svg.insertBefore(layer, corridor.nextSibling);
  }

  function currentModel() {
    // S is the upstream application's global lexical binding, not a new store.
    return typeof S !== 'undefined' && S ? S : null;
  }

  function enhance() {
    const model = currentModel();
    if (!model?.floors) return;
    const portals = root.SICUWardSpaces?.contexts() || [];
    const contexts = portals.length ? portals.map(context=>({svg:context.svg,floor:{...context.floor,units:[context.unit]}})) :
      [...document.querySelectorAll('#floors > .floor')].map((element,index)=>({svg:element.querySelector('.ward-map-viewport > svg'),floor:model.floors[index]}));
    contexts.forEach(function ({svg,floor}) {
      if(!floor||!svg)return;
      const mapX = Math.min(...floor.units.map(unit=>Number(unit.x)),Number(model.elevator_x)-3);
      const mapRight = Math.max(...floor.units.map(unit=>Number(unit.x)+Number(unit.w)),Number(model.elevator_x)+2.7)+.6;
      const mapHeight = Math.max(...floor.units.map(unit=>Number(unit.h)));
      // Exterior number lanes get their own top margin; the lower extent still
      // includes native transport captions at unit.h + 1.65.
      svg.setAttribute('viewBox', [mapX - 1, -1.6, mapRight-mapX+1, mapHeight + 4].join(' '));
      const columns=floor.units.reduce((sum,unit)=>sum+Number(unit.w)/8,0);
      const columnWidth=floor.units.every(unit=>unit.facility_layout==='single')?144:180;
      svg.style.minWidth=Math.max(760,columns*columnWidth+120)+'px';
      svg.querySelectorAll('.spatial-architecture, .spatial-elevator-context').forEach(layer=>layer.remove());
      const backgrounds = svg.querySelectorAll('rect.unit-r');
      floor.units.forEach(function (unit,index) {
        const background=backgrounds[index];
        if(background)svg.insertBefore(unitDrawing(unit),background.nextSibling);
      });
      elevatorDrawing(svg,model);svg.classList.add('spatial-map-ready');
    });
  }

  const originalBuild = root.build;
  if (typeof originalBuild === 'function') {
    root.build = function () {
      const result = originalBuild.apply(this, arguments);
      enhance();
      return result;
    };
    root.build.spatialOriginal = originalBuild;
  }
  root.SpatialMap = Object.freeze({ version: 1, enhance: enhance, layoutKind:layoutKind, isOpenBed:isOpenBed });
  // Also support injection into an already rendered canonical page.
  enhance();
})(window);
