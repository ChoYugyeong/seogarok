/* 서가록 — AdSense 동의 게이트 + 고정 슬롯(홈/책 상세).
   게시자 ID·슬롯 ID: /api/ads/config (Cloud Run env), 실패 시 meta fallback.
   동의 전에는 스크립트/광고/쿠키를 로드하지 않는다. */
(function () {
  var KEY = 'seogarok.ads.consent';
  var config = { client: '', slots: {} };

  function fetchConfig() {
    return fetch('/api/ads/config', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .catch(function () { return {}; })
      .then(function (d) {
        var meta = document.querySelector('meta[name="seogarok-adsense-client"]');
        var fromMeta = meta && meta.content ? meta.content.trim() : '';
        var client = (d && d.client) || fromMeta || '';
        return {
          client: client.indexOf('ca-pub-') === 0 ? client : '',
          slots: (d && d.slots) || {},
        };
      });
  }

  function init(cfg) {
    config = cfg;
    if (!config.client) return;

    function loadScript() {
      if (document.getElementById('adsbygoogle-js')) return;
      var s = document.createElement('script');
      s.id = 'adsbygoogle-js';
      s.async = true;
      s.crossOrigin = 'anonymous';
      s.src = 'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=' + encodeURIComponent(config.client);
      document.head.appendChild(s);
    }

    function mountSlots() {
      var slots = config.slots || {};
      document.querySelectorAll('[data-ad-slot]').forEach(function (el) {
        var key = el.getAttribute('data-ad-slot');
        var slot = slots[key];
        if (!slot) { el.hidden = true; return; }
        if (el.getAttribute('data-ad-mounted') === '1') return;
        el.hidden = false;
        var label = document.createElement('div');
        label.className = 'ad-label';
        label.textContent = '광고';
        var ins = document.createElement('ins');
        ins.className = 'adsbygoogle';
        ins.style.display = 'block';
        ins.setAttribute('data-ad-client', config.client);
        ins.setAttribute('data-ad-slot', slot);
        ins.setAttribute('data-ad-format', 'auto');
        ins.setAttribute('data-full-width-responsive', 'true');
        el.appendChild(label);
        el.appendChild(ins);
        el.setAttribute('data-ad-mounted', '1');
        try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (e) {}
      });
    }

    function observe() {
      if (!window.MutationObserver) return;
      var root = document.getElementById('view') || document.body;
      var timer = null;
      new MutationObserver(function () {
        if (timer) clearTimeout(timer);
        timer = setTimeout(mountSlots, 150);
      }).observe(root, { childList: true, subtree: true });
    }

    function decide(value) {
      try { localStorage.setItem(KEY, value); } catch (e) {}
      var b = document.getElementById('adsConsent');
      if (b) b.remove();
      if (value === 'yes') { loadScript(); mountSlots(); }
    }

    window.SEOG_ADS = { client: config.client, slots: config.slots, decide: decide, mount: mountSlots };

    var choice = null;
    try { choice = localStorage.getItem(KEY); } catch (e) {}
    if (choice === 'yes') { loadScript(); mountSlots(); observe(); return; }
    if (choice === 'no') { observe(); return; }

    function showBanner() {
      if (document.getElementById('adsConsent')) return;
      var el = document.createElement('div');
      el.id = 'adsConsent';
      el.className = 'ad-consent';
      el.setAttribute('role', 'dialog');
      el.setAttribute('aria-label', '광고 쿠키 동의');
      el.innerHTML =
        '<div class="ad-consent-body">' +
        '<b>광고·쿠키 설정</b>' +
        '<p>동의하면 Google AdSense 광고·쿠키가 사용됩니다. 거부해도 모든 기능을 그대로 쓸 수 있어요.</p>' +
        '<p class="ad-consent-links"><a href="/privacy.html" target="_blank" rel="noopener">개인정보처리방침</a> · <a href="https://adssettings.google.com" target="_blank" rel="noopener">Google 광고 설정</a></p>' +
        '</div>' +
        '<div class="ad-consent-actions">' +
        '<button type="button" class="ad-consent-no" data-adconsent="no">필수만</button>' +
        '<button type="button" class="ad-consent-yes" data-adconsent="yes">광고 허용</button>' +
        '</div>';
      document.body.appendChild(el);
      el.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-adconsent]');
        if (!btn) return;
        decide(btn.getAttribute('data-adconsent'));
      });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', showBanner);
    else showBanner();
    observe();
  }

  fetchConfig().then(init);
})();
