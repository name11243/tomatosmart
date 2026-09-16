"""Import older SQLite knowledge rows into the native Python graph.

Run: .venv/bin/python -m backend.migrate_knowledge
Existing graph records win; they are never overwritten by old SQLite rows.
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
