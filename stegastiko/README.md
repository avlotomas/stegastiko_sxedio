# Housing Scheme App (`stegastiko`)

Milestone 1 foundation for the Housing Scheme system (Django).

## Local setup

1. Install Python 3.13+.
2. Install dependencies:
   - `python -m pip install -r requirements.txt`
3. Apply migrations:
   - `python manage.py migrate`
4. Sign in to the application at `/login/` (or Django admin at `/admin/`) with username `admin` and password `1234` (created on first migrate if no `admin` user exists). Change the password immediately in admin.
5. Run development server:
   - `python manage.py runserver`
   - Or from the repo root, double-click `run-app.bat`.

## Tests

- `python -m pytest`

## Remote demo (different network)

**One command (local + public URL, same terminal):** `.\scripts\start-local-and-public.ps1`  
Or in Cursor: slash command **start-local-and-public-demo**. The green **PUBLIC URL** banner appears in that window.

Manual steps:

1. Start Django: `python manage.py runserver 127.0.0.1:8000`
2. In another terminal: `.\scripts\start-remote-demo.ps1`
3. Copy the printed `https://….lhr.life` URL (new each time you start the tunnel). The script updates `.env` for that hostname.
4. Restart `runserver` after the tunnel prints the URL if Django was already running.

Change the default `admin` password before exposing the app.

## Notes

- Local development defaults to SQLite.
- Production is intended to use PostgreSQL via `DATABASE_URL`.
