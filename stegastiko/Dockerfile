FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# collectstatic needs a non-default secret key only because DEBUG is off at build time.
RUN DJANGO_DEBUG=False DJANGO_SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput

RUN useradd --create-home app && mkdir -p /data/media && chown -R app /data /app
USER app

EXPOSE 8000
ENTRYPOINT ["sh", "deploy/entrypoint.sh"]
