/* Code-native equipment glyphs and an explicitly labelled drain placement. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;if(root)root.SICUDeviceVisuals=api;})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  const E=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const paths={
    oxygen:'<path d="M7 4h10v4l-2 2v9H9v-9L7 8Zm3 0V2h4v2M9 14h6M5 10v4a3 3 0 0 0 3 3h1"/>',
    ventilator:'<rect x="3" y="3" width="14" height="15" rx="2"/><path d="M6 8h2l2-3 2 6 2-3M7 14h6M8 18v3m-3 0h8m4-11h2q2 0 2 2v4"/>',
    iv:'<path d="M12 2v20M8 3h8M8 5H5v8l3 2 3-2V5H8m4 13h6q3 0 3-3v-3M9 22h6"/><path d="M5 10h6"/>',
    central_line:'<path d="M11 3v6q0 3 3 3h4q3 0 3 3v5M8 3h6M3 21h6v-5H3Zm3-5V9q0-3 3-3h2M16 15h5"/>',
    arterial_line:'<path d="M3 8h5l2-4 4 14 3-10h4M6 15v6m-3 0h6"/><circle cx="6" cy="12" r="3"/>',
    urinary_catheter:'<path d="M6 3v6q0 3 3 3h3V7h8v13h-8v-8M12 10h8M15 14h2m-2 3h2M5 3h2"/>',
    drain:'<path d="M4 3v6q0 3 3 3h5v-3h8v12h-8v-9M12 13h8m-5 3h2m-2 3h2"/>',
    ecmo:'<circle cx="7" cy="12" r="5"/><path d="m6 9 3 3-3 3M12 6h8v15h-8M15 9h2m-2 3h2m-2 3h2M7 7V3h9v3"/>',
    crrt:'<rect x="12" y="5" width="8" height="15" rx="2"/><path d="M16 2v3M3 3h5v8H3Zm2 8v5q0 3 3 3h4m3-10 3 7m0-7-3 7M2 3h7"/>'
  };
  function icon(key){return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(paths[key]||paths.drain)+'</svg>';}
  function overlay(model,options={}){
    const ko=options.language!=='en';
    return (model.renderSites||[]).filter(s=>s.deviceKey==='drain').map((s,i)=>{
      const x=+(s.position.x*300).toFixed(2),y=+(s.position.y*420).toFixed(2),example=s.sourceKind==='fictional_example';
      const bagX=232-i*38,bagY=329;
      return '<g class="device-site-marker" data-device-site="'+E(s.id)+'" data-device-key="drain" data-site-kind="'+E(s.sourceKind)+'" data-site-x="'+x+'" data-site-y="'+y+'" pointer-events="none"><title>'+E(s.label+' · '+s.source)+'</title><path d="M'+x+' '+y+'C'+(x+33)+' '+y+' '+bagX+' '+(y+29)+' '+bagX+' '+(bagY-8)+'" stroke="#AC6857" stroke-width="2.2" stroke-dasharray="'+(example?'4 3':'none')+'" fill="none"/><circle cx="'+x+'" cy="'+y+'" r="5" fill="#FFF2EC" stroke="#AC6857" stroke-width="1.8"/><circle cx="'+x+'" cy="'+y+'" r="1.7" fill="#AC6857"/><path d="M'+(bagX-5)+' '+(bagY-8)+'h10v8h8v35q0 5-5 5h-16q-5 0-5-5v-35h8Z" fill="#FFF9F4" stroke="#AC6857" stroke-width="1.5"/><path d="M'+(bagX-12)+' '+(bagY+10)+'h24m-18 8h5m-5 7h5m-5 7h5" fill="none" stroke="#C89786" stroke-width="1"/><text x="'+bagX+'" y="'+(bagY+57)+'" text-anchor="middle" fill="#8C5042" font-size="11" font-weight="600" stroke="none">'+(example?(ko?'배액관 · 예시':'Drain · example'):(ko?'배액관 · 기록':'Drain · recorded'))+'</text></g>';
    }).join('');
  }
  return Object.freeze({icon,overlay});
});
