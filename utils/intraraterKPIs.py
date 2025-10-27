"""Utility functions for calculating intra-rater reliability KPIs."""

from typing import List, Dict, Any, Tuple
from collections import defaultdict
import json


def calculate_kpis_for_tasks(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate KPIs for intra-rater reliability tasks.
    
    Args:
        tasks: List of task dictionaries with original and repeated grades
        
    Returns:
        Dictionary with calculated KPIs by disease type
    """
    disease_stats = defaultdict(lambda: {
        'total_tasks': 0,
        'consistent_grades': 0,
        'inconsistent_grades': 0,
        'grade_pairs': []  # List of (original, repeated) tuples
    })
    
    for task in tasks:
        disease_name = task.get('disease_name', 'Unknown')
        original_grade = task.get('original_grade_name')
        repeated_grade = task.get('grade_name')
        
        # Skip tasks without proper grading data
        if not original_grade or not repeated_grade:
            continue
            
        disease_stats[disease_name]['total_tasks'] += 1
        disease_stats[disease_name]['grade_pairs'].append((original_grade, repeated_grade))
        
        # Check if original and repeated grades match
        if original_grade == repeated_grade:
            disease_stats[disease_name]['consistent_grades'] += 1
        else:
            disease_stats[disease_name]['inconsistent_grades'] += 1
    
    # Calculate final KPIs
    kpis = {}
    for disease, stats in disease_stats.items():
        total = stats['total_tasks']
        consistent = stats['consistent_grades']
        inconsistent = stats['inconsistent_grades']
        
        consistency_rate = (consistent / total * 100) if total > 0 else 0
        
        kpis[disease] = {
            'total_tasks': total,
            'consistent_grades': consistent,
            'inconsistent_grades': inconsistent,
            'consistency_rate': round(consistency_rate, 2),
            'grade_pairs': stats['grade_pairs']
        }
    
    return kpis


def generate_cross_tabulation(tasks: List[Dict[str, Any]], disease_name: str, grade_ordering: str = 'id') -> Dict[str, Any]:
    """
    Generate cross-tabulation for a specific disease showing original vs repeated grades.
    
    Args:
        tasks: List of task dictionaries
        disease_name: Name of disease to generate cross-tab for
        grade_ordering: How to order grades ('id' for by ID, 'name' for by name)
        
    Returns:
        Dictionary with cross-tabulation data
    """
    # Collect all unique grades for this disease with their IDs
    all_grade_info = {}  # Maps grade_name -> grade_id
    grade_pairs = []
    
    for task in tasks:
        if task.get('disease_name') != disease_name:
            continue
            
        original_grade = task.get('original_grade_name')
        original_grade_id = task.get('original_grade_id')
        repeated_grade = task.get('grade_name')
        repeated_grade_id = task.get('disease_grading_id')
        
        if original_grade and repeated_grade:
            # Store grade name to ID mapping for original grade
            if original_grade and original_grade_id is not None:
                all_grade_info[original_grade] = original_grade_id
            # Store grade name to ID mapping for repeated grade  
            if repeated_grade and repeated_grade_id is not None:
                all_grade_info[repeated_grade] = repeated_grade_id
            
            grade_pairs.append((original_grade, repeated_grade))
    
    # Determine order based on grade_ordering parameter
    if grade_ordering == 'id' and all_grade_info:
        # Sort by grade ID
        all_grades = sorted(all_grade_info.keys(), key=lambda x: all_grade_info[x])
    else:
        # Sort by grade name
        all_grades = sorted(list(all_grade_info.keys()))
    
    # Create cross-tabulation matrix
    matrix = {}
    for orig in all_grades:
        matrix[orig] = {}
        for rep in all_grades:
            matrix[orig][rep] = 0
    
    # Fill in the counts
    for orig, rep in grade_pairs:
        if orig in matrix and rep in matrix[orig]:
            matrix[orig][rep] = matrix[orig].get(rep, 0) + 1
    
    return {
        'rows': all_grades,  # Original grades
        'columns': all_grades,  # Repeated grades
        'matrix': matrix,
        'total_tasks': len(grade_pairs)
    }


def generate_kpi_dataframe(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate a simplified data frame with key metrics for each task.
    
    Args:
        tasks: List of task dictionaries
        
    Returns:
        List of dictionaries with simplified metrics for each task
    """
    dataframe = []
    
    for task in tasks:
        row = {
            'id': task.get('id'),
            'task_uuid': task.get('uuid'),
            'disease': task.get('disease_name'),
            'lab_unit': task.get('lab_unit_name'),
            'batch_id': task.get('batch_id'),
            'original_grade': task.get('original_grade_name'),
            'repeated_grade': task.get('grade_name'),
            'consistent': task.get('original_grade_name') == task.get('grade_name'),
            'graded_at': task.get('graded_at'),
            'created_at': task.get('created_at'),
            'task_state': task.get('state')
        }
        dataframe.append(row)
    
    return dataframe


def calculate_cohens_kappa(tasks: List[Dict[str, Any]], disease_name: str) -> float:
    """
    Calculate Cohen's Kappa for measuring inter-rater agreement for a specific disease.
    For intra-rater, this measures consistency between original and repeated grading.
    
    Args:
        tasks: List of task dictionaries
        disease_name: Name of the disease to calculate for
        
    Returns:
        Cohen's Kappa value
    """
    from collections import Counter
    
    # Filter tasks for the specific disease and create dataframe-style list
    disease_tasks = [task for task in tasks if task.get('disease_name') == disease_name]
    
    if not disease_tasks:
        return 0.0
    
    # Extract grade pairs
    grade_pairs = [(task.get('original_grade_name'), task.get('grade_name')) 
                   for task in disease_tasks 
                   if task.get('original_grade_name') and task.get('grade_name')]
    
    if not grade_pairs:
        return 0.0
    
    # Get all unique grades
    all_grades = set()
    for orig, rep in grade_pairs:
        all_grades.add(orig)
        all_grades.add(rep)
    
    all_grades = sorted(list(all_grades))
    n_grades = len(all_grades)
    
    if n_grades < 2:
        return 1.0  # Perfect agreement if only one grade type
    
    # Create index mapping
    grade_to_idx = {grade: idx for idx, grade in enumerate(all_grades)}
    
    # Create confusion/contingency matrix
    n = len(grade_pairs)
    observed_matrix = [[0 for _ in range(n_grades)] for _ in range(n_grades)]
    
    for orig, rep in grade_pairs:
        i = grade_to_idx[orig]
        j = grade_to_idx[rep]
        observed_matrix[i][j] += 1
    
    # Calculate observed agreement
    observed_agreement = sum(observed_matrix[i][i] for i in range(n_grades)) / n
    
    # Calculate expected agreement
    row_totals = [sum(observed_matrix[i]) for i in range(n_grades)]  # Original grades totals
    col_totals = [sum(observed_matrix[i][j] for i in range(n_grades)) for j in range(n_grades)]  # Repeated grades totals
    
    expected_agreement = sum(
        (row_totals[i] / n) * (col_totals[i] / n)
        for i in range(n_grades)
    )
    
    # Calculate kappa
    if expected_agreement == 1.0:
        return 1.0  # Avoid division by zero
    
    kappa = (observed_agreement - expected_agreement) / (1 - expected_agreement)
    return round(kappa, 3)


def calculate_weighted_kappa(tasks: List[Dict[str, Any]], disease_name: str, weights: str = 'quadratic') -> float:
    """
    Calculate weighted kappa for ordinal data where distance between categories matters.
    
    Args:
        tasks: List of task dictionaries
        disease_name: Name of the disease to calculate for
        weights: Type of weights to use ('quadratic' or 'linear')
        
    Returns:
        Weighted Kappa value
    """
    # Filter tasks for the specific disease
    disease_tasks = [task for task in tasks if task.get('disease_name') == disease_name]
    
    if not disease_tasks:
        return 0.0
    
    # Extract grade pairs
    grade_pairs = [(task.get('original_grade_name'), task.get('grade_name')) 
                   for task in disease_tasks 
                   if task.get('original_grade_name') and task.get('grade_name')]
    
    if not grade_pairs:
        return 0.0
    
    # Get all unique grades and sort them to create ordinal mapping
    all_grades = set()
    for orig, rep in grade_pairs:
        all_grades.add(orig)
        all_grades.add(rep)
    
    all_grades = sorted(list(all_grades))  # Order grades to use as ordinal scale
    n_grades = len(all_grades)
    
    if n_grades < 2:
        return 1.0  # Perfect agreement if only one grade type
    
    # Create index mapping (this creates the ordinal scale)
    grade_to_idx = {grade: idx for idx, grade in enumerate(all_grades)}
    
    # Create confusion matrix
    n = len(grade_pairs)
    observed_matrix = [[0 for _ in range(n_grades)] for _ in range(n_grades)]
    
    for orig, rep in grade_pairs:
        i = grade_to_idx[orig]
        j = grade_to_idx[rep]
        observed_matrix[i][j] += 1
    
    # Normalize observed matrix to get proportions
    observed_prop = [[observed_matrix[i][j] / n for j in range(n_grades)] for i in range(n_grades)]
    
    # Calculate row and column totals (marginal probabilities)
    row_totals = [sum(observed_prop[i]) for i in range(n_grades)]
    col_totals = [sum(observed_prop[i][j] for i in range(n_grades)) for j in range(n_grades)]
    
    # Create weight matrix based on the distance between categories
    weights_matrix = [[0.0 for _ in range(n_grades)] for _ in range(n_grades)]
    for i in range(n_grades):
        for j in range(n_grades):
            if i == j:
                weights_matrix[i][j] = 0.0  # No penalty for perfect agreement
            else:
                diff = abs(i - j)
                if weights == 'quadratic':
                    weights_matrix[i][j] = diff ** 2  # Quadratic weights
                elif weights == 'linear':
                    weights_matrix[i][j] = diff  # Linear weights
                else:
                    weights_matrix[i][j] = diff ** 2  # Default to quadratic
    
    # Calculate observed disagreement (weighted)
    observed_disagreement = sum(
        weights_matrix[i][j] * observed_prop[i][j] 
        for i in range(n_grades) 
        for j in range(n_grades)
    )
    
    # Calculate expected disagreement (weighted)
    expected_disagreement = sum(
        weights_matrix[i][j] * row_totals[i] * col_totals[j]
        for i in range(n_grades)
        for j in range(n_grades)
    )
    
    # Calculate weighted kappa
    if expected_disagreement == 0:
        return 1.0 if observed_disagreement == 0 else 0.0  # Avoid division by zero
    
    weighted_kappa = 1 - (observed_disagreement / expected_disagreement)
    return round(weighted_kappa, 3)


def get_disease_summary(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Get a comprehensive summary for all diseases.
    
    Args:
        tasks: List of task dictionaries
        
    Returns:
        Dictionary with comprehensive summary for all diseases
    """
    kpis = calculate_kpis_for_tasks(tasks)
    
    summary = {
        'total_tasks': len(tasks),
        'diseases': {}
    }
    
    for disease, stats in kpis.items():
        summary['diseases'][disease] = {
            'total_tasks': stats['total_tasks'],
            'consistent_grades': stats['consistent_grades'],
            'inconsistent_grades': stats['inconsistent_grades'],
            'consistency_rate': stats['consistency_rate'],
            'cohens_kappa': calculate_cohens_kappa(tasks, disease),
            'weighted_kappa': calculate_weighted_kappa(tasks, disease)
        }
    
    return summary