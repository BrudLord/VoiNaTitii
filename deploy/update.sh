#!/usr/bin/env bash
set -euo pipefail
cd /home/budimir/VoiNaTitii
git pull --ff-only
.venv/bin/pip install -r requirements.lock
sudo -n -u postgres pg_dump voinatitii | gzip > /home/budimir/voinatitii-before-update.sql.gz
set -a
source /etc/voinatitii.env
set +a
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py structure_catalog
.venv/bin/python manage.py audit_book
.venv/bin/python manage.py collectstatic --noinput
sudo -n mkdir -p /var/www/voinatitii/static
sudo -n cp -R staticfiles/. /var/www/voinatitii/static/
sudo -n systemctl restart voinatitii
