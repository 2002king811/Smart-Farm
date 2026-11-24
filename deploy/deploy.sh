#!/usr/bin/env bash
# Called by CI: copy the compose files to the server, pull the new images, run migrations as a
# separate release step, then restart. Needs HOST, USER, SSH_KEY and TAG.
set -euo pipefail
KEY=$(mktemp)
trap 'rm -f "$KEY"' EXIT
printf '%s\n' "$SSH_KEY" > "$KEY"
chmod 600 "$KEY"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$USER@$HOST")
"${SSH[@]}" "mkdir -p smart-farm/deploy/backup"
scp -i "$KEY" -o StrictHostKeyChecking=accept-new -r deploy/docker-compose.prod.yml deploy/Caddyfile deploy/backup \
  "$USER@$HOST:smart-farm/deploy/"
"${SSH[@]}" bash -s <<REMOTE
set -euo pipefail
cd smart-farm/deploy
test -f .env || { echo "Missing smart-farm/deploy/.env on the server (copy .env.example and fill it in)"; exit 1; }
sed -i "s/^TAG=.*/TAG=$TAG/" .env
grep -q '^TAG=' .env || echo "TAG=$TAG" >> .env
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml run --rm migrate
docker compose -f docker-compose.prod.yml up -d --remove-orphans
docker image prune -f
for i in \$(seq 1 30); do
  if docker compose -f docker-compose.prod.yml exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" 2>/dev/null; then
    echo "Healthy: $TAG"; exit 0
  fi
  sleep 5
done
echo "Not healthy after deploy"; exit 1
REMOTE
