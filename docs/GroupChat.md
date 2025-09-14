核心思路

三层选择链：规则优先（selector_func）→ 候选过滤（candidate_func）→ 判官模型（selector_prompt + history）。
轮转约束：默认不允许连续发言 allow_repeated_speaker=false；若判官误选上一位，返回“不能重复”反馈重试，至多 max_selector_attempts 次，然后兜底。
可插话/暂停：编排器只在“轮与轮之间”推进；按键暂停时立即“停止调度下一位”，可选“终止当前生成”；用户发言后继续下一轮。
后端落地（状态与流程）

会话状态（新增）
orchestrator: { mode: "selector", allowRepeated: false, maxSelectorAttempts: 3 }
lastSpeaker: agentId 或 null
pending: 当前轮的候选名单、选择对话上下文（供判官重试）
paused: boolean（是否暂停推进）
回合流程
start turn → 选人（规则/候选/判官）→ 下发“请发言”给被选中 agent → 收齐输出 → 终止检查 → 下一轮
若 paused=true：在“下一轮开始”时停住；若需要也可中断“当前生成”（见下“暂停语义”）
接口扩展（契约，不写实现）

创建组会话（已有，增加判官配置）
POST /api/group-conversations
body 关键字段：
participants[]: [{ agentId, roleCardId, name, model?, providerAlias? }]
orchestrator?: { mode: "selector", allowRepeated?: false, maxSelectorAttempts?: 3, selectorPrompt?: "...", judgeProviderAlias?: "deepseek_a", judgeModel?: "deepseek-chat" }
发起一轮（SSE，沿用现有接口，增加判官事件）
POST /api/group-conversations/{gid}/assistant/stream
body:
text: 若用户在这一轮开场发言，则是用户文本；否则可空或省略（仅用于推进 AI→AI）
strategy?: "selector"（默认）
事件序列（在你现有基础上新增 judge.*）
status.start: { conversationId, agents:[...] }
judge.start: { attempts, allowRepeated, candidates:[agentId...] }
judge.delta: { text }（可选，展示判官思考/流式输出）
judge.feedback: { text }（重试时注入的约束/纠错）
judge.decision: { agentId, reason? }
agent.message.created / agent.message.delta / agent.message.completed
status.paused（若收到暂停指令后停住）
done
暂停/继续
POST /api/group-conversations/{gid}/pause
body: { now?: true, stopCurrent?: false }
now=false（默认）：在“本轮完成”后暂停，不再推进下一轮（观感好，安全）
stopCurrent=true：请求立即中止“当前生成”（需底层模型支持取消；否则仅“停止后续调度”）
POST /api/group-conversations/{gid}/resume
用户插话（不推进判官）
POST /api/group-conversations/{gid}/user
body: { text }（写入 user 消息，不触发 agent 生成）
跳过/指定下一位（人为覆盖）
POST /api/group-conversations/{gid}/override-next
body: { agentId }（跳过判官、直接点名下一位）
规则/候选（简单可编程配置）
PATCH /api/group-conversations/{gid}/orchestrator
body: { allowRepeated?, rotation?: ["marx","engels",...], exclude?: [agentId...], selectorPrompt? }
注：短期用配置替代“真正的 selector_func/candidate_func 回调”。需要真回调时可设计一个 DSL 或服务端注册的策略名。
暂停语义与实现建议

默认“软暂停”：不再开始下一位；当前发言完成后停住（不需要真正取消模型请求，兼容你现在“非流→切块”的实现）。
“硬暂停”：立即中断当前发言
理想：用底层流式 + 取消 token（后续接入真流式时实现）
当前非流式：服务端可以停止继续向前端推送剩余分块，但无法阻止已发出的 LLM 请求计费；因此建议仍以“软暂停”为主
判官模型与性能

模型选择：判官可以用更轻的模型（只做选择），与发言人模型解耦，降低延迟与成本。
降延迟做法：
规则优先：命中则不调判官
候选缩小：根据关键词/角色相关性提前裁剪列表
缩短上下文：history 截断 + 摘要化（使用你已有摘要机制的骨架）
限制重试：maxSelectorAttempts=2 或 3，并设兜底（round-robin/上一位/第一个候选）
仅在“候选>=2”时调判官：若只有一位候选则直接选中
终止条件

条件组合：max_turns、用户发“/end”、达到目标（比如“主持人已输出总结”）。
接口：PATCH /api/group-conversations/{gid}/orchestrator 里携带 termination: { maxTurns?: n, stopOnTag?: "summary_done" }
知识库与角色结合（可选扩展位）

判官：可读每位候选的“角色简介/能力标签”作为 roles 列表，提高判定准确性。
发言人：保持你已有 KbManager 接口，将“相关片段”注入 system/developer 段（等你需要 RAG 时启用即可）。
前端交互建议

控制栏：
开始/下一轮（用于 AI→AI 自推进）
暂停（默认软暂停：仅停止调度下一位；若选“硬暂停”则提示可能产生部分响应丢弃）
插话：暂停时打开输入框，POST /user 后再 Resume
指定下一位：展示参与者列表，调用 override-next 点名
可观测：
显示 judge.* 事件（小弹窗/侧边栏），包括重试原因和选择依据
在消息气泡上标注“轮到谁”，对齐 judge.decision
显示 usage 与 providerAlias（便于调试成本/路由）
SSE 事件规范小结

judge.start: { candidates, allowRepeated, attempts }
judge.delta: { text }（可选）
judge.feedback: { text }（重试时系统反馈）
judge.decision: { agentId, reason? }
agent.message.*（你已实现）
status.paused（收到暂停指令且已生效）
done（本轮结束）
失败与兜底

判官失败：重试若仍失败，优先上一位（若允许）、否则第一个候选
候选为空：直接 done（并抛出 warning 事件）
模型不可用：切换到备用 provider（你已支持多 provider），或回退到规则/轮转
MVP 落地顺序

阶段 1：软暂停 + 手动推进下一轮（按钮触发），判官只做“候选>=2”时选择，1 次重试，兜底 round-robin
阶段 2：加入“指定下一位”与“插话”API，front 端完整联动
阶段 3：判官可流式展示（judge.delta），并发/并行优化与主持人总结 Agent