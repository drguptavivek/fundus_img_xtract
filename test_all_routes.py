#!/usr/bin/env python3
"""
Comprehensive Route Testing Script for Fundus Image Manager

This script systematically tests all routes in the Flask application with different
user roles and generates a detailed report of accessibility, status codes,
response times, and authentication requirements.

Usage:
    uv run test_all_routes.py [options]

Options:
    --role ROLE       Test with specific role only (admin, resident, ophthalmologist, etc.)
    --blueprint BP    Test specific blueprint only (admin, analytics, grading, etc.)
    --method METHOD   Test specific HTTP method only (GET, POST, etc.)
    --output FILE     Save report to file (default: route_test_report.txt)
    --verbose         Show detailed output during testing
    --fail-fast       Stop on first failure
    --timeout SECONDS Request timeout in seconds (default: 30)
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app import create_app
from models import Session, User, Role
from auth.security import hash_password


@dataclass
class RouteTestResult:
    """Data class to store individual route test results."""
    route: str
    method: str
    blueprint: str
    roles_required: List[str]
    tested_with_role: Optional[str]
    status_code: int
    response_time_ms: float
    success: bool
    error_message: Optional[str] = None
    redirect_location: Optional[str] = None
    content_type: Optional[str] = None
    response_length: int = 0


@dataclass
class TestSummary:
    """Data class to store test summary statistics."""
    total_routes: int
    successful_tests: int
    failed_tests: int
    public_routes: int
    protected_routes: int
    role_based_failures: Dict[str, int]
    average_response_time_ms: float
    test_duration_seconds: float
    timestamp: str


class RouteTester:
    """Main class for testing Flask application routes."""
    
    def __init__(self, timeout: int = 30):
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret-key",
            WTF_CSRF_ENABLED=False,
            LOGIN_DISABLED=False,
        )
        self.timeout = timeout
        self.test_results: List[RouteTestResult] = []
        self.start_time = None
        self.end_time = None
        
        # Define test users with their credentials (from conftest.py)
        self.test_users = {
            'admin': {'username': 'test_admin', 'password': 'Test@2026'},
            'resident': {'username': 'test_resident', 'password': 'TestPassword123!'},
            'resident2': {'username': 'test_resident2', 'password': 'Test@2026'},
            'testResident': {'username': 'testResident', 'password': 'TestPassword123!'},
            'testresident2': {'username': 'testresident2', 'password': 'TestPassword123!'},
            'testArbitrator': {'username': 'testArbitrator', 'password': 'TestPassword123!'},
        }
        
        # Define routes from flask_routes_analysis.md
        self.routes_data = self._load_routes_data()
    
    def _load_routes_data(self) -> List[Dict[str, Any]]:
        """Load route data from the analysis file."""
        return [
            # Main Application Routes
            {"route": "/", "methods": ["GET"], "blueprint": "main", "roles": ["authenticated"], "public": False},
            {"route": "/login", "methods": ["GET", "POST"], "blueprint": "main", "roles": [], "public": True},
            {"route": "/logout", "methods": ["GET"], "blueprint": "main", "roles": ["authenticated"], "public": False},
            {"route": "/change_password", "methods": ["GET", "POST"], "blueprint": "main", "roles": ["authenticated"], "public": False},
            
            # Account Blueprint
            {"route": "/account/", "methods": ["GET"], "blueprint": "account", "roles": ["authenticated"], "public": False},
            {"route": "/account/change_password", "methods": ["GET", "POST"], "blueprint": "account", "roles": ["authenticated"], "public": False},
            
            # Admin Blueprint
            {"route": "/admin/", "methods": ["GET"], "blueprint": "admin", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/admin/users", "methods": ["GET", "POST"], "blueprint": "admin", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/admin/edit_user/<int:user_id>", "methods": ["GET", "POST"], "blueprint": "admin", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/admin/add_user", "methods": ["GET", "POST"], "blueprint": "admin", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/admin/change_password/<int:user_id>", "methods": ["GET", "POST"], "blueprint": "admin", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/admin/ai_models", "methods": ["GET"], "blueprint": "admin", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/admin/ai_model_edit/<int:model_id>", "methods": ["GET", "POST"], "blueprint": "admin", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/admin/disease_gradings", "methods": ["GET", "POST"], "blueprint": "admin", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/admin/edit_grading_eligibility", "methods": ["GET", "POST"], "blueprint": "admin", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/admin/lookup_edit/<string:lookup_type>", "methods": ["GET", "POST"], "blueprint": "admin", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/admin/lookup_list/<string:lookup_type>", "methods": ["GET"], "blueprint": "admin", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/admin/malicious_uploads", "methods": ["GET"], "blueprint": "admin", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/admin/role_usage", "methods": ["GET"], "blueprint": "admin", "roles": ["admin", "data_manager"], "public": False},
            
            # Analytics Blueprint
            {"route": "/analytics/", "methods": ["GET"], "blueprint": "analytics", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/analytics/view_upload/<string:uuid_str>", "methods": ["GET"], "blueprint": "analytics", "roles": ["admin", "data_manager", "optometrist"], "public": False},
            {"route": "/analytics/direct_files_kpi", "methods": ["GET"], "blueprint": "analytics", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/analytics/encounter_files_kpi", "methods": ["GET"], "blueprint": "analytics", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/analytics/encounter_results", "methods": ["GET"], "blueprint": "analytics", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/analytics/image_results", "methods": ["GET"], "blueprint": "analytics", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/analytics/images_without_tasks", "methods": ["GET"], "blueprint": "analytics", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/analytics/task_details/<int:task_id>", "methods": ["GET"], "blueprint": "analytics", "roles": ["admin", "data_manager", "optometrist"], "public": False},
            {"route": "/analytics/direct_view", "methods": ["GET"], "blueprint": "analytics", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/analytics/encounter_view", "methods": ["GET"], "blueprint": "analytics", "roles": ["admin", "data_manager"], "public": False},
            
            # API Blueprint
            {"route": "/api/hospitals", "methods": ["GET"], "blueprint": "api", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/api/lab_units/<int:hospital_id>", "methods": ["GET"], "blueprint": "api", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/api/ai_models", "methods": ["GET", "POST"], "blueprint": "api", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/api/disease", "methods": ["GET", "POST"], "blueprint": "api", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/api/grading_eligibility", "methods": ["GET", "POST"], "blueprint": "api", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/api/gradings", "methods": ["GET", "POST"], "blueprint": "api", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/api/kpis/direct_files_kpis", "methods": ["GET"], "blueprint": "api", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/api/kpis/encounter_files_kpis", "methods": ["GET"], "blueprint": "api", "roles": ["admin", "data_manager"], "public": False},
            
            # Auth Blueprint
            {"route": "/forgot-password", "methods": ["GET", "POST"], "blueprint": "auth", "roles": [], "public": True},
            {"route": "/reset-password", "methods": ["GET", "POST"], "blueprint": "auth", "roles": [], "public": True},
            
            # Dashboard Blueprint
            {"route": "/dashboard/", "methods": ["GET"], "blueprint": "dashboard", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/dashboard/hospitals", "methods": ["GET"], "blueprint": "dashboard", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/dashboard/hospital/<int:hospital_id>", "methods": ["GET"], "blueprint": "dashboard", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/dashboard/images", "methods": ["GET"], "blueprint": "dashboard", "roles": ["admin", "data_manager"], "public": False},
            
            # Direct Uploads Blueprint
            {"route": "/direct_uploads/", "methods": ["GET"], "blueprint": "direct_uploads", "roles": ["fileUploader", "optometrist", "data_manager", "admin"], "public": False},
            {"route": "/direct_uploads/upload", "methods": ["GET", "POST"], "blueprint": "direct_uploads", "roles": ["fileUploader", "optometrist", "data_manager", "admin"], "public": False},
            {"route": "/direct_uploads/edit_upload/<string:uuid_str>", "methods": ["GET", "POST"], "blueprint": "direct_uploads", "roles": ["fileUploader", "optometrist", "data_manager", "admin"], "public": False},
            {"route": "/direct_uploads/pregraded_upload", "methods": ["GET", "POST"], "blueprint": "direct_uploads", "roles": ["fileUploader", "optometrist", "data_manager", "admin"], "public": False},
            {"route": "/direct_uploads/pregraded_grades/<string:uuid_str>", "methods": ["GET", "POST"], "blueprint": "direct_uploads", "roles": ["fileUploader", "optometrist", "data_manager", "admin"], "public": False},
            {"route": "/direct_uploads/recent_grades", "methods": ["GET"], "blueprint": "direct_uploads", "roles": ["fileUploader", "optometrist", "data_manager", "admin"], "public": False},
            
            # Grading Blueprint
            {"route": "/grading/", "methods": ["GET"], "blueprint": "grading", "roles": ["resident", "ophthalmologist"], "public": False},
            {"route": "/grading/task/<string:task_uuid>/<string:slot_type>", "methods": ["GET"], "blueprint": "grading", "roles": ["resident", "ophthalmologist", "admin"], "public": False},
            {"route": "/grading/task/submit", "methods": ["POST"], "blueprint": "grading", "roles": ["resident", "ophthalmologist", "admin"], "public": False},
            {"route": "/grading/revise/<int:grade_id>", "methods": ["GET"], "blueprint": "grading", "roles": ["resident", "ophthalmologist", "admin"], "public": False},
            {"route": "/grading/intra-task/<string:task_uuid>", "methods": ["GET"], "blueprint": "grading", "roles": ["resident", "ophthalmologist", "admin"], "public": False},
            {"route": "/grading/intra-task/submit", "methods": ["POST"], "blueprint": "grading", "roles": ["resident", "ophthalmologist", "admin"], "public": False},
            {"route": "/grading/grade/<int:disease_id>/<string:role_slot>", "methods": ["GET"], "blueprint": "grading", "roles": ["resident", "ophthalmologist"], "public": False},
            
            # Help Blueprint
            {"route": "/help/", "methods": ["GET"], "blueprint": "help", "roles": ["authenticated"], "public": False},
            
            # Jobs Blueprint
            {"route": "/jobs/", "methods": ["GET"], "blueprint": "jobs", "roles": ["authenticated"], "public": False},
            {"route": "/jobs/upload_processing/<string:job_id>", "methods": ["GET"], "blueprint": "jobs", "roles": ["authenticated"], "public": False},
            
            # Media Blueprint
            {"route": "/media/uploads/<path:filename>", "methods": ["GET"], "blueprint": "media", "roles": ["authenticated"], "public": False},
            
            # Remedio ZIP Uploads Blueprint
            {"route": "/remedio_zip_uploads/", "methods": ["GET"], "blueprint": "remedio_zip_uploads", "roles": ["fileUploader", "optometrist", "data_manager", "admin"], "public": False},
            {"route": "/remedio_zip_uploads/upload", "methods": ["GET", "POST"], "blueprint": "remedio_zip_uploads", "roles": ["fileUploader", "optometrist", "data_manager", "admin"], "public": False},
            
            # Reports Blueprint
            {"route": "/reports/", "methods": ["GET"], "blueprint": "reports", "roles": ["admin", "data_manager"], "public": False},
            
            # Review Blueprint
            {"route": "/review/discrepancy_review", "methods": ["GET", "POST"], "blueprint": "review", "roles": ["admin", "data_manager", "ophthalmologist"], "public": False},
            {"route": "/review/task_review", "methods": ["GET", "POST"], "blueprint": "review", "roles": ["admin", "data_manager", "ophthalmologist"], "public": False},
            
            # Screenings Blueprint
            {"route": "/screenings/", "methods": ["GET"], "blueprint": "screenings", "roles": ["admin", "data_manager", "optometrist"], "public": False},
            {"route": "/screenings/detail/<int:encounter_id>", "methods": ["GET"], "blueprint": "screenings", "roles": ["admin", "data_manager", "optometrist"], "public": False},
            
            # Search Blueprint
            {"route": "/search/", "methods": ["GET"], "blueprint": "search", "roles": ["admin", "data_manager"], "public": False},
            {"route": "/search/images", "methods": ["GET"], "blueprint": "search", "roles": ["admin", "data_manager"], "public": False},
            
            # Tasks Blueprint
            {"route": "/tasks/", "methods": ["GET"], "blueprint": "tasks", "roles": ["admin", "data_manager", "ophthalmologist", "optometrist"], "public": False},
            {"route": "/tasks/pending", "methods": ["GET"], "blueprint": "tasks", "roles": ["admin", "data_manager", "ophthalmologist", "optometrist"], "public": False},
            {"route": "/tasks/viewTaskDetails/<int:task_id>", "methods": ["GET"], "blueprint": "tasks", "roles": ["admin", "data_manager", "optometrist"], "public": False},
            
            # Verify Remedio DR Blueprint
            {"route": "/verify_remedio_dr/list", "methods": ["GET"], "blueprint": "verify_remedio_dr", "roles": ["admin", "optometrist", "data_manager"], "public": False},
            {"route": "/verify_remedio_dr/detail/<int:report_id>", "methods": ["GET"], "blueprint": "verify_remedio_dr", "roles": ["admin", "optometrist", "data_manager"], "public": False},
            {"route": "/verify_remedio_dr/edit/<int:report_id>", "methods": ["GET", "POST"], "blueprint": "verify_remedio_dr", "roles": ["admin", "optometrist", "data_manager"], "public": False},
            {"route": "/verify_remedio_dr/edit/<int:report_id>/verify", "methods": ["POST"], "blueprint": "verify_remedio_dr", "roles": ["admin", "optometrist", "data_manager"], "public": False},
            {"route": "/verify_remedio_dr/edit/<int:report_id>/unverify", "methods": ["POST"], "blueprint": "verify_remedio_dr", "roles": ["admin", "optometrist", "data_manager"], "public": False},
            {"route": "/verify_remedio_dr/edit/<int:report_id>/mark_eye", "methods": ["POST"], "blueprint": "verify_remedio_dr", "roles": ["admin", "optometrist", "data_manager"], "public": False},
            
            # Verify Remedio No-DR Blueprint
            {"route": "/verify_remedio_nodr/list", "methods": ["GET"], "blueprint": "verify_remedio_nodr", "roles": ["admin", "optometrist", "data_manager"], "public": False},
            {"route": "/verify_remedio_nodr/edit/<int:encounter_id>", "methods": ["GET", "POST"], "blueprint": "verify_remedio_nodr", "roles": ["admin", "optometrist", "data_manager"], "public": False},
            {"route": "/verify_remedio_nodr/edit/<int:encounter_id>/verify", "methods": ["POST"], "blueprint": "verify_remedio_nodr", "roles": ["admin", "optometrist", "data_manager"], "public": False},
            {"route": "/verify_remedio_nodr/edit/<int:encounter_id>/unverify", "methods": ["POST"], "blueprint": "verify_remedio_nodr", "roles": ["admin", "optometrist", "data_manager"], "public": False},
            {"route": "/verify_remedio_nodr/edit/<int:encounter_id>/mark_eye", "methods": ["POST"], "blueprint": "verify_remedio_nodr", "roles": ["admin", "optometrist", "data_manager"], "public": False},
            
            # Audit Blueprint
            {"route": "/audit/missing_capture_date", "methods": ["GET"], "blueprint": "audit", "roles": ["admin"], "public": False},
            
            # Docs Blueprint (Public)
            {"route": "/docs/", "methods": ["GET"], "blueprint": "docs", "roles": [], "public": True},
            {"route": "/docs/api.md", "methods": ["GET"], "blueprint": "docs", "roles": [], "public": True},
            {"route": "/docs/api.html", "methods": ["GET"], "blueprint": "docs", "roles": [], "public": True},
            {"route": "/docs/openapi.yaml", "methods": ["GET"], "blueprint": "docs", "roles": [], "public": True},
            
            # Additional routes from app.py
            {"route": "/favicon.ico", "methods": ["GET"], "blueprint": "main", "roles": [], "public": True},
            {"route": "/style_guide", "methods": ["GET"], "blueprint": "main", "roles": [], "public": True},
            {"route": "/test-rate-limit", "methods": ["GET"], "blueprint": "main", "roles": [], "public": True},
            {"route": "/healthz", "methods": ["GET"], "blueprint": "main", "roles": [], "public": True},
            {"route": "/check-email-status", "methods": ["GET"], "blueprint": "main", "roles": [], "public": True},
            {"route": "/email-sse", "methods": ["GET"], "blueprint": "main", "roles": [], "public": True},
            {"route": "/refresh-captcha", "methods": ["GET"], "blueprint": "main", "roles": [], "public": True},
            {"route": "/captcha-audio", "methods": ["GET"], "blueprint": "main", "roles": [], "public": True},
        ]
    
    def _create_test_user(self, username: str, password: str, role_name: str) -> None:
        """Create a test user with the specified role if it doesn't exist."""
        db = Session()
        try:
            # Check if user already exists
            existing_user = db.query(User).filter(User.username == username).first()
            if existing_user:
                return
            
            # Get or create role
            role = db.query(Role).filter(Role.name == role_name).first()
            if not role:
                role = Role(name=role_name)
                db.add(role)
                db.commit()
            
            # Create user
            user = User(
                username=username,
                password_hash=hash_password(password),
                is_active=True,
                full_name=f"Test {role_name.title()}",
                roles=[role]
            )
            db.add(user)
            db.commit()
        finally:
            db.close()
    
    def _login_as_user(self, client, username: str, password: str) -> bool:
        """Login as a specific user."""
        try:
            response = client.post("/login", data={
                "username": username,
                "password": password
            }, follow_redirects=False)
            return response.status_code in [200, 302]
        except Exception as e:
            print(f"Login failed for {username}: {e}")
            return False
    
    def _test_route(self, route_info: Dict[str, Any], role: Optional[str] = None) -> List[RouteTestResult]:
        """Test a specific route with the given role."""
        results = []
        
        if role is None:
            role_str = "no auth"
        else:
            role_str = role
        
        if role is not None:
            print(f"DEBUG: Testing {route_info['route']} with role {role_str}")
        else:
            print(f"DEBUG: Testing {route_info['route']} without authentication")
        
        for method in route_info["methods"]:
            print(f"DEBUG: Testing method {method}")
            # Prepare route URL (replace parameters with test values)
            route_url = route_info["route"]
            if "<int:" in route_url:
                route_url = route_url.replace("<int:user_id>", "1")
                route_url = route_url.replace("<int:model_id>", "1")
                route_url = route_url.replace("<int:disease_id>", "1")
                route_url = route_url.replace("<int:grade_id>", "1")
                route_url = route_url.replace("<int:task_id>", "1")
                route_url = route_url.replace("<int:encounter_id>", "1")
                route_url = route_url.replace("<int:report_id>", "1")
                route_url = route_url.replace("<int:hospital_id>", "1")
            elif "<string:" in route_url:
                route_url = route_url.replace("<string:uuid_str>", "test-uuid-12345")
                route_url = route_url.replace("<string:task_uuid>", "test-task-uuid-12345")
                route_url = route_url.replace("<string:role_slot>", "resident")
                route_url = route_url.replace("<string:lookup_type>", "test")
            elif "<path:" in route_url:
                route_url = route_url.replace("<path:filename>", "test.jpg")
            
            with self.app.test_client() as client:
                # Login if role is specified
                if role and role in self.test_users:
                    user_info = self.test_users[role]
                    # Ensure test user exists
                    self._create_test_user(user_info['username'], user_info['password'], role)
                    # Login
                    if not self._login_as_user(client, user_info['username'], user_info['password']):
                        results.append(RouteTestResult(
                            route=route_info["route"],
                            method=method,
                            blueprint=route_info["blueprint"],
                            roles_required=route_info["roles"],
                            tested_with_role=role,
                            status_code=0,
                            response_time_ms=0,
                            success=False,
                            error_message=f"Failed to login as {role}"
                        ))
                        continue
                
                # Make the request
                start_time = time.time()
                try:
                    if method == "GET":
                        response = client.get(route_url, follow_redirects=False)
                    elif method == "POST":
                        response = client.post(route_url, data={}, follow_redirects=False)
                    else:
                        # Skip unsupported methods
                        continue
                    
                    end_time = time.time()
                    response_time_ms = (end_time - start_time) * 1000
                    
                    # Determine if test was successful
                    success = self._is_test_successful(response, route_info, role)
                    
                    result = RouteTestResult(
                        route=route_info["route"],
                        method=method,
                        blueprint=route_info["blueprint"],
                        roles_required=route_info["roles"],
                        tested_with_role=role,
                        status_code=response.status_code,
                        response_time_ms=response_time_ms,
                        success=success,
                        redirect_location=response.location if response.status_code == 302 else None,
                        content_type=response.content_type,
                        response_length=len(response.data)
                    )
                    
                    results.append(result)
                    
                except Exception as e:
                    end_time = time.time()
                    response_time_ms = (end_time - start_time) * 1000
                    
                    results.append(RouteTestResult(
                        route=route_info["route"],
                        method=method,
                        blueprint=route_info["blueprint"],
                        roles_required=route_info["roles"],
                        tested_with_role=role_str,
                        status_code=0,
                        response_time_ms=response_time_ms,
                        success=False,
                        error_message=str(e)
                    ))
        
        return results
    
    def _is_test_successful(self, response, route_info: Dict[str, Any], role: Optional[str]) -> bool:
        """Determine if a route test was successful based on response and expected behavior."""
        # Public routes should be accessible without authentication
        if route_info["public"]:
            return response.status_code in [200, 302]
        
        # If no role specified (testing without authentication)
        if not role:
            # Should redirect to login for protected routes
            return response.status_code == 302 and ("login" in (response.location or "") or response.status_code == 200)
        
        # If role is specified, check if user has access
        if role in route_info["roles"] or "authenticated" in route_info["roles"]:
            # Should be accessible (200 OK or 302 redirect is acceptable)
            return response.status_code in [200, 302]
        else:
            # Should be denied (redirect or forbidden)
            return response.status_code in [302, 403, 401]
    
    def run_tests(self, role_filter: Optional[str] = None, blueprint_filter: Optional[str] = None, 
                  method_filter: Optional[str] = None, verbose: bool = False, fail_fast: bool = False) -> None:
        """Run all route tests."""
        self.start_time = datetime.now()
        
        if verbose:
            print(f"Starting route testing at {self.start_time}")
            print(f"Testing {len(self.routes_data)} routes...")
        
        # Filter routes if specified
        routes_to_test = self.routes_data
        if blueprint_filter:
            routes_to_test = [r for r in routes_to_test if r["blueprint"] == blueprint_filter]
        if method_filter:
            routes_to_test = [r for r in routes_to_test if method_filter in r["methods"]]
        
        total_tests = 0
        for route_info in routes_to_test:
            total_tests += len(route_info["methods"])
        
        if verbose:
            print(f"Total tests to run: {total_tests}")
        
        # Test each route
        for i, route_info in enumerate(routes_to_test):
            if verbose:
                print(f"\nTesting {i+1}/{len(routes_to_test)}: {route_info['route']} ({route_info['blueprint']})")
        
        # Test with appropriate roles
        roles_to_test = []
        if role_filter:
            if role_filter in route_info["roles"] or (route_info["public"] and role_filter == "anonymous"):
                roles_to_test = [role_filter]
        else:
            # Test with all relevant roles
            if route_info["public"]:
                roles_to_test = ["anonymous"]
            else:
                # Test with one role that should have access
                if route_info["roles"]:
                    if "authenticated" in route_info["roles"]:
                        roles_to_test = ["admin"]  # Use admin as representative authenticated user
                    else:
                        roles_to_test = [route_info["roles"][0]]
        
        if verbose:
            print(f"  Roles to test: {roles_to_test}")
        
        # Test without authentication for protected routes
        if not route_info["public"]:
            results = self._test_route(route_info, role=None)
            if verbose:
                print(f"  No auth test results: {len(results)} results")
            self.test_results.extend(results)
            
            if fail_fast and any(not r.success for r in results):
                print(f"Failed testing {route_info['route']} without authentication")
                return
            
            for role in roles_to_test:
                if role == "anonymous":
                    continue  # Already tested without authentication
                
                results = self._test_route(route_info, role=role)
                if verbose:
                    print(f"  {role} test results: {len(results)} results")
                self.test_results.extend(results)
                
                if verbose:
                    for result in results:
                        status = "✓" if result.success else "✗"
                        print(f"  {status} {result.method} {result.route} as {role} - {result.status_code} ({result.response_time_ms:.1f}ms)")
                
                if fail_fast and any(not r.success for r in results):
                    print(f"Failed testing {route_info['route']} with role {role}")
                    return
        
        # If no roles were tested, still test the route (for public routes)
        if not roles_to_test and route_info["public"]:
            results = self._test_route(route_info, role=None)
            if verbose:
                print(f"  Public route test results: {len(results)} results")
            self.test_results.extend(results)
        
        self.end_time = datetime.now()
        
        if verbose:
            print(f"\nTesting completed at {self.end_time}")
            print(f"Total test results collected: {len(self.test_results)}")
    
    def generate_report(self, output_file: Optional[str] = None) -> TestSummary:
        """Generate a comprehensive test report."""
        if not self.test_results:
            raise ValueError("No test results available. Run tests first.")
        
        # Calculate statistics
        total_routes = len(set(r.route for r in self.test_results))
        successful_tests = sum(1 for r in self.test_results if r.success)
        failed_tests = len(self.test_results) - successful_tests
        public_routes = len(set(r.route for r in self.test_results if "anonymous" in str(r.tested_with_role) or any(route["public"] for route in self.routes_data if route["route"] == r.route)))
        protected_routes = total_routes - public_routes
        
        # Role-based failures
        role_based_failures = defaultdict(int)
        for result in self.test_results:
            if not result.success and result.tested_with_role:
                role_based_failures[result.tested_with_role] += 1
        
        # Average response time
        avg_response_time = sum(r.response_time_ms for r in self.test_results) / len(self.test_results)
        
        # Test duration
        test_duration = (self.end_time - self.start_time).total_seconds()
        
        summary = TestSummary(
            total_routes=total_routes,
            successful_tests=successful_tests,
            failed_tests=failed_tests,
            public_routes=public_routes,
            protected_routes=protected_routes,
            role_based_failures=dict(role_based_failures),
            average_response_time_ms=avg_response_time,
            test_duration_seconds=test_duration,
            timestamp=self.start_time.isoformat()
        )
        
        # Generate report content
        report_lines = [
            "=" * 80,
            "FLASK APPLICATION ROUTE TEST REPORT",
            "=" * 80,
            f"Generated: {self.start_time}",
            f"Test Duration: {test_duration:.2f} seconds",
            "",
            "SUMMARY",
            "-" * 40,
            f"Total Routes Tested: {total_routes}",
            f"Total Tests Run: {len(self.test_results)}",
            f"Successful Tests: {successful_tests}",
            f"Failed Tests: {failed_tests}",
            f"Success Rate: {(successful_tests / len(self.test_results) * 100):.1f}%",
            f"Public Routes: {public_routes}",
            f"Protected Routes: {protected_routes}",
            f"Average Response Time: {avg_response_time:.1f}ms",
            "",
            "ROLE-BASED FAILURES",
            "-" * 40,
        ]
        
        for role, count in role_based_failures.items():
            report_lines.append(f"{role}: {count} failures")
        
        report_lines.extend([
            "",
            "DETAILED RESULTS",
            "-" * 40,
        ])
        
        # Group results by blueprint
        by_blueprint = defaultdict(list)
        for result in self.test_results:
            by_blueprint[result.blueprint].append(result)
        
        for blueprint, results in sorted(by_blueprint.items()):
            report_lines.extend([
                "",
                f"BLUEPRINT: {blueprint.upper()}",
                "-" * 40,
            ])
            
            for result in results:
                status = "✓" if result.success else "✗"
                role_info = f" (as {result.tested_with_role})" if result.tested_with_role else " (no auth)"
                error_info = f" - {result.error_message}" if result.error_message else ""
                redirect_info = f" -> {result.redirect_location}" if result.redirect_location else ""
                
                report_lines.append(
                    f"{status} {result.method} {result.route}{role_info} - "
                    f"{result.status_code} ({result.response_time_ms:.1f}ms)"
                    f"{redirect_info}{error_info}"
                )
        
        report_content = "\n".join(report_lines)
        
        # Output report
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report_content)
            print(f"Report saved to: {output_file}")
        else:
            print(report_content)
        
        return summary


def main():
    """Main function to run the route testing script."""
    parser = argparse.ArgumentParser(description="Test all Flask application routes")
    parser.add_argument("--role", help="Test with specific role only")
    parser.add_argument("--blueprint", help="Test specific blueprint only")
    parser.add_argument("--method", help="Test specific HTTP method only")
    parser.add_argument("--output", default="route_test_report.txt", help="Save report to file")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first failure")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds")
    
    args = parser.parse_args()
    
    # Create and run tester
    tester = RouteTester(timeout=args.timeout)
    tester.run_tests(
        role_filter=args.role,
        blueprint_filter=args.blueprint,
        method_filter=args.method,
        verbose=args.verbose,
        fail_fast=args.fail_fast
    )
    
    # Generate report
    summary = tester.generate_report(output_file=args.output)
    
    # Exit with appropriate code
    if summary.failed_tests > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()