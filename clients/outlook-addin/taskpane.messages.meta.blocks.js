/* ========================================
   MolduBot – Taskpane Messages Meta Blocks
   ======================================== */

(function initTaskpaneMessagesMetaBlocks(global) {
  var SHOW_EVIDENCE_MAIL_BLOCK = false;

  function create(options) {
    var escapeHtml = options.escapeHtml;
    var escapeAttr = options.escapeAttr || options.escapeHtml;
    var applyInlineFormatting = options.applyInlineFormatting;
    var normalizeHeadingToken = options.normalizeHeadingToken;
    var normalizeDisplayName = options.normalizeDisplayName;
    var moduleLoaderFactory =
      (global && global.TaskpaneModuleLoader && typeof global.TaskpaneModuleLoader.create === 'function')
        ? global.TaskpaneModuleLoader
        : (typeof module !== 'undefined' && module.exports ? require('./taskpane.module_loader.js') : null);
    var moduleLoader = moduleLoaderFactory && typeof moduleLoaderFactory.create === 'function'
      ? moduleLoaderFactory.create()
      : { resolveModule: function () { return null; } };
    var resolveModule = moduleLoader.resolveModule;
    var actionBlocksModule = resolveModule('TaskpaneMessagesMetaActions', './taskpane.messages.meta_actions.js');
    var basicInfoModule = resolveModule('TaskpaneMessagesMetaBasicInfo', './taskpane.messages.meta.basic_info.js');
    var actionBlocks = actionBlocksModule && typeof actionBlocksModule.create === 'function'
      ? actionBlocksModule.create({
        escapeHtml: escapeHtml,
        escapeAttr: escapeAttr,
      })
      : null;
    var basicInfoBlocks = basicInfoModule && typeof basicInfoModule.create === 'function'
      ? basicInfoModule.create({
        applyInlineFormatting: applyInlineFormatting,
        normalizeHeadingToken: normalizeHeadingToken,
        normalizeDisplayName: normalizeDisplayName,
      })
      : null;

    function normalizeReplyDraftBodyText(raw) {
      var text = String(raw || '').trim();
      if (!text) return '';
      var fencedMatch = text.match(/```[^\n]*\n([\s\S]*?)```/);
      if (fencedMatch && fencedMatch[1]) {
        text = String(fencedMatch[1] || '').trim();
      }
      text = extractReplyBodyFromJsonText(text) || text;
      text = text.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n').replace(/\\r/g, '\n');
      var lines = text.split(/\r?\n/);
      while (lines.length) {
        var first = String(lines[0] || '').trim();
        if (!first) {
          lines.shift();
          continue;
        }
        if (/^(?:#{1,6}\s*)?회신\s*메일\s*본문\s*초안\s*[:：]?$/i.test(first)) {
          lines.shift();
          continue;
        }
        if (/^(?:#{1,6}\s*)?회신\s*본문\s*초안\s*[:：]?$/i.test(first)) {
          lines.shift();
          continue;
        }
        if (/^(?:[-=]{3,})$/.test(first)) {
          lines.shift();
          continue;
        }
        break;
      }
      var firstDraftLineIndex = -1;
      for (var idx = 0; idx < lines.length; idx += 1) {
        var line = String(lines[idx] || '').trim();
        if (!line) continue;
        if (/^(안녕하세요|안녕하십니까|감사합니다)[,.\s]?/.test(line)) {
          firstDraftLineIndex = idx;
          break;
        }
        if (/^[가-힣a-zA-Z0-9._-]+님[,.\s]*$/.test(line)) {
          firstDraftLineIndex = idx;
          break;
        }
      }
      if (firstDraftLineIndex > 0) {
        lines = lines.slice(firstDraftLineIndex);
      }
      return lines.join('\n').trim();
    }

    function extractReplyBodyFromJsonText(text) {
      var source = String(text || '').trim();
      if (!source) return '';
      if (source.indexOf('{') !== 0) return '';
      var parsed = safeJsonParse(source);
      if (!parsed || typeof parsed !== 'object') return '';
      var keys = ['reply_draft', 'draft_answer', 'additional_body', 'reply_body', 'response_body', 'answer'];
      for (var i = 0; i < keys.length; i += 1) {
        var key = keys[i];
        var value = parsed[key];
        if (typeof value === 'string' && String(value || '').trim()) {
          return String(value || '').trim();
        }
      }
      return '';
    }

    function safeJsonParse(source) {
      try {
        return JSON.parse(String(source || ''));
      } catch (_) {
        return null;
      }
    }

    function shouldHideEvidenceList(metadata) {
      var confirm = metadata && metadata.confirm && typeof metadata.confirm === 'object' ? metadata.confirm : null;
      if (!confirm || !confirm.required) return false;
      var actions = Array.isArray(confirm.actions) ? confirm.actions : [];
      var firstAction = actions[0] && typeof actions[0] === 'object' ? actions[0] : {};
      var actionName = String(firstAction.name || '').trim();
      return actionName === 'book_meeting_room' || actionName === 'create_outlook_todo';
    }

    function isCurrentMailResponse(metadata) {
      var data = metadata && typeof metadata === 'object' ? metadata : {};
      var queryType = String(data.query_type || '').trim().toLowerCase();
      if (queryType === 'current_mail') return true;
      var answerFormat = data.answer_format && typeof data.answer_format === 'object' ? data.answer_format : null;
      var formatType = String(answerFormat && answerFormat.format_type ? answerFormat.format_type : '').trim().toLowerCase();
      return formatType === 'current_mail';
    }

    function buildEvidenceListHtml(metadata) {
      if (!SHOW_EVIDENCE_MAIL_BLOCK) return '';
      if (isCurrentMailResponse(metadata)) return '';
      if (shouldHideEvidenceList(metadata)) return '';
      var evidenceList = metadata && Array.isArray(metadata.evidence_mails) ? metadata.evidence_mails : [];
      if (!evidenceList.length) return '';
      var items = evidenceList.map(function (item) {
        var messageId = String(item && item.message_id ? item.message_id : '').trim();
        var subject = String(item && item.subject ? item.subject : '제목 없음').trim();
        var receivedDate = String(item && item.received_date ? item.received_date : '-').trim();
        var senderNames = String(item && item.sender_names ? item.sender_names : '-').trim();
        var webLink = String(item && item.web_link ? item.web_link : '').trim();
        if (!messageId && !webLink) return '';
        return (
          '<li class="evidence-item">' +
          '<button type="button" class="evidence-open-btn" data-action="open-evidence-mail" data-message-id="' + escapeAttr(messageId) + '" data-web-link="' + escapeAttr(webLink) + '" title="메일 열기">' +
          '<span class="evidence-subject">' + escapeHtml(subject) + '</span>' +
          '<span class="evidence-meta">' + escapeHtml(receivedDate) + ' · ' + escapeHtml(senderNames) + '</span>' +
          '</button>' +
          '</li>'
        );
      }).filter(function (value) { return Boolean(value); }).join('');
      if (!items) return '';
      return '<div class="evidence-block"><div class="evidence-title rich-heading major-summary-heading">📬 근거 메일</div><ul class="evidence-list">' + items + '</ul></div>';
    }

    function buildScopeClarificationHtml(metadata) {
      var clarification = metadata && metadata.clarification && typeof metadata.clarification === 'object' ? metadata.clarification : null;
      if (!clarification || !clarification.required) return '';
      var question = String(clarification.question || '').trim() || '질문의 범위를 선택해 주세요.';
      var originalQuery = String(clarification.original_query || '').trim();
      var options = Array.isArray(clarification.options) ? clarification.options : [];
      if (!options.length || !originalQuery) return '';
      var optionButtons = options.map(function (option) {
        var scope = String(option && option.scope ? option.scope : '').trim();
        var label = String(option && option.label ? option.label : '').trim() || scope;
        var description = String(option && option.description ? option.description : '').trim();
        if (!scope) return '';
        return (
          '<button type="button" class="scope-choice-btn" ' +
          'data-action="scope-select" ' +
          'data-scope="' + escapeAttr(scope) + '" ' +
          'data-scope-label="' + escapeAttr(label) + '" ' +
          'data-original-query="' + escapeAttr(originalQuery) + '" ' +
          'title="' + escapeAttr(description || label) + '">' +
          '<span class="scope-choice-label">' + escapeHtml(label) + '</span>' +
          '<span class="scope-choice-desc">' + escapeHtml(description || '이 범위로 처리') + '</span>' +
          '</button>'
        );
      }).filter(function (value) { return Boolean(value); }).join('');
      if (!optionButtons) return '';
      return '<div class="scope-clarification-block"><div class="scope-clarification-title">' + escapeHtml(question) + '</div><div class="scope-choice-list">' + optionButtons + '</div></div>';
    }

    function buildHitlConfirmHtml(metadata) {
      if (!actionBlocks || typeof actionBlocks.buildHitlConfirmHtml !== 'function') return '';
      return actionBlocks.buildHitlConfirmHtml(metadata);
    }

    function buildNextActionsHtml(metadata) {
      if (!actionBlocks || typeof actionBlocks.buildNextActionsHtml !== 'function') return '';
      return actionBlocks.buildNextActionsHtml(metadata);
    }

    function buildReplyDraftActionHtml(metadata) {
      if (!actionBlocks || typeof actionBlocks.buildReplyDraftActionHtml !== 'function') return '';
      return actionBlocks.buildReplyDraftActionHtml(metadata, normalizeReplyDraftBodyText);
    }

    function buildReplyTonePickerHtml(metadata) {
      if (!actionBlocks || typeof actionBlocks.buildReplyTonePickerHtml !== 'function') return '';
      return actionBlocks.buildReplyTonePickerHtml(metadata);
    }

    function buildWebSourcesHtml(metadata) {
      if (!actionBlocks || typeof actionBlocks.buildWebSourcesHtml !== 'function') return '';
      return actionBlocks.buildWebSourcesHtml(metadata);
    }

    function renderBasicInfoRows(headers, rows) {
      if (!basicInfoBlocks || typeof basicInfoBlocks.renderBasicInfoRows !== 'function') return '';
      return basicInfoBlocks.renderBasicInfoRows(headers, rows);
    }

    return {
      buildEvidenceListHtml: buildEvidenceListHtml,
      buildScopeClarificationHtml: buildScopeClarificationHtml,
      buildHitlConfirmHtml: buildHitlConfirmHtml,
      buildNextActionsHtml: buildNextActionsHtml,
      buildReplyTonePickerHtml: buildReplyTonePickerHtml,
      buildReplyDraftActionHtml: buildReplyDraftActionHtml,
      buildWebSourcesHtml: buildWebSourcesHtml,
      normalizeReplyDraftBodyText: normalizeReplyDraftBodyText,
      renderBasicInfoRows: renderBasicInfoRows,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneMessagesMetaBlocks = api;
})(typeof window !== 'undefined' ? window : globalThis);
