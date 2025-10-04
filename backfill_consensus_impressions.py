#!/usr/bin/env python
"""
One-time backfill script to populate the final_grade_name field in the consensus table.

This script fills in NULL values in the final_grade_name field by copying the 
impression from the related DiseaseGrading record.
"""

from models import Session, Consensus, DiseaseGrading


def backfill_consensus_impressions():
    """Backfill NULL final_grade_name values in the consensus table."""
    db = Session()
    
    try:
        # Query for all consensus records where final_grade_name is NULL
        null_impression_consensus = db.query(Consensus).filter(
            Consensus.final_grade_name.is_(None)
        ).all()
        
        print(f"Found {len(null_impression_consensus)} consensus records with NULL final_grade_name")
        
        updated_count = 0
        for consensus in null_impression_consensus:
            # Get the related DiseaseGrading record
            disease_grading = db.query(DiseaseGrading).filter(
                DiseaseGrading.id == consensus.final_disease_grading_id
            ).first()
            
            if disease_grading:
                # Update the denormalized field with the impression
                consensus.final_grade_name = disease_grading.impression
                updated_count += 1
                print(f"Updated consensus {consensus.id}: set final_grade_name to '{disease_grading.impression}'")
            else:
                print(f"Warning: Consensus {consensus.id} references non-existent DiseaseGrading ID {consensus.final_disease_grading_id}")
        
        # Commit all changes
        db.commit()
        print(f"Successfully updated {updated_count} consensus records")
        
    except Exception as e:
        # Rollback in case of error
        db.rollback()
        print(f"Error during backfill: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Starting consensus impression backfill...")
    backfill_consensus_impressions()
    print("Backfill completed!")