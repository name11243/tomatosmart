"""Explicit, repeatable migration of existing local knowledge into Neo4j.

Run: .venv/bin/python -m backend.migrate_knowledge
Existing Neo4j records win; they are never overwritten by old SQLite rows.
"""
from . import store
from .knowledge_graph import kg


def main():
    store.init()
    store.seed()
    kg.initialize()
    existing = {k['id'] for k in kg.all()}
    imported = []
    for item in store.allof('knowledge'):
        if item['id'] not in existing:
            kg.upsert(item)
            imported.append(item['id'])
    print({'imported': imported, **kg.status()})


if __name__ == '__main__':
    main()
