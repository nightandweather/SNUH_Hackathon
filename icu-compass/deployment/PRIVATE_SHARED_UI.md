# Canonical presentation on the private clinical server

Port 8007 `/` now uses `static/shared-clinical.html`. The previous evidence layout remains at `/evidence.html`. Port 8006 and its canonical public redirect remain unchanged.

`analysis/build_private_shared_shell.py` copies the canonical public presentation CSS and care pictograms from `../public-icu-preview/dist`, then combines the private record renderer with the existing tested clinical-detail / timepoint-chat controller. Run this after presentation or private-detail changes. `static/shared-shell-version.json` records the source HTML SHA-256.

This adapter never loads the public `snapshot.json`, public-view.js, fictional staff, bed reservations or simulated clinical states. It fetches same-origin authenticated `api/cases` and `api/case-detail`; chat uses existing private discussion endpoints. No raw data or credentials are included in static assets or published to Sites.

The current pool has 38 hospital-001 SICU admissions, including 8 detail-linked cases. Eight slots are independent admission examples, not reconstructed simultaneous occupancy. Hospital/ICU choices come only from the loaded records. BLUE indicates incomplete transfer-review evidence, not a validated severity determination. Unmapped care indicators stay unknown. Gray unused display slots do not assert bed availability.

Deployment script `analysis/deploy_shared_clinical.py` stages the exact existing pool and environment, checks API/asset/time boundaries, preserves a backup and restarts only the existing 8007 process. Other services, including KHDP.AI's independently edited 8008 app, must not be modified.
