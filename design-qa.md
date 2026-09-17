# 视觉与交互验收

**Comparison target**
- source visual truth: `docs/design-reference.png`，用户选定的第 3 张原型。
- implementation: `http://127.0.0.1:5176/#knowledge`。
- source pixels: 1487 × 1058；implementation pixels / CSS viewport: 1488 × 1056，DPR 1。
- normalization: 原图整体重采样至 1488 × 1056，仅用于并排比较；未修改保留参考图。
- state: 教师身份、知识问答、番茄叶片发黄、两个来源；当前日期和读数随系统实际时间更新。
- full-view evidence: `docs/qa/comparison-final.png`。
- focused graph + answer evidence: `docs/qa/focused-final.png`。
- final browser capture: `docs/qa/desktop-final.png`。
- mobile evidence: `docs/qa/mobile-final.png`，390 × 844。

**Comparison history**
1. 首轮桌面：主体比例已匹配，图谱缺少节点图标，引用和按钮字号偏小（P2）；移动图谱节点相撞（P2）。
2. 修复：使用 Remix Icon 官方字体渲染图谱图标，引用和主操作字号增大，图谱按画布大小缩放节点。保留 ECharts 交互能力。
3. 第二轮：手机底部八项导航需要横向滚动（P2）；调整为五项常用导航，“我的”提供任务与设备入口。手机关系标签在总览缩放下隐藏，点击节点/连线可查看关系。
4. 最新浏览器截图重新与原图做全屏、图谱和回答面板组合对比。无待处理 P0/P1/P2；不是逐像素截图铺底，所有文字、图谱、表单与按钮均为真实界面。

**Required fidelity surfaces**
- Fonts: 标题自托管 Noto Serif SC 700，正文使用中文系统字体；原图中的图像生成字形无法完全等同系统字体。引用、节点、主操作已调整到可读比例。
- Layout: 66px 深绿顶栏、100px 侧栏、57px 标签栏、左图谱右回答 1.48:1、640px 主工作区；保留底部环境上下文。手机改为纵向内容。
- Colors: 深绿 #20543f、米白 #fcfbf8、绿色按钮和五类语义节点色与参考一致。原图少量不规则阴影未照搬。
- Assets: 叶片和功能图标使用 Remix Icon，图谱由 ECharts 原生 Canvas 绘制，可缩放、漫游和点选。没有用整张参考图代替可操作页面。
- Copy: 标题、导航、问题、原因、来源和操作保持设计结构；知识正文采用本地库里的完整文字，日期和读数为实际当前状态。显示演示数据与未连接状态。

**Browser interactions verified**
- 八个业务页面均可打开，1488px 下 documentWidth 与 viewport 相等，无横向页面溢出。
- 探究记录保存后从列表读回；改变问题为“液位不足”后切换为 KB-003，并能打开来源正文。
- 模拟水泵经过确认弹窗后显示“模拟已执行”，不冒充实机成功。
- MQTT 教师权限提示、管理员字段、保存、连接失败提示；修复定时刷新覆盖编辑表单问题。
- 曲线与知识问答截图保存入档；档案可以提交到课程任务。
- 390px 手机视图 documentWidth=390，固定导航和表单未溢出。
- 最新页面 console error/warn: 0。接口失败分支的预期错误提示不计为控制台故障。

**Follow-up polish / constraints**
- P3: 图谱节点坐标、连线角度与原图有轻微差别，以可交互关系布局为准；源图部分图标由最接近的图标库图形替代。
- 相机与麦克风实际权限未请求，避免访问用户实体设备；照片上传、识别接口和截图入档已测试。
- 硬件、模型、原生安装包与生产身份体系边界见 `docs/requirements-coverage.md`。

final result: passed

## 2026-09-14 识别统计补充验证

浏览器通过上传按钮上传带 DEMO ONLY 字样的测试图片，明确开启演示识别。页面显示果实数量 2、未成熟 0、半成熟 1、成熟 1、平均置信度 90.0%，原图与标注图显示正常。证据：docs/qa/recognition-summary.png。API 测试核对识别读回、档案关联和 JSON 导出统计一致；空检测平均置信度为 null，不伪装为零置信度。切换设备或筛选条件后清除已选记录，避免显示旧设备详情。

## 2026-09-14 日志证据补充验证

通过页面查询后进入 AI 日志，展开「查看当时的关联证据」，核对七项采样、采集时间、演示来源、茬次与 KB-001/KB-002 原文。截图 docs/qa/log-evidence.png。13 项 API/MQTT 测试通过，包含设备归属、环境快照不被新采样覆盖、全局事件不伪造设备关联、演示与实机来源隔离。

## MQTT 设置页

按用户要求新增 #settings，将原 MQTT 抽屉改为独立设置页；提供服务地址、端口、Client ID、用户名/密码、TLS、QoS、Keepalive 与三类主题。浏览器填写测试地址和遥测主题，保存后离开再进入，值正确回显；后端读回一致，测试后恢复原始未配置地址。桌面截图 docs/qa/mqtt-settings.png；390px 手机视图文档宽度 390px，无水平溢出。生产构建通过。

## Neo4j 知识图谱界面更新

知识关系继续由真实 Neo4j 持久化和 Cypher 查询提供。图谱观察窗支持节点拖动、画布平移、缩放、复位和聚焦，并扩大桌面与手机端的探索空间；资料来源和待核验标记继续保留，不冒充设备实测或已核验专业结论。

## 用户番茄架协议 V1.1 与 YAML

MQTT 配置改为 backend/config/mqtt.yaml。页面实际读回通信协议 V1.1、1883、120 秒和 tomato_hnsw0001 的 set/result/state/telemetry/availability 主题；模拟数据与真实协议保持区分。17 项测试通过，包含本机 TCP Broker 的 V1.1 遥测、单位换算、状态及控制结果关联。
