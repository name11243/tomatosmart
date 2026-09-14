# 番茄种植架 MQTT V1.1 后端配置

依据用户提供的《番茄种植架_MQTT通信协议_V1.1.docx》，对应 tomato_main.py Build r18。

配置文件：`backend/config/mqtt.yaml`。后端直接读取此 YAML；前端无 MQTT 配置表单或入口，不再从 SQLite settings 覆盖 MQTT 配置。连接操作使用管理员后端接口 `/api/mqtt/test`、`/api/mqtt/connect` 和 `/api/mqtt/disconnect`（POST）。可通过 `HYDRO_MQTT_CONFIG` 指定其他 YAML 路径。

## 需要填写

`mqtt.host` 为实际服务主机名或 IP；`mqtt.username`、`mqtt.password` 按 Broker 填写。文档未提供实际值，因此留空。端口 1883、Keep Alive 120 秒、TLS 默认关闭。后端 Client ID 使用独立名称，避免与 ESP32 的 `tomato-esp32s3-<芯片唯一ID>` 冲突。

`mqtt.device_id: HY-001` 是本系统设备与固定根主题的绑定，可修改为设备管理中的实际编号。协议报文不含 device_id，不能继续按旧示例假定消息体有设备编号。

## 主题

|方向|配置键|主题|QoS|Retain|
|---|---|---|---|---|
|平台发布|command_topic|tomato_hnsw0001/set|1（平台策略）|false|
|平台订阅|ack_topic|tomato_hnsw0001/result|1|false|
|平台订阅|state_topic|tomato_hnsw0001/state|1|true|
|平台订阅|telemetry_topic|tomato_hnsw0001/telemetry|0|false|
|平台订阅|availability_topic|tomato_hnsw0001/availability|1|true|

原文的「订阅 set」是从 ESP32 角度描述；平台必须向 set 发布。原文没有指定 set 的 QoS，YAML 明确注明平台采用 QoS 1。后端不会自动连接或自动下发命令。

## 消息适配

- 控制请求严格使用 `request_id`、两位字符串 `cmd` 和 `data`。YAML 包含 01–09 全部命令、范围、手动限制、五个补光模式、休息时间、错误码与固件 RS485 规则。
- `POST /api/devices/{id}/protocol-commands` 可发送全部九种命令。例如请求体 `{"cmd":"05","data":{"value":3},"confirmed":true}`，后端生成 request_id。必须先连接 MQTT；只允许绑定设备。
- 现有水泵/补光开关对应 CMD 03/04，模式切换对应 CMD 08。V1.1 没有通风、水雾命令，后端拒绝自造命令码。固件 AI 模式不由平台的旧阈值自动策略代替。
- result 按 request_id 与 cmd 关联。只有 success=true 且 applied=true 才记录设备确认；实际状态由 state 同步，不能收到 result 就自行翻转开关。result 不等于独立物理传感器的动作确认。
- state 保存红蓝亮度、水泵、总灯、种植模式、工作时长与休息计划；availability 保存 online/offline。
- telemetry 每 10 秒上报。七个字段按 YAML 映射；EC 原值已由固件除以 20.15，后端仅乘 0.001 转为界面的 mS/cm；水位保留 cm，不臆造水箱高度换成百分比。采样和快照保留单位，历史聚合不混合不同来源或单位。
- 35 秒采样过期、30 秒结果等待是平台策略，在 YAML 中单独注明，不冒充固件要求。

协议文件中红蓝 485 帧各发送 3 次、帧间隔至少 300ms，由 ESP32 负责；平台不将 MQTT 请求重复三次。

## 验证范围

使用隔离的本机 AMQTT Broker 测试真实 TCP MQTT。覆盖固定主题、telemetry、保留 state、CMD 03 请求、result 关联、单位换算、配置持久化及参数范围。未连接外部 Broker 或真实硬件。

旧平台协议仍可显式选择 `legacy` 用于旧设备和回归测试；当前默认协议为 `tomato_v1_1`，不会自动猜测两种报文格式。
