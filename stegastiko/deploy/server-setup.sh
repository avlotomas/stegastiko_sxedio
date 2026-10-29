#!/bin/sh
# First-time setup on a fresh server (Docker already installed). Safe to re-run.
#   - creates .env for <public-ip>.sslip.io with random secrets (kept if it already exists)
#   - builds and starts the stack
#   - replaces the default admin/1234 password with a random one, saved to ~/admin-password.txt
#     (RESET_ADMIN_PASSWORD=1 sh deploy/server-setup.sh replaces it whatever it currently is)
set -e
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    ip=$(curl -fsS https://checkip.amazonaws.com)
    host="$(echo "$ip" | tr . -).sslip.io"
    umask 077
    cat > .env <<EOF
SITE_ADDRESS=$host
DJANGO_ALLOWED_HOSTS=$host
DJANGO_CSRF_TRUSTED_ORIGINS=https://$host
DJANGO_SECRET_KEY=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 16)
DJANGO_HTTPS=True
EOF
    echo "Created .env for $host"
fi

docker compose up -d --build

echo "Waiting for migrations..."
tries=0
until docker compose exec -T web python manage.py migrate --check >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "$tries" -gt 60 ]; then
        echo "web did not become ready; check: docker compose logs web" >&2
        exit 1
    fi
    sleep 3
done

password=$(openssl rand -base64 12)
changed=$(docker compose exec -T -e NEW_PASSWORD="$password" -e RESET="${RESET_ADMIN_PASSWORD:-0}" \
    web python manage.py shell --no-imports -c "
import os
from django.contrib.auth import get_user_model
user = get_user_model().objects.filter(username='admin').first()
if user and (os.environ['RESET'] == '1' or user.check_password('1234')):
    user.set_password(os.environ['NEW_PASSWORD'])
    user.save()
    print('password-changed')
")
# The shell may print other lines (e.g. auto-import notices); look for the marker only.
if echo "$changed" | grep -qx 'password-changed'; then
    (umask 077 && echo "$password" > "$HOME/admin-password.txt")
    echo "Default admin password replaced; see ~/admin-password.txt"
fi

. ./.env
echo "Site: https://$SITE_ADDRESS/"
