(function initTaskpaneMessagesAnswerBlocks(globalScope) {
  function create(options) {
    const escapeAttr = options.escapeAttr;
    const applyInlineFormatting = options.applyInlineFormatting;
    const renderMarkdownTable = options.renderMarkdownTable;
    const renderBasicInfoRows = options.renderBasicInfoRows;
    const resolveHeadingClass = options.resolveHeadingClass;
    const isNoiseStructuralToken = options.isNoiseStructuralToken;
    const resolveSummarySectionKey = options.resolveSummarySectionKey;
    const normalizeHeadingToken = options.normalizeHeadingToken;
    const isExecutiveBriefHeading = options.isExecutiveBriefHeading;
    const buildExecutiveBriefHtml = options.buildExecutiveBriefHtml;
    const buildMajorSummaryListHtml = options.buildMajorSummaryListHtml;
    const buildTechIssueListHtml = options.buildTechIssueListHtml;
    const buildRecipientRoleListHtml = options.buildRecipientRoleListHtml;
    const buildInlineEvidencePopover = options.buildInlineEvidencePopover;

    function stripLeadingHeadingEmoji(text) {
      const value = String(text || '').trim();
      if (!value) return '';
      return value
        .replace(/^[📋🔍📌💡👤👥🧾✅🛠🔎📝📬\s]+/u, '')
        .trim();
    }

    function buildCodeReviewQualityBadgesHtml(metadata) {
      var quality = metadata && typeof metadata.code_review_quality === 'object'
        ? metadata.code_review_quality
        : null;
      if (!quality || !quality.enabled) return '';
      var badges = [];
      if (quality.critic_used) {
        badges.push('<span class="quality-badge quality-badge-critic">Critic 검증</span>');
      }
      if (quality.revise_applied) {
        badges.push('<span class="quality-badge quality-badge-revise">Revise 적용</span>');
      } else {
        badges.push('<span class="quality-badge quality-badge-draft">원본 유지</span>');
      }
      var sourceCount = Number(quality.web_source_count);
      if (Number.isFinite(sourceCount) && sourceCount > 0) {
        badges.push('<span class="quality-badge quality-badge-source">출처 ' + String(sourceCount) + '건</span>');
      }
      if (!badges.length) return '';
      return '<div class="quality-badge-row">' + badges.join('') + '</div>';
    }

    function renderAnswerFormatBlocks(blocks, metadata) {
      if (!Array.isArray(blocks) || !blocks.length) return '';
      const chunks = [];
      let orderedStartIndex = 1;
      let lastHeading = '';
      let activeSection = '';
      let executiveBriefRendered = false;
      let activeSectionBodyOpened = false;
      let majorSummaryRunningIndex = 1;
      const answerFormat = metadata && typeof metadata.answer_format === 'object' ? metadata.answer_format : null;
      const formatType = String(answerFormat && answerFormat.format_type ? answerFormat.format_type : '').trim().toLowerCase();

      function closeSectionIfNeeded() {
        if (!activeSection) return;
        if (activeSectionBodyOpened) {
          chunks.push('</div>');
          activeSectionBodyOpened = false;
        }
        chunks.push('</section>');
        activeSection = '';
      }

      for (let index = 0; index < blocks.length; index += 1) {
        const block = blocks[index];
        if (!block || typeof block !== 'object') continue;
        const type = String(block.type || '').trim();
        if (type === 'heading') {
          closeSectionIfNeeded();
          const level = Number.isFinite(Number(block.level)) ? Math.min(Math.max(Number(block.level), 1), 4) : 3;
          const text = String(block.text || '').trim();
          if (text) {
            lastHeading = text;
            executiveBriefRendered = false;
            const sectionKey = resolveSummarySectionKey(text);
            if (sectionKey === 'title') {
              activeSection = 'title_skip';
              continue;
            }
            if (sectionKey) {
              activeSection = sectionKey;
              const headingText = stripLeadingHeadingEmoji(text);
              const headingHtml = '<h' + level + ' class="' + resolveHeadingClass(text) + '">' + applyInlineFormatting(headingText || text) + '</h' + level + '>';
              if (sectionKey === 'major') {
                chunks.push('<section class="summary-section section-' + escapeAttr(sectionKey) + '"><div class="summary-section-head">' + headingHtml + '<button type="button" class="section-toggle-btn" data-action="section-toggle" data-section="major" aria-expanded="true">접기</button></div><div class="summary-section-body">');
              } else if (sectionKey === 'code-review') {
                chunks.push('<section class="summary-section section-' + escapeAttr(sectionKey) + '">' + headingHtml + '<div class="summary-section-body">' + buildCodeReviewQualityBadgesHtml(metadata));
              } else {
                chunks.push('<section class="summary-section section-' + escapeAttr(sectionKey) + '">' + headingHtml + '<div class="summary-section-body">');
              }
              activeSectionBodyOpened = true;
            } else {
              chunks.push('<h' + level + ' class="' + resolveHeadingClass(text) + '">' + applyInlineFormatting(text) + '</h' + level + '>');
            }
          }
          orderedStartIndex = 1;
          continue;
        }
        if (type === 'ordered_list' || type === 'unordered_list') {
          const items = Array.isArray(block.items) ? block.items : [];
          if (!items.length) continue;
          if (activeSection === 'major' && type === 'unordered_list') {
            chunks.push(buildMajorSummaryListHtml(items, [], metadata, majorSummaryRunningIndex));
            majorSummaryRunningIndex += items.filter(function (item) { return Boolean(String(item || '').trim()); }).length;
            continue;
          }
          if (activeSection === 'recipient-role' && type === 'unordered_list') {
            continue;
          }
          if (activeSection === 'major' && type === 'ordered_list') {
            let subtitles = [];
            const nextBlock = blocks[index + 1];
            if (nextBlock && typeof nextBlock === 'object' && String(nextBlock.type || '').trim() === 'unordered_list' && Array.isArray(nextBlock.items)) {
              subtitles = nextBlock.items.map(function (item) { return String(item || '').trim(); });
              index += 1;
            }
            chunks.push(buildMajorSummaryListHtml(items, subtitles, metadata, majorSummaryRunningIndex));
            majorSummaryRunningIndex += items.filter(function (item) { return Boolean(String(item || '').trim()); }).length;
            orderedStartIndex += items.length;
            continue;
          }
          if (activeSection === 'recipient-role' && type === 'ordered_list') {
            let subtitles = [];
            const nextBlock = blocks[index + 1];
            if (nextBlock && typeof nextBlock === 'object' && String(nextBlock.type || '').trim() === 'unordered_list' && Array.isArray(nextBlock.items)) {
              subtitles = nextBlock.items.map(function (item) { return String(item || '').trim(); });
              index += 1;
            }
            chunks.push(buildRecipientRoleListHtml(items, subtitles, metadata, orderedStartIndex));
            orderedStartIndex += items.length;
            continue;
          }
          if (activeSection === 'tech-issue') {
            chunks.push(buildTechIssueListHtml(items, metadata, orderedStartIndex));
            if (type === 'ordered_list') orderedStartIndex += items.length;
            continue;
          }
          const isCurrentMailPlainList =
            (type === 'ordered_list' || type === 'unordered_list')
            && formatType === 'current_mail'
            && !activeSection
            && !normalizeHeadingToken(lastHeading);
          if (isCurrentMailPlainList) {
            chunks.push(buildMajorSummaryListHtml(items, [], metadata, orderedStartIndex));
            if (type === 'ordered_list') orderedStartIndex += items.length;
            continue;
          }
          const tag = type === 'ordered_list' ? 'ol' : 'ul';
          const orderedClass = type === 'ordered_list' ? ' ordered' : '';
          const itemPrefixOpen = type === 'ordered_list' ? '<span class="rich-ol-title">' : '';
          const itemPrefixClose = type === 'ordered_list' ? '</span>' : '';
          const startAttr = type === 'ordered_list' && orderedStartIndex > 1 ? ' start="' + String(orderedStartIndex) + '"' : '';
          const headingToken = normalizeHeadingToken(lastHeading);
          const includeInlineEvidence = type === 'ordered_list' && (
            headingToken.indexOf('주요내용') >= 0 || headingToken.indexOf('외부정보요약') >= 0
          );
          const itemHtml = items.map(function (item) { return String(item || '').trim(); }).filter(function (item) { return Boolean(item); }).map(function (item) {
            const evidencePopover = includeInlineEvidence ? buildInlineEvidencePopover(metadata, item) : '';
            if (!evidencePopover) return '<li>' + itemPrefixOpen + applyInlineFormatting(item) + itemPrefixClose + '</li>';
            return ('<li><div class="rich-ol-head"><div class="rich-ol-line">' + itemPrefixOpen + applyInlineFormatting(item) + itemPrefixClose + '</div>' + evidencePopover + '</div></li>');
          }).join('');
          if (!itemHtml) continue;
          chunks.push('<' + tag + ' class="rich-list' + orderedClass + '"' + startAttr + '>' + itemHtml + '</' + tag + '>');
          if (type === 'ordered_list') orderedStartIndex += items.length;
          continue;
        }
        if (type === 'paragraph') {
          const text = String(block.text || '').trim();
          if (!text || activeSection === 'title_skip') continue;
          if (/^(-{3,}|\*{3,}|_{3,})$/.test(text)) {
            chunks.push('<hr class="rich-divider" />');
            continue;
          }
          if (isNoiseStructuralToken(text)) continue;
          if (isExecutiveBriefHeading(lastHeading) && !executiveBriefRendered) {
            chunks.push(buildExecutiveBriefHtml(text, metadata));
            executiveBriefRendered = true;
            continue;
          }
          chunks.push('<p class="rich-paragraph">' + applyInlineFormatting(text) + '</p>');
          continue;
        }
        if (type === 'quote') {
          const text = String(block.text || '').trim();
          if (text) chunks.push('<blockquote class="rich-quote">' + applyInlineFormatting(text) + '</blockquote>');
          continue;
        }
        if (type === 'table') {
          if (activeSection === 'title_skip') continue;
          const headers = Array.isArray(block.headers) ? block.headers : [];
          const rows = Array.isArray(block.rows) ? block.rows : [];
          if (!headers.length) continue;
          const hasOnlyDelimiterHeaders = headers.every(function (cell) { return /^:?-{3,}:?$/.test(String(cell || '').trim()); });
          if (hasOnlyDelimiterHeaders) continue;
          if (activeSection === 'basic') {
            chunks.push(renderBasicInfoRows(headers, rows));
            continue;
          }
          const headerLine = '| ' + headers.map(function (cell) { return String(cell || '').trim(); }).join(' | ') + ' |';
          const rowLines = rows.map(function (row) { return Array.isArray(row) ? row : []; }).map(function (row) { return '| ' + row.map(function (cell) { return String(cell || '').trim(); }).join(' | ') + ' |'; });
          chunks.push(renderMarkdownTable(headerLine, rowLines));
        }
      }
      closeSectionIfNeeded();
      return chunks.join('');
    }

    return {
      buildCodeReviewQualityBadgesHtml: buildCodeReviewQualityBadgesHtml,
      renderAnswerFormatBlocks: renderAnswerFormatBlocks,
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
    return;
  }
  globalScope.TaskpaneMessagesAnswerBlocks = api;
})(typeof window !== 'undefined' ? window : globalThis);
