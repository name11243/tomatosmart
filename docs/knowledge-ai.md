# 本地 AI 与纯 Python 图谱查询

知识原文和关系由 `backend/knowledge_graph.py` 的内存邻接图管理。随项目提供的资料位于 `backend/knowledge_content.py`；网页新增和编辑内容持久化到 `HYDRO_KNOWLEDGE_FILE`，默认是 `backend/real-data/knowledge_graph.json`。问答快照、收藏、探究记录和日志仍存入业务 SQLite。

本机 Ollama 地址由 `HYDRO_OLLAMA_URL` 配置，默认 `http://127.0.0.1:11434`；模型默认 `qwen3.5:4b`。页面可刷新模型状态，不调用云端服务，也不自动下载模型。Ollama 不可用时，纯 Python 图谱检索仍可正常使用。

查询流程：

1. Python 图谱按标题、问题、标签、中文短语和常见同义表达检索，最多返回 6 条来源，再从邻接表提取对应子图。
2. 本地 AI 只接收来源原文、真实性标记和提问时的设备采样上下文；空值与过期采样保持原样。
3. Ollama 返回 JSON，后端校验结构以及每个引用编号，模型不能引用上下文以外的资料。
4. 无来源时不生成农艺诊断；模型不可用、超时或引用无效时返回明确错误，用户可切换到“仅查询知识资料”。
5. 收藏与探究记录使用回答 ID 保存当次模型、原文、图谱与环境快照。编辑资料保留历史版本并恢复为待核验。

接口：`GET /api/ai/status`、`GET /api/knowledge/status`、`GET /api/knowledge/graph?q=…`、`POST /api/ask`、`POST /api/knowledge`、`PUT /api/knowledge/{id}`。`/api/ask` 的模式为 `local_ai` 或 `python_graph`；设备可留空。资料编辑仅限教师和管理员。

内置资料包含用户提供的番茄四阶段科普、番茄观察与水培数据边界，以及个人卫生、水电安全、实验防护、食品卫生、眼健康和劳动工具安全等健康教育主题。健康教育条目是课程主题整理而非教材原文，全部保留待核验标记。

软件验证覆盖 JSON 重启读回、图谱遍历、资料编辑、无来源处理、错误引用拒绝、跨账户保存限制、旧茬次隔离和 Ollama 问答。结构与引用校验不能保证模型理解完全正确，页面始终提供来源原文与真实性标记。
