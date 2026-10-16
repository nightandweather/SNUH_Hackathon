/* Pure network view of recorded beds, preparation and team work. No clinical rules. */
(function (root,factory) {
  const common = typeof module === 'object' && module.exports;
  const dependencies = common ? {facility:require('./facility-profiles.js'),operations:require('./operations-model.js')} : {};
  const api = factory(root,dependencies);
  if (common) module.exports = api;
  if (root) root.SICUNetworkModel = api;
})(typeof window !== 'undefined' ? window : null,function (root,dependencies) {
  'use strict';
  const clone = value => value == null ? value : typeof structuredClone === 'function' ? structuredClone(value) : JSON.parse(JSON.stringify(value));
  const unitsOf = data => (data?.floors || []).flatMap(f => f.units || []);
  const finite = value => typeof value === 'number' && Number.isFinite(value);

  function localScope(data,hospital,unitId='') {
    const floors = (data.floors || []).map(f => ({...f,units:(f.units || []).filter(u =>
      (u.hospital_id || 'A') === hospital && (!unitId || u.id === unitId))})).filter(f => f.units.length);
    const ids = new Set(floors.flatMap(f => f.units.map(u => u.id)));
    const beds = new Set(floors.flatMap(f => f.units.flatMap(u => u.beds.map(b => b.id))));
    return {...data,floors,nurses:(data.nurses || []).filter(n => ids.has(n.unit)),
      doctors:(data.doctors || []).filter(n => ids.has(n.unit)),roster:(data.roster || []).filter(n => ids.has(n.unit)),
      incidents:(data.incidents || []).filter(i => beds.has(i.bed))};
  }
  function profileFor(provider,id) {
    if (typeof provider === 'function') return provider(id) || null;
    if (typeof provider?.forHospital === 'function') return provider.forHospital(id) || null;
    return provider?.definitions?.[id] || provider?.[id] || null;
  }
  function defaultStatus(bed) {
    if (bed.patient) return {key:'unknown',label:'Unknown',color:'#8192a3'};
    if (bed.reservation) return {key:'reserved',label:'RESERVED',color:'#fff1b8'};
    return {key:'empty',label:'EMPTY',color:'#e7ebf0'};
  }
  function counts(beds,ops,state) {
    const statuses = {};
    beds.forEach(bed => {statuses[bed.statusKey] = (statuses[bed.statusKey] || 0)+1;});
    return {total:beds.length,occupied:beds.filter(b => b.kind==='occupied').length,
      empty:beds.filter(b => b.kind==='vacant').length,reserved:beds.filter(b => b.kind==='reserved').length,
      turnover:beds.filter(b => b.kind==='turnover').length,nurses:(state.nurses || []).length,
      physicians:(state.doctors || []).length,ready:ops.readyCount || 0,unknownPrep:ops.unknownPrepCount || 0,
      pendingPrep:ops.pendingPrepCount || 0,reservations6h:(ops.reservations6h || []).length,
      support:(ops.support || []).length,critical:statuses.critical || 0,watch:statuses.watch || 0,
      stable:statuses.stable || 0,unknownClinical:beds.filter(b => b.unknownClinical).length,
      activeTransport:ops.metrics?.activeTransport || 0,statuses};
  }
  function derive(data,options={}) {
    const facility = dependencies.facility || root?.FacilityProfiles;
    const operations = options.operations || dependencies.operations || root?.SICUOperationsModel;
    const operationsDerive = typeof operations === 'function' ? operations : operations?.derive;
    if (typeof operationsDerive !== 'function') throw new TypeError('SICUNetworkModel requires SICUOperationsModel.derive.');
    const project = options.project || facility?.project || (value => value);
    const scope = options.scope || localScope;
    const profileProvider = options.profiles || facility;
    const status = typeof options.status === 'function' ? options.status : null;
    const input = data && Array.isArray(data.floors) ? data : {floors:[],nurses:[],doctors:[],roster:[],incidents:[]};
    const raw = project(input),sourceUnits = unitsOf(raw);
    const opsFor = state => clone(operationsDerive(state));
    const globalOps = opsFor(raw);
    const hospitalIds = [...new Set(sourceUnits.map(u => u.hospital_id || 'A'))];
    const work = {arrivals:[],support:[],preparation:[]};
    const hospitals = hospitalIds.map(id => {
      const state = scope(raw,id,''),hospitalOps = opsFor(state),definition = profileFor(profileProvider,id);
      const hospitalUnits = unitsOf(state),name = hospitalUnits[0]?.hospital_name || 'Demo Hospital '+id;
      const operationalBeds = new Map(hospitalOps.beds.map(b => [b.id,b]));
      const units = hospitalUnits.map(unit => {
        const unitState = scope(raw,id,unit.id),ops = opsFor(unitState);
        const floor = state.floors.find(f => f.units.some(u => u.id === unit.id));
        const beds = unit.beds.map(bed => {
          const operational = operationalBeds.get(bed.id);
          // A native/local flow already contains its explicit display state.
          const display = bed.flow?.status || (bed.patient && status ? status(bed.patient) : null) || defaultStatus(bed);
          const kind = operational.kind,unknownClinical = Boolean(bed.patient && (!display.key || display.key==='unknown'));
          return {id:bed.id,number:String(bed.id).split('-').pop(),unit:unit.id,hospital:id,
            x:Number(bed.x),y:Number(bed.y),kind,occupied:Boolean(bed.patient),
            statusKey:display.key || 'unknown',color:display.color || '#8192a3',
            statusLabel:display.label || display.key || 'Unknown',label:display.label || display.key || 'Unknown',
            ink:display.ink || null,unknownClinical,
            prep:operational.prep,unknown:operational.prep==='unknown',ready:kind==='vacant'&&operational.prep==='confirmed',
            requirements:clone(operational.requirements),missing:[...operational.missing],pending:[...operational.pending],
            owner:operational.owner,expected_t:operational.expected_t,reservation:clone(operational.reservation),
            flow:clone(operational.flow),acceptance:null};
        });
        const unitCounts = counts(beds,ops,unitState);
        return {id:unit.id,hospital:id,name:unit.name,nameKo:unit.name_ko || unit.name,nameEn:unit.name_en || unit.name,
          floor:unit.display_floor ?? floor?.floor ?? null,floorId:floor?.floor ?? null,
          layout:unit.facility_layout || 'paired',facility_layout:unit.facility_layout || 'paired',
          geometry:{x:Number(unit.x),w:Number(unit.w),h:Number(unit.h)},bedCount:beds.length,beds,
          counts:unitCounts,nurseCount:unitCounts.nurses,physicianCount:unitCounts.physicians,ops,acceptance:null};
      });
      const beds = units.flatMap(unit => unit.beds),hospitalCounts = counts(beds,hospitalOps,state);
      const names = new Map(units.map(unit => [unit.id,unit.name]));
      const tag = row => ({...clone(row),hospital:id,hospitalId:id,hospitalName:name,unitName:names.get(row.unit) || row.unit});
      work.arrivals.push(...hospitalOps.reservations6h.map(tag));
      work.support.push(...hospitalOps.support.map(tag));
      work.preparation.push(...hospitalOps.beds.filter(b => b.kind!=='occupied').map(row => tag({...row,bed:row.id})));
      return {id,name,typeKo:definition?.typeKo || null,typeEn:definition?.typeEn || null,
        type:definition?{ko:definition.typeKo || null,en:definition.typeEn || null}:null,
        profile:clone(definition),units,counts:hospitalCounts,nurseCount:hospitalCounts.nurses,
        physicianCount:hospitalCounts.physicians,ops:hospitalOps,acceptance:null};
    });
    work.arrivals.sort((a,b) => a.expected_t-b.expected_t || a.hospital.localeCompare(b.hospital) || a.bed.localeCompare(b.bed));
    const beds = hospitals.flatMap(h => h.units.flatMap(u => u.beds));
    return {clock:raw.clock || '',now:finite(raw.t)?raw.t:0,horizon:globalOps.horizon,
      scope:sourceUnits.map(u => u.id),totals:{hospitals:hospitals.length,units:sourceUnits.length,...counts(beds,globalOps,raw)},
      hospitals,work,acceptance:null,sourceScope:clone(raw.facility_projection || null)};
  }
  return Object.freeze({derive,version:'network-operations-v1'});
});
