# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

User preference: 前端不提供 MQTT 配置页面、表单或入口；服务地址、连接参数与订阅主题统一在后端 YAML 中管理。前端仅保留只读连接状态。

User requirement: 知识库与知识图谱必须使用真实 Neo4j 持久化及 Cypher 查询。禁止内存/SQLite 图谱回退；离线明确返回 503，保留源数据真实性标记。

User requirement: MQTT 以 backend/config/mqtt.yaml 为权威配置，遵循用户最新提供的 ESP32-S3 r19 固件与 V1.1 消息格式。固定根主题 tomato_hnsw0001，所有收发使用 QoS 0，遥测每 15 秒，EC μS/cm、水位 cm；CMD 03 为固件雾化泵，不添加独立风扇/水雾命令，不把设备 AI 模式变成平台阈值模式。

User requirement: 页面仅使用真实数据。默认 HYDRO_REAL_ONLY=1，禁止示例初始化、模拟遥测及演示识别；历史演示数据隔离保留，不改标签冒充真实数据。

User decision: 用户确认 best(3).pt 是番茄模型（虽然训练实验名为 strawberry_exp），并授权部署。使用其真实类别 0=Unripe/未成熟、1=Half-ripe/半成熟、2=Ripe/成熟；部署权重位于 backend/models/tomato-v1.pt。实验名不作为作物来源判定，模型识别准确性须用真实番茄照片验证。

User preference: 番茄识别页面提供可调整的最低置信度，默认值为 65%。低于阈值的目标不显示，标注框、结果列表和数量统计保持一致；新推理使用所选阈值，历史原始识别存档保持可追溯。

User requirement: 修复拍照时提示未登录的问题，登录失效时保留已拍照片以便重试。远程热点摄像头按用户提供的 01_WiFi_SCAN.zip 固件接入：ESP32-P4 + UVC，HTTP GET /image，默认 AP IP 192.168.4.1，约每 20 秒发布最新照片。固件实际采集时间未知，不把获取时间冒充采集时间；设备未返回照片时明确报错，不使用替代画面。

User decision: 本机原生 EMQX 适配硬件端，硬件代码和设备配置保持不动。用户确认硬件连接 NANANA，MQTT 服务器为 192.168.31.217:1883。Docker 后端通过 host.docker.internal:1883 访问本机 EMQX；网页只读展示通信状态。密码留在本机，公开 Git 仓库仅保存 YAML 中的环境变量引用，不上传硬件源文件中包含的凭据。
