#!/usr/bin/env python3
"""Migrate features from JSON to gradings_features table."""
from __future__ import annotations

import sys
import os
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sqlalchemy import text
from models import engine, Session, DiseaseGrading, GradingsFeatures
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def migrate_features_json_to_table():
    """Migrate features from JSON to gradings_features table."""
    logger.info("Starting migration of features from JSON to gradings_features table...")
    
    session = Session()
    total_gradings = 0
    migrated_gradings = 0
    total_features = 0
    
    try:
        # Get all disease gradings with features_json
        gradings = session.query(DiseaseGrading).filter(
            DiseaseGrading.features_json.isnot(None),
            DiseaseGrading.features_json != ''
        ).all()
        
        total_gradings = len(gradings)
        logger.info(f"Found {total_gradings} gradings with features to migrate")
        
        for grading in gradings:
            try:
                # Parse the JSON
                features_data = json.loads(grading.features_json)
                
                if features_data and 'features' in features_data and features_data['features']:
                    # Create GradingsFeatures records
                    for feature in features_data['features']:
                        gradings_feature = GradingsFeatures(
                            disease_grading_id=grading.id,
                            sr_no=feature.get('sr_no', 0),
                            label=feature.get('label', '')
                        )
                        session.add(gradings_feature)
                        total_features += 1
                    
                    migrated_gradings += 1
                    logger.info(f"Migrated {len(features_data['features'])} features for grading ID {grading.id}")
                else:
                    logger.info(f"No features found in JSON for grading ID {grading.id}")
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON for grading ID {grading.id}: {e}")
                continue
            except Exception as e:
                logger.error(f"Error processing grading ID {grading.id}: {e}")
                continue
        
        # Commit all changes
        session.commit()
        
        logger.info(f"Migration completed successfully:")
        logger.info(f"  - Total gradings with features: {total_gradings}")
        logger.info(f"  - Gradings migrated: {migrated_gradings}")
        logger.info(f"  - Total features created: {total_features}")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Migration failed: {str(e)}")
        raise
    finally:
        session.close()

def verify_migration():
    """Verify that migration was successful."""
    logger.info("Verifying migration...")
    
    session = Session()
    try:
        # Count gradings with features_json
        gradings_with_json = session.query(DiseaseGrading).filter(
            DiseaseGrading.features_json.isnot(None),
            DiseaseGrading.features_json != ''
        ).count()
        
        # Count gradings with features in new table
        gradings_with_features = session.query(DiseaseGrading.id).join(GradingsFeatures).group_by(DiseaseGrading.id).count()
        
        # Count total features
        total_features = session.query(GradingsFeatures).count()
        
        logger.info(f"Verification results:")
        logger.info(f"  - Gradings with features_json: {gradings_with_json}")
        logger.info(f"  - Gradings with features in new table: {gradings_with_features}")
        
        # Note: features_json is now deprecated but kept for backward compatibility
        logger.info("  - features_json field is deprecated but kept for backward compatibility")
        logger.info(f"  - Total features in new table: {total_features}")
        
        if gradings_with_json == gradings_with_features:
            logger.info("✓ Verification passed: All gradings with JSON have corresponding features in new table")
        else:
            logger.warning("⚠ Verification warning: Mismatch between gradings with JSON and gradings with features in new table")
            
    except Exception as e:
        logger.error(f"Verification failed: {str(e)}")
        raise
    finally:
        session.close()

def main():
    """Main migration function."""
    logger.info("Starting migration: Migrate features from JSON to gradings_features table...")
    
    try:
        migrate_features_json_to_table()
        verify_migration()
        logger.info("Migration completed successfully.")
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        raise

if __name__ == "__main__":
    main()