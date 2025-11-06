#!/usr/bin/env python3
"""
Script to clean up orphaned ZIP file records.
Orphaned ZIP files are those that exist in the zip_files table
but no longer have an associated PatientEncounters record.
"""

import sys
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import ZipFile, PatientEncounters
from db_transaction_manager import get_db_session
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def cleanup_orphaned_zip_files(dry_run=True):
    """
    Find and delete orphaned ZIP file records.
    
    Args:
        dry_run (bool): If True, only report what would be deleted without actually deleting
    
    Returns:
        dict: Statistics about the cleanup operation
    """
    stats = {
        'total_zip_files': 0,
        'orphaned_zip_files': 0,
        'deleted_zip_files': 0,
        'orphaned_details': []
    }
    
    with get_db_session() as db:
        # Get all ZIP files
        all_zip_files = db.query(ZipFile).all()
        stats['total_zip_files'] = len(all_zip_files)
        
        logger.info(f"Found {stats['total_zip_files']} total ZIP file records")
        
        # Find orphaned ZIP files (those without associated PatientEncounters)
        orphaned_files = []
        for zip_file in all_zip_files:
            # Check if there's a PatientEncounters record associated with this ZIP file
            associated_encounter = db.query(PatientEncounters).filter(
                PatientEncounters.zip_file_id == zip_file.id
            ).first()
            
            if not associated_encounter:
                orphaned_files.append(zip_file)
                stats['orphaned_details'].append({
                    'id': zip_file.id,
                    'filename': zip_file.zip_filename,
                    'md5_hash': zip_file.md5_hash,
                    'upload_date': zip_file.upload_date
                })
        
        stats['orphaned_zip_files'] = len(orphaned_files)
        
        if stats['orphaned_zip_files'] > 0:
            logger.warning(f"Found {stats['orphaned_zip_files']} orphaned ZIP file records:")
            
            for detail in stats['orphaned_details']:
                logger.warning(f"  - ID: {detail['id']}, Filename: {detail['filename']}, "
                            f"MD5: {detail['md5_hash']}, Upload Date: {detail['upload_date']}")
            
            if not dry_run:
                logger.info("Deleting orphaned ZIP file records...")
                for zip_file in orphaned_files:
                    db.delete(zip_file)
                    stats['deleted_zip_files'] += 1
                
                logger.info(f"Successfully deleted {stats['deleted_zip_files']} orphaned ZIP file records")
            else:
                logger.info("DRY RUN: Use --execute to actually delete the orphaned records")
        else:
            logger.info("No orphaned ZIP file records found")
    
    return stats

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean up orphaned ZIP file records')
    parser.add_argument('--execute', action='store_true', 
                       help='Actually delete the orphaned records (default is dry-run)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("Starting orphaned ZIP file cleanup...")
    logger.info(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")
    
    stats = cleanup_orphaned_zip_files(dry_run=not args.execute)
    
    # Print summary
    print("\n" + "="*50)
    print("CLEANUP SUMMARY")
    print("="*50)
    print(f"Total ZIP file records: {stats['total_zip_files']}")
    print(f"Orphaned ZIP file records: {stats['orphaned_zip_files']}")
    if args.execute:
        print(f"Deleted ZIP file records: {stats['deleted_zip_files']}")
    else:
        print("Run with --execute to delete orphaned records")
    print("="*50)
    
    if stats['orphaned_zip_files'] > 0 and not args.execute:
        print("\nOrphaned files found. Run with --execute to delete them.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())