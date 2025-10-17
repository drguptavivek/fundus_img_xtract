#!/usr/bin/env python3
"""
Script to find and remove duplicate DirectImageUpload records based on file_hash.
This script will:
1. Find all duplicates based on file_hash
2. For each duplicate group, keep the oldest record (first uploaded)
3. Remove all associated data for the duplicates:
   - DirectImageVerify records
   - GradingTask records
   - Grade records
   - Consensus records
   - TaskTracker records
   - ImageGrading records
4. Finally remove the duplicate DirectImageUpload records
5. Optionally clean up the actual image files
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import (
    Session as DBSession,
    DirectImageUpload,
    DirectImageVerify,
    GradingTask,
    Grade,
    Consensus,
    TaskTracker,
    ImageGrading,
)
from utils.utils import with_session


def find_duplicates(db_session: Session) -> List[Dict]:
    """
    Find all duplicate DirectImageUpload records based on file_hash.
    Returns a list of groups, where each group contains duplicates of the same hash.
    """
    # Find all file_hashes that have duplicates
    duplicate_hashes_query = (
        select(DirectImageUpload.file_hash)
        .group_by(DirectImageUpload.file_hash)
        .having(func.count(DirectImageUpload.id) > 1)
    )
    
    duplicate_hashes = [row[0] for row in db_session.execute(duplicate_hashes_query).all()]
    
    if not duplicate_hashes:
        print("No duplicate hashes found.")
        return []
    
    # For each duplicate hash, get all records
    duplicate_groups = []
    for file_hash in duplicate_hashes:
        duplicates_query = (
            select(DirectImageUpload)
            .where(DirectImageUpload.file_hash == file_hash)
            .order_by(DirectImageUpload.created_at)  # Oldest first
        )
        
        duplicates = db_session.execute(duplicates_query).scalars().all()
        
        # Skip if there's only one record (shouldn't happen based on query above)
        if len(duplicates) <= 1:
            continue
            
        group = {
            'file_hash': file_hash,
            'keep_record': duplicates[0],  # Keep the oldest
            'remove_records': duplicates[1:],  # Remove the rest
            'total_count': len(duplicates)
        }
        duplicate_groups.append(group)
    
    return duplicate_groups


def get_associated_data_counts(db_session: Session, record_ids: List[int]) -> Dict[str, int]:
    """
    Get counts of all associated data for a list of DirectImageUpload IDs.
    """
    counts = {}
    
    # DirectImageVerify records
    verify_count = db_session.execute(
        select(func.count(DirectImageVerify.id))
        .where(DirectImageVerify.image_upload_id.in_(record_ids))
    ).scalar()
    counts['direct_image_verifies'] = verify_count
    
    # GradingTask records
    task_count = db_session.execute(
        select(func.count(GradingTask.id))
        .where(GradingTask.direct_image_upload_id.in_(record_ids))
    ).scalar()
    counts['grading_tasks'] = task_count
    
    # Grade records (through GradingTask)
    grade_count = db_session.execute(
        select(func.count(Grade.id))
        .where(Grade.task_id.in_(
            select(GradingTask.id)
            .where(GradingTask.direct_image_upload_id.in_(record_ids))
        ))
    ).scalar()
    counts['grades'] = grade_count
    
    # Consensus records (through GradingTask)
    consensus_count = db_session.execute(
        select(func.count(Consensus.id))
        .where(Consensus.task_id.in_(
            select(GradingTask.id)
            .where(GradingTask.direct_image_upload_id.in_(record_ids))
        ))
    ).scalar()
    counts['consensus'] = consensus_count
    
    # TaskTracker records (through GradingTask)
    tracker_count = db_session.execute(
        select(func.count(TaskTracker.id))
        .where(TaskTracker.task_id.in_(
            select(GradingTask.id)
            .where(GradingTask.direct_image_upload_id.in_(record_ids))
        ))
    ).scalar()
    counts['task_trackers'] = tracker_count
    
    # ImageGrading records
    image_grading_count = db_session.execute(
        select(func.count(ImageGrading.id))
        .where(ImageGrading.direct_image_upload_id.in_(record_ids))
    ).scalar()
    counts['image_gradings'] = image_grading_count
    
    return counts


def remove_associated_data(db_session: Session, record_ids: List[int]) -> None:
    """
    Remove all associated data for the given DirectImageUpload IDs.
    This is done in the correct order to respect foreign key constraints.
    """
    if not record_ids:
        return
    
    print(f"Removing associated data for {len(record_ids)} DirectImageUpload records...")
    
    # 1. Remove TaskTracker records (through GradingTask)
    tracker_delete = delete(TaskTracker).where(
        TaskTracker.task_id.in_(
            select(GradingTask.id)
            .where(GradingTask.direct_image_upload_id.in_(record_ids))
        )
    )
    result = db_session.execute(tracker_delete)
    print(f"  Deleted {result.rowcount} TaskTracker records")
    
    # 2. Remove Consensus records (through GradingTask)
    consensus_delete = delete(Consensus).where(
        Consensus.task_id.in_(
            select(GradingTask.id)
            .where(GradingTask.direct_image_upload_id.in_(record_ids))
        )
    )
    result = db_session.execute(consensus_delete)
    print(f"  Deleted {result.rowcount} Consensus records")
    
    # 3. Remove Grade records (through GradingTask)
    grade_delete = delete(Grade).where(
        Grade.task_id.in_(
            select(GradingTask.id)
            .where(GradingTask.direct_image_upload_id.in_(record_ids))
        )
    )
    result = db_session.execute(grade_delete)
    print(f"  Deleted {result.rowcount} Grade records")
    
    # 4. Remove ImageGrading records
    image_grading_delete = delete(ImageGrading).where(
        ImageGrading.direct_image_upload_id.in_(record_ids)
    )
    result = db_session.execute(image_grading_delete)
    print(f"  Deleted {result.rowcount} ImageGrading records")
    
    # 5. Remove GradingTask records
    task_delete = delete(GradingTask).where(
        GradingTask.direct_image_upload_id.in_(record_ids)
    )
    result = db_session.execute(task_delete)
    print(f"  Deleted {result.rowcount} GradingTask records")
    
    # 6. Remove DirectImageVerify records
    verify_delete = delete(DirectImageVerify).where(
        DirectImageVerify.image_upload_id.in_(record_ids)
    )
    result = db_session.execute(verify_delete)
    print(f"  Deleted {result.rowcount} DirectImageVerify records")


def remove_duplicate_records(db_session: Session, record_ids: List[int]) -> None:
    """
    Remove the duplicate DirectImageUpload records.
    """
    if not record_ids:
        return
    
    # Get file paths before deletion for optional file cleanup
    records_query = select(DirectImageUpload).where(DirectImageUpload.id.in_(record_ids))
    records = db_session.execute(records_query).scalars().all()
    
    file_paths = []
    for record in records:
        if record.filename and record.folder_rel:
            # Construct full path
            base_dir = Path(__file__).parent.parent
            file_path = base_dir / record.folder_rel / record.filename
            file_paths.append(file_path)
    
    # Delete the records
    delete_query = delete(DirectImageUpload).where(DirectImageUpload.id.in_(record_ids))
    result = db_session.execute(delete_query)
    print(f"Deleted {result.rowcount} DirectImageUpload records")
    
    return file_paths


def cleanup_files(file_paths: List[Path], dry_run: bool = True) -> None:
    """
    Clean up the actual image files on disk.
    """
    if not file_paths:
        return
    
    print(f"\n{'[DRY RUN] Would clean up' if dry_run else 'Cleaning up'} {len(file_paths)} files...")
    
    for file_path in file_paths:
        if file_path.exists():
            if not dry_run:
                try:
                    file_path.unlink()
                    print(f"  Deleted file: {file_path}")
                except Exception as e:
                    print(f"  Error deleting file {file_path}: {e}")
            else:
                print(f"  Would delete: {file_path}")
        else:
            print(f"  File not found: {file_path}")


def main(dry_run: bool = True, cleanup_files_flag: bool = False):
    """
    Main function to find and remove duplicates.
    """
    print(f"{'[DRY RUN] ' if dry_run else ''}Starting duplicate cleanup process...")
    print(f"Timestamp: {datetime.now()}")
    
    with with_session() as db_session:
        # Find all duplicates
        print("\n1. Finding duplicate records...")
        duplicate_groups = find_duplicates(db_session)
        
        if not duplicate_groups:
            print("No duplicates found. Nothing to do.")
            return
        
        # Print summary
        total_duplicates = sum(group['total_count'] - 1 for group in duplicate_groups)
        print(f"\nFound {len(duplicate_groups)} groups of duplicates")
        print(f"Total duplicate records to remove: {total_duplicates}")
        
        # Get counts of associated data
        all_duplicate_ids = []
        for group in duplicate_groups:
            all_duplicate_ids.extend([r.id for r in group['remove_records']])
        
        print("\n2. Analyzing associated data...")
        counts = get_associated_data_counts(db_session, all_duplicate_ids)
        print("Associated data to be removed:")
        for data_type, count in counts.items():
            print(f"  {data_type}: {count}")
        
        # Print details for each group
        print("\n3. Duplicate group details:")
        for i, group in enumerate(duplicate_groups, 1):
            print(f"\nGroup {i}: Hash {group['file_hash'][:8]}...")
            print(f"  Keep: ID {group['keep_record'].id}, "
                  f"Filename: {group['keep_record'].filename}, "
                  f"Created: {group['keep_record'].created_at}")
            print(f"  Remove ({len(group['remove_records'])} records):")
            for record in group['remove_records']:
                print(f"    ID {record.id}, "
                      f"Filename: {record.filename}, "
                      f"Created: {record.created_at}")
        
        if dry_run:
            print("\n[DRY RUN] No changes made. Run with --execute to apply changes.")
            return
        
        # Confirm before proceeding
        if not dry_run:
            response = input("\nProceed with cleanup? (y/N): ")
            if response.lower() != 'y':
                print("Cleanup cancelled.")
                return
        
        # Remove associated data
        print("\n4. Removing associated data...")
        remove_associated_data(db_session, all_duplicate_ids)
        
        # Remove duplicate records and get file paths
        print("\n5. Removing duplicate records...")
        file_paths = remove_duplicate_records(db_session, all_duplicate_ids)
        
        # Clean up files if requested
        if cleanup_files_flag:
            cleanup_files(file_paths, dry_run=False)
        
        # Commit all changes
        db_session.commit()
        print("\n✅ Cleanup completed successfully!")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Find and remove duplicate DirectImageUpload records"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the cleanup (default is dry-run)"
    )
    parser.add_argument(
        "--cleanup-files",
        action="store_true",
        help="Also delete the actual image files from disk"
    )
    
    args = parser.parse_args()
    
    try:
        main(dry_run=not args.execute, cleanup_files_flag=args.cleanup_files)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)