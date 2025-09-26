#!/usr/bin/env python3
\"\"\"
Test script for consensus functionality
\"\"\"

import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from models import Session, GradingTask, Grade, Consensus, User, Disease, DiseaseGrading, LabUnit, Hospital
from utils.consensusUtils import create_or_update_consensus, get_task_consensus_status, update_task_state_based_on_grades, has_consensus

def create_test_data():
    \"\"\"
    Create test data for consensus testing
    \"\"\"
    db = Session()
    
    try:
        # Fetch an existing hospital, lab unit, disease, and user if they exist
        hospital = db.query(Hospital).first()
        if not hospital:
            hospital = Hospital(name=\"Test Hospital\")
            db.add(hospital)
            db.commit()
            db.refresh(hospital)
        
        lab_unit = db.query(LabUnit).first()
        if not lab_unit:
            lab_unit = LabUnit(name=\"Test Lab Unit\", hospital_id=hospital.id)
            db.add(lab_unit)
            db.commit()
            db.refresh(lab_unit)
        
        disease = db.query(Disease).first()
        if not disease:
            disease = Disease(name=\"Test Disease\")
            db.add(disease)
            db.commit()
            db.refresh(disease)
        
        # Create disease gradings
        grading_1 = db.query(DiseaseGrading).filter(
            DiseaseGrading.disease_id == disease.id,
            DiseaseGrading.impression == \"Normal\"
        ).first()
        if not grading_1:
            grading_1 = DiseaseGrading(
                disease_id=disease.id,
                impression=\"Normal\",
                display_order=1
            )
            db.add(grading_1)
            db.commit()
            db.refresh(grading_1)
        
        grading_2 = db.query(DiseaseGrading).filter(
            DiseaseGrading.disease_id == disease.id,
            DiseaseGrading.impression == \"Abnormal\"
        ).first()
        if not grading_2:
            grading_2 = DiseaseGrading(
                disease_id=disease.id,
                impression=\"Abnormal\",
                display_order=2
            )
            db.add(grading_2)
            db.commit()
            db.refresh(grading_2)
        
        user = db.query(User).first()
        if not user:
            user = User(
                username=\"test_user\",
                password_hash=\"dummy_hash\",
                full_name=\"Test User\"
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        
        # Create a minimal EncounterFile for the task (required due to constraint)
        from models import EncounterFile
        encounter_file = db.query(EncounterFile).first()  # Try to get any existing file first
        if not encounter_file:
            encounter_file = EncounterFile(
                patient_encounter_id=None,  # This should be a valid ID if needed
                filename=\"test_image.jpg\",
                file_type=\"image\"
            )
            db.add(encounter_file)
            db.commit()
            db.refresh(encounter_file)
        
        # Create a test task - using encounter file to satisfy constraint
        task = GradingTask(
            encounter_file_id=encounter_file.id,  # Add this to satisfy the constraint
            disease_id=disease.id,
            lab_unit_id=lab_unit.id,
            state=\"pending\"
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        return task, user, grading_1, grading_2
        
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

def test_consensus_functionality():
    \"\"\"
    Test the consensus functionality
    \"\"\"
    print(\"Testing consensus functionality...\")
    
    # Create test data
    task, user, grading_1, grading_2 = create_test_data()
    print(f\"Created test task with ID: {task.id}\")
    
    # Initially, there should be no consensus
    has_cons = has_consensus(task.id)
    print(f\"Task initially has consensus: {has_cons}\")
    assert not has_cons, \"Task should not have consensus initially\"
    
    # Add a resident grade
    db = Session()
    try:
        resident_grade = Grade(
            task_id=task.id,
            grader_user_id=user.id,
            role_slot=\"resident\",
            disease_grading_id=grading_1.id
        )
        db.add(resident_grade)
        db.commit()
        print(\"Added resident grade\")
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
    
    # Check consensus status after adding resident grade
    status = get_task_consensus_status(task.id)
    print(f\"Consensus status after resident grade: {status}\")
    
    # Add a faculty grade that matches the resident grade
    db = Session()
    try:
        faculty_grade = Grade(
            task_id=task.id,
            grader_user_id=user.id,
            role_slot=\"faculty\",
            disease_grading_id=grading_1.id  # Same as resident grade
        )
        db.add(faculty_grade)
        db.commit()
        print(\"Added faculty grade (matching resident)\")
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
    
    # Check task state - it should still be pending since we haven't called update_task_state_based_on_grades yet
    db = Session()
    try:
        task_after_grades = db.query(GradingTask).filter(GradingTask.id == task.id).first()
        print(f\"Task state after grades but before update: {task_after_grades.state}\")
    finally:
        db.close()
    
    # Update task state based on grades
    updated_task = update_task_state_based_on_grades(task.id)
    print(f\"Updated task state after grades: {updated_task.state}\")
    assert updated_task.state == \"final\", \"Task state should be 'final' when resident and faculty match\"
    
    # Now create the consensus
    created_consensus = create_or_update_consensus(task.id)
    print(f\"Created consensus: {created_consensus.method if created_consensus else None}\")
    assert created_consensus is not None, \"Consensus should be created\"
    assert created_consensus.method == \"match\", \"Consensus method should be 'match'\"
    
    # Verify the task now has consensus
    has_cons = has_consensus(task.id)
    print(f\"Task now has consensus: {has_cons}\")
    assert has_cons, \"Task should have consensus after match\"
    
    # Check the final consensus status
    final_status = get_task_consensus_status(task.id)
    print(f\"Final consensus status: {final_status}\")
    
    # Create a new task for testing arbitration
    print(\"\\nTesting arbitration scenario...\")
    
    task2, user2, grading_1_2, grading_2_2 = create_test_data()
    print(f\"Created test task for arbitration with ID: {task2.id}\")
    
    # Add a resident grade
    db = Session()
    try:
        resident_grade2 = Grade(
            task_id=task2.id,
            grader_user_id=user.id,
            role_slot=\"resident\",
            disease_grading_id=grading_1_2.id
        )
        db.add(resident_grade2)
        faculty_grade2 = Grade(
            task_id=task2.id,
            grader_user_id=user2.id,
            role_slot=\"faculty\",
            disease_grading_id=grading_2_2.id  # Different from resident grade
        )
        db.add(faculty_grade2)
        db.commit()
        print(\"Added resident and faculty grades (not matching)\")
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
    
    # Update task state - should go to arbitration since grades don't match
    updated_task2 = update_task_state_based_on_grades(task2.id)
    print(f\"Task2 state after non-matching grades: {updated_task2.state}\")
    assert updated_task2.state == \"arbitration\", \"Task state should be 'arbitration' when resident and faculty don't match\"
    
    # Add an arbitrator grade
    db = Session()
    try:
        arbitrator_grade = Grade(
            task_id=task2.id,
            grader_user_id=user.id,
            role_slot=\"arbitrator\",
            disease_grading_id=grading_1_2.id  # Arbitrator agrees with resident
        )
        db.add(arbitrator_grade)
        db.commit()
        print(\"Added arbitrator grade\")
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
    
    # Update task state again - should go to final
    updated_task2 = update_task_state_based_on_grades(task2.id)
    print(f\"Task2 state after arbitrator grade: {updated_task2.state}\")
    assert updated_task2.state == \"final\", \"Task state should be 'final' after arbitrator grade\"
    
    # Create consensus for the arbitrator case
    created_consensus2 = create_or_update_consensus(task2.id)
    print(f\"Created consensus for arbitration task: {created_consensus2.method if created_consensus2 else None}\")
    assert created_consensus2 is not None, \"Consensus should be created for arbitration task\"
    assert created_consensus2.method == \"adjudication\", \"Consensus method should be 'adjudication' for arbitrator decision\"
    
    print(\"\\nAll tests passed!\")
    return True

if __name__ == \"__main__\":
    test_consensus_functionality()