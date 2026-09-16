# 本机 EMQX 与 r19 固件

硬件侧连接 Wi-Fi `NANANA`（Windows 网络配置文件名显示为 `NANANA 2`），MQTT 服务器为 `192.168.31.217:1883`。本机原生 EMQX 5.2.0 位于 `C:\emqx\emqx-5.2.0`，节点名保持 `emqx@127.0.0.1`（改绑局域网地址会与已有 mnesia 数据不匹配、启动失败），普通 MQTT 监听 `0.0.0.0:1883`，Dashboard 为 `http://127.0.0.1:18083`（局域网 `http://192.168.31.217:18083`）。原生 Python 后端经 `192.168.31.217:1883` 连接同一个 Broker，前端通过 FastAPI 调用，不直接连接 MQTT WebSocket。网页监听所有本机接口，局域网入口为 `http://192.168.31.217:5176/`，本机也可使用 `http://127.0.0.1:5176/`。

## 认证与方向

固件使用 MQTT 3.1.1 普通用户名密码。认证数据库保留 `admin` 与 `tomatosmart-platform` 两个非超级用户账号，设备与 Python 后端当前都使用 `admin`；未改动已有 Dashboard 管理员密码。

用户要求比赛期间简化限制、保持稳定、不拦截未填账号密码的客户端：EMQX 内置认证器（`password_based:built_in_database`、`scram:built_in_database`）已禁用，允许匿名连接，账号密码不再校验；授权对全部客户端（含匿名）统一为全局白名单 `tomato_hnsw0001/#`（订阅与发布全部允许），其余主题拒绝。此前细分的设备/平台方向规则已被该白名单取代，修改前的认证与授权快照保存在忽略提交的 `data/emqx-diagnosis/auth-before-anonymous.json` 与 `acl-before-competition-whitelist.json`。全部 QoS 0，控制和结果不保留，状态与在线状态允许保留；原有其他授权源保留。

Windows 入站规则 `TomatoSmart-MQTT-1883` 允许本地子网访问 TCP 1883。连接本机 MQTT 不等于硬件已在线：硬件必须能经 Wi-Fi 路由到本机，页面仍等待真实 telemetry 和 state。

## 配置复用

`scripts/configure-local-emqx.ps1 -HardwareSource <本机硬件源文件路径>` 解析固件默认 MQTT 凭据，配置本机认证、账号、主题权限和防火墙。需要 PowerShell 7 与管理员权限。脚本不执行或修改硬件代码，不切换网络，不输出密码；使用临时 Dashboard 账号，完成后删除。EMQX 原配置备份在忽略提交的 `data/emqx-backups/`。

设备与平台共用的 MQTT 密码保存在忽略提交的 `.env`，`backend/config/mqtt.yaml` 仅保存 `${TOMATO_MQTT_PASSWORD}` 引用。任一已登录账户在页面替换密码时，后端更新本机 `.env` 和当前进程环境，YAML 与 API 响应都不会包含明文；直接手工修改 `.env` 后需重启 Python API。迁移时按 `.env.example` 准备本机配置并重新配置 EMQX，不能只克隆代码就使用原机账号。

## 验证边界

本机 EMQX 认证和订阅验证使用临时唯一 Client ID，既不冒充 `tomato-esp32s3-*` 硬件，也不发布任何控制、遥测或状态。网页九种命令测试使用临时 Broker 和临时业务数据库。生产页面不注入测试读数。

若扫描不到 `NANANA`，先恢复该路由器或热点。电脑连接后还必须确认 `192.168.31.217` 实际是这台运行 EMQX 的电脑，并建议在路由器上为该网卡保留固定地址。电脑拿到其他地址时，需同步 `backend/config/mqtt.yaml` 的 `mqtt.host`、`backend/config/camera.yaml` 的 URL 及硬件保存的服务器/推送地址；web 已监听全部接口，无需随 IP 修改端口绑定，不能仅修改平台的主题来解决网络不通。

## Windows 运行信息上报异常

本机 EMQX 5.2.0 的可选运行信息上报模块曾反复调用缺失的 `memsup:get_system_memory_data/0`，导致 `emqx_telemetry` 每约 10 秒崩溃重启。已通过管理 API 将 `telemetry.enable` 持久化为 `false`。这项设置仅停止 EMQX 自身的运行信息上报，不关闭 `tomato_hnsw0001/telemetry` 等 MQTT 业务主题；无需修改节点名或重置数据目录。
