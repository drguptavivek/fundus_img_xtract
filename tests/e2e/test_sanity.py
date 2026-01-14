from playwright.sync_api import Page, expect

def test_home_page_loads(page: Page, base_url: str):
    """
    Basic sanity test to ensure the application homepage loads.
    This test runs locally with 'pytest tests/e2e --headed'.
    """
    page.goto(base_url)
    
    # Check that we didn't get a connection refused or 404
    # Note: On a fresh clone, the server might not be running, so this validates the *test setup*
    # works, even if the assertion fails due to server down (which is expected on local machine before `flask run`)
    
    # We expect the title to contain something specific to your app
    # Adjust this expectation based on your actual homepage title
    expect(page).to_have_title(lambda title: "Login" in title or "Fundus" in title)
