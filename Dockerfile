
FROM python:3.9

RUN pip install pipenv

WORKDIR /usr/src/flask_app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install nltk && python -m nltk.downloader punkt

ENV PYTHONUNBUFFERED 1
