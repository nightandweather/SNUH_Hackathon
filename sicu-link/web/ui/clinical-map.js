/* Fictional spatial context and occupied-bed presentation.
 * Native coordinates, patient records, focus targets and controllers are untouched.
 */
(function (root) {
  'use strict';
  if (root.SICUClinicalMap) return;
  const NS = 'http://www.w3.org/2000/svg';
  const views = new WeakMap();
  const current = () => typeof S !== 'undefined' && S ? S : null;
  const korean = () => typeof I18n !== 'undefined' ? I18n.language === 'ko' : document.documentElement.lang.startsWith('ko');
  const set = (element, key, value) => {
    const text = String(value);
    if (element.getAttribute(key) !== text) element.setAttribute(key, text);
  };
  function node(tag, attributes, parent) {
    const element = document.createElementNS(NS, tag);
    Object.entries(attributes || {}).forEach(([key, value]) => element.setAttribute(key, String(value)));
    if (parent) parent.appendChild(element);
    return element;
  }
  function spaces(unit, elevator) {
    if (typeof root.SICUTransportModel?.spaces === 'function') return root.SICUTransportModel.spaces(unit, elevator);
    const e = Number(elevator);
    const corridorY = unit?.facility_layout === 'single' ? 6.6 : 7;
    const x = Number(unit?.x || 0), right = x + Number(unit?.w || 0);
    return {
      procedure: { x: e - 2.3, y: .35, w: 4.6, h: 3.4, door: [e, 3.75] },
      staging: [e, 4.8], corridorY: corridorY,
      gate: [Math.abs(e - x) < Math.abs(e - right) ? x : right, corridorY],
    };
  }
  function procedureRoom(svg, floor, model) {
    const layout = spaces(floor.units[0], Number(model.elevator_x));
    const room = layout.procedure, e = Number(model.elevator_x);
    const group = node('g', {
      class: 'clinical-procedure-room', transform: 'translate(' + e + ' 0)',
      'data-floor': floor.floor, 'data-room-x': room.x, 'data-room-y': room.y,
      'data-room-width': room.w, 'data-room-height': room.h,
      'data-door-x': room.door[0], 'data-door-y': room.door[1],
      'data-staging-x': layout.staging[0], 'data-staging-y': layout.staging[1],
      'aria-hidden': 'true', 'pointer-events': 'none', focusable: 'false',
    });
    const title = node('title', {}, group);
    node('rect', {class: 'clinical-procedure-surface', x: -2.3, y: .35, width: 4.6, height: 3.4, rx: .16}, group);
    node('path', {class: 'clinical-procedure-wall', d: 'M-.78 3.75H-2.3V.35H2.3v3.4H.78'}, group);
    node('path', {class: 'clinical-procedure-inset', d: 'M-2.14 1.3H2.14'}, group);
    const label = node('text', {class: 'clinical-procedure-label', x: 0, y: .98, 'text-anchor': 'middle'}, group);
    // Top-view procedure couch, linen and rails; this room symbol encodes no occupancy.
    const couch = node('g', {class: 'clinical-procedure-couch', transform: 'translate(-.63 2.43)'}, group);
    node('path', {class: 'clinical-procedure-bed-frame', d: 'M-.55-.9h1.1q.12 0 .12.12V.85q0 .12-.12.12h-1.1q-.12 0-.12-.12V-.78q0-.12.12-.12Z'}, couch);
    node('rect', {class: 'clinical-procedure-linen', x: -.52, y: -.75, width: 1.04, height: 1.54, rx: .1}, couch);
    node('rect', {class: 'clinical-procedure-pillow', x: -.4, y: -.65, width: .8, height: .36, rx: .09}, couch);
    node('path', {class: 'clinical-procedure-bed-detail', d: 'M-.78-.3V.53M.78-.3V.53M-.38.93v.15M.38.93v.15M-.46.66h.92'}, couch);
    const equipment = node('g', {class: 'clinical-procedure-equipment', transform: 'translate(1.15 2.03)'}, group);
    node('rect', {class: 'clinical-procedure-monitor', x: -.44, y: -.34, width: .88, height: .64, rx: .08}, equipment);
    node('path', {class: 'clinical-procedure-screen', d: 'M-.25-.12h.21m.12 0h.16M-.25.04h.49M0 .31v.72m-.31.04h.62'}, equipment);
    node('path', {class: 'clinical-procedure-door', d: 'M-.78 3.62v.13m1.56-.13v.13M-.73 3.65h.58m.3 0h.58'}, group);
    node('path', {class: 'clinical-procedure-door-threshold', d: 'M-.78 3.75H.78'}, group);
    const corridor = svg.querySelector('rect.corr');
    svg.insertBefore(group, corridor ? corridor.nextSibling : svg.firstChild);
    return {group, title, label};
  }
  function elevatorMarker(svg, model) {
    const group = node('g', {
      class: 'clinical-elevator-marker', transform: 'translate(' + Number(model.elevator_x) + ' 8.55)',
      'aria-hidden': 'true', 'pointer-events': 'none', focusable: 'false',
    });
    const title = node('title', {}, group);
    node('path', {class: 'clinical-elevator-icon', d: 'M-1.7-.36h.52v.65h-.52ZM-1.44-.3v.54M-1.61-.49l.17-.18.17.18'}, group);
    const label = node('text', {class: 'clinical-elevator-label', x: -.94, y: .13}, group);
    const corridor = svg.querySelector('rect.corr');
    svg.insertBefore(group, corridor ? corridor.nextSibling : svg.firstChild);
    return {group, title, label};
  }
  function makeView(svg, floor, model) {
    const procedure = procedureRoom(svg, floor, model);
    const elevator = elevatorMarker(svg, model);
    svg.querySelectorAll(':scope > text.unit-t').forEach(element => {
      if (element.textContent.trim() === 'E/V') element.classList.add('clinical-original-elevator-label');
    });
    const occupants = node('g', {class: 'clinical-occupants', 'aria-hidden': 'true', 'pointer-events': 'none', focusable: 'false'});
    // Keep original staff, links and transport above the bed occupants.
    const staffLayer = svg.querySelector('.ward-space-staff') || (typeof floorSvg !== 'undefined' ? floorSvg[floor.floor] : null);
    svg.insertBefore(occupants, staffLayer?.parentNode === svg ? staffLayer : null);
    svg.classList.add('clinical-map-ready');
    const view = {procedure, elevator, occupants, patients: new Map(), language: '', geometry: Number(model.elevator_x)};
    views.set(svg, view);
    return view;
  }
  function updateLanguage(view) {
    const language = korean() ? 'ko' : 'en';
    if (view.language === language) return;
    view.language = language;
    view.procedure.label.textContent = language === 'ko' ? '처치실' : 'Procedure room';
    view.procedure.title.textContent = language === 'ko' ? '처치실 · 가상 공간도, 실제 건축 도면이 아님' : 'Procedure room · fictional schematic, not an architectural plan';
    view.elevator.label.textContent = language === 'ko' ? '승강기' : 'Elevator';
    view.elevator.title.textContent = language === 'ko' ? '승강기 · 처치실과 별도 공간' : 'Elevator · separate from the procedure room';
    view.patients.forEach(record => { record.language = ''; });
  }
  function eligible(bed) {
    return Boolean(bed.patient) && bed.unavailable !== true && bed.flow?.status?.key !== 'turnover' && bed.flow?.scene !== 'porter-story';
  }
  function layoutBedContents(floor) {
    // Preserve the six source indicators and their order; reserve the right side
    // for the physical bed so the pillow and patient's face remain unobscured.
    floor.units.forEach(unit => (unit.beds || []).forEach(bed => {
      const entry = typeof bedEl !== 'undefined' ? bedEl[bed.id] : null;
      if (!entry) return;
      // Keep the original number node and its bed-space anchor, but reserve an
      // exterior label lane clear of the roof, headwall service and foot wall.
      const number = entry.r.parentElement.querySelector('.bed-id');
      if (number) {
        const upper = Number(bed.y) < Number(unit.h) / 2;
        set(number, 'y', upper ? -.65 : Number(unit.h) + .65);
        set(number, 'dominant-baseline', 'middle');
        set(number, 'data-bed-label-edge', upper ? 'top' : 'bottom');
      }
      const icons = entry.icons;
      if (icons) {
        set(icons, 'data-clinical-layout', '3x2');
        icons.querySelectorAll('.sicu-map-care').forEach((indicator, index) => {
          set(indicator, 'transform', 'translate(' + ((index % 3) * .75) + ' ' + (Math.floor(index / 3) * .84) + ')');
        });
      }
      if (entry.tx) {
        entry.tx.classList.add('clinical-bed-status');
        set(entry.tx,'data-map-color-only',/^(RED|BLUE|GREEN)$/.test(entry.tx.textContent.trim()));
        set(entry.tx, 'x', Number(bed.x) - 1.425);
        set(entry.tx, 'y', Number(bed.y) + 1.45);
      }
    }));
  }
  function updateOccupants(view, floor) {
    const factory = root.SICUTransportVisuals?.bedPatient;
    if (typeof factory !== 'function') return;
    const present = new Set();
    floor.units.forEach(unit => (unit.beds || []).forEach(bed => {
      if (!eligible(bed)) return;
      const id = String(bed.id), patient = bed.patient;
      const key = JSON.stringify([String(patient.pid ?? ''), patient.admit_t ?? null]);
      const deceased = bed.flow?.kind === 'icu_death';
      const upper = Number(bed.y) < Number(unit.h) / 2;
      const transform = 'translate(' + (Number(bed.x) + 2.25) + ' ' + (upper ? 2.3 : 11.5) + ')' + (upper ? '' : ' rotate(180)');
      const signature = JSON.stringify([key, deceased, transform]);
      present.add(id);
      let record = view.patients.get(id);
      if (!record) {
        const group = node('g', {class: 'clinical-bed-patient', 'data-bed-id': id, 'pointer-events': 'none', 'aria-hidden': 'true', focusable: 'false'}, view.occupants);
        record = {group, signature: '', language: ''};
        view.patients.set(id, record);
      }
      if (record.signature !== signature) {
        set(record.group, 'transform', transform);
        set(record.group, 'data-patient-key', key);
        set(record.group, 'data-deceased', deceased);
        // Identity is recorded in attributes; no clinical state is inferred from art.
        if (record.deceased !== deceased || record.factory !== factory) {
          record.group.innerHTML = factory({deceased: deceased});
          record.deceased = deceased;
          record.factory = factory;
        }
        record.signature = signature;
      }
    }));
    view.patients.forEach((record, id) => {
      if (!present.has(id)) { record.group.remove(); view.patients.delete(id); }
    });
    set(view.occupants, 'data-occupied-count', present.size);
  }
  function decorate() {
    const model = current();
    if (!model?.floors) return;
    const portals = root.SICUWardSpaces?.contexts() || [];
    const contexts = portals.length ? portals.map(context=>({svg:context.svg,floor:{...context.floor,units:[context.unit]}})) :
      [...document.querySelectorAll('#floors > .floor')].map((element,index)=>({svg:element.querySelector('.ward-map-viewport > svg'),floor:model.floors[index]}));
    contexts.forEach(({svg,floor})=>{
      if (!floor || !svg || !floor.units?.length) return;
      let view = views.get(svg);
      if (!view || !view.procedure.group.isConnected || view.geometry !== Number(model.elevator_x)) {
        svg.querySelectorAll('.clinical-procedure-room, .clinical-elevator-marker, .clinical-occupants').forEach(layer => layer.remove());
        view = makeView(svg, floor, model);
      }
      updateLanguage(view);layoutBedContents(floor);updateOccupants(view,floor);
    });
  }
  const originalDraw = root.draw;
  if (typeof originalDraw === 'function') {
    root.draw = function () { const result = originalDraw.apply(this, arguments); decorate(); return result; };
    root.draw.clinicalMapOriginal = originalDraw;
  }
  const originalBuild = root.build;
  if (typeof originalBuild === 'function') {
    root.build = function () { const result = originalBuild.apply(this, arguments); decorate(); return result; };
    root.build.clinicalMapOriginal = originalBuild;
  }
  root.SICUClinicalMap = Object.freeze({version: 1, spaces: spaces, decorate: decorate});
  decorate();
})(window);
