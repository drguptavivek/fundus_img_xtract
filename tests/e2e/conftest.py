import pytest
import os

@pytest.fixture(scope="session")
def base_url():
    # Use environment variable or default to local dev server
    return os.getenv("BASE_URL", "http://localhost:5001")

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {
            "width": 1280,
            "height": 720,
        },
    }
