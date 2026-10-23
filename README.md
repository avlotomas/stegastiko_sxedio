# Διαχείριση Στεγαστικού Σχεδίου · Επαρχία Λευκωσίας

Το αποθετήριο περιέχει την εφαρμογή Django **`stegastiko/`** (η ενεργή εφαρμογή), τις απαιτήσεις και το υλικό αναφοράς από το οποίο προέκυψε.

## Δομή

| Διαδρομή | Περιεχόμενο |
|---|---|
| `stegastiko/` | Η εφαρμογή (Django 5.2). Οδηγίες εγκατάστασης, εκκίνησης και δοκιμών: [`stegastiko/README.md`](stegastiko/README.md). |
| `run-app.bat` | Εκκίνηση του τοπικού εξυπηρετητή στα Windows (`http://127.0.0.1:8000/`). |
| `requirements/` | Προδιαγραφές λογισμικού, ερωτήσεις προς λειτουργούς και παράδειγμα οντοτήτων. |
| `requirements_*_extract.txt`, `conversation*.md` | Κείμενο που εξήχθη από τα αρχικά έγγραφα και ιστορικό συζητήσεων ανάλυσης. |
| `Στεγαστικό_Λευκωσίας_Codex (1)/` | Παλαιό πρωτότυπο (`app.py`, χωρίς Django), μόνο για αναφορά. Δεν χρησιμοποιείται από την εφαρμογή. |

## Γρήγορη εκκίνηση

```bash
cd stegastiko
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Δοκιμές

```bash
cd stegastiko
python -m pytest tests
```

Οι δοκιμές περιήγησης (`stegastiko/e2e`) απαιτούν Playwright: `python -m playwright install chromium` και κατόπιν `python -m pytest e2e`.
