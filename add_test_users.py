#!/usr/bin/env python3
"""
Script to add test users to the fundus image management application.
This script adds three test users with different roles and grading eligibility.
"""

import sys
from pathlib import Path

# Add the project directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select
from models import Session, User, Role, Hospital, LabUnit, Disease, UserDiseaseUnitRole
from auth.security import hash_password


def add_test_users():
    """Add test users with specific roles and permissions."""
    with Session() as db:
        # Hash the password for all test users
        password_hash = hash_password("Vivek@2026")
        
        # Check if the hospital "RPC AIIMS" exists, create if not
        hospital = db.execute(
            select(Hospital).where(Hospital.name == "RPC AIIMS")
        ).scalar_one_or_none()
        
        if not hospital:
            hospital = Hospital(name="RPC AIIMS")
            db.add(hospital)
            db.commit()
            print(f"Created hospital: {hospital.name}")
        else:
            print(f"Found existing hospital: {hospital.name}")
        
        # Check if the lab unit "Community Ophthalmology" exists for RPC AIIMS, create if not
        lab_unit = db.execute(
            select(LabUnit).where(
                LabUnit.name == "Community Ophthalmology",
                LabUnit.hospital_id == hospital.id
            )
        ).scalar_one_or_none()
        
        if not lab_unit:
            lab_unit = LabUnit(
                name="Community Ophthalmology",
                hospital_id=hospital.id
            )
            db.add(lab_unit)
            db.commit()
            print(f"Created lab unit: {lab_unit.name}")
        else:
            print(f"Found existing lab unit: {lab_unit.name}")
        
        # Get disease IDs for Glaucoma and DR
        glaucoma_disease = db.execute(
            select(Disease).where(Disease.name == "Glaucoma")
        ).scalar_one_or_none()
        
        if not glaucoma_disease:
            print("Error: Glaucoma disease not found in the database.")
            return
        
        dr_disease = db.execute(
            select(Disease).where(Disease.name == "DR")
        ).scalar_one_or_none()
        
        if not dr_disease:
            print("Error: DR disease not found in the database.")
            return
        
        print(f"Found diseases: {glaucoma_disease.name}, {dr_disease.name}")
        
        # Check if the ophthalmologist role exists
        oph_role = db.execute(
            select(Role).where(Role.name == "ophthalmologist")
        ).scalar_one_or_none()
        
        if not oph_role:
            print("Error: 'ophthalmologist' role not found in the database.")
            return
        
        print(f"Found role: {oph_role.name}")
        
        # Add test2ComophArbit user
        user1 = db.execute(
            select(User).where(User.username == "test2ComophArbit")
        ).scalar_one_or_none()
        
        if not user1:
            user1 = User(
                username="test2ComophArbit",
                password_hash=password_hash,
                is_active=True,
                full_name="Test Comoph Arbitrator",
                roles=[oph_role]
            )
            db.add(user1)
            db.commit()
            print(f"Created user: {user1.username}")
        else:
            print(f"User {user1.username} already exists")
        
        # Add grading eligibility for arbitrator
        # Glaucoma: Arbitrator
        glaucoma_arbitration_role = db.execute(
            select(UserDiseaseUnitRole).where(
                UserDiseaseUnitRole.user_id == user1.id,
                UserDiseaseUnitRole.disease_id == glaucoma_disease.id,
                UserDiseaseUnitRole.lab_unit_id == lab_unit.id
            )
        ).scalar_one_or_none()
        
        if not glaucoma_arbitration_role:
            glaucoma_arbitration_role = UserDiseaseUnitRole(
                user_id=user1.id,
                disease_id=glaucoma_disease.id,
                lab_unit_id=lab_unit.id,
                can_arbitrate=True,
                can_grade_resident=False,
                can_grade_faculty=False,
                active=True
            )
            db.add(glaucoma_arbitration_role)
        else:
            glaucoma_arbitration_role.can_arbitrate = True
            glaucoma_arbitration_role.can_grade_resident = False
            glaucoma_arbitration_role.can_grade_faculty = False
            glaucoma_arbitration_role.active = True
        
        # DR: Arbitrator
        dr_arbitration_role = db.execute(
            select(UserDiseaseUnitRole).where(
                UserDiseaseUnitRole.user_id == user1.id,
                UserDiseaseUnitRole.disease_id == dr_disease.id,
                UserDiseaseUnitRole.lab_unit_id == lab_unit.id
            )
        ).scalar_one_or_none()
        
        if not dr_arbitration_role:
            dr_arbitration_role = UserDiseaseUnitRole(
                user_id=user1.id,
                disease_id=dr_disease.id,
                lab_unit_id=lab_unit.id,
                can_arbitrate=True,
                can_grade_resident=False,
                can_grade_faculty=False,
                active=True
            )
            db.add(dr_arbitration_role)
        else:
            dr_arbitration_role.can_arbitrate = True
            dr_arbitration_role.can_grade_resident = False
            dr_arbitration_role.can_grade_faculty = False
            dr_arbitration_role.active = True
        
        db.commit()
        print(f"Updated grading eligibility for {user1.username}")
        
        # Add test2ComophFac user
        user2 = db.execute(
            select(User).where(User.username == "test2ComophFac")
        ).scalar_one_or_none()
        
        if not user2:
            user2 = User(
                username="test2ComophFac",
                password_hash=password_hash,
                is_active=True,
                full_name="Test Comoph Faculty",
                roles=[oph_role]
            )
            db.add(user2)
            db.commit()
            print(f"Created user: {user2.username}")
        else:
            print(f"User {user2.username} already exists")
        
        # Add grading eligibility for faculty
        # Glaucoma: Faculty
        glaucoma_faculty_role = db.execute(
            select(UserDiseaseUnitRole).where(
                UserDiseaseUnitRole.user_id == user2.id,
                UserDiseaseUnitRole.disease_id == glaucoma_disease.id,
                UserDiseaseUnitRole.lab_unit_id == lab_unit.id
            )
        ).scalar_one_or_none()
        
        if not glaucoma_faculty_role:
            glaucoma_faculty_role = UserDiseaseUnitRole(
                user_id=user2.id,
                disease_id=glaucoma_disease.id,
                lab_unit_id=lab_unit.id,
                can_grade_faculty=True,
                can_grade_resident=False,
                can_arbitrate=False,
                active=True
            )
            db.add(glaucoma_faculty_role)
        else:
            glaucoma_faculty_role.can_grade_faculty = True
            glaucoma_faculty_role.can_grade_resident = False
            glaucoma_faculty_role.can_arbitrate = False
            glaucoma_faculty_role.active = True
        
        # DR: Faculty
        dr_faculty_role = db.execute(
            select(UserDiseaseUnitRole).where(
                UserDiseaseUnitRole.user_id == user2.id,
                UserDiseaseUnitRole.disease_id == dr_disease.id,
                UserDiseaseUnitRole.lab_unit_id == lab_unit.id
            )
        ).scalar_one_or_none()
        
        if not dr_faculty_role:
            dr_faculty_role = UserDiseaseUnitRole(
                user_id=user2.id,
                disease_id=dr_disease.id,
                lab_unit_id=lab_unit.id,
                can_grade_faculty=True,
                can_grade_resident=False,
                can_arbitrate=False,
                active=True
            )
            db.add(dr_faculty_role)
        else:
            dr_faculty_role.can_grade_faculty = True
            dr_faculty_role.can_grade_resident = False
            dr_faculty_role.can_arbitrate = False
            dr_faculty_role.active = True
        
        db.commit()
        print(f"Updated grading eligibility for {user2.username}")
        
        # Add test2ComophResident user
        user3 = db.execute(
            select(User).where(User.username == "test2ComophResident")
        ).scalar_one_or_none()
        
        if not user3:
            user3 = User(
                username="test2ComophResident",
                password_hash=password_hash,
                is_active=True,
                full_name="Test Comoph Resident",
                roles=[oph_role]
            )
            db.add(user3)
            db.commit()
            print(f"Created user: {user3.username}")
        else:
            print(f"User {user3.username} already exists")
        
        # Add grading eligibility for resident
        # Glaucoma: Resident
        glaucoma_resident_role = db.execute(
            select(UserDiseaseUnitRole).where(
                UserDiseaseUnitRole.user_id == user3.id,
                UserDiseaseUnitRole.disease_id == glaucoma_disease.id,
                UserDiseaseUnitRole.lab_unit_id == lab_unit.id
            )
        ).scalar_one_or_none()
        
        if not glaucoma_resident_role:
            glaucoma_resident_role = UserDiseaseUnitRole(
                user_id=user3.id,
                disease_id=glaucoma_disease.id,
                lab_unit_id=lab_unit.id,
                can_grade_resident=True,
                can_grade_faculty=False,
                can_arbitrate=False,
                active=True
            )
            db.add(glaucoma_resident_role)
        else:
            glaucoma_resident_role.can_grade_resident = True
            glaucoma_resident_role.can_grade_faculty = False
            glaucoma_resident_role.can_arbitrate = False
            glaucoma_resident_role.active = True
        
        # DR: Resident
        dr_resident_role = db.execute(
            select(UserDiseaseUnitRole).where(
                UserDiseaseUnitRole.user_id == user3.id,
                UserDiseaseUnitRole.disease_id == dr_disease.id,
                UserDiseaseUnitRole.lab_unit_id == lab_unit.id
            )
        ).scalar_one_or_none()
        
        if not dr_resident_role:
            dr_resident_role = UserDiseaseUnitRole(
                user_id=user3.id,
                disease_id=dr_disease.id,
                lab_unit_id=lab_unit.id,
                can_grade_resident=True,
                can_grade_faculty=False,
                can_arbitrate=False,
                active=True
            )
            db.add(dr_resident_role)
        else:
            dr_resident_role.can_grade_resident = True
            dr_resident_role.can_grade_faculty = False
            dr_resident_role.can_arbitrate = False
            dr_resident_role.active = True
        
        db.commit()
        print(f"Updated grading eligibility for {user3.username}")
        
        # Add the lab unit to each user if not already associated
        if lab_unit not in user1.lab_units:
            user1.lab_units.append(lab_unit)
        if lab_unit not in user2.lab_units:
            user2.lab_units.append(lab_unit)
        if lab_unit not in user3.lab_units:
            user3.lab_units.append(lab_unit)
        db.commit()
        
        print("Successfully added all test users with their roles and grading eligibility!")
        print("\nSummary:")
        print(f"- User: test2ComophArbit, Password: Vivek@2026, Role: ophthalmologist")
        print(f"  Eligibility: Glaucoma Arbitrator, DR Arbitrator")
        print(f"- User: test2ComophFac, Password: Vivek@2026, Role: ophthalmologist")
        print(f"  Eligibility: Glaucoma Faculty, DR Faculty")
        print(f"- User: test2ComophResident, Password: Vivek@2026, Role: ophthalmologist")
        print(f"  Eligibility: Glaucoma Resident, DR Resident")


if __name__ == "__main__":
    add_test_users()