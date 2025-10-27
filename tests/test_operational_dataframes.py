"""
Test script for operational dataframes utility functions.

This script validates that the dataframe generators work correctly
and produce expected output formats.
"""

import sys
import os
from datetime import datetime, timedelta

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.dataframeEncounterFiles import (
    generate_encounter_upload_metrics_df,
    generate_image_upload_metrics_df,
    generate_grading_efficiency_df,
    generate_consensus_metrics_df,
    generate_workflow_analysis_df,
    get_common_date_ranges,
    get_operational_summary_stats
)
from utils.utils import with_session


def test_encounter_upload_metrics():
    """Test encounter upload metrics dataframe generation."""
    print("Testing encounter upload metrics dataframe generation...")
    
    try:
        # Test with date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        df = generate_encounter_upload_metrics_df(start_date=start_date, end_date=end_date)
        
        print(f"Generated dataframe with {len(df)} rows")
        if not df.empty:
            print(f"Date range: {df['upload_date'].min()} to {df['upload_date'].max()}")
            print(f"Columns: {list(df.columns)}")
            
            # Show some sample data
            print("\nSample data:")
            print(df[['encounter_id', 'patient_name', 'total_images', 'has_dr_report', 
                     'has_glaucoma_report', 'completely_verified']].head())
            
            # Show summary stats
            stats = get_operational_summary_stats(df)
            print("\nSummary statistics:")
            for key, value in stats.items():
                print(f"  {key}: {value}")
        else:
            print("No data found for the specified date range")
            
        print("✓ Encounter upload metrics test passed\n")
        return True
        
    except Exception as e:
        print(f"✗ Encounter upload metrics test failed: {e}")
        return False


def test_image_upload_metrics():
    """Test image upload metrics dataframe generation."""
    print("Testing image upload metrics dataframe generation...")
    
    try:
        # Test with date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        df = generate_image_upload_metrics_df(start_date=start_date, end_date=end_date)
        
        print(f"Generated dataframe with {len(df)} rows")
        if not df.empty:
            print(f"Date range: {df['upload_date'].min()} to {df['upload_date'].max()}")
            print(f"Columns: {list(df.columns)}")
            
            # Show some sample data
            print("\nSample data:")
            print(df[['image_id', 'upload_type', 'filename', 'lab_unit_name', 
                     'upload_date']].head())
        else:
            print("No data found for the specified date range")
            
        print("✓ Image upload metrics test passed\n")
        return True
        
    except Exception as e:
        print(f"✗ Image upload metrics test failed: {e}")
        return False


def test_grading_efficiency():
    """Test grading efficiency dataframe generation."""
    print("Testing grading efficiency dataframe generation...")
    
    try:
        # Test with date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        df = generate_grading_efficiency_df(start_date=start_date, end_date=end_date)
        
        print(f"Generated dataframe with {len(df)} rows")
        if not df.empty:
            print(f"Date range: {df['grading_date'].min()} to {df['grading_date'].max()}")
            print(f"Columns: {list(df.columns)}")
            
            # Show some sample data
            print("\nSample data:")
            print(df[['task_id', 'disease_name', 'lab_unit_name', 'task_state',
                     'resident_grader_username', 'resident2_grader_username']].head())
        else:
            print("No data found for the specified date range")
            
        print("✓ Grading efficiency test passed\n")
        return True
        
    except Exception as e:
        print(f"✗ Grading efficiency test failed: {e}")
        return False



