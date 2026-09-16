# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

User preference: 物联网页为所有已登录账户提供完整 MQTT 配置，包括服务地址、端口、Client ID、账号、密码、TLS、QoS、Keepalive、自动连接、绑定设备和全部协议主题，并提供保存、测试连接、连接、断开操作。入口固定显示在物联网页标题区；编辑草稿不得被状态轮询覆盖。配置必须写入后端 YAML；密码只允许替换且不得明文回显，连接状态保持只读展示。

User requirement: 知识库与知识图谱必须使用真实 Neo4j 持久化及 Cypher 查询。禁止内存/SQLite 图谱回退；离线明确返回 503，保留源数据真实性标记。

User requirement: MQTT 以 backend/config/mqtt.yaml 为权威配置，遵循用户最新提供的 ESP32-S3 r19 固件与 V1.1 消息格式。固定根主题 tomato_hnsw0001，所有收发使用 QoS 0，遥测每 15 秒，EC μS/cm、水位 cm；CMD 03 为固件雾化泵，不添加独立风扇/水雾命令，不把设备 AI 模式变成平台阈值模式。

User requirement: 页面仅使用真实数据。默认 HYDRO_REAL_ONLY=1，禁止示例初始化、模拟遥测及演示识别；历史演示数据隔离保留，不改标签冒充真实数据。

User decision: 用户确认 best(3).pt 是番茄模型（虽然训练实验名为 strawberry_exp），并授权部署。使用其真实类别 0=Unripe/未成熟、1=Half-ripe/半成熟、2=Ripe/成熟；部署权重位于 backend/models/tomato-v1.pt。实验名不作为作物来源判定，模型识别准确性须用真实番茄照片验证。

User preference: 番茄识别页面提供可调整的最低置信度，默认值为 65%。低于阈值的目标不显示，标注框、结果列表和数量统计保持一致；新推理使用所选阈值，历史原始识别存档保持可追溯。

User requirement: 修复拍照时提示未登录的问题，登录失效时保留已拍照片以便重试。远程热点摄像头按用户提供的 01_WiFi_SCAN.zip 固件接入：ESP32-P4 + UVC，HTTP GET /image，默认 AP IP 192.168.4.1，约每 20 秒发布最新照片。固件实际采集时间未知，不把获取时间冒充采集时间；设备未返回照片时明确报错，不使用替代画面。

User decision: 本机原生 EMQX 适配硬件端，硬件代码和设备配置保持不动。用户确认硬件连接 NANANA，MQTT 服务器为 192.168.31.217:1883。Docker 后端默认通过 host.docker.internal:1883 访问本机 EMQX；网页允许所有已登录账户修改完整 MQTT 配置。密码不得由 API 明文回显；公开 Git 仓库仅保存 YAML 中的环境变量引用，不上传硬件源文件中包含的凭据。

User decision (2026-09-15): 用户授权本次设备网络配置修复作为上述“设备配置保持不动”的例外：将设备保存的 Wi-Fi 从 admin 改为 NANANA，Wi-Fi 密码使用用户已提供的本机值，MQTT 地址从 192.168.124.10 改为 192.168.31.217；允许保存后自动重启。保留固件程序、控制参数及 MQTT 账号密码。现场存在同名 A-tomato 热点，写入前必须核对设备身份与原配置。

User requirement: 系统加入番茄生长周期科普，使用用户提供的发芽期、幼苗期、开花坐果期、结果期四张配图；桌面与手机均提供入口，图片注明用户提供的科普素材，阶段说明不代表当前设备的实测生长状态。

User decision (2026-09-15, 比赛现场): 用户要求简化限制、保持比赛稳定：EMQX 内置授权对 `admin` 与 `tomatosmart-platform` 统一改为白名单 `tomato_hnsw0001/#` 订阅与发布全部允许，其余主题拒绝；修改前快照保存在忽略提交的 `data/emqx-diagnosis/acl-before-competition-whitelist.json`。设备保存的 MQTT 地址更新为 `10.186.117.102`（Wi-Fi 仍为 `NANANA`，账号密码不变，写入前已核对设备页面身份与原配置）；EMQX 节点名保持 `emqx@127.0.0.1`，局域网客户端经 `0.0.0.0:1883` 访问。

User decision (2026-09-15, 比赛现场): 用户要求 MQTT 认证不拦截未填写账号密码的客户端（比赛现场有多台电脑/多设备接入，免去逐个配置账号）。EMQX 内置认证器（`password_based`、`scram`）已禁用，允许匿名连接，账号密码不再校验；授权对全部客户端（含匿名）统一为全局白名单 `tomato_hnsw0001/#` 订阅与发布、其余主题拒绝。修改前的认证与授权快照保存在忽略提交的 `data/emqx-diagnosis/auth-before-anonymous.json`。

User decision (2026-09-15): 成熟度页面“远程摄像头”的默认地址改为 `http://10.186.117.102:500/snapshot`，由后端 `backend/config/camera.yaml` 权威提供（不再硬编码旧固件的 `/image`）。页面修改“摄像头地址”后点击“连接摄像头”立即请求新地址；“保存为默认地址”把当前地址写回后端 YAML，其他账号、刷新页面与后端重启后同样生效。只填 `IP:端口` 时自动补上已配置的路径。地址变更仍需 HTTP/HTTPS IPv4 校验，仅非家长角色可保存；获取时间不得冒充采集时间，摄像头无照片时明确报错。

User clarification (2026-09-15): 摄像头地址以用户当前输入为准。普通连接和刷新仅 GET 该地址，不自动改用其他路径；仅主动“检测连接”可探测其他照片路径。允许连接期间编辑地址，编辑后取消旧请求和旧预览，再点击连接请求新地址。摄像头服务可以位于与网页相同的主机，不仅凭 IP 相同提示地址错误。

Implementation (2026-09-15): 知识问答已接入本机 Ollama `qwen3.5:4b`。知识与关系仍以真实 Neo4j 为唯一来源；模型不可用明确返回 503，无来源不生成诊断。资料修订、收藏和探究记录保留原文、模型回答及当次采样快照。项目文档导入项标记为待核验，不冒充专家农艺知识。

User requirement (2026-09-15): 补齐 ESP32-P4 向电脑 HTTP 推送照片的接收服务，继续使用现有 web/api/neo4j 三个容器。web 额外发布 500 端口，仅代理 /snapshot；后端 POST /snapshot 接收照片、GET /snapshot 提供最新原图。兼容 JPEG/PNG 原始数据及单文件 multipart，最新照片持久化到现有数据卷，不自动写入识别档案；服务接收时间不代表设备采集时间。前端默认 URL 和修改地址的行为保持不变。

User decision (2026-09-15，最新 IP 同步): 用户确认本机局域网地址已改为 `192.168.31.217`，要求同步全部当前连接配置，替代此前比赛现场的 `10.186.117.102`。MQTT 服务地址为 `192.168.31.217:1883`，摄像头默认及照片推送目标为 `http://192.168.31.217:500/snapshot`。EMQX 节点名保持 `emqx@127.0.0.1`，监听保持 `0.0.0.0:1883`；保留匿名连接与 `tomato_hnsw0001/#` 全局白名单。设备端只更新可核实设备的持久化服务器地址，保留固件、账号、密码和控制参数。历史诊断与存档保留原地址以便追溯。

User clarification (2026-09-15，IP 同步范围): 用户随后明确本次只需将配置统一为 `192.168.31.217`，无需继续排查实际网络或切换 Wi-Fi；按指定地址完成软件配置。

User decision (2026-09-16，知识图谱架构更新): 用户明确要求移除项目内 Docker 与 Neo4j 运行依赖，并以 `外部参考目录/03-药品与知识图谱` 的轻量邻接表思路为技术参考，改用纯 Python 内存图谱作为正式实现；教师新增与编辑资料使用本地 JSON 持久化。此前“Neo4j 为唯一来源、离线 503、禁止内存回退”和“三容器部署”要求由本决定替代。图谱内容仅使用番茄种植、劳动教育与健康教育主题；健康教育整理内容不得冒充教材原文或已核验专业结论，继续保留来源与真实性标记。

User preference (2026-09-16，图谱交互): 知识图谱必须表现为观察窗下可无限漫游的“海面”，不能把全部节点压缩堆进固定小窗口。节点使用力导向浮动与碰撞避让，可单独拖动；画布可平移、缩放、复位和聚焦，观察窗移动后仍能查看完整图谱。文字和节点要分层清晰，优先避免标签、图片或关系文字互相遮挡；桌面提供宽阔图谱观察区，移动端保持可用的拖拽与缩放体验。

User decision (2026-09-16，整站视觉): 项目界面以 `外部参考目录/UI修改参考图片/页面UI.png` 为布局与视觉来源，采用深绿色教育平台顶栏、左侧课堂功能导航、浅色内容底、紧凑圆角数据卡片和绿色/蓝色状态体系；`UI插入图片1.png` 用作番茄课堂横幅，`UI插入图片2.png` 用作侧栏校园插画。功能与真实数据规则保持不变，桌面和移动端均延续该视觉语言。
