# Test Scripts

This folder contains test scripts for verifying the functionality of the Fundus Image Manager.

## Test Files

- `test_locking.py` - Tests the locking mechanism for images in the dual grading system
- `test_matching.py` - Tests the matching process for dual grading

## Running Tests

To run the tests, use the following command from the project root directory:

```bash
uv run python3 tests/test_locking.py
uv run python3 tests/test_matching.py
```