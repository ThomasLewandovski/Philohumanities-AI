(() => {
  console.log('[app] frontend script booting');
  const API_BASE = '';

  // 合并重复的DOM元素变量
  const DOM = {
    // 会话列表
    singleconvList: document.getElementById('singleconversationList'),
    multiconvList: document.getElementById('multiconversationList'),
    // 消息区域
    messages: document.getElementById('messages'),
    input: document.getElementById('input'),
    model: document.getElementById('model'),
    composer: document.getElementById('composer'),
    // 按钮
    newChatBtn: document.getElementById('newChatBtn'),
    clearChatBtn: document.getElementById('clearChatBtn'),
    suggestBtn: document.getElementById('suggestBtn'),
    suggestionsPanel: document.getElementById('suggestionsPanel'),
    groupControls: document.getElementById('groupControls'),
    autoRunBtn: document.getElementById('autoRunBtn'),
    wantSpeakBtn: document.getElementById('wantSpeakBtn'),
    pauseBtn: document.getElementById('pauseBtn'),
    // 侧边栏
    multiChatBtn: document.getElementById('multiChatBtn'),
    singleChatBtn: document.getElementById('singleChatBtn'),
    multiPanel: document.getElementById('multi-panel'),
    singlePanel: document.getElementById('single-panel'),
    toggleSidebarBtn: document.getElementById('toggleSidebar'),
    sidebar: document.getElementById('sidebar'),
    chatmian: document.getElementById('chat-main'),
    singlePanelTitle: document.getElementById('single-title'),
    multiPanelTitle: document.getElementById('multi-title'),
    // 模态框
    typeModal: document.getElementById('typeModal'),
    roleModal: document.getElementById('roleModal'),
    confirmModal: document.getElementById('confirmModal'),
    choosePrivateBtn: document.getElementById('choosePrivateBtn'),
    chooseGroupBtn: document.getElementById('chooseGroupBtn'),
    roleGrid: document.getElementById('roleGrid'),
    confirmText: document.getElementById('confirmText'),
    confirmCreateBtn: document.getElementById('confirmCreateBtn'),
    groupRoleModal: document.getElementById('groupRoleModal'),
    groupRoleGrid: document.getElementById('groupRoleGrid'),
    confirmGroupCreateBtn: document.getElementById('confirmGroupCreateBtn')
  };

  // 初始化按钮样式
  if (DOM.wantSpeakBtn) {
    DOM.wantSpeakBtn.classList.add('group-toggle-btn');
    DOM.wantSpeakBtn.classList.remove('secondary');
  }
  if (DOM.pauseBtn) {
    DOM.pauseBtn.classList.add('group-toggle-btn');
    DOM.pauseBtn.classList.remove('secondary');
  }

  // 状态变量
  let state = {
    conversations: [],
    activeId: null, // 私聊ID
    groupConversations: [],
    activeGroupId: null, // 群聊ID
    isGroupMode: false,
    groupParticipantsById: {},
    groupInFlight: false,
    autoRun: true,
    wantSpeak: false,
    paused: false,
    selectedRole: null, // { slug, name }
    selectedGroup: new Set()
  };

  // 更新群聊控制UI
  function updateGroupControlsUI() {
    if (DOM.groupControls) {
      DOM.groupControls.classList.toggle('hidden', !state.isGroupMode);
    }
    if (DOM.autoRunBtn) {
      DOM.autoRunBtn.textContent = `自动续聊：${state.autoRun ? '开' : '关'}`;
    }
    if (DOM.wantSpeakBtn) {
      DOM.wantSpeakBtn.classList.toggle('group-toggle-btn--pending', state.wantSpeak);
    }
    if (DOM.pauseBtn) {
      DOM.pauseBtn.textContent = state.paused ? '继续' : '暂停';
      DOM.pauseBtn.classList.toggle('group-toggle-btn--paused', state.paused);
    }
    // 小智囊仅在私聊启用
    if (DOM.suggestBtn) {
      const groupDisabled = !!state.isGroupMode;
      DOM.suggestBtn.disabled = false;
      DOM.suggestBtn.classList.toggle('soft-disabled', groupDisabled);
      DOM.suggestBtn.title = groupDisabled ? 'AI小智囊仅用于私聊' : 'AI小智囊';
    }
  }

  // 创建带角色的私聊会话
  async function createSingleConversationWithRole(role) {
    try {
      const title = `与${role}的对话`;
      const meta = await fetchJSON('/api/conversations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, title })
      });
      state.activeId = meta.id;
      window.__msgs = [];
      await loadSingleConversations();
      await loadMessages();
    } catch (err) {
      alert('创建会话失败: ' + (err.message || err));
    }
  }

  // 通用JSON请求
  async function fetchJSON(path, init) {
    const resp = await fetch(API_BASE + path, init);
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(text || (`HTTP ${resp.status}`));
    }
    return resp.json();
  }

  // 加载私聊会话
  async function loadSingleConversations() {
    state.conversations = await fetchJSON('/api/conversations');
    if (!state.activeId && state.conversations[0]) {
      state.activeId = state.conversations[0].id;
    }
    renderSingleConversations();
  }

  // 渲染私聊会话列表
  function renderSingleConversations() {
    DOM.singleconvList.innerHTML = '';
    state.conversations.forEach((c) => {
      const li = document.createElement('li');
      li.textContent = c.title || '未命名会话';
      if (c.id === state.activeId) {
        li.classList.add('active');
      }
      li.onclick = () => {
        state.activeId = c.id;
        renderSingleConversations();
        loadMessages();
      };
      DOM.singleconvList.appendChild(li);
    });
  }

  // 渲染消息
  function renderMessages() {
    DOM.messages.innerHTML = '';
    const messages = state.isGroupMode ? (window.__gmsgs || []) : (window.__msgs || []);

    messages.forEach((m) => {
      if (m.role === 'system') return;

      const div = document.createElement('div');
      div.className = `msg ${m.role}`;

      if (state.isGroupMode && m.role === 'assistant' && m.agentId) {
        const info = state.groupParticipantsById[m.agentId];
        const prefix = info ? `[${info.name}] ` : `[${m.agentId}] `;
        div.textContent = prefix + (m.content || '');
      } else {
        div.textContent = m.content;
      }

      DOM.messages.appendChild(div);
    });

    DOM.messages.scrollTop = DOM.messages.scrollHeight;
  }

  // 处理流式响应
  async function handleStreamResponse(resp, isManual = false) {
    if (!resp.ok || !resp.body) {
      throw new Error(await resp.text());
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    const inProgress = {};

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buf += decoder.decode(value, { stream: true });
      let idx;

      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const chunk = buf.slice(0, idx).trim();
        buf = buf.slice(idx + 2);
        if (!chunk) continue;

        const lines = chunk.split('\n');
        let eventName = 'message';
        let dataLine = '';

        lines.forEach(line => {
          if (line.startsWith('event:')) {
            eventName = line.slice(6).trim();
          }
          if (line.startsWith('data:')) {
            dataLine = line.slice(5).trim();
          }
        });

        let dataObj = {};
        if (dataLine) {
          try {
            dataObj = JSON.parse(dataLine);
          } catch { }
        }

        if (eventName === 'status.paused') {
          state.paused = true;
          updateGroupControlsUI();
        } else if (eventName === 'agent.message.created') {
          inProgress[dataObj.messageId] = { agentId: dataObj.agentId, text: '' };
        } else if (eventName === 'agent.message.delta') {
          const it = inProgress[dataObj.messageId];
          if (it) {
            it.text += (dataObj.delta || '');
          }
        } else if (eventName === 'agent.message.completed') {
          const it = inProgress[dataObj.messageId];
          const content = it ? it.text : '';
          window.__gmsgs = window.__gmsgs || [];
          window.__gmsgs.push({
            role: 'assistant',
            agentId: dataObj.agentId,
            content,
            ts: new Date().toISOString()
          });
          renderMessages();
        }
      }
    }

    return isManual;
  }

  // 群聊运行循环
  async function groupRunLoop() {
    if (!state.isGroupMode || !state.activeGroupId || state.groupInFlight || state.paused) {
      return;
    }

    state.groupInFlight = true;
    try {
      const resp = await fetch(`/api/group-conversations/${state.activeGroupId}/assistant/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });

      const wasManual = await handleStreamResponse(resp);

      if (wasManual) {
        state.wantSpeak = false;
        updateGroupControlsUI();
      }
    } catch (e) {
      console.error('groupRunLoop error', e);
    } finally {
      state.groupInFlight = false;
      if (!state.paused && state.autoRun) {
        setTimeout(groupRunLoop, 200);
      }
    }
  }

  // 加载消息
  async function loadMessages() {
    if (!state.activeId && !state.activeGroupId) return;

    try {
      if (state.isGroupMode) {
        const data = await fetchJSON(`/api/group-conversations/${state.activeGroupId}`);
        const parts = data.participants || [];
        state.groupParticipantsById = {};
        parts.forEach(p => {
          state.groupParticipantsById[p.agentId] = {
            name: p.name || p.roleCardId,
            roleCardId: p.roleCardId
          };
        });
        window.__gmsgs = data.messages || [];
      } else {
        const data = await fetchJSON(`/api/conversations/${state.activeId}/messages`);
        window.__msgs = data.messages || [];
      }
      renderMessages();
    } catch (err) {
      console.error('加载消息失败', err);
    }
  }

  // 发送私聊消息
  async function handleSend(text) {
    if (!state.activeId) {
      await createConversation();
    }

    const convId = state.activeId;
    // 本地乐观更新
    window.__msgs = window.__msgs || [];
    window.__msgs.push({
      role: 'user',
      content: text,
      ts: new Date().toISOString()
    });
    renderMessages();

    let payload = { content: text };
    if (DOM.model.value && DOM.model.value.trim()) {
      payload.model = DOM.model.value.trim();
    }

    try {
      const data = await fetchJSON(`/api/conversations/${convId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      window.__msgs.push(data.assistant);
      await loadSingleConversations();
      renderMessages();
    } catch (err) {
      window.__msgs.push({
        role: 'assistant',
        content: `【错误】${err.message || err}`,
        ts: new Date().toISOString()
      });
      renderMessages();
    }
  }

  // 发送群聊消息
  async function groupHandleSend(text) {
    if (!state.activeGroupId) {
      alert('请选择一个群聊');
      return;
    }
    if (state.groupInFlight) {
      alert('当前回合进行中，请稍候…');
      return;
    }

    state.groupInFlight = true;
    // 本地乐观更新
    window.__gmsgs = window.__gmsgs || [];
    window.__gmsgs.push({
      role: 'user',
      content: text,
      ts: new Date().toISOString()
    });
    renderMessages();

    try {
      const resp = await fetch(`/api/group-conversations/${state.activeGroupId}/assistant/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });

      const wasManual = await handleStreamResponse(resp, true);

      if (wasManual) {
        state.wantSpeak = false;
        updateGroupControlsUI();
      }
    } catch (e) {
      alert('群聊生成失败: ' + (e.message || e));
    } finally {
      state.groupInFlight = false;
      if (!state.paused && state.autoRun) {
        setTimeout(groupRunLoop, 200);
      }
    }
  }

  // 渲染建议
  function renderSuggestions(items) {
    if (!items || !items.length) {
      DOM.suggestionsPanel.classList.add('hidden');
      DOM.suggestionsPanel.innerHTML = '';
      return;
    }

    DOM.suggestionsPanel.classList.remove('hidden');
    DOM.suggestionsPanel.innerHTML = '';

    items.forEach((sug) => {
      const card = document.createElement('div');
      card.className = 'suggestion-card';

      const text = document.createElement('div');
      text.textContent = sug.text;

      const angle = document.createElement('div');
      angle.className = 'angle';
      angle.textContent = sug.angle || '';

      const actions = document.createElement('div');
      actions.className = 'actions';

      const sendBtn = document.createElement('button');
      sendBtn.setAttribute('type', 'button');
      sendBtn.textContent = '一键发送';
      sendBtn.onclick = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        clearSuggestions();
        state.isGroupMode ? groupHandleSend(sug.text) : handleSend(sug.text);
      };

      const useBtn = document.createElement('button');
      useBtn.setAttribute('type', 'button');
      useBtn.textContent = '填入输入框';
      useBtn.onclick = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        DOM.input.value = sug.text;
        clearSuggestions();
        DOM.input.focus();
      };

      actions.appendChild(useBtn);
      actions.appendChild(sendBtn);
      card.appendChild(text);
      card.appendChild(angle);
      card.appendChild(actions);
      DOM.suggestionsPanel.appendChild(card);
    });
  }

  // 清除建议
  function clearSuggestions() {
    DOM.suggestionsPanel.classList.add('hidden');
    DOM.suggestionsPanel.innerHTML = '';
  }

  // 创建会话
  async function createConversation() {
    try {
      const meta = await fetchJSON('/api/conversations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      state.activeId = meta.id;
      window.__msgs = [];
      await loadSingleConversations();
      await loadMessages();
    } catch (err) {
      alert('创建会话失败: ' + (err.message || err));
    }
  }

  // 加载群聊会话
  async function loadGroupConversations() {
    try {
      console.log('[group] loadGroupConversations: fetching list…');
      state.groupConversations = await fetchJSON('/api/group-conversations');
      console.log('[group] loadGroupConversations: fetched',
        Array.isArray(state.groupConversations) ? state.groupConversations.length : state.groupConversations);
      renderGroupConversations();
    } catch (e) {
      console.error('[group] loadGroupConversations error', e);
    }
  }

  // 渲染群聊会话列表
  function renderGroupConversations() {
    if (!DOM.multiconvList) return;

    DOM.multiconvList.innerHTML = '';
    (state.groupConversations || []).forEach(g => {
      const li = document.createElement('li');
      li.textContent = g.title || g.id;
      if (g.id === state.activeGroupId) {
        li.classList.add('active');
      }
      li.onclick = async () => {
        state.isGroupMode = true;
        state.activeGroupId = g.id;
        await loadMessages();
        renderGroupConversations();
      };
      DOM.multiconvList.appendChild(li);
    });
  }

  // 切换聊天模式（私聊/群聊）
  function switchChatMode(isGroup) {
    state.isGroupMode = isGroup;
    DOM.multiPanel.style.display = isGroup ? '' : 'none';
    DOM.singlePanel.style.display = isGroup ? 'none' : '';
    DOM.multiChatBtn.classList.toggle('active', isGroup);
    DOM.singleChatBtn.classList.toggle('active', !isGroup);

    if (isGroup) {
      state.activeId = null;
      loadGroupConversations();
      // 开启自动续聊
      if (state.autoRun && !state.paused) {
        setTimeout(groupRunLoop, 200);
      }
    } else {
      state.activeGroupId = null;
    }

    renderMessages();
    updateGroupControlsUI();
  }

  // 模态框操作
  function openModal(el) {
    el.classList.remove('hidden');
  }

  function closeModal(el) {
    el.classList.add('hidden');
  }

  // 初始化事件监听
  function initEvents() {
    // 表单提交
    DOM.composer.addEventListener('submit', (e) => {
      e.preventDefault();
      const text = DOM.input.value.trim();
      if (!text) return;
      DOM.input.value = '';
      state.isGroupMode ? groupHandleSend(text) : handleSend(text);
    });

    // 输入框回车提交
    DOM.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        DOM.composer.requestSubmit();
      }
    });

    // 新会话按钮
    DOM.newChatBtn.onclick = () => openModal(DOM.typeModal);

    // 清除会话按钮
    DOM.clearChatBtn.onclick = async () => {
      if (!state.activeId) return;
      if (!confirm('确定要删除当前会话吗？该操作不可恢复。')) return;

      try {
        const res = await fetch(`/api/conversations/${encodeURIComponent(state.activeId)}`, {
          method: 'DELETE',
        });

        if (!res.ok) {
          const msg = await res.text().catch(() => '');
          throw new Error(msg || res.statusText || '删除失败');
        }

        // 成功后更新UI
        state.activeId = null;
        window.__msgs = [];
        await loadSingleConversations();
        await loadMessages();
      } catch (err) {
        alert('删除失败: ' + (err?.message || err));
      }
    };

    // AI小智囊
    DOM.suggestBtn.onclick = async () => {
      if (state.isGroupMode) {
        alert('AI小智囊仅用于私聊');
        return;
      }
      if (!state.activeId) {
        alert('请先创建或选择一个会话');
        return;
      }

      DOM.suggestBtn.disabled = true;
      DOM.suggestBtn.textContent = '生成中...';

      try {
        const resp = await fetch(`/api/conversations/${state.activeId}/suggestions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ k: 4, maxSentences: 2 })
        });

        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        renderSuggestions(data.suggestions || []);
      } catch (e) {
        alert('小智囊生成失败: ' + (e.message || e));
      } finally {
        DOM.suggestBtn.disabled = false;
        DOM.suggestBtn.textContent = 'AI小智囊';
      }
    };

    // 侧边栏切换
    DOM.toggleSidebarBtn.onclick = function () {
      if (DOM.sidebar.classList.contains('collapsed')) {
        DOM.sidebar.classList.remove('collapsed');
        DOM.chatmian.classList.remove('expanded');
        DOM.toggleSidebarBtn.innerHTML = '&lt';
        DOM.multiChatBtn.style.visibility = 'visible';
        DOM.singleChatBtn.style.visibility = 'visible';
        DOM.multiPanel.style.display = 'none';
        DOM.singlePanel.style.display = '';
        DOM.multiPanelTitle.style.display = 'none';
      } else {
        DOM.sidebar.classList.add('collapsed');
        DOM.chatmian.classList.add('expanded');
        DOM.toggleSidebarBtn.innerHTML = '&gt';
        DOM.multiChatBtn.style.visibility = 'hidden';
        DOM.singleChatBtn.style.visibility = 'hidden';
        DOM.multiPanel.style.display = 'none';
        DOM.singlePanel.style.display = 'none';
      }
    };

    // 聊天模式切换按钮
    DOM.multiChatBtn.onclick = () => switchChatMode(true);
    DOM.singleChatBtn.onclick = () => switchChatMode(false);

    // 群聊控制按钮
    if (DOM.autoRunBtn) {
      DOM.autoRunBtn.onclick = () => {
        state.autoRun = !state.autoRun;
        updateGroupControlsUI();
        if (state.autoRun && !state.paused && !state.groupInFlight) {
          groupRunLoop();
        }
      };
    }

    if (DOM.wantSpeakBtn) {
      DOM.wantSpeakBtn.onclick = () => {
        state.wantSpeak = true;
        updateGroupControlsUI();
        if (!state.groupInFlight) {
          DOM.input && DOM.input.focus();
        }
      };
    }

    if (DOM.pauseBtn) {
      DOM.pauseBtn.onclick = async () => {
        if (!state.activeGroupId) return;

        try {
          if (!state.paused) {
            await fetch(`/api/group-conversations/${state.activeGroupId}/pause`, { method: 'POST' });
            state.paused = true;
            state.autoRun = false;
          } else {
            await fetch(`/api/group-conversations/${state.activeGroupId}/resume`, { method: 'POST' });
            state.paused = false;
            if (state.autoRun && !state.groupInFlight) {
              groupRunLoop();
            }
          }
        } catch (e) {
          console.error(e);
        }

        updateGroupControlsUI();
      };
    }

    // 关闭按钮通用委托
    document.body.addEventListener('click', (e) => {
      const target = e.target;
      if (target && target.hasAttribute('data-close')) {
        const id = target.getAttribute('data-close');
        const el = document.getElementById(id);
        if (el) closeModal(el);
      }
    });

    // 选择私聊
    DOM.choosePrivateBtn.onclick = async () => {
      closeModal(DOM.typeModal);
      state.selectedRole = null;
      DOM.roleGrid.innerHTML = '<div style="color:var(--muted);padding:8px;">加载角色中...</div>';
      openModal(DOM.roleModal);

      try {
        const roles = await fetch('/api/role-cards').then(r => r.json());
        DOM.roleGrid.innerHTML = '';

        roles.forEach(r => {
          const card = document.createElement('div');
          card.className = 'role-card';

          const img = document.createElement('img');
          img.src = `/resources/${r.slug}.png`;

          const name = document.createElement('div');
          name.className = 'name';
          name.textContent = r.name || r.slug;

          card.appendChild(img);
          card.appendChild(name);
          card.onclick = () => {
            state.selectedRole = { slug: r.slug, name: r.name || r.slug };
            DOM.confirmText.textContent = `确认与“${state.selectedRole.name}”开始新的会话？`;
            openModal(DOM.confirmModal);
          };

          DOM.roleGrid.appendChild(card);
        });
      } catch (e) {
        DOM.roleGrid.innerHTML = '<div style="color:tomato;">角色加载失败</div>';
      }
    };

    // 选择群聊
    DOM.chooseGroupBtn.onclick = () => {
      closeModal(DOM.typeModal);
      openModal(DOM.groupRoleModal);
      state.selectedGroup = new Set();
      DOM.groupRoleGrid.innerHTML = '<div style="color:var(--muted);padding:8px;">加载角色中...</div>';

      fetch('/api/role-cards').then(r => r.json()).then(roles => {
        DOM.groupRoleGrid.innerHTML = '';

        roles.forEach(r => {
          const card = document.createElement('div');
          card.className = 'role-card';

          const img = document.createElement('img');
          img.src = `/resources/${r.slug}.png`;

          const name = document.createElement('div');
          name.className = 'name';
          name.textContent = r.name || r.slug;

          card.appendChild(img);
          card.appendChild(name);
          card.onclick = () => {
            if (state.selectedGroup.has(r.slug)) {
              state.selectedGroup.delete(r.slug);
              card.style.outline = '';
            } else {
              if (state.selectedGroup.size >= 3) {
                alert('最多选择3人');
                return;
              }
              state.selectedGroup.add(r.slug);
              card.style.outline = '2px solid var(--accent)';
            }
          };

          DOM.groupRoleGrid.appendChild(card);
        });
      }).catch(() => {
        DOM.groupRoleGrid.innerHTML = '<div style="color:tomato;">角色加载失败</div>';
      });
    };

    // 确认创建群聊
    DOM.confirmGroupCreateBtn.onclick = async () => {
      if (!state.selectedGroup.size) {
        alert('请至少选择1个参与者');
        return;
      }

      const selected = Array.from(state.selectedGroup);
      try {
        const participants = selected.map((slug, i) => ({
          roleCardId: slug,
          name: slug.toUpperCase(),
          agentId: `agent-${i + 1}`
        }));

        const resp = await fetch('/api/group-conversations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ participants })
        });

        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();

        closeModal(DOM.groupRoleModal);
        // 切换到群聊模式
        switchChatMode(true);
        state.activeGroupId = data.id;
        await loadMessages();
        await loadGroupConversations();
      } catch (e) {
        alert('创建群聊失败: ' + (e.message || e));
      }
    };

    // 确认创建私聊
    DOM.confirmCreateBtn.onclick = async () => {
      if (!state.selectedRole) return;

      try {
        const resp = await fetch('/api/role-conversations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            roleCardId: state.selectedRole.slug,
            title: `与${state.selectedRole.name}的对话`
          })
        });

        if (!resp.ok) throw new Error(await resp.text());
        await resp.json();

        // 关闭弹窗并刷新
        closeModal(DOM.confirmModal);
        closeModal(DOM.roleModal);
        window.location.reload();
      } catch (err) {
        alert('创建会话失败: ' + (err.message || err));
      }
    };
  }

  // 初始化
  async function init() {
    try {
      await loadSingleConversations();
      await loadMessages();
    } catch (err) {
      console.error(err);
      alert('加载失败，请检查后端是否启动');
    }

    try {
      await loadGroupConversations();
    } catch (err) {
      console.error('loadGroupConversations', err);
    }

    updateGroupControlsUI();
    initEvents();
  }

  // 暴露群聊API
  window.__groupAPI = {
    loadConversations: loadGroupConversations,
    loadMessages: loadMessages,
    setActive: (id) => {
      state.isGroupMode = true;
      state.activeGroupId = id;
      updateGroupControlsUI();
    },
  };

  // 启动应用
  init();
})();