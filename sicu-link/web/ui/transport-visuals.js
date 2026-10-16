/* Original transport scene artwork. Callers own phase, movement and outcome.
 * All factories return SVG <g> fragments, without timers or clinical inference.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.SICUTransportVisuals = api;
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  function escape(value) {
    return String(value).replace(/[&<>"']/g, function (character) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character];
    });
  }

  function patientArt(deceased) {
    if (deceased) {
      return '<path class="transport-patient-sheet" d="M0-.94c.2 0 .28.13.28.29v.15c.1.08.15.18.15.32v.94q0 .16-.16.16h-.54q-.16 0-.16-.16v-.94c0-.14.05-.24.15-.32v-.15C-.28-.81-.2-.94 0-.94Z" fill="#E2E7ED" stroke="#8192A5" stroke-width=".045"/>' +
        '<path d="M-.24-.36q.24-.08.48 0M-.29.74h.58" fill="none" stroke="#C0CCD8" stroke-width=".04" stroke-linecap="round"/>';
    }
    return '<path d="M-.12-.49h.24v.23h-.24Z" fill="#EAF1F8"/>' +
      '<path class="transport-patient-body" d="M-.16-.32h.32q.25.03.28.32v.75H-.44V0q.03-.29.28-.32Z" fill="#EAF1F8" stroke="#7893AF" stroke-width=".04"/>' +
      '<path class="transport-patient-head" d="M.24-.68a.24.25 0 1 1-.48 0 .24.25 0 1 1 .48 0Z" fill="#EDF3F8" stroke="#718EAA" stroke-width=".045"/>' +
      '<path d="M-.23-.72q0-.21.23-.21t.23.21q-.22-.09-.46 0Z" fill="#597B9D"/>' +
      '<path class="transport-patient-blanket" d="M-.4-.2q.4-.08.8 0v.97q0 .13-.13.13h-.54q-.13 0-.13-.13Z" fill="#BFD9EF" stroke="#789ABD" stroke-width=".045"/>' +
      '<path d="M-.38-.08q.38-.06.76 0M-.28.74h.56" fill="none" stroke="#96B9D9" stroke-width=".04" stroke-linecap="round"/>' +
      '<path d="M-.29.04V.64" stroke="#F7FBFF" stroke-width=".045" stroke-linecap="round"/>';
  }

  function bedPatient(options) {
    const deceased = Boolean(options && options.deceased === true);
    return '<g class="transport-bed-patient" data-deceased="' + deceased + '" aria-hidden="true" pointer-events="none">' + patientArt(deceased) + '</g>';
  }

  function porter() {
    return '<g class="transport-porter" stroke-linecap="round" stroke-linejoin="round">' +
      '<ellipse cx="-2.08" cy=".86" rx=".34" ry=".085" fill="#183F65" opacity=".1"/>' +
      '<g class="transport-porter-feet"><g class="transport-porter-foot-left"><path d="M-2.22.32v.42" stroke="#345B7E" stroke-width=".13"/><path d="M-2.29.78h.2" stroke="#173F68" stroke-width=".11"/></g><g class="transport-porter-foot-right"><path d="M-1.94.32v.42" stroke="#345B7E" stroke-width=".13"/><path d="M-1.97.78h.2" stroke="#173F68" stroke-width=".11"/></g></g>' +
      '<g class="transport-porter-bob"><g class="transport-porter-arms"><path d="m-1.91-.18.26-.19.29-.05m-.54.49.25.22.29.08" fill="none" stroke="#DFEAF5" stroke-width=".17"/>' +
      '<path d="m-1.91-.18.26-.19.29-.05m-.54.49.25.22.29.08" fill="none" stroke="#3C7B9F" stroke-width=".085"/></g>' +
      '<path d="M-2.23-.32h.3q.22.1.22.34v.4h-.73v-.4q0-.24.21-.34Z" fill="#287B9A" stroke="#4A6F91" stroke-width=".045"/>' +
      '<path d="m-2.22-.29.14.17.14-.17" fill="none" stroke="#FFFFFF" stroke-width=".065"/>' +
      '<path d="M-1.85.09h.12v.13h-.12Z" fill="#FFFFFF" opacity=".35"/>' +
      '<path d="M-1.85-.62a.24.27 0 1 1-.48 0 .24.27 0 1 1 .48 0Z" fill="#EAF1F8" stroke="#527597" stroke-width=".045"/>' +
      '<path d="M-2.33-.67q0-.24.24-.24t.24.24q-.23-.12-.48 0Z" fill="#173F68"/>' +
      '<path d="M-2.17-.48q.08.04.16 0" fill="none" stroke="#93ADC5" stroke-width=".035"/>' +
      '</g>' +
      '<path d="M-1.28-.42a.075.065 0 1 1-.15 0 .075.065 0 1 1 .15 0Zm0 .76a.075.065 0 1 1-.15 0 .075.065 0 1 1 .15 0Z" fill="#EAF1F8" stroke="#7894AE" stroke-width=".035"/>' +
      '</g>';
  }

  function cart(options) {
    options = options || {};
    const occupied = options.occupied === true;
    const deceased = options.deceased === true;
    const facing = Number(options.facing) < 0 ? -1 : 1;
    const title = occupied ? (deceased ? '이송침대 · 사망 시나리오' : '환자 탑승 이송침대') : '빈 이송침대';
    return '<g class="transport-cart" data-occupied="' + occupied + '" data-deceased="' + deceased + '" data-facing="' + facing + '" transform="scale(' + facing + ' 1)" aria-hidden="true" pointer-events="none" stroke-linecap="round" stroke-linejoin="round">' +
      '<title>' + title + '</title><ellipse cx=".35" cy=".1" rx="1.87" ry=".86" fill="#153E64" opacity=".045"/>' +
      '<g class="transport-cart-castors" fill="#6D86A1" stroke="#FFFFFF" stroke-width=".035">' +
      '<path d="M-1.12-.8a.1.1 0 1 1 .2 0 .1.1 0 1 1-.2 0Zm2.83 0a.1.1 0 1 1 .2 0 .1.1 0 1 1-.2 0ZM-1.12.8a.1.1 0 1 1 .2 0 .1.1 0 1 1-.2 0Zm2.83 0a.1.1 0 1 1 .2 0 .1.1 0 1 1-.2 0Z"/></g>' +
      '<path d="M-1.02-.69v-.1M1.81-.69v-.1M-1.02.69v.1M1.81.69v.1" stroke="#7894B0" stroke-width=".055"/>' +
      '<rect class="transport-cart-frame" x="-1.32" y="-.68" width="3.45" height="1.36" rx=".16" fill="#F3F7FC" stroke="#7293B5" stroke-width=".065"/>' +
      '<rect class="transport-cart-mattress" x="-1.2" y="-.56" width="3.2" height="1.12" rx=".12" fill="#FFFFFF" stroke="#CCD9E7" stroke-width=".04"/>' +
      '<rect class="transport-cart-pillow" x="-1.11" y="-.43" width=".61" height=".86" rx=".12" fill="#FAFCFF" stroke="#91ACC6" stroke-width=".045"/>' +
      '<g class="transport-cart-patient" opacity="' + (occupied ? '1' : '0') + '" transform="translate(.28 0) rotate(-90) scale(.92 1.43)">' + patientArt(deceased) + '</g>' +
      '<path class="transport-cart-rails" d="M-.26-.77H1.62m-1.88 1.54H1.62M-.16-.68v-.09m1.65.09v-.09M-.16.68v.09m1.65-.09v.09" fill="none" stroke="#6488AB" stroke-width=".055"/>' +
      '<path class="transport-cart-handle" d="M-1.32-.42h-.16v.84h.16" fill="none" stroke="#547A9F" stroke-width=".065"/>' +
      porter() + '</g>';
  }

  function door(options) {
    options = options || {};
    const numeric = Number(options.open);
    const open = Number.isFinite(numeric) ? Math.min(1, Math.max(0, numeric)) : 0;
    const distance = Number((1.9 * open).toFixed(4));
    const id = 'sicu-transport-door-' + String(options.id || 'entry').replace(/[^A-Za-z0-9_-]/g, '-');
    const safeId = escape(id);
    return '<g class="transport-door" data-open="' + open + '" aria-hidden="true" pointer-events="none">' +
      '<title>ICU 출입문</title><defs><clipPath id="' + safeId + '" clipPathUnits="userSpaceOnUse"><rect x="-.46" y="-2" width=".92" height="4"/></clipPath></defs>' +
      '<g class="transport-door-leaves doubleleaves" clip-path="url(#' + safeId + ')">' +
      '<g class="transport-door-leaf transport-door-leaf-upper" transform="translate(0 -' + distance + ')"><rect x="-.17" y="-1.9" width=".34" height="1.9" rx=".035" fill="#DCE8F4" stroke="#6D90B2" stroke-width=".055"/><path d="M-.065-1.63v1.2" stroke="#F9FCFF" stroke-width=".05"/></g>' +
      '<g class="transport-door-leaf transport-door-leaf-lower" transform="translate(0 ' + distance + ')"><rect x="-.17" y="0" width=".34" height="1.9" rx=".035" fill="#DCE8F4" stroke="#6D90B2" stroke-width=".055"/><path d="M-.065.43v1.2" stroke="#F9FCFF" stroke-width=".05"/></g>' +
      '</g><path class="transport-door-frame" d="M-.3-2V2M.3-2V2M-.43-2h.86M-.43 2h.86" fill="none" stroke="#8BA7C2" stroke-width=".065" stroke-linecap="round"/>' +
      '</g>';
  }

  function porterTransform(rotation, facing) {
    const angle=Number(rotation)||0,flip=Number(facing)<0?-1:1;
    const mirror=Math.cos(angle*Math.PI/180)*flip<-.5?-1:1;
    // Keep the same front-facing camera as the nursing team while the cart turns.
    return 'translate(-2.08 0) scale('+flip+' 1) rotate('+(-angle)+') scale('+mirror+' 1) translate(2.08 0)';
  }

  function gait(distance,walking){
    const traveled=Math.max(0,Number(distance)||0),phase=walking?traveled/3.2*Math.PI*2:0,wave=walking?Math.sin(phase):0;
    return {walking:Boolean(walking),distance:traveled,phase,left:wave*11,right:-wave*11,
      bob:walking?-.035*Math.abs(Math.sin(phase*2)):0,arms:wave*1.8};
  }
  const poseNodes=new WeakMap();
  function posePorter(porter,options){
    const o=options||{},pose=gait(o.distance,o.walking);
    if(!porter)return pose;
    let parts=poseNodes.get(porter);
    if(!parts){parts={feet:porter.querySelector('.transport-porter-feet'),left:porter.querySelector('.transport-porter-foot-left'),right:porter.querySelector('.transport-porter-foot-right'),body:porter.querySelector('.transport-porter-bob'),arms:porter.querySelector('.transport-porter-arms')};poseNodes.set(porter,parts);}
    const set=(el,key,value)=>{if(el&&el.getAttribute(key)!==String(value))el.setAttribute(key,String(value));};
    set(porter,'transform',porterTransform(o.rotation,o.facing));set(porter,'data-walking',pose.walking);set(porter,'data-walk-distance',pose.distance);
    set(parts.feet,'data-phase',pose.phase);set(parts.left,'transform',`rotate(${pose.left} -2.22 .32)`);set(parts.right,'transform',`rotate(${pose.right} -1.94 .32)`);
    set(parts.body,'transform',`translate(0 ${pose.bob})`);set(parts.arms,'transform',`rotate(${pose.arms} -1.32 .12)`);
    return pose;
  }

  return Object.freeze({ cart: cart, door: door, bedPatient: bedPatient, porterTransform: porterTransform, gait:gait,posePorter:posePorter });
});
