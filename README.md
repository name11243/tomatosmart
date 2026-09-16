# 多源感知水培智控系统

番茄水培教学与设备管理原型。前端使用 Vue 3，后端使用原生 Python FastAPI，业务记录存入 SQLite，知识库使用纯 Python 邻接表图谱和本地 JSON 持久化，Paho MQTT 连接真实设备。项目不依赖 Docker 或 Neo4j。

## 本机入口

- 前端：http://127.0.0.1:5176/#knowledge
- 局域网前端：http://192.168.31.217:5176/#knowledge
- API 文档：http://127.0.0.1:8016/docs
- ESP32-P4 照片推送：http://192.168.31.217:500/snapshot

默认 `HYDRO_REAL_ONLY=1`，禁止模拟遥测和演示识别。业务数据、上传照片和知识编辑记录保存在 `backend/real-data/`；设备、茬次与实际课程由用户录入。随代码提供的番茄与健康教育知识是有来源状态的课程材料，不是设备数据，全部默认标记为待核验。

## 安装与启动

Windows：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm install
Copy-Item .env.example .env
.\start.ps1
```

Linux / macOS：

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm install
cp .env.example .env
./start.sh
```

启动脚本同时运行主 API（8016）、仅提供 `/snapshot` 的照片接收服务（500）和前端（5176）。前端监听所有本机接口，API 仅绑定回环地址。生产前端构建输出到 `dist/client`。

## 纯 Python 知识图谱

`backend/knowledge_graph.py` 采用内存邻接表，提供节点、关系、类型索引、邻居查询、路径查找和子图导出。`backend/knowledge_content.py` 内置番茄生长周期、种植观察以及劳动与健康教育主题；健康教育内容明确标注为主题整理、非教材原文。

教师或管理员新增、编辑资料后，内容原子写入 `HYDRO_KNOWLEDGE_FILE`，默认是 `backend/real-data/knowledge_graph.json`。重启后会先载入 Python 内置资料，再用本地持久化版本恢复编辑和新增内容。问答、收藏和探究记录继续保留当次来源、图谱、模型与环境快照。

知识问答可选择纯图谱检索，或使用本机 Ollama `qwen3.5:4b` 根据检索原文生成带引用的回答。无来源不生成诊断；模型离线不会影响纯 Python 图谱查询。详见 [纯 Python 图谱](docs/python-knowledge-graph.md)和[本地 AI 查询](docs/knowledge-ai.md)。

## 功能与边界

- 物联网：完整 MQTT 配置、真实遥测、小时/天/周曲线、设备控制、回执和状态展示。
- MQTT：按 ESP32-S3 r19 与 V1.1 协议使用固定根主题 `tomato_hnsw0001`、QoS 0 和 15 秒遥测；权威配置为 `backend/config/mqtt.yaml`。
- 成熟度：真实番茄 YOLO 模型推理，默认最低置信度 65%，同步筛选框、列表和统计；原图与推理记录可追溯。
- 摄像头：浏览器拍照以及 ESP32-P4 HTTP 推送/读取；默认地址由 `backend/config/camera.yaml` 管理，获取时间不冒充采集时间。
- 档案与课程：环境快照、图片、识别记录、任务提交、评价、CSV/Excel/PDF/ZIP 导出。
- 知识与教育：番茄种植、劳动安全、个人卫生、食品卫生、屏幕与工具安全等内容；待核验状态始终展示。

## 真实模型

用户确认的番茄模型部署于 `backend/models/tomato-v1.pt`，类别为 `0=Unripe/未成熟`、`1=Half-ripe/半成熟`、`2=Ripe/成熟`。权重来源和 SHA-256 记录在 `backend/models/tomato-v1.json`。需要推理时安装额外依赖：

```powershell
.venv\Scripts\python.exe -m pip install -r backend\requirements-vision.txt
```

启动时加载模型，`/api/health` 的 `model.ready` 表示状态。模型准确性仍须用真实番茄照片验证；空白对照只验证链路。

## 真实设备

本机原生 EMQX 监听 `0.0.0.0:1883`，硬件和 Python 后端均按当前配置访问 `192.168.31.217:1883`。所有已登录账户可在物联网页修改完整 MQTT 配置；密码只允许替换且不会由 API 明文回显。设备 AI 模式由固件执行，平台不把它替换成阈值控制。详见 [MQTT 协议](docs/mqtt-protocol.md)和[本机 EMQX](docs/local-emqx.md)。

## 版本管理

`.env`、SQLite、知识图谱运行 JSON、上传照片、依赖目录、构建产物和模型权重不提交。跨电脑部署时从 `.env.example` 创建本机配置，单独复制授权模型及需要迁移的 `backend/real-data/`。

## 测试

```powershell
.venv\Scripts\python.exe -m pip install -r backend\requirements-test.txt
.venv\Scripts\python.exe -m pytest tests\test_api.py tests\test_knowledge_ai.py tests\test_python_graph.py tests\test_mqtt_live.py tests\test_tomato_protocol.py -q
npm run build
npm run test:sites
```

图谱测试使用隔离临时 JSON 和 SQLite；MQTT 测试使用随机本机端口的临时 Broker，不访问生产设备。
