#!/usr/bin/env python3
"""
Route role analyzer for admin visibility.

This module provides functionality to analyze route decorators and extract
role information for display in the admin UI.
"""

import ast
import os
from typing import Dict, List, Set, Tuple
from flask import current_app

def extract_roles_from_decorators(file_path: str) -> List[Dict[str, any]]:
    """
    Extract role information from route decorators in a Python file.
    
    Args:
        file_path: Path to the Python file to analyze
        
    Returns:
        List of dictionaries containing route and role information
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        routes_info = []
        
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef):
                # Look for route decorators
                route_info = _analyze_function_decorators(node, file_path)
                if route_info:
                    routes_info.extend(route_info)
                    
        return routes_info
    except Exception as e:
        if current_app:
            current_app.logger.warning(f"Failed to analyze {file_path}: {e}")
        return []

def _analyze_function_decorators(function_node: ast.FunctionDef, file_path: str) -> List[Dict[str, any]]:
    """
    Analyze decorators on a function to extract route and role information.
    
    Args:
        function_node: AST node for the function
        file_path: Path to the file containing the function
        
    Returns:
        List of route information dictionaries
    """
    routes_info = []
    
    for decorator in function_node.decorator_list:
        # Check for route decorators
        route_info = _extract_route_info(decorator, function_node.name, file_path)
        if route_info:
            # Check for role decorators on the same function
            role_info = _extract_role_info(function_node.decorator_list)
            if role_info:
                route_info.update(role_info)
                routes_info.append(route_info)
                
    return routes_info

def _extract_route_info(decorator: ast.AST, function_name: str, file_path: str) -> Dict[str, any] | None:
    """
    Extract route information from a decorator.
    
    Args:
        decorator: AST node for the decorator
        function_name: Name of the function
        file_path: Path to the file
        
    Returns:
        Route information dictionary or None if not a route decorator
    """
    if isinstance(decorator, ast.Call):
        # Check for @bp.route(...) or @app.route(...)
        if isinstance(decorator.func, ast.Attribute) and decorator.func.attr == 'route':
            if decorator.args:
                route_path = ast.get_source_segment(open(file_path).read(), decorator.args[0])
                return {
                    'function': function_name,
                    'file': os.path.relpath(file_path),
                    'route': route_path.strip('\'"'),
                    'methods': _extract_methods(decorator.keywords)
                }
        # Check for @route(...) 
        elif isinstance(decorator.func, ast.Name) and decorator.func.id == 'route':
            if decorator.args:
                route_path = ast.get_source_segment(open(file_path).read(), decorator.args[0])
                return {
                    'function': function_name,
                    'file': os.path.relpath(file_path),
                    'route': route_path.strip('\'"'),
                    'methods': _extract_methods(decorator.keywords)
                }
    return None

def _extract_methods(keywords: List[ast.keyword]) -> List[str]:
    """
    Extract HTTP methods from decorator keywords.
    
    Args:
        keywords: List of keyword arguments from decorator
        
    Returns:
        List of HTTP methods
    """
    for keyword in keywords:
        if keyword.arg == 'methods' and isinstance(keyword.value, ast.List):
            methods = []
            for elt in keyword.value.elts:
                if isinstance(elt, ast.Constant):  # Python 3.8+
                    methods.append(str(elt.value))
                elif isinstance(elt, ast.Str):  # Python < 3.8
                    methods.append(elt.s)
            return methods
    return ['GET']  # Default method

def _extract_role_info(decorators: List[ast.AST]) -> Dict[str, any] | None:
    """
    Extract role information from decorators.
    
    Args:
        decorators: List of decorator AST nodes
        
    Returns:
        Role information dictionary or None if no role decorators found
    """
    roles = []
    for decorator in decorators:
        if isinstance(decorator, ast.Call):
            # Check for @roles_required(...)
            if isinstance(decorator.func, ast.Name) and decorator.func.id in ['roles_required', 'roles_any', 'roles_all']:
                role_names = _extract_role_names(decorator.args)
                if role_names:
                    roles.extend(role_names)
            # Check for method calls like @auth.roles_required(...)
            elif isinstance(decorator.func, ast.Attribute) and decorator.func.attr in ['roles_required', 'roles_any', 'roles_all']:
                role_names = _extract_role_names(decorator.args)
                if role_names:
                    roles.extend(role_names)
                    
    if roles:
        return {'roles': list(set(roles)), 'role_count': len(set(roles))}
    return None

def _extract_role_names(args: List[ast.AST]) -> List[str]:
    """
    Extract role names from decorator arguments.
    
    Args:
        args: List of argument AST nodes
        
    Returns:
        List of role names
    """
    roles = []
    for arg in args:
        if isinstance(arg, ast.Constant):  # Python 3.8+
            roles.append(str(arg.value))
        elif isinstance(arg, ast.Str):  # Python < 3.8
            roles.append(arg.s)
        elif isinstance(arg, ast.Name):  # Role constants like ROLE_ADMIN
            # We can't resolve these at analysis time, but we can note them
            roles.append(f"<{arg.id}>")
    return roles

def analyze_all_routes(base_path: str = '.') -> List[Dict[str, any]]:
    """
    Analyze all route files to extract role information.
    
    Args:
        base_path: Base path to search for route files
        
    Returns:
        List of route information dictionaries
    """
    all_routes = []
    
    # Find all routes.py files
    for root, dirs, files in os.walk(base_path):
        # Skip virtual environments and other irrelevant directories
        dirs[:] = [d for d in dirs if d not in ['venv', '.venv', '__pycache__', '.git']]
        
        for file in files:
            if file == 'routes.py' or (file.endswith('.py') and 'route' in file):
                file_path = os.path.join(root, file)
                try:
                    routes_info = extract_roles_from_decorators(file_path)
                    all_routes.extend(routes_info)
                except Exception as e:
                    if current_app:
                        current_app.logger.warning(f"Failed to analyze {file_path}: {e}")
                        
    return all_routes

def get_role_usage_statistics(routes_info: List[Dict[str, any]]) -> Dict[str, int]:
    """
    Get statistics on role usage across all routes.
    
    Args:
        routes_info: List of route information dictionaries
        
    Returns:
        Dictionary mapping role names to usage counts
    """
    role_counts = {}
    for route in routes_info:
        if 'roles' in route:
            for role in route['roles']:
                # Skip role constants that we can't resolve
                if not role.startswith('<'):
                    role_counts[role] = role_counts.get(role, 0) + 1
    return role_counts

def get_routes_by_role(routes_info: List[Dict[str, any]], role_name: str) -> List[Dict[str, any]]:
    """
    Get all routes that require a specific role.
    
    Args:
        routes_info: List of route information dictionaries
        role_name: Name of the role to filter by
        
    Returns:
        List of routes that require the specified role
    """
    matching_routes = []
    for route in routes_info:
        if 'roles' in route and role_name in route['roles']:
            matching_routes.append(route)
    return matching_routes