# Checkpoint - Verify Remedio Unified Edit

Status: Planning + partial implementation in progress

Scope:
- Combine DR/Glaucoma/NoDR verification into a single `verify_remedio` edit page
- Keep existing model structure and per-disease verification flags
- Show images + laterality/centering tagging controls
- Show PDF reports inline for DR and Glaucoma (if present)
- Support multiple DR/Glaucoma reports (edge case) by stacking sections
- Auto-create Glaucoma cleaned rows if missing when route loads

Decisions:
- One unified edit page at `/verify_remedio/edit/<encounter_id>`
- Separate toggles for DR, Glaucoma, and Encounter
- Encounter verify allowed only when applicable DR/Glaucoma toggles are verified

Next steps:
1) Implement `/verify_remedio/edit/<encounter_id>` with form sections:
   - Patient fields
   - DR report fields (result, qualitative, PDF iframe)
   - Glaucoma cleaned fields (vcdr R/L numeric, result, qualitative, OCR raw, PDF iframe)
   - Laterality/centering tagging for images
2) Wire DR/Glaucoma/Encounter verify/unverify toggles to existing actions
3) Add per-encounter save handler for updates to DR/Glaucoma cleaned fields
4) Update combined list "Verify" button to route to unified edit
5) Manual verification: combined list, edit, toggles, tag updates, PDFs

