/* ========================================
   MolduBot – Taskpane Logger
   ======================================== */

(function initMolduLogger(global) {
  const sessionId = `tp_${Date.now().toString(36)}_${Math.random()
    .toString(36)
    .slice(2, 8)}`;
  const clientLogEndpoint = '/addin/client-logs';
  const maxTransportFailures = 5;
  let sequence = 0;
  let transportFailures = 0;

  function getRuntimeMeta() {
    try {
      return {
        page_path: String(global.location?.pathname || ''),
        href: String(global.location?.href || '').slice(0, 300),
        user_agent: String(global.navigator?.userAgent || '').slice(0, 220),
      };
    } catch {
      return { page_path: '', href: '', user_agent: '' };
    }
  }

  function nowIso() {
    try {
      return new Date().toISOString();
    } catch {
      return '';
    }
  }

  function normalizeError(error) {
    if (!error) return null;
    return {
      name: String(error.name || ''),
      message: String(error.message || error),
      code: error.code ?? null,
      stack: String(error.stack || '').slice(0, 500),
    };
  }

  function normalizeMeta(meta) {
    if (!meta || typeof meta !== 'object') return {};
    const out = {};
    for (const [key, value] of Object.entries(meta)) {
      if (value === undefined) continue;
      if (value === null) {
        out[key] = null;
        continue;
      }
      if (typeof value === 'string') {
        out[key] = value;
        continue;
      }
      if (typeof value === 'number' || typeof value === 'boolean') {
        out[key] = value;
        continue;
      }
      try {
        out[key] = JSON.parse(JSON.stringify(value));
      } catch {
        out[key] = String(value);
      }
    }
    return out;
  }

  function emit(level, event, status, meta, error) {
    sequence += 1;
    const runtimeMeta = getRuntimeMeta();
    const payload = {
      ts: nowIso(),
      seq: sequence,
      session_id: sessionId,
      event: String(event || 'unknown'),
      status: String(status || 'ok'),
      ...runtimeMeta,
      ...normalizeMeta(meta),
    };

    if (error) payload.error = normalizeError(error);

    const prefix = `[MolduBot][${payload.ts}][${sessionId}][${payload.seq}][${payload.event}][${payload.status}]`;
    const writer =
      level === 'error'
        ? console.error
        : level === 'warn'
          ? console.warn
          : console.log;
    writer(prefix, payload);
    sendToCollector(payload);
  }

  function sendToCollector(payload) {
    if (transportFailures >= maxTransportFailures) return;
    let body = '';
    try {
      body = JSON.stringify(payload);
    } catch {
      return;
    }

    try {
      if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
        const blob = new Blob([body], { type: 'application/json' });
        const sent = navigator.sendBeacon(clientLogEndpoint, blob);
        if (sent) return;
      }
    } catch {
      // ignore and fallback to fetch
    }

    if (typeof fetch !== 'function') return;
    fetch(clientLogEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
      cache: 'no-store',
      credentials: 'same-origin',
    })
      .then(() => {
        transportFailures = 0;
      })
      .catch(() => {
        transportFailures += 1;
      });
  }

  function reasonToString(reason) {
    if (reason == null) return '';
    if (reason instanceof Error) return `${reason.name}: ${reason.message}`;
    if (typeof reason === 'string') return reason;
    try {
      return JSON.stringify(reason);
    } catch {
      return String(reason);
    }
  }

  function installGlobalErrorHooks(logger) {
    if (global.__molduGlobalErrorHooksInstalled) return;
    global.__molduGlobalErrorHooksInstalled = true;

    if (typeof global.addEventListener !== 'function') return;

    global.addEventListener(
      'error',
      (event) => {
        try {
          logger.error(
            'window.error',
            event?.error || new Error(String(event?.message || 'window.error')),
            {
              source: String(event?.filename || ''),
              line: Number(event?.lineno || 0),
              column: Number(event?.colno || 0),
            }
          );
        } catch {
          // no-op
        }
      },
      true
    );

    global.addEventListener(
      'unhandledrejection',
      (event) => {
        try {
          const reason = event?.reason;
          logger.error(
            'window.unhandledrejection',
            reason instanceof Error ? reason : new Error('Unhandled promise rejection'),
            { reason: reasonToString(reason) }
          );
        } catch {
          // no-op
        }
      },
      true
    );
  }

  const logger = {
    sessionId,
    event(event, status = 'ok', meta = {}) {
      const normalizedStatus = String(status || 'ok').toLowerCase();
      const level =
        normalizedStatus === 'error'
          ? 'error'
          : normalizedStatus === 'warn'
            ? 'warn'
            : 'log';
      emit(level, event, normalizedStatus, meta, null);
    },
    info(event, meta = {}) {
      emit('log', event, 'ok', meta, null);
    },
    warn(event, meta = {}) {
      emit('warn', event, 'warn', meta, null);
    },
    error(event, error, meta = {}) {
      emit('error', event, 'error', meta, error);
    },
  };

  global.MolduLog = logger;
  global.molduLogEvent = (event, status = 'ok', meta = {}) =>
    logger.event(event, status, meta);
  global.molduLogInfo = (event, meta = {}) => logger.info(event, meta);
  global.molduLogWarn = (event, meta = {}) => logger.warn(event, meta);
  global.molduLogError = (event, error, meta = {}) =>
    logger.error(event, error, meta);
  installGlobalErrorHooks(logger);
})(window);
