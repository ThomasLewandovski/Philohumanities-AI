角色卡全攻略：从零开始到私聊、群聊完全联动

面向第一次接触本项目的同学。只要照着本文操作，就能把一个全新的角色卡无缝接入个人会话和群聊功能。

--------------------------------------------------

1. 核心概念

角色卡（Role Card）存放在 backend/prompts/ 目录下的 JSON 文件中，用来定义人物设定（人格、语气、招呼语等）。
私聊（角色对话）通过 /api/role-conversations 和 /api/role-conversations/{cid}/assistant/stream 提供的一对一会话，新会话会把角色卡写入首条 system 消息。
群聊通过 /api/group-conversations 等接口创建多角色对话室，请求体里的每个参与者需要引用某个 roleCardId。
后端加载逻辑在 backend/core/roles/registry.py，会扫描 backend/prompts/*.json 并把所有合法角色提供给 API。
只要角色卡文件存在且格式正确，私聊与群聊接口都会立即识别到它。

--------------------------------------------------

2. 开始前的准备

确认环境变量（.env 或系统环境）：
LLM_BASE_URL 与 LLM_MODEL 必填，LLM_API_KEY 在网关鉴权时必填，DATA_DIR 可选（默认 ./data）。
在仓库根目录执行 uvicorn backend.main:app --reload --port 3000 启动后端。
浏览器访问 http://127.0.0.1:3000/health 返回 {"status":"ok"} 代表服务正常。

--------------------------------------------------

3. 手把手创建第一个角色卡

步骤一：挑一个唯一的 slug。建议使用无空格英文，例如 Socrates。文件名必须与 slug 相同，如 backend/prompts/Socrates.json。

步骤二：填写 JSON 内容。
必填字段：
name  展示名，例如 苏格拉底。
prompt  LLM 的 system 提示，用于定义身份、边界、拒答策略。
可选字段：
style  语气或写作风格提示，会附加到 system prompt。
greeting  建议发送给用户的第一句招呼语。
locales  支持的语言列表，默认 ['zh-CN']。

示例 JSON：
{
  "name": "苏格拉底",
  "prompt": "你是苏格拉底，以苏格拉底式问答帮助对方澄清概念和前提。在涉及医学或法律时只提供一般原则，并建议咨询专业人士。",
  "style": "语气温和、问题驱动、循序渐进地拆解概念。",
  "greeting": "我们从一个定义开始：你如何理解‘善’？",
  "locales": ["zh-CN"]
}

步骤三：保存文件。后端无需重启，RoleCardRegistry 会在下一次请求时自动重新扫描。

--------------------------------------------------

4. 验证私聊流程

确认角色已加载：
curl http://127.0.0.1:3000/api/role-cards | jq
输出数组中应包含你的 slug。如果没有出现，检查 JSON 是否有效、文件名是否正确。

创建角色会话：
curl -X POST http://127.0.0.1:3000/api/role-conversations \
  -H 'Content-Type: application/json' \
  -d '{"roleCardId":"Socrates","title":"与苏格拉底聊天"}'
响应会返回 conversationId，后续聊天依赖它。

开启 SSE 聊天：
curl -N -X POST http://127.0.0.1:3000/api/role-conversations/<conversationId>/assistant/stream \
  -H 'Content-Type: application/json' \
  -d '{"roleCardId":"Socrates","text":"什么是正义？"}'
你会看到 event: status.start、若干条 message.delta，以及 event: done。前端通常使用 EventSource 监听并渲染这些事件。

查看会话历史（可选）：
curl http://127.0.0.1:3000/api/conversations/<conversationId>/messages
首条消息应该是 system（即你的角色卡 prompt），之后是用户输入和助手回答。

--------------------------------------------------

5. 验证群聊流程

群聊允许多个角色共同参与。在创建群聊时把新角色的 roleCardId 填进去即可。

群聊请求体示例：
{
  "participants": [
    {
      "roleCardId": "Socrates",
      "name": "苏老师",
      "model": null,
      "providerAlias": null
    },
    {
      "roleCardId": "Marx",
      "name": "小马克"
    }
  ],
  "title": "思想圆桌"
}

创建群聊会话：
curl -X POST http://127.0.0.1:3000/api/group-conversations \
  -H 'Content-Type: application/json' \
  -d @payload.json
响应包含群聊 id，用于后续操作。

可选：先插入一条用户消息：
curl -X POST http://127.0.0.1:3000/api/group-conversations/<gid>/user \
  -H 'Content-Type: application/json' \
  -d '{"text":"请两位讨论正义的本质"}'
如果略过这一步，系统会让角色根据历史自行决定话题。

触发一轮群聊（SSE）：
curl -N -X POST http://127.0.0.1:3000/api/group-conversations/<gid>/assistant/stream \
  -H 'Content-Type: application/json' \
  -d '{"text":null}'
命令中的 -N 让 curl 保持流式输出。事件顺序通常是 status.start、judge.*、agent.message.created、多个 agent.message.delta、agent.message.completed、最后是 done。在 data/group/ 目录可以检查每轮生成的消息与裁判日志，以确认新角色已经参与发言。

查看群聊详情：
curl http://127.0.0.1:3000/api/group-conversations/<gid>
返回结果中的 participants 会列出所有角色，messages 中能看到每轮发言及 agentId。

--------------------------------------------------

6. 常用排查与 QA 清单

GET /api/role-cards 没有出现新角色：检查 JSON 语法是否正确，文件名是否等于 slug，保存位置是否为 backend/prompts/。
创建会话返回 404：确认请求体中的 roleCardId 与文件名一致，并注意大小写。
SSE 无响应或立即结束：确认 LLM 服务可用，检查 LLM_BASE_URL 和 LLM_MODEL 是否正确，查看后端日志是否有 502。
群聊内角色不发言：确认 participants 中正确引用 roleCardId，providerAlias 指向的 Provider 是否存在。
角色口吻与预期不符：调整 prompt 和 style，明确语调、句式、引用习惯等细节。

建议为重要角色编写简单的冒烟测试，例如固定提问“请简介你的身份”，以验证 persona 是否生效。

--------------------------------------------------

7. 进阶方向

批量角色管理：把 backend/prompts/ 纳入版本库或配置中心，并建立评审流程。
多语言支持：在 locales 中列出语言列表，前端可按语言过滤。
知识库联动：结合 /api/kb 系列接口，为角色预先绑定资料并在 prompt 中引用。
安全审计：对敏感领域角色卡进行额外审阅，确保 prompt 明确拒答策略。

--------------------------------------------------

完成以上步骤后，你的新角色卡就可以同时用于私聊和群聊。如果遇到问题，先查看 uvicorn 控制台输出，再检查 data/ 目录下的持久化文件，根据上面的排查表逐项定位即可。
