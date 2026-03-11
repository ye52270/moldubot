/* ========================================
   MolduBot – Taskpane Message Interactions
   ======================================== */

(function initTaskpaneInteractions(global) {
  function create(options) {
    const byId = options.byId;
    const logClientEvent = options.logClientEvent;
    const copiedResetMs = Number(options.copiedResetMs || 1300);
    const addMessage = options.addMessage;
    const setSendingState = options.setSendingState;
    const requestAssistantReply = options.requestAssistantReply;
    const openEvidenceMail = options.openEvidenceMail;
    const showClarificationToast = options.showClarificationToast;
    const clearClarificationToast = options.clearClarificationToast;
    let popoverDismissBound = false;
    const POPOVER_SELECTOR = 'details.inline-evidence-popover[open], details.web-source-popover[open]';

    function closeEvidencePopovers(exceptNode) {
      if (typeof document === 'undefined' || typeof document.querySelectorAll !== 'function') return;
      const openPopovers = document.querySelectorAll(POPOVER_SELECTOR);
      openPopovers.forEach(function (node) {
        if (!node || (exceptNode && node === exceptNode)) return;
        if (typeof node.removeAttribute === 'function') {
          node.removeAttribute('open');
        }
      });
    }

    function bindPopoverDismissHandlers() {
      if (popoverDismissBound) return;
      if (typeof document === 'undefined' || typeof document.addEventListener !== 'function') return;
      document.addEventListener('click', function (event) {
        const target = event && event.target ? event.target : null;
        const inPopover = target && target.closest
          ? target.closest('details.inline-evidence-popover, details.web-source-popover')
          : null;
        closeEvidencePopovers(inPopover);
      });
      document.addEventListener('keydown', function (event) {
        if (!event || event.key !== 'Escape') return;
        closeEvidencePopovers(null);
      });
      popoverDismissBound = true;
    }

    function escapeHtml(text) {
      return String(text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function showRawAnswerModal(rawText, renderedText, rawModelText, rawModelContentText) {
      var raw = String(rawText || '').trim();
      var rendered = String(renderedText || '').trim();
      var rawModel = String(rawModelText || '').trim();
      var rawModelContent = String(rawModelContentText || '').trim();
      if (!raw && !rawModel && !rawModelContent) return;
      if (typeof document === 'undefined' || !document.body || typeof document.createElement !== 'function') {
        try {
          window.alert(rawModelContent || rawModel || raw);
        } catch (_error) {
          logClientEvent('warning', 'raw_answer_modal_fallback_failed', {});
        }
        return;
      }
      var overlay = document.createElement('div');
      overlay.className = 'raw-answer-modal';
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.35);z-index:9999;display:flex;align-items:center;justify-content:center;padding:16px;';
      overlay.innerHTML =
        '<div style="width:min(920px,96vw);max-height:88vh;overflow:auto;background:#fff;border:1px solid #ddd;border-radius:14px;padding:14px 14px 16px;">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
        + '<strong style="font-size:16px;">원문/가공 비교</strong>'
        + '<button type="button" data-action="close-raw-modal" style="border:1px solid #ddd;background:#fff;border-radius:8px;padding:6px 10px;cursor:pointer;">닫기</button>'
        + '</div>'
        + '<div style="display:grid;grid-template-columns:1fr;gap:10px;">'
        + '<section><div style="font-weight:600;margin-bottom:6px;">가공 답변</div><pre style="white-space:pre-wrap;border:1px solid #eee;border-radius:10px;padding:10px;background:#fafafa;">' + escapeHtml(rendered || '(없음)') + '</pre></section>'
        + '<section><div style="font-weight:600;margin-bottom:6px;">에이전트 최종 텍스트(raw_answer)</div><pre style="white-space:pre-wrap;border:1px solid #eee;border-radius:10px;padding:10px;background:#fcfcfc;">' + escapeHtml(raw || '(없음)') + '</pre></section>'
        + '<section><div style="font-weight:600;margin-bottom:6px;">모델 직출력(raw_model_output)</div><pre style="white-space:pre-wrap;border:1px solid #eee;border-radius:10px;padding:10px;background:#f8fbff;">' + escapeHtml(rawModel || '(없음)') + '</pre></section>'
        + '<section><div style="font-weight:600;margin-bottom:6px;">모델 content 원본(raw_model_content)</div><pre style="white-space:pre-wrap;border:1px solid #eee;border-radius:10px;padding:10px;background:#f5f9ff;">' + escapeHtml(rawModelContent || '(없음)') + '</pre></section>'
        + '</div></div>';
      overlay.addEventListener('click', function (event) {
        var target = event && event.target ? event.target : null;
        if (target === overlay || (target && target.closest && target.closest('[data-action="close-raw-modal"]'))) {
          overlay.remove();
        }
      });
      document.body.appendChild(overlay);
    }

    async function copyToClipboard(text) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        return;
      }
      const area = document.createElement('textarea');
      area.value = text;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.focus();
      area.select();
      document.execCommand('copy');
      area.remove();
    }

    function markCopied(button) {
      if (!button) return;
      button.dataset.copied = 'true';
      setTimeout(function () {
        button.dataset.copied = 'false';
      }, copiedResetMs);
    }

    function markFeedback(button) {
      if (!button) return;
      const container = button.closest('.assistant-actions');
      if (!container) return;
      const buttons = container.querySelectorAll('.msg-action-btn[data-action="up"], .msg-action-btn[data-action="down"]');
      buttons.forEach(function (node) {
        node.dataset.active = node === button ? (node.dataset.active === 'true' ? 'false' : 'true') : 'false';
      });
    }

    function handleScopeSelect(button) {
      if (!button) return;
      const originalQuery = String(button.dataset.originalQuery || '').trim();
      const scope = String(button.dataset.scope || '').trim();
      const scopeLabel = String(button.dataset.scopeLabel || scope).trim();
      if (!originalQuery || !scope) return;
      button.disabled = true;
      if (typeof clearClarificationToast === 'function') {
        clearClarificationToast();
      }
      setSendingState(true);
      addMessage('user', '질문 범위 선택: ' + scopeLabel);
      requestAssistantReply(originalQuery, null, { scope: scope }).then(function (assistantPayload) {
        const answer = assistantPayload && assistantPayload.answer ? assistantPayload.answer : '응답을 생성하지 못했습니다.';
        const metadata = assistantPayload && assistantPayload.metadata ? assistantPayload.metadata : {};
        addMessage('assistant', answer, metadata);
        if (typeof showClarificationToast === 'function') {
          showClarificationToast(metadata);
        }
      }).catch(function () {
        addMessage('assistant', '응답을 가져오는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
      }).finally(function () {
        setSendingState(false);
        button.disabled = false;
        const input = byId('chatInput');
        if (input) input.focus();
      });
    }

    function findActionButtonFromEvent(event) {
      const target = event && event.target ? event.target : null;
      if (!target || !target.closest) return null;
      return target.closest(
        '.msg-action-btn, .evidence-open-btn, [data-action="selected-mail-open"], [data-action="report-open-file"], [data-action="section-toggle"], [data-action="scope-select"]'
      );
    }

    function handleClick(event) {
      const button = findActionButtonFromEvent(event);
      if (!button) return;
      if (String(button.dataset.action || '') === 'section-toggle') {
        const sectionNode = button.closest('.summary-section.section-major');
        if (!sectionNode) return;
        const collapsed = sectionNode.classList.toggle('is-collapsed');
        button.textContent = collapsed ? '펼치기' : '접기';
        button.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        return;
      }
      if (button.classList.contains('evidence-open-btn') || String(button.dataset.action || '') === 'selected-mail-open') {
        if (event && typeof event.preventDefault === 'function') {
          event.preventDefault();
        }
        const messageId = String(button.dataset.messageId || '').trim();
        if (!messageId) return;
        if (typeof openEvidenceMail === 'function') {
          openEvidenceMail(messageId).catch(function () {
            logClientEvent('warning', 'evidence_mail_open_failed', {
              message_id_present: Boolean(messageId),
            });
          });
        }
        return;
      }
      if (button.classList.contains('scope-choice-btn') || String(button.dataset.action || '') === 'scope-select') {
        handleScopeSelect(button);
        return;
      }
      if (String(button.dataset.action || '') === 'report-open-file') {
        const previewUrl = String(button.dataset.previewUrl || '').trim();
        const docxUrl = String(button.dataset.docxUrl || '').trim();
        const openUrl = previewUrl || docxUrl;
        if (!openUrl) return;
        window.open(openUrl, '_blank', 'noopener,noreferrer');
        return;
      }
      const messageNode = button.closest('.message');
      const bodyNode = messageNode ? messageNode.querySelector('.msg-body') : null;
      const rawNode = messageNode ? messageNode.querySelector('.msg-raw-answer') : null;
      const rawModelNode = messageNode ? messageNode.querySelector('.msg-raw-model-output') : null;
      const rawModelContentNode = messageNode ? messageNode.querySelector('.msg-raw-model-content') : null;
      const text = bodyNode ? String(bodyNode.textContent || '').trim() : '';
      const rawText = rawNode ? String(rawNode.textContent || '').trim() : '';
      const rawModelText = rawModelNode ? String(rawModelNode.textContent || '').trim() : '';
      const rawModelContentText = rawModelContentNode ? String(rawModelContentNode.textContent || '').trim() : '';
      const action = String(button.dataset.action || '');
      if (!action) return;

      if (action === 'raw') {
        if (!rawText && !rawModelText && !rawModelContentText) return;
        showRawAnswerModal(rawText, text, rawModelText, rawModelContentText);
        return;
      }

      if (!text) return;

      if (action === 'copy') {
        copyToClipboard(text).then(function () {
          markCopied(button);
        }).catch(function () {
          logClientEvent('warning', 'copy_action_failed', { action: 'copy' });
        });
        return;
      }

      if (action === 'edit') {
        const input = byId('chatInput');
        if (input) {
          input.value = text;
          input.focus();
        }
        return;
      }

      if (action === 'retry') {
        setSendingState(true);
        requestAssistantReply(text).then(function (assistantPayload) {
          const answer = assistantPayload && assistantPayload.answer ? assistantPayload.answer : '응답을 생성하지 못했습니다.';
          const metadata = assistantPayload && assistantPayload.metadata ? assistantPayload.metadata : {};
          addMessage('assistant', answer, metadata);
          if (typeof showClarificationToast === 'function') {
            showClarificationToast(metadata);
          }
        }).catch(function () {
          addMessage('assistant', '응답을 가져오는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.');
        }).finally(function () {
          setSendingState(false);
          const input = byId('chatInput');
          if (input) input.focus();
        });
        return;
      }

      if (action === 'up' || action === 'down') {
        markFeedback(button);
        logClientEvent('info', 'assistant_feedback_clicked', {
          action: action,
          text_length: text.length,
        });
      }
    }

    function bindMessageActions() {
      const chatArea = byId('chatArea');
      bindPopoverDismissHandlers();
      const chatClickHandler = function (event) {
        const target = event && event.target ? event.target : null;
        const inPopover = target && target.closest
          ? target.closest('details.inline-evidence-popover, details.web-source-popover')
          : null;
        closeEvidencePopovers(inPopover);
        handleClick(event);
      };
      if (chatArea) {
        chatArea.addEventListener('click', chatClickHandler);
      }
      const toastHost = byId('clarificationToastHost');
      if (toastHost) {
        toastHost.addEventListener('click', handleClick);
      }
    }

    return {
      bindMessageActions: bindMessageActions,
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneInteractions = api;
})(typeof window !== 'undefined' ? window : globalThis);
