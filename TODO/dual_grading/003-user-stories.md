# User Stories

Status: ✅ Core functionality implemented, 🔄 Dashboard/UX improvements in progress

Admin
- As an admin, I can assign grading eligibility per user per disease per lab unit, independently from upload permissions.
- As an admin, I can enable or disable a user for Resident, Resident2, or Arbitrator slots for specific diseases at specific lab units.
- As an admin, I can create missing grading tasks for a disease across verified images in a lab unit.

Resident
- As a resident, I can only see and grade verified images for diseases and lab units where I'm marked eligible.
- As a resident, I cannot see the resident2's grade and identity during grading.
- As a resident, I get "next image" suggestions prioritizing cases where the other slot (resident2) has already graded.

Resident2 (Ophthalmologist)
- As a resident2 member, I can only see and grade verified images where I'm eligible for the Resident2 slot.
- As a resident2 member, I cannot see the resident's grade and identity during grading.
- As a resident2 member, I cannot arbitrate a task where I have already graded.

Arbitrator (Ophthalmologist)
- As an arbitrator, I see cases that were escalated due to disagreement and I am eligible to arbitrate in that lab unit and disease.
- As an arbitrator, I can see the resident and resident2 grades with their identities to make a final decision.
- As an arbitrator, submitting my decision finalizes the task and records consensus via adjudication.

Data Manager / Auditor
- As a data manager, I can view dashboards and CSV reports of consensus, arbitration rates, and per-disease counts without exposing PHI.
- As an auditor, I can compare AI model outputs with final human consensus for research (admin-only view).

System
- When a direct image is verified, the system auto-creates a grading task for its native disease.
- When a Remed.io encounter is verified for DR or Glaucoma, the system auto-creates tasks for all images in that encounter for the verified disease.
- The system only surfaces verified images for grading, and never allows grading of locked images.
 - Once a final consensus exists for an image×disease (in any lab unit), the system does not create or reassign another task for the same image×disease in other lab units; the gold standard is set.