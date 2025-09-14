# Philohumanities-AI · API 规范（v0）

目标：极薄后端代理开源大模型（OpenAI 兼容端点），会话与消息历史持久化在仓库内 `data/` 目录（JSON 文件）。

基础
- 基础路径：同源部署，静态与 API 共域。
- 响应格式：`application/json; charset=utf-8`
- 身份认证：无（私域使用）。

数据模型（摘要）
- Message: `{ role: 'system'|'user'|'assistant', content: string, ts: ISO8601 }`
- ConversationMeta: `{ id: string, title: string, createdAt: ISO8601, updatedAt: ISO8601 }`
- Conversation: `{ id, title, createdAt, updatedAt, messages: Message[] }`

路由
1) 创建会话
   - POST `/api/conversations`
   - body: `{ "title"?: string, "system"?: string }`
   - 200: ConversationMeta

2) 列出会话
   - GET `/api/conversations`
   - 200: ConversationMeta[]（按 `updatedAt` 倒序）

3) 获取会话消息
   - GET `/api/conversations/{id}/messages`
   - 200: `{ id: string, messages: Message[] }`

4) 重命名会话
   - PATCH `/api/conversations/{id}`
   - body: `{ "title": string }`
   - 200: ConversationMeta

5) 删除会话
   - DELETE `/api/conversations/{id}`
   - 204: 无内容

6) 发送消息（非流式）
   - POST `/api/conversations/{id}/messages`
   - body: `{ "content": string, "model"?: string, "temperature"?: number, "max_tokens"?: number }`
   - 服务端：先将 user 写入，再代理 LLM，写入 assistant，更新 `updatedAt`。
   - 200: `{ "assistant": Message }`

大模型代理（内部）
- OpenAI 兼容接口 `/v1/chat/completions`
- `Authorization: Bearer <LLM_API_KEY>`（若配置）
- payload: `{ model, messages, temperature?, max_tokens?, stream: false }`

错误
- 400: 参数校验失败；404: 会话不存在；502: LLM 代理失败。

