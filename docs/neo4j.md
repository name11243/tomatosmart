# 真实 Neo4j 知识图谱

知识条目和节点关系以 Neo4j 为权威数据源。`backend/knowledge_graph.py` 使用官方 Python Bolt 驱动执行参数化 Cypher；`backend/main.py` 不再生成固定节点或从 SQLite 查询知识答案。前端 ECharts 只负责呈现数据库返回的节点和关系。

## 本机连接

- 容器：`hydroponic-neo4j`，独立命名卷 `hydroponic-neo4j-data`。
- 已验证版本：Neo4j Community 5.26.30，Python 驱动 5.28.5.0。
- Browser：http://127.0.0.1:7476
- Bolt：`bolt://127.0.0.1:7689`
- 数据库/用户名：`neo4j`。随机密码存于项目 `.env`，源码压缩包不包含密码。
- 配置模板：`.env.example`；外部服务器可修改 `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD`、`NEO4J_DATABASE`。不把密码放到前端。

`./scripts/start-neo4j.sh` 会创建缺失的本机配置、启动容器、等待数据库就绪，再执行一次可重复的迁移。`./start.sh` 已包含此步骤。如果连接外部 Neo4j，直接按 README 启动 FastAPI，按需单独执行迁移命令，不运行本机容器脚本。

## 数据与查询

六类节点：Crop、Environment、Problem、Cause、Measure、HydroKnowledge。全部带 `HydroNode` 标签及 `scope` 隔离字段；`uid` 有唯一约束。

五类关系：`AFFECTS`、`HAS_PROBLEM`、`HAS_CAUSE`、`ADDRESSED_BY`、`SUPPORTED_BY`。检索先在 Neo4j 内按问题与关键词评分，再在数据库中遍历匹配资料对应的子图。布局坐标在后端按节点类别排列，坐标不代表虚构知识关系。

```cypher
MATCH (a:HydroNode {scope:'hydroponic'})-[r]->(b:HydroNode {scope:'hydroponic'})
RETURN a,r,b;
```

```cypher
MATCH p=(crop:Crop {scope:'hydroponic'})-[:HAS_PROBLEM]->(:Problem)
  -[:HAS_CAUSE]->(:Cause)-[:SUPPORTED_BY]->(kb:HydroKnowledge)
WHERE kb.id='KB-001'
RETURN p;
```

`GET /api/knowledge/status` 返回连接状态及节点/关系数量；需要登录。`GET /api/knowledge`、`POST /api/ask`、新增经验、收藏子图均读取或写入 Neo4j。新增经验使用单一 Cypher 事务落库，后续查询立即可见。SQLite 仍保存档案、任务、遥测、收藏快照和日志。

原来的 4 条示例知识已迁入 Neo4j，当前共 19 个节点、18 条关系。资料仍标记待核验；真实数据库不等于资料已经过专家审定。未接入 LLM，不宣称生成式 RAG。旧 SQLite 知识仅作为显式迁移的输入，已有 Neo4j 条目不会被迁移覆盖。

## 验证

`tests/test_neo4j_live.py` 使用独立测试 scope，在真实 Neo4j 中写入知识，通过另一个 Bolt 驱动读回，直接修改关系后验证 API 图谱同步变化。测试结束仅删除本次测试 scope。

运行：
```sh
.venv/bin/python -m pytest tests/test_api.py tests/test_mqtt_live.py tests/test_neo4j_live.py -q
```

另已实际停止并重启本项目容器：停库时 `/api/ask` 返回 HTTP 503，未使用替代图；重启后节点与关系数量一致。证据见 `qa/neo4j-live-verification.json` 与 `qa/neo4j-graph.png`。浏览器查询失败时清空旧图，避免把缓存结果展示为实时结果。

实现依据：[Neo4j Docker 部署文档](https://neo4j.com/docs/operations-manual/current/docker/introduction/)、[官方 Python 驱动事务文档](https://neo4j.com/docs/python-manual/current/transactions/)。
