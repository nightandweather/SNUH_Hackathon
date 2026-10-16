/* Presentation adapters installed before the unmodified application starts. */
(() => {
  'use strict';
  const nativeStatus = Readiness.status;
  Readiness.status = patient => {
    const status = nativeStatus(patient);
    return {...status, label: status.assessment.decision};
  };
  // The source evaluator still supplies color keys. Advisory UI is intentionally omitted.
  Readiness.render = () => '';
  Readiness.badges = () => '';
  Readiness.intro = () => {};
  Readiness.updateIntro = () => {};
  function trimColorLegend() {
    document.querySelectorAll('.side .legend>span').forEach(span => {
      const text=span.textContent.trim(),match=text.match(/^(RED|BLUE|GREEN)\s*·/);
      if(match){const square=span.querySelector('.sq');span.dataset.noTranslate='';span.replaceChildren(...(square?[square]:[]),document.createTextNode(match[1]));}
      else if(/Transfer-review draft|전실.*초안/.test(text))span.remove();
    });
  }
  document.addEventListener('DOMContentLoaded',trimColorLegend);
  document.addEventListener('icu-language',()=>queueMicrotask(trimColorLegend));
  const state = window.SICULinkState = {raw: null, notify: null};
  const nativeSelect = Network.select;
  Network.select = function (data) {
    state.raw = data;
    const result = nativeSelect.apply(this, arguments);
    queueMicrotask(() => state.notify?.());
    return result;
  };
})();
