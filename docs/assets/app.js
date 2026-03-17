/* ──────────────────────────────────────────
   货币金融学知识图谱问答系统 · app.js
   Phase 1  |  GitHub Pages + Coze SDK
   ────────────────────────────────────────── */

const HEALTH_URL   = 'https://kg-plugin-production.up.railway.app/health';
const SESSION_ID   = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);

// ── Coze SDK 客户端（Phase 2 可绑定消息事件）──
let chatClient = null;
let sdkBtnRef  = null;   // SDK 创建的 asstBtn 引用（MO 捕获后隐藏）
let chatOpen   = false;

// ── 常见问题数组 ──────────────────────────────
const EXAMPLE_QUESTIONS = [
  {
    topic: 'policy',
    label: '货币政策',
    text: '央行降息对通货膨胀有什么影响？',
    hint: '多跳推理：利率→投资→总需求→价格水平',
  },
  {
    topic: 'policy',
    label: '货币政策',
    text: '货币政策的传导机制是什么？',
    hint: null,
  },
  {
    topic: 'inflation',
    label: '通货膨胀',
    text: '通货膨胀和失业率之间是什么关系？',
    hint: '菲利普斯曲线',
  },
  {
    topic: 'rate',
    label: '利率',
    text: '实际利率和名义利率有什么区别？',
    hint: '费雪效应',
  },
  {
    topic: 'bank',
    label: '商业银行',
    text: '商业银行如何创造货币？',
    hint: '存款乘数效应',
  },
  {
    topic: 'intl',
    label: '国际金融',
    text: '汇率升值对出口有什么影响？',
    hint: 'J曲线效应',
  },
  {
    topic: 'supply',
    label: '货币供给',
    text: 'M1和M2的区别是什么？',
    hint: null,
  },
  {
    topic: 'central',
    label: '中央银行',
    text: '中央银行有哪些货币政策工具？',
    hint: null,
  },
];

// 主题 → CSS tag 类名映射
const TOPIC_CLASS = {
  policy:    'tag-policy',
  inflation: 'tag-inflation',
  rate:      'tag-rate',
  bank:      'tag-bank',
  intl:      'tag-intl',
  supply:    'tag-supply',
  central:   'tag-central',
};

// ── 概念速查词条 ──────────────────────────────
const CONCEPTS = [
  '货币乘数', '公开市场操作', '存款准备金率', '菲利普斯曲线',
  '泰勒规则', '流动性陷阱', '货币数量论', '利率平价',
  '购买力平价', '货币政策传导', '通货膨胀目标制', '汇率制度',
  '最优货币区', 'M1/M2', '货币创造',
];

// ── 初始化 ────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  document.getElementById('theme-toggle').addEventListener('click', toggleTheme);
  initCoze();
  renderQuestions('all');
  bindTagFilters();
  bindFeedback();
  checkHealth();
  renderConcepts();
  renderRecentQuestions();
  initCollapsible();
});

// ── 深色模式 ──────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem('kg_theme');
  // Default: dark
  const theme = saved !== null ? saved : 'dark';
  if (theme === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.setAttribute('data-theme', '');
  }
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
}

function toggleTheme() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  document.documentElement.setAttribute('data-theme', isDark ? '' : 'dark');
  localStorage.setItem('kg_theme', isDark ? 'light' : 'dark');
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.textContent = isDark ? '🌙' : '☀️';
}

// ── Coze SDK 初始化 ───────────────────────────
async function initCoze() {
  const el = document.getElementById('chat-container');
  if (!el || typeof CozeWebSDK === 'undefined') {
    console.warn('CozeWebSDK not loaded');
    return;
  }

  // 从后端获取 token，PAT 不暴露在前端源码中
  let token;
  try {
    const res = await fetch('https://kg-plugin-production.up.railway.app/coze-token');
    const data = await res.json();
    token = data.token;
  } catch (e) {
    console.error('Failed to fetch Coze token:', e);
    return;
  }

  // 每个标签页生成一次 user_id（sessionStorage 关闭标签后自动清空）
  // 关闭标签重开 → 新 UUID → SDK 创建全新会话；刷新 → 保留同一 UUID → 继续会话
  let sessionUserId = sessionStorage.getItem('coze_user_id');
  const isNewTab = !sessionUserId;
  if (isNewTab) {
    sessionUserId = crypto.randomUUID
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2) + Date.now().toString(36);
    sessionStorage.setItem('coze_user_id', sessionUserId);
    // 新标签页：清除 SDK 缓存的 conversation_id，确保会话不延续
    _clearCozeConversationCache();
  }

  try {
    watchForSdkBtn();   // 必须在构造之前设好，SDK 构造时同步插入容器
    chatClient = new CozeWebSDK.WebChatClient({
      config: {
        bot_id: '7613708062620696585',
      },
      user: {
        user_id: sessionUserId,   // 绑定会话到标签页级别
      },
      auth: {
        type: 'token',
        token: token,
        onRefreshToken: async () => {
          const res = await fetch('https://kg-plugin-production.up.railway.app/coze-token');
          const data = await res.json();
          return data.token;
        },
      },
      ui: {
        base: { layout: 'pc', lang: 'zh-CN' },
        asstBtn: { isNeed: true },
        chatBot: {
          title: '货币金融学助手',
          uploadable: false,
          el: el,
        },
        footer: { isShow: false },
      },
    });
    // 新标签页：尝试通过 API 主动创建新会话（覆盖 SDK 持久化的旧 conversation_id）
    if (isNewTab && typeof chatClient.createConversation === 'function') {
      try {
        await chatClient.createConversation();
        console.log('[kg] createConversation() succeeded');
      } catch (e) {
        console.warn('[kg] createConversation() failed (non-fatal):', e);
      }
    }

    // 短暂 delay 确保 SDK 完成内部 mount
    setTimeout(() => {
      openCozeChat();
    }, 300);
  } catch (e) {
    console.error('CozeWebSDK init error:', e);
    // 失败降级：显示启动卡片，按钮改为"重试连接"
    const launchEl = document.getElementById('chat-launch');
    if (launchEl) launchEl.style.display = 'flex';
    const launchBtn = document.getElementById('chat-launch-btn');
    if (launchBtn) {
      launchBtn.textContent = '重试连接';
      launchBtn.onclick = () => { launchEl.style.display = 'none'; initCoze(); };
    }
  }
}

// ── 清除 Coze SDK 缓存的 conversation（新标签页调用）──
function _clearCozeConversationCache() {
  // SDK 在 localStorage 中以 bot_id 或 "coze"/"conversation" 为前缀存储会话
  const BOT_ID = '7613708062620696585';
  const patterns = ['coze', 'conversation', BOT_ID, 'chat_', 'session_'];
  const toDelete = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key) continue;
    const lower = key.toLowerCase();
    if (patterns.some(p => lower.includes(p.toLowerCase()))) {
      toDelete.push(key);
    }
  }
  toDelete.forEach(k => {
    console.log('[kg] clearing Coze cache key:', k);
    localStorage.removeItem(k);
  });
  if (toDelete.length === 0) {
    console.log('[kg] no Coze cache keys found in localStorage');
  }
}

// ── 捕获 SDK 浮钮容器（监听 body 直接子节点）──
function watchForSdkBtn() {
  const ownEls = new Set([
    document.querySelector('.site-header'),
    document.querySelector('.app-body'),
    document.getElementById('graph-panel'),
    document.querySelector('.site-footer'),
    document.getElementById('toast'),
  ]);
  // SCRIPT / TEXTAREA 等不是浮钮容器
  const skipTags = new Set(['SCRIPT', 'STYLE', 'LINK', 'NOSCRIPT', 'TEXTAREA']);

  const tryCapture = (node) => {
    if (node.nodeType !== 1) return false;
    if (skipTags.has(node.tagName)) return false;
    if (ownEls.has(node)) return false;
    if (node.parentElement !== document.body) return false;
    sdkBtnRef = node;
    hideSdkContainer(node);
    return true;
  };

  // 立即扫描：SDK 构造时可能已同步插入容器
  for (const child of document.body.children) {
    if (tryCapture(child)) return;
  }

  // 未命中则继续用 MO 等待
  const mo = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (tryCapture(node)) { mo.disconnect(); return; }
      }
    }
  });
  mo.observe(document.body, { childList: true });
}

function hideSdkContainer(el) {
  el.style.setProperty('opacity', '0', 'important');
  el.style.setProperty('pointer-events', 'none', 'important');
}

// ── 打开聊天 ──────────────────────────────────────
function openCozeChat() {
  if (sdkBtnRef) {
    sdkBtnRef.style.removeProperty('opacity');
    sdkBtnRef.style.removeProperty('pointer-events');
  }
  document.getElementById('chat-launch').style.display = 'none';
  document.getElementById('chat-wrapper').style.display = 'flex';
  chatClient?.showChatBot();
  updateToggleBtn(true);
}

// ── 切换聊天面板（关闭后可重开）──────────────────
function toggleChat() {
  if (chatOpen) {
    document.getElementById('chat-wrapper').style.display = 'none';
    document.getElementById('chat-launch').style.display = 'flex';
    updateToggleBtn(false);
  } else {
    openCozeChat();
  }
}

function updateToggleBtn(open) {
  chatOpen = open;
  const btn = document.getElementById('chat-toggle-btn');
  if (btn) btn.textContent = open ? '关闭对话' : '打开对话';
}

// ── 尝试多种 sendMessage 格式（兼容不同 SDK 版本）─────
function _trySdkSend(question) {
  if (!chatClient || typeof chatClient.sendMessage !== 'function') return false;

  // 格式 1：{ content }（beta.10 文档格式）
  try {
    chatClient.sendMessage({ content: question });
    return true;
  } catch (e1) {
    console.warn('[kg] sendMessage({content}) threw:', e1);
  }

  // 格式 2：纯字符串
  try {
    chatClient.sendMessage(question);
    return true;
  } catch (e2) {
    console.warn('[kg] sendMessage(string) threw:', e2);
  }

  // 格式 3：{ type, content }
  try {
    chatClient.sendMessage({ type: 'text', content: question });
    return true;
  } catch (e3) {
    console.warn('[kg] sendMessage({type,content}) threw:', e3);
  }

  return false;
}

// ── DOM 降级：模拟输入 + 回车（ErrorBoundary 兜底）──
function _sendViaDom(text) {
  const selectors = [
    '[class*="chat"] textarea',
    '[class*="chat"] input[type="text"]',
    '#chat-container textarea',
    '#chat-container input[type="text"]',
    'textarea',
  ];
  for (const sel of selectors) {
    const input = document.querySelector(sel);
    if (!input) continue;
    try {
      const proto = input.tagName === 'TEXTAREA'
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype;
      const nativeSet = Object.getOwnPropertyDescriptor(proto, 'value');
      if (nativeSet) nativeSet.set.call(input, text);
      else input.value = text;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true }));
      input.dispatchEvent(new KeyboardEvent('keyup',  { key: 'Enter', keyCode: 13, bubbles: true }));
      console.log('[kg] DOM send via:', sel);
      return true;
    } catch (e) {
      console.warn('[kg] DOM send failed for', sel, e);
    }
  }
  return false;
}

// ── 发送到聊天框（带剪贴板降级）────────────────
function sendToChat(question) {
  if (chatClient) {
    const doSend = () => {
      const sdkOk = _trySdkSend(question);
      if (!sdkOk) {
        console.warn('[kg] SDK send failed, trying DOM fallback');
        const domOk = _sendViaDom(question);
        if (!domOk) {
          navigator.clipboard.writeText(question)
            .then(() => showToast('已复制到剪贴板，请粘贴到对话框'))
            .catch(() => showToast('请手动复制：' + question));
        }
      }
      document.getElementById('chat-container')
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    if (!chatOpen) {
      openCozeChat();
      // 等待聊天框挂载完成后再发送（SDK showChatBot 是异步的）
      setTimeout(doSend, 600);
    } else {
      doSend();
    }
  } else {
    navigator.clipboard.writeText(question)
      .then(() => showToast('已复制到剪贴板，请粘贴到对话框'))
      .catch(() => showToast('请手动复制：' + question));
  }
  saveRecentQuestion(question);
  renderRecentQuestions();
}

// ── 渲染常见问题卡片 ──────────────────────────
function renderQuestions(filterTopic) {
  const list = document.getElementById('question-list');
  if (!list) return;
  list.innerHTML = '';

  const filtered = filterTopic === 'all'
    ? EXAMPLE_QUESTIONS
    : EXAMPLE_QUESTIONS.filter(q => q.topic === filterTopic);

  filtered.forEach((q, idx) => {
    const card = document.createElement('div');
    card.className = 'question-card';
    card.style.animationDelay = `${idx * 40}ms`;
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-label', '点击发送问题：' + q.text);

    const tagClass = TOPIC_CLASS[q.topic] || '';
    card.innerHTML = `
      <span class="question-topic-badge ${tagClass}">${q.label}</span>
      <span class="question-text">${q.text}</span>
      ${q.hint ? `<span class="question-hint">💡 ${q.hint}</span>` : ''}
    `;

    card.addEventListener('click',   () => sendToChat(q.text));
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') sendToChat(q.text); });

    list.appendChild(card);
  });

  if (filtered.length === 0) {
    list.innerHTML = '<div style="color:var(--text-dim);font-size:11px;padding:8px 0;">暂无该主题常见问题</div>';
  }

  // 更新搜索计数并重新绑定搜索
  updateQuestionCount();
  bindSearch();
}

// ── 常见问题搜索 ──────────────────────────────
function bindSearch() {
  const input = document.getElementById('question-search');
  if (!input) return;
  // 替换旧监听（避免重复绑定）
  const newInput = input.cloneNode(true);
  input.parentNode.replaceChild(newInput, input);
  newInput.addEventListener('input', () => {
    const keyword = newInput.value.trim().toLowerCase();
    const cards = document.querySelectorAll('#question-list .question-card');
    let visible = 0;
    cards.forEach(card => {
      const text = card.querySelector('.question-text')?.textContent.toLowerCase() || '';
      const match = !keyword || text.includes(keyword);
      card.classList.toggle('hidden', !match);
      if (match) visible++;
    });
    const countEl = document.getElementById('question-count');
    if (countEl) {
      countEl.textContent = keyword ? `${visible} / ${cards.length} 条` : `${cards.length} 条`;
    }
  });
}

function updateQuestionCount() {
  const cards = document.querySelectorAll('#question-list .question-card');
  const countEl = document.getElementById('question-count');
  if (countEl) countEl.textContent = `${cards.length} 条`;
}

// ── 标签过滤 ──────────────────────────────────
function bindTagFilters() {
  document.querySelectorAll('.topic-tag').forEach(tag => {
    tag.addEventListener('click', () => {
      document.querySelectorAll('.topic-tag').forEach(t => t.classList.remove('active'));
      tag.classList.add('active');
      // 清空搜索框
      const searchInput = document.getElementById('question-search');
      if (searchInput) searchInput.value = '';
      renderQuestions(tag.dataset.topic);
    });
  });
}

// ── 反馈机制 ──────────────────────────────────
function bindFeedback() {
  document.querySelectorAll('.feedback-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const vote = btn.dataset.vote;
      submitFeedback(vote);
      document.querySelectorAll('.feedback-btn').forEach(b => b.disabled = true);
      const thanks = document.getElementById('feedback-thanks');
      if (thanks) { thanks.style.display = 'inline'; }
    });
  });
}

function submitFeedback(vote) {
  const entry = {
    timestamp: new Date().toISOString(),
    vote,
    sessionId: SESSION_ID,
    question: null,   // Phase 2: 填入最后一次发送的问题
    kgPath: null,     // Phase 2: 填入知识图谱推理路径
  };
  try {
    const log = JSON.parse(localStorage.getItem('kg_feedback') || '[]');
    log.push(entry);
    localStorage.setItem('kg_feedback', JSON.stringify(log));
  } catch (e) {
    console.warn('localStorage write failed:', e);
  }
}

// ── 概念速查 ──────────────────────────────────
function renderConcepts() {
  const container = document.getElementById('concept-chips');
  if (!container) return;
  CONCEPTS.forEach(c => {
    const chip = document.createElement('button');
    chip.className = 'concept-chip';
    chip.textContent = c;
    chip.onclick = () => sendToChat(`请解释一下：${c}`);
    container.appendChild(chip);
  });
}

// ── 最近提问记录 ──────────────────────────────
function saveRecentQuestion(text) {
  try {
    const list = JSON.parse(sessionStorage.getItem('kg_recent') || '[]');
    list.unshift({ text, timestamp: new Date().toISOString() });
    // 最多保留 10 条，去重（保留最新）
    const seen = new Set();
    const deduped = list.filter(item => {
      if (seen.has(item.text)) return false;
      seen.add(item.text);
      return true;
    }).slice(0, 10);
    sessionStorage.setItem('kg_recent', JSON.stringify(deduped));
  } catch (e) {
    console.warn('sessionStorage write failed:', e);
  }
}

function renderRecentQuestions() {
  const card = document.getElementById('recent-card');
  const listEl = document.getElementById('recent-list');
  if (!card || !listEl) return;

  let list = [];
  try {
    list = JSON.parse(sessionStorage.getItem('kg_recent') || '[]');
  } catch (e) { /* ignore */ }

  if (list.length === 0) {
    card.style.display = 'none';
    return;
  }

  card.style.display = '';
  listEl.innerHTML = '';

  list.forEach((item, idx) => {
    const row = document.createElement('div');
    row.className = 'recent-item';

    const timeStr = formatRecentTime(item.timestamp);

    row.innerHTML = `
      <span class="recent-item-text" title="${escapeHtml(item.text)}">${escapeHtml(item.text)}</span>
      <span class="recent-item-time">${timeStr}</span>
      <button class="recent-item-del" title="删除" aria-label="删除该记录">×</button>
    `;

    row.querySelector('.recent-item-text').addEventListener('click', () => sendToChat(item.text));
    row.querySelector('.recent-item-del').addEventListener('click', (e) => {
      e.stopPropagation();
      deleteRecentQuestion(idx);
    });

    listEl.appendChild(row);
  });
}

function deleteRecentQuestion(idx) {
  try {
    const list = JSON.parse(sessionStorage.getItem('kg_recent') || '[]');
    list.splice(idx, 1);
    sessionStorage.setItem('kg_recent', JSON.stringify(list));
  } catch (e) { /* ignore */ }
  renderRecentQuestions();
}

function formatRecentTime(iso) {
  try {
    const d = new Date(iso);
    const h = String(d.getHours()).padStart(2, '0');
    const m = String(d.getMinutes()).padStart(2, '0');
    return `${h}:${m}`;
  } catch { return ''; }
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── 健康状态检测 ──────────────────────────────
async function checkHealth() {
  const dot   = document.getElementById('status-dot');
  const label = document.getElementById('status-label');
  if (!dot || !label) return;

  try {
    const res = await fetch(HEALTH_URL, { signal: AbortSignal.timeout(5000) });
    if (res.ok) {
      dot.classList.add('online');
      dot.classList.remove('offline');
      label.textContent = '服务正常';
    } else {
      throw new Error('non-ok');
    }
  } catch {
    dot.classList.add('offline');
    dot.classList.remove('online');
    label.textContent = '服务异常';
  }
}

// ── Toast 提示 ────────────────────────────────
function showToast(msg) {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    toast.className = 'toast';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2800);
}

// ── 卡片折叠/展开 ─────────────────────────────
function initCollapsible() {
  document.querySelectorAll('.card.collapsible > .card-title').forEach(title => {
    title.addEventListener('click', () => {
      const card = title.closest('.card');
      card.classList.toggle('collapsed');
    });
  });
}

// [Phase 3] 用户登录后在此处显示 #user-area，绑定 userId 到反馈/记录数据
// function initUserArea(userId) { ... }
