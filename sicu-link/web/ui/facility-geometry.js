/* Place the existing interactive staff in each facility's visible corridor. */
(() => {
  'use strict';
  window.layoutStaff=function(){
    staffPositions={};
    for(const floor of S.floors)for(const unit of floor.units){
      const columns=Math.round(Number(unit.w)/8);
      const slots=unit.facility_layout==='single'
        ? Array.from({length:columns},(_,i)=>({x:Number(unit.x)+4+i*8,y:5.25}))
        : [5.2,8.3].flatMap(y=>Array.from({length:columns},(_,i)=>({x:Number(unit.x)+4+i*8,y})));
      const used=new Set();
      const people=[...S.nurses.filter(n=>n.unit===unit.id),...(S.doctors||[]).filter(d=>d.unit===unit.id)];
      for(const person of people){
        const next=slots.map((position,index)=>({position,index,distance:Math.hypot(position.x-person.x,position.y-person.y)})).filter(item=>!used.has(item.index)).sort((a,b)=>a.distance-b.distance || a.index-b.index)[0];
        if(next){used.add(next.index);staffPositions[person.id]=next.position;}
      }
    }
  };
  function labels(){
    if(typeof S==='undefined' || !S)return;
    document.querySelectorAll('#floors>.floor').forEach((floorElement,index)=>{
      const floor=S.floors[index];if(!floor)return;
      for(const unit of floor.units){
        if(!unit.name_ko)continue;
        const label=[...floorElement.querySelectorAll('text.unit-t')].find(node=>node.dataset.facilityUnit===unit.id || node.textContent===unit.name);
        if(label){label.dataset.facilityUnit=unit.id;label.dataset.noTranslate='';label.textContent=FacilityRuntime.unitName(unit);}
      }
    });
  }
  const nativeBuild=window.build;
  window.build=function(){const result=nativeBuild.apply(this,arguments);labels();return result;};
  const nativeDraw=window.draw;
  window.draw=function(){
    // Network.navigate uses its private select, so every native draw needs the same geometry.
    if(typeof S!=='undefined' && S?.facility_projection)S=FacilityRuntime.geometry(S);
    const result=nativeDraw.apply(this,arguments);
    FacilityRuntime.decorate();
    return result;
  };
  document.addEventListener('icu-language',()=>queueMicrotask(labels));
  if(typeof S!=='undefined' && S){built=false;window.draw();}
})();
