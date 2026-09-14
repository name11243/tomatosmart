# 多源感知水培智控系统

基于用户选定的第 3 张 ImageGen 原型实现。前端 Vue 3，后端 Python FastAPI，业务数据使用 SQLite；知识与关系使用真实 Neo4j 持久化和 Cypher 查询，Paho MQTT 连接设备。默认打开知识图谱工作区。

## 版本管理

Git 仓库保存前后端源码、依赖锁定文件、部署配置、测试和项目文档。`.env`、数据库、上传照片等运行数据、依赖目录、构建产物及模型权重不纳入版本管理；模型来源与校验值保留在 `backend/models/tomato-v1.json`。在另一台电脑部署时，从 `.env.example` 创建本机配置，单独放置授权的 `backend/models/tomato-v1.pt` 权重；已有运行数据需要另行备份和迁移。

## 本机入口

- 前端：http://127.0.0.1:5176/#knowledge
- API 文档：http://127.0.0.1:8016/docs

默认仅使用真实数据（`HYDRO_REAL_ONLY=1`）。业务记录存储在 `backend/real-data/`，Neo4j 使用独立 `hydroponic-real` 空间；旧演示数据库及图谱原样保留，但不用于当前页面。没有预置设备、遥测、课程或示例知识。当前本机角色登录与数据模式分离，免密角色不代表模拟数据。MQTT 参数仍由后端 YAML 管理。

## 启动

### 当前 Windows Docker 部署

本机已改为三服务容器部署，项目位于 `D:\xxxxxxxxxxxxxxxx\tomatosmart`。使用 `docker compose up -d --build`，无需在 Windows 安装 Python 或 Node 依赖。

网页使用 http://127.0.0.1:5176/#knowledge ，也兼容原入口 http://127.0.0.1:5173/ 。容器版应用数据存储在 `data/app`，Neo4j 数据在 `data/neo4j`，均位于 D 盘。具体配置见 [Docker 部署说明](docs/docker-deployment.md)。下面保留源项目的非容器开发方式供参考。

### 非容器开发方式

需要运行 Docker Desktop。安装下述依赖后，先执行 `./scripts/start-neo4j.sh` 启动独立 Neo4j 并迁入已有知识，再启动两端；或直接使用 `./start.sh`。Neo4j 浏览器地址 http://127.0.0.1:7476，Bolt 地址 bolt://127.0.0.1:7689。自动生成的随机密码仅保存在本机 `.env`，未打包。

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm install
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8016
# 第二个终端
npm run dev -- --host 127.0.0.1 --port 5176 --strictPort
```

也可运行 `./start.sh`，它会使用已有依赖同时启动两端，Ctrl+C 停止本次启动的进程。生产前端 `npm run build` 输出 `dist/client`。Neo4j 使用独立容器 `hydroponic-neo4j` 和命名卷 `hydroponic-neo4j-data`。服务不可用时知识接口返回 503，不回退到写死节点。[图谱接入说明](docs/neo4j.md)。此项目还包含 Product Design 的静态托管构建骨架，但 MQTT 与数据库功能必须同时部署 FastAPI，不能仅发布静态页。

## 功能与边界

- 知识问答：Neo4j Cypher 知识检索与真实关系遍历，按来源编号追溯，支持新增经验、收藏、探究记录及截图。当前未接入大语言模型，不将检索文本冒充模型生成结论。示例知识不是经专家审定的农艺规则。
- 物联网：七项参数、小时/天/周曲线、快照、CSV/Excel、四执行器、确认弹窗、状态回执、阈值自动规则。
- MQTT：真实协议实现，包括 TLS 校验、认证、QoS、主题配置、测试、连接、断开、遥测校验、指令编号关联、回执超时；[接入协议](docs/mqtt-protocol.md)给出设备端载荷。
- 成熟度：上传、拍照入口、原图标注图、列表筛选、对比、报告。使用用户提供的番茄 YOLOv8n 权重进行真实推理，页面显示模型就绪状态，真实数据模式禁止演示识别。
- 档案：图文与环境快照、时间轴、设备/茬次筛选、记录对比、照片包、PDF 与 CSV。
- 课程：12 个实训、发布、领取、提交、照片和数据附件、教师评分评价；家长只读学生成果。
- 移动端：同一 Vue 应用适配手机，包含监控、拍照、记录、预警、问答、任务、个人中心。相机/麦克风需要浏览器权限，语音使用浏览器能力；不是 iOS/Android 原生安装包。

## 真实模型

已配置用户提供并确认为番茄模型的 `best(3).pt`，部署副本位于 `backend/models/tomato-v1.pt`。Docker 以只读目录挂载权重，使用 CPU 推理；类别为 `0=Unripe/未成熟`、`1=Half-ripe/半成熟`、`2=Ripe/成熟`。权重来源和 SHA-256 记录在 `backend/models/tomato-v1.json`，训练实验名原样保留。

非容器环境在同一 Python 环境安装推理依赖：
```sh
.venv/bin/pip install -r backend/requirements-vision.txt
export YOLO_MODEL_PATH='backend/models/tomato-v1.pt'
export YOLO_DEVICE=cpu
```
启动时加载模型，`/api/health` 的 `model.ready` 表示加载状态。真实数据模式下缺少权重或推理失败返回 503，不产生识别记录。中文标签按权重中的实际英文类别翻译；可选 `YOLO_CLASS_MAP` 必须覆盖全部真实类别。每次识别保存类别编号、原始类别名、权重 SHA-256 和推理参数。登记实际设备与茬次后，在“成熟度”页面上传番茄照片。模型准确性需用真实番茄照片验证；空白对照图检查仅验证推理链路，不作为准确率证据。

成熟度页面提供最低置信度滑块，默认 **65%**，可在 10%–95% 间调整。历史照片按所选阈值同步筛选标注框、结果列表、数量和成熟度统计；原始识别存档及其导出保留。上传或拍照时后端使用同一阈值进行推理，并把阈值写入新记录。历史记录无法显示当次推理阈值以下未留存的目标，需要重新上传原图识别。

## 真实设备

MQTT 的权威配置为 `backend/config/mqtt.yaml`，已写入用户提供的番茄种植架 V1.1 协议。前端不再提供 MQTT 配置入口。服务地址、账号密码留待实际填写。

1. 编辑后端 YAML 的连接参数；通过管理员接口 `POST /api/mqtt/test` 测试、`POST /api/mqtt/connect` 建立连接。
2. 编辑目标设备，把数据来源切换为 `mqtt`。
3. 番茄种植架按 V1.1 每 10 秒发布遥测；平台订阅 result/state/telemetry/availability，向 set 发布控制。
4. 番茄架的 AI 模式通过 CMD 08 交给固件执行；平台不套用旧版阈值自动策略。先以手动模式联调。

实际设备、班级、茬次和课程由用户录入；遥测必须来自 MQTT，识别必须来自已配置模型，知识须录入实际来源。

默认仅绑定回环地址。已提供并配置真实 YOLO 权重；硬件联调和模型准确率须分别用实际设备、带标注的番茄照片验收。

## 关闭免密演示

设置 `HYDRO_DEMO=0`，并在运行环境设置 `HYDRO_ADMIN_PASSWORD`、`HYDRO_TEACHER_PASSWORD`、`HYDRO_STUDENT_PASSWORD`、`HYDRO_PARENT_PASSWORD`。密码不放进前端。此版本为本机教学原型的角色账户，不是多学校、多学生生产身份系统；公网部署需接入正式用户认证、班级数据授权和 HTTPS。

## 测试

```sh
.venv/bin/pip install -r backend/requirements-test.txt
.venv/bin/python -m pytest tests/test_api.py tests/test_mqtt_live.py tests/test_neo4j_live.py tests/test_tomato_protocol.py -q
npm run build
```

MQTT 测试创建随机本机端口的 AMQTT Broker，用模拟设备验证真实 TCP MQTT 的接收和回执；不访问外部 Broker。
