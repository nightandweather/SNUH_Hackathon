/* Minimal operational projection for the coordination prototype. The hospital
 * workspace keeps its source records; this DTO carries anonymous bed slots only.
 */
(function(root,factory){
  const common=typeof module==='object'&&module.exports;
  const api=factory(root,common?require('./facility-profiles.js'):null);
  if(common)module.exports=api;if(root)root.SICUCoordinationModel=api;
})(typeof window!=='undefined'?window:null,function(root,dependency){
  'use strict';
  const finite=value=>typeof value==='number'&&Number.isFinite(value);
  const prepKeys=['staff','equipment','cleaning'];
  const emptyPrep=()=>({eligible:0,confirmed:0,pending:0,unknown:0,turnover:0,
    requirements:Object.fromEntries(prepKeys.map(key=>[key,{confirmed:0,pending:0,unknown:0}]))});
  const emptySupport=()=>({eventCount:0,needKnown:0,needUnknownCount:0,assignedCount:0,arrivedCount:0,pendingCount:0,shortageKnown:0,shortageUnknownCount:0});
  const emptyCounts=()=>({total:0,occupied:0,empty:0,reserved:0,turnover:0,nurses:0,physicians:0,ready:0,unknownPrep:0,pendingPrep:0,reservations6h:0,support:0,activeTransport:0});
  function clockAt(clock,now,at){
    const parts=String(clock||'07:00').split(':').map(Number);
    const base=Number.isFinite(parts[0])&&Number.isFinite(parts[1])?parts[0]*60+parts[1]:420;
    const value=((base-now+at)%1440+1440)%1440;
    return String(Math.floor(value/60)).padStart(2,'0')+':'+String(Math.floor(value%60)).padStart(2,'0');
  }
  function merge(items,clock,now){
    const counts=emptyCounts(),preparation=emptyPrep(),support=emptySupport(),times=new Map();
    for(const item of items){
      for(const key of Object.keys(counts))counts[key]+=item.counts[key];
      for(const key of ['eligible','confirmed','pending','unknown','turnover'])preparation[key]+=item.preparation[key];
      for(const key of prepKeys)for(const state of ['confirmed','pending','unknown'])preparation.requirements[key][state]+=item.preparation.requirements[key][state];
      for(const key of Object.keys(support))support[key]+=item.support[key];
      for(const group of item.arrivals.groups)times.set(group.at,(times.get(group.at)||0)+group.count);
    }
    const groups=[...times].sort((a,b)=>a[0]-b[0]).map(([at,count])=>({at,clock:clockAt(clock,now,at),count}));
    return {counts,preparation,support,arrivals:{count:groups.reduce((sum,group)=>sum+group.count,0),groups},activeTransport:counts.activeTransport};
  }
  function derive(input,options={}){
    const facility=dependency||root?.FacilityProfiles;
    const data=(options.project||facility?.project||((value)=>value))(input||{floors:[]});
    const now=finite(data.t)?data.t:0,clock=String(data.clock||''),horizon=360;
    const hospitalMap=new Map();
    for(const floor of data.floors||[])for(const unit of floor.units||[]){
      const hospital=String(unit.hospital_id||'A'),counts=emptyCounts(),preparation=emptyPrep(),support=emptySupport(),times=new Map();
      const sourceBeds=unit.beds||[],bedIds=new Set(sourceBeds.map(bed=>bed.id));
      const beds=sourceBeds.map((bed,index)=>{
        const occupied=Boolean(bed.patient),kind=occupied?'occupied':bed.unavailable?'turnover':bed.reservation?'reserved':'vacant';
        counts.total++;counts[kind==='vacant'?'empty':kind]++;
        if(!occupied){
          preparation.eligible++;
          const record=bed.operational_readiness||{};
          for(const key of prepKeys)preparation.requirements[key][record[key]===true?'confirmed':record[key]===false?'pending':'unknown']++;
          const pending=prepKeys.some(key=>record[key]===false),unknown=prepKeys.some(key=>record[key]!==true&&record[key]!==false);
          if(kind==='turnover')preparation.turnover++;
          else if(pending){preparation.pending++;counts.pendingPrep++;}
          else if(unknown){preparation.unknown++;counts.unknownPrep++;}
          else{preparation.confirmed++;if(kind==='vacant')counts.ready++;}
        }
        const expected=bed.reservation?.expected_t;
        if(kind==='reserved'&&finite(expected)&&expected>=now&&expected<=now+horizon)times.set(expected,(times.get(expected)||0)+1);
        if(bed.flow&&finite(bed.flow.stage)&&bed.flow.stage>=0&&bed.flow.stage<4)counts.activeTransport++;
        return {index,kind,occupied,x:Number(bed.x),y:Number(bed.y)};
      });
      for(const event of data.incidents||[]){
        if(!bedIds.has(event.bed)||event.type==='focus')continue;
        const assigned=[...new Set(event.responders||[])],arrived=[...new Set(event.arrived||[])];
        support.eventCount++;support.assignedCount+=assigned.length;support.arrivedCount+=arrived.length;
        support.pendingCount+=assigned.filter(id=>!arrived.includes(id)).length;
        if(finite(event.need)){const need=Math.max(0,event.need);support.needKnown+=need;support.shortageKnown+=Math.max(0,need-assigned.length);}
        else{support.needUnknownCount++;support.shortageUnknownCount++;}
      }
      counts.nurses=(data.nurses||[]).filter(person=>person.unit===unit.id).length;
      counts.physicians=(data.doctors||[]).filter(person=>person.unit===unit.id).length;
      counts.support=support.eventCount;
      const groups=[...times].sort((a,b)=>a[0]-b[0]).map(([at,count])=>({at,clock:clockAt(clock,now,at),count}));
      const arrivals={count:groups.reduce((sum,group)=>sum+group.count,0),groups};counts.reservations6h=arrivals.count;
      const safeUnit={id:String(unit.id||''),hospital,name:String(unit.name||unit.id||''),
        nameKo:String(unit.name_ko||unit.name||unit.id||''),nameEn:String(unit.name_en||unit.name||unit.id||''),
        floor:unit.display_floor??floor.floor??null,floorId:floor.floor??null,
        layout:unit.facility_layout||'paired',facility_layout:unit.facility_layout||'paired',
        geometry:{x:Number(unit.x),w:Number(unit.w),h:Number(unit.h)},bedCount:beds.length,beds,
        counts,preparation,arrivals,support,activeTransport:counts.activeTransport};
      if(!hospitalMap.has(hospital)){
        const definition=facility?.forHospital?.(hospital);
        hospitalMap.set(hospital,{id:hospital,name:String(unit.hospital_name||'Demo Hospital '+hospital),
          typeKo:definition?.typeKo||'',typeEn:definition?.typeEn||'',units:[]});
      }
      hospitalMap.get(hospital).units.push(safeUnit);
    }
    const hospitals=[...hospitalMap.values()].map(hospital=>({...hospital,...merge(hospital.units,clock,now)}));
    const summary=merge(hospitals,clock,now),units=hospitals.flatMap(hospital=>hospital.units);
    const rows=units.map(unit=>({hospital:unit.hospital,unit:unit.id,nameKo:unit.nameKo,nameEn:unit.nameEn,floor:unit.floor,
      counts:unit.counts,preparation:unit.preparation,arrivals:unit.arrivals,support:unit.support,activeTransport:unit.activeTransport}));
    return {version:'coordination-operational-v1',clock,now,horizon,
      totals:{hospitals:hospitals.length,units:units.length,...summary.counts},preparation:summary.preparation,
      arrivals:summary.arrivals,support:summary.support,hospitals,
      work:{arrivals:rows.filter(row=>row.arrivals.count>0),preparation:rows.filter(row=>row.preparation.eligible>0),support:rows.filter(row=>row.support.eventCount>0)}};
  }
  return Object.freeze({derive,version:'coordination-operational-v1'});
});
