/* Browser-local facility geometry for fictional hospitals; no clinical evaluation. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.FacilityProfiles = api;
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';
  const VERSION = 'fictional-facilities-v2-four-nurses';
  const freeze = value => {
    if (value && typeof value === 'object') {
      Object.values(value).forEach(freeze);
      Object.freeze(value);
    }
    return value;
  };
  const definitions = freeze({
    A: {id:'A', typeKo:'상급종합병원형', typeEn:'Tertiary hospital concept',
      nursesPerUnit:4, chargePerUnit:1, bedsidePerUnit:3, nurseCount:16,
      unitCount:4, bedCount:32, layoutKo:'두 층의 전문 ICU', layoutEn:'Specialist ICUs across two floors',
      units:[{id:'CSICU',beds:8},{id:'NSICU',beds:8},{id:'SICU',beds:8},{id:'TSICU',beds:8}]},
    B: {id:'B', typeKo:'종합병원형', typeEn:'General hospital concept',
      nursesPerUnit:4, chargePerUnit:1, bedsidePerUnit:3, nurseCount:8,
      unitCount:2, bedCount:14, layoutKo:'한 층의 두 ICU', layoutEn:'Two ICUs on one floor',
      units:[{id:'B-SICU',beds:6,floor:102,display_floor:2,x:0,w:24,h:14,layout:'paired'},
        {id:'B-NSICU',beds:8,floor:102,display_floor:2,x:38,w:32,h:14,layout:'paired'}]},
    C: {id:'C', typeKo:'지역 종합병원형', typeEn:'Community hospital concept',
      nursesPerUnit:4, chargePerUnit:1, bedsidePerUnit:3, nurseCount:4,
      unitCount:1, bedCount:6, layoutKo:'단일 통합 ICU', layoutEn:'One mixed ICU',
      units:[{id:'C-SICU',beds:6,floor:201,display_floor:1,x:0,w:48,h:9,layout:'single',
        nameKo:'통합중환자실',nameEn:'Mixed ICU'}]}
  });
  const unitDefinitions = new Map(Object.values(definitions).flatMap(h => h.units.map(u => [u.id,u])));
  const clone = value => typeof structuredClone === 'function' ? structuredClone(value) : JSON.parse(JSON.stringify(value));
  const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

  function project(data) {
    if (!data || !Array.isArray(data.floors) || data.facility_projection?.version === VERSION) return data;
    const out = clone(data);
    const originalUnits = new Map(data.floors.flatMap(f => f.units.map(u => [u.id,u])));
    const projectedUnits = new Map();
    const originalBedCount = data.facility_projection?.original_bed_count ??
      data.floors.reduce((n,f) => n + f.units.reduce((m,u) => m + u.beds.length,0),0);
    const originalUnitCount = data.facility_projection?.original_unit_count ?? originalUnits.size;

    for (const floor of out.floors) for (const unit of floor.units) {
      const definition = unitDefinitions.get(unit.id);
      if (!definition) continue;
      unit.beds = unit.beds.slice(0, definition.beds);
      if (definition.floor != null) {
        Object.assign(unit, {x:definition.x,w:definition.w,h:definition.h,display_floor:definition.display_floor,
          facility_layout:definition.layout});
        if (definition.nameEn) Object.assign(unit, {name:definition.nameEn,name_ko:definition.nameKo,name_en:definition.nameEn});
        const columns = definition.layout === 'single' ? definition.beds : Math.ceil(definition.beds / 2);
        unit.beds.forEach((bed,index) => {
          bed.x = definition.x + 4 + (index % columns) * 8;
          bed.y = definition.layout === 'single' || index < columns ? 2.5 : definition.h - 2.5;
        });
      }
      projectedUnits.set(unit.id,unit);
    }
    // A retains its source floors, wards and coordinates; only staff assignments change.
    out.floors = out.floors.map(f => ({...f,units:f.units.filter(u => definitions.A.units.some(d => d.id === u.id))}))
      .filter(f => f.units.length);
    for (const hospitalId of ['B','C']) {
      const local = definitions[hospitalId].units.map(d => projectedUnits.get(d.id)).filter(Boolean);
      if (local.length) out.floors.push({floor:definitions[hospitalId].units[0].floor,units:local});
    }

    const unitIds = new Set(projectedUnits.keys());
    const bedMap = new Map([...projectedUnits.values()].flatMap(u => u.beds.map(b => [b.id,b])));
    const bedIds = new Set(bedMap.keys());
    const allowedSlots = new Set([...unitIds].flatMap(id => ['C','1','2','3'].map(slot => `${id}-${slot}`)));
    out.nurses = (out.nurses || []).filter(n => unitIds.has(n.unit) && allowedSlots.has(n.id));
    out.roster = (out.roster || []).filter(n => unitIds.has(n.unit) && allowedSlots.has(n.slot_id || String(n.staff_id || '').replace(/^[DEN]-/,'')));
    out.doctors = (out.doctors || []).filter(d => unitIds.has(d.unit));
    const nurseIds = new Set(out.nurses.map(n => n.id));
    const staffIds = new Set(out.roster.map(n => n.staff_id).concat(out.nurses.map(n => n.staff_id || n.id)));
    const doctorIds = new Set(out.doctors.map(d => d.id));
    const sourceNurseIds = new Set((data.nurses || []).map(n => n.id));
    const sourceStaffIds = new Set((data.roster || []).map(n => n.staff_id).concat((data.nurses || []).map(n => n.staff_id || n.id)));
    const has = (set,value) => value == null || value === '' || set.has(value);
    const inScope = row => typeof row === 'string'
      ? (!sourceNurseIds.has(row) || nurseIds.has(row)) && (!sourceStaffIds.has(row) || staffIds.has(row))
      : !row || typeof row !== 'object' ||
      (has(unitIds,row.unit) && has(bedIds,row.bed) && has(bedIds,row.bed_id) &&
        has(nurseIds,row.nurse_id) && has(nurseIds,row.slot_id) && has(staffIds,row.staff_id) &&
        (!sourceNurseIds.has(row.id) || nurseIds.has(row.id)) &&
        (!sourceStaffIds.has(row.id) || staffIds.has(row.id)));
    const byScope = rows => (rows || []).filter(inScope);

    function scrubEvent(event) {
      if (Array.isArray(event.responders)) event.responders = event.responders.filter(id => nurseIds.has(id));
      if (Array.isArray(event.arrived)) event.arrived = event.arrived.filter(id => nurseIds.has(id));
      if (Array.isArray(event.responders) && Number.isFinite(event.need)) event.shortage = Math.max(0,event.need-event.responders.length);
      if (!has(doctorIds,event.doctor_id)) event.doctor_id = null;
      return event;
    }
    out.incidents = byScope(out.incidents).map(scrubEvent);
    const incidentIds = new Set(out.incidents.map(i => i.id));
    const removedIncidentIds = new Set((data.incidents || []).filter(i => !incidentIds.has(i.id)).map(i => i.id));
    for (const key of ['care_actions','activities','diagnostics','handover_receipts']) out[key] = byScope(out[key]);
    const diagnosticIds = new Set(out.diagnostics.map(d => d.id));
    const removedDiagnosticIds = new Set((data.diagnostics || []).filter(d => !diagnosticIds.has(d.id)).map(d => d.id));
    // Historical records remain historical; an incident may already be resolved.
    function scrubRecord(row) {
      for (const key of ['from_staff_id','to_staff_id','received_by']) if (!has(staffIds,row[key])) row[key] = null;
      if (!has(nurseIds,row.nurse)) row.nurse = null;
      if (!has(doctorIds,row.doctor_id)) row.doctor_id = null;
      if (removedIncidentIds.has(row.incident_id)) row.incident_id = null;
      if (removedDiagnosticIds.has(row.diagnostic_id)) row.diagnostic_id = null;
      const definition = unitDefinitions.get(row.unit);
      if ('floor' in row && definition?.floor != null) row.floor = definition.floor;
      return row;
    }
    const recordLists = ['patients','nurses','roster','staff','assignments','actions','care_actions','activities',
      'diagnostics','incidents','open_events','handover_receipts','receipts','questions'];
    function scrubContainer(container) {
      if (!container || typeof container !== 'object') return container;
      scrubRecord(container);
      if (container.responders || container.arrived) scrubEvent(container);
      if (Array.isArray(container.beds)) container.beds = container.beds.filter(b => typeof b === 'string' ? bedIds.has(b) : inScope(b)).map(b => typeof b === 'object' ? scrubContainer(b) : b);
      if (Array.isArray(container.cover)) container.cover = container.cover.filter(id => bedIds.has(id));
      for (const key of recordLists) if (Array.isArray(container[key])) container[key] = byScope(container[key]).map(scrubContainer);
      if (container.receipt) scrubContainer(container.receipt);
      if (Array.isArray(container.patients) && 'patient_count' in container) container.patient_count = container.patients.length;
      if (Array.isArray(container.patients) && 'open_event_count' in container) container.open_event_count = container.patients.reduce((n,p) => n + (p.open_events || []).length,0);
      return container;
    }
    for (const key of ['care_actions','activities','diagnostics','handover_receipts']) out[key].forEach(scrubContainer);
    if (out.last_handover) out.last_handover = scrubContainer(out.last_handover);
    for (const key of ['handover_history','completed_shifts']) out[key] = byScope(out[key]).map(scrubContainer);

    function relocate(person) {
      const definition = unitDefinitions.get(person.unit);
      if (definition.floor == null) return;
      const source = originalUnits.get(person.unit), target = projectedUnits.get(person.unit);
      person.floor = definition.floor;
      if (definition.layout === 'single') {
        const incident = out.incidents.find(i => i.id === person.incident);
        const originalBeds = source.beds.filter(b => bedIds.has(b.id));
        const nearest = incident?.bed ? originalBeds.find(b => b.id === incident.bed) :
          originalBeds.reduce((best,b) => !best || Math.hypot(b.x-person.x,b.y-person.y) < Math.hypot(best.x-person.x,best.y-person.y) ? b : best,null);
        person.x = nearest ? bedMap.get(nearest.id).x : target.x + target.w / 2;
        person.y = clamp(Number(person.y) / source.h * target.h,5.2,7.2);
      } else {
        person.x = target.x + (Number(person.x) - source.x) / source.w * target.w;
        person.y = Number(person.y) / source.h * target.h;
      }
    }
    for (const nurse of out.nurses) {
      nurse.beds = (nurse.beds || []).filter(id => bedIds.has(id));
      nurse.cover = (nurse.cover || []).filter(id => bedIds.has(id));
      nurse.care_actions = byScope(nurse.care_actions).map(scrubContainer);
      nurse.activities = byScope(nurse.activities).map(scrubContainer);
      if (!has(incidentIds,nurse.incident)) {
        nurse.incident = null;
        if (['moving','responding','incident','called'].includes(nurse.status)) nurse.status = 'care';
      }
      if (!has(diagnosticIds,nurse.diagnostic_id)) nurse.diagnostic_id = null;
      relocate(nurse);
    }
    for (const doctor of out.doctors) {
      if (!has(incidentIds,doctor.incident)) {
        doctor.incident = null;
        if (['moving','responding','incident','called'].includes(doctor.status)) doctor.status = 'available';
      }
      relocate(doctor);
    }

    // Retain existing N1–N3 assignments. Redistribute only orphaned assignments,
    // using bed geometry rather than moving staff positions so replay stays stable.
    for (const unit of projectedUnits.values()) {
      const bedside = out.nurses.filter(n => n.unit === unit.id && n.role !== 'charge')
        .sort((a,b) => a.id.localeCompare(b.id));
      const assigned = new Map(bedside.map(n => [n.id,unit.beds.filter(b => b.nurse === n.id)]));
      for (const bed of unit.beds) {
        if (nurseIds.has(bed.nurse) && out.nurses.some(n => n.id === bed.nurse && n.unit === unit.id)) continue;
        const candidates = bedside.map(n => {
          const beds = assigned.get(n.id), center = beds.length
            ? {x:beds.reduce((sum,b) => sum+b.x,0)/beds.length,y:beds.reduce((sum,b) => sum+b.y,0)/beds.length}
            : {x:unit.x+unit.w/2,y:unit.h/2};
          return {n,count:beds.length,distance:Math.hypot(center.x-bed.x,center.y-bed.y)};
        }).sort((a,b) => a.count-b.count || a.distance-b.distance || a.n.id.localeCompare(b.n.id));
        bed.nurse = candidates[0]?.n.id || null;
        if (bed.nurse) assigned.get(bed.nurse).push(bed);
      }
      for (const nurse of out.nurses.filter(n => n.unit === unit.id)) {
        const owned = unit.beds.filter(b => b.nurse === nurse.id).map(b => b.id);
        nurse.beds = [...new Set(nurse.beds.filter(id => owned.includes(id)).concat(owned))];
        nurse.cover = nurse.cover.filter(id => !owned.includes(id));
      }
    }
    for (const incident of out.incidents) {
      const definition = unitDefinitions.get(incident.unit);
      if (definition?.floor != null) incident.floor = definition.floor;
    }
    for (const bed of bedMap.values()) if (!has(nurseIds,bed.nurse)) bed.nurse = null;
    if (out.shift) Object.assign(out.shift,{on_duty:out.nurses.length,total_staff:out.roster.length});
    out.shift_schedule = (out.shift_schedule || []).map(s => ({...s,staff_count:out.roster.filter(n => n.shift_code === s.code).length}));
    out.log = out.activities.map(a => `${a.clock} · ${a.bed} · ${a.text}`);
    out.facility_projection = {
      version:VERSION, fictional:true,
      metrics_scope:'original_unprojected_network',
      metrics_note_ko:`운영 지표는 원본 3개 병원·${originalBedCount}병상과 원래 간호 인력 구성의 시뮬레이션 기준입니다.`,
      metrics_note_en:`Operational metrics retain the original three-hospital, ${originalBedCount}-bed simulation scope and its original staffing.`,
      original_unit_count:originalUnitCount, original_bed_count:originalBedCount,
      projected_unit_count:unitIds.size, projected_bed_count:bedIds.size,
      nurses_per_unit:4, charge_nurses_per_unit:1, bedside_nurses_per_unit:3,
      projected_nurse_count:out.nurses.length, projected_roster_count:out.roster.length,
      assignment_strategy:'retain_existing_then_lowest_bed_count_nearest_bed_centroid_and_slot_id'
    };
    return out;
  }
  return Object.freeze({definitions,project,forHospital:id => definitions[id] || null,version:VERSION});
});
