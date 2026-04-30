"""Celery task root package.

Task modules are imported by ``celery_tasks.tasks`` according to the configured
worker profile. Keep this package import-light so Celery Beat can start with its
minimal dependency set.
"""
