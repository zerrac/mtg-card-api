#!/bin/sh
# Import the latest Scryfall bulk data, then drop nginx's cached redirects
# so they don't point to images selected from the previous data.
# Usage: ./import.sh [extra import_data args]   (defaults to --online)
set -e
cd "$(dirname "$0")"

if [ $# -eq 0 ]; then
    set -- --online
fi

docker compose exec -T web python manage.py import_data "$@"

docker compose exec -T nginx sh -c 'rm -rf /var/cache/nginx/cards/*'
docker compose restart nginx
echo "nginx card cache cleared."
