from playwright.sync_api import sync_playwright

STORAGE_PATH = "backend/app/ingestion/ig_session.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()

    page = context.new_page()
    page.goto("https://www.instagram.com/accounts/login/")

    print("Please log in manually in the opened browser.")
    print("After login, press ENTER here.")

    input()

    context.storage_state(path=STORAGE_PATH)
    print("Session saved.")

    browser.close()
