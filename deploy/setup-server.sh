#!/usr/bin/env bash
# One-command install of Smart Farm on a fresh Ubuntu server (e.g. AWS Lightsail):
#
#   curl -fsSL https://raw.githubusercontent.com/2002king811/Smart-Farm/claude/festive-turing-ugjviy/deploy/setup-server.sh | bash
#
# Run it again any time to update to the latest code. Without a domain it uses a free
# address based on the server's IP (https://1-2-3-4.sslip.io) with a real HTTPS certificate.
# To use your own domain later:  SITE_DOMAIN=app.example.com bash setup-server.sh
set -euo pipefail

REPO="https://github.com/2002king811/Smart-Farm.git"
BRANCH="${BRANCH:-claude/festive-turing-ugjviy}"
DIR="$HOME/smart-farm"
say() { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }

say "1/6 Memory: adding 2 GB swap (helps small servers build the app)"
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if ! sudo swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  grep -q /swapfile /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

say "2/6 Installing Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo systemctl enable --now docker >/dev/null

say "3/6 Getting the Smart Farm code ($BRANCH)"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch -q origin "$BRANCH" && git -C "$DIR" checkout -q "$BRANCH" && git -C "$DIR" reset -q --hard "origin/$BRANCH"
else
  git clone -q --branch "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR/deploy"

say "4/6 Settings"
IP="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')"
DOMAIN="${SITE_DOMAIN:-$(echo "$IP" | tr . -).sslip.io}"
rand() { openssl rand -hex "$1"; }
if [ ! -f .env ]; then
  DBPW="$(rand 24)"
  cat > .env <<ENV
APP_ENV=production
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_SECRET_KEY=$(rand 40)
DJANGO_ALLOWED_HOSTS=$DOMAIN,localhost,127.0.0.1,api,websocket
SITE_DOMAIN=$DOMAIN
FRONTEND_URL=https://$DOMAIN
CORS_ALLOWED_ORIGINS=https://$DOMAIN
CSRF_TRUSTED_ORIGINS=https://$DOMAIN
POSTGRES_PASSWORD=$DBPW
DATABASE_URL=postgres://smartfarm:$DBPW@db:5432/smartfarm
REDIS_URL=redis://redis:6379/0
USE_REDIS=true
USE_S3=false
# Until an email provider (e.g. AWS SES) is set up, emails are written to the server log.
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=Smart Farm <no-reply@$DOMAIN>
# console = SMS/WhatsApp are logged, not sent. Change to "live" with real keys later.
MESSAGING_ADAPTER=console
WEBHOOK_TOKEN=$(rand 24)
LOG_FORMAT=json
TAG=local
ENV
  if [ "$MEM_MB" -lt 1800 ]; then
    # Small server (1 GB): fewer copies of the web server and one background worker.
    printf 'GUNICORN_WORKERS=2\nCELERY_CONCURRENCY=1\n' >> .env
    echo "Small server ($MEM_MB MB memory): using a lighter setup"
  fi
  chmod 600 .env
  echo "Created deploy/.env for https://$DOMAIN (secrets generated on this server only)"
elif [ -n "${SITE_DOMAIN:-}" ]; then
  OLD="$(grep '^SITE_DOMAIN=' .env | cut -d= -f2)"
  sed -i "s/$OLD/$DOMAIN/g" .env
  echo "Switched settings from $OLD to $DOMAIN"
else
  DOMAIN="$(grep '^SITE_DOMAIN=' .env | cut -d= -f2)"
  echo "Keeping existing settings for https://$DOMAIN"
fi

COMPOSE=(sudo docker compose -f docker-compose.prod.yml -f docker-compose.build.yml)
say "5/6 Building Smart Farm (first time takes 5-15 minutes)"
"${COMPOSE[@]}" build

say "6/6 Starting"
"${COMPOSE[@]}" up -d db redis
"${COMPOSE[@]}" run --rm migrate
"${COMPOSE[@]}" up -d --remove-orphans
for i in $(seq 1 40); do
  if curl -fsS -o /dev/null "https://$DOMAIN/api/health" 2>/dev/null; then
    say "Smart Farm is running: https://$DOMAIN"
    echo "Open that address, then click 'Create an account' to set up your farm."
    echo "Optional demo farm:  cd ~/smart-farm/deploy && ${COMPOSE[*]} exec api python manage.py seed_demo --force"
    exit 0
  fi
  sleep 5
done
echo "Started, but https://$DOMAIN is not answering yet (the HTTPS certificate can take a minute)."
echo "Check:  cd ~/smart-farm/deploy && ${COMPOSE[*]} ps   and   ${COMPOSE[*]} logs --tail 50 caddy api"
