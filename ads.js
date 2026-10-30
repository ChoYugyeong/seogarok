/* 서가록 — AdSense 동의 게이트.
   게시자 ID: meta[name=seogarok-adsense-client] 우선, 없으면 /api/ads/config.
   동의 전에는 스크립트/쿠키를 로드하지 않는다. */
(function () {
  var KEY = 'seogarok.ads.consent';

  function getClient() {
    var meta = document.querySelector('meta[name="seogarok-adsense-client"]');
    var fromMeta = meta && meta.content ? meta.content.trim() : '';
    if (fromMeta.indexOf('ca-pub-') === 0) return Promise.resolve(fromMeta);
    return fetch('/api/ads/config', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (d) { return d && d.client && d.client.indexOf('ca-pub-') === 0 ? d.client : ''; })
      .catch(function () { return ''; });
  }

  function init(client) {
    if (!client) return;

    function loadScript() {
      if (document.getElementById('adsbygoogle-js')) return;
      var s = document.createElement('script');
      s.id = 'adsbygoogle-js';
      s.async = true;
      s.crossOrigin = 'anonymous';
      s.src = 'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=' + encodeURIComponent(client);
      document.head.appendChild(s);
    }

    function decide(value) {
      try { localStorage.setItem(KEY, value); } catch (e) {}
      var b = document.getElementById('adsConsent');
      if (b) b.remove();
      if (value === 'yes') loadScript();
    }

    window.SEOG_ADS = { client: client, decide: decide, reload: loadScript };

    var choice = null;
    try { choice = localStorage.getItem(KEY); } catch (e) {}
    if (choice === 'yes') { loadScript(); return; }
    if (choice === 'no') return;

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
        '<p>서가록은 무료로 운영됩니다. 동의하면 Google AdSense 광고(맞춤형)가 표시되며, Google이 광고 쿠키를 사용할 수 있습니다. 거부해도 모든 기능을 그대로 쓸 수 있어요.</p>' +
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
  }

  getClient().then(init);
})();
