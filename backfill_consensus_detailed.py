#!/usr/bin/env python
"""
One-time backfill script to populate missing final_disease_name and final_grade_description fields 
in the consensus table.

This script fills in NULL values in these denormalized fields by copying data 
from the related DiseaseGrading and Disease records.
"""

from models import Session, Consensus, DiseaseGrading, Disease


def backfill_consensus_detailed():
    """Backfill missing fields in the consensus table."""
    db = Session()
    
    try:
        # Query for all consensus records where any of the denormalized fields are NULL
        null_disease_name_consensus = db.query(Consensus).filter(
            Consensus.final_disease_name.is_(None)
        ).all()
        
        print(f"Found {len(null_disease_name_consensus)} consensus records with NULL final_disease_name")
        
        updated_disease_count = 0
        for consensus in null_disease_name_consensus:
            # Get the related DiseaseGrading record
            disease_grading = db.query(DiseaseGrading).filter(
                DiseaseGrading.id == consensus.final_disease_grading_id
            ).first()
            
            if disease_grading:
                # Get the related Disease from the DiseaseGrading
                disease = db.query(Disease).filter(
                    Disease.id == disease_grading.disease_id
                ).first()
                
                if disease:
                    # Update the denormalized field with the disease name
                    consensus.final_disease_name = disease.name
                    updated_disease_count += 1
                    print(f"Updated consensus {consensus.id}: set final_disease_name to '{disease.name}'")
                else:
                    print(f"Warning: DiseaseGrading {disease_grading.id} references non-existent Disease ID {disease_grading.disease_id}")
            else:
                print(f"Warning: Consensus {consensus.id} references non-existent DiseaseGrading ID {consensus.final_disease_grading_id}")
        
        # Query for consensus records where final_grade_description is NULL
        null_grade_description_consensus = db.query(Consensus).filter(
            Consensus.final_grade_description.is_(None)
        ).all()
        
        print(f"Found {len(null_grade_description_consensus)} consensus records with NULL final_grade_description")
        
        updated_grade_desc_count = 0
        for consensus in null_grade_description_consensus:
            # Get the related DiseaseGrading record
            disease_grading = db.query(DiseaseGrading).filter(
                DiseaseGrading.id == consensus.final_disease_grading_id
            ).first()
            
            if disease_grading:
                # Update the denormalized field with the guidelines
                consensus.final_grade_description = disease_grading.guidelines
                updated_grade_desc_count += 1
                print(f"Updated consensus {consensus.id}: set final_grade_description to '{disease_grading.guidelines}'")
            else:
                print(f"Warning: Consensus {consensus.id} references non-existent DiseaseGrading ID {consensus.final_disease_grading_id}")
        
        # Commit all changes
        db.commit()
        print(f"Successfully updated {updated_disease_count} final_disease_name fields")
        print(f"Successfully updated {updated_grade_desc_count} final_grade_description fields")
        
    except Exception as e:
        # Rollback in case of error
        db.rollback()
        print(f"Error during backfill: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Starting detailed consensus backfill...")
    backfill_consensus_detailed()
    print("Detailed backfill completed!")