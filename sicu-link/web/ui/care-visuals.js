/* Original vector artwork. No patient waveform or clinical inference. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;if(root)root.SICUVisuals=api;})(typeof window!=='undefined'?window:null,function(){
  'use strict';
  function bed(options){
    options=options||{};
    const occupied=options.occupied!==false;
    const width=Number(options.width)||160,height=Number(options.height)||236;
    const linen=occupied
      ? '<path d="M44 88Q80 82 116 88V177Q80 181 44 177Z" fill="var(--bed-cover,#E7F0F9)" stroke="var(--bed-edge,#7896B4)" stroke-width="1.15"/><path d="M45 100Q80 96 115 100M48 170Q80 173 112 170" fill="none" stroke="var(--bed-edge,#7896B4)" stroke-opacity=".5" stroke-width="1.1"/><path d="M52 106V163" fill="none" stroke="#FFF" stroke-width="2" stroke-linecap="round"/>'
      : '<path d="M44 153H116V178H44Z" fill="var(--bed-cover,#E7F0F9)" stroke="var(--bed-edge,#7896B4)" stroke-width="1.1"/><path d="M45 160H115" stroke="var(--bed-edge,#7896B4)" stroke-opacity=".45" stroke-width="1.1"/>';
    const art='<g stroke-linecap="round" stroke-linejoin="round">'+
      '<path d="M36 32V18Q36 12 43 12H117Q124 12 124 18V32" fill="var(--bed-head,#D9E6F3)" stroke="var(--bed-frame,#5B7C9E)" stroke-width="1.5"/>'+
      '<path d="M30 202V213H130V202" fill="#EDF3F8" stroke="var(--bed-frame,#5B7C9E)" stroke-width="1.3"/>'+
      '<g fill="#FFF" stroke="var(--bed-frame,#5B7C9E)" stroke-width="1.4"><rect x="31" y="208" width="14" height="11" rx="4"/><rect x="115" y="208" width="14" height="11" rx="4"/><path d="M38 210V217M122 210V217"/></g>'+
      '<rect x="30" y="25" width="100" height="180" rx="13" fill="var(--bed-platform,#F5F8FC)" stroke="var(--bed-frame,#5B7C9E)" stroke-width="1.6"/>'+
      '<rect x="37" y="32" width="86" height="161" rx="10" fill="var(--bed-mattress,#FFF)" stroke="var(--bed-seam,#C9D7E6)" stroke-width="1.1"/>'+
      '<rect x="47" y="43" width="66" height="32" rx="9" fill="var(--bed-pillow,#F8FBFE)" stroke="var(--bed-edge,#7896B4)" stroke-width="1.2"/>'+
      '<path d="M54 49Q80 45 106 49" fill="none" stroke="var(--bed-seam,#C9D7E6)" stroke-width="1"/>'+linen+
      '<g fill="var(--bed-rail,#EDF3FA)" stroke="var(--bed-frame,#5B7C9E)" stroke-width="1.4"><rect x="22" y="89" width="7" height="66" rx="3.5"/><rect x="131" y="89" width="7" height="66" rx="3.5"/></g>'+
      '<path d="M25.5 98V145M134.5 98V145" stroke="#FFF" stroke-width="1.3"/>'+
      '<rect x="139" y="111" width="10" height="24" rx="3" fill="#FFF" stroke="var(--bed-frame,#5B7C9E)" stroke-width="1.2"/>'+
      '<circle cx="144" cy="118" r="1.4" fill="var(--bed-accent,#0160BA)"/><path d="M142 124H146M142 128H146" stroke="var(--bed-edge,#7896B4)" stroke-width="1"/>'+
      '<path d="M40 190H120V201H40Z" fill="var(--bed-head,#D9E6F3)" stroke="var(--bed-frame,#5B7C9E)" stroke-width="1.35"/>'+
      '<path d="M48 195H112" stroke="#FFF" stroke-width="1.4"/></g>';
    return '<svg xmlns="http://www.w3.org/2000/svg" width="'+width+'" height="'+height+'" viewBox="0 0 160 236" class="sicu-bed-topview" fill="none" aria-hidden="true" focusable="false"><g'+(options.orientation==='south'?' transform="rotate(180 80 118)"':'')+'>'+art+'</g></svg>';
  }
  function mark(size){
    size=Number(size)||64;
    return '<svg xmlns="http://www.w3.org/2000/svg" width="'+size+'" height="'+size+'" viewBox="0 0 64 64" fill="none" aria-hidden="true" focusable="false">'+
      '<path d="M23 8H41C45.4 8 49 11.6 49 16V48C49 52.4 45.4 56 41 56H23C18.6 56 15 52.4 15 48V16C15 11.6 18.6 8 23 8Z" fill="#0C3C6E"/>'+
      '<rect x="22" y="15" width="20" height="12" rx="4" fill="#FFF"/>'+
      '<path d="M22 34H42V46C42 47.7 40.7 49 39 49H25C23.3 49 22 47.7 22 46V34Z" fill="#FFF"/>'+
      '<path d="M22 34C27 32.7 37 32.7 42 34" stroke="#0160BA" stroke-width="2"/>'+
      '<path d="M9 26V39M55 25V38" stroke="#0160BA" stroke-width="3.5" stroke-linecap="round"/>'+
      '<path d="M4 32H9M55 31H60" stroke="#0160BA" stroke-width="2"/>'+
      '<circle cx="3" cy="32" r="2.5" fill="#0160BA"/><circle cx="61" cy="31" r="2.5" fill="#0160BA"/>'+
      '</svg>';
  }
  return Object.freeze({bed:bed,topview:bed,mark:mark});
});
