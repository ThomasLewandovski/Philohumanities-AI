(() => {
  console.log('[app] frontend script booting');
  const API_BASE = '';

  // DOM elements
  const $singleconvList = document.getElementById('singleconversationList');
  const $multiconvList = document.getElementById('multiconversationList');
  const $messages = document.getElementById('messages');
  const $input = document.getElementById('input');
  const $model = document.getElementById('model');
  const $composer = document.getElementById('composer');
  const $newChatBtn = document.getElementById('newChatBtn');
  const $clearChatBtn = document.getElementById('clearChatBtn');
  const $suggestBtn = document.getElementById('suggestBtn');
  const $suggestionsPanel = document.getElementById('suggestionsPanel');
  const $groupControls = document.getElementById('groupControls');
  const $autoRunBtn = document.getElementById('autoRunBtn');
  const $wantSpeakBtn = document.getElementById('wantSpeakBtn');
  const $pauseBtn = document.getElementById('pauseBtn');

  if ($wantSpeakBtn) {
    $wantSpeakBtn.classList.add('group-toggle-btn');
    $wantSpeakBtn.classList.remove('secondary');
  }
  if ($pauseBtn) {
    $pauseBtn.classList.add('group-toggle-btn');
    $pauseBtn.classList.remove('secondary');
  }

  let conversations = [];
  let activeId = null; // single chat id
  let groupConversations = [];
  let activeGroupId = null; // group chat id
  let isGroupMode = false;
  let groupParticipantsById = {};
  let groupInFlight = false;
  let autoRun = true;
  let wantSpeak = false;
  let paused = false;

  function updateGroupControlsUI() {
    if ($groupControls) {
      if (isGroupMode) $groupControls.classList.remove('hidden'); else $groupControls.classList.add('hidden');
    }
    if ($autoRunBtn) $autoRunBtn.textContent = `自动续聊：${autoRun ? '开' : '关'}`;
    if ($wantSpeakBtn) {
      $wantSpeakBtn.classList.toggle('group-toggle-btn--pending', wantSpeak);
    }
    if ($pauseBtn) {
      $pauseBtn.textContent = paused ? '继续' : '暂停';
      $pauseBtn.classList.toggle('group-toggle-btn--paused', paused);
    }
    // 小智囊仅在私聊启用
    if ($suggestBtn) {
      const groupDisabled = !!isGroupMode;
      $suggestBtn.disabled = false;
      $suggestBtn.classList.toggle('soft-disabled', groupDisabled);
      $suggestBtn.title = groupDisabled ? 'AI小智囊仅用于私聊' : 'AI小智囊';
    }
  }

  async function createSingleConversationWithRole(role) {
    try {
      const title = `与${role}的对话`;
      const meta = await fetchJSON('/api/conversations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, title })
      });
      activeId = meta.id;
      window.__msgs = [];
      await loadSingleConversations();
      await loadMessages();
    } catch (err) {
      alert('创建会话失败: ' + (err.message || err));
    }
  }

  async function fetchJSON(path, init) {
    const resp = await fetch(API_BASE + path, init);
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(text || (`HTTP ${resp.status}`));
    }
    return resp.json();
  }

  async function loadSingleConversations() {
    conversations = await fetchJSON('/api/conversations');
    if (!activeId && conversations[0]) activeId = conversations[0].id;
    renderSingleConversations();
  }

  function renderSingleConversations() {
    $singleconvList.innerHTML = '';
    conversations.forEach((c) => {
      const li = document.createElement('li');
      li.textContent = c.title || '未命名会话';
      if (c.id === activeId) li.classList.add('active');
      li.onclick = () => {
        activeId = c.id;
        renderSingleConversations();
        loadMessages();
      };
      $singleconvList.appendChild(li);
    });
  }

  function renderMessages() {
    $messages.innerHTML = '';
    if (isGroupMode) {
      (window.__gmsgs || []).forEach((m) => {
        if (m.role === 'system') return;
        const div = document.createElement('div');
        div.className = `msg ${m.role}`;
        let prefix = '';
        if (m.role === 'assistant' && m.agentId) {
          const info = groupParticipantsById[m.agentId];
          prefix = info ? `[${info.name}] ` : `[${m.agentId}] `;
        }
        div.textContent = prefix + (m.content || '');
        $messages.appendChild(div);
      });
    } else {
      (window.__msgs || []).forEach((m) => {
        if (m.role === 'system') return; // 不显示 system prompt
        const div = document.createElement('div');
        div.className = `msg ${m.role}`;
        div.textContent = m.content;
        $messages.appendChild(div);
      });
    }
    $messages.scrollTop = $messages.scrollHeight;
  }

  async function groupRunLoop() {
    if (!isGroupMode || !activeGroupId || groupInFlight || paused) return;
    groupInFlight = true;
    try {
      const resp = await fetch(`/api/group-conversations/${activeGroupId}/assistant/stream`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({})
      });
      if (!resp.ok || !resp.body) throw new Error(await resp.text());
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
            if (line.startsWith('event:')) eventName = line.slice(6).trim();
            if (line.startsWith('data:')) dataLine = line.slice(5).trim();
          });
          let dataObj = {};
          if (dataLine) { try { dataObj = JSON.parse(dataLine); } catch {} }
          if (eventName === 'status.paused') {
            paused = true; updateGroupControlsUI();
          } else if (eventName === 'agent.message.created') {
            inProgress[dataObj.messageId] = { agentId: dataObj.agentId, text: '' };
          } else if (eventName === 'agent.message.delta') {
            const it = inProgress[dataObj.messageId]; if (it) it.text += (dataObj.delta || '');
          } else if (eventName === 'agent.message.completed') {
            const it = inProgress[dataObj.messageId]; const content = it ? it.text : '';
            window.__gmsgs = window.__gmsgs || [];
            window.__gmsgs.push({ role: 'assistant', agentId: dataObj.agentId, content, ts: new Date().toISOString() });
            renderMessages();
          }
        }
      }
    } catch (e) {
      console.error('groupRunLoop error', e);
    } finally {
      const wasManual = wantSpeak;
      groupInFlight = false;
      if (wasManual) {
        wantSpeak = false;
        updateGroupControlsUI();
      }
      if (!paused && autoRun) setTimeout(groupRunLoop, 200);
    }
  }

  async function loadMessages() {
    if (!activeId) return;
    const data = await fetchJSON(`/api/conversations/${activeId}/messages`);
    window.__msgs = data.messages || [];
    renderMessages();
  }

  async function handleSend(text) {
    if (!activeId) await createConversation();
    const convId = activeId;
    // Optimistic append user locally
    window.__msgs = window.__msgs || [];
    window.__msgs.push({ role: 'user', content: text, ts: new Date().toISOString() });
    renderMessages();

    let payload = { content: text };
    if ($model.value && $model.value.trim()) payload.model = $model.value.trim();
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
      window.__msgs.push({ role: 'assistant', content: `【错误】${err.message || err}`, ts: new Date().toISOString() });
      renderMessages();
    }
  }

  // Events
  $composer.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = $input.value.trim();
    if (!text) return;
    $input.value = '';
    if (isGroupMode) {
      groupHandleSend(text);
    } else {
      handleSend(text);
    }
  });

  $input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      $composer.requestSubmit();
    }
  });

  // 新会话：打开类型选择弹窗
  $newChatBtn.onclick = () => openTypeModal();

  $clearChatBtn.onclick = () => {
    if (!activeId) return;
    if (!confirm('确定要删除当前会话吗？该操作不可恢复。')) return;
    fetchJSON(`/api/conversations/${activeId}`, { method: 'DELETE' })
      .then(() => {
        activeId = null;
        window.__msgs = [];
        loadSingleConversations().then(loadMessages);
      })
      .catch((err) => alert('删除失败: ' + (err.message || err)));
  };

  // AI小智囊：生成建议
  $suggestBtn.onclick = async () => {
    if (isGroupMode) { alert('AI小智囊仅用于私聊'); return; }
    if (!activeId) {
      alert('请先创建或选择一个会话');
      return;
    }
    $suggestBtn.disabled = true;
    $suggestBtn.textContent = '生成中...';
    try {
      const resp = await fetch(`/api/conversations/${activeId}/suggestions`, {
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
      $suggestBtn.disabled = false;
      $suggestBtn.textContent = 'AI小智囊';
    }
  };

  function renderSuggestions(items) {
    if (!items || !items.length) {
      $suggestionsPanel.classList.add('hidden');
      $suggestionsPanel.innerHTML = '';
      return;
    }
    $suggestionsPanel.classList.remove('hidden');
    $suggestionsPanel.innerHTML = '';
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
      sendBtn.setAttribute('type','button');
      sendBtn.textContent = '一键发送';
      sendBtn.onclick = (ev) => {
        ev && ev.preventDefault && ev.preventDefault();
        ev && ev.stopPropagation && ev.stopPropagation();
        clearSuggestions();
        if (isGroupMode) {
          groupHandleSend(sug.text);
        } else {
          handleSend(sug.text);
        }
      };
      const useBtn = document.createElement('button');
      useBtn.setAttribute('type','button');
      useBtn.textContent = '填入输入框';
      useBtn.onclick = (ev) => { ev && ev.preventDefault && ev.preventDefault(); ev && ev.stopPropagation && ev.stopPropagation(); $input.value = sug.text; clearSuggestions(); $input.focus(); };
      actions.appendChild(useBtn);
      actions.appendChild(sendBtn);
      card.appendChild(text);
      card.appendChild(angle);
      card.appendChild(actions);
      $suggestionsPanel.appendChild(card);
    });
  }

  function clearSuggestions() {
    $suggestionsPanel.classList.add('hidden');
    $suggestionsPanel.innerHTML = '';
  }

  async function createConversation() {
    try {
      const meta = await fetchJSON('/api/conversations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
      activeId = meta.id;
      window.__msgs = [];
      await loadSingleConversations();
      await loadMessages();
    } catch (err) {
      alert('创建会话失败: ' + (err.message || err));
    }
  }

  // init
  loadSingleConversations().then(loadMessages).catch((err) => {
    console.error(err);
    alert('加载失败，请检查后端是否启动');
  });
  loadGroupConversations().catch((err) => console.error('loadGroupConversations', err));
  updateGroupControlsUI();

  async function loadGroupConversations() {
    try {
      console.log('[group] loadGroupConversations: fetching list…');
      groupConversations = await fetchJSON('/api/group-conversations');
      console.log('[group] loadGroupConversations: fetched', Array.isArray(groupConversations) ? groupConversations.length : groupConversations);
      renderGroupConversations();
    } catch (e) { console.error('[group] loadGroupConversations error', e); }
  }

  function renderGroupConversations() {
    const $list = document.getElementById('multiconversationList');
    if (!$list) return;
    $list.innerHTML = '';
    const rows = groupConversations || [];
    console.log('[group] renderGroupConversations: rendering', rows.length, 'items');
    (groupConversations||[]).forEach(g => {
      const li = document.createElement('li');
      li.textContent = g.title || g.id;
      if (g.id === activeGroupId) li.classList.add('active');
      li.onclick = async () => { isGroupMode = true; activeGroupId = g.id; await loadGroupMessages(); renderGroupConversations(); };
      $list.appendChild(li);
    });
  }

  async function loadGroupMessages() {
    if (!activeGroupId) return;
    const data = await fetchJSON(`/api/group-conversations/${activeGroupId}`);
    const parts = data.participants || [];
    groupParticipantsById = {};
    parts.forEach(p => { groupParticipantsById[p.agentId] = { name: p.name || p.roleCardId, roleCardId: p.roleCardId }; });
    window.__gmsgs = data.messages || [];
    renderMessages();
  }

  async function groupHandleSend(text) {
    if (!activeGroupId) { alert('请选择一个群聊'); return; }
    if (groupInFlight) { alert('当前回合进行中，请稍候…'); return; }
    groupInFlight = true;
    // optimistic user append
    window.__gmsgs = window.__gmsgs || [];
    window.__gmsgs.push({ role: 'user', content: text, ts: new Date().toISOString() });
    renderMessages();
    try {
      const resp = await fetch(`/api/group-conversations/${activeGroupId}/assistant/stream`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text })
      });
      if (!resp.ok || !resp.body) { throw new Error(await resp.text()); }
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
            if (line.startsWith('event:')) eventName = line.slice(6).trim();
            if (line.startsWith('data:')) dataLine = line.slice(5).trim();
          });
          let dataObj = {};
          if (dataLine) { try { dataObj = JSON.parse(dataLine); } catch { } }
          if (eventName === 'status.paused') {
            paused = true; updateGroupControlsUI();
          } else if (eventName === 'agent.message.created') {
            inProgress[dataObj.messageId] = { agentId: dataObj.agentId, text: '' };
          } else if (eventName === 'agent.message.delta') {
            const it = inProgress[dataObj.messageId];
            if (it) { it.text += (dataObj.delta || ''); }
          } else if (eventName === 'agent.message.completed') {
            const it = inProgress[dataObj.messageId];
            const content = it ? it.text : '';
            window.__gmsgs.push({ role: 'assistant', agentId: dataObj.agentId, content, ts: new Date().toISOString() });
            renderMessages();
          }
        }
      }
    } catch (e) {
      alert('群聊生成失败: ' + (e.message || e));
    } finally {
      const wasManual = wantSpeak;
      groupInFlight = false;
      if (wasManual) {
        wantSpeak = false;
        updateGroupControlsUI();
      }
      if (!paused && autoRun) setTimeout(groupRunLoop, 200);
    }
  }

  // Expose minimal group helpers for outer handlers (modal created outside IIFE)
  window.__groupAPI = {
    loadConversations: loadGroupConversations,
    loadMessages: loadGroupMessages,
    setActive: (id) => { isGroupMode = true; activeGroupId = id; updateGroupControlsUI(); },
  };

  // Sidebar tabs
  const multiChatBtn2 = document.getElementById('multiChatBtn');
  const singleChatBtn2 = document.getElementById('singleChatBtn');
  const multi_panel2 = document.getElementById('multi-panel');
  const single_panel2 = document.getElementById('single-panel');
  multiChatBtn2.addEventListener('click', () => {
    console.log('[group] top tab click handler triggered');
    multi_panel2.style.display = '';
    single_panel2.style.display = 'none';
    multiChatBtn2.classList.add('active');
    singleChatBtn2.classList.remove('active');
    isGroupMode = true;
    activeId = null;
    loadGroupConversations();
    updateGroupControlsUI();
    // 开启自动续聊
    if (autoRun && !paused) setTimeout(groupRunLoop, 200);
  });
  singleChatBtn2.addEventListener('click', () => {
    multi_panel2.style.display = 'none';
    single_panel2.style.display = '';
    singleChatBtn2.classList.add('active');
    multiChatBtn2.classList.remove('active');
    isGroupMode = false;
    activeGroupId = null;
    renderMessages();
    updateGroupControlsUI();
  });

  // Group controls events
  if ($autoRunBtn) $autoRunBtn.onclick = () => { autoRun = !autoRun; updateGroupControlsUI(); if (autoRun && !paused && !groupInFlight) groupRunLoop(); };
  if ($wantSpeakBtn) $wantSpeakBtn.onclick = () => { wantSpeak = true; updateGroupControlsUI(); if (!groupInFlight) { $input && $input.focus(); } };
  if ($pauseBtn) $pauseBtn.onclick = async () => {
    if (!activeGroupId) return;
    try {
      if (!paused) {
        await fetch(`/api/group-conversations/${activeGroupId}/pause`, { method: 'POST' });
        paused = true; autoRun = false;
      } else {
        await fetch(`/api/group-conversations/${activeGroupId}/resume`, { method: 'POST' });
        paused = false;
        if (autoRun && !groupInFlight) groupRunLoop();
      }
    } catch (e) { console.error(e); }
    updateGroupControlsUI();
  };
})();

const multiChatBtn = document.getElementById('multiChatBtn');
const singleChatBtn = document.getElementById('singleChatBtn');
const multi_panel = document.getElementById('multi-panel');
const single_panel = document.getElementById('single-panel');
const toggleSidebarBtn = document.getElementById('toggleSidebar');
const sidebar = document.getElementById('sidebar');
const chatmian = document.getElementById('chat-main');
const single_panel_title = document.getElementById('single-title');
const multi_panel_title = document.getElementById('multi-title');

  multiChatBtn.onclick = function() {
  console.log('[group] bottom tab click handler triggered');
  multi_panel.style.display = '';
  single_panel.style.display = 'none';
  multiChatBtn.classList.add('active');
  singleChatBtn.classList.remove('active');
  if (window.__groupAPI && typeof window.__groupAPI.loadConversations === 'function') {
    window.__groupAPI.loadConversations().catch((err) => console.error('[group] bottom tab load error', err));
  }
};
singleChatBtn.onclick = function() {
  multi_panel.style.display = 'none';
  single_panel.style.display = '';
  singleChatBtn.classList.add('active');
  multiChatBtn.classList.remove('active');
};
toggleSidebarBtn.onclick = function() {
  if (sidebar.classList.contains('collapsed')) {
    sidebar.classList.remove('collapsed');
    chatmian.classList.remove('expanded');
    toggleSidebarBtn.innerHTML = '&lt';
    multiChatBtn.style.visibility = 'visible';
    singleChatBtn.style.visibility = 'visible';
    multi_panel.style.display = 'none';
    single_panel.style.display = '';
    multi_panel_title.style.display = 'none';
  } else {
    sidebar.classList.add('collapsed');
    chatmian.classList.add('expanded');
    toggleSidebarBtn.innerHTML = '&gt';
    multiChatBtn.style.visibility = 'hidden';
    singleChatBtn.style.visibility = 'hidden';
    multi_panel.style.display = 'none';
    single_panel.style.display = 'none';
  }
};

// ====== 新会话弹窗逻辑 ======
const typeModal = document.getElementById('typeModal');
const roleModal = document.getElementById('roleModal');
const confirmModal = document.getElementById('confirmModal');
const choosePrivateBtn = document.getElementById('choosePrivateBtn');
const chooseGroupBtn = document.getElementById('chooseGroupBtn');
const roleGrid = document.getElementById('roleGrid');
const confirmText = document.getElementById('confirmText');
const confirmCreateBtn = document.getElementById('confirmCreateBtn');

let __selectedRole = null; // { slug, name }

function openModal(el) { el.classList.remove('hidden'); }
function closeModal(el) { el.classList.add('hidden'); }

function openTypeModal() {
  openModal(typeModal);
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

choosePrivateBtn.onclick = async () => {
  // 关闭类型选择 → 打开角色选择
  closeModal(typeModal);
  __selectedRole = null;
  roleGrid.innerHTML = '<div style="color:var(--muted);padding:8px;">加载角色中...</div>';
  openModal(roleModal);
  try {
    const roles = await fetch('/api/role-cards').then(r => r.json());
    roleGrid.innerHTML = '';
    roles.forEach(r => {
      const card = document.createElement('div');
      card.className = 'role-card';
      const img = document.createElement('img');
      // 简单尝试本地图片（若存在）
      img.src = `/resources/${r.slug}.png`;
      const name = document.createElement('div');
      name.className = 'name';
      name.textContent = r.name || r.slug;
      card.appendChild(img);
      card.appendChild(name);
      card.onclick = () => {
        __selectedRole = { slug: r.slug, name: r.name || r.slug };
        confirmText.textContent = `确认与“${__selectedRole.name}”开始新的会话？`;
        openModal(confirmModal);
      };
      roleGrid.appendChild(card);
    });
  } catch (e) {
    roleGrid.innerHTML = '<div style="color:tomato;">角色加载失败</div>';
  }
};

const groupRoleModal = document.getElementById('groupRoleModal');
const groupRoleGrid = document.getElementById('groupRoleGrid');
const confirmGroupCreateBtn = document.getElementById('confirmGroupCreateBtn');
let __selectedGroup = new Set();

chooseGroupBtn.onclick = () => {
  closeModal(typeModal);
  openModal(groupRoleModal);
  __selectedGroup = new Set();
  groupRoleGrid.innerHTML = '<div style="color:var(--muted);padding:8px;">加载角色中...</div>';
  fetch('/api/role-cards').then(r => r.json()).then(roles => {
    groupRoleGrid.innerHTML = '';
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
        if (__selectedGroup.has(r.slug)) { __selectedGroup.delete(r.slug); card.style.outline=''; }
        else { if (__selectedGroup.size >= 3) { alert('最多选择3人'); return; } __selectedGroup.add(r.slug); card.style.outline='2px solid var(--accent)'; }
      };
      groupRoleGrid.appendChild(card);
    });
  }).catch(()=>{ groupRoleGrid.innerHTML = '<div style="color:tomato;">角色加载失败</div>'; });
};

confirmGroupCreateBtn.onclick = async () => {
  if (!__selectedGroup.size) { alert('请至少选择1个参与者'); return; }
  const selected = Array.from(__selectedGroup);
  try {
    const participants = selected.map((slug, i) => ({ roleCardId: slug, name: slug.toUpperCase(), agentId: `agent-${i+1}` }));
    const resp = await fetch('/api/group-conversations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ participants }) });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    closeModal(groupRoleModal);
    // switch to group mode and open (using exposed helpers)
    if (window.__groupAPI) {
      window.__groupAPI.setActive(data.id);
      await window.__groupAPI.loadConversations();
      await window.__groupAPI.loadMessages();
      const multiBtn = document.getElementById('multiChatBtn');
      const singleBtn = document.getElementById('singleChatBtn');
      const multiP = document.getElementById('multi-panel');
      const singleP = document.getElementById('single-panel');
      multiP.style.display=''; singleP.style.display='none'; multiBtn.classList.add('active'); singleBtn.classList.remove('active');
    } else {
      // fallback
      window.location.reload();
    }
  } catch (e) {
    alert('创建群聊失败: ' + (e.message || e));
  }
};

confirmCreateBtn.onclick = async () => {
  if (!__selectedRole) return;
  // 创建角色会话：调用后端 /api/role-conversations
  try {
    const resp = await fetch('/api/role-conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roleCardId: __selectedRole.slug, title: `与${__selectedRole.name}的对话` })
    });
    if (!resp.ok) throw new Error(await resp.text());
    await resp.json();
    // 关闭弹窗并刷新（新会话会在顶部）
    closeModal(confirmModal);
    closeModal(roleModal);
    window.location.reload();
  } catch (err) {
    alert('创建会话失败: ' + (err.message || err));
  }
};
