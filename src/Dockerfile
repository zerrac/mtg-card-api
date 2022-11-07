FROM python:3.7-slim AS build-base

RUN apt-get update
RUN apt-get install ffmpeg libsm6 libxext6  -y
RUN python -m pip install --upgrade pip

FROM build-base AS build

WORKDIR /code
COPY requirements.txt requirements.txt
RUN python -m pip install -r requirements.txt


COPY . .