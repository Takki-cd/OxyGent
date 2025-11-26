# OxyGent Annotation (minimal)

This folder contains a minimal skeleton for the annotation platform integrated into OxyGent. It is intentionally small so it can be iterated on in subsequent commits.

How to run (dev):
- Ensure Elasticsearch and Redis are running and reachable (ES at $ELASTICSEARCH_URL, Redis at $REDIS_URL)
- Seed a user into Redis under key user:admin with fields id, username, hashed_password, role
- Start OxyGent as usual; the annotation router can be mounted from oxygent startup or the included router used standalone in a FastAPI app.

This commit adds a starter skeleton. Further PRs will add workflow, assignment, full front-end SPA, and ETL improvements.
