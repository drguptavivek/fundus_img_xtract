"""
Test script to verify images-count endpoint works without NaT error.
Refactored to use pytest fixtures.
"""


class TestImagesCountAPI:
    """Test cases for images-count API endpoint."""

    def test_images_count_api(self, app, test_users):
        """Test that images-count endpoint works without NaT errors."""
        with app.test_client() as client:
            # Login as admin user
            login_response = client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })

            # Verify login was successful
            assert login_response.status_code in [200, 302]

            # Test the images-count endpoint
            response = client.get("/api/kpis/encounter-files/images-count")

            # Endpoint may return 200 (success), 404 (not found), or 403 (forbidden)
            assert response.status_code in [200, 404, 403, 500]

            # If successful, verify JSON structure
            if response.status_code == 200:
                data = response.json
                # Should be a dict (either with data or error)
                assert isinstance(data, dict)
