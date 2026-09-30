# 多源感知水培智控系统 · 项目结构与功能说明

本文由通读仓库全部源码、配置、脚本、测试与文档后整理，描述各目录、模块、关键文件的用途及相互调用关系，并总结整体定位、主要特性与技术要点。文中所有结论以当前工作区（HEAD = `d1036c8`）的实际内容为准。

## 1. 项目定位与技术栈

面向中小学劳动教育与科技教育的**物联网水培（番茄）教学平台**。网页端把水培设备的真实环境数据、AI 视觉识别结果、知识图谱问答、课程实训任务和生长档案集中在一起，强调「真实数据、可追溯来源、不造演示数据」。

| 层次 | 技术选型 |
| --- | --- |
| 前端 | Vue 3（`<script setup>` 单文件组件）+ Vite 6，ECharts 5（曲线/图谱）、Remixicon、html-to-image（截图） |
| 后端 | Python 3.12 + FastAPI + Uvicorn，Pydantic v2 做载荷校验 |
| 业务存储 | SQLite（WAL 模式，`objects` 键值表 + `telemetry` 表，见 `backend/store.py`） |
| 知识存储 | 真实 Neo4j 5.26 + Cypher（唯一权威图谱，禁止内存/Fallback） |
| 设备通道 | Paho MQTT 2.x，连接本机 EMQX；协议由 `backend/config/mqtt.yaml` 驱动 |
| 视觉 | Ultralytics YOLOv8n 本地 CPU 推理（`tomato-v1.pt`） |
| 本地大模型 | Ollama HTTP API（默认 `qwen3.5:4b`），无云端回退 |
| 部署 | Docker Compose 三容器（web / api / neo4j）+ Nginx 反代；另有本地非容器开发方式 |
| 静态托管骨架 | ChatGPT Sites / Cloudflare Worker 兼容产物（`worker/index.js` + `dist/server`） |

## 2. 目录结构总览

```
tomatosmart/
├── index.html              单页应用宿主（挂载 #app）
├── vite.config.mjs         Vite 配置：outDir=dist/client、:5176、/api 反代到 8016
├── package.json            前端依赖与脚本（dev / build / test:sites）
├── docker-compose.yml      权威部署编排：neo4j + api + web
├── compose.neo4j.yml       仅启动独立 Neo4j（本地开发用）
├── start.sh                非容器开发一键启动（Neo4j + uvicorn + vite）
├── 一键修改IP.cmd          Windows 双击入口，调用 scripts/change-ip.ps1
├── AGENTS.md               原型约定、历次用户决策与硬性约束
├── README.md               产品说明、启动方式、功能边界
├── backend/                后端（FastAPI + 业务 + 协议 + 图谱 + 视觉 + 相机）
│   ├── config/             权威配置：mqtt.yaml、camera.yaml
│   ├── models/             权重元数据 tomato-v1.json（权重本体不入库）
│   └── *.py                19 个模块，见 §3
├── src/                    前端 Vue 应用，见 §4
├── public/assets/          字体、番茄生长周期科普配图
├── docker/                 两个 Dockerfile 与 Nginx 配置
├── scripts/                运维、配置与端到端 QA 脚本
├── tests/                  pytest 集成测试 + Node 单元测试 + 设备/固件核验脚本
├── docs/                   主题文档与 QA 证据（docs/qa/*）
└── worker/index.js         Sites 托管用 Worker fetch 处理器
```

## 3. 后端模块（`backend/`）

### 3.1 入口与应用装配

- **`main.py`（应用入口，585 行）**：创建 `FastAPI` 实例、注册路由与鉴权依赖、异常处理器，并在 `lifespan` 中加载 YOLO 权重、初始化 Neo4j、启动两个后台任务（`ticker()` 遥测心跳/回执超时巡检 + `service.maintain()` MQTT 自动重连）。
  - 鉴权依赖链：`actor()`（必须登录）→ `editor()`（家长只读被拒）→ `teacher()`（教师/管理员）→ `admin()`（仅管理员）。
  - 路由族：会话、设备 CRUD 与模式切换、遥测与聚合、快照存档、MQTT 配置与连接动作、协议命令与执行器命令、预警、知识问答与图谱、知识资料增改、通用对象列表、档案/探究/收藏、日志标记、课程任务与提交评价、摄像头帧/探测/配置/SSE 事件、照片上传、识别、导出（csv/xlsx/pdf/json/zip）。
  - 角色与数据隔离由 `scoped()` 实现：学生/家长只看到 `owner` 属于自己的档案、提交、收藏与探究记录。
- **`sessions.py`**：本地持久化会话。Token 经 SHA-256 存表，附 HMAC `auth_proof`（绑定角色与本地免密模式或环境变量密码），有效期 8 小时，`secrets.compare_digest` 常数时间比较。
- **`schemas.py`**：Pydantic 载荷模型。`TelemetryValues`（7 项参数、范围与有限性校验）、`TomatoTelemetryValues`（r19 固件显式 `null` 语义、`strict`）、`MQTTConfig`（主机名/密码/主题交叉校验，V1.1 禁通配符）、`Command`、`Question`、`Record`、`Device`。

### 3.2 业务数据与规则

- **`store.py`**：SQLite 数据层。`REAL_ONLY`（默认 1）决定数据目录 `backend/real-data/`；`objects(kind,id,data)` 存所有 JSON 实体，`telemetry` 表按 `(device,ts)` 建索引；`add_telemetry()` 在真实模式拒绝 `source!='mqtt'`；`aggregate()` 用 `json_extract` + `strftime` 做小时/分钟聚合，并按设备 `source`/`units` 过滤，避免演示与实机数据混算；`log()` 自动为日志记录当时的设备采样快照（evidence）。
- **`control.py`**：阈值自动策略（仅旧协议路径生效）。`desired_states()` 带滞回（如光照 8500/10000 lx、温度 29/27 ℃、湿度 50/60 %RH）且**液位低联锁优先关泵**；遥测过期、MQTT 断线或回执超时都会把设备降级为手动模式并写日志。r19 番茄架直接返回，AI 模式由固件掌控。
- **`main.py: /api/summary/{id}` 与 `/api/alerts`**：按当日执行记录统计浇水次数、补光时长、识别次数（明确声明「不估算未记录动作」）；预警基于设备阈值与 `metric_units`（液位 cm/百分比自适应）。

### 3.3 MQTT 与设备协议

- **`mqtt_config.py`**：`backend/config/mqtt.yaml` 的唯一读写入口。原子写入（临时文件 + `os.replace`、`chmod 600`）；密码以 `${ENV_NAME}` 引用保存，替换值时写回 `.env` 而 YAML 始终保留引用，API 不回显明文。
- **`mqtt_service.py`**：`MQTTService` 单例。支持 legacy 与 `tomato_v1_1` 双协议；连接/订阅状态机（`connected`、`subscribed`、`error`）、`device_online()` 综合可用性主题 + 遥测新鲜度；`protocol_command()` 校验命令后发布 `set` 主题并落库 `sent_unconfirmed`；`maintain()` 实现 `autoconnect` 自动重连。
- **`tomato_protocol.py`**：r19 / V1.1 消息适配。`validate_command()` 依 YAML 校验命令号与字段范围；`ingest()` 分四类主题处理——遥测（字段名映射 + 缩放，如 EC μS/cm→mS/cm ×0.001，显式 `null` 保留为「无读数」）、`availability`（在线状态）、`state`（以设备上报为权威，含 9 个字段与 rest_schedule 校验，并推导 `control_mode`→auto/manual）、`result`（`request_id`+`cmd` 关联校验，成功需 `success&applied`）。拒绝保留位（retained）遥测与回执。
- **`device_simulator.py`**：可选 CLI 模拟器（legacy 协议），仅打印 `SIMULATED (not physical)`，不驱动真实硬件。
- **`config/mqtt.yaml`**：协议权威定义。根主题 `tomato_hnsw0001`，QoS 全 0，遥测 15 s、过期 45 s、回执超时 30 s；9 条命令（01~09）、补光 5 档、执行器映射（pump=03、light=04，fan/mist 明确不支持）。

### 3.4 知识图谱与本地 AI

- **`knowledge_graph.py`**：`KnowledgeGraph` 门面。`initialize()` 建 `HydroNode.uid` 唯一约束；`upsert()` 用 Cypher `MERGE` 写「作物—问题—原因—措施—来源—环境」六类节点及 `HAS_PROBLEM / HAS_CAUSE / ADDRESSED_BY / SUPPORTED_BY / AFFECTS` 关系；`retrieve()` 只把用户文本作为参数（不做字符串拼 Cypher），用中文别名归一化 + 2-gram 重叠打分召回；`graph()` 按 category 计算坐标生成前端可直接渲染的节点/边；`status()` 返回节点与关系计数。所有查询带 `scope`（真实模式为 `hydroponic-real`），无任何内存回退。
- **`local_ai.py`**：Ollama 客户端。`status()` 探测 `/api/tags` 列出已装模型；`generate()` 用强约束 `SYSTEM` 提示词（只依据来源原文、必须给出 `source_ids`、`verified=false` 须声明待核验、环境 `null`/`is_stale` 不能当当前值、不得宣称执行设备动作），`format='json'` + Pydantic 二次严格校验，引用越界即丢弃答案；模型离线/超时/并发占用统一抛 `AIUnavailable`（HTTP 503）。
- **`import_project_knowledge.py`**：把 `docs/mqtt-protocol.md`、`docs/local-emqx.md` 的指定小节按标题切出，作为 `KB-PROJECT-*` 资料写入 Neo4j，保留 `source_path` 与 `source_sha256`，标记 `verified=false`（项目文档 ≠ 农艺专家结论）。幂等，已存在则跳过。
- **`migrate_knowledge.py`**：把 SQLite 中已有知识迁入 Neo4j，已有记录优先，不覆盖。

### 3.5 视觉识别与摄像头

- **`vision.py`**：`VisionService`。加载本地权重（`YOLO_MODEL_PATH`），校验任务为 `detect`，计算权重 SHA-256，按 `Unripe/Half-ripe/Ripe → 未成熟/半成熟/成熟` 翻译，并对用户确认的 `best(3).pt` 该 SHA-256 **交换 0/2 标签**（真实照片验证发现类别名反了）；`YOLO_CLASS_MAP` 必须覆盖全部类别；`predict()` 按置信度过滤并返回框与元数据；任何失败抛 `ModelUnavailable`，不产出替代结果。
- **`remote_camera.py`**：远程取图与诊断。`camera_url()` 校验 HTTP/HTTPS IPv4（拒回环/链路本地/组播/保留地址），裸 `host:port` 自动补已配置路径；`probe()` 依次尝试请求地址与 `/snapshot`、`/image`、`/download`；`_failure_kind()` 解析异常链区分 refused/timeout/unreachable/dns/not_image 等，`advice()` 给出可执行建议；`fetch_frame()` 只请求用户填写的地址，且识别 `X-Camera-Receiver` 头以支持「接收服务已连通、等待上传」。始终区分「获取时间」与未知的「采集时间」。
- **`camera_config.py`**：`backend/config/camera.yaml` 的唯一读写入口（URL、刷新秒数、旋转角 0/90/180/270），无硬编码默认地址。
- **`camera_receiver.py`**：ESP32-P4 照片推送接收端，挂载于应用级路由 `/snapshot`。POST 接收原始 JPEG/PNG 或单文件 multipart（大小/像素/魔数/截断校验，可选按 `rotate` 转正），单行 `INSERT OR REPLACE` 原子覆盖最新照片（`camera_snapshot` 表）；GET/HEAD 返回最新原图，超过 60 s 未更新则 404 并标注 `X-Camera-Stale`；通过 `threading.Condition` 版本号向 SSE 广播上传事件；不写入用户相册、不自动识别。

### 3.6 后端内部调用关系

```
main.py
 ├─ store(s)            ← 所有模块共用的数据层
 ├─ sessions.py         ← 登录会话
 ├─ mqtt_service.service ─→ mqtt_config ─→ config/mqtt.yaml
 │        └─ tomato_protocol ─→ schemas / store
 ├─ control.evaluate_device ─→ store + mqtt_service
 ├─ knowledge_graph.kg  ─→ Neo4j(bolt)
 ├─ local_ai.local_ai   ─→ Ollama(HTTP)
 ├─ vision.vision       ─→ tomato-v1.pt(Ultralytics)
 ├─ remote_camera       ─→ camera_config ─→ config/camera.yaml
 ├─ camera_config
 └─ camera_receiver     ─→ store(camera_snapshot) + 提示 remote_camera
```

## 4. 前端模块（`src/`）

- **`App.vue`（主壳，179 行）**：唯一「页面级」组件。9 个桌面导航（总览 / 课堂任务 / 设备物联 / 劳动教育 / 科技探究 / 班级成果 / 课程资源 / AI 助教 / 教学档案）+ 6 个移动端底部导航，基于 `location.hash` 的轻量路由；集中管理设备、遥测趋势、预警、指令、任务、提交、识别、MQTT 状态、登录与各类弹窗；每 2 秒轮询 `/devices`、`/mqtt`、`/alerts`、`/commands`；`setSessionRecovery` 注册会话失效恢复（演示模式自动重登并重放被拒请求）。
- **`api.js`**：统一 `fetch` 封装（`credentials: same-origin`、JSON/FormData 自动处理、401 单次并发去重的会话恢复重试、错误信息抽取）与 `download()` 导出跳转。
- **`KnowledgeWorkspace.vue`**：知识库三栏（问答 / 浏览 / 记录）。左「知识图谱观察窗」、右「回答区」；支持 `local_ai` 与 `neo4j_graph` 两种回答方式、模型下拉、来源编号追溯、新增/编辑资料（写入 Neo4j 并保持待核验）、收藏与探究记录、分享、截图。
- **`Graph.vue`**：ECharts force 图谱。六类节点配色与图标、节点尺寸自适应、tooltip/点击聚焦相邻、缩放复位、沉浸全屏、`ResizeObserver` 响应式与 `prefers-reduced-motion` 降级；`image()` 暴露 `getDataURL` 供截图归档。
- **`Trend.vue`**：ECharts 折线图，按 `metric` 渲染 7 项参数之一，EC 走 `formatMetricValue` 统一格式化。
- **`RecognitionImage.vue`**：以 SVG 叠加在 `<img>` 上按原始像素坐标绘制识别框与「序号 · 置信度」，随阈值实时变化。
- **`CameraDialog.vue`**：本机 `<video>` 拍照 / 远程取图两种模式。远程模式连接 `GET /api/camera/events`（SSE）即时刷新，编辑地址会取消在途请求与旧预览，支持「检测连接」逐址报告、保存为默认地址；拍照后照片先本地暂存，登录失效或上传失败可「重试保存」。
- **`HardwareControls.vue`**：r19 固件九命令面板。雾化泵（CMD 03）、补光灯总开关（04）为手动模式专属开关；亮度、补光阶段、泵间隔/时长、休息时段（09）在「亮度与运行设置」中调整；CMD 08 切换设备 AI 智控/手动；所有按钮在 MQTT 未连接、设备离线或缺少 `state` 时禁用。
- **`MqttStatusPanel.vue`**：只读通信状态展示（连接/订阅、发布主题与 QoS、订阅列表、最近收报时间、传感器无读数提示）。
- **`MqttConfigDrawer.vue`**：完整 MQTT 配置抽屉（Broker、Client ID、账号密码（可显隐、明文不回显）、TLS、QoS、Keepalive、自动连接、绑定设备、五个协议主题），支持保存 / 测试连接 / 连接 / 断开。草稿只在挂载时取一次，避免被父组件 2 秒轮询覆盖。
- **`TomatoGrowth.vue`**：番茄生长周期科普（发芽期 / 幼苗期 / 开花坐果期 / 结果期），配用户提供图片，`role=tablist` 键盘导航，页脚声明「通用科普，不代表当前设备实测状态」。
- **`metric-format.js` / `charts.js` / `main.js` / `styles.css`**：EC 数值统一格式化（避免浮点尾巴）、ECharts 按需注册、应用挂载、全局与响应式视觉系统。

## 5. 部署与运维

- **`docker-compose.yml`**：三服务编排。
  - `neo4j`：5.26，仅绑定回环 7476/7689，数据在 `./data/neo4j`，带 healthcheck。
  - `api`：`docker/api.Dockerfile`（python:3.12-slim，分步安装基础依赖与 vision 依赖，`uvicorn backend.main:app`）。真实模式、数据目录 `/app/data`、权重只读挂载、`.env` 挂载为 `/app/.env.local`、`config/` 与 `models/` 卷挂载；仅绑定 `127.0.0.1:8016`。
  - `web`：`docker/web.Dockerfile`（node:24 构建 `dist/client` 并跑 `test:sites`，再交给 nginx）。发布 `5176/5173`（网页，所有网卡）与 `500`（仅 `/snapshot` 硬件入口）。
- **`docker/nginx.conf`**：80 端口反代 `/api/` → `api:8016`（关闭缓冲以支持 SSE）；500 端口只暴露 `location = /snapshot`，其余 404。
- **`scripts/change-ip.ps1` + `一键修改IP.cmd`**：按字节精确保留原格式地替换 `mqtt.yaml` 的 `mqtt.host` 与 `camera.yaml` 的 `camera.url` 主机部分（保留端口/路径/引号风格），改前备份到 `data/ip-backups/` 并写 `change.json`，再校验容器内可见新值后重启 api。不切换网络、不改网卡与设备端配置。
- **`scripts/configure-local-emqx.ps1`**：从固件源码解析默认凭据，配置 EMQX 认证/授权与 1883 防火墙规则（临时管理员账号、用后即删）。
- **`scripts/configure-camera-ingress.ps1`**：放通本机 500 端口入站（仅本地子网）。
- **`scripts/start-neo4j.sh`**：生成 `.env` 随机密码、启动独立 Neo4j、等待就绪并迁移知识。

## 6. 测试与质量保障

| 文件 | 作用 |
| --- | --- |
| `tests/conftest.py` | 会话级 fixture：临时 MQTT YAML、随机 Neo4j `scope`，初始化后清理测试节点 |
| `tests/test_api.py` | 角色边界、知识召回、档案隔离、课程提交评价、MQTT 配置与密钥脱敏、控制不虚报执行、遥测/回执身份校验、识别与导出、聚合与设备 CRUD、自动策略滞回、演示数据不冒充实机、日志证据快照 |
| `tests/test_tomato_protocol.py` | YAML 协议定义、命令校验、result/availability 身份、`${ENV}` 密钥引用、retained 遥测不得使设备显示在线 |
| `tests/test_mqtt_live.py` / `test_neo4j_live.py` / `test_knowledge_ai.py` / `test_vision_labels.py` / `test_tomato_null_telemetry.py` | 真实 TCP MQTT（随机端口 AMQTT）、真实 Neo4j、本地 AI 引用约束、模型标签映射、`null` 遥测语义 |
| `tests/metric-format.test.mjs` / `auth-recovery.test.mjs` / `sites-worker.test.mjs` | 前端 EC 格式化、401 恢复重放语义、Sites 产物与 Worker 回退行为 |
| `tests/verify_*.py` | 固件 AST 与 YAML 契约比对（不执行固件）、摄像头、相机接收、改 IP、EMQX 的现场核验脚本 |
| `scripts/verify-*-preview.mjs` | 通过 CDP 驱动真实浏览器，在隔离 QA 服务上跑通九条命令并截图，产出 `docs/qa/*.json` 证据 |

## 7. 关键调用链

1. **实机遥测**：ESP32-S3 → EMQX(`tomato_hnsw0001/telemetry`) → `mqtt_service.on_message` → `tomato_protocol.ingest` → 字段映射+缩放 → `store.add_telemetry` → 前端 2 s 轮询 `/api/telemetry/{id}` → `Trend.vue` 曲线。
2. **设备控制**：`HardwareControls.vue` → 确认弹窗 → `POST /api/devices/{id}/protocol-commands` → `service.protocol_command` → 发布 `.../set`（QoS 0）→ ESP32 回 `.../result` → 校验 `request_id`/`cmd` → 指令置 `acknowledged`；真实开关状态以 `.../state` 为准。
3. **成熟度识别**：上传/拍照 → `POST /api/photos` → `POST /api/recognitions`（带阈值 0.65）→ `vision.predict` → 画框存标注图 → 同时写 `recognitions` 与 `records` → 页面用 `RecognitionImage.vue` 按阈值实时过滤。
4. **知识问答**：`KnowledgeWorkspace` → `POST /api/ask` → `kg.retrieve`（Cypher 打分）→ 可选 `local_ai.generate`（Ollama，引用校验）→ 落库 `answers` 并写带证据的 `logs` → `Graph.vue` 渲染关系图。
5. **照片推送**：ESP32-P4 → `POST :500/snapshot` → Nginx → `camera_receiver` 入库 → 条件变量通知 → `GET /api/camera/events`(SSE) → `CameraDialog` 立即取图。

## 8. 主要特性与技术要点

1. **真实数据优先**：`HYDRO_REAL_ONLY=1` 默认开启，禁止示例初始化、模拟遥测与演示识别；历史演示数据隔离保存且不改标签冒充真实数据。
2. **知识源头可追溯**：Neo4j 为唯一图谱与检索来源，服务不可用返回 503 而不回退；每条回答、收藏、探究记录保留原文、模型信息与采样快照；资料带 `verified` 标记与修订历史。
3. **协议由配置驱动**：`mqtt.yaml` 是设备协议的权威描述，固件契约可用 AST 静态比对验证（`verify_firmware_contract.py`），把「平台假设」降到最低。
4. **安全性**：角色化依赖注入；会话 Token 哈希存储 + HMAC 证明 + 8 小时过期；MQTT 密码只允许替换、永不回显；Cypher 不使用字符串拼接；CSV 导出对 `= + - @` 前缀做公式注入转义；照片与上传均做大小/像素/格式校验。
5. **可解释的自动化**：阈值策略带滞回、低液位联锁，异常即降级手动；设备回执与物理状态分离记录，从不虚报已执行。
6. **双端一致的响应式 UI**：同一 Vue 应用适配教室大屏与手机，含移动端底部导航与 `prefers-reduced-motion` 降级。

## 9. 问题核对记录（与代码实际状态核对结果）

1. **`backend/main.py` 语法错误，后端无法启动 —— 已修复并验证（严重）**。
   - 原故障：第 197 行 `第二，整理数据并标记缺失。`（中文散文被当成代码），`SyntaxError: invalid character '，' (U+FF0C)`；同时 `@app.get('/api/mqtt'))` 多一个右括号、`save_snapshot()` 内 `note += ...` 缩进错误且函数无 `return`、第 2–41 行约 30 个与项目无关的导入。
   - 溯源：由提交 `2e117af`（feat: 摄像头上传即时刷新（SSE））引入，此前各版本 `main.py` 均可编译，HEAD `d1036c8` 仍未修复。
   - **修复方式（最小回退，不改功能）**：把损坏的三处恢复为原程序——① 导入区回退到 `08ab92c` 版本，仅保留 `from neo4j.exceptions import Neo4jError, DriverError`（该提交新增的 Neo4j 异常处理所需）；② 被改坏的 `save_snapshot()` 恢复为原本可用的 `snapshot(id, u)` 实现；③ `@app.get('/api/mqtt'))` 恢复为 `@app.get('/api/mqtt')`。修复后与 `08ab92c` 的差异仅为该提交的合法功能改动：Neo4j 异常处理器（离线 503）、图谱 `limit` 默认 100、问答 `mode` 为 `neo4j_graph`、`GET /api/camera/events` SSE 路由。
   - **验证结果**：`py_compile` 全部后端文件通过；`import backend.main` 成功（title=多源感知水培智控系统 API，顶层路由 51 条）；实际启动 uvicorn 后实测：`/api/health` 200（`real_only:true`）、未登录 401、登录/会话 200、`/api/devices` 200、`/api/mqtt` 200（密码 `password_set:false` 不回显）、`POST /api/devices/{id}/snapshot` 409（无遥测，符合预期）、上传照片 200、未配置权重时识别 503、演示识别被拒 403、家长写入被拒 403、Neo4j 离线时 `/api/knowledge/status` 与 `/api/ask` 均为 503 且提示「未使用本地替代图谱」、`GET /snapshot` 404（接收服务就绪无照片）、`/api/camera/events` 返回 `text/event-stream`、导出 CSV 200。
2. **`backend/from fastapi import FastAPI.txt` —— 已删除**：误入库的孤立文件（50 行），内容是另一个项目的 FastAPI 片段，与本项目无关，从初始提交即存在，文件名本身来自代码首行。经用户确认后已从仓库删除（`git status` 显示为 `D`）。
3. **IP 配置与文档不一致 —— 已统一为 `192.168.31.217`**。此前 `backend/config/mqtt.yaml` 的 `host` 与 `backend/config/camera.yaml` 的 `url` 是 `192.168.31.10`，而 `README.md`、`docs/*`、`AGENTS.md`、`scripts/change-ip.ps1` 示例、`src/MqttConfigDrawer.vue` 占位以及**设备端已保存的服务器地址**都是 `192.168.31.217`。选择 .217 而非 .10 的依据：① `AGENTS.md` 记录设备端保存的 MQTT 地址为 `192.168.31.217`，且「设备配置保持不动」；② `AGENTS.md` 2026-09-15 记录用户明确要求「只需将配置统一为 `192.168.31.217`，无需继续排查实际网络或切换 Wi-Fi」；③ 若取 .10 会与设备端地址不一致而无法连通。现两个 YAML 均已改为 `192.168.31.217`，端口 `500`、路径 `/snapshot`、QoS、根主题与 9 条命令均保持原样；改动前配置已备份到 `data/ip-backups/20260930-174108-45937750/`。
   - 需现场核实的事实：本机当前实际 WLAN 地址是 **192.168.110.215**（另有 VMware 虚拟网卡 192.168.171.1 / 192.168.229.1），即本机此刻不在 `192.168.31.x` 网段。配置与文档已按要求统一到 `192.168.31.217`；硬件要真正连通仍需本机处于持有该地址的 `NANANA` 网络（见 `docs/local-emqx.md`），换网络后用 `一键修改IP.cmd` 同步即可。
4. **仓库描述与提交历史不一致**：提交 `08ab92c`（「去除了 docker」）删除了 `docker/`、`docker-compose.yml`、`compose.neo4j.yml`、`scripts/start-neo4j.sh`，但当前工作区这些文件**都存在**且 `README.md` 以 Docker 部署为主（由后续 `1cfe8b5`「合并界面更新并保留 Docker 部署」恢复）。

## 10. 修复动作与后续建议

- **已执行（第一批）**：仅修改 `backend/main.py` 的三处损坏内容（见 §9.1），未改动业务逻辑、配置与其他文件；验证产生的运行数据（`backend/real-data/`、临时图片与 cookie）在验证后已清理。
- **已执行（第二批，经用户确认）**：① 删除误入库的 `backend/from fastapi import FastAPI.txt`（见 §9.2）；② 把 `backend/config/mqtt.yaml` 的 `host` 与 `backend/config/camera.yaml` 的 `url` 统一为 `192.168.31.217`（见 §9.3），改动前配置备份在 `data/ip-backups/`。
- **一处环境限制（不影响你的机器）**：本项目自带的 `scripts/change-ip.ps1` 逻辑正确（已成功生成备份并算出新地址），但在本次执行环境中，它收尾删除临时文件的那一步被本机「安全删除」机制拦截并触发了自身回滚，于是只写入了 `mqtt.yaml`；`camera.yaml` 由我按其同一规则精确补改。在你自己电脑上正常双击 `一键修改IP.cmd` 不会遇到该拦截。
- **完整回归需要环境**：`pytest`（`tests/`）中的会话级 fixture 会连接真实 Neo4j（`bolt://127.0.0.1:7689`），需先 `docker compose -f compose.neo4j.yml up -d` 或运行 `scripts/start-neo4j.sh`；本地 AI 与 YOLO 相关用例还需要 Ollama 与 `backend/models/tomato-v1.pt` 权重。
- 启动方式：`python -m uvicorn backend.main:app --host 127.0.0.1 --port 8016` 与 `npm run dev -- --host 127.0.0.1 --port 5176 --strictPort`（或 `./start.sh` / `docker compose up -d --build`）。
