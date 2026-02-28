(function () {
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function escapeAttr(text) {
    return String(text || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
  }

  function normalizeSafeHttpUrl(rawUrl) {
    const candidate = String(rawUrl || '').trim().replace(/&amp;/gi, '&');
    if (!candidate || !/^https?:\/\//i.test(candidate)) return '';
    try {
      const parsed = new URL(candidate);
      if (!['http:', 'https:'].includes(String(parsed.protocol || '').toLowerCase())) return '';
      return parsed.toString();
    } catch (_) {
      return '';
    }
  }

  function renderInlineMarkdownBase(text) {
    let html = escapeHtml(String(text || ''));
    const inlineCodeSegments = [];
    html = html.replace(/`([^`]+?)`/g, (_, code) => {
      const idx = inlineCodeSegments.push(`<code>${code}</code>`) - 1;
      return `@@INLINE_CODE_${idx}@@`;
    });
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\[([^\]]+?)\]\((https?:\/\/[^\s)]+)\)/gi, (_, label, url) => {
      const safeUrl = normalizeSafeHttpUrl(url);
      if (!safeUrl) return label;
      return `<a href="${escapeAttr(safeUrl)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
    });
    html = html.replace(/@@INLINE_CODE_(\d+)@@/g, (_, idx) => inlineCodeSegments[Number(idx)] || '');
    return html;
  }

  function renderInlineMarkdown(text) {
    return renderInlineMarkdownBase(text);
  }

  const SOURCE_SECTION_HEADING_RE = /^(관련\s*근거|관련\s*링크|관련\s*참고\s*링크(?:\s*\(발췌\))?|sources?)[:：]?$/i;
  const SOURCE_LINK_LINE_RE = /^\[([^\]]+?)\]\((https?:\/\/[^\s)]+)\)\s*$/i;
  const SOURCE_TEXT_LINK_LINE_RE = /^(.+?)\s*[:：]\s*(https?:\/\/\S+)\s*$/i;

  const MARKDOWN_SECTION_LINE_RE =
    /^(?:[-*•]\s+)?(?:\d+[\.\)]\s*)?(핵심\s*요약|주요\s*이슈|영향|권장\s*조치|권고\s*조치|다음\s*단계|결론|핵심\s*내용|요약|참고\s*메일|관련\s*메일)\s*(?:[:：]\s*(.+))?$/i;

  const MARKDOWN_SEMANTIC_LABEL_RE =
    /^((?:이슈\s*\d+|최우선|긴급|주의|리스크|위험|핵심|요약|결론|권장\s*조치|권고\s*조치|영향))\s*[:：]\s*(.+)$/i;

  const ENABLE_SEMANTIC_MARKDOWN_STYLING = false;

  function normalizeMarkdownLabel(label) {
    return String(label || '').replace(/\s+/g, ' ').trim();
  }

  function extractMarkdownSectionLine(text) {
    const matched = String(text || '').trim().match(MARKDOWN_SECTION_LINE_RE);
    if (!matched) return null;
    return {
      label: normalizeMarkdownLabel(matched[1]),
      detail: String(matched[2] || '').trim(),
    };
  }

  function renderLineWithSemanticLabel(content) {
    const raw = String(content || '').trim();
    if (!raw) return '';
    if (!ENABLE_SEMANTIC_MARKDOWN_STYLING) return renderInlineMarkdown(raw);

    const matched = raw.match(MARKDOWN_SEMANTIC_LABEL_RE);
    if (!matched) return renderInlineMarkdown(raw);

    const label = normalizeMarkdownLabel(matched[1]);
    const detail = String(matched[2] || '').trim();
    const detailHtml = detail ? `: ${renderInlineMarkdown(detail)}` : '';
    return `<strong>${renderInlineMarkdown(label)}</strong>${detailHtml}`;
  }

  function renderMarkdownHeadingInline(text) {
    const section = extractMarkdownSectionLine(text);
    if (!section) return renderInlineMarkdown(text);
    if (!section.detail) {
      return `<span class="md-section-label">${escapeHtml(section.label)}</span>`;
    }
    return `<span class="md-section-label">${escapeHtml(section.label)}</span>: ${renderLineWithSemanticLabel(section.detail)}`;
  }

  function splitMarkdownTableRow(line) {
    const raw = String(line || '').trim();
    if (!raw) return [];
    let body = raw;
    if (body.startsWith('|')) body = body.slice(1);
    if (body.endsWith('|')) body = body.slice(0, -1);
    return body.split('|').map((cell) => cell.trim());
  }

  function isMarkdownTableSeparator(line) {
    const cells = splitMarkdownTableRow(line);
    if (!cells.length) return false;
    return cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s+/g, '')));
  }

  function renderMarkdownTableBlock(lines, startIndex) {
    const headerCells = splitMarkdownTableRow(lines[startIndex]);
    const alignCells = splitMarkdownTableRow(lines[startIndex + 1]);
    const aligns = alignCells.map((token) => {
      const normalized = token.replace(/\s+/g, '');
      if (/^:-+:$/.test(normalized)) return 'center';
      if (/^-+:$/.test(normalized)) return 'right';
      return 'left';
    });
    let i = startIndex + 2;
    const rowHtml = [];
    while (i < lines.length) {
      const rowRaw = String(lines[i] || '').trim();
      if (!rowRaw || !rowRaw.includes('|')) break;
      const cells = splitMarkdownTableRow(lines[i]);
      rowHtml.push(
        `<tr>${cells
          .map(
            (cell, idx) =>
              `<td style="text-align:${escapeAttr(aligns[idx] || 'left')}">${renderInlineMarkdown(cell)}</td>`
          )
          .join('')}</tr>`
      );
      i += 1;
    }
    const html = `<div class="result-table-wrap markdown-table-wrap"><table class="result-table markdown-table"><thead><tr>${headerCells
      .map(
        (cell, idx) =>
          `<th style="text-align:${escapeAttr(aligns[idx] || 'left')}">${renderInlineMarkdown(cell)}</th>`
      )
      .join('')}</tr></thead><tbody>${rowHtml.join('')}</tbody></table></div>`;
    return { html, nextIndex: i };
  }

  function renderMarkdownUnorderedListItem(content) {
    const taskMatch = String(content || '').match(/^\[( |x|X)\]\s+(.+)$/);
    if (taskMatch) {
      const checked = String(taskMatch[1] || '').toLowerCase() === 'x';
      return `<li class="markdown-task-item"><label><input type="checkbox" disabled ${checked ? 'checked' : ''} />` +
        `<span>${renderInlineMarkdown(taskMatch[2])}</span></label></li>`;
    }
    return `<li>${renderLineWithSemanticLabel(content)}</li>`;
  }

  function closeMarkdownList(parts, state) {
    if (!state.listType) return;
    parts.push(`</${state.listType}>`);
    state.listType = '';
  }

  function openMarkdownList(parts, state, type) {
    if (state.listType === type) return;
    closeMarkdownList(parts, state);
    state.listType = type;
    parts.push(`<${type}>`);
  }

  function consumeMarkdownCodeBlockLine(line, trimmed, parts, state) {
    if (!state.inCodeBlock) return false;
    if (/^```/.test(trimmed)) {
      parts.push(`<pre><code>${escapeHtml(state.codeLines.join('\n'))}</code></pre>`);
      state.inCodeBlock = false;
      state.codeLines = [];
    } else {
      state.codeLines.push(line);
    }
    return true;
  }

  function startMarkdownCodeBlock(trimmed, parts, state) {
    if (!/^```/.test(trimmed)) return false;
    closeMarkdownList(parts, state);
    state.inCodeBlock = true;
    state.codeLines = [];
    return true;
  }

  function appendMarkdownHeadingLine(trimmed, parts, state) {
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (!headingMatch) return false;
    closeMarkdownList(parts, state);
    const level = Math.min(6, headingMatch[1].length);
    const headingText = String(headingMatch[2] || '').trim();
    state.inSourceSection = SOURCE_SECTION_HEADING_RE.test(headingText);
    parts.push(`<h${level}>${renderMarkdownHeadingInline(headingText)}</h${level}>`);
    return true;
  }

  function appendMarkdownSectionLine(trimmed, parts, state) {
    if (!ENABLE_SEMANTIC_MARKDOWN_STYLING) return false;
    const section = extractMarkdownSectionLine(trimmed);
    if (!section) return false;
    closeMarkdownList(parts, state);
    parts.push(`<h3><span class="md-section-label">${escapeHtml(section.label)}</span></h3>`);
    if (section.detail) {
      parts.push(`<p>${renderLineWithSemanticLabel(section.detail)}</p>`);
    }
    return true;
  }

  function renderMarkdownTableAt(lines, index, parts, state) {
    const line = String(lines[index] || '').trim();
    const nextLine = String(lines[index + 1] || '').trim();
    if (!line.includes('|')) return -1;

    // Standard markdown table with separator row
    if (isMarkdownTableSeparator(nextLine)) {
      closeMarkdownList(parts, state);
      const tableBlock = renderMarkdownTableBlock(lines, index);
      parts.push(tableBlock.html);
      return tableBlock.nextIndex;
    }

    // Tolerant mode: header/rows use "|" but separator row is missing.
    // Example:
    // 이슈 | 원인 | 영향 | 근거 링크
    // - A | B | C | https://...
    const headerRow = splitMarkdownTableRow(line);
    if (line.startsWith('-') || line.startsWith('*') || headerRow.length < 3) return -1;
    let i = index + 1;
    const rowHtml = [];
    let pendingContinuation = '';
    while (i < lines.length) {
      const rowRaw = String(lines[i] || '').trim();
      if (!rowRaw) {
        i += 1;
        continue;
      }
      if (!rowRaw.includes('|')) {
        // LLM이 행을 줄바꿈으로 끊는 경우 마지막 셀에 이어 붙인다.
        if (rowHtml.length) {
          pendingContinuation = pendingContinuation
            ? `${pendingContinuation} ${rowRaw}`
            : rowRaw;
          i += 1;
          continue;
        }
        break;
      }
      const normalizedRow = rowRaw.replace(/^[-*•]\s+/, '');
      const cells = splitMarkdownTableRow(normalizedRow);
      if (cells.length < 2) break;
      if (pendingContinuation) {
        const lastIdx = cells.length - 1;
        cells[lastIdx] = `${cells[lastIdx]} ${pendingContinuation}`.trim();
        pendingContinuation = '';
      }
      rowHtml.push(
        `<tr>${cells.map((cell) => `<td style="text-align:left">${renderInlineMarkdown(cell)}</td>`).join('')}</tr>`
      );
      i += 1;
    }
    if (!rowHtml.length) return -1;
    closeMarkdownList(parts, state);
    parts.push(
      `<div class="result-table-wrap markdown-table-wrap"><table class="result-table markdown-table">` +
      `<thead><tr>${headerRow.map((cell) => `<th style="text-align:left">${renderInlineMarkdown(cell)}</th>`).join('')}</tr></thead>` +
      `<tbody>${rowHtml.join('')}</tbody></table></div>`
    );
    return i;
  }

  function buildSourceFaviconUrl(rawUrl) {
    const safeUrl = normalizeSafeHttpUrl(rawUrl);
    if (!safeUrl) return '';
    try {
      const parsed = new URL(safeUrl);
      const origin = `${parsed.protocol}//${parsed.host}`;
      return `https://www.google.com/s2/favicons?domain_url=${encodeURIComponent(origin)}&sz=32`;
    } catch (_) {
      return '';
    }
  }

  function renderMarkdownSourceListItem(content) {
    const raw = String(content || '').trim();
    let label = '';
    let rawUrl = '';

    const markdownMatched = raw.match(SOURCE_LINK_LINE_RE);
    if (markdownMatched) {
      label = String(markdownMatched[1] || '').trim();
      rawUrl = String(markdownMatched[2] || '').trim();
    } else {
      const textMatched = raw.match(SOURCE_TEXT_LINK_LINE_RE);
      if (textMatched) {
        label = String(textMatched[1] || '').trim();
        rawUrl = String(textMatched[2] || '').trim();
      } else {
        const genericUrlMatched = raw.match(/https?:\/\/\S+/i);
        if (!genericUrlMatched) return '';
        rawUrl = String(genericUrlMatched[0] || '').trim();
        label = String(raw || '')
          .replace(rawUrl, ' ')
          .replace(/[\[\]\(\)]/g, ' ')
          .replace(/^[-*•]\s+/, '')
          .replace(/\s+/g, ' ')
          .trim();
      }
    }

    const safeUrl = normalizeSafeHttpUrl(rawUrl);
    if (!safeUrl) return '';
    const faviconUrl = buildSourceFaviconUrl(safeUrl);
    const safeLabel = renderInlineMarkdownBase(label || safeUrl);
    const safeHost = (() => {
      try {
        return escapeHtml(new URL(safeUrl).host || '');
      } catch (_) {
        return '';
      }
    })();
    const faviconHtml = faviconUrl
      ? `<img class="markdown-source-favicon" src="${escapeAttr(faviconUrl)}" alt="" loading="lazy" referrerpolicy="no-referrer" />`
      : '';
    const hostHtml = safeHost ? `<span class="markdown-source-host">${safeHost}</span>` : '';
    return (
      '<li class="markdown-source-item">' +
      `<a class="markdown-source-link" href="${escapeAttr(safeUrl)}" target="_blank" rel="noopener noreferrer">` +
      `${faviconHtml}<span class="markdown-source-label">${safeLabel}</span>${hostHtml}</a></li>`
    );
  }

  function appendMarkdownListOrParagraph(trimmed, parts, state, indentSpaces = 0) {
    if (appendMarkdownSectionLine(trimmed, parts, state)) return;

    const orderedMatch = trimmed.match(/^(\d+)[\.\)]\s*(.+)$/);
    if (orderedMatch) {
      openMarkdownList(parts, state, 'ol');
      parts.push(`<li>${renderLineWithSemanticLabel(orderedMatch[2])}</li>`);
      return;
    }
    const unorderedMatch = trimmed.match(/^[-*•]\s+(.+)$/);
    if (unorderedMatch) {
      const unorderedContent = unorderedMatch[1];
      if (state.inSourceSection) {
        const sourceItemHtml = renderMarkdownSourceListItem(unorderedContent);
        if (sourceItemHtml) {
          openMarkdownList(parts, state, 'ul');
          parts.push(sourceItemHtml);
          return;
        }
      }
      const pseudoOrderedMatch = unorderedContent.match(/^(\d+)[\.\)]\s*(.+)$/);
      const isTaskItem = /^\[( |x|X)\]\s+/.test(unorderedContent);
      if (pseudoOrderedMatch && !isTaskItem) {
        openMarkdownList(parts, state, 'ol');
        parts.push(`<li>${renderLineWithSemanticLabel(pseudoOrderedMatch[2])}</li>`);
        return;
      }
      openMarkdownList(parts, state, 'ul');
      if (indentSpaces >= 2) {
        parts.push(`<li style="list-style:none;">- ${renderLineWithSemanticLabel(unorderedContent)}</li>`);
        return;
      }
      parts.push(renderMarkdownUnorderedListItem(unorderedContent));
      return;
    }
    closeMarkdownList(parts, state);
    parts.push(`<p>${renderLineWithSemanticLabel(trimmed)}</p>`);
  }

  function consumeMarkdownLineAt(lines, index, parts, state) {
    const line = String(lines[index] || '');
    const indentSpaces = (line.match(/^\s*/) || [''])[0].length;
    const trimmed = line.trim();

    if (consumeMarkdownCodeBlockLine(line, trimmed, parts, state)) return index + 1;
    if (startMarkdownCodeBlock(trimmed, parts, state)) return index + 1;
    if (!trimmed) {
      closeMarkdownList(parts, state);
      return index + 1;
    }
    if (appendMarkdownHeadingLine(trimmed, parts, state)) return index + 1;

    const nextIndex = renderMarkdownTableAt(lines, index, parts, state);
    if (nextIndex > -1) return nextIndex;

    appendMarkdownListOrParagraph(trimmed, parts, state, indentSpaces);
    return index + 1;
  }

  function flushMarkdownRenderState(parts, state) {
    closeMarkdownList(parts, state);
    if (state.inCodeBlock) {
      parts.push(`<pre><code>${escapeHtml(state.codeLines.join('\n'))}</code></pre>`);
    }
  }

  function renderMarkdown(text) {
    const raw = String(text || '').replace(/\r\n/g, '\n');
    if (!raw.trim()) return '';

    const lines = raw.split('\n');
    const parts = [];
    let i = 0;
    const state = {
      listType: '',
      inCodeBlock: false,
      codeLines: [],
      inSourceSection: false,
    };

    while (i < lines.length) {
      i = consumeMarkdownLineAt(lines, i, parts, state);
    }

    flushMarkdownRenderState(parts, state);
    return parts.join('');
  }

  window.TaskpaneMarkdownUtils = {
    escapeHtml,
    escapeAttr,
    normalizeSafeHttpUrl,
    renderInlineMarkdownBase,
    renderInlineMarkdown,
    MARKDOWN_SECTION_LINE_RE,
    MARKDOWN_SEMANTIC_LABEL_RE,
    ENABLE_SEMANTIC_MARKDOWN_STYLING,
    normalizeMarkdownLabel,
    extractMarkdownSectionLine,
    renderLineWithSemanticLabel,
    renderMarkdownHeadingInline,
    splitMarkdownTableRow,
    isMarkdownTableSeparator,
    renderMarkdownTableBlock,
    renderMarkdownUnorderedListItem,
    closeMarkdownList,
    openMarkdownList,
    consumeMarkdownCodeBlockLine,
    startMarkdownCodeBlock,
    appendMarkdownHeadingLine,
    appendMarkdownSectionLine,
    renderMarkdownTableAt,
    appendMarkdownListOrParagraph,
    consumeMarkdownLineAt,
    flushMarkdownRenderState,
    renderMarkdown,
  };
})();
