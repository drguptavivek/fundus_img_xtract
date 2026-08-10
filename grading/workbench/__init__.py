"""Unified human-grading workbench domain.

Application code should import commands and queries from ``service`` only.
The remaining modules are implementation details of this domain boundary.

This package deliberately does not re-export the façade: feature model modules
are imported while the root SQLAlchemy registry is still being constructed,
so an eager façade import would create a circular dependency.
"""
