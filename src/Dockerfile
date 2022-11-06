FROM python:3.7-slim

RUN python -m pip install --upgrade pip
WORKDIR /code
COPY requirements.txt requirements.txt
RUN python -m pip install -r requirements.txt

RUN apt-get update
RUN apt-get install ffmpeg libsm6 libxext6  -y

COPY . .