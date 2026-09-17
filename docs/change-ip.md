# 一键修改电脑端连接 IP

双击项目根目录的 `一键修改IP.cmd`，输入电脑的新 IPv4 地址，按回车即可。无需安装 Python、PowerShell 模块或使用管理员权限。空白回车取消，不会自动切换 Wi-Fi。

脚本同步 `backend/config/mqtt.yaml` 的 `mqtt.host` 和 `backend/config/camera.yaml` 中 URL 的主机 IP，保留摄像头端口、路径、查询参数，以及 MQTT 端口、账号、密码引用和全部主题。网页从后端读取这些配置，无需重新构建前端。运行中的 Docker API 容器会自动重启并检查挂载配置；照片、数据库、Neo4j、EMQX 认证和主题权限保持原样。

每次实际改动前，两个原始 YAML 文件都会备份到忽略提交的 `data/ip-backups/日期时间-编号/`。写入失败时尝试恢复本次已经写入的文件；备份保留完整原始内容。恢复原值可把备份中的 `mqtt.yaml`、`camera.yaml` 复制回 `backend/config/`，再使用原 IP 运行脚本应用到后端。

本脚本修改的是软件连接的服务器地址，不修改 Windows 网卡地址、ESP32 固件或设备保存的服务器地址。EMQX 现有 `0.0.0.0:1883` 和网页所有接口监听无需随电脑 IP 改写。配置保存成功不代表硬件已在线；Docker 未运行或重启未完成时，会明确显示“已保存但尚未应用”。

命令行可选用法：

```powershell
# 同步并自动应用
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\change-ip.ps1 -NewIP 192.168.31.217
# 只预览，不写入、不重启
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\change-ip.ps1 -NewIP 192.168.31.217 -Preview
# 仅保存 YAML
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\change-ip.ps1 -NewIP 192.168.31.217 -SkipRestart
```

退出码：`0` 为操作成功（包括预览、取消或指定跳过重启）；`1` 为校验或文件写入失败；`2` 为配置已保存、后端尚未应用。历史档案、诊断报告和文档中的当时地址不批量改写。
