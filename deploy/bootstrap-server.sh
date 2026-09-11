#!/usr/bin/env bash
set -euo pipefail
cd /home/budimir/VoiNaTitii
if ! sudo -n -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='budimir'" | grep -q 1; then
    sudo -n -u postgres createuser budimir
fi
if ! sudo -n -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='voinatitii'" | grep -q 1; then
    sudo -n -u postgres createdb -O budimir voinatitii
fi
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/pip install -r requirements.lock
if ! sudo -n test -f /etc/voinatitii.env; then
    sudo -n python3 - <<'PY'
import secrets
from pathlib import Path
path = Path('/etc/voinatitii.env')
path.write_text('SECRET_KEY=' + secrets.token_urlsafe(60) + '\nDEBUG=0\nDB_NAME=voinatitii\nDB_USER=budimir\nDB_HOST=\nALLOWED_HOSTS=voinatitii.84.201.155.77.sslip.io,localhost,127.0.0.1\nHTTPS=1\n')
path.chmod(0o640)
PY
    sudo -n chown root:budimir /etc/voinatitii.env
fi
set -a
source /etc/voinatitii.env
set +a
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py bootstrap
.venv/bin/python manage.py collectstatic --noinput
sudo -n mkdir -p /var/www/voinatitii/static
sudo -n cp -R staticfiles/. /var/www/voinatitii/static/
sudo -n cp deploy/voinatitii.service /etc/systemd/system/voinatitii.service
if [ ! -f /etc/letsencrypt/live/voinatitii.84.201.155.77.sslip.io/fullchain.pem ]; then
    sudo -n cp deploy/nginx.conf /etc/nginx/sites-available/voinatitii
    sudo -n ln -sf /etc/nginx/sites-available/voinatitii /etc/nginx/sites-enabled/voinatitii
    sudo -n nginx -t
    sudo -n systemctl reload nginx
    sudo -n certbot --nginx -d voinatitii.84.201.155.77.sslip.io --non-interactive --agree-tos --register-unsafely-without-email --redirect
fi
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now voinatitii
sudo -n systemctl restart voinatitii
.venv/bin/python manage.py check --deploy
sudo -n systemctl is-active voinatitii nginx postgresql
