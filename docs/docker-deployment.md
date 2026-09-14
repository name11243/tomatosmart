# 本机 Docker 部署

部署目录：`D:\xxxxxxxxxxxxxxxx\tomatosmart`。执行 `docker compose up -d --build` 启动前端、FastAPI 和 Neo4j。

网页：http://127.0.0.1:5176/#knowledge ，同时兼容 http://127.0.0.1:5173/ 。API：http://127.0.0.1:8016/docs 。Neo4j 浏览器：http://127.0.0.1:7476/ 。

默认保留源项目本机免密角色登录，`HYDRO_REAL_ONLY=1`。没有预置示例数据，未配置模型时不能进行真实识别。MQTT 继续使用 `backend/config/mqtt.yaml`，不会自动向设备下发命令。

MQTT Broker 使用 Windows 原生 EMQX，API 容器经 `host.docker.internal:1883` 自动连接并订阅四个固定上报主题。固件保持 `192.168.31.217:1883`；电脑须处于可接收该地址访问的网络。认证、主题方向和复用脚本见 [本机 EMQX 接入](local-emqx.md)。

番茄成熟度模型使用 `backend/models/tomato-v1.pt`（用户提供的 `best(3).pt`），目录只读挂载到 API 容器。镜像固定使用 Ultralytics 8.3.223、PyTorch 2.9.0 CPU 和 torchvision 0.24.0 CPU，无需显卡。权重未打包进镜像，迁移部署时须同时复制 `backend/models/`。类别和权重校验值见同目录 JSON 清单。

识别入口：http://127.0.0.1:5176/#maturity 。`GET /api/health` 返回 `model.ready`、类别和 SHA-256；未加载成功时真实识别返回 503。模型只在后端配置。上传前需在设备管理登记实际设备和茬次，识别结果与原图、标注图、权重信息一并留存。测试使用隔离临时数据库，不向真实档案加入测试图片或识别记录。

应用数据在 `data/app`，图谱在 `data/neo4j`，日志在 `data/neo4j-logs`，均位于 D 盘。Neo4j 随机密码保存在 `.env`。三个服务均设置 `restart: unless-stopped`。

修改后端后执行 `docker compose up -d --build api`；修改前端后执行 `docker compose up -d --build web`。前端使用构建产物及同源 API 代理。

本机国际软件源下载较慢时，可使用构建参数 `--build-arg DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn --build-arg VISION_PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple`。Debian 仍校验软件包签名；CPU 版 PyTorch 权重运行依赖来自 PyTorch 官方下载源。默认构建参数保留官方 Debian 和 PyPI 地址。

模型部署验证可在一次性容器运行 `docker compose run --rm --no-deps -v ./tests:/app/tests:ro api python tests/verify_vision.py`，覆盖真实 CPU 空白对照图推理、原图与标注图接口、权重来源留存、缺失模型返回 503、演示识别拒绝和类别映射校验。测试使用临时业务数据库，不调用硬件、不向线上档案写入测试数据；空白对照图不用于评估番茄识别准确率。
