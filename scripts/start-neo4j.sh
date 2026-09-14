#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
.venv/bin/python - <<'PY'
from pathlib import Path
import secrets
p=Path('.env')
if not p.exists():
    p.write_text('NEO4J_URI=bolt://127.0.0.1:7689\nNEO4J_USER=neo4j\nNEO4J_PASSWORD='+secrets.token_urlsafe(24)+'\nNEO4J_DATABASE=neo4j\nNEO4J_SCOPE=hydroponic\n')
    p.chmod(0o600)
PY
docker compose -f compose.neo4j.yml up -d
.venv/bin/python - <<'PY'
import time
from backend.knowledge_graph import kg
from backend.migrate_knowledge import main
from neo4j.exceptions import Neo4jError, DriverError
for attempt in range(30):
    try:
        kg.initialize()
        break
    except (Neo4jError, DriverError):
        if attempt==29:raise
        time.sleep(1)
main()
PY
