FROM python:3.13-alpine AS base

WORKDIR /app/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apk --no-cache add --virtual='.build-deps' 'gcc' 'musl-dev' 'libffi-dev'


####

FROM base as requirements-builder

WORKDIR /build/

RUN pip --no-cache-dir install poetry poetry-plugin-export

COPY pyproject.toml poetry.lock /build/

RUN poetry export --without-hashes -f requirements.txt -o requirements.txt


####

FROM base

COPY --from=requirements-builder /build/requirements.txt /app/requirements.txt

ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

RUN pip install --no-cache-dir -r requirements.txt

RUN adduser --disabled-password 'user'

USER user

COPY ./app /app/app

#HEALTHCHECK CMD curl -fs "http://localhost:$PORT/healthcheck" || exit 1

ENTRYPOINT ["/bin/sh", "-c", "exec uvicorn --host '0.0.0.0' --port \"$PORT\" 'app.app:app' \"$@\""]
