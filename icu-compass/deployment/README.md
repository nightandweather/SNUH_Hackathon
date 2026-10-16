# Canonical ICU presentation

User requirement: KHDP and shared-site entry points must show the same published UI.

- Canonical presentation: https://icu-ward-board-20261016.kanghoun.chatgpt.site/
- KHDP presentation entry: https://s4w66hdi1zteriq8oyfb8wzm.khdp.net/proxy/8006/
- The KHDP presentation entry navigates to the canonical presentation. Publishing the canonical Site updates both entry points without a second UI deployment.
- Language, hospital, ward and nurse-slot preferences are allowlisted. Do not forward arbitrary query parameters, credentials, source case IDs or chat content.
- Existing authenticated developer/live-simulation UI remains at `/proxy/8006/?view=private`. This explicitly private tool is separate from the shared presentation.
- Real K-MIMIC record discussion remains at `/proxy/8007/`; do not redirect it or publish its records or API keys.
- `install_shared_entry.py` idempotently places `shared-entry.js` into the head of the dashboard. Preserve this block on subsequent deployments to KHDP.
- This unifies application versions and presentation entry points, not browser-local simulation state. Visitors retain independent sandbox state. Cross-user live state requires an explicitly implemented shared state backend.

The public Site source is `../../public-icu-preview`, with build output in `dist/`. Publish using the Sites workflow; never substitute a separately modified KHDP presentation release as the canonical version.
