# 角色卡后端对接与新增流程指南

本指南面向前端与后端同事，说明：如何对接“角色卡”接口、如何发起基于角色的 SSE 聊天，以及纯人工新增一个新角色的完整流程。后端已移除本地模拟逻辑，必须配置真实 LLM（OpenAI 兼容接口）方可使用。

## 一、系统概览

- 角色卡来源：`backend/prompts/*.json`（一角一卡，数据化配置）。
- 角色卡接口：`/api/role-cards`（列表、详情），供前端展示与选择角色。
- 会话与消息：创建会话时自动将角色 persona 写入首条 `system` 消息；消息保存在 `data/conversations/*.json`。
- 聊天协议：SSE（服务端将 LLM 非流式回复切块成事件流）。
- LLM：通过 `backend/core/llm/client.py` 调用 OpenAI 兼容 `/v1/chat/completions`。

目录要点：

- `backend/core/roles/registry.py`：角色卡加载器（从 `backend/prompts` 读取）。
- `backend/api/roles.py`：角色卡 API（列表/详情）。
- `backend/api/role_chat.py`：基于角色的会话创建与 SSE 聊天。
- `backend/core/llm/streams.py`：`OpenAICompatProvider`（调用 LLM，服务端切块输出）。
- `backend/core/conversations/repository.py`：JSON 文件存储会话与消息。
- `backend/core/settings.py`：读取环境变量，强制检查 LLM 配置。
- `backend/prompts/*.json`：角色卡配置文件（人工新增角色就在这里）。

## 二、环境配置

在项目根目录 `.env`（或环境变量）中配置：

- `LLM_BASE_URL`：OpenAI 兼容网关地址（如 `http://localhost:8001`）。
- `LLM_MODEL`：模型名（如 `gpt-4o-mini`、`llama3`、`qwen2` 等，视网关支持）。
- `LLM_API_KEY`：若网关需要认证，填入即可；否则可留空。
- `DATA_DIR`（可选）：对话存储目录，默认 `./data`。
- `ALLOW_ORIGINS`（可选）：CORS 白名单，逗号分隔。

启动：`uvicorn backend.main:app --reload`

## 三、API 契约（对前端）

1) 列出角色卡

- `GET /api/role-cards`
- 响应示例：
  ```json
  [
    {"id":"Marx","slug":"Marx","name":"马克思","locales":["zh-CN"],"tags":[]},
    {"id":"Engels","slug":"Engels","name":"恩格斯","locales":["zh-CN"],"tags":[]}
  ]
  ```

2) 角色卡详情（可选）

- `GET /api/role-cards/{slug}`
- 响应示例：
  ```json
  {"id":"Marx","slug":"Marx","name":"马克思","styleHints":"...","greeting":"...","locales":["zh-CN"]}
  ```

3) 创建角色会话

- `POST /api/role-conversations`
- 请求体：`{ "roleCardId": "Marx", "title": "与马克思的对话" }`
- 响应：`{ conversationId, title, roleCardId, roleCardName, createdAt }`

4) 角色聊天（SSE）

- `POST /api/role-conversations/{conversationId}/assistant/stream`
- 请求体：`{ "roleCardId": "Marx", "text": "如何理解异化劳动？", "temperature": 0.7, "max_tokens": 300 }`
- 响应：`text/event-stream`（SSE 事件顺序）
  - `status.start`：`{ conversationId, roleCardId, model: "openai-compatible", promptVersion }`
  - `message.created`：`{ messageId, state: "generating" }`
  - 多次 `message.delta`：`{ messageId, delta }`
  - `message.completed`：`{ messageId, usage, finishReason }`
  - `done`
- 错误：`error`（`{ code, message }`），随后关闭连接。

5) 获取会话历史（可选）

- `GET /api/conversations/{conversationId}/messages`
- 返回：该会话的全部 `system/user/assistant` 消息列表。

前端建议：使用 `EventSource` 监听 `message.delta` 逐字渲染；`message.completed` 固定消息，展示 `usage`/`finishReason`；`done` 结束本次流。

## 四、纯人工新增角色流程

目标：在前端“角色列表”出现新角色，并可基于该角色发起会话与聊天。

1) 新增角色文件

- 在 `backend/prompts/` 下创建 `<Slug>.json`，`<Slug>` 即角色 id（建议英文无空格，如 `Socrates.json`）。

2) 填写字段

- 必填：
  - `name`：展示名（如“苏格拉底”）。
  - `prompt`：system 提示词，明确身份、方法、主题范围、拒答策略（如敏感领域仅给一般原则并提示求助专业人士）。
- 可选：
  - `style`：风格提示（语气、结构、措辞习惯）。
  - `greeting`：建议的首句招呼语（前端可直接展示）。
  - `locales`：可用语言列表（如 `["zh-CN"]`）。

3) 示例（可直接拷贝修改）

```json
{
  "name": "苏格拉底",
  "prompt": "你是苏格拉底，以问答法澄清概念与前提，鼓励自我反思。涉及医学/法律建议时，仅提供一般原则并提示寻求专业帮助。",
  "style": "语气温和、以问题引导、逐步澄清定义与矛盾。",
  "greeting": "我们先从一个定义开始：你如何理解‘善’？",
  "locales": ["zh-CN"]
}
```

4) 自测与联调

- 列表：`GET /api/role-cards` 应出现新 `slug/name`。
- 详情：`GET /api/role-cards/<Slug>` 应返回 `styleHints/greeting/locales`。
- 创建会话：`POST /api/role-conversations`，body `{ "roleCardId": "<Slug>" }`，返回 `conversationId`。
- SSE 聊天：`POST /api/role-conversations/{cid}/assistant/stream`，body `{ "roleCardId": "<Slug>", "text": "你的问题..." }`。
- 历史：`GET /api/conversations/{cid}/messages` 回放 system/user/assistant。

5) 质量清单（建议）

- Persona 清晰：身份/方法/范围/边界一段话内说清楚。
- 风格稳定：`style` 简洁明确（语气、结构、引用习惯）。
- 安全边界：敏感领域给出拒答或降级策略。
- 语言一致：确认 `locales` 与 prompt 语言一致。

## 五、联调流程（前端）

1) 角色选择页：`GET /api/role-cards` → 展示卡片（使用 `slug` 作为 id）。
2) 进入角色：`POST /api/role-conversations` → 返回 `conversationId`。
3) 开始聊天：`POST /api/role-conversations/{conversationId}/assistant/stream`（SSE）。
4) 渲染事件：
   - `status.start` → 显示“正在思考”。
   - `message.delta` → 逐字追加文本。
   - `message.completed` → 固定消息、展示 `usage/finishReason`。
   - `done` → 结束本轮。
5) （可选）历史：`GET /api/conversations/{conversationId}/messages` 回放。

## 六、常见问题

- 500/配置错误：确认 `.env` 中 `LLM_BASE_URL`、`LLM_MODEL`（和 `LLM_API_KEY`）已设置且网关可访问。
- 404/角色不存在：检查文件名 `<Slug>.json` 与请求中的 `roleCardId` 是否一致；JSON 至少要有 `name` 和 `prompt`。
- SSE 无显示：确认使用 `EventSource` 或正确处理 `text/event-stream`；检查浏览器/代理是否截断 POST SSE。

## 七、扩展与规划（预留）

- RAG：在请求侧检索片段，注入在 system 之后、user 之前的上下文；统一 `citation` 输出结构。
- 多人群聊：扩展为多 Agent 并发发言（事件名可升级为 `agent.message.delta`），或引入主持人总结。
- 角色卡版本化：将 prompts 迁移到数据库/配置中心，支持灰度发布与 A/B 测试。

—— 完 ——
