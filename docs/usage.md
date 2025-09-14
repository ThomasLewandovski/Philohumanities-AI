后端运行与自测帮助文档（Quick Start）

本文件汇总了后端的本地运行步骤与常用自测命令（仅后端）。可直接复制执行，便于你或前端同事快速联调。

1. 环境准备
- Python 环境（建议 3.10+）
- 创建虚拟环境并安装依赖：
  - python3 -m venv .venv
  - source .venv/bin/activate
  - pip install -r requirements.txt
- 配置环境变量（.env 已示例 DeepSeek）：
  - LLM_BASE_URL=https://api.deepseek.com
  - LLM_MODEL=deepseek-chat
  - LLM_API_KEY=sk-xxxxx
  - DATA_DIR=./data
  - ALLOW_ORIGINS=*
  - 可选：PORT=3000（仅作为参考，uvicorn 仍以命令行参数为准）

2. 启动服务
- 使用端口 3000：
  - uvicorn backend.main:app --reload --port 3000
- 如使用默认 8000：
  - uvicorn backend.main:app --reload

提示：下文所有 URL 默认使用 3000 端口，如用 8000 请替换端口。

3. 基础探活
- 健康检查：
  - curl -s http://localhost:3000/health
- 角色卡列表：
  - curl -s http://localhost:3000/api/role-cards
- Provider 列表（验证多账号加载）：
  - curl -s http://localhost:3000/api/providers | jq

4. 单角色会话（SSE）
1) 创建与马克思的会话：
  - curl -s -X POST http://localhost:3000/api/role-conversations -H 'Content-Type: application/json' -d '{"roleCardId":"Marx","title":"与马克思的对话"}'
  - 记录返回中的 conversationId 为 CID。
2) 发起一次对话回合（SSE 逐字流）：
  - curl -N -X POST http://localhost:3000/api/role-conversations/CID/assistant/stream -H 'Content-Type: application/json' -d '{"roleCardId":"Marx","text":"如何理解异化劳动？","temperature":0.7,"max_tokens":300}'
3) 拉取历史消息：
  - curl -s http://localhost:3000/api/conversations/CID/messages | jq

5. 多人群聊（多账号 / 多模型）
1) 配置多个 Provider 账号（可选）
- 在 data/providers.json 中填写多个账号，示例：
{
  "accounts": [
    {"alias": "deepseek_a", "base_url": "https://api.deepseek.com", "api_key": "sk-...", "default_model": "deepseek-chat", "priority": 20},
    {"alias": "deepseek_b", "base_url": "https://api.deepseek.com", "api_key": "sk-...", "default_model": "deepseek-chat", "priority": 19},
    {"alias": "deepseek_c", "base_url": "https://api.deepseek.com", "api_key": "sk-...", "default_model": "deepseek-chat", "priority": 18}
  ]
}
- 校验加载：curl -s http://localhost:3000/api/providers | jq
- 说明：即使存在 providers.json，.env 中的账号也会作为一个默认 Provider 注入（alias 为 default 或 default_env）。
2) 创建群聊会话（为每位参与者绑定账号/模型）：
- curl -s -X POST http://localhost:3000/api/group-conversations -H 'Content-Type: application/json' -d '{ "title":"三人讨论：马克思与恩格斯", "participants":[ {"roleCardId":"Marx","name":"马克思","providerAlias":"deepseek_a","model":"deepseek-chat","agentId":"marx"}, {"roleCardId":"Engels","name":"恩格斯","providerAlias":"deepseek_b","model":"deepseek-chat","agentId":"engels"} ] }'
- 记录返回中的 id 为 GID。
3) 发起一轮群聊（SSE）：
- curl -N -X POST http://localhost:3000/api/group-conversations/GID/assistant/stream -H 'Content-Type: application/json' -d '{"text":"请讨论‘异化劳动’与‘家庭结构’的关系"}'
4) 查看群聊详情：
- curl -s http://localhost:3000/api/group-conversations/GID | jq
提示：事件流包含：status.start → agent.message.created / agent.message.delta / agent.message.completed → done。

6. 知识库（文本 → 结构化 → 角色绑定）
1) 创建知识库并绑定角色：
- curl -s -X POST http://localhost:3000/api/kb -H 'Content-Type: application/json' -d '{"title":"马克思语料","roleCardId":"Marx"}'
- 记录返回中的 id 为 KBID。
2) 文本入库并结构化：
- curl -s -X POST http://localhost:3000/api/kb/KBID/ingest-text -H 'Content-Type: application/json' -d '{"title":"手稿片段","text":"第一段……\n\n第二段……"}' | jq
3) 查看文档列表：
- curl -s http://localhost:3000/api/kb/KBID/docs | jq
4) 按角色查看已绑定知识库：
- curl -s http://localhost:3000/api/kb/role/Marx | jq

7. 常见问题（FAQ）
- 启动报错 LLM 配置缺失：确认 .env 中 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY（如网关需要）已设置。
- /api/providers 看不到账号：检查 data/providers.json 格式是否正确；或确认服务已重启（一般不需要，重新发起请求即可）。
- SSE 不显示：使用 curl -N 或前端 EventSource；网络代理/网关不要拦截 text/event-stream。
- 单人聊天支持多账号吗：当前单人接口默认使用 .env 账号；若需要也支持 providerAlias，可后续加一个入参（群聊已支持）。
