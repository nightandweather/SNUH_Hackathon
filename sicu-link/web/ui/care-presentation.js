/* Six distinct care indicators and a real top-view bed, presentation only.
 * Load after Network and care-visuals.js, before the upstream main script.
 * Call SICUCare.decorate() after the preserved application's draw().
 */
(function (root) {
  'use strict';
  if (root.SICUCare) return;

  const definitions = [
    ['cpr_today', 'cpr', '당일 CPR', 'CPR today', '#A53740'],
    ['ecmo', 'ecmo', 'ECMO', 'ECMO', '#255CAA'],
    ['crrt', 'crrt', 'CRRT', 'CRRT', '#7155A1'],
    ['pressor_unstable', 'pressor', '승압제·불안정', 'Pressor / unstable', '#8B611B'],
    ['ventilator', 'ventilation', '인공호흡기', 'Ventilator', '#24766E'],
    ['surgery_today', 'surgery', '당일 수술', 'Surgery today', '#5D638C'],
  ];
  const paths = {
    cpr: '<path d="M20.2 5.1a5 5 0 0 0-7.1 0L12 6.2l-1.1-1.1A5 5 0 0 0 3.8 12L12 20l8.2-8a5 5 0 0 0 0-6.9Z"/><path d="M2.5 12h4l1.8-3.2 3.1 7.1 2.8-5.1 1.5 2.2h5.8"/>',
    ecmo: '<rect x="14" y="3" width="6.5" height="12" rx="1.6"/><path d="M16.2 6h2.1m-2.1 2.7h2.1m-2.1 2.7h2.1M14 6H8a4 4 0 0 0-4 4v2.1M7 19.5v1h10.3V15"/><circle cx="7" cy="15.5" r="4"/><path d="m5.5 13.8 3.2 1.7-3.2 1.7"/>',
    crrt: '<path d="M4 2.5v2m0 0H2.5v6.2A1.3 1.3 0 0 0 3.8 12h3.4a1.3 1.3 0 0 0 1.3-1.3V4.5H4Z"/><path d="M5.5 7v2.5M5.5 12v6a3 3 0 0 0 3 3H15m3-14V3h3.5"/><rect x="14" y="7" width="7" height="11" rx="2"/><path d="m16 10 3 5m-3-1.7L19 10M17.5 18v3H21"/>',
    pressor: '<path d="m5 16 3 3 8-8-3-3-8 8Zm1.5 1.5-4 4m9-15 6 6m-3-3 4-4m-2-2 4 4m-10.5 3 2 2m-4 0 2 2"/>',
    ventilation: '<path d="M12 3v7m0-3L9 9m3-2 3 2M8.2 7.5C6 8.2 3.1 12.1 3 16.5c-.1 3.2 1.4 4.5 4 3.6l2.4-.9c1.1-.4 1.8-1.5 1.8-2.7V12L8.2 7.5Zm7.6 0c2.2.7 5.1 4.6 5.2 9 .1 3.2-1.4 4.5-4 3.6l-2.4-.9a2.9 2.9 0 0 1-1.8-2.7V12l3-4.5Z"/>',
    surgery: '<path d="m3 15.6 10.4-12 4 3.6-10.9 11.5L3 20l.1-4.4Zm7-8 4.1 3.6"/><circle cx="17.5" cy="17.5" r="4"/><path d="M17.5 15v2.8l1.7 1"/>',
  };
  const signatures = new WeakMap();
  const bedSignatures = new WeakMap();

  function language(explicit) {
    if (explicit) return explicit === 'ko' ? 'ko' : 'en';
    return document.documentElement.lang.startsWith('ko') ? 'ko' : 'en';
  }

  function state(value) {
    return value === true ? true : value === false ? false : null;
  }

  function statesFor(patient) {
    const values = patient ? Network.careIndicators(patient) : {};
    return Object.fromEntries(definitions.map(function (definition) {
      return [definition[0], state(values[definition[0]])];
    }));
  }

  function stateLabel(value, lang) {
    return value === true ? (lang === 'ko' ? '해당' : 'Active') :
      value === false ? (lang === 'ko' ? '없음' : 'Not active') :
        (lang === 'ko' ? '미확인' : 'Unknown');
  }

  function icon(name) {
    return '<svg class="clinical-care-symbol" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + paths[name] + '</svg>';
  }

  function stripContents(states, lang, legend) {
    return definitions.map(function (definition) {
      const key = definition[0], value = states[key];
      const label = definition[lang === 'ko' ? 2 : 3];
      const status = stateLabel(value, lang);
      const token = value === true ? 'true' : value === false ? 'false' : 'null';
      const example = lang === 'ko' ? '활성 표시 예시' : 'Active example';
      return '<span class="care-badge ' + (value === true ? 'is-active' : value === false ? 'is-inactive' : 'is-unknown') +
        '" data-care-key="' + key + '" data-care-state="' + token + '" style="--care-color:' + definition[4] +
        '" title="' + label + ' · ' + (legend ? example : status) +
        '" aria-label="' + label + ' · ' + (legend ? example : status) + '">' +
        '<span class="care-icon">' + icon(definition[1]) +
        (value === null ? '<span class="unknown-mark" aria-hidden="true">?</span>' : '') +
        '</span><span class="care-label">' + label + '</span><span class="care-state">' +
        (legend ? '' : status) + '</span></span>';
    }).join('');
  }

  function setStrip(strip, states, lang, legend) {
    const signature = JSON.stringify([lang, Boolean(legend), states]);
    if (signatures.get(strip) === signature && strip.querySelector('[data-care-key="crrt"]')) return;
    strip.classList.add('sicu-care-strip');
    strip.dataset.noTranslate = '';
    strip.innerHTML = stripContents(states, lang, legend);
    signatures.set(strip, signature);
  }

  function mapIcons(patient) {
    const states = statesFor(patient), lang = language();
    return definitions.map(function (definition, index) {
      const value = states[definition[0]];
      const label = definition[lang === 'ko' ? 2 : 3] + ' · ' + stateLabel(value, lang);
      const color = value === true ? definition[4] : '#8291A2';
      const glyphColor = value === true ? '#FFFFFF' : color;
      return '<g class="sicu-map-care" data-care-key="' + definition[0] + '" data-care-state="' +
        (value === true ? 'true' : value === false ? 'false' : 'null') +
        '" transform="translate(' + (index * .75) + ' 0)" role="img" aria-label="' + label + '" data-no-translate="">' +
        '<title>' + label + '</title><rect x="0" y=".04" width=".69" height=".72" rx=".1" fill="' +
        (value === true ? color : '#F5F7FA') + '" stroke="' + color + '" stroke-width=".035"' +
        (value === null ? ' stroke-dasharray=".08 .06"' : '') + '/>' +
        '<svg x=".055" y=".105" width=".58" height=".58" viewBox="0 0 24 24" style="width:.58px;height:.58px" fill="none" color="' + glyphColor +
        '" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + paths[definition[1]] + '</svg>' +
        (value === null ? '<text x=".53" y=".81" font-size=".3" fill="#52647A">?</text>' : '') + '</g>';
    }).join('');
  }

  function patientArtwork(factory) {
    if (typeof factory === 'function') return factory({ deceased: false });
    // A first paint can precede the optional transport artwork. Keep the same
    // north-facing head/blanket grammar until that factory becomes available.
    return '<g fill="none" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M-.12-.49h.24v.23h-.24Z" fill="#EAF1F8"/>' +
      '<path d="M-.16-.32h.32q.25.03.28.32v.75H-.44V0q.03-.29.28-.32Z" fill="#EAF1F8" stroke="#7893AF" stroke-width=".04"/>' +
      '<path d="M.24-.68a.24.25 0 1 1-.48 0 .24.25 0 1 1 .48 0Z" fill="#EDF3F8" stroke="#718EAA" stroke-width=".045"/>' +
      '<path d="M-.23-.72q0-.21.23-.21t.23.21q-.22-.09-.46 0Z" fill="#597B9D"/>' +
      '<path d="M-.4-.2q.4-.08.8 0v.97q0 .13-.13.13h-.54q-.13 0-.13-.13Z" fill="#BFD9EF" stroke="#789ABD" stroke-width=".045"/>' +
      '<path d="M-.38-.08q.38-.06.76 0M-.28.74h.56" stroke="#96B9D9" stroke-width=".04"/>' +
      '</g>';
  }

  function topView(occupied, factory, patientFactory) {
    let markup = typeof factory === 'function' ? factory({ occupied: occupied, width: 80, height: 118 }) :
      '<svg class="sicu-bed-topview" viewBox="0 0 80 118" fill="none" aria-hidden="true"><g stroke="#5B7C9E" stroke-width="1.2"><rect x="17" y="8" width="46" height="98" rx="7" fill="#F5F8FC"/><rect x="21" y="14" width="38" height="84" rx="5" fill="#FFF"/><rect x="26" y="20" width="28" height="16" rx="4"/><path d="M13 44v33m54-33v33M24 100h32" stroke-linecap="round"/></g></svg>';
    markup = markup.replace('<svg ', '<svg data-occupied="' + occupied + '" ');
    if (!occupied) return markup;
    const bounds = markup.match(/viewBox=["']\s*[-.\d]+\s+[-.\d]+\s+([.\d]+)\s+([.\d]+)\s*["']/);
    const width = bounds ? Number(bounds[1]) : 160;
    const height = bounds ? Number(bounds[2]) : 236;
    const figure = '<g class="patient-card-occupant" data-occupied="true" data-source="bed.patient" aria-hidden="true" pointer-events="none" transform="translate(' + (width / 2) + ' ' + (height * 109 / 236) + ') scale(' + (width * .45) + ')">' + patientArtwork(patientFactory) + '</g>';
    return markup.replace(/<\/svg>\s*$/, figure + '</svg>');
  }

  function replaceBedDrawings(card, occupied) {
    const existing = Array.from(card.querySelectorAll('.clinical-bed-visual'));
    const legacy = Array.from(card.querySelectorAll('svg.patient-bed-drawing'));
    let visual = existing.shift();
    existing.forEach(function (duplicate) { duplicate.remove(); });
    if (!visual) {
      visual = document.createElement('span');
      visual.className = 'clinical-bed-visual';
      visual.setAttribute('aria-hidden', 'true');
      visual.dataset.noTranslate = '';
      if (legacy.length) legacy.shift().replaceWith(visual);
      else {
        // Native flow cards contain no bed SVG, but their real patient occupancy
        // follows the same source record as every other patient-list row.
        const heading = card.querySelector('.card-top');
        if (heading) heading.after(visual); else card.appendChild(visual);
      }
    }
    legacy.forEach(function (old) { old.remove(); });
    const factory = root.SICUVisuals && (root.SICUVisuals.topview || root.SICUVisuals.bed);
    const patientFactory = root.SICUTransportVisuals && root.SICUTransportVisuals.bedPatient;
    const previous = bedSignatures.get(visual);
    const occupantCount = visual.querySelectorAll('.patient-card-occupant').length;
    if (!previous || previous.occupied !== occupied || previous.factory !== factory ||
        previous.patientFactory !== patientFactory || !visual.querySelector('svg') || occupantCount !== (occupied ? 1 : 0)) {
      visual.innerHTML = topView(occupied, factory, patientFactory);
      bedSignatures.set(visual, { occupied: occupied, factory: factory, patientFactory: patientFactory });
    }
    visual.dataset.occupied = String(occupied);
    visual.dataset.bedId = card.dataset.patient;
  }

  function decorate() {
    const lang = language();
    let model;
    try { model = typeof S !== 'undefined' ? S : null; } catch (_) { return; }
    const beds = new Map();
    if (model && model.floors) model.floors.forEach(function (floor) {
      floor.units.forEach(function (unit) {
        unit.beds.forEach(function (bed) { beds.set(bed.id, bed); });
      });
    });
    document.querySelectorAll('#patientCards .patient-card[data-patient]').forEach(function (card) {
      const bed = beds.get(card.dataset.patient);
      if (!bed) return;
      const values = statesFor(bed.patient);
      card.querySelectorAll('.care-strip').forEach(function (strip) { setStrip(strip, values, lang, false); });
      replaceBedDrawings(card, Boolean(bed.patient));
    });
    const legend = document.getElementById('careIconLegend');
    if (legend) {
      legend.setAttribute('aria-label',lang==='ko'?'6개 간호 상태':'Six care indicators');
      const allActive = Object.fromEntries(definitions.map(function (definition) { return [definition[0], true]; }));
      let strip = legend.querySelector('.sicu-care-legend');
      if (!strip) {
        strip = document.createElement('span');
        strip.className = 'care-strip care-key sicu-care-legend';
        legend.replaceChildren(strip);
      }
      setStrip(strip, allActive, lang, true);
    }
  }

  function decoratePublic(bed, explicitLanguage) {
    if (!bed || !bed.patient) return;
    const body = document.getElementById('publicPatientBody');
    if (!body) return;
    const heading = Array.from(body.children).find(function (element) {
      return element.tagName === 'H3' && /간호 상태|Care indicators/i.test(element.textContent);
    });
    if (!heading) return;
    let next = heading.nextElementSibling;
    // Only replace the care rows in their original section. Anatomy,
    // vital signs, source paragraphs and dialog controls remain original nodes.
    while (next && next.tagName === 'DIV') {
      const remove = next;
      next = next.nextElementSibling;
      remove.remove();
    }
    const strip = document.createElement('div');
    strip.className = 'care-strip sicu-detail-care';
    setStrip(strip, statesFor(bed.patient), language(explicitLanguage), false);
    heading.after(strip);
  }

  // Keep both upstream evidence functions intact, including any combined view.
  // Only the map's presentation renderer is replaced.
  if (typeof Network !== 'undefined') Network.careMapIcons = mapIcons;
  if (typeof root.openPublicBed === 'function') {
    const originalOpenPublicBed = root.openPublicBed;
    root.openPublicBed = function (bed, lang) {
      const result = originalOpenPublicBed.apply(this, arguments);
      decoratePublic(bed, lang);
      return result;
    };
  }
  root.SICUCare = Object.freeze({ decorate: decorate, decoratePublic: decoratePublic });
})(window);
