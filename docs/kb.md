# 知识库后端基础与流程

本说明描述文本知识输入→结构化文档输出→按角色绑定知识库的基础流程（后端已实现骨架，便于后续接入向量检索/RAG）。

## 数据结构与目录
- 根目录：`DATA_DIR/kb/`
  - `index.json`：知识库索引
  - `bindings.json`：角色与知识库的绑定关系 `{ roleCardId: [kbId, ...] }`
  - `<kbId>/meta.json`：知识库元信息
  - `<kbId>/docs/<docId>.json`：结构化文档，含 outline/summary/chunks

## 接口
- 创建知识库：`POST /api/kb`
  - 请求：`{ "title": "<名称>", "roleCardId": "<可选角色id>" }`
  - 响应：`{ id, title, createdAt, updatedAt, roleCardId }`
- 列表：`GET /api/kb`
- 按角色列出：`GET /api/kb/role/{slug}`
- 文本入库：`POST /api/kb/{kbId}/ingest-text`
  - 请求：`{ "title": "<文档标题>", "text": "<原始文本>" }`
  - 输出：结构化文档 `{ id, title, createdAt, outline[], summary, chunks[] }`
- 文档列表：`GET /api/kb/{kbId}/docs`

## 结构化策略（当前简化版）
- 按空行分段得到段落。
- 简易标题识别：以“第…章/节/部/篇”、数字点/顿号/右括号或 markdown `#` 开头，或长度很短的段落视为标题。
- `outline`：收集前若干标题行；`summary`：取第一段前 200 字。
- `chunks`：数组，`{ index, type: heading|paragraph, text }`。

## 与角色卡的关系
- 创建 KB 时可传 `roleCardId` 自动绑定；也可后续扩展独立绑定接口（当前已存储于 `bindings.json`）。
- 未来在调用 LLM 前，可将相关 KB 的片段检索并插入到 system/developer/knowledge 段落中，实现 RAG。

## 后续计划（预留）
- 文件上传与解析（PDF/Doc/Markdown），统一转文本再结构化。
- 向量化与检索接口（topK、阈值、引用附带来源元数据）。
- 文档/片段版本化与删除、安全审核与去敏处理。

