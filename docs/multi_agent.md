多人群聊后端基础（准备文档）

请参考以下接口：
- POST /api/group-conversations
- GET /api/group-conversations/{gid}
- POST /api/group-conversations/{gid}/assistant/stream （SSE）

Provider 配置：DATA_DIR/providers.json；列表接口：GET /api/providers。

事件流：
- status.start
- agent.message.created / agent.message.delta / agent.message.completed
- done

