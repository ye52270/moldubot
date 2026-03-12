/* ========================================
   MolduBot – Taskpane Summary Cards
   ======================================== */

(function initTaskpaneMessagesSummaryCards(global) {
  function create(options) {
    var escapeHtml = options.escapeHtml;
    var escapeAttr = options.escapeAttr || options.escapeHtml;
    var applyInlineFormatting = options.applyInlineFormatting;
    var renderIndexedSummaryCard = options.renderIndexedSummaryCard;
    var evidenceUi = options && options.evidenceUi && typeof options.evidenceUi === 'object'
      ? options.evidenceUi
      : null;

    function normalizeEvidenceToken(text) {
      if (evidenceUi && typeof evidenceUi.normalizeEvidenceToken === 'function') {
        return evidenceUi.normalizeEvidenceToken(text);
      }
      return String(text || '').replace(/\s+/g, '').toLowerCase();
    }

    function buildInlineEvidencePopover(metadata, title, optionsArg) {
      if (!evidenceUi || typeof evidenceUi.buildInlineEvidencePopover !== 'function') return '';
      return evidenceUi.buildInlineEvidencePopover(metadata, title, optionsArg);
    }

    function normalizeMajorSummaryMetaFromChunk(lines) {
      var values = Array.isArray(lines) ? lines.map(function (item) { return String(item || '').trim(); }).filter(function (item) { return Boolean(item); }) : [];
      if (!values.length) return { date: '', summary: '' };
      var summaryLine = values.find(function (line) { return /^요약\s*[:：]/i.test(line); }) || '';
      var dateLine = values.find(function (line) { return /^(수신일|날짜|received(?:_date)?)\s*[:：]/i.test(line); }) || '';
      var senderLine = values.find(function (line) { return /^(보낸\s*사람|발신자|from)\s*[:：]/i.test(line); }) || '';
      var summary = stripLeadingLabel(summaryLine, ['요약']);
      if (!summary) {
        var fallbackSummary = values.find(function (line) {
          return !/^(보낸\s*사람|발신자|from|수신일|날짜|received(?:_date)?)\s*[:：]/i.test(line);
        }) || '';
        summary = stripLeadingLabel(fallbackSummary, ['요약']);
      }
      if (!summary && senderLine) summary = '';
      var date = stripLeadingLabel(dateLine, ['수신일', '날짜', 'received', 'received_date']);
      return { date: date, summary: summary };
    }

    function stripLeadingLabel(text, labels) {
      var value = String(text || '').trim();
      if (!value) return '';
      var normalizedLabels = Array.isArray(labels) ? labels : [];
      for (var index = 0; index < normalizedLabels.length; index += 1) {
        var label = String(normalizedLabels[index] || '').trim();
        if (!label) continue;
        var pattern = new RegExp('^' + label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*[:：]\\s*', 'i');
        if (pattern.test(value)) return value.replace(pattern, '').trim();
      }
      return value;
    }

    function buildMajorSummaryMetaItems(itemCount, subtitles) {
      var totalCount = Number.isFinite(Number(itemCount)) ? Math.max(0, Number(itemCount)) : 0;
      if (!totalCount) return [];
      var raw = Array.isArray(subtitles) ? subtitles.map(function (item) { return String(item || '').trim(); }).filter(function (item) { return Boolean(item); }) : [];
      var emptyItems = Array(totalCount).fill(null).map(function () { return ({ date: '', summary: '' }); });
      if (!raw.length) return emptyItems;

      if (raw.length >= totalCount && raw.length % totalCount === 0) {
        var chunkSize = raw.length / totalCount;
        if (chunkSize >= 1 && chunkSize <= 4) {
          return emptyItems.map(function (_, index) {
            var chunk = raw.slice(index * chunkSize, (index + 1) * chunkSize);
            return normalizeMajorSummaryMetaFromChunk(chunk);
          });
        }
      }

      return emptyItems.map(function (_, index) {
        var value = raw[index] || '';
        return normalizeMajorSummaryMetaFromChunk(value ? [value] : []);
      });
    }

    function buildMajorSummaryListHtml(items, subtitles, metadata, startIndex) {
      var values = Array.isArray(items) ? items : [];
      if (!values.length) return '';
      var subtitleMeta = buildMajorSummaryMetaItems(values.length, subtitles);
      var initialIndex = Number.isFinite(Number(startIndex)) ? Number(startIndex) : 1;
      var itemHtml = values.map(function (item, index) {
        var title = String(item || '').trim();
        if (!title) return '';
        var meta = subtitleMeta[index] || { date: '', summary: '' };
        var subtitle = String(meta.summary || '').trim();
        var subtitleDate = String(meta.date || '').trim();
        var evidenceHtml = buildInlineEvidencePopover(metadata, title, { preferredIndex: index });
        var titleHtml = resolveMajorSummaryTitleHtml(title, metadata, index);
        return renderIndexedSummaryCard({
          index: initialIndex + index,
          titleHtml: titleHtml,
          subtitleDateHtml: subtitleDate ? applyInlineFormatting(subtitleDate) : '',
          subtitleHtml: subtitle ? applyInlineFormatting(subtitle) : '',
          rightAddonHtml: evidenceHtml || '',
          cardClassName: '',
          textBlockClassName: '',
        });
      }).filter(function (value) { return Boolean(value); }).join('');
      if (!itemHtml) return '';
      return '<ol class="major-summary-list">' + itemHtml + '</ol>';
    }

    function resolveMajorSummaryTitleHtml(title, metadata, index) {
      var linked = buildWebSourceTitleLinkHtml(title, metadata, index);
      if (linked) return linked;
      return applyInlineFormatting(title);
    }

    function buildWebSourceTitleLinkHtml(title, metadata, index) {
      var sources = metadata && Array.isArray(metadata.web_sources) ? metadata.web_sources : [];
      if (!sources.length) return '';
      var source = sources[index];
      if (!source || typeof source !== 'object') return '';
      var url = String(source.url || '').trim();
      if (!url) return '';
      var sourceTitle = String(source.title || '').trim();
      var siteName = String(source.site_name || '').trim();
      if (!_isLikelyExternalSummaryTitle(title, sourceTitle, siteName)) return '';
      return (
        '<a class="major-summary-link" href="' + escapeAttr(url) + '" target="_blank" rel="noopener noreferrer">' +
          applyInlineFormatting(title) +
        '</a>'
      );
    }

    function _isLikelyExternalSummaryTitle(title, sourceTitle, siteName) {
      var normalizedTitle = normalizeEvidenceToken(title);
      if (!normalizedTitle) return false;
      var normalizedSourceTitle = normalizeEvidenceToken(sourceTitle);
      var normalizedSiteName = normalizeEvidenceToken(siteName);
      if (normalizedSiteName && normalizedTitle.indexOf(normalizedSiteName) >= 0) return true;
      if (normalizedSourceTitle && normalizedTitle.indexOf(normalizedSourceTitle.slice(0, 14)) >= 0) return true;
      return /\([^)]+\.[^)]+\)/.test(String(title || ''));
    }

    function resolveTechIssueCluster(metadata, issueText, preferredIndex) {
      var enrichment = metadata && typeof metadata.context_enrichment === 'object' ? metadata.context_enrichment : null;
      var clusters = enrichment && Array.isArray(enrichment.tech_issue_clusters) ? enrichment.tech_issue_clusters : [];
      if (!clusters.length) return null;
      var preferred = Number(preferredIndex);
      if (Number.isInteger(preferred) && preferred >= 0 && preferred < clusters.length) {
        var preferredRow = clusters[preferred];
        if (preferredRow && typeof preferredRow === 'object') return preferredRow;
      }
      var target = normalizeEvidenceToken(issueText);
      if (!target) return null;
      for (var index = 0; index < clusters.length; index += 1) {
        var row = clusters[index];
        if (!row || typeof row !== 'object') continue;
        var summary = normalizeEvidenceToken(String(row.summary || ''));
        if (!summary) continue;
        if (summary.indexOf(target) >= 0 || target.indexOf(summary) >= 0) return row;
      }
      return null;
    }

    function buildTechIssueDetailPopover(cluster) {
      if (!evidenceUi || typeof evidenceUi.buildTechIssueDetailPopover !== 'function') return '';
      return evidenceUi.buildTechIssueDetailPopover(cluster, {
        triggerTitle: '기술 근거 보기',
        panelTitle: '기술 근거 상세',
      });
    }

    function buildTechIssueListHtml(items, metadata, startIndex) {
      var values = Array.isArray(items) ? items : [];
      if (!values.length) return '';
      var initialIndex = Number.isFinite(Number(startIndex)) ? Number(startIndex) : 1;
      var itemHtml = values.map(function (item, index) {
        var issueText = String(item || '').trim();
        if (!issueText) return '';
        var cluster = resolveTechIssueCluster(metadata, issueText, index);
        var issueType = cluster ? String(cluster.issue_type || '').trim() : '';
        var keywords = cluster && Array.isArray(cluster.keywords)
          ? cluster.keywords.map(function (value) { return String(value || '').trim(); }).filter(function (value) { return Boolean(value); }).slice(0, 5)
          : [];
        var detailPopover = buildTechIssueDetailPopover(cluster);
        var keywordLine = keywords.length
          ? '<div class="tech-issue-keywords">Keyword: ' + escapeHtml(keywords.join(', ')) + '</div>'
          : '';
        var issueTypeLine = issueType ? '<div class="tech-issue-type">유형: ' + escapeHtml(issueType) + '</div>' : '';
        return renderIndexedSummaryCard({
          index: initialIndex + index,
          titleHtml: applyInlineFormatting(issueText),
          subtitleDateHtml: '',
          subtitleHtml: '',
          rightAddonHtml: detailPopover || '',
          cardClassName: 'tech-issue-card',
          textBlockClassName: 'tech-issue-meta-block',
          subtitleExtraHtml: keywordLine + issueTypeLine,
        });
      }).filter(function (value) { return Boolean(value); }).join('');
      if (!itemHtml) return '';
      return '<ol class="major-summary-list tech-issue-list">' + itemHtml + '</ol>';
    }

    function resolveRecipientRoleTone(roleText) {
      var compact = normalizeEvidenceToken(roleText);
      if (!compact) return 'default';
      if (compact.indexOf('참여') >= 0 || compact.indexOf('협업') >= 0 || compact.indexOf('지원') >= 0) return 'participation';
      if (compact.indexOf('요청') >= 0 || compact.indexOf('문의') >= 0 || compact.indexOf('등록') >= 0) return 'request';
      if (compact.indexOf('시간') >= 0 || compact.indexOf('일정') >= 0 || compact.indexOf('시점') >= 0) return 'time';
      if (compact.indexOf('확인') >= 0 || compact.indexOf('검증') >= 0 || compact.indexOf('해결') >= 0) return 'confirm';
      return 'default';
    }

    function parseRecipientRoleItem(rawTitle, rawSubtitle) {
      var headline = String(rawTitle || '').trim();
      if (!headline) return null;
      var matched = /^(.+?)\s*[—-]\s*(.+)$/.exec(headline);
      var name = matched ? String(matched[1] || '').trim() : headline;
      var role = matched ? String(matched[2] || '').trim() : '';
      var reason = String(rawSubtitle || '').trim().replace(/^근거\s*[:：]\s*/i, '').trim();
      if (!name) return null;
      return {
        name: name,
        role: role,
        reason: reason,
      };
    }

    function buildRecipientRoleListHtml(items, subtitles, metadata, startIndex) {
      var values = Array.isArray(items) ? items : [];
      if (!values.length) return '';
      var subtitleRows = Array.isArray(subtitles) ? subtitles : [];
      var initialIndex = Number.isFinite(Number(startIndex)) ? Number(startIndex) : 1;
      var itemHtml = values.map(function (item, index) {
        var parsed = parseRecipientRoleItem(item, subtitleRows[index] || '');
        if (!parsed) return '';
        var tone = resolveRecipientRoleTone(parsed.role);
        var evidenceHtml = buildInlineEvidencePopover(metadata, parsed.name || String(item || '').trim(), { preferredIndex: index });
        var badgeHtml = parsed.role
          ? '<span class="recipient-role-badge tone-' + escapeHtml(tone) + '">' + applyInlineFormatting(parsed.role) + '</span>'
          : '';
        var reasonHtml = parsed.reason ? '<div class="recipient-role-reason">' + applyInlineFormatting(parsed.reason) + '</div>' : '';
        return (
          '<li class="recipient-role-item">' +
            '<div class="recipient-role-card">' +
              '<span class="recipient-role-num">' + String(initialIndex + index) + '</span>' +
              '<div class="recipient-role-main">' +
                '<div class="recipient-role-top">' +
                  '<span class="recipient-role-name">' + applyInlineFormatting(parsed.name) + '</span>' +
                  badgeHtml +
                '</div>' +
                reasonHtml +
              '</div>' +
              (evidenceHtml || '') +
            '</div>' +
          '</li>'
        );
      }).filter(function (value) { return Boolean(value); }).join('');
      if (!itemHtml) return '';
      return '<ol class="recipient-role-list">' + itemHtml + '</ol>';
    }

    return {
      buildMajorSummaryListHtml: buildMajorSummaryListHtml,
      buildTechIssueListHtml: buildTechIssueListHtml,
      buildRecipientRoleListHtml: buildRecipientRoleListHtml,
    };
  }

  var api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  if (global) {
    global.TaskpaneMessagesSummaryCards = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
