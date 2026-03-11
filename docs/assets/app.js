/* ──────────────────────────────────────────
   货币金融学知识图谱问答系统 · app.js
   Phase 1  |  GitHub Pages + Coze SDK
   ────────────────────────────────────────── */

const HEALTH_URL   = 'https://kg-plugin-production.up.railway.app/health';
const SESSION_ID   = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);

// ── Coze SDK 客户端（Phase 2 可绑定消息事件）──
let chatClient = null;

// ── 示例问题数组 ──────────────────────────────
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

// ── 初始化 ────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initCoze();
  renderQuestions('all');
  bindTagFilters();
  bindFeedback();
  checkHealth();
});

// ── Coze SDK 初始化 ───────────────────────────
function initCoze() {
  const el = document.getElementById('chat-container');
  if (!el || typeof CozeWebSDK === 'undefined') {
    console.warn('CozeWebSDK not loaded');
    return;
  }

  try {
    chatClient = new CozeWebSDK.WebChatClient({
      config: {
        type: 'bot',
        bot_id: '7613708062620696585',
        isIframe: true,
      },
      auth: {
        type: 'token',
        token: 'pat_2cQHMTQPJnWoYSTzuYUeXnAU3HKqhfNeNN5DKgNd9UcyKcHnWJ7ItTfuHpHqS8wG',
        onRefreshToken: async () => 'pat_2cQHMTQPJnWoYSTzuYUeXnAU3HKqhfNeNN5DKgNd9UcyKcHnWJ7ItTfuHpHqS8wG',
      },
      ui: {
        base: {
          layout: 'pc',
          lang: 'zh-CN',
        },
        header: {
          isShow: true,
          isNeedClose: false,
        },
        asstBtn: {
          isNeed: true,
        },
        chatBot: {
          title: '货币金融学助手',
          uploadable: false,
          el: el,
        },
        footer: {
          isShow: false,
        },
      },
    });
    // 尝试自动展开聊天窗口
    setTimeout(() => {
      try {
        if (typeof chatClient.open === 'function') chatClient.open();
        else if (typeof chatClient.show === 'function') chatClient.show();
        else if (typeof chatClient.showChat === 'function') chatClient.showChat();
      } catch (_) {}
    }, 400);
  } catch (e) {
    console.error('CozeWebSDK init error:', e);
  }
}

// ── 发送到聊天框（带剪贴板降级）────────────────
function sendToChat(question) {
  if (chatClient && typeof chatClient.sendMessage === 'function') {
    chatClient.sendMessage({ content: question });
    document.getElementById('chat-container')
      .scrollIntoView({ behavior: 'smooth', block: 'start' });
  } else {
    navigator.clipboard.writeText(question)
      .then(() => showToast('已复制到剪贴板，请粘贴到对话框'))
      .catch(() => showToast('请手动复制：' + question));
  }
}

// ── 渲染示例问题卡片 ──────────────────────────
function renderQuestions(filterTopic) {
  const list = document.getElementById('question-list');
  if (!list) return;
  list.innerHTML = '';

  const filtered = filterTopic === 'all'
    ? EXAMPLE_QUESTIONS
    : EXAMPLE_QUESTIONS.filter(q => q.topic === filterTopic);

  filtered.forEach(q => {
    const card = document.createElement('div');
    card.className = 'question-card';
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
    list.innerHTML = '<div style="color:var(--text-dim);font-size:11px;padding:8px 0;">暂无该主题示例问题</div>';
  }
}

// ── 标签过滤 ──────────────────────────────────
function bindTagFilters() {
  document.querySelectorAll('.topic-tag').forEach(tag => {
    tag.addEventListener('click', () => {
      document.querySelectorAll('.topic-tag').forEach(t => t.classList.remove('active'));
      tag.classList.add('active');
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
