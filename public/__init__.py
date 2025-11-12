"""Public Routes Module

Public-facing routes that don't require authentication.
Currently includes analytics dashboard for system transparency.
"""

from flask import Blueprint

# Create blueprint for public routes
bp = Blueprint('public', __name__, url_prefix='/')

# Import routes to register them with the blueprint
from .analytics import public_analytics, api_analytics_kpi, api_analytics_chart_data

# Register routes with the blueprint
bp.add_url_rule('/analytics', view_func=public_analytics, methods=['GET'])
bp.add_url_rule('/api/analytics/kpi', view_func=api_analytics_kpi, methods=['GET'])
bp.add_url_rule('/api/analytics/chart-data', view_func=api_analytics_chart_data, methods=['GET'])

# Export the blueprint
__all__ = ['bp']