# SICU LINK private clinical integration

Visual source: SNUH_Hackathon PR #1, commit bc10e557f6e11f4c986446568bf69bc32ff2d3b3.

The adapter applies the PR's bed artwork, clinician figures, architectural station and workspace hierarchy to the existing authenticated K-MIMIC shell. It does not import the PR's snapshot.json, demo patient generator, clocks, scenario controller or API stubs.

- Clinical data, case IDs, equipment evidence and selected time remain owned by shared-clinical-controller.js.
- MonthlyReplay and StaffSimulation retain the existing 31-day timetable, source observation checkpoints and transport coordinates.
- Preserve the existing porter pushing a wheeled patient trolley for admission and discharge (user preference, 2026-10-17). Keep the patient on the trolley during transport and retain the linked handoff, bed occupancy and color transitions. Do not replace this animation when changing the clinician or bed artwork; `renderPlanTransport()` owns its SVG layer.
- Clinical and image APIs remain same-origin behind KHDP authentication. GroundedChat now presents nurse/AI message bubbles and a verified CXR selector; it reuses the existing image-review endpoint.
- Tabs separate the ward, patient/tests, 31-day plan and dataset information. Patient modal close remains prominent.
- Colors reflect the existing scenario plan; the adapter never infers transfer suitability.
- Equipment icon activation and hover evidence remain untouched. Decorative beds never imply a new device observation.
- All source cohort data remains on the Pod; no patient records or credentials are bundled.

## Build

Run `python3 analysis/build_sicu_private_shell.py` after editing adapter.js or presentation.css. The standard build_private_shared_shell.py invokes this bundler too. Marked JS/CSS blocks are replaced on repeat builds. The vendor folder retains PR artwork attribution.

## Deployment

The two marked visual blocks are packaged separately and appended to the *remote existing* controller and CSS. This preserves remote clinical changes rather than overwriting them with a local copy. `analysis/deploy_sicu_visuals.py` backs up both assets and compares `/api/cases` SHA-256 before and after. It does not restart the server or change data pools.

First original backup: `/home/khdp-user/workspace/icu-runtime/sicu-ui-backup-20261017-055749`
Latest receipt: `/home/khdp-user/workspace/icu-runtime/sicu-ui-deploy-receipt.json`
To revert, restore shared-clinical-controller.js and shared-clinical.css from the original backup into kmimic-board-v1/static, then refresh.

## Verified 2026-10-17

- 34 clinical/chat/image unit tests passed.
- GS UI source-time boundary and 10-minute replay checks passed.
- 31-day transition validation: 4,870 frames, 527 events, eight slots, no endpoint staff/bed/porter geometric overlap.
- Staff component: 200 manual plus 24 record-linked frames, timer/lifecycle checks passed.
- Authenticated browser: real case detail, lab records, CXR panel and AI context-ready state; ward-to-plan navigation; day 3 and day 31; Korean/English; eight patient cards; no browser JS errors.
- No new model response quality evaluation is implied by this UI integration.

Public Site and port 8006 redirect are unchanged; this integration is on the authenticated port 8007 clinical board.
