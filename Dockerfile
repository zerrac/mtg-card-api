FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    ffmpeg libsm6 libxext6 build-essential python3-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

RUN pip install --upgrade pip

WORKDIR /code

COPY src/requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY src/ .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
