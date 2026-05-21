# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Django REST Framework API that serves Magic: The Gathering card images. It pulls card data from the [Scryfall](https://scryfall.com/docs/api) bulk data API, stores it in PostgreSQL, and exposes endpoints to retrieve the best available card image for a given card name/oracle ID, with scoring logic based on language preference, print era, and image sharpness.

## Repository Layout

- `src/` — Django application (a ll Python code lives here)
- `nginx/` — Nginx reverse-proxy config and Dockerfile
- `claude/` — Dockerfile and config for the Claude Code container
- `docker-compose.yml` — Full stack: PostgreSQL + Django/gunicorn + Nginx + Claude Code

## Environment
This project runs inside Docker. Always execute Python commands via `docker compose exec web python <command>`

## Environment Variables

Copy `.env.sample` to `.env`. Required:

```
DJANGO_SECRET_KEY=<secret>
DB_NAME=<name>
DB_USER=<user>
DB_PASS=<password>
DB_SERVICE=<host>
DB_PORT=<port>
```

Optional: `DEBUG`, `ALLOWED_HOSTS`, `SENTRY_DSN`, `SENTRY_ENV`, `TRAEFIK_BRIDGE`

## Common Commands

All Django management commands must be run from `src/`:

```bash
# Run development server
cd src && python manage.py runserver

# Apply migrations
cd src && python manage.py migrate

# Create migrations after model changes
cd src && python manage.py makemigrations

# Import card data from Scryfall (streaming bulk download)
cd src && python manage.py import_data --online

# Import from a local Scryfall bulk JSON file
cd src && python manage.py import_data --bulk-file /path/to/all-cards.json

# Run tests (tests.py is currently empty — no tests exist yet)
cd src && python manage.py test
```

Docker Compose:

```bash
docker compose up -d          # start full stack
docker compose logs -f web    # follow Django logs
docker compose exec web python manage.py import_data --online
```

## Architecture

### Data model

`Card` → `Face` → `Image` (three-level hierarchy)

- A **Card** represents a specific printed card (unique by `name + edition + collector_number + lang` and by `scryfall_id`). It stores metadata like frame era, language, and `image_status`.
- A **Face** is a named face of a card (`front`/`back` for double-faced cards). The card name is split on `" // "` to produce faces.
- An **Image** stores the URL and optionally a locally downloaded file for a face, in `jpg` or `png` extension. `bluriness` (Laplacian variance via OpenCV) is computed on download. Note: `bluriness` is the intentional spelling used throughout the codebase.

### Card selection logic (`/cards/` endpoint)

`CardApiView.select_best_candidate()` in `src/mtgcards/api/views.py` picks the best (face, image) pair by:
1. Scoring each card via `Card.evaluate_score()` — weights language preference (+200 preferred, +100 English), numeric collector number (+50), frame ≥ 2003 (+50), and edition adjustments (`tle` −100, `sld` −10).
2. Breaking ties by comparing `bluriness` (higher = sharper image).
3. Short-circuiting when the preferred language is found with bluriness above `BLURINESS_HIGH_TRESHOLD` (1000). Note: `bluriness` defaults to 0.0 until the image is downloaded, so this only fires on previously downloaded images.
4. If the selected image has bluriness below `BLURINESS_LOW_TRESHOLD` (150) and preferred language isn't English, it retries in English.

Images are lazily downloaded on first request (`Image.download()`).

### API endpoints

| URL | Description |
|-----|-------------|
| `/` | HTML home page |
| `/cards/` | Card image selector (`CardApiView`) — returns HTTP 302 to best image URL |
| `/api/cards/` | DRF ModelViewSet for `Card` (browse, filter, paginate) |
| `/api/` | DRF browsable API root |

`/cards/` query parameters: `oracle_id` or `face_name` (required), `lang` (default `en`), `image_format` (`jpg`/`png`, default `png`), `side` (`front`/`back`, default `front`), `preferred_set`, `preferred_number`, `debug`.

When `preferred_set` or `preferred_number` is provided, the language filter is skipped entirely and the query filters by set/number instead.

### Data import (`import_data` management command)

Streams the Scryfall bulk JSON file using `ijson` to avoid loading the full file into memory, processes cards in batches of 800, and uses `bulk_create` for efficiency. Skips cards already in the database by `scryfall_id`. After import, handles Scryfall card migrations (card ID changes) by deleting deprecated records.

Double-faced cards (DFCs) have `image_uris: null` at the top level, with per-face `image_uris` nested inside `card_faces[]`. `_get_face_data()` handles this by checking `card[field] is not None` before returning the top-level value, falling through to `card_faces` when it is null. The import also backfills images for existing cards whose faces have no images yet (e.g. cards imported when `image_status` was `"missing"` but later updated by Scryfall).

### Scryfall utility (`src/mtgcards/api/utils/scryfall.py`)

Rate-limited to 50 ms between requests (thread-safe `Throttle` class). Uses a `requests.Session` with retry logic for 429/5xx responses. `_get_face_data()` abstracts single-faced vs. double-faced card JSON structures.

### Blurriness utility (`src/mtgcards/api/utils/images.py`)

Measures image sharpness as the variance of the Laplacian (`cv2.Laplacian`). Higher value = sharper. Thresholds are defined in `src/mtgcards/api/__init__.py`.

### Deployment

Production uses Traefik as an external reverse proxy (configured via Docker labels on the `nginx` service). The `nginx` service serves Django static/media files from named volumes and proxies API requests to the `web` (gunicorn/gevent) container.
