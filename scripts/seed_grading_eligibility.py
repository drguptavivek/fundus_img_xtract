import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure project root is importable
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv()

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models import Session, User, Role, Disease, LabUnit, UserDiseaseUnitRole

def seed_grading_eligibility(dry_run=False):
    """
    Seeds default grading eligibility based on user roles.
    - Residents get can_grade_resident.
    - Ophthalmologists get can_grade_faculty and can_arbitrate.
    This is applied for all disease/lab_unit combinations where the user
    does not already have an entry.
    """
    print("Seeding default grading eligibility...")
    with Session() as db:
        users_to_process = db.execute(
            select(User)
            .options(selectinload(User.roles))
            .join(User.roles)
            .where(Role.name.in_(['resident', 'ophthalmologist']))
        ).scalars().unique().all()

        diseases = db.execute(select(Disease)).scalars().all()
        lab_units = db.execute(select(LabUnit)).scalars().all()

        if not diseases or not lab_units:
            print("No diseases or lab units found. Cannot seed eligibility.")
            return

        added_count = 0
        for user in users_to_process:
            is_resident = user.has_role('resident')
            is_ophthalmologist = user.has_role('ophthalmologist')

            for disease in diseases:
                for lab_unit in lab_units:
                    exists = db.execute(
                        select(UserDiseaseUnitRole).where(
                            UserDiseaseUnitRole.user_id == user.id,
                            UserDiseaseUnitRole.disease_id == disease.id,
                            UserDiseaseUnitRole.lab_unit_id == lab_unit.id
                        )
                    ).scalar_one_or_none()

                    if exists:
                        continue

                    # Create new eligibility entry
                    can_resident = is_resident
                    can_faculty = is_ophthalmologist
                    can_arbitrate = is_ophthalmologist

                    if not (can_resident or can_faculty or can_arbitrate):
                        continue

                    print(f"Adding eligibility for {user.username} - {disease.name} @ {lab_unit.name}")
                    added_count += 1

                    if not dry_run:
                        new_rule = UserDiseaseUnitRole(
                            user_id=user.id,
                            disease_id=disease.id,
                            lab_unit_id=lab_unit.id,
                            can_grade_resident=can_resident,
                            can_grade_faculty=can_faculty,
                            can_arbitrate=can_arbitrate,
                            active=True
                        )
                        db.add(new_rule)
        
        if not dry_run:
            db.commit()
        
        print(f"Finished seeding. Added {added_count} new eligibility rules.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show what would be added without committing changes.")
    args = parser.parse_args()
    seed_grading_eligibility(dry_run=args.dry_run)
