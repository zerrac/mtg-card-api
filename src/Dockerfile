FROM python:3.7-slim

RUN apt-get update && apt-get install -y \
    install \
    ffmpeg \
    libsm6  \
    libxext6  \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --upgrade pip

WORKDIR /code
COPY requirements.txt requirements.txt
RUN python -m pip install -r requirements.txt

COPY . .