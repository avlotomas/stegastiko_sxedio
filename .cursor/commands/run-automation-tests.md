# Run automation tests

Run the housing scheme test suites from `stegastiko/`.

## Fast suite (pytest, no browser)

```powershell
cd stegastiko
.\scripts\run_tests.ps1 unit
```

Or:

```powershell
cd stegastiko
python -m pytest -m "not e2e"
```

## Browser E2E (Playwright)

One-time browser install:

```powershell
cd stegastiko
pip install -r requirements.txt
python -m playwright install chromium
```

Run E2E only:

```powershell
cd stegastiko
.\scripts\run_tests.ps1 e2e
```

## Everything

```powershell
cd stegastiko
.\scripts\run_tests.ps1 all
```

Golden-path coverage: `tests/test_application_create_http.py` (HTTP) and `e2e/test_application_create_browser.py` (UAT §Β.7.5).
