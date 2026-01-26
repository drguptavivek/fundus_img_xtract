"""
Celery worker entrypoint.

This module must not import Flask app or blueprints.
"""

from utils.env_loader import load_environment
from celery_app import celery_app


def main() -> None:
    load_environment()
    celery_app.start()


if __name__ == "__main__":
    main()
