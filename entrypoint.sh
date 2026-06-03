#!/bin/sh
set -e
python manage.py collectstatic --no-input
python manage.py migrate --no-input
if [ -n "$CLOUDFLARE_R2_ACCOUNT_ID" ]; then
    python manage.py seed_popular_cards --langs fr
    python manage.py seed_bluriness --langs fr
fi
exec gunicorn mtgcards.wsgi:application \
    --worker-class gevent \
    -w 4 \
    -b :8000 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
