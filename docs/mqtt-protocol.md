# 番茄种植架 MQTT V1.1 后端配置

以用户最新提供的 ESP32-S3 固件 `2026-09-03-esp32s3-stable-mqtt-r19` 为准，消息格式沿用 V1.1。硬件代码不作修改。原始文件包含凭据，不提交到公开仓库；文件 SHA-256 为 `c5075abe3c7f869655fe23fadab55c815355c4228b04e6339f67d7b71ebe2b48`。

配置文件：`backend/config/mqtt.yaml`。后端直接读取此 YAML；前端无 MQTT 配置表单或入口，不再从 SQLite settings 覆盖 MQTT 配置。连接操作使用管理员后端接口 `/api/mqtt/test`、`/api/mqtt/connect` 和 `/api/mqtt/disconnect`（POST）。可通过 `HYDRO_MQTT_CONFIG` 指定其他 YAML 路径。

## 本机连接

本机原生 EMQX 监听 1883；Docker 后端通过 `host.docker.internal:1883` 连接，硬件保留 `192.168.31.217:1883`。两者必须到达同一个 Broker。非 Docker Python 部署应把 YAML 的 `mqtt.host` 改为 `127.0.0.1`。Keep Alive 120 秒、TLS 关闭，与固件的 MQTT 3.1.1 TCP 客户端一致。

后端使用独立的 `tomatosmart-platform` 账号和 Client ID，避免与 ESP32 的 `tomato-esp32s3-<芯片唯一ID>` 冲突。YAML 的密码引用 `${TOMATO_MQTT_PASSWORD}` 由后端从本机环境解析；实际密码仅在忽略提交的 `.env` 中。配置保存保留引用，API 不返回实际密码。EMQX 用户与主题权限配置见 [本机 EMQX 接入](local-emqx.md)。

`mqtt.device_id: HY-001` 是本系统设备与固定根主题的绑定，可修改为设备管理中的实际编号。协议报文不含 device_id，不能继续按旧示例假定消息体有设备编号。

## 主题

|方向|配置键|主题|QoS|Retain|
|---|---|---|---|---|
|平台发布|command_topic|tomato_hnsw0001/set|0|false|
|平台订阅|ack_topic|tomato_hnsw0001/result|0|false|
|平台订阅|state_topic|tomato_hnsw0001/state|0|true|
|平台订阅|telemetry_topic|tomato_hnsw0001/telemetry|0|false|
|平台订阅|availability_topic|tomato_hnsw0001/availability|0|true|

固件订阅 set，平台向 set 发布。r19 明确要求所有方向使用 QoS 0。`autoconnect: true` 使后端启动时自动连接、断线后自动重连；收到 SUBACK 后才显示订阅完成。启动和重连只订阅数据，不自动下发控制。

## 消息适配

- 控制请求严格使用 `request_id`、两位字符串 `cmd` 和 `data`。YAML 包含 01–09 全部命令、范围、手动限制、五个补光模式、休息时间、错误码与固件 RS485 规则。
- `POST /api/devices/{id}/protocol-commands` 可发送全部九种命令。例如请求体 `{"cmd":"05","data":{"value":3},"confirmed":true}`，后端生成 request_id。必须先连接 MQTT；只允许绑定设备。
- 雾化泵/补光总开关对应 CMD 03/04，模式切换对应 CMD 08，后者仅教师或管理员可用。页面另提供红蓝亮度、补光阶段、泵间隔/时长和休息时段设置，所有操作须确认。固件没有独立风扇/水雾命令；AI 模式由固件运行，直接开关和亮度调节仅在手动模式可用。
- result 按 request_id 与 cmd 关联。只有 success=true 且 applied=true 才记录设备确认；实际状态由 state 同步，不能收到 result 就自行翻转开关。result 不等于独立物理传感器的动作确认。
- state 保存红蓝亮度、水泵、总灯、种植模式、工作时长与休息计划；availability 保存 online/offline。
- telemetry 每 15 秒上报。七个字段按 YAML 映射；EC 原值已由固件除以 20.15，后端仅乘 0.001 转为界面的 mS/cm；水位保留 cm，不臆造水箱高度换成百分比。采样和快照保留单位，历史聚合不混合不同来源或单位。保留的 telemetry 不当作新的实测数据。
- 45 秒采样过期、30 秒结果等待是平台策略。平台断开、设备离线或没有新鲜遥测时禁用控制；结果超时不擅自更改固件 AI 模式。

协议文件中红蓝 485 帧各发送 3 次、帧间隔至少 300ms，由 ESP32 负责；平台不将 MQTT 请求重复三次。

## 验证范围

`tests/verify_firmware_contract.py` 静态对照用户固件的主题、QoS、上报间隔、七个字段与九种命令范围，不执行固件。隔离 AMQTT 与浏览器测试覆盖九种命令、QoS 0、非保留控制、结果/状态、权限与离线禁用。`tests/verify_local_emqx.py` 仅验证真实本机 EMQX 的认证和订阅，不向硬件发送指令或测试遥测。真实硬件联通必须另看实际设备客户端及实时遥测，不以隔离测试代替。

旧平台协议仍可显式选择 `legacy` 用于旧设备和回归测试；当前默认协议为 `tomato_v1_1`，不会自动猜测两种报文格式。
