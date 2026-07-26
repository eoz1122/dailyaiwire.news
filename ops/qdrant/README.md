# DailyAIWire Qdrant

DailyAIWire uses a dedicated Qdrant service so Gunicorn and the fetcher can
share vector collections without contending for an embedded database lock.

The service binds only to localhost on ports `6433` and `6434`. Its API key is
stored outside the repository in `/home/dailyai/.secrets/dailyaiwire-qdrant.env`.

Start or update the service from the application directory:

```bash
docker compose \
  --env-file /home/dailyai/.secrets/dailyaiwire-qdrant.env \
  -f ops/qdrant/docker-compose.yml up -d
```

Rollback by removing `QDRANT_URL` and `QDRANT_API_KEY` from the application
environment, restarting the web and fetcher processes, and stopping this
container. The application then returns to its embedded Qdrant fallback.
