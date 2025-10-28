#!/usr/bin/env python3
"""
Performance testing script for Tasks DataFrame generation approaches.

This script tests and compares the performance of three different approaches:
1. Multiple joinedload approach
2. Batch query optimization  
3. Raw SQL query

Usage:
    python scripts/test_tasks_dataframe_performance.py [--approach 1|2|3|all] [--limit 1000]
"""

import sys
import os
import time
import argparse
from datetime import datetime, timedelta
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.dataFrameTasks import (
    generate_tasks_dataframe_approach1,
    generate_tasks_dataframe_approach2, 
    generate_tasks_dataframe_approach3,
    get_filtered_tasks_dataframe
)
from utils.utils import with_session
from api.kpis.kpiutils import get_user_permissions


def time_function(func, *args, **kwargs):
    """Time a function execution and return result + timing info."""
    start_time = time.time()
    start_memory = get_memory_usage()
    
    try:
        result = func(*args, **kwargs)
        end_time = time.time()
        end_memory = get_memory_usage()
        
        return {
            'result': result,
            'execution_time': end_time - start_time,
            'memory_used': end_memory - start_memory,
            'success': True,
            'error': None
        }
    except Exception as e:
        end_time = time.time()
        end_memory = get_memory_usage()
        
        return {
            'result': None,
            'execution_time': end_time - start_time,
            'memory_used': end_memory - start_memory,
            'success': False,
            'error': str(e)
        }


def get_memory_usage():
    """Get current memory usage in MB."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # Convert to MB
    except ImportError:
        return 0


def test_approach(approach_num: int, db, limit: int = None):
    """Test a specific approach and return performance metrics."""
    print(f"\n{'='*60}")
    print(f"Testing Approach {approach_num}")
    print(f"{'='*60}")
    
    # Set up test parameters
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)  # Last 30 days
    
    params = {
        'start_date': start_date,
        'end_date': end_date
    }
    
    # Add limit if specified
    if limit:
        params['limit'] = limit
    
    # Get user permissions (use admin user for full access)
    try:
        user_lab_unit_ids = get_user_permissions(1)  # Assuming admin user ID 1
    except:
        user_lab_unit_ids = set()
    
    # Choose the appropriate function
    if approach_num == 1:
        func = generate_tasks_dataframe_approach1
        func_name = "generate_tasks_dataframe_approach1"
    elif approach_num == 2:
        func = generate_tasks_dataframe_approach2
        func_name = "generate_tasks_dataframe_approach2"
    elif approach_num == 3:
        func = generate_tasks_dataframe_approach3
        func_name = "generate_tasks_dataframe_approach3"
    else:
        raise ValueError("Approach must be 1, 2, or 3")
    
    # Time the execution
    print(f"Running {func_name}...")
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    if limit:
        print(f"Limit: {limit} records")
    
    metrics = time_function(
        func,
        db,
        start_date=start_date,
        end_date=end_date
    )
    
    # Report results
    print(f"\nResults for Approach {approach_num}:")
    print(f"  Success: {metrics['success']}")
    
    if metrics['success']:
        df = metrics['result']
        record_count = len(df) if df is not None else 0
        
        print(f"  Records returned: {record_count}")
        print(f"  Execution time: {metrics['execution_time']:.3f} seconds")
        print(f"  Memory used: {metrics['memory_used']:.2f} MB")
        
        if record_count > 0:
            print(f"  Time per record: {metrics['execution_time']/record_count*1000:.2f} ms")
            print(f"  Memory per record: {metrics['memory_used']/record_count:.2f} MB")
        
        # Show sample of data structure
        if df is not None and not df.empty:
            print(f"\n  Sample columns: {list(df.columns)[:10]}...")
            print(f"  First record keys: {list(df.iloc[0].keys())[:5]}...")
    else:
        print(f"  Error: {metrics['error']}")
    
    return metrics


def test_filtering_performance(db, approach: int = 2):
    """Test filtering performance with different approaches."""
    print(f"\n{'='*60}")
    print(f"Testing Filtering Performance (Approach {approach})")
    print(f"{'='*60}")
    
    # Test with various filter combinations
    test_cases = [
        {
            'name': 'No filters',
            'params': {}
        },
        {
            'name': 'Date filter only',
            'params': {
                'start_date': datetime.now() - timedelta(days=7),
                'end_date': datetime.now()
            }
        },
        {
            'name': 'State filter only',
            'params': {
                'states': ['pending', 'final']
            }
        },
        {
            'name': 'Disease filter only',
            'params': {
                'disease_ids': [1, 2]  # Assuming these exist
            }
        },
        {
            'name': 'Multiple filters',
            'params': {
                'start_date': datetime.now() - timedelta(days=7),
                'states': ['final'],
                'disease_ids': [1, 2],
                'image_source_types': ['direct']
            }
        }
    ]
    
    user_lab_unit_ids = set()  # Empty set for testing
    
    for test_case in test_cases:
        print(f"\n  Testing: {test_case['name']}")
        
        metrics = time_function(
            get_filtered_tasks_dataframe,
            db,
            test_case['params'],
            user_lab_unit_ids,
            approach=approach
        )
        
        if metrics['success']:
            df = metrics['result']
            record_count = len(df) if df is not None else 0
            print(f"    Records: {record_count}, Time: {metrics['execution_time']:.3f}s")
        else:
            print(f"    Error: {metrics['error']}")


def compare_approaches(db, limit: int = None):
    """Compare all three approaches with the same parameters."""
    print(f"\n{'='*80}")
    print("PERFORMANCE COMPARISON - ALL APPROACHES")
    print(f"{'='*80}")
    
    # Test parameters
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    print(f"Test Parameters:")
    print(f"  Date range: {start_date.date()} to {end_date.date()}")
    if limit:
        print(f"  Record limit: {limit}")
    print(f"  Database: SQLite (production-like)")
    
    # Test all approaches
    results = {}
    for approach in [1, 2, 3]:
        results[approach] = test_approach(approach, db, limit)
    
    # Summary comparison
    print(f"\n{'='*80}")
    print("PERFORMANCE SUMMARY")
    print(f"{'='*80}")
    
    print(f"{'Approach':<10} {'Time (s)':<10} {'Records':<10} {'Time/Rec (ms)':<15} {'Memory (MB)':<12}")
    print(f"{'-'*80}")
    
    for approach in [1, 2, 3]:
        metrics = results[approach]
        if metrics['success']:
            df = metrics['result']
            record_count = len(df) if df is not None else 0
            time_per_record = (metrics['execution_time'] / record_count * 1000) if record_count > 0 else 0
            
            print(f"{approach:<10} {metrics['execution_time']:<10.3f} {record_count:<10} {time_per_record:<15.2f} {metrics['memory_used']:<12.2f}")
        else:
            print(f"{approach:<10} {'ERROR':<10} {'-':<10} {'-':<15} {'-':<12}")
    
    # Find best performer
    successful_approaches = {k: v for k, v in results.items() if v['success']}
    
    if successful_approaches:
        # Fastest by total time
        fastest = min(successful_approaches.items(), key=lambda x: x[1]['execution_time'])
        print(f"\nFastest by total time: Approach {fastest[0]} ({fastest[1]['execution_time']:.3f}s)")
        
        # Fastest per record
        if fastest[1]['result'] is not None and len(fastest[1]['result']) > 0:
            fastest_per_record = min(
                successful_approaches.items(), 
                key=lambda x: x[1]['execution_time'] / len(x[1]['result']) if len(x[1]['result']) > 0 else float('inf')
            )
            print(f"Fastest per record: Approach {fastest_per_record[0]}")
        
        # Most memory efficient
        most_efficient = min(successful_approaches.items(), key=lambda x: x[1]['memory_used'])
        print(f"Most memory efficient: Approach {most_efficient[0]} ({most_efficient[1]['memory_used']:.2f} MB)")


def main():
    """Main function to run performance tests."""
    parser = argparse.ArgumentParser(description='Test Tasks DataFrame performance')
    parser.add_argument('--approach', type=int, choices=[1, 2, 3], 
                       help='Test specific approach (1, 2, or 3)')
    parser.add_argument('--limit', type=int, 
                       help='Limit number of records for testing')
    parser.add_argument('--compare', action='store_true',
                       help='Compare all approaches')
    parser.add_argument('--filter-test', action='store_true',
                       help='Test filtering performance')
    
    args = parser.parse_args()
    
    print("Tasks DataFrame Performance Testing")
    print("=" * 50)
    
    with with_session() as db:
        if args.compare:
            compare_approaches(db, args.limit)
        elif args.filter_test:
            test_filtering_performance(db)
        elif args.approach:
            test_approach(args.approach, db, args.limit)
        else:
            # Default: compare all approaches
            compare_approaches(db, args.limit)


if __name__ == "__main__":
    main()