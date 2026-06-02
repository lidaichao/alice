// ═══════════════════════════════════════════════════
//  WorkBuddy AI — Jira Chat Panel (薄壳版)
//  不复制对话框代码，直接 fetch 共享片段
//  chat-dialog.html = 配置页同款对话框
// ═══════════════════════════════════════════════════
(function() {
  'use strict';

  // ═══ FAB ═══
  function createFAB() {
    if (!document.body) return;
    if (document.getElementById('wb-fab')) return;
    // 配置页不显示 FAB
    if (window.location.href.indexOf('wb-admin') !== -1) return;
    var fab = document.createElement('div');
    fab.id = 'wb-fab'; fab.className = 'wb-chat-fab'; fab.title = '唤起 WorkBuddy AI';
    fab.innerHTML = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M11.5 2C11.8 4.8 13.2 7.2 16 7.5C13.2 7.8 11.8 10.2 11.5 13C11.2 10.2 9.8 7.8 7 7.5C9.8 7.2 11.2 4.8 11.5 2Z"/><path d="M18.5 13C18.7 14.8 19.8 16.2 22 16.5C19.8 16.8 18.7 18.2 18.5 20C18.3 18.2 17.2 16.8 15 16.5C17.2 16.2 18.3 14.8 18.5 13Z"/><path d="M5.5 15C5.6 16.2 6.4 17.2 8 17.4C6.4 17.6 5.6 18.6 5.5 19.8C5.4 18.6 4.6 17.6 3 17.4C4.6 17.2 5.4 16.2 5.5 15Z"/></svg>';
    fab.onclick = function() { if (typeof togglePanel === 'function') togglePanel(); };
    document.body.appendChild(fab);
  }

  // ═══ 背景遮罩 ═══
  function createBackdrop() {
    if (document.getElementById('wb-chat-backdrop')) return;
    var bd = document.createElement('div');
    bd.id = 'wb-chat-backdrop';
    // 任务页不自动关闭：遮罩仅做视觉提示，不绑定点击关闭
    document.body.appendChild(bd);
  }

  // ═══ 外置关闭按钮 ═══
  function createExtCloseBtn() {
    if (document.getElementById('wb-ext-close-btn')) return;
    var btn = document.createElement('button');
    btn.id = 'wb-ext-close-btn';
    btn.textContent = '✕';
    btn.title = '关闭面板';
    btn.onclick = function() { togglePanel(); };
    document.body.appendChild(btn);
  }

  // ═══ Overlay 容器 ═══
  function createOverlay() {
    if (document.getElementById('wb-chat-overlay')) return;
    var o = document.createElement('div');
    o.id = 'wb-chat-overlay'; o.className = 'wb-dialog-scope';
    o.setAttribute('data-theme', localStorage.getItem('wb_theme') === 'dark' ? 'dark' : '');
    o.innerHTML = '<div id="wb-chat-dialog-container" style="display:flex;flex-direction:column;height:100%;overflow:hidden">'
      + '<div style="padding:16px 20px;background:var(--c-chat-header,#fff);border-bottom:1px solid var(--c-divider,#DFE1E6);font-size:16px;font-weight:700;color:var(--c-chat-header-text,#172B4D)">🤖 Jira AI</div>'
      + '<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px 20px;text-align:center">'
      + '<div style="font-size:40px;margin-bottom:16px">💬</div>'
      + '<div style="font-size:14px;font-weight:600;color:var(--c-chat-header-text,#172B4D);margin-bottom:8px">正在加载 AI 助手...</div>'
      + '<div class="skeleton" style="width:80%;max-width:300px">'
      + '<div class="skel-line"></div><div class="skel-line"></div><div class="skel-line"></div>'
      + '</div></div></div>';
    document.body.appendChild(o);
  }

  // ═══ Toggle 动画 ═══
  var _dialogLoaded = false;
  function togglePanel() {
    try {
      var p = document.getElementById('wb-chat-overlay');
      var bd = document.getElementById('wb-chat-backdrop');
      if (!p || !bd) { console.warn('[WorkBuddy] togglePanel: elements missing', !!p, !!bd); return; }
      var show = !p.classList.contains('wb-show');
      if (show) {
        p.classList.add('wb-show');
        bd.classList.add('wb-show');
        var extBtn = document.getElementById('wb-ext-close-btn');
        if (extBtn) { extBtn.classList.add('show'); extBtn.style.left = (window.innerWidth - 694) + 'px'; }
        var fab = document.getElementById('wb-fab');
        if (fab) fab.style.zIndex = '2147483644';
        if (!_dialogLoaded && !window._dialogLoading) { window._dialogLoading = true; loadDialog(); }
        var m = window.location.href.match(/(?:\/browse\/|selectedIssue=|\/issues\/|item\/)([A-Z][A-Z0-9]*-\d+)/i);
        var key = (m || [])[1] || '';
        setTimeout(function() {
          if (window.wbSetIssueKey) window.wbSetIssueKey(key);

          var bodyEl = document.getElementById('chat-body');
          if (bodyEl) { bodyEl.scrollTop = bodyEl.scrollHeight; }

          var inp = document.getElementById('chat-input');
          if (inp) inp.focus();
        }, 400);
      } else {
        p.classList.remove('wb-show');
        bd.classList.remove('wb-show');
        var extBtn2 = document.getElementById('wb-ext-close-btn');
        if (extBtn2) extBtn2.classList.remove('show');
        var fab2 = document.getElementById('wb-fab');
        if (fab2) fab2.style.zIndex = '2147483647';
        var inp = document.getElementById('chat-input');
        if (inp) inp.blur();
      }
    } catch(e) {
      console.error('[WorkBuddy] togglePanel error:', e);
    }
  }

  window.wbTogglePanel = togglePanel;

  window.addEventListener('resize', function() {
    var btn = document.getElementById('wb-ext-close-btn');
    if (btn && btn.classList.contains('show')) {
      btn.style.left = (window.innerWidth - 694) + 'px';
    }
  });

  // ═══ Init (带重试防 Jira 页面生命周期干扰) ═══
  var _initAttempts = 0;
  function tryInit() {
    if (!document.body || document.body.children.length === 0) {
      // DOM 还没就绪，延迟重试
      if (_initAttempts < 10) { _initAttempts++; setTimeout(tryInit, 500); }
      return;
    }
    createFAB();
    createBackdrop();
    createExtCloseBtn();
    createOverlay();
    _initAttempts = 0;
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') tryInit();
  else document.addEventListener('DOMContentLoaded', tryInit);
  setTimeout(tryInit, 500);
  setTimeout(tryInit, 2000);

  // ═══ Load shared dialog from server ═══
  function loadDialog() {
    var container = document.getElementById('wb-chat-dialog-container');
    if (!container) return;

    fetch('/plugins/servlet/wb/chat-dialog?_=' + Date.now())
      .then(function(r) { return r.text(); })
      .then(function(html) {
        container.innerHTML = html;

        var inlineCode = '';
        var externalScripts = [];
        container.querySelectorAll('script').forEach(function(oldScript) {
          if (oldScript.src) externalScripts.push(oldScript.src);
          else inlineCode += oldScript.textContent + '\n';
          oldScript.remove();
        });

        function loadScripts(urls, callback) {
          if (urls.length === 0) return callback();
          var s = document.createElement('script');
          s.src = urls.shift();
          var _done = false;
          s.onload = function() { if (!_done) { _done = true; loadScripts(urls, callback); } };
          s.onerror = function() { console.warn('[WorkBuddy] CDN script failed:', s.src); if (!_done) { _done = true; loadScripts(urls, callback); } };
          // 超时兜底：8 秒后跳过，防止国内网络 CDN 永久阻塞
          setTimeout(function() { if (!_done) { console.warn('[WorkBuddy] CDN script timeout:', s.src); _done = true; loadScripts(urls, callback); } }, 8000);
          document.head.appendChild(s);
        }

        loadScripts(externalScripts, function() {
          if (inlineCode) {
            var s = document.createElement('script');
            s.textContent = inlineCode;
            container.appendChild(s);
          }
          _dialogLoaded = true;
          window.wbChatApiEndpoint = '/plugins/servlet/wb/chat';
          var savedCfg = null;
          try { savedCfg = JSON.parse(localStorage.getItem('wb_test_config')); } catch(e) {}
          window.wbBridgeUrl = (savedCfg && savedCfg.bridge_url) || 'http://localhost:9099';
          var m = window.location.href.match(/(?:\/browse\/|selectedIssue=|\/issues\/|item\/)([A-Z][A-Z0-9]*-\d+)/i);
        var key = (m || [])[1] || '';
          setTimeout(function() {
            if (window.wbSetIssueKey) window.wbSetIssueKey(key);
          }, 500);
        });
      })
      .catch(function() {
        container.innerHTML = '<div style="text-align:center;padding:60px 20px">'
          + '<div style="font-size:48px;margin-bottom:16px">⚠️</div>'
          + '<div style="color:var(--c-ai-label, #8C98A8);font-size:14px;margin-bottom:8px">对话框加载失败</div>'
          + '<div style="color:var(--c-ai-label, #8C98A8);font-size:12px;margin-bottom:20px">请检查网络连接或 Jira 插件状态</div>'
          + '<button onclick="location.reload()" style="padding:8px 24px;border:1px solid var(--c-input-focus,#4C9AFF);border-radius:8px;background:var(--c-input-focus,#4C9AFF);color:#fff;cursor:pointer;font-size:14px;font-weight:600">🔄 点击重试</button>'
          + '</div>';
      });
  }

})();
