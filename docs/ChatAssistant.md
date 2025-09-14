目标与定位

作用：当用户“卡住”时，生成3个极短的“下一条用户回复选项”，每个不超过2句、不同角度，点选即可作为用户消息发送给当前对话中的AI。
范围：针对单角色对话与群聊均可用；默认中文，随会话 locale 切换。
输出：短文本选项 + 简短角度标签；可选返回隐藏“理由/思路”供悬浮提示。
关键设计

生成对象：是“用户下一句”，不是AI回复。所以提示词要以“帮用户说”的身份来约束。
角度多样性：内置角度库，优先生成“澄清/追问/挑战/举例/连接现实/收束总结/换视角”等不同类型。
严格长度：生成后服务端进行二次约束（句子切分+截断），确保“≤2句/选项”。
历史裁剪：基于token预算优先取“系统persona + 最近3–6轮 + 会话摘要”。摘要可用你现有摘要策略骨架。
幂等/可重放：结果缓存键为（conversationId + lastMessageId + k + angles），避免重复成本。
接口契约（建议）

生成选项（单聊/群聊通用）
POST /api/conversations/{cid}/suggestions
入参：
roleCardId（单聊必传；群聊可选，用于选定“对谁说”）
targetAgentId?（群聊可传，明确下一句要对哪位 agent 说）
k?（默认3）
maxSentences?（默认2）
angles?（可选角度提示；不传则由后端多样化采样）
locale?（默认会话的locale）
temperature?、diversityPenalty?（可选）
返回：
suggestions: [{ id, text, angle, tone? }]
meta: { model, promptVersion, usage, cached:boolean }
使用选项（沿用现有聊天接口）
前端把被选中的 text 直接作为用户消息调用现有发送接口：
单聊流式：POST /api/role-conversations/{cid}/assistant/stream body { roleCardId, text: <选项> }
群聊流式：POST /api/group-conversations/{gid}/assistant/stream body { text: <选项> }
多角色/群聊适配

面向对象：建议明确 targetAgentId（或角色名）让建议“对某个发言者接话”，生成更贴切的选项。
角度建议：在群聊里优先产出“对X的追问/对Y观点的挑战/跨人总结提问/请X给例子”等可操作类型。
与“判官”兼容：用户选择一个选项后，正常走下一轮调度（或将本轮“指定下一位”设置为该选项指向的对象）。
提示词与约束（核心要点）

角色感知：将“对方AI的persona摘要”作为条件，让建议贴合对话语境。
输出格式契约：要求严格输出 JSON 数组，3项，每项≤2句，避免噪声。
多样性控制：
把角度库作为“候选类型”，提示“需覆盖不同角度、避免重复语义”；
轻度提升 temperature/加多样性惩罚（或通过模板明确不同角度）。
安全与合规：继承你“拒绝/降级”的策略；对敏感请求给出“安全提示型建议”（如“请提供一般原则并提示求助专业人士”）。
长度与合规的后处理

句子切分（中英文标点），强制取前2句，多余截断。
去重：基于相似度（简单可用去标点+lowercase+前N字对比）剔除重复；不足时补样。
空洞过滤：剔除“重复寒暄/与上下文无关”的短句；不足时重采。
性能与成本

非流式返回即可（体感快）。若需流式，可用 suggestions.delta 事件，通常没必要。
缓存：命中率高，当用户反复点“换一组”可附 seed/diversify=true 强制不同。
小模型：建议使用较轻的模型（仅做“建议”），与主对话模型解耦。
前端交互建议

触发：输入区旁“没思路？智能建议”按钮
展示：3个卡片，显示“短文本 + 角度标签”；可 hover 展示隐藏 rationale（可选）
行为：
“一键发送”：直接作为用户消息发出
“复制/编辑后发送”：作为草稿填入输入框
“换一组”：增加 diversify=true 再次调用
群聊模式：上方下拉选择“对谁说”（若不选，默认对上一位/指定对象）
与现有后端的衔接

复用：Storage 读历史、RoleCardRegistry 读persona、LLMClient 统一调用。
新增：一个 SuggestionEngine（内部：历史裁剪+模板渲染+调用+后处理+缓存）。
文档：在 docs/usage.md 新增“智能建议”段落；在 docs/multi_agent.md 标注群聊适配要点（targetAgentId）。
可选进阶

意图定制：支持前端传“希望的角度/语气”（clarify/challenge/ask-example/softer/stronger）。
强化学习：收集用户点击率，离线调整角度权重与模板。
RAG：必要时用知识库提取“建议所需概念/引用”，但仍保持≤2句。
MVP 建议

后端先做非流式 /suggestions，3条、≤2句、多角度、缓存。
单聊先上线；群聊加 targetAgentId 参数与提示词引导。
前端提供“一键发送/编辑后发送/换一组”三种操作。