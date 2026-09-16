"""Pure-Python tomato and education knowledge graph.

The primary store is an in-memory adjacency graph. Built-in course content is
defined in Python, while teacher-created records and edits are persisted to a
local JSON file. No Neo4j driver, remote graph service, or Docker fallback is
used.
"""
from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import threading
from collections import defaultdict, deque
from hashlib import sha256
from pathlib import Path
from typing import Any

from .knowledge_content import KNOWLEDGE_DOCUMENTS


class AdjacencyGraph:
    """Small directed property graph with indexes and traversal helpers."""

    def __init__(self):
        self.entities: dict[str, dict[str, Any]] = {}
        self.relations: dict[str, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
        self.entity_index: dict[str, set[str]] = defaultdict(set)
        self.relation_index: dict[str, set[tuple[str, str]]] = defaultdict(set)

    def add_entity(self, entity_id: str, entity_type: str, properties: dict | None = None):
        previous = self.entities.get(entity_id)
        if previous and previous["type"] != entity_type:
            self.entity_index[previous["type"]].discard(entity_id)
        self.entities[entity_id] = {
            "id": entity_id, "type": entity_type,
            "properties": copy.deepcopy(properties or {}),
        }
        self.entity_index[entity_type].add(entity_id)

    def add_relation(self, source_id: str, target_id: str, relation_type: str,
                     properties: dict | None = None):
        props = copy.deepcopy(properties or {})
        signature = (target_id, relation_type, json.dumps(props, ensure_ascii=False, sort_keys=True))
        existing = {
            (target, kind, json.dumps(value, ensure_ascii=False, sort_keys=True))
            for target, kind, value in self.relations[source_id]
        }
        if signature not in existing:
            self.relations[source_id].append((target_id, relation_type, props))
            self.relation_index[relation_type].add((source_id, target_id))

    def get_entity(self, entity_id: str):
        entity = self.entities.get(entity_id)
        return copy.deepcopy(entity) if entity else None

    def get_neighbors(self, entity_id: str, relation_type: str | None = None):
        output = []
        for target_id, kind, props in self.relations.get(entity_id, []):
            if relation_type and kind != relation_type:
                continue
            target = copy.deepcopy(self.entities.get(target_id, {
                "id": target_id, "type": "unknown", "properties": {"name": target_id}
            }))
            target["relation"] = kind
            target["relation_props"] = copy.deepcopy(props)
            output.append(target)
        return output

    def find_path(self, start_id: str, end_id: str, max_depth: int = 4):
        if start_id == end_id:
            return [start_id]
        queue = deque([(start_id, [start_id])])
        visited = {start_id}
        while queue:
            current, path = queue.popleft()
            if len(path) - 1 >= max_depth:
                continue
            for target_id, _, _ in self.relations.get(current, []):
                if target_id == end_id:
                    return path + [target_id]
                if target_id not in visited:
                    visited.add(target_id)
                    queue.append((target_id, path + [target_id]))
        return None

    def search_by_type(self, entity_type: str):
        return [copy.deepcopy(self.entities[key]) for key in sorted(self.entity_index.get(entity_type, set()))]

    def search_by_property(self, property_name: str, property_value: Any):
        return [copy.deepcopy(entity) for entity in self.entities.values()
                if entity["properties"].get(property_name) == property_value]

    def get_subgraph(self, center_id: str, depth: int = 1):
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        queue = deque([(center_id, 0)])
        visited = set()
        while queue:
            current, current_depth = queue.popleft()
            if current in visited or current_depth > depth:
                continue
            visited.add(current)
            if current in self.entities:
                nodes[current] = copy.deepcopy(self.entities[current])
            if current_depth == depth:
                continue
            for target, kind, props in self.relations.get(current, []):
                edges.append({"source": current, "target": target, "type": kind,
                              "properties": copy.deepcopy(props)})
                queue.append((target, current_depth + 1))
        return {"nodes": list(nodes.values()), "edges": edges}

    def get_statistics(self):
        return {
            "total_entities": len(self.entities),
            "total_relations": sum(len(values) for values in self.relations.values()),
            "entity_types": {key: len(value) for key, value in self.entity_index.items()},
            "relation_types": {key: len(value) for key, value in self.relation_index.items()},
        }

    def to_json(self):
        edges = []
        for source, relations in self.relations.items():
            for target, kind, props in relations:
                edges.append({"source": source, "target": target, "type": kind,
                              "properties": copy.deepcopy(props)})
        return json.dumps({"entities": list(self.entities.values()), "edges": edges},
                          ensure_ascii=False, indent=2)


class KnowledgeGraph:
    """Thread-safe domain service backed by an adjacency graph and local JSON."""

    VERSION = 1
    ALIASES = {
        "黄叶": "叶片发黄", "叶子黄": "叶片发黄", "水位": "液位",
        "酸碱度": "ph", "电导率": "ec", "拍照": "相机", "用电": "水电安全",
        "卫生": "健康教育", "洗手": "手卫生", "番茄成熟": "结果期 成熟",
    }
    GENERIC_TAGS = {"番茄", "水培", "健康教育", "劳动", "观察", "生长周期"}

    def __init__(self, storage_path: str | Path | None = None):
        real_only = os.getenv("HYDRO_REAL_ONLY", "1") == "1"
        data_root = Path(os.getenv(
            "HYDRO_DATA_DIR", Path(__file__).parent / ("real-data" if real_only else "data")
        ))
        self.storage_path = Path(storage_path or os.getenv(
            "HYDRO_KNOWLEDGE_FILE", data_root / "knowledge_graph.json"
        ))
        self.lock = threading.RLock()
        self.documents: dict[str, dict] = {}
        self.engine = AdjacencyGraph()
        self.document_nodes: dict[str, set[str]] = {}
        self.document_edges: dict[str, set[tuple[str, str, str]]] = {}
        self.initialized = False

    @staticmethod
    def _key(kind: str, value: str):
        return f"{kind}:{sha256(value.encode('utf-8')).hexdigest()[:20]}"

    @staticmethod
    def _normalise(text: str):
        value = str(text or "").strip().lower()
        for alias, replacement in KnowledgeGraph.ALIASES.items():
            value = value.replace(alias, replacement)
        return value

    @staticmethod
    def _tokens(text: str):
        normalised = KnowledgeGraph._normalise(text)
        ascii_terms = re.findall(r"[a-z0-9_]+", normalised)
        chinese_terms = []
        for part in re.findall(r"[\u4e00-\u9fff]+", normalised):
            if len(part) == 1:
                chinese_terms.append(part)
            else:
                chinese_terms.extend(part[index:index + 2] for index in range(len(part) - 1))
        return list(dict.fromkeys(ascii_terms + chinese_terms))[:120]

    def initialize(self):
        with self.lock:
            documents = {item["id"]: copy.deepcopy(item) for item in KNOWLEDGE_DOCUMENTS}
            if self.storage_path.exists():
                try:
                    stored = json.loads(self.storage_path.read_text(encoding="utf-8"))
                    items = stored.get("items", []) if isinstance(stored, dict) else stored
                    if not isinstance(items, list):
                        raise ValueError("items must be a list")
                    for item in items:
                        if isinstance(item, dict) and item.get("id"):
                            documents[item["id"]] = item
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    raise RuntimeError(f"本地知识图谱文件无法读取：{self.storage_path}: {exc}") from exc
            self.documents = documents
            self._rebuild()
            self.initialized = True
            return self.status()

    def _ensure(self):
        if not self.initialized:
            self.initialize()

    def _rebuild(self):
        self.engine = AdjacencyGraph()
        self.document_nodes = {}
        self.document_edges = {}
        for item in self.documents.values():
            self._index_document(item)

    def _index_document(self, item: dict):
        source_id = self._key("source", item["id"])
        crop = item.get("crop") or "番茄"
        crop_id = self._key("topic", crop)
        problem_id = self._key("problem", crop + ":" + item["problem"])
        cause_id = self._key("cause", item["id"])
        measure_id = self._key("measure", item["id"])
        nodes = {source_id, crop_id, problem_id, cause_id, measure_id}
        edges: set[tuple[str, str, str]] = set()

        self.engine.add_entity(crop_id, "topic", {"name": crop, "category": 0})
        self.engine.add_entity(problem_id, "problem", {"name": item["problem"], "category": 2})
        self.engine.add_entity(cause_id, "cause", {"name": item["cause"], "category": 3})
        self.engine.add_entity(measure_id, "measure", {"name": item["measure"], "category": 4})
        self.engine.add_entity(source_id, "source", {
            "id": item["id"], "name": item["id"], "title": item["title"], "category": 5,
            "verified": bool(item.get("verified")), "source_kind": item.get("source_kind", "manual"),
        })

        relation_rows = [
            (crop_id, problem_id, "HAS_PROBLEM", "关联主题"),
            (problem_id, cause_id, "HAS_CAUSE", "原因或说明"),
            (cause_id, measure_id, "ADDRESSED_BY", "建议措施"),
            (cause_id, source_id, "SUPPORTED_BY", "来源支持"),
        ]
        for source, target, kind, label in relation_rows:
            self.engine.add_relation(source, target, kind, {"label": label, "document_id": item["id"]})
            edges.add((source, target, kind))

        for environment in item.get("environments") or []:
            environment_id = self._key("environment", environment)
            nodes.add(environment_id)
            self.engine.add_entity(environment_id, "environment", {"name": environment, "category": 1})
            self.engine.add_relation(environment_id, crop_id, "AFFECTS", {
                "label": "影响或观察因素", "document_id": item["id"]
            })
            edges.add((environment_id, crop_id, "AFFECTS"))

        self.document_nodes[item["id"]] = nodes
        self.document_edges[item["id"]] = edges

    def _persist(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": self.VERSION,
                   "items": [self.documents[key] for key in sorted(self.documents)]}
        handle, temporary_name = tempfile.mkstemp(
            prefix=self.storage_path.name + ".", suffix=".tmp", dir=self.storage_path.parent
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as temporary:
                json.dump(payload, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
            os.replace(temporary_name, self.storage_path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise

    def all(self, q: str = ""):
        with self.lock:
            self._ensure()
            items = [copy.deepcopy(self.documents[key]) for key in sorted(self.documents)]
            query = self._normalise(q)
            if not query:
                return items
            terms = self._tokens(query)
            output = []
            for item in items:
                haystack = self._normalise(json.dumps(item, ensure_ascii=False))
                if query in haystack:
                    output.append(item)
                    continue
                if sum(1 for term in terms if term in haystack) >= 2:
                    output.append(item)
            return output

    def upsert(self, item: dict):
        with self.lock:
            self._ensure()
            value = copy.deepcopy(item)
            value["crop"] = value.get("crop") or "番茄"
            if not value.get("id"):
                raise ValueError("知识资料必须包含 id")
            self.documents[value["id"]] = value
            self._rebuild()
            self._persist()
            return copy.deepcopy(value)

    def retrieve(self, question: str):
        with self.lock:
            self._ensure()
            query = self._normalise(question)
            terms = self._tokens(query)
            ranked = []
            for item in self.documents.values():
                title = self._normalise(item.get("title", ""))
                problem = self._normalise(item.get("problem", ""))
                cause = self._normalise(item.get("cause", ""))
                content = self._normalise(item.get("content", ""))
                tags = [self._normalise(tag) for tag in item.get("tags", [])]
                score = 0
                if query and query in (title, problem, self._normalise(item["id"])):
                    score += 100
                if query and (query in title or query in problem):
                    score += 40
                score += sum(18 for tag in tags
                             if tag and tag not in self.GENERIC_TAGS and tag in query)
                searchable = " ".join([title, problem, cause, content, *tags])
                overlap = sum(1 for term in terms if term in searchable)
                score += overlap * 3
                if score >= 6 or (terms and overlap >= 2):
                    ranked.append((score, item["id"], copy.deepcopy(item)))
            ranked.sort(key=lambda row: (-row[0], row[1]))
            return [row[2] for row in ranked[:6]]

    def graph(self, items: list[dict]):
        with self.lock:
            self._ensure()
            if not items:
                return {"nodes": [], "edges": [], "backend": "python"}
            document_ids = [item["id"] for item in items if item.get("id") in self.documents]
            selected_nodes = set().union(*(self.document_nodes[key] for key in document_ids)) if document_ids else set()
            selected_edges = set().union(*(self.document_edges[key] for key in document_ids)) if document_ids else set()
            edge_rows = []
            for source in sorted(self.engine.relations):
                for target, kind, props in self.engine.relations[source]:
                    if (source, target, kind) in selected_edges:
                        edge_rows.append({"source": source, "target": target, "type": kind,
                                          "label": props.get("label", kind)})

            entities = [self.engine.entities[key] for key in selected_nodes if key in self.engine.entities]
            entities.sort(key=lambda entity: (entity["properties"].get("category", 9),
                                               entity["properties"].get("name", ""), entity["id"]))
            counts: dict[int, int] = defaultdict(int)
            for entity in entities:
                counts[entity["properties"].get("category", 0)] += 1
            positions: dict[int, int] = defaultdict(int)
            icons = {0: "seedling-fill", 1: "drop-fill", 2: "", 3: "leaf-fill",
                     4: "settings-3-fill", 5: "file-text-line"}
            xs = {0: 220, 1: 70, 2: 390, 3: 560, 4: 735, 5: 935}
            output = []
            for entity in entities:
                props = entity["properties"]
                category = props.get("category", 0)
                index = positions[category]
                positions[category] += 1
                count = counts[category]
                y = 230 if count == 1 else (40 + index * 410 / (count - 1) if category == 5
                                             else 100 + index * 260 / (count - 1))
                if category in (3, 4) and count == 2:
                    y = 145 + index * 175
                name = props.get("name", entity["id"])
                if category == 4:
                    name = name.replace("营养液 ", "").replace("检查", "检查\n", 1)
                if category == 5:
                    name += "\n" + ("已核验资料" if props.get("verified") else "待核验资料")
                output.append({
                    "id": props.get("id", entity["id"]), "name": name, "category": category,
                    "x": xs[category], "y": y, "full_name": props.get("title") or props.get("name", ""),
                    "icon": {"EC": "pulse-line", "水温": "temp-cold-line"}.get(
                        props.get("name"), icons[category]), "graph_uid": entity["id"],
                })

            display_ids = {entity["id"]: entity["properties"].get("id", entity["id"])
                           for entity in entities}
            return {
                "nodes": output,
                "edges": [{**edge, "source": display_ids[edge["source"]],
                           "target": display_ids[edge["target"]]} for edge in edge_rows],
                "backend": "python",
            }

    def status(self):
        with self.lock:
            if not self.initialized:
                self.initialize()
            stats = self.engine.get_statistics()
            return {
                "backend": "python", "connected": True, "storage": "local_json",
                "persistent": True, "path": str(self.storage_path),
                "sources": len(self.documents), "nodes": stats["total_entities"],
                "relationships": stats["total_relations"],
                "entity_types": stats["entity_types"],
                "relation_types": stats["relation_types"],
            }


kg = KnowledgeGraph()
