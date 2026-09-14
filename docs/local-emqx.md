# 本机 EMQX 与 r19 固件

硬件保持原样：连接用户指定的 Wi-Fi `NANANA`，MQTT 服务器为 `192.168.31.217:1883`。本机原生 EMQX 5.2.0 位于 `C:\emqx\emqx-5.2.0`，Dashboard 为 `http://127.0.0.1:18083`。Docker 后端使用 `host.docker.internal:1883`，前端通过同源 FastAPI 调用，不直接连接 MQTT WebSocket。

## 认证与方向

固件使用 MQTT 3.1.1 普通用户名密码，需要 EMQX 的 `password_based:built_in_database` 认证。此认证已放在认证链首位，原有 SCRAM 配置保留；未改动已有 Dashboard 管理员密码。设备账号取自用户提供的硬件文件，平台使用独立账号 `tomatosmart-platform`，两者均不是超级用户。

内置数据库授权优先匹配这两个账号：设备仅订阅 `tomato_hnsw0001/set`，发布 `telemetry`、`state`、`availability`、`result`；平台方向相反。全部 QoS 0，控制和结果不保留，状态与在线状态允许保留。账号的其他主题操作被拒绝；原有其他授权源保留。

Windows 入站规则 `TomatoSmart-MQTT-1883` 允许本地子网访问 TCP 1883。连接本机 MQTT 不等于硬件已在线：硬件必须能经 Wi-Fi 路由到本机，页面仍等待真实 telemetry 和 state。

## 配置复用

`scripts/configure-local-emqx.ps1 -HardwareSource <本机硬件源文件路径>` 解析固件默认 MQTT 凭据，配置本机认证、账号、主题权限和防火墙。需要 PowerShell 7 与管理员权限。脚本不执行或修改硬件代码，不切换网络，不输出密码；使用临时 Dashboard 账号，完成后删除。EMQX 原配置备份在忽略提交的 `data/emqx-backups/`。

平台随机密码保存在忽略提交的 `.env`，`backend/config/mqtt.yaml` 仅保存 `${TOMATO_MQTT_PASSWORD}` 引用。修改 `.env` 后需重新创建 API 容器，使环境变量更新；平台代码不会把解析出的密码写回 YAML。迁移时按 `.env.example` 准备本机配置并重新配置 EMQX，不能只克隆代码就使用原机账号。

## 验证边界

本机 EMQX 认证和订阅验证使用临时唯一 Client ID，既不冒充 `tomato-esp32s3-*` 硬件，也不发布任何控制、遥测或状态。网页九种命令测试运行在独立容器、独立 Broker 和临时业务数据库中。生产页面不注入测试读数。

若扫描不到 `NANANA`，先恢复该路由器或热点。电脑连接后还必须确认 `192.168.31.217` 实际指向这台运行 EMQX 的电脑；电脑拿到其他地址时，应在该网络内处理地址分配或路由，不能仅修改平台的主题来解决网络不通。
