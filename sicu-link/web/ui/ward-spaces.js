/* One ICU per visual row. Original interactive nodes and source coordinates
 * are moved into unit viewports; the native floor controllers keep their joins.
 */
(() => {
  'use strict';
  const NS='http://www.w3.org/2000/svg';
  const views=[];
  let doorRules=null,doorSignature='';
  const current=()=>typeof S!=='undefined'&&S?S:null;
  const ko=()=>document.documentElement.lang.startsWith('ko');
  const t=(a,b)=>ko()?a:b;
  const namesKo={'Cardiovascular Surgical ICU':'심혈관외과 중환자실','Neurosurgical ICU':'신경외과 중환자실','Surgical ICU':'외과 중환자실','Trauma Surgical ICU':'외상외과 중환자실','Mixed ICU':'통합중환자실'};
  function svg(tag,attrs,parent){const node=document.createElementNS(NS,tag);Object.entries(attrs||{}).forEach(([key,value])=>node.setAttribute(key,String(value)));if(parent)parent.append(node);return node;}
  function names(unit){const english=unit.name_en||unit.name||unit.id;return {ko:unit.name_ko||namesKo[english]||english,en:english};}
  function bilingual(unit){const pair=names(unit);return ko()?pair.ko+' ('+pair.en+')':pair.en+' ('+pair.ko+')';}
  function contexts(){
    const model=current();if(!model)return [];
    const units=new Map(model.floors.flatMap(floor=>floor.units.map(unit=>[unit.id,{unit,floor}])));
    return views.filter(view=>view.row.isConnected&&units.has(view.id)).map(view=>Object.assign(view,units.get(view.id)));
  }
  function contextForUnit(id){return contexts().find(view=>view.id===id)||null;}
  function labels(){
    const model=current();if(!model)return;
    for(const view of contexts()){
      const pair=names(view.unit),floor=view.unit.display_floor??view.floor.floor;
      view.floorLabel.textContent=String(floor)+'F';view.code.textContent=view.unit.id;
      view.title.textContent=ko()?pair.ko:pair.en;
      view.subtitle.textContent='('+(ko()?pair.en:pair.ko)+')';
      const concept=view.unit.id==='C-SICU'?t('단일 병동 · 개별실 중심','Single unit · mainly individual rooms'):
        view.unit.id.startsWith('B-')?t('소규모 ICU · 개별실 중심','Compact ICU · mainly individual rooms'):
        t('개방형 / 개별실 혼합','Mixed open bays / individual rooms');
      view.caption.textContent=view.unit.beds.length+t('병상 · ',' beds · ')+concept+t(' · 가상 배치',' · fictional layout');
      view.row.setAttribute('aria-label',String(floor)+'F · '+bilingual(view.unit));
      view.svg.querySelectorAll('.spatial-station-label').forEach(node=>node.textContent=t('간호 스테이션','Nurse station'));
      const sourceTitle=view.svg.querySelector(':scope > text.unit-t');
      if(sourceTitle)sourceTitle.textContent=bilingual(view.unit);
    }
    // The source dropdown retains sibling wards while S is narrowed to one ICU.
    const allUnits=[...model.floors,...(window.SICULinkState?.raw?.floors||[])].flatMap(floor=>floor.units);
    document.querySelectorAll('#wardScope option,#rosterUnit option').forEach(option=>{
      const unit=allUnits.find(unit=>unit.id===option.value);if(!unit)return;
      option.dataset.noTranslate='';option.textContent=unit.id+' · '+bilingual(unit);
    });
  }
  function arrange(){
    const model=current();if(!model?.floors)return;
    // A rebuild replaces #floors children; discard detached view metadata only.
    for(let i=views.length-1;i>=0;i--)if(!views[i].row.isConnected)views.splice(i,1);
    document.querySelectorAll('#floors > .floor').forEach((element,index)=>{
      const floor=model.floors[index];if(!floor)return;
      if(element.dataset.wardSpacesReady==='true')return;
      const viewport=element.querySelector(':scope > .ward-map-viewport'),source=viewport?.querySelector(':scope > svg');
      if(!source)return;
      const backgrounds=[...source.querySelectorAll(':scope > rect.unit-r')];
      const titles=[...source.querySelectorAll(':scope > text.unit-t')].filter(node=>node.textContent.trim()!=='E/V');
      viewport.classList.remove('ward-map-viewport');viewport.classList.add('ward-map-source');viewport.hidden=true;
      source.setAttribute('aria-hidden','true');source.setAttribute('focusable','false');
      element.classList.add('ward-spaces-floor');element.dataset.wardSpacesReady='true';
      floor.units.forEach((unit,unitIndex)=>{
        const row=document.createElement('div');row.className='ward-space-row';row.dataset.wardId=unit.id;
        row.dataset.floor=String(unit.display_floor??floor.floor);row.dataset.sourceFloor=String(floor.floor);
        row.dataset.layoutKind=window.SpatialMap.layoutKind(unit);
        const meta=document.createElement('div');meta.className='ward-space-meta';meta.dataset.noTranslate='';
        const floorLabel=document.createElement('strong');floorLabel.className='ward-space-floor';
        const code=document.createElement('span');code.className='ward-space-code';
        const title=document.createElement('h3');title.className='ward-space-unit-name';
        const subtitle=document.createElement('p');subtitle.className='ward-space-unit-english';
        const caption=document.createElement('small');caption.className='ward-space-caption';
        meta.append(floorLabel,code,title,subtitle,caption);row.append(meta);
        const map=document.createElement('div');map.className='ward-space-map ward-map-viewport';row.append(map);
        const canvas=svg('svg',{'data-ward-id':unit.id,'data-source-floor':floor.floor,xmlns:NS},map);
        const e=Number(model.elevator_x),left=Math.min(Number(unit.x),e-3),right=Math.max(Number(unit.x)+Number(unit.w),e+2.7)+.6;
        canvas.setAttribute('viewBox',[left-1,-1.6,right-left+1,Number(unit.h)+4].join(' '));
        canvas.style.minWidth=Math.max(760,Number(unit.w)/8*(unit.facility_layout==='single'?144:180)+120)+'px';
        svg('rect',{class:'corr',x:e-3,y:0,width:6,height:unit.h},canvas);
        if(backgrounds[unitIndex])canvas.append(backgrounds[unitIndex]);
        const architecture=[...source.querySelectorAll('.spatial-architecture')].find(node=>node.dataset.spatialUnit===unit.id);
        if(architecture)canvas.append(architecture);
        if(titles[unitIndex])canvas.append(titles[unitIndex]);
        for(const bed of unit.beds){const group=typeof bedEl!=='undefined'?bedEl[bed.id]?.r.parentElement:null;if(group){group.dataset.bedId=bed.id;group.dataset.wardId=unit.id;canvas.append(group);}}
        const linksLayer=svg('g',{class:'ward-space-links','pointer-events':'none','aria-hidden':'true'},canvas);
        const staffLayer=svg('g',{class:'ward-space-staff'},canvas);
        element.append(row);views.push({id:unit.id,row,svg:canvas,unit,floor,floorLabel,code,title,subtitle,caption,linksLayer,staffLayer});
      });
      source.querySelectorAll('.clinical-procedure-room,.clinical-elevator-marker,.clinical-occupants,.staff-assignment-layer').forEach(node=>node.remove());
    });
    labels();
  }
  function staff(){
    const model=current();if(!model)return;
    const lookup=new Map(contexts().map(view=>[view.id,view]));
    for(const [person,doctor]of [...model.nurses.map(person=>[person,false]),...(model.doctors||[]).map(person=>[person,true])]){
      const marker=doctor?doctorEl[person.id]:nurseEl[person.id],view=lookup.get(person.unit);
      if(marker&&view&&marker.parentNode!==view.staffLayer)view.staffLayer.append(marker);
    }
  }
  function links(replace){
    const model=current();if(!model)return;
    const maps=contexts();if(replace)maps.forEach(view=>view.linksLayer.replaceChildren());
    for(const floor of model.floors){
      const source=typeof linkG!=='undefined'?linkG[floor.floor]:null;if(!source)continue;
      for(const line of [...source.children]){
        const x=Number(line.getAttribute('x1')),y=Number(line.getAttribute('y1'));
        const view=maps.find(view=>view.floor.floor===floor.floor&&view.unit.beds.some(bed=>Math.abs(Number(bed.x)-x)<.01&&Math.abs(Number(bed.y)-y)<.01));
        if(view)view.linksLayer.append(line);
      }
    }
  }
  function doors(){
    // An open bay has no individual room door. ICU entrance doors remain native.
    // A declarative rule also covers transport layers created between source draws.
    const openBeds=contexts().flatMap(view=>view.unit.beds.filter(bed=>window.SpatialMap.isOpenBed(view.unit,bed)).map(bed=>String(bed.id)));
    const signature=JSON.stringify(openBeds);if(signature===doorSignature)return;
    doorSignature=signature;
    if(!doorRules){doorRules=document.createElement('style');doorRules.id='wardSpaceDoorRules';document.head.append(doorRules);}
    doorRules.textContent=openBeds.map(id=>{
      const escaped=CSS.escape(id);
      return '.ward-space-map .sicu-native-transport[data-native-bed="'+escaped+'"] .native-transport-room-door,'+
        '.ward-space-map .transport-story-layer[data-transport-bed="'+escaped+'"] .transport-story-room-door{display:none}';
    }).join('\n');
  }
  function decorate(){
    arrange();if(!contexts().length)return;
    window.SICUClinicalMap?.decorate();staff();links(false);window.SICUStaff?.syncSelection();doors();labels();
  }
  window.SICUWardSpaces=Object.freeze({contexts,contextForUnit,decorate,bilingual});
  const nativeBuild=window.build;window.build=function(){const result=nativeBuild.apply(this,arguments);decorate();return result;};
  const nativeDraw=window.draw;window.draw=function(){
    const focused=document.activeElement;
    const mapFocus=focused?.matches('#floors g[role="button"]')&&
      (focused.classList.contains('nurse')||focused.classList.contains('doctor')||focused.hasAttribute('data-bed-id'))?focused:null;
    const result=nativeDraw.apply(this,arguments);decorate();
    // Native staff redraw briefly returns the same interactive node to its hidden
    // controller SVG. Recover only a focus lost by that move, never a new choice.
    if(mapFocus?.isConnected&&document.activeElement===document.body&&!document.querySelector('dialog[open],.modal.open'))mapFocus.focus({preventScroll:true});
    return result;
  };
  const nativeLinks=window.drawLinks;window.drawLinks=function(){const result=nativeLinks.apply(this,arguments);links(true);return result;};
  const nativeDetail=window.detail;window.detail=function(){const result=nativeDetail.apply(this,arguments);staff();return result;};
  document.addEventListener('icu-language',()=>queueMicrotask(()=>{labels();staff();window.SICUClinicalMap?.decorate();window.SICUStaff?.syncSelection();}));
  decorate();
})();
