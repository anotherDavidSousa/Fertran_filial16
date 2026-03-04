(function () {
  var STORAGE_PREFIX = 'filial16-sidebar-';

  function getStorageKey(id) {
    return STORAGE_PREFIX + (id || '').replace('nav-group-', '') + '-collapsed';
  }

  function initGroup(groupId) {
    var group = document.getElementById(groupId);
    var btn = group && document.querySelector('#' + groupId + ' .nav-group-toggle');
    if (!group || !btn) return;

    var storageKey = getStorageKey(groupId);
    function isCollapsed() {
      return group.classList.contains('collapsed');
    }
    function setCollapsed(collapsed) {
      if (collapsed) {
        group.classList.add('collapsed');
        btn.setAttribute('aria-expanded', 'false');
      } else {
        group.classList.remove('collapsed');
        btn.setAttribute('aria-expanded', 'true');
      }
      try {
        localStorage.setItem(storageKey, collapsed ? '1' : '0');
      } catch (e) {}
    }
    function toggle() {
      setCollapsed(!isCollapsed());
    }

    try {
      var saved = localStorage.getItem(storageKey);
      if (saved === '1') setCollapsed(true);
    } catch (e) {}
    btn.addEventListener('click', toggle);
  }

  function initPopups() {
    document.querySelectorAll('.nav-add[data-popup]').forEach(function (el) {
      el.addEventListener('click', function (e) {
        e.preventDefault();
        var url = el.getAttribute('data-popup');
        if (url) {
          var fullUrl = url.indexOf('/') === 0 ? window.location.origin + url : url;
          window.open(fullUrl, 'popupCadastro', 'width=620,height=720,scrollbars=yes,resizable=yes');
        }
      });
    });
  }

  function init() {
    ['nav-group-fila', 'nav-group-veiculos', 'nav-group-ferramentas', 'nav-group-agregados'].forEach(function (id) {
      if (document.getElementById(id)) initGroup(id);
    });
    initPopups();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
