(function initTaskpaneMessagesRichTextUtils(globalScope) {
  function create(options) {
    const escapeHtml = options.escapeHtml;
    const escapeAttr = options.escapeAttr || options.escapeHtml;

    function insertStructuralNewlines(text) {
      let normalized = String(text || '');
      normalized = normalized.replace(/([^\n])---(?=#)/g, '$1\n---\n');
      normalized = normalized.replace(/---(?=#)/g, '---\n');
      normalized = normalized.replace(/([^\n])(?=#{1,6}[^\s#])/g, '$1\n');
      return normalized;
    }

    function normalizeRichSourceText(text) {
      const raw = insertStructuralNewlines(String(text || '').replace(/\r\n/g, '\n'));
      const actualNewlineCount = (raw.match(/\n/g) || []).length;
      if (actualNewlineCount <= 1 && raw.indexOf('\\n') >= 0) {
        return raw.replace(/\\n/g, '\n').replace(/\\t/g, '\t').trim();
      }
      return raw.trim();
    }

    function isMarkdownTableDelimiter(line) {
      return /^[:\-\|\s]+$/.test(String(line || '').replace(/\|/g, '').trim());
    }

    function splitMarkdownTableCells(line) {
      const trimmed = String(line || '').trim().replace(/^\|/, '').replace(/\|$/, '');
      return trimmed.split('|').map(function (cell) { return cell.trim(); });
    }

    function parseMailOpenUrl(url) {
      const raw = String(url || '').replace(/&amp;/g, '&').trim();
      if (!raw) return { webLink: '', messageId: '' };
      const matched = /[?&]moldubot_mid=([^&#]+)/.exec(raw);
      if (!matched) return { webLink: raw, messageId: extractItemId(raw) };
      let webLink = raw.replace(/([?&])moldubot_mid=[^&#]*&?/, '$1');
      webLink = webLink.replace(/[?&]$/, '').replace(/\?&/, '?');
      let messageId = '';
      try {
        messageId = decodeURIComponent(String(matched[1] || ''));
      } catch (_error) {
        messageId = String(matched[1] || '');
      }
      return { webLink: webLink, messageId: messageId };
    }

    function extractItemId(raw) {
      const matched = /[?&]ItemID=([^&#]+)/i.exec(String(raw || ''));
      if (!matched) return '';
      try {
        return decodeURIComponent(String(matched[1] || '').trim());
      } catch (_error) {
        return String(matched[1] || '').trim();
      }
    }

    function applyInlineFormatting(text) {
      let rendered = escapeHtml(String(text || ''));
      rendered = rendered.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      rendered = rendered.replace(/<\/strong>\s+:/g, '</strong>:');
      rendered = rendered.replace(/`(.+?)`/g, '<code class="rich-inline-code">$1</code>');
      rendered = rendered.replace(/\[([^\n]+)\]\((https?:\/\/[^\s)]+)\)/g, function (_match, label, url) {
        const normalizedLabel = String(label || '').replace(/\\\[/g, '[').replace(/\\\]/g, ']');
        const parsed = parseMailOpenUrl(url);
        if (parsed.messageId) {
          return (
            '<a class="rich-link evidence-open-btn" data-action="open-evidence-mail" data-message-id="' +
            escapeAttr(parsed.messageId) +
            '" data-web-link="' +
            escapeAttr(parsed.webLink) +
            '" href="' +
            escapeAttr(parsed.webLink) +
            '" target="_blank" rel="noopener noreferrer">' +
            normalizedLabel +
            '</a>'
          );
        }
        return '<a class="rich-link" href="' + String(url || '') + '" target="_blank" rel="noopener noreferrer">' + normalizedLabel + '</a>';
      });
      return rendered;
    }

    function renderMarkdownTable(headerLine, rowLines) {
      const headers = splitMarkdownTableCells(headerLine);
      const rows = rowLines
        .map(splitMarkdownTableCells)
        .filter(function (cells) {
          return !cells.every(function (cell) {
            return /^:?-{3,}:?$/.test(String(cell || '').trim());
          });
        })
        .map(function (cells) {
          return cells.map(function (cell) { return String(cell || '').trim(); });
        })
        .filter(function (cells) {
          if (!cells.length) return false;
          if (cells.length === 1 && cells[0] === '---') return false;
          return cells.some(function (cell) { return Boolean(cell); });
        })
        .map(function (cells) {
          if (headers.length >= 2 && cells.length === 1 && cells[0]) {
            return [cells[0], '-'];
          }
          return cells;
        });
      if (!headers.length || !rows.length) return '';
      const headHtml = '<thead><tr>' + headers.map(function (cell) {
        return '<th>' + applyInlineFormatting(cell) + '</th>';
      }).join('') + '</tr></thead>';
      const bodyHtml = '<tbody>' + rows.map(function (cells) {
        return '<tr>' + headers.map(function (_, index) {
          const value = cells[index] || '';
          return '<td>' + applyInlineFormatting(value) + '</td>';
        }).join('') + '</tr>';
      }).join('') + '</tbody>';
      return '<table class="md-table">' + headHtml + bodyHtml + '</table>';
    }

    function normalizeCodeFenceLanguageTag(rawFenceInfo) {
      const normalized = String(rawFenceInfo || '').trim().toLowerCase();
      if (!normalized) return '';
      const matched = /^([a-z0-9_+#.-]+)/.exec(normalized);
      if (!matched) return '';
      const token = String(matched[1] || '').trim();
      if (token === 'js') return 'javascript';
      if (token === 'ts') return 'typescript';
      if (token === 'py') return 'python';
      if (token === 'sh') return 'bash';
      if (token === 'yml') return 'yaml';
      return token;
    }

    function isLikelyJspSource(text) {
      const source = String(text || '').toLowerCase();
      if (!source) return false;
      return (
        source.indexOf('<%@') >= 0 || source.indexOf('<%--') >= 0 || source.indexOf('<%') >= 0 ||
        source.indexOf('<jsp:') >= 0 || source.indexOf('<bean:') >= 0 || source.indexOf('<logic:') >= 0 ||
        source.indexOf('<ac:') >= 0
      );
    }

    function formatCodeLanguageLabel(languageTag) {
      const lang = String(languageTag || '').trim().toLowerCase();
      if (!lang) return 'plain text';
      const labelMap = {
        javascript: 'JavaScript', typescript: 'TypeScript', python: 'Python', java: 'Java',
        csharp: 'C#', cpp: 'C++', c: 'C', go: 'Go', rust: 'Rust', kotlin: 'Kotlin',
        swift: 'Swift', sql: 'SQL', html: 'HTML', css: 'CSS', json: 'JSON', yaml: 'YAML', bash: 'Bash',
      };
      return labelMap[lang] || lang.toUpperCase();
    }

    function resolveHighlightLanguageClass(languageTag) {
      const lang = String(languageTag || '').trim().toLowerCase();
      if (!lang) return '';
      if (lang === 'jsp') return 'xml';
      return lang;
    }

    function shouldUpgradeFenceLanguageToJsp(languageTag, codeLine) {
      const lang = String(languageTag || '').trim().toLowerCase();
      if (!lang) return false;
      if (lang !== 'java' && lang !== 'html' && lang !== 'xml' && lang !== 'plaintext' && lang !== 'text') {
        return false;
      }
      return isLikelyJspSource(codeLine);
    }

    function isNoiseStructuralToken(text) {
      const value = String(text || '').trim();
      if (!value) return true;
      return /^#{1,6}$/.test(value);
    }

    function isMailListMetaLine(text) {
      const value = String(text || '').trim();
      if (!value) return false;
      return /^(발신자|보낸\s*사람|수신일|링크)\s*[:：]/.test(value);
    }

    function parseInlineMailListMeta(text) {
      const value = String(text || '').trim();
      if (!value) return null;
      const matched = /^보낸\s*사람\s*[:：]\s*(.+?)\s+수신일\s*[:：]\s*(.+?)\s+요약\s*[:：]\s*(.+)$/i.exec(value);
      if (!matched) return null;
      const sender = String(matched[1] || '').trim();
      const receivedAt = String(matched[2] || '').trim();
      let summary = String(matched[3] || '').trim();
      summary = summary.replace(/\[메일\s*링크\]\s*\([^)]*\)/gi, '').trim();
      return { sender: sender, receivedAt: receivedAt, summary: summary };
    }

    function isMailLinkNoiseLine(text) {
      const value = String(text || '').trim();
      if (!value) return false;
      if (/\[메일\s*링크\]/i.test(value)) return true;
      if (/\]\(https?:\/\/outlook\.live\.com\/owa\/\?/i.test(value)) return false;
      if (/^\(?https?:\/\/outlook\.live\.com\/owa\/\?/i.test(value)) return true;
      if (/viewmodel=ReadMessageItem/i.test(value)) return true;
      if (/^https?:\/\/\S+$/i.test(value)) return true;
      return false;
    }

    function resolveHeadingClass(text) {
      const normalized = String(text || '').trim();
      if (!normalized) return 'rich-heading';
      if (normalized.indexOf('📌 주요 내용') >= 0 || normalized === '주요 내용') {
        return 'rich-heading major-summary-heading';
      }
      return 'rich-heading';
    }

    function normalizeHeadingToken(text) {
      return String(text || '').toLowerCase().replace(/\s+/g, '').replace(/[^a-z0-9가-힣]/g, '');
    }

    function resolveCodeReviewSectionKey(headingText) {
      const token = normalizeHeadingToken(headingText);
      if (!token) return '';
      if (token === '코드분석') return 'code-analysis';
      if (token === '코드리뷰') return 'code-review';
      return '';
    }

    function buildCodeBlockOpenHtml(languageTag) {
      const normalizedTag = String(languageTag || '').trim().toLowerCase();
      const highlightLanguage = resolveHighlightLanguageClass(normalizedTag);
      const languageClass = highlightLanguage ? (' language-' + escapeAttr(highlightLanguage)) : '';
      const languageLabel = formatCodeLanguageLabel(normalizedTag);
      return (
        '<div class="rich-code-block">' +
          '<div class="rich-code-head">' +
            '<span class="rich-code-head-label">코드 리뷰</span>' +
            '<span class="rich-code-head-lang">' + escapeHtml(languageLabel) + '</span>' +
          '</div>' +
          '<pre class="rich-pre"><code class="rich-code' + languageClass + '">'
      );
    }

    function openCodeBlock(htmlChunks, trimmed) {
      const fenceInfo = String(trimmed || '').replace(/^```+/, '').trim();
      const codeBlockLanguage = normalizeCodeFenceLanguageTag(fenceInfo);
      htmlChunks.push(buildCodeBlockOpenHtml(codeBlockLanguage));
      return codeBlockLanguage;
    }

    function closeCodeBlock(htmlChunks) {
      htmlChunks.push('</code></pre></div>');
    }

    function consumeMarkdownTable(lines, startIndex, headerLine) {
      const rowLines = [];
      let rowIndex = startIndex + 2;
      while (rowIndex < lines.length) {
        const rowLine = String(lines[rowIndex] || '').trim();
        if (!rowLine || rowLine.indexOf('|') < 0) break;
        rowLines.push(rowLine);
        rowIndex += 1;
      }
      return {
        html: renderMarkdownTable(headerLine, rowLines),
        nextIndex: rowIndex - 1,
      };
    }

    return {
      insertStructuralNewlines: insertStructuralNewlines,
      normalizeRichSourceText: normalizeRichSourceText,
      isMarkdownTableDelimiter: isMarkdownTableDelimiter,
      splitMarkdownTableCells: splitMarkdownTableCells,
      parseMailOpenUrl: parseMailOpenUrl,
      applyInlineFormatting: applyInlineFormatting,
      renderMarkdownTable: renderMarkdownTable,
      normalizeCodeFenceLanguageTag: normalizeCodeFenceLanguageTag,
      formatCodeLanguageLabel: formatCodeLanguageLabel,
      resolveHighlightLanguageClass: resolveHighlightLanguageClass,
      shouldUpgradeFenceLanguageToJsp: shouldUpgradeFenceLanguageToJsp,
      isNoiseStructuralToken: isNoiseStructuralToken,
      isMailListMetaLine: isMailListMetaLine,
      parseInlineMailListMeta: parseInlineMailListMeta,
      isMailLinkNoiseLine: isMailLinkNoiseLine,
      resolveHeadingClass: resolveHeadingClass,
      resolveCodeReviewSectionKey: resolveCodeReviewSectionKey,
      buildCodeBlockOpenHtml: buildCodeBlockOpenHtml,
      openCodeBlock: openCodeBlock,
      closeCodeBlock: closeCodeBlock,
      consumeMarkdownTable: consumeMarkdownTable,
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
    return;
  }
  globalScope.TaskpaneMessagesRichtextUtils = api;
})(typeof window !== 'undefined' ? window : globalThis);
