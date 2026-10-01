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

## Notes

- Local development defaults to SQLite.
- Production is intended to use PostgreSQL via `DATABASE_URL`.
