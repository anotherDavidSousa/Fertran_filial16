(function () {
  const STORAGE_KEY = 'filial16-theme';
  const root = document.documentElement;

  function getStored() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return null;
    }
  }

  function setStored(value) {
    try {
      localStorage.setItem(STORAGE_KEY, value);
    } catch (e) {}
  }

  function applyTheme(theme) {
    if (theme === 'light' || theme === 'dark') {
      root.setAttribute('data-theme', theme);
      setStored(theme);
      return theme;
    }
    return null;
  }

  function toggleTheme() {
    var current = root.getAttribute('data-theme') || 'dark';
    var next = current === 'dark' ? 'light' : 'dark';
    applyTheme(next);
  }

  function init() {
    var preferred = getStored();
    if (preferred === 'light' || preferred === 'dark') {
      applyTheme(preferred);
    } else {
      root.setAttribute('data-theme', 'dark');
    }

    var btn = document.getElementById('theme-toggle');
    if (btn) {
      btn.addEventListener('click', toggleTheme);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
