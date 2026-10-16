/* Original clinician figures. Upstream owns identity, status and movement.
 * The four named child nodes remain compatible with the native draw loop.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.SICUStaffVisuals = api;
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';

  function escape(value) {
    return String(value).replace(/[&<>"']/g, function (character) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character];
    });
  }

  function uniformColor(staff, isDoctor) {
    if (isDoctor) return '#FFFFFF';
    return staff && staff.role === 'charge' ? '#76518F' : '#287B9A';
  }

  function avatar(staff, isDoctor) {
    staff = staff || {};
    const charge = !isDoctor && staff.role === 'charge';
    const number = String(staff.id || '').match(/\d+$/);
    const identifier = isDoctor ? 'Dr.' : charge ? 'NC' : number ? 'N' + number[0] : 'N';
    const role = isDoctor ? 'Physician' : charge ? 'Charge nurse' : 'Nurse';
    const torso = uniformColor(staff, isDoctor);
    // Hair identifies the role consistently in the map, legend and nurse sheet.
    const hairStyle = charge ? 'bun' : 'bob';
    const originalOutline = 'M0-1.5c-.34 0-.58.27-.58.6 0 .27.13.45.3.54v.06C-.76-.2-1 .05-1 .43V.7q0 .12.14.12H.86Q1 .82 1 .7V.43C1 .05.76-.2.28-.3v-.06C.45-.45.58-.63.58-.9.58-1.23.34-1.5 0-1.5Z';
    const outline = isDoctor ? originalOutline : hairStyle === 'bun'
      ? 'M0-1.55c-.37 0-.63.28-.63.65 0 .28.16.48.35.56v.04C-.76-.2-1 .05-1 .43V.7q0 .12.14.12H.86Q1 .82 1 .7V.43C1 .05.76-.2.28-.3v-.04q.2-.1.27-.31c.25.04.4-.1.4-.32 0-.21-.15-.34-.37-.32C.5-1.43.29-1.55 0-1.55Z'
      : 'M0-1.55c-.4 0-.67.27-.67.66l-.06.53q.23.13.45.02v.04C-.76-.2-1 .05-1 .43V.7q0 .12.14.12H.86Q1 .82 1 .7V.43C1 .05.76-.2.28-.3v-.04q.22.11.45-.02L.67-.89c0-.39-.27-.66-.67-.66Z';
    const hairBack = isDoctor ? '' : hairStyle === 'bun'
      ? '<path class="sicu-clinician-hair-back sicu-nurse-bun" d="M.4-.97c0-.18.11-.28.27-.28s.26.1.26.28-.1.28-.26.28S.4-.79.4-.97Z" fill="#173F68"/><path class="sicu-nurse-hair-seam" d="M.69-1.12q.13.12.01.29" fill="none" stroke="#6585A4" stroke-width=".045" stroke-linecap="round"/>'
      : '<path class="sicu-clinician-hair-back sicu-nurse-bob" d="M-.6-.97q0-.52.6-.52t.6.52l.07.56q-.18.13-.41.02h-.52q-.23.11-.41-.02Z" fill="#173F68"/>';
    const hairFront = isDoctor
      ? '<path class="sicu-clinician-cap" d="M-.49-1.02q-.01-.47.49-.47t.49.47Q.25-1.15 0-1.15t-.49.13Z" fill="#173F68"/>'
      : hairStyle === 'bun'
        ? '<path class="sicu-clinician-hair-front" d="M-.51-.96c-.02-.37.16-.54.51-.54s.53.22.53.54v.22L.4-.81l-.07-.27Q.08-1.08-.08-1.29q-.14.26-.43.33Z" fill="#173F68"/><path class="sicu-nurse-hair-part" d="M-.08-1.29q.21-.12.4.08" fill="none" stroke="#6585A4" stroke-width=".045" stroke-linecap="round"/>'
        : '<path class="sicu-clinician-hair-front" d="M-.55-1q0-.5.55-.5t.55.5v.45L.38-.66l-.08-.4Q.04-1.11-.12-1.31q-.14.28-.43.31Z" fill="#173F68"/><path class="sicu-nurse-hair-part" d="M-.12-1.31q.2-.1.39.06" fill="none" stroke="#6585A4" stroke-width=".045" stroke-linecap="round"/>';
    const coat = isDoctor
      ? '<path class="sicu-clinician-coat" d="M-.22-.26 0 .11.22-.26M-.34-.2-.19.16 0 .31.19.16.34-.2M0 .31V.7" fill="none" stroke="#8CA5BC" stroke-width=".055"/>' +
        '<path class="sicu-clinician-stethoscope" d="M-.27-.21V.13Q-.27.39 0 .39T.27.13V-.21M0 .39V.52Q0 .65.16.65H.31" fill="none" stroke="#315F89" stroke-width=".07"/>' +
        '<path class="sicu-clinician-chestpiece" d="M.43.65a.12.12 0 1 1-.24 0 .12.12 0 1 1 .24 0Z" fill="#E9F1F8" stroke="#315F89" stroke-width=".055"/>'
      : '<path class="sicu-clinician-collar" d="M-.23-.25 0-.02.23-.25" fill="none" stroke="#FFFFFF" stroke-width=".095"/>' +
        '<path class="sicu-clinician-pocket" d="M.32.23h.24v.19H.32Z" fill="#FFFFFF" fill-opacity=".2" stroke="#FFFFFF" stroke-opacity=".55" stroke-width=".035"/>';
    const leader = charge
      ? '<path class="sicu-charge-badge" d="m.46-.13.19-.07.19.07v.2Q.84.25.65.32.46.25.46.07Z" fill="#E0B963" stroke="#FFFFFF" stroke-width=".035"/>' +
        '<path class="sicu-charge-badge-mark" d="m.55.05.07.07.13-.14" fill="none" stroke="#193F66" stroke-width=".055"/>'
      : '';

    return '<g class="staff-avatar sicu-staff-avatar" data-clinician-role="' + (isDoctor ? 'physician' : charge ? 'charge' : 'nurse') + '" data-visual-style="' + (isDoctor ? 'classic' : hairStyle) + '">' +
      '<title>' + escape(role + ' · ' + (staff.id || 'Fictional staff')) + '</title>' +
      '<path class="avatar-care" d="' + outline + '" fill="#FFFFFF" stroke="#BACCDD" stroke-width=".105" stroke-linejoin="round"/>' +
      hairBack +
      '<path class="avatar-scrubs" d="M-.24-.28h.48l.36.15Q.87-.02.87.29V.7H-.87V.29q0-.31.27-.42Z" fill="' + torso + '" stroke="#476C8D" stroke-width=".055" stroke-linejoin="round"/>' +
      '<path class="sicu-clinician-neck" d="M-.16-.58h.32v.28L0-.1-.16-.3Z" fill="#EAF1F8"/>' +
      '<path class="sicu-clinician-face" d="M-.46-1.02q0-.43.46-.43t.46.43v.13c0 .3-.18.48-.46.48s-.46-.18-.46-.48Z" fill="#EAF1F8" stroke="#456A8D" stroke-width=".055"/>' +
      hairFront +
      '<path class="sicu-clinician-face-line" d="M-.15-.64q.15.08.3 0" fill="none" stroke="#91A9C0" stroke-width=".045" stroke-linecap="round"/>' +
      coat + leader +
      '<path class="sicu-staff-id-surface" d="M-.6.8h1.2q.15 0 .15.15v.28q0 .15-.15.15H-.6q-.15 0-.15-.15V.95q0-.15.15-.15Z" fill="#153F6A" stroke="#FFFFFF" stroke-width=".035"/>' +
      '<text class="staff-glyph sicu-staff-id" x="0" y="1.225" fill="#FFFFFF" text-anchor="middle" font-size=".5" font-weight="700" font-family="Pretendard,Arial,sans-serif" letter-spacing="0">' + escape(identifier) + '</text>' +
      '</g>';
  }

  return Object.freeze({ avatar: avatar, uniformColor: uniformColor });
});
