/* ========================================
   MolduBot – Theme Utils Module
   ======================================== */

(function (global) {
  let outlookThemeSyncBound = false;

  function parseRgbColor(colorText = '') {
    const raw = String(colorText || '').trim();
    if (!raw) return null;
    const hex = raw.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (hex) {
      const token = hex[1].length === 3
        ? hex[1].split('').map((ch) => ch + ch).join('')
        : hex[1];
      return {
        r: Number.parseInt(token.slice(0, 2), 16),
        g: Number.parseInt(token.slice(2, 4), 16),
        b: Number.parseInt(token.slice(4, 6), 16),
      };
    }
    const rgb = raw.match(/^rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
    if (!rgb) return null;
    return {
      r: Number.parseInt(rgb[1], 10),
      g: Number.parseInt(rgb[2], 10),
      b: Number.parseInt(rgb[3], 10),
    };
  }

  function isDarkRgb(rgb) {
    if (!rgb) return true;
    const luminance = (0.2126 * rgb.r + 0.7152 * rgb.g + 0.0722 * rgb.b) / 255;
    return luminance < 0.5;
  }

  function resolveExplicitThemeDarkFlag(theme) {
    if (!theme || typeof theme !== 'object') return null;
    const candidates = [theme.isDarkTheme, theme.isDark, theme.dark];
    for (const candidate of candidates) {
      if (typeof candidate === 'boolean') return candidate;
    }
    const themeName = String(theme.themeId || theme.name || theme.id || '')
      .trim()
      .toLowerCase();
    if (!themeName) return null;
    if (/(dark|black|highcontrastblack|hcblack)/i.test(themeName)) return true;
    if (/(light|white|colorful)/i.test(themeName)) return false;
    return null;
  }

  function createThemeSyncDeps(options = {}) {
    const logEvent = typeof options.logEvent === 'function' ? options.logEvent : null;
    const logError = typeof options.logError === 'function' ? options.logError : null;
    return {
      logEvent: (event, status, meta) => {
        if (logEvent) {
          logEvent(event, status, meta);
          return;
        }
        try {
          console.debug('[MolduBot][theme]', event, status || 'ok', meta || {});
        } catch (_) {
          // ignore console issues
        }
      },
      logError: (event, error) => {
        if (logError) {
          logError(event, error);
          return;
        }
        try {
          console.warn('[MolduBot][theme.error]', event, error);
        } catch (_) {
          // ignore console issues
        }
      },
    };
  }

  function applyOutlookTheme(officeTheme = null, options = {}) {
    const { logEvent } = createThemeSyncDeps(options);
    const theme = officeTheme || global?.Office?.context?.officeTheme || null;
    const color = theme?.bodyBackgroundColor || theme?.controlBackgroundColor || '';
    const explicitDark = resolveExplicitThemeDarkFlag(theme);
    const colorBasedDark = isDarkRgb(parseRgbColor(color));
    const keepCurrentDark = global?.document?.documentElement?.classList?.contains('theme-dark');
    const dark =
      typeof explicitDark === 'boolean'
        ? explicitDark
        : color
          ? (colorBasedDark || keepCurrentDark)
          : true;
    global?.document?.documentElement?.classList?.toggle('theme-dark', dark);
    logEvent('theme.sync', 'ok', {
      mode: dark ? 'dark' : 'light',
      has_office_theme: Boolean(theme),
      sample_color: String(color || ''),
    });
  }

  function initializeOutlookThemeSync(options = {}) {
    const { logError } = createThemeSyncDeps(options);
    applyOutlookTheme(null, options);
    if (outlookThemeSyncBound) return;
    outlookThemeSyncBound = true;
    try {
      const OfficeRef = global?.Office;
      const themeObj = OfficeRef?.context?.officeTheme;
      if (themeObj?.addHandlerAsync && OfficeRef?.EventType?.OfficeThemeChanged) {
        themeObj.addHandlerAsync(OfficeRef.EventType.OfficeThemeChanged, (eventArgs) => {
          applyOutlookTheme(eventArgs?.officeTheme || null, options);
        });
        return;
      }
      if (OfficeRef?.context?.mailbox?.addHandlerAsync && OfficeRef?.EventType?.OfficeThemeChanged) {
        OfficeRef.context.mailbox.addHandlerAsync(OfficeRef.EventType.OfficeThemeChanged, (eventArgs) => {
          applyOutlookTheme(eventArgs?.officeTheme || null, options);
        });
      }
    } catch (error) {
      logError('theme.sync.bind_failed', error);
    }
  }

  global.TaskpaneThemeUtils = {
    initializeOutlookThemeSync,
    applyOutlookTheme,
    resolveExplicitThemeDarkFlag,
    isDarkRgb,
    parseRgbColor,
  };
})(window);

