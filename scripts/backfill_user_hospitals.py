#!/usr/bin/env python3
"""
Backfill script for assigning hospital_id to existing users.

This script assigns hospital_id to users based on their lab_unit assignments.
Required before production deployment of hospital isolation feature.

Usage:
    uv run python -m scripts.backfill_user_hospitals

Optional flags:
    --dry-run   Perform all calculations but do not commit changes.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure project root is importable when invoked as a module
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from models import Session, User  # noqa: E402
from sqlalchemy import and_  # noqa: E402
from utils.log_sanitize import sanitize_log_value # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_users_needing_hospital_assignment() -> List[User]:
    """
    Query users who need hospital_id assignment.
    
    Returns users where:
    - hospital_id is NULL
    - is_master_admin is False (master admins can have NULL hospital_id)
    """
    with Session() as db:
        users = db.query(User).filter(
            and_(
                User.hospital_id.is_(None),
                User.is_master_admin == False
            )
        ).all()
        
        # Detach from session to avoid lazy loading issues
        db.expunge_all()
        return users


def determine_hospital_for_user(user: User) -> Tuple[int | None, str]:
    """
    Determine appropriate hospital_id for a user based on their lab_units.
    
    Args:
        user: User object to determine hospital for
        
    Returns:
        Tuple of (hospital_id, reason_message)
    """
    with Session() as db:
        # Re-attach user to this session
        user = db.merge(user)
        
        # Get user's lab units with hospital info
        lab_units = user.lab_units
        
        if not lab_units:
            return None, "No lab units assigned"
        
        # Get unique hospital IDs from user's lab units
        hospital_ids = set()
        for lab_unit in lab_units:
            if lab_unit.hospital_id:
                hospital_ids.add(lab_unit.hospital_id)
        
        if not hospital_ids:
            return None, "Lab units have no hospital assignment"
        
        if len(hospital_ids) == 1:
            hospital_id = list(hospital_ids)[0]
            return hospital_id, f"Single hospital from {len(lab_units)} lab unit(s)"
        
        # Multiple hospitals - use the first lab unit's hospital
        # This is a reasonable default for existing users
        first_hospital_id = lab_units[0].hospital_id
        return first_hospital_id, f"First lab unit hospital (user has {len(hospital_ids)} hospitals)"


def backfill_user_hospitals(*, dry_run: bool = False) -> Dict[str, int]:
    """
    Assign hospital_id to users based on their lab_unit assignments.
    
    Args:
        dry_run: If True, calculate assignments but don't commit
        
    Returns:
        Dictionary with statistics:
        - assigned: Number of users assigned a hospital
        - skipped: Number of users skipped (no lab units)
        - already_assigned: Number of users already having hospital_id
    """
    stats = {
        'assigned': 0,
        'skipped': 0,
        'already_assigned': 0,
        'errors': 0
    }
    
    assignments = []  # Track assignments for reporting
    
    # Get users needing assignment
    users = get_users_needing_hospital_assignment()
    logger.info(f"Found {len(users)} users needing hospital assignment")
    
    # Determine hospital for each user
    for user in users:
        try:
            hospital_id, reason = determine_hospital_for_user(user)
            
            if hospital_id:
                assignments.append({
                    'user_id': user.id,
                    'username': user.username,
                    'hospital_id': hospital_id,
                    'reason': reason
                })
                stats['assigned'] += 1
            else:
                logger.warning(
                    "User %s (ID: %s): %s",
                    sanitize_log_value(user.username),
                    sanitize_log_value(user.id),
                    sanitize_log_value(reason),
                )
                stats['skipped'] += 1
                
        except Exception as e:
            logger.error(
                "Error processing user %s (ID: %s): %s",
                sanitize_log_value(user.username),
                sanitize_log_value(user.id),
                sanitize_log_value(e),
            )
            stats['errors'] += 1
    
    # Apply assignments
    if not dry_run and assignments:
        with Session() as db:
            for assignment in assignments:
                user = db.query(User).filter(User.id == assignment['user_id']).first()
                if user:
                    user.hospital_id = assignment['hospital_id']
                    logger.info(
                        "Assigned hospital_id=%s to user %s (ID: %s) - %s",
                        sanitize_log_value(assignment['hospital_id']),
                        sanitize_log_value(assignment['username']),
                        sanitize_log_value(assignment['user_id']),
                        sanitize_log_value(assignment['reason']),
                    )
            
            db.commit()
            logger.info("✅ Committed %s hospital assignments", len(assignments))
    
    # Generate report
    if dry_run:
        logger.info("\n=== DRY RUN REPORT ===")
        logger.info("Would assign hospital_id to %d users", stats['assigned'])
        logger.info("Would skip %d users (no lab units)", stats['skipped'])
        if assignments:
            logger.info("\nAssignments that would be made:")
            for a in assignments:
                logger.info(
                    "  - User %s (ID: %s) → Hospital %s (%s)",
                    sanitize_log_value(a['username']),
                    sanitize_log_value(a['user_id']),
                    sanitize_log_value(a['hospital_id']),
                    sanitize_log_value(a['reason']),
                )
    else:
        logger.info("\n=== BACKFILL COMPLETE ===")
        logger.info("Assigned: %d users", stats['assigned'])
        logger.info("Skipped: %d users", stats['skipped'])
        logger.info("Errors: %d users", stats['errors'])
    
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill hospital_id for existing users based on lab_unit assignments."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without committing changes.",
    )
    args = parser.parse_args()
    
    logger.info("Starting user hospital_id backfill process")
    
    try:
        stats = backfill_user_hospitals(dry_run=args.dry_run)
        
        if args.dry_run:
            print(f"\n[DRY RUN] Would update {stats['assigned']} users")
        else:
            print(f"\n✅ Updated {stats['assigned']} users with hospital_id")
            
        if stats['skipped'] > 0:
            print(f"⚠️  Skipped {stats['skipped']} users (no lab units)")
        if stats['errors'] > 0:
            print(f"❌ Errors: {stats['errors']} users")
            
    except Exception as e:
        logger.error(f"Fatal error during backfill process: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
