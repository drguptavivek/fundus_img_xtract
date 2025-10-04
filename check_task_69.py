#!/usr/bin/env python
"""
Script to check and fix a specific task's consensus record if needed.
"""

from models import Session, Consensus, DiseaseGrading, GradingTask


def check_and_fix_task_69():
    """Check if task 69's consensus needs updating."""
    db = Session()
    
    try:
        # Get the specific task
        task = db.query(GradingTask).filter(GradingTask.id == 69).first()
        
        if not task:
            print("Task 69 not found")
            return
            
        if not task.consensus:
            print("Task 69 has no consensus record")
            return
            
        print(f"Task 69 consensus ID: {task.consensus.id}")
        print(f"Current final_grade_name: {repr(task.consensus.final_grade_name)}")
        print(f"Final disease grading ID: {task.consensus.final_disease_grading_id}")
        
        if task.consensus.final_grade_name is None:
            # Get the related DiseaseGrading record
            disease_grading = db.query(DiseaseGrading).filter(
                DiseaseGrading.id == task.consensus.final_disease_grading_id
            ).first()
            
            if disease_grading:
                # Update the denormalized field with the impression
                task.consensus.final_grade_name = disease_grading.impression
                print(f"Updating consensus {task.consensus.id}: setting final_grade_name to '{disease_grading.impression}'")
                
                # Commit the change
                db.commit()
                print("Update successful!")
            else:
                print(f"Error: Referenced DiseaseGrading ID {task.consensus.final_disease_grading_id} not found")
        else:
            print("Task 69's final_grade_name is already populated")
    
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    check_and_fix_task_69()