# Deploy σε AWS (ένας server με Docker)

Η εφαρμογή τρέχει σε **ένα** μηχάνημα (AWS Lightsail ή EC2) με τρία containers:

| Container | Ρόλος |
|---|---|
| `web` | Django + gunicorn (στατικά αρχεία μέσω WhiteNoise) |
| `db` | PostgreSQL 17 (volume `pgdata`) |
| `caddy` | HTTPS (αυτόματο πιστοποιητικό Let's Encrypt) → `web` |

Τα ανεβασμένα αρχεία (πρότυπα συμφωνιών) μένουν στο volume `media`. Τα συνημμένα των
υποθέσεων αποθηκεύονται μέσα στη βάση.

> **Προσωπικά δεδομένα (Ν.125(Ι)/2018, Ενότ. 6–7 του Σχεδίου):** χρησιμοποίησε region της ΕΕ
> (`eu-central-1` Frankfurt). Πριν ανεβούν πραγματικά δεδομένα αιτητών, χρειάζεται έγκριση
> από ΥΠΕΣ / Τμήμα Υπηρεσιών Πληροφορικής για φιλοξενία σε δημόσιο cloud.

> **AWS Free plan:** όταν λήξει (ημερομηνία ή εξάντληση credits) ο λογαριασμός κλείνει και τα
> δεδομένα διαγράφονται μετά από 90 ημέρες, εκτός αν γίνει αναβάθμιση σε Paid plan. Κράτα
> backups (βήμα 7).

---

## 1. Δημιουργία server (Lightsail)

1. AWS Console → **Lightsail** → *Create instance*.
2. Region: **Frankfurt (eu-central-1)**.
3. Platform **Linux/Unix** → Blueprint **OS Only → Ubuntu 24.04 LTS**.
4. Plan: **2 GB RAM** (~12 $/μήνα). Το 1 GB είναι οριακό για Postgres + 3 workers.
5. Όνομα: `stegastiko` → *Create instance*.
6. **Networking** του instance:
   - *Create static IP* και σύνδεσέ την στο instance (π.χ. `3.120.45.67`).
   - IPv4 Firewall: πρόσθεσε **HTTPS (443)**· τα SSH (22) και HTTP (80) υπάρχουν ήδη.

> Εναλλακτικά EC2: `t3.small`, Ubuntu 24.04, Security Group με 22/80/443 και Elastic IP.

## 2. Εγκατάσταση Docker στον server

Σύνδεση με το κουμπί **Connect using SSH** του Lightsail (ή `ssh ubuntu@<IP>`):

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit
```

Ξανασυνδέσου ώστε να ισχύσει η ομάδα `docker`.

## 3. Αντιγραφή του κώδικα

Με git (αν το repo είναι σε GitHub/GitLab):

```bash
git clone <repo-url> nantia
cd nantia/stegastiko
```

Ή από τα Windows, χωρίς git server (PowerShell, από το `C:\temp\nantia`):

```powershell
git archive --format=tar.gz -o stegastiko.tar.gz HEAD stegastiko
scp stegastiko.tar.gz ubuntu@<IP>:~
# στον server: mkdir nantia && tar -xzf stegastiko.tar.gz -C nantia && cd nantia/stegastiko
```

(Για Lightsail, το SSH key κατεβαίνει από *Account → SSH keys*.)

> **Συντόμευση για τα βήματα 4–5:** `sh deploy/server-setup.sh` δημιουργεί `.env` για
> `<IP>.sslip.io` με τυχαία secrets, ξεκινά το stack και αντικαθιστά τον κωδικό `admin`/`1234`
> με τυχαίο (στο `~/admin-password.txt`). Τρέξ' το αφού συνδεθεί η static IP.

## 4. Ρυθμίσεις (`.env`)

```bash
cp deploy/env.production.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # → DJANGO_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # → POSTGRES_PASSWORD
nano .env
```

Χωρίς δικό σου domain, χρησιμοποίησε το **sslip.io** με τη static IP (`3.120.45.67` →
`3-120-45-67.sslip.io`) στα `SITE_ADDRESS`, `DJANGO_ALLOWED_HOSTS` και
`DJANGO_CSRF_TRUSTED_ORIGINS` (με `https://`). Με δικό domain, δημιούργησε A record προς την IP
και βάλε το domain στη θέση του.

## 5. Εκκίνηση

```bash
docker compose up -d --build
docker compose logs -f web      # Ctrl+C για έξοδο
```

Η πρώτη εκκίνηση τρέχει τα migrations και δημιουργεί τον χρήστη **`admin` / `1234`**.
**Άλλαξέ τον αμέσως:**

```bash
docker compose exec web python manage.py changepassword admin
```

Άνοιξε `https://3-120-45-67.sslip.io/`.

## 6. Μεταφορά των υπαρχόντων δεδομένων (προαιρετικά)

Στα Windows, από το `stegastiko/` (εξαγωγή από την τοπική SQLite):

```powershell
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission -e admin.logentry -e sessions --indent 1 -o data.json
scp data.json ubuntu@<IP>:~/nantia/stegastiko/
scp -r media ubuntu@<IP>:~/nantia/stegastiko/media-upload
```

Στον server (κάνει πρώτα backup της τωρινής βάσης στο `~/backup-before-import-*.sql.gz`,
μετά `flush` + `loaddata` και αντιγραφή των media):

```bash
sh deploy/import-data.sh data.json media.tar.gz   # media: tar -czf media.tar.gz -C media .
```

Αν το `loaddata` αποτύχει με «ContentType matching query does not exist», η τοπική βάση έχει
δικαιώματα χρηστών για μοντέλα που δεν υπάρχουν πια· τρέξε τοπικά
`python manage.py remove_stale_contenttypes` και ξανακάνε την εξαγωγή.

Μετά το `loaddata` ισχύουν οι κωδικοί χρηστών της τοπικής βάσης.

## 7. Backup / restore

```bash
# backup βάσης + αρχείων
docker compose exec -T db pg_dump -U stegastiko stegastiko | gzip > backup-$(date +%F).sql.gz
docker compose cp web:/data/media ./media-backup-$(date +%F)

# restore βάσης
gunzip -c backup-YYYY-MM-DD.sql.gz | docker compose exec -T db psql -U stegastiko stegastiko
```

Κατέβασε τα backups και τοπικά (`scp ubuntu@<IP>:~/nantia/stegastiko/backup-*.sql.gz .`).
Στο Lightsail μπορείς επίσης να ενεργοποιήσεις **Automatic snapshots** στο instance.

## 8. Ενημέρωση σε νέα έκδοση

```bash
git pull                        # ή νέο tar.gz όπως στο βήμα 3
docker compose up -d --build    # τα migrations τρέχουν αυτόματα
```

## 9. Αυτόματο deploy σε κάθε push στο `main` (GitHub Actions)

Το [.github/workflows/deploy.yml](../../.github/workflows/deploy.yml), σε κάθε push στο `main`:

1. τρέχει τις δοκιμές (`pytest tests`)· αν αποτύχουν, **δεν** γίνεται deploy,
2. συνδέεται με SSH στον server, που εκτελεί **μόνο** την εντολή deploy:
   `git checkout origin/main` → backup βάσης (`~/backups/pre-deploy-*.sql.gz`, κρατά τα 10
   τελευταία) → `docker compose up -d --build` → τα migrations εφαρμόζονται αυτόματα
   ([deploy.sh](deploy.sh)),
3. ελέγχει ότι το site απαντά.

Χειροκίνητη εκτέλεση: GitHub → *Actions* → *Deploy* → *Run workflow*.

### Ρύθμιση (μία φορά)

**α. Κλειδί SSH** (τοπικά, χωρίς passphrase):

```bash
ssh-keygen -t ed25519 -N "" -C github-deploy -f github-deploy
```

**β. Δημόσιο κλειδί στον server, περιορισμένο στην εντολή deploy** — στον server:

```bash
echo 'command="cd ~/nantia && git fetch -q origin main && git checkout -q -f -B main origin/main && sh stegastiko/deploy/deploy.sh",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty <περιεχόμενο του github-deploy.pub>' >> ~/.ssh/authorized_keys
```

Με το `command="…"`, ακόμη κι αν διαρρεύσει το κλειδί, το μόνο που επιτρέπει είναι ένα deploy
του `origin/main`.

**γ. Ιδιωτικό κλειδί ως secret στο GitHub** — από τον φάκελο του repo:

```bash
gh secret set DEPLOY_SSH_KEY < github-deploy
```

(ή GitHub → *Settings → Secrets and variables → Actions → New repository secret*). Μετά σβήσε
τα τοπικά αρχεία `github-deploy` / `github-deploy.pub`.

Αν αλλάξει η IP ή το domain, ενημέρωσε τα `DEPLOY_HOST` / `SITE_URL` στην αρχή του workflow.

### Αν αποτύχει migration

Το deploy σταματά με σφάλμα στο GitHub Actions και τυπώνει την εντολή επαναφοράς του backup που
πάρθηκε λίγο πριν. Διόρθωσε τη migration, κάνε push ξανά· ή επανάφερε τη βάση με:

```bash
gunzip -c ~/backups/pre-deploy-<ημερομηνία>.sql.gz | docker compose exec -T db psql -U stegastiko stegastiko
```

(για καθαρή επαναφορά, πρώτα `docker compose exec -T db psql -U stegastiko -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" stegastiko`).

## Χρήσιμες εντολές

```bash
docker compose ps
docker compose logs --tail 100 web
docker compose exec web python manage.py createsuperuser
docker compose restart web
```

Email: ο SMTP ρυθμίζεται από την οθόνη **Ρυθμίσεις** της εφαρμογής (π.χ. Amazon SES SMTP ή
τον SMTP του ΥΠΕΣ).
