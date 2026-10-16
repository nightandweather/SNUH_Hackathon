# ICU dashboard deployment

The user requires the KHDP presentation and shared Site to always open the same published dashboard. Preserve `deployment/shared-entry.js` in `static/index.html` on KHDP port 8006. The shared Site is the canonical presentation; publish presentation changes there rather than independently diverging KHDP and public screens. See `deployment/README.md`.

Keep actual K-MIMIC records, credentials, and the grounded LLM discussion on the authenticated KHDP source-record server (port 8007). Do not copy those records or credentials into public Site assets. Browser-local sandbox state is not cross-user synchronized; do not claim it is.

## Preserve the full GS cohort for model development

The user explicitly requires retaining the full GS ICU cohort (currently 14,321 stays, 12,264 distinct hospital-subjects) for future model development. Never reduce, delete, or replace that cohort with the dashboard sample or monthly scenario allocation. Preserve the source K-MIMIC dataset partitions and full cohort index; store scenario selections and any future model features or splits as separate derived artifacts. Preserve versioned cohort indexes and provenance when the selection definition changes. Do not begin training or choose train/test splits merely because the user asked to retain the data.
