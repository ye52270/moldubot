/* ========================================
   MolduBot – Taskpane Chat Client
   ======================================== */

(function () {
  let isSending = false;

  function byId(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function scrollToBottom() {
    const chatArea = byId('chatArea');
    if (!chatArea) return;
    chatArea.scrollTop = chatArea.scrollHeight;
  }

  function removeWelcomeStateIfExists() {
    const welcome = byId('welcomeState');
    if (welcome) welcome.remove();
  }

  function addMessage(role, text) {
    const chatArea = byId('chatArea');
    if (!chatArea) return;

    removeWelcomeStateIfExists();

    const safeRole = role === 'user' ? 'user' : 'assistant';
    const html =
      '<div class="message ' + safeRole + '">' +
      '  <div class="msg-body">' + escapeHtml(text) + '</div>' +
      '</div>';

    chatArea.insertAdjacentHTML('beforeend', html);
    scrollToBottom();
  }

  function resetSession() {
    const chatArea = byId('chatArea');
    if (!chatArea) return;

    chatArea.innerHTML =
      '<div id="welcomeState" class="welcome-state">' +
      '  <div class="welcome-icon">' +
      '    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
      '      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>' +
      '    </svg>' +
      '  </div>' +
      '  <h2 class="welcome-title">안녕하세요.무엇을 도와 드릴까요?</h2>' +
      '  <p class="welcome-desc">메일 요약, 일정 등록, 회의실 예약 등 다양한 업무를 지원합니다.</p>' +
      '</div>';
  }

  function setSendingState(nextState) {
    const sendBtn = byId('sendBtn');
    const input = byId('chatInput');
    isSending = Boolean(nextState);
    if (sendBtn) sendBtn.disabled = isSending;
    if (input) input.disabled = isSending;
  }

  async function requestAssistantReply(message) {
    const response = await fetch('/search/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: message }),
    });

    if (!response.ok) {
      throw new Error('chat request failed: ' + response.status);
    }

    const payload = await response.json();
    return String(payload && payload.answer ? payload.answer : '').trim() || '응답을 생성하지 못했습니다.';
  }

  async function sendMessage() {
    const input = byId('chatInput');
    if (!input || isSending) return;
    const text = String(input.value || '').trim();
    if (!text) return;

    addMessage('user', text);
    input.value = '';

    setSendingState(true);
    try {
      const assistantReply = await requestAssistantReply(text);
      addMessage('assistant', assistantReply);
    } catch (error) {
      addMessage('assistant', '응답을 가져오는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
    } finally {
      setSendingState(false);
      input.focus();
    }
  }

  function bindUi() {
    const sendBtn = byId('sendBtn');
    const input = byId('chatInput');
    const newSessionBtn = byId('newSessionBtn');
    const marketPlusBtn = byId('marketPlusBtn');

    if (sendBtn) {
      sendBtn.addEventListener('click', sendMessage);
    }

    if (input) {
      input.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' && !event.shiftKey) {
          event.preventDefault();
          sendMessage();
        }
      });
    }

    if (newSessionBtn) {
      newSessionBtn.addEventListener('click', resetSession);
    }

    if (marketPlusBtn) {
      marketPlusBtn.addEventListener('click', function () {
        addMessage('assistant', '현재 마켓 기능은 준비 중입니다.');
      });
    }
  }

  function bootstrap() {
    bindUi();
  }

  if (window.Office && typeof window.Office.onReady === 'function') {
    window.Office.onReady(function () {
      bootstrap();
    });
  } else {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', bootstrap);
    } else {
      bootstrap();
    }
  }
})();
