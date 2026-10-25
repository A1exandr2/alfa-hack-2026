FROM python:3.12.15-alpine3.23 AS dependencies
WORKDIR /build
COPY backend/requirements.txt backend/requirements.lock ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt -c requirements.lock

FROM python:3.12.15-alpine3.23 AS runtime
LABEL io.credit.project="credit" io.credit.component="backend"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN apk add --no-cache poppler-utils tesseract-ocr tesseract-ocr-data-rus tesseract-ocr-data-eng ttf-dejavu \
    && mkdir -p /usr/share/fonts/truetype \
    && ln -s /usr/share/fonts/dejavu /usr/share/fonts/truetype/dejavu
RUN addgroup -S -g 10001 app && adduser -S -D -H -u 10001 -G app app
COPY --from=dependencies /wheels /wheels
COPY backend/requirements.txt backend/requirements.lock ./
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt -c requirements.lock && rm -rf /wheels
COPY --chown=10001:10001 ml ./ml
COPY --chown=10001:10001 backend/app ./app
COPY --chown=10001:10001 backend/migrations ./migrations
COPY --chown=10001:10001 backend/alembic.ini ./alembic.ini
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/ready', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

FROM runtime AS test
COPY --chown=10001:10001 backend/tests ./tests
COPY --chown=10001:10001 backend/pytest.ini ./pytest.ini
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

FROM runtime AS production
