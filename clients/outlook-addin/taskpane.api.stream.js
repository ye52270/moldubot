(function initTaskpaneApiStream(global) {
  function create(fetchRef) {
    const fetchFn = typeof fetchRef === 'function' ? fetchRef : fetch;

    function parseSseChunk(rawChunk) {
      const lines = String(rawChunk || '').replace(/\r\n/g, '\n').split('\n');
      let eventType = '';
      const dataLines = [];
      lines.forEach(function (lineRaw) {
        const line = String(lineRaw || '');
        if (!line || line.indexOf(':') === 0) return;
        if (line.indexOf('event:') === 0) {
          eventType = line.replace(/^event:\s*/, '').trim();
          return;
        }
        if (line.indexOf('data:') === 0) {
          dataLines.push(line.replace(/^data:\s*/, ''));
        }
      });
      const dataText = dataLines.join('\n').trim();
      if (!eventType || !dataText) return null;
      try {
        return {
          event: eventType,
          data: JSON.parse(dataText),
        };
      } catch (_error) {
        return null;
      }
    }

    async function forEachSseEvent(response, onEvent) {
      if (!response.body || typeof response.body.getReader !== 'function') {
        throw new Error('stream-body-unavailable');
      }
      const decoder = new TextDecoder();
      const reader = response.body.getReader();
      let buffered = '';
      while (true) {
        const state = await reader.read();
        if (state.done) break;
        buffered += decoder.decode(state.value || new Uint8Array(), { stream: true });
        const chunks = buffered.split('\n\n');
        buffered = chunks.pop() || '';
        chunks.forEach(function (chunk) {
          const parsed = parseSseChunk(chunk);
          if (!parsed) return;
          onEvent(parsed);
        });
      }
    }

    async function readCompletionPayload(response, onProgress, onToken) {
      let completedPayload = null;
      await forEachSseEvent(response, function (parsed) {
        if (parsed.event === 'progress' && typeof onProgress === 'function') {
          onProgress(parsed.data || {});
          return;
        }
        if (parsed.event === 'token' && typeof onToken === 'function') {
          onToken(parsed.data || {});
          return;
        }
        if (parsed.event === 'completed') {
          completedPayload = parsed.data || null;
        }
      });
      return completedPayload;
    }

    async function streamEvents(url, requestBody, onEvent, requestErrorLabel, streamErrorLabel) {
      const response = await fetchFn(url, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'ngrok-skip-browser-warning': 'true',
        },
        body: JSON.stringify(requestBody),
      });
      if (!response.ok) {
        throw new Error(requestErrorLabel + ': ' + response.status);
      }
      if (!response.body || typeof response.body.getReader !== 'function') {
        throw new Error(streamErrorLabel);
      }
      await forEachSseEvent(response, function (parsed) {
        if (!parsed || !parsed.data) return;
        if (typeof onEvent === 'function') onEvent(parsed.data);
      });
    }

    return {
      parseSseChunk: parseSseChunk,
      readCompletionPayload: readCompletionPayload,
      streamEvents: streamEvents,
    };
  }

  const api = { create: create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  global.TaskpaneApiStream = api;
})(typeof window !== 'undefined' ? window : globalThis);
