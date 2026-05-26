FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    ffmpeg libsm6 libxext6 build-essential python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

WORKDIR /code

COPY src/requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY src/ .

# Placeholder key for build-time management commands only — replaced by secret at runtime
ARG DJANGO_SECRET_KEY=build-time-placeholder
ENV DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}

ARG BUILD_DATE=unknown
RUN python manage.py collectstatic --no-input && \
    python manage.py migrate && \
    python manage.py import_data --online

CMD ["gunicorn", "mtgcards.wsgi:application", \
     "--worker-class", "gevent", "-w", "1", "-b", ":8000", \
     "--timeout", "120", \
     "--access-logfile", "-", "--error-logfile", "-"]
