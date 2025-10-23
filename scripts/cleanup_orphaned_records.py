#!/usr/bin/env python3
"""
Comprehensive script to clean up various types of orphaned records and files.
This script can clean up:
1. Orphaned ZIP file records (without associated PatientEncounters)
2. Orphaned encounter files (without associated PatientEncounters)
3. Orphaned PDF files (without associated PatientEncounters)
4. Orphaned reports (without associated PatientEncounters)
5. Orphaned files on disk (without database records)
"""

from datetime import datetime, timedelta
import sys
import os
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import (
    Session, ZipFile, PatientEncounters, EncounterFile, EncounterFilePDF,
    DiabeticRetinopathyReport, GlaucomaReport,
    IMAGE_DIR, PDF_DIR, DR_PDF_DIR, GLAUCOMA_PDF_DIR
)
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def cleanup_orphaned_zip_files(db, dry_run=True):
    """Clean up orphaned ZIP file records."""
    stats = {'found': 0, 'deleted': 0, 'details': []}
    
    all_zip_files = db.query(ZipFile).all()
    
    for zip_file in all_zip_files:
        associated_encounter = db.query(PatientEncounters).filter(
            PatientEncounters.zip_file_id == zip_file.id
        ).first()
        
        if not associated_encounter:
            stats['found'] += 1
            stats['details'].append({
                'type': 'zip_file',
                'id': zip_file.id,
                'filename': zip_file.zip_filename,
                'md5_hash': zip_file.md5_hash
            })
            
            if not dry_run:
                db.delete(zip_file)
                stats['deleted'] += 1
    
    return stats

def cleanup_orphaned_encounter_files(db, dry_run=True):
    """Clean up orphaned encounter file records."""
    stats = {'found': 0, 'deleted': 0, 'details': []}
    
    all_files = db.query(EncounterFile).all()
    
    for file_record in all_files:
        associated_encounter = db.query(PatientEncounters).filter(
            PatientEncounters.id == file_record.patient_encounter_id
        ).first()
        
        if not associated_encounter:
            stats['found'] += 1
            stats['details'].append({
                'type': 'encounter_file',
                'id': file_record.id,
                'filename': file_record.filename,
                'uuid': file_record.uuid
            })
            
            if not dry_run:
                # Also try to delete the file from disk
                try:
                    # Get the upload date from the associated encounter (if it existed)
                    # For now, we'll search in recent directories
                    for days_back in range(0, 7):
                        date_str = (datetime.now() - timedelta(days=days_back)).strftime("%Y_%m_%d")
                        file_path = IMAGE_DIR / date_str / file_record.filename
                        if file_path.exists():
                            file_path.unlink()
                            logger.info(f"Deleted orphaned file from disk: {file_path}")
                            break
                except Exception as e:
                    logger.warning(f"Failed to delete orphaned file {file_record.filename}: {e}")
                
                db.delete(file_record)
                stats['deleted'] += 1
    
    return stats

def cleanup_orphaned_pdf_files(db, dry_run=True):
    """Clean up orphaned PDF file records."""
    stats = {'found': 0, 'deleted': 0, 'details': []}
    
    all_pdfs = db.query(EncounterFilePDF).all()
    
    for pdf_record in all_pdfs:
        associated_encounter = db.query(PatientEncounters).filter(
            PatientEncounters.id == pdf_record.patient_encounter_id
        ).first()
        
        if not associated_encounter:
            stats['found'] += 1
            stats['details'].append({
                'type': 'pdf_file',
                'id': pdf_record.id,
                'filename': pdf_record.filename,
                'uuid': pdf_record.uuid
            })
            
            if not dry_run:
                # Also try to delete the PDF file from disk
                try:
                    for days_back in range(0, 7):
                        date_str = (datetime.now() - timedelta(days=days_back)).strftime("%Y_%m_%d")
                        file_path = PDF_DIR / date_str / pdf_record.filename
                        if file_path.exists():
                            file_path.unlink()
                            logger.info(f"Deleted orphaned PDF from disk: {file_path}")
                            break
                except Exception as e:
                    logger.warning(f"Failed to delete orphaned PDF {pdf_record.filename}: {e}")
                
                db.delete(pdf_record)
                stats['deleted'] += 1
    
    return stats

def cleanup_orphaned_reports(db, dry_run=True):
    """Clean up orphaned DR and Glaucoma report records."""
    stats = {'found': 0, 'deleted': 0, 'details': []}
    
    # Check DR reports
    dr_reports = db.query(DiabeticRetinopathyReport).all()
    for report in dr_reports:
        associated_encounter = db.query(PatientEncounters).filter(
            PatientEncounters.id == report.patient_encounter_id
        ).first()
        
        if not associated_encounter:
            stats['found'] += 1
            stats['details'].append({
                'type': 'dr_report',
                'id': report.id,
                'uuid': report.uuid,
                'report_file_name': report.report_file_name
            })
            
            if not dry_run:
                # Try to delete the split report file from disk
                if report.report_file_name:
                    try:
                        for days_back in range(0, 7):
                            date_str = (datetime.now() - timedelta(days=days_back)).strftime("%Y_%m_%d")
                            file_path = DR_PDF_DIR / date_str / report.report_file_name
                            if file_path.exists():
                                file_path.unlink()
                                logger.info(f"Deleted orphaned DR report from disk: {file_path}")
                                break
                    except Exception as e:
                        logger.warning(f"Failed to delete orphaned DR report {report.report_file_name}: {e}")
                
                db.delete(report)
                stats['deleted'] += 1
    
    # Check Glaucoma reports
    gl_reports = db.query(GlaucomaReport).all()
    for report in gl_reports:
        associated_encounter = db.query(PatientEncounters).filter(
            PatientEncounters.id == report.patient_encounter_id
        ).first()
        
        if not associated_encounter:
            stats['found'] += 1
            stats['details'].append({
                'type': 'glaucoma_report',
                'id': report.id,
                'uuid': report.uuid,
                'report_file_name': report.report_file_name
            })
            
            if not dry_run:
                # Try to delete the split report file from disk
                if report.report_file_name:
                    try:
                        for days_back in range(0, 7):
                            date_str = (datetime.now() - timedelta(days=days_back)).strftime("%Y_%m_%d")
                            file_path = GLAUCOMA_PDF_DIR / date_str / report.report_file_name
                            if file_path.exists():
                                file_path.unlink()
                                logger.info(f"Deleted orphaned Glaucoma report from disk: {file_path}")
                                break
                    except Exception as e:
                        logger.warning(f"Failed to delete orphaned Glaucoma report {report.report_file_name}: {e}")
                
                db.delete(report)
                stats['deleted'] += 1
    
    return stats

def cleanup_all_orphaned_records(dry_run=True):
    """
    Clean up all types of orphaned records.
    
    Args:
        dry_run (bool): If True, only report what would be deleted without actually deleting
    
    Returns:
        dict: Statistics about the cleanup operation
    """
    from datetime import datetime, timedelta
    
    db = Session()
    total_stats = {
        'zip_files': {'found': 0, 'deleted': 0, 'details': []},
        'encounter_files': {'found': 0, 'deleted': 0, 'details': []},
        'pdf_files': {'found': 0, 'deleted': 0, 'details': []},
        'reports': {'found': 0, 'deleted': 0, 'details': []}
    }
    
    try:
        logger.info("Starting comprehensive orphaned record cleanup...")
        
        # Clean up each type of orphaned record
        total_stats['zip_files'] = cleanup_orphaned_zip_files(db, dry_run)
        total_stats['encounter_files'] = cleanup_orphaned_encounter_files(db, dry_run)
        total_stats['pdf_files'] = cleanup_orphaned_pdf_files(db, dry_run)
        total_stats['reports'] = cleanup_orphaned_reports(db, dry_run)
        
        if not dry_run:
            db.commit()
            logger.info("Successfully committed all deletions")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        db.rollback()
        raise
    finally:
        db.close()
    
    return total_stats

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean up orphaned records and files')
    parser.add_argument('--execute', action='store_true', 
                       help='Actually delete the orphaned records (default is dry-run)')
    parser.add_argument('--type', choices=['zip', 'files', 'pdfs', 'reports', 'all'], 
                       default='all', help='Type of orphaned records to clean up (default: all)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("Starting orphaned record cleanup...")
    logger.info(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")
    logger.info(f"Type: {args.type}")
    
    stats = cleanup_all_orphaned_records(dry_run=not args.execute)
    
    # Print summary
    print("\n" + "="*60)
    print("CLEANUP SUMMARY")
    print("="*60)
    
    total_found = 0
    total_deleted = 0
    
    for record_type, type_stats in stats.items():
        if record_type == 'reports':
            print(f"\nReports (DR + Glaucoma):")
        else:
            print(f"\n{record_type.replace('_', ' ').title()}:")
        
        print(f"  Found: {type_stats['found']}")
        if args.execute:
            print(f"  Deleted: {type_stats['deleted']}")
        
        total_found += type_stats['found']
        total_deleted += type_stats['deleted']
        
        if type_stats['details'] and args.verbose:
            for detail in type_stats['details'][:5]:  # Show first 5 details
                print(f"    - {detail}")
            if len(type_stats['details']) > 5:
                print(f"    ... and {len(type_stats['details']) - 5} more")
    
    print("\n" + "="*60)
    print(f"TOTAL Found: {total_found}")
    if args.execute:
        print(f"TOTAL Deleted: {total_deleted}")
    else:
        print("Run with --execute to delete orphaned records")
    print("="*60)
    
    if total_found > 0 and not args.execute:
        print("\nOrphaned records found. Run with --execute to delete them.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())