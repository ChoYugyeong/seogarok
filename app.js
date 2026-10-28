/* =========================================================
   서가록 (seogarok) — app
   ========================================================= */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const LS_KEY = 'seogarok.v1';
const LS_LEGACY = 'seoga.v1'; // 이전 버전 데이터 마이그레이션
const DEFAULT_STATE = {
  subs: { millie: true, ridiselect: false, sam: true, willa: false },
  shelf: { want: ['hailmary', 'samche', 'mulgogi'], reading: ['chae'], done: ['pyeonuijeom'] },
  alerts: {},
};

const state = {
  tab: 'explore',
  query: '',
  filter: 'all',
  collection: null,
  shelfTab: 'want',
  openId: null,
  taste: { answers: [] },
  subs: { ...DEFAULT_STATE.subs },
  shelf: { want: [...DEFAULT_STATE.shelf.want], reading: [...DEFAULT_STATE.shelf.reading], done: [...DEFAULT_STATE.shelf.done] },
  alerts: {},
  // --- 백엔드 연동 상태 ---
  searchMode: 'hybrid',
  api: { on: false, checked: false, loading: false, hits: [], meta: null, error: null, seq: 0, health: null },
  discover: [],
  tlDate: null,
  cache: {}, // id -> api book (검색 결과/상세 캐시)
  notices: [], // 수집된 종료 예정 공지 (실데이터 + fixture)
};

/* =========================================================
   백엔드 API (없으면 자동으로 로컬 데모 모드로 폴백)
   ========================================================= */
const API = {
  base: location.protocol === 'file:' ? null : '',
  async call(path, params) {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    const t = performance.now();
    const res = await fetch((this.base ?? '') + path + qs, { headers: { accept: 'application/json' } });
    if (!res.ok) throw new Error(path + ' ' + res.status);
    const data = await res.json();
    data.__rtt = Math.round(performance.now() - t);
    return data;
  },
  health() { return this.call('/api/health'); },
  search(q, mode, limit) { return this.call('/api/search', { q, mode, limit: limit || 24 }); },
  book(id) { return this.call('/api/book', { id }); },
  suggest(q) { return this.call('/api/suggest', { q }); },
};

function mapApiBook(r) {
  const cat = (r.category || '').split('>').map((s) => s.trim()).filter(Boolean);
  return {
    id: r.id,
    title: r.title,
    author: r.author || '저자 미상',
    publisher: r.publisher || '',
    year: (r.pubdate || '').slice(0, 4),
    pages: null,
    tags: cat.slice(1, 3).length ? cat.slice(1, 3) : cat.slice(0, 2),
    moods: [],
    blurb: r.description || null,
    av: r.av || {},
    av_origin: r.av_origin || {},
    notices: r.notices || [],
    cover_url: r.cover_url || null,
    price: r.price,
    price_list: r.price_list,
    rating: r.rating,
    link: r.link,
    score: r.score,
    similar: r.similar || [],
    real: true,
  };
}
function cacheBooks(list) {
  list.forEach((b) => { state.cache[b.id] = b; });
}
function lookupBook(id) {
  return bookById(id) || state.cache[id] || null;
}

/* ---------------- persistence ---------------- */
function save() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ subs: state.subs, shelf: state.shelf, alerts: state.alerts }));
  } catch (e) { /* ignore */ }
}
function load() {
  try {
    const raw = localStorage.getItem(LS_KEY) || localStorage.getItem(LS_LEGACY);
    if (raw && !localStorage.getItem(LS_KEY)) {
      // 이전 버전(seoga.v1) 데이터를 새 키로 승계
      localStorage.setItem(LS_KEY, raw);
      localStorage.removeItem(LS_LEGACY);
    }
    if (!raw) return;
    const d = JSON.parse(raw);
    if (d.subs) state.subs = { ...DEFAULT_STATE.subs, ...d.subs };
    if (d.shelf) state.shelf = { ...DEFAULT_STATE.shelf, ...d.shelf };
    if (d.alerts) state.alerts = d.alerts;
  } catch (e) { /* ignore */ }
}

/* ---------------- helpers ---------------- */
const bookById = (id) => BOOKS.find((b) => b.id === id);
const subsOn = () => SUB_KEYS.filter((k) => state.subs[k]);
const isEnding = (v) => v && v.s === 'ending';
const isOn = (v) => v && v.s === 'on';

function coverStyle(book) {
  let h = 0;
  for (let i = 0; i < book.title.length; i++) h = (h * 31 + book.title.charCodeAt(i)) % 360;
  const h2 = (h + 46) % 360;
  return `--cg: linear-gradient(152deg, hsl(${h} 44% 27%), hsl(${h2} 50% 12%) 74%)`;
}

function coverHTML(book, extraClass = '') {
  const end = endings(book)[0];
  const band = end ? `<div class="cover-band"><i></i>${esc(PLATFORMS[end.k].short)} · D-${end.d}</div>` : '';
  const mods = `${end ? 'has-band' : ''} ${end && end.d <= 7 ? 'urgent' : ''} ${extraClass}`;

  // 실표지가 있으면 이미지로 (알라딘/교보 수집분)
  if (book.cover_url) {
    return `<div class="cover has-img ${mods}" style="${coverStyle(book)}">
      ${band}
      <img class="cover-img" src="${esc(book.cover_url)}" alt="${esc(book.title)}" loading="lazy"
        onerror="this.closest('.cover').classList.remove('has-img'); this.remove();" />
    </div>`;
  }

  return `<div class="cover ${mods}" style="${coverStyle(book)}">
    ${band}
    <div class="cover-top">
      <div class="cover-rule"></div>
      <div class="cover-title">${esc(book.title)}</div>
    </div>
    <div class="cover-bottom"><div class="cover-author">${esc(book.author)}</div></div>
  </div>`;
}

function daysWord(d) {
  if (d === 0) return '오늘';
  if (d === 1) return '내일';
  return `D-${d}`;
}
function endDateText(d) {
  const t = new Date();
  t.setDate(t.getDate() + d);
  return `${t.getMonth() + 1}월 ${t.getDate()}일`;
}

/** 책의 모든 가용성 정보를 정규화 */
function avInfo(book) {
  const subs = SUB_KEYS.map((k) => {
    const v = book.av[k];
    if (!v) return { k, status: 'none' };
    if (v.s === 'on') return { k, status: 'on' };
    if (v.s === 'ending') return { k, status: 'ending', d: v.d };
    return { k, status: 'none' };
  });
  const buy = ['aladin', 'yes24', 'kyobo', 'ridi']
    .filter((k) => book.av[k] && book.av[k].buy)
    .map((k) => ({ k, price: book.av[k].buy }));
  const free = [];
  if (book.av.gongu) free.push({ k: 'gongu' });
  if (book.av.library) free.push({ k: 'library', wait: book.av.library.wait || 0 });
  return { subs, buy, free };
}

/** 내 구독 기준으로 지금 읽을 수 있는가 */
function myAccess(book) {
  const on = subsOn();
  const rows = on
    .map((k) => ({ k, v: book.av[k] }))
    .filter((x) => x.v && (isOn(x.v) || isEnding(x.v)));
  return rows;
}
function endings(book) {
  return subsOn()
    .map((k) => ({ k, v: book.av[k] }))
    .filter((x) => isEnding(x.v))
    .map((x) => ({ k: x.k, d: x.v.d }))
    .sort((a, b) => a.d - b.d);
}
function anyFree(book) {
  return !!(book.av.gongu || book.av.library);
}

/** 카드에 표시할 배지 */
function pillsHTML(book, max = 3) {
  const out = [];
  const end = endings(book)[0];
  if (end) out.push(`<span class="pill end">${esc(PLATFORMS[end.k].short)} D-${end.d}</span>`);

  const mine = myAccess(book)
    .filter((x) => !end || x.k !== end.k)
    .slice(0, 2);
  mine.forEach((x) => out.push(`<span class="pill sub">${esc(PLATFORMS[x.k].short)}</span>`));

  if (out.length < max) {
    const anySub = avInfo(book).subs.find((s) => s.status === 'on' && !out.some((o) => o.includes(PLATFORMS[s.k].short)));
    if (anySub && !state.subs[anySub.k]) out.push(`<span class="pill ghost">${esc(PLATFORMS[anySub.k].short)}</span>`);
  }
  if (out.length < max && book.av.gongu) out.push(`<span class="pill free">무료</span>`);
  if (out.length < max && book.av.library) {
    const w = book.av.library.wait || 0;
    out.push(`<span class="pill free">도서관${w ? ` 대기${w}` : ''}</span>`);
  }
  if (out.length === 0) {
    const b = avInfo(book).buy[0];
    if (b) out.push(`<span class="pill buy">${b.price.toLocaleString()}원</span>`);
    else out.push(`<span class="pill ghost">정보 없음</span>`);
  }
  // 운영 모드: 구독 가용성이 아직 확인되지 않은 책은 '미확인'으로 정직하게 표시
  const unknownSubs = SUB_KEYS.filter((k) => (book.av_origin || {})[k] === 'unknown');
  if (unknownSubs.length && out.length < max) {
    out.push(`<span class="pill ghost">가용성 미확인</span>`);
  }
  return out.slice(0, max).join('');
}

function bookCardHTML(book) {
  return `<button class="card" data-book="${book.id}" aria-label="${esc(book.title)} 상세 보기">
    <div class="card-cover">
      ${coverHTML(book)}
    </div>
    <div class="card-body">
      <div class="card-title">${esc(book.title)}</div>
      <div class="card-author">${esc(book.author)}</div>
      <div class="avail">${pillsHTML(book)}</div>
    </div>
  </button>`;
}

const gridHTML = (list) => `<div class="grid">${list.map(bookCardHTML).join('')}</div>`;

function sortByUsefulness(list) {
  return list.slice().sort((a, b) => {
    const ea = endings(a).length ? endings(a)[0].d : 999;
    const eb = endings(b).length ? endings(b)[0].d : 999;
    if (ea !== eb) return ea - eb;
    if (!!b.hot - !!a.hot) return (!!b.hot) - (!!a.hot);
    return a.title.localeCompare(b.title, 'ko');
  });
}

/* ---------------- toast ---------------- */
let toastTimer = null;
function toast(msg) {
  const root = $('#toastRoot');
  const el = document.createElement('div');
  el.className = 'toast';
  el.innerHTML = `<span class="tick">✓</span>${esc(msg)}`;
  root.appendChild(el);
  setTimeout(() => {
    el.classList.add('is-out');
    setTimeout(() => el.remove(), 260);
  }, 2100);
}

/* ---------------- shelf helpers ---------------- */
const SHELF_LABEL = { want: '관심', reading: '읽는 중', done: '완독' };
function inShelf(id) {
  return ['want', 'reading', 'done'].find((k) => state.shelf[k].includes(id)) || null;
}
function toggleShelf(id, list) {
  const current = inShelf(id);
  ['want', 'reading', 'done'].forEach((k) => {
    state.shelf[k] = state.shelf[k].filter((x) => x !== id);
  });
  if (current !== list) {
    state.shelf[list].push(id);
    toast(`서재 > ${SHELF_LABEL[list]}에 담았어요`);
  } else {
    toast('서재에서 뺐어요');
  }
  save();
  render();
  refreshDrawer();
}
function toggleAlert(key, days) {
  if (state.alerts[key]) {
    delete state.alerts[key];
    toast('종료 알림을 껐어요');
  } else {
    state.alerts[key] = true;
    const n = Number(days);
    const lead = Number.isFinite(n) && n > 0 ? Math.max(1, Math.min(30, n - 3)) : 3;
    toast(`이 책이 내려가기 ${lead}일 전에 알려드릴게요`);
  }
  save();
  render();
  refreshDrawer();
}
function shelfCount() {
  return state.shelf.want.length + state.shelf.reading.length + state.shelf.done.length;
}

/* ---------------- views ---------------- */
function heroChips() {
  const chips = ['한강', '김초엽', 'SF', '에세이', '삼체'];
  return `<span class="q-label">이런 걸 자주 찾아요</span>` + chips
    .map((c) => `<button class="chip" data-quick="${esc(c)}">${esc(c)}</button>`)
    .join('');
}

function alertPanelHTML(entries, inShelfMode) {
  const rows = entries.map(({ b, k, d }) => {
    const key = `${b.id}:${k}`;
    const on = !!state.alerts[key];
    return `<div class="alert-row" data-book="${b.id}" role="button" tabindex="0">
      <div class="mini-cover" style="${coverStyle(b)}; background: var(--cg)"><span>${esc(b.title)}</span></div>
      <div class="alert-main">
        <b>${esc(b.title)}</b>
        <p><span class="plat">${esc(PLATFORMS[k].name)}</span><span class="sep">·</span>${endDateText(d)} 종료<span class="sep">·</span>${esc(b.author)}</p>
      </div>
      <div class="alert-right">
        <span class="alert-dday">D-${d}</span>
        <button class="btn-alert ${on ? 'is-on' : ''}" data-alert="${b.id}:${k}" data-d="${d}">${on ? '알림 켜짐 ✓' : '종료 알림'}</button>
      </div>
    </div>`;
  }).join('');
  return `<div class="alert-panel">${rows}</div>`;
}

function endingEntries() {
  const ids = new Set([...state.shelf.want, ...state.shelf.reading]);
  const out = [];
  BOOKS.forEach((b) => {
    if (!ids.has(b.id)) return;
    endings(b).forEach(({ k, d }) => out.push({ b, k, d }));
  });
  return out.sort((a, b) => a.d - b.d);
}
function allEndings() {
  const out = [];
  BOOKS.forEach((b) => endings(b).forEach(({ k, d }) => out.push({ b, k, d })));
  return out.sort((a, b) => a.d - b.d);
}

function collectionGrid(filterId) {
  const c = COLLECTIONS.find((x) => x.id === filterId);
  if (!c) return '';
  let list = BOOKS.filter(c.pick);
  if (subsOn().length) list = sortByUsefulness(list.filter((b) => myAccess(b).length));
  if (!list.length) list = BOOKS.filter(c.pick).slice(0, 8);
  return `<div class="section" id="collectionResult">
    <div class="sec-head">
      <div>
        <h3 class="sec-title">${esc(c.title)}</h3>
        <p class="sec-desc">${esc(c.desc)} · ${list.length}권</p>
      </div>
      <button class="sec-more" data-act="clear-collection">닫기 ✕</button>
    </div>
    ${gridHTML(list.slice(0, 12))}
  </div>`;
}

const COLLECTION_QUERY = {
  night: '에세이', commute: '에세이', weekend: '소설',
  think: '문학', science: '과학', korean: '한국소설',
};

/* API(운영) 모드 홈: 실수집 공지 + 검색으로 이어지는 컬렉션만 보여준다.
   데모 전용 데이터(시뮬레이션 종료/가용성)를 라이브 화면에 노출하지 않기 위함. */
/* ---------------- 검색 자동완성 / 최근 검색 / 발견 ---------------- */
const RECENT_KEY = 'seogarok.recent';
const GENRE_CHIPS = ['소설', '에세이', '인문', '과학', 'SF', '역사', '자기계발', '경제', '여행', '어린이'];
const DISCOVER_QUERIES = [
  { label: '지금 서가의 소설', q: '소설' },
  { label: '이번 주 에세이', q: '에세이' },
];

function hl(text, q) {
  const term = (q || '').trim();
  const t = String(text || '');
  if (!term) return esc(t);
  const i = t.toLowerCase().indexOf(term.toLowerCase());
  if (i < 0) return esc(t);
  return esc(t.slice(0, i)) + '<mark>' + esc(t.slice(i, i + term.length)) + '</mark>' + esc(t.slice(i + term.length));
}

function recentSearches() {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]').slice(0, 6); } catch (e) { return []; }
}
function pushRecent(q) {
  const v = String(q || '').trim();
  if (!v) return;
  const list = recentSearches().filter((x) => x !== v);
  list.unshift(v);
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 6))); } catch (e) { }
  renderRecent();
}
function renderRecent() {
  const row = document.querySelector('#recentRow');
  if (!row) return;
  const list = recentSearches();
  if (!list.length) { row.hidden = true; row.innerHTML = ''; return; }
  row.hidden = false;
  row.innerHTML = `<span class="recent-label">최근 검색</span>` +
    list.map((q) => `<button class="recent-chip" data-recent="${esc(q)}">${esc(q)}</button>`).join('') +
    `<button class="recent-clear" data-recent-clear aria-label="최근 검색 지우기">지우기</button>`;
}

function setupSuggest(inputSel, popSel) {
  const input = document.querySelector(inputSel);
  const pop = document.querySelector(popSel);
  if (!input || !pop) return;
  let items = [];
  let active = -1;
  let timer = null;
  let seq = 0;

  const close = () => { pop.hidden = true; pop.innerHTML = ''; active = -1; items = []; };
  const render = (q) => {
    if (!items.length) { close(); return; }
    pop.innerHTML =
      items.map((it, i) => `<button class="sug-row${i === active ? ' is-active' : ''}" data-sug="${i}" role="option" aria-selected="${i === active}">
        <span class="sug-cover">${it.cover_url ? `<img src="${esc(it.cover_url)}" alt="" loading="lazy">` : ''}</span>
        <span class="sug-main"><b>${hl(it.title, q)}</b><span class="sug-author">${hl(it.author || '', q)}</span></span>
      </button>`).join('') +
      `<button class="sug-more" data-sug-more>‘${esc(q)}’ 전체 결과 보기 <span aria-hidden="true">→</span></button>`;
    pop.hidden = false;
  };
  const fetchItems = (q) => {
    const my = ++seq;
    clearTimeout(timer);
    if (!q) { close(); return; }
    timer = setTimeout(async () => {
      try {
        let next = [];
        if (state.api.on) {
          const r = await API.suggest(q);
          next = (r.items || []).slice(0, 6);
        } else {
          const lower = q.toLowerCase();
          next = BOOKS
            .filter((b) => `${b.title} ${b.author}`.toLowerCase().includes(lower))
            .slice(0, 6)
            .map((b) => ({ id: b.id, title: b.title, author: b.author, cover_url: b.cover_url }));
        }
        if (my !== seq) return;
        items = next;
        active = -1;
        render(q);
      } catch (e) { close(); }
    }, 160);
  };
  const choose = (i) => {
    const it = items[i];
    if (!it) return;
    close();
    input.blur();
    openBook(it.id);
  };
  const searchAll = () => {
    const q = input.value.trim();
    if (!q) return;
    close();
    setQuery(q);
    pushRecent(q);
  };

  input.addEventListener('input', () => fetchItems(input.value.trim()));
  input.addEventListener('focus', () => { if (input.value.trim()) fetchItems(input.value.trim()); });
  input.addEventListener('keydown', (e) => {
    if (pop.hidden) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); active = (active + 1) % items.length; render(input.value.trim()); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); active = (active - 1 + items.length) % items.length; render(input.value.trim()); }
    else if (e.key === 'Enter') { if (active >= 0) { e.preventDefault(); choose(active); } else { searchAll(); } }
    else if (e.key === 'Escape') { close(); }
  });
  pop.addEventListener('mousedown', (e) => {
    e.preventDefault();
    const row = e.target.closest('[data-sug]');
    if (row) { choose(Number(row.dataset.sug)); return; }
    if (e.target.closest('[data-sug-more]')) searchAll();
  });
  document.addEventListener('click', (e) => {
    if (!pop.hidden && !pop.contains(e.target) && e.target !== input) close();
  });
}

async function loadDiscover() {
  if (!state.api.on) return;
  try {
    const res = await Promise.all(DISCOVER_QUERIES.map((d) => API.search(d.q, 'hybrid', 6)));
    state.discover = DISCOVER_QUERIES
      .map((d, i) => ({ label: d.label, q: d.q, books: (res[i].results || []).map(mapApiBook) }))
      .filter((x) => x.books.length);
    cacheBooks(state.discover.flatMap((x) => x.books));
    render();
  } catch (e) { }
}

function renderDiscoverRails() {
  const rails = (state.discover || []).map((r) => `<section class="section">
    <div class="sec-head">
      <div>
        <h3 class="sec-title">${esc(r.label)}</h3>
        <p class="sec-desc">실제 서가에서 찾은 ${r.books.length}권 · ‘${esc(r.q)}’ 검색</p>
      </div>
      <button class="sec-more" data-genre="${esc(r.q)}">더 보기 →</button>
    </div>
    <div class="grid rail-grid">${r.books.map(bookCardHTML).join('')}</div>
  </section>`).join('');
  return rails;
}

function renderGenreChips() {
  const chips = GENRE_CHIPS.map((g) => `<button class="genre-chip" data-genre="${esc(g)}">${esc(g)}</button>`).join('');
  return `<section class="section">
    <div class="sec-head">
      <div>
        <h3 class="sec-title">장르로 둘러보기</h3>
        <p class="sec-desc">지금 서가에 있는 책을 장르로 바로 찾아보세요.</p>
      </div>
    </div>
    <div class="genre-row">${chips}</div>
  </section>`;
}

function renderExploreApi() {
  const collections = COLLECTIONS.map((c) => `
    <button class="col-card" data-col="${c.id}">
      <b>${esc(c.title)}</b>
      <p>${esc(c.desc)}</p>
      <span class="col-n">검색 · ${esc(COLLECTION_QUERY[c.id] || '')}</span>
    </button>`).join('');
  return `
  ${noticesSection()}
  ${renderGenreChips()}
  ${renderDiscoverRails()}

  <section class="section">
    <div class="sec-head">
      <div>
        <h3 class="sec-title">상황으로 찾기</h3>
        <p class="sec-desc">장르보다 '지금 내 상황'이 먼저일 때. 실제 서가에서 바로 찾아드려요.</p>
      </div>
    </div>
    <div class="collections">${collections}</div>
  </section>

  <section class="cta-band">
    <div>
      <h3>뭘 읽을지 모르겠다면</h3>
      <p>네 문항이면 끝나요. 고른 취향으로 <b>서가를 검색</b>해 실제 책을 보여드려요.</p>
    </div>
    <button class="cta-btn" data-tab="taste">취향 찾기 시작 →</button>
  </section>`;
}

function renderExplore() {
  if (state.api.on) return renderExploreApi();
  const on = subsOn();
  const readable = sortByUsefulness(BOOKS.filter((b) => myAccess(b).length)).slice(0, 12);

  const mineEnd = endingEntries();
  const entries = mineEnd.length ? mineEnd : allEndings().slice(0, 4);
  const alertTitle = mineEnd.length ? '서재에서 곧 사라져요' : '이번 달, 문을 닫는 책';
  const alertDesc = mineEnd.length
    ? '관심 목록·읽는 중인 책 중 30일 안에 구독에서 내려가는 책이에요.'
    : '아직 서재에 없어요. 담아두면 종료 전에 알려드려요.';

  const alertSection = `<section class="section">
    <div class="sec-head">
      <div>
        <h3 class="sec-title"><span class="ico">!</span>${entries.length ? alertTitle : '종료 임박 추적'}</h3>
        <p class="sec-desc">${entries.length ? alertDesc : (on.length ? '지금은 30일 안에 종료되는 책이 없어요.' : '쓰는 구독을 켜면 종료 예정인 책을 여기서 추적해드려요.')}</p>
      </div>
    </div>
    ${entries.length
      ? alertPanelHTML(entries, mineEnd.length > 0)
      : `<div class="alert-empty">
          <span>${on.length ? '종료 예정이 잡히면 바로 알려드릴게요.' : '구독을 켜야 종료 예정을 추적할 수 있어요.'}</span>
          ${on.length ? '' : '<button class="btn-alert" data-act="open-subs">내 구독 설정</button>'}
        </div>`}
  </section>`;

  const subRow = `<div class="filter-bar" style="border:none;margin:4px 0 16px;padding:0">
    <span class="fb-label">내 구독</span>
    ${SUB_KEYS.map((k) => `<button class="fchip ${state.subs[k] ? 'is-on' : ''}" data-subs-toggle="${k}">${esc(PLATFORMS[k].short)}</button>`).join('')}
    <span class="spacer"></span>
    <span style="font-size:12px;color:var(--text-3)">바로 읽을 수 있는 책 <b style="color:var(--text-2)">${BOOKS.filter((b) => myAccess(b).length).length}</b>권</span>
  </div>`;

  const readableBlock = on.length
    ? (readable.length ? gridHTML(readable) : `<div class="empty"><b>조건에 맞는 책이 없어요</b><p>다른 구독을 켜보거나 검색해 보세요.</p></div>`)
    : `<div class="empty">
        <b>구독을 아직 고르지 않았어요</b>
        <p>위에서 쓰고 있는 구독을 켜면, 당장 읽을 수 있는 책만 모아드려요.</p>
        <button class="link" data-act="open-subs">내 구독 설정하기 →</button>
      </div>`;

  return `
  ${alertSection}

  <section class="section">
    <div class="sec-head">
      <div>
        <h3 class="sec-title">내 구독으로 바로 읽는 책</h3>
        <p class="sec-desc">${on.length ? `${on.map((k) => PLATFORMS[k].name).join(' · ')} 기준` : '구독을 선택해 주세요'}</p>
      </div>
      <button class="sec-more" data-act="open-subs">구독 설정 →</button>
    </div>
    ${subRow}
    ${readableBlock}
  </section>

  ${noticesSection()}

  <section class="section">
    <div class="sec-head">
      <div>
        <h3 class="sec-title">상황으로 찾기</h3>
        <p class="sec-desc">장르보다 '지금 내 상황'이 먼저일 때.</p>
      </div>
    </div>
    <div class="collections">
      ${COLLECTIONS.map((c) => {
        const n = BOOKS.filter(c.pick).length;
        return `<button class="col-card" data-col="${c.id}">
          <b>${esc(c.title)}</b>
          <p>${esc(c.desc)}</p>
          <span class="col-n">${n}권</span>
        </button>`;
      }).join('')}
    </div>
  </section>

  ${state.collection ? collectionGrid(state.collection) : ''}

  <section class="cta-band">
    <div>
      <h3>뭘 읽을지 모르겠다면</h3>
      <p>네 문항이면 끝나요. 취향을 고르면 <b>왜 이 책인지</b>까지 설명해 드려요.</p>
    </div>
    <button class="cta-btn" data-tab="taste">취향 찾기 시작 →</button>
  </section>`;
}

function renderSearch() {
  return state.api.on ? renderApiSearch() : renderLocalSearch();
}

const MODE_LABEL = { hybrid: '하이브리드', keyword: '키워드', vector: '벡터' };
const PLATFORM_NAME = { millie: '밀리의 서재', ridiselect: '리디셀렉트', sam: '교보 sam', willa: '윌라', crema: '크레마클럽' };

function daysUntil(iso) {
  if (!iso) return null;
  const d = new Date(iso + 'T00:00:00');
  if (Number.isNaN(d.getTime())) return null;
  return Math.round((d - new Date(new Date().toDateString())) / 86400000);
}

function noticesSection() {
  if (!state.api.on) return '';
  const all = state.notices || [];
  if (!all.length) return '';
  const real = all.filter((n) => n.source_kind && n.source_kind !== 'fixture');
  const src = real.length ? real : all;
  const platforms = [...new Set(src.map((n) => n.platform))];
  const label = platforms.map((p) => PLATFORM_NAME[p] || p).join(' · ');
  const realCount = state.noticeReal || real.length;

  // 날짜별 버킷 (YYYY-MM-DD)
  const buckets = new Map();
  src.forEach((n) => {
    const k = String(n.ends_at || '').slice(0, 10);
    if (!k) return;
    if (!buckets.has(k)) buckets.set(k, []);
    buckets.get(k).push(n);
  });

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(today);
    d.setDate(d.getDate() + i);
    const k = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    days.push({ i, date: d, k, n: (buckets.get(k) || []).length });
  }
  const totalUpcoming = days.reduce((a, b) => a + b.n, 0);

  const rowFor = (n) => {
    const d = daysUntil(n.ends_at);
    const isReal = n.source_kind && n.source_kind !== 'fixture';
    const dd = d === null ? '미확인' : d < 0 ? '종료됨' : d === 0 ? '오늘' : `D-${d}`;
    return `<div class="notice-row">
      <div class="notice-main">
        <b>${esc(n.title)}</b>
        <p>${esc(n.author || '저자 미상')}<span class="sep">·</span><span class="plat">${esc(PLATFORM_NAME[n.platform] || n.platform)}</span></p>
      </div>
      <div class="notice-right">
        <span class="notice-dday ${d !== null && d <= 3 ? 'hot' : ''}">${dd}</span>
        ${n.source_url && isReal ? `<a class="notice-src" href="${esc(n.source_url)}" target="_blank" rel="noopener" title="출처 열기">↗</a>` : ''}
      </div>
    </div>`;
  };

  // 타임라인 스트립 (오늘~D-6)
  const dow = ['일', '월', '화', '수', '목', '금', '토'];
  const strip = days.map((d) => `<button class="tl-day${d.i === 0 ? ' is-today' : ''}${d.n ? ' has' : ''}${state.tlDate === d.k ? ' is-on' : ''}" data-tl="${d.k}" aria-label="${d.date.getMonth() + 1}월 ${d.date.getDate()}일 ${d.n}권">
      <span class="tl-dow">${dow[d.date.getDay()]}</span>
      <span class="tl-date">${d.date.getDate()}</span>
      <span class="tl-n">${d.n || '·'}</span>
    </button>`).join('');

  // 그룹 (선택된 날짜가 있으면 그것만, 없으면 전체 예정일, 예정이 없으면 최근 6건)
  const visible = state.tlDate ? days.filter((d) => d.k === state.tlDate) : days.filter((d) => d.n);
  const groups = visible.map((d) => {
    const list = (buckets.get(d.k) || []).slice(0, 4);
    const head = d.i === 0 ? '오늘' : d.i === 1 ? '내일' : `D-${d.i}`;
    return `<div class="tl-group">
      <div class="tl-group-head"><b>${head}</b> · ${d.date.getMonth() + 1}월 ${d.date.getDate()}일 (${dow[d.date.getDay()]}) <span>${d.n}권</span></div>
      <div class="notice-panel">${list.map(rowFor).join('')}</div>
    </div>`;
  }).join('');

  const fallback = (() => {
    const past = src
      .filter((n) => n.ends_at && daysUntil(n.ends_at) < 0)
      .sort((a, b) => String(b.ends_at).localeCompare(String(a.ends_at)))
      .slice(0, 6);
    return past.length ? `<div class="notice-panel">${past.map(rowFor).join('')}</div>` : '';
  })();

  return `<section class="section" id="timeline">
    <div class="sec-head">
      <div>
        <h3 class="sec-title"><span class="ico">↓</span>종료 예정 타임라인</h3>
        <p class="sec-desc">${esc(label)} 공지 <b style="color:var(--text-2)">${realCount}건</b> · 이번 주 예정 <b style="color:var(--accent)">${totalUpcoming}권</b> · 매일 갱신</p>
      </div>
      ${state.tlDate ? `<button class="sec-more" data-tl-clear>전체 보기 →</button>` : ''}
    </div>
    <div class="tl-strip">${strip}</div>
    <div class="tl-groups">${groups || fallback}</div>
  </section>`;
}

function renderApiSearch() {
  const api = state.api;
  const q = state.query.trim();
  const m = api.meta;
  const modeBtn = (id, label) =>
    `<button class="fchip ${state.searchMode === id ? 'is-on' : ''}" data-mode="${id}">${label}</button>`;

  const timing = m
    ? `<span class="timing">
         <b>${m.took_ms}ms</b>
         <span class="timing-sub">키워드 ${(m.stage_ms && m.stage_ms.keyword) || 0}ms · 벡터 ${(m.stage_ms && m.stage_ms.vector) || 0}ms · 융합 ${(m.stage_ms && m.stage_ms.fuse) || 0}ms</span>
       </span>`
    : '';

  const cand = m && m.candidates
    ? `<span class="cand">후보 · 키워드 ${m.candidates.keyword} · 벡터 ${m.candidates.vector}</span>`
    : '';
  const STRAT = { 'exact-first': '정확 일치 우선', rrf: 'RRF 융합', 'vector-only': '벡터 단독' };
  const strat = m && m.strategy
    ? `<span class="strat strat-${m.strategy}">${STRAT[m.strategy] || m.strategy}</span>`
    : '';

  let body;
  if (api.loading && !api.hits.length) {
    body = `<div class="grid skeleton-grid">${Array.from({ length: 6 }).map(() => '<div class="skel"></div>').join('')}</div>`;
  } else if (api.error) {
    body = `<div class="empty"><b>검색 백엔드에 연결하지 못했어요</b><p>${esc(api.error)}</p></div>`;
  } else if (!api.hits.length) {
    body = `<div class="empty">
        <b>'${esc(q)}' 검색 결과가 없어요</b>
        <p>${state.searchMode === 'keyword'
          ? '키워드 검색은 정확한 단어만 찾습니다. <b>벡터</b>나 <b>하이브리드</b>로 바꿔보세요.'
          : '다른 표현으로 검색해 보세요. 예: “우주 과학 소설”, “한강”, “SF”'}</p>
        ${state.searchMode === 'keyword' ? '<button class="link" data-mode="hybrid">하이브리드로 검색 →</button>' : ''}
      </div>`;
  } else {
    body = gridHTML(api.hits);
  }

  return `
  <div class="result-head">
    <h2>‘${esc(q)}’</h2>
    <span>${api.hits.length}권</span>
    <span class="spacer"></span>
    <button class="sec-more" data-act="clear-query">검색 지우기 ✕</button>
  </div>

  <div class="filter-bar">
    <span class="fb-label">검색 방식</span>
    ${modeBtn('hybrid', '하이브리드')}
    ${modeBtn('keyword', '키워드')}
    ${modeBtn('vector', '벡터')}
    <span class="spacer"></span>
    ${strat}
    ${cand}
    ${timing}
  </div>

  ${body}

  <div class="search-note">
    <b>${MODE_LABEL[state.searchMode]}</b> ·
    ${state.searchMode === 'keyword'
      ? '정확한 단어로 찾았어요. 의미가 비슷한 책은 ‘벡터’ 모드에서 더 잘 나와요.'
      : state.searchMode === 'vector'
        ? '뜻이 비슷한 책을 찾았어요. 단어가 정확히 겹치지 않아도 찾아드려요.'
        : '제목·저자 정확 일치를 우선하고, 의미가 비슷한 책도 함께 찾았어요.'}
  </div>`;
}

function renderLocalSearch() {
  const q = state.query.trim().toLowerCase();
  let list = BOOKS.filter((b) =>
    [b.title, b.author, b.publisher, ...b.tags, ...b.moods].join(' ').toLowerCase().includes(q)
  );
  if (state.filter === 'mine') list = list.filter((b) => myAccess(b).length > 0);
  if (state.filter === 'free') list = list.filter(anyFree);
  if (state.filter === 'end') list = list.filter((b) => endings(b).length > 0);
  list = sortByUsefulness(list);

  const fbtn = (id, label) =>
    `<button class="fchip ${state.filter === id ? 'is-on' : ''}" data-filter="${id}">${label}</button>`;

  const body = list.length
    ? gridHTML(list)
    : `<div class="empty">
        <b>'${esc(state.query)}' 검색 결과가 없어요</b>
        <p>제목·저자·태그로 다시 찾아보세요. 데모 데이터는 ${BOOKS.length}권이에요.</p>
        <button class="link" data-act="clear-query">전체 보기 →</button>
      </div>`;

  return `
  <div class="result-head">
    <h2>‘${esc(state.query)}’</h2>
    <span>${list.length}권</span>
    <span class="spacer"></span>
    <button class="sec-more" data-act="clear-query">검색 지우기 ✕</button>
  </div>
  <div class="filter-bar">
    <span class="fb-label">필터</span>
    ${fbtn('all', '전체')}
    ${fbtn('mine', '내 구독')}
    ${fbtn('free', '무료·도서관')}
    ${fbtn('end', '종료 임박')}
  </div>
  ${body}`;
}

/* ---------- 실검색(API) 비동기 ---------- */
let searchTimer = null;

function scheduleApiSearch() {
  if (!state.api.on) return;
  const q = state.query.trim();
  clearTimeout(searchTimer);
  if (!q) {
    state.api.hits = [];
    state.api.meta = null;
    state.api.loading = false;
    return;
  }
  state.api.loading = true;
  searchTimer = setTimeout(runApiSearch, 130);
}

async function runApiSearch() {
  const q = state.query.trim();
  if (!q) return;
  pushRecent(q);
  const seq = ++state.api.seq;
  try {
    const r = await API.search(q, state.searchMode, 24);
    if (seq !== state.api.seq) return;
    state.api.hits = (r.results || []).map(mapApiBook);
    cacheBooks(state.api.hits);
    state.api.meta = r;
    state.api.error = null;
  } catch (e) {
    if (seq !== state.api.seq) return;
    state.api.error = String(e.message || e);
    state.api.hits = [];
    state.api.meta = null;
  } finally {
    if (seq === state.api.seq) {
      state.api.loading = false;
      render();
    }
  }
}

async function hydrateShelf() {
  if (!state.api.on) return;
  const ids = [...state.shelf.want, ...state.shelf.reading, ...state.shelf.done];
  const missing = ids.filter((id) => !lookupBook(id));
  if (!missing.length) return;
  for (const id of missing.slice(0, 12)) {
    try {
      const r = await API.book(id);
      state.cache[id] = mapApiBook(r);
    } catch (e) { /* skip */ }
  }
  render();
}

function renderShelf() {
  const tab = state.shelfTab;
  const list = sortByUsefulness(state.shelf[tab].map(lookupBook).filter(Boolean));
  const mineEnd = endingEntries();

  const tabs = ['want', 'reading', 'done']
    .map((k) => `<button class="shelf-tab ${tab === k ? 'is-on' : ''}" data-shelftab="${k}">${SHELF_LABEL[k]}<span class="n">${state.shelf[k].length}</span></button>`)
    .join('');

  const body = list.length
    ? gridHTML(list)
    : `<div class="empty">
        <b>아직 ${SHELF_LABEL[tab]} 목록이 비어 있어요</b>
        <p>책 상세에서 담으면, 종료 예정까지 같이 관리해 드려요.</p>
        <button class="link" data-tab="explore">책 둘러보기 →</button>
      </div>`;

  return `
  <div class="page-head">
    <h2>내 서재</h2>
    <p>담아둔 책의 <b>가용성이 바뀌는 순간</b>을 추적해요. 구독에서 내려가기 전에 알려드려요.</p>
  </div>

  ${mineEnd.length ? `<section class="section" style="margin-top:34px">
    <div class="sec-head">
      <div>
        <h3 class="sec-title"><span class="ico">!</span>서재에서 곧 사라져요</h3>
        <p class="sec-desc">30일 안에 종료되는 책 ${mineEnd.length}권</p>
      </div>
    </div>
    ${alertPanelHTML(mineEnd, true)}
  </section>` : ''}

  <div class="shelf-tabs">${tabs}</div>
  ${body}`;
}

/* ---------- 취향 찾기 ---------- */
function currentTasteStep() {
  return state.taste.answers.length;
}

function renderTaste() {
  const answers = state.taste.answers;
  if (answers.length >= TASTE_FLOW.length) return renderTasteResult();

  const step = answers.length;
  const q = TASTE_FLOW[step];
  const pct = (step / TASTE_FLOW.length) * 100;

  return `<div class="taste-wrap">
    <div class="progress"><i style="width:${pct}%"></i></div>
    <div class="q-step">${step + 1} / ${TASTE_FLOW.length}</div>
    <h2 class="q-title">${esc(q.q)}</h2>
    <div class="q-opts">
      ${q.opts.map((o, i) => `<button class="q-opt" data-qopt="${i}">
        <span class="idx">${'ABCD'[i]}</span>${esc(o.label)}
      </button>`).join('')}
    </div>
    ${step > 0 ? `<button class="q-back" data-qback>← 이전 질문</button>` : `<button class="q-back" data-tab="explore">← 탐색으로</button>`}
  </div>`;
}

function recommend(answers) {
  const weights = {};
  let pagesMax = Infinity;
  let pagesMin = 0;
  let essay = 0;
  const bans = new Set();
  const picked = [];

  answers.forEach((optIdx, i) => {
    const opt = TASTE_FLOW[i].opts[optIdx];
    if (!opt) return;
    picked.push(opt.label);
    Object.entries(opt.w || {}).forEach(([k, v]) => {
      if (k === '_pagesMax') pagesMax = Math.min(pagesMax, v);
      else if (k === '_pagesMin') pagesMin = Math.max(pagesMin, v);
      else if (k === '_essay') essay += v;
      else weights[k] = (weights[k] || 0) + v;
    });
    Object.keys(opt.ban || {}).forEach((b) => bans.add(b));
  });

  const scored = BOOKS.map((b) => {
    let s = 0;
    const hit = [];
    Object.entries(weights).forEach(([k, v]) => {
      if (b.moods.includes(k)) { s += v * 2.2; hit.push(k); }
      if (b.tags.includes(k)) { s += v * 1.5; hit.push(k); }
    });
    if (essay && b.tags.includes('에세이')) { s += essay * 1.6; hit.push('에세이'); }
    if (pagesMax < Infinity) s += b.pages <= pagesMax ? 3.2 : -4.5;
    if (pagesMin) s += b.pages >= pagesMin ? 2.4 : -2.2;
    if (bans.has('무거운') && b.moods.includes('무거운')) s -= 6.5;
    if (bans.has('_thick') && b.pages > 400) s -= 4.2;
    if (bans.has('_foreign') && b.tags.some((t) => ['일본소설', '중국소설', '고전'].includes(t))) s -= 3.4;
    if (b.hot) s += 0.8;
    return { book: b, score: s, hit: Array.from(new Set(hit)) };
  });

  scored.sort((a, b) => b.score - a.score);
  return { top: scored.slice(0, 3), weights, hit: scored[0].hit, pagesMax, pagesMin, essay, bans: Array.from(bans) };
}

function whyText(rec, ctx) {
  const b = rec.book;
  const ranked = rec.hit.slice().sort((x, y) => (ctx.weights[y] || 0) - (ctx.weights[x] || 0));
  const moods = ranked.filter((k) => MOODS.includes(k)).slice(0, 2);

  const bits = [];
  if (moods.length) bits.push(`‘${moods.join(' · ')}’ 쪽`);
  if (ctx.essay && b.tags.includes('에세이')) bits.push('짧게 끊어 읽는 에세이');
  if (ctx.pagesMax < Infinity && b.pages <= ctx.pagesMax) bits.push(`${b.pages}p, 한 번에 읽기 좋은 분량`);
  else if (ctx.pagesMin && b.pages >= ctx.pagesMin) bits.push(`${b.pages}p, 주말에 몰입하는 분량`);
  else if (!bits.length) bits.push(`${b.pages}p라 부담 없는 분량`);

  const lead = `${bits.join(' · ')} — 그래서 골랐어요.`;

  const end = endings(b)[0];
  const acc = myAccess(b);
  let avail = '';
  if (end) avail = `지금은 <b>${esc(PLATFORMS[end.k].name)}</b>에서 읽을 수 있는데, <b>${end.d}일 뒤 종료</b>돼요. 지금 시작하면 딱이에요.`;
  else if (acc.length) avail = `<b>${esc(PLATFORMS[acc[0].k].name)}</b>에서 바로 읽을 수 있어요.`;
  else if (b.av.gongu) avail = '저작권이 만료돼 <b>무료</b>로 읽을 수 있어요.';
  else if (b.av.library) avail = `<b>도서관 전자책</b>으로 대출할 수 있어요${b.av.library.wait ? ` (대기 ${b.av.library.wait}명)` : ''}.`;
  else avail = '구독에는 없고 구매로만 볼 수 있어요.';

  return `${lead} ${avail}`;
}

const GENRE_KEYS = ['한국소설','일본소설','중국소설','SF','미스터리','스릴러','에세이','인문','철학','과학','역사','사회','심리','자기계발','경제','여행','로맨스','문학'];
function tasteQuery(answers) {
  const w = {};
  answers.forEach((idx, qi) => {
    const q = TASTE_FLOW[qi];
    if (!q) return;
    const opt = q.opts[idx];
    if (!opt || !opt.w) return;
    Object.entries(opt.w).forEach(([k, v]) => { w[k] = (w[k] || 0) + v; });
  });
  const genres = Object.entries(w)
    .filter(([k]) => GENRE_KEYS.includes(k))
    .sort((a, b) => b[1] - a[1])
    .map(([k]) => k);
  return genres.slice(0, 2).join(' ') || '문학';
}

function renderTasteResult() {
  const ctx = recommend(state.taste.answers);
  const sigs = [];
  Object.entries(ctx.weights)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .forEach(([k]) => {
      if (!sigs.includes(k)) sigs.push(k);
    });
  if (ctx.pagesMax < 300) sigs.push('짧은 호흡');
  if (ctx.essay) sigs.push('에세이');
  if (ctx.bans.includes('무거운')) sigs.push('무거운 것 제외');
  if (ctx.bans.includes('_thick')) sigs.push('두꺼운 책 제외');

  const recHTML = ctx.top.map((rec, i) => {
    const b = rec.book;
    return `<button class="rec" data-book="${b.id}">
      <div class="card-cover">${coverHTML(b)}</div>
      <div class="rec-body">
        <div class="rec-top"><b>${i + 1}. ${esc(b.title)}</b><span>${esc(b.author)}</span></div>
        <div class="rec-why">${whyText(rec, ctx)}</div>
        <div class="rec-meta">${esc(b.publisher)} · ${b.pages}p · <span class="avail" style="display:inline-flex">${pillsHTML(b, 2)}</span></div>
      </div>
    </button>`;
  }).join('');

  return `<div class="taste-wrap">
    <div class="progress"><i style="width:100%"></i></div>
    <div class="taste-result-head">
      <div>
        <h2>당신의 취향으로<br />고른 세 권</h2>
        <div class="taste-signature">${sigs.map((s) => `<span class="sig">${esc(s)}</span>`).join('')}</div>
      </div>
      <button class="sec-more" data-act="taste-reset">다시 하기 ↺</button>
    </div>
    <div class="rec-list">${recHTML}</div>
    <div class="dw-note" style="margin:22px 0 0">
      <b>왜 이 방식인가요?</b> 책은 영화보다 평가 데이터가 희박해서 별점 기반 추천이 잘 맞지 않아요.
      그래서 <b>취향 조건 → 후보 압축 → 가용성 확인</b> 순서로 추천하고, 근거를 함께 보여드려요.
    </div>
    <div style="margin-top:26px">
      <button class="q-opt" data-tab="explore" style="justify-content:center">탐색으로 돌아가기</button>
    </div>
  </div>`;
}

/* ---------------- drawer ---------------- */
function avRowHTML(book) {
  const rows = [];
  const mineEnd = endings(book);

  rows.push(`<div class="av-group-label">구독</div>`);
  avInfo(book).subs.forEach((s) => {
    const name = PLATFORMS[s.k].name;
    const mine = state.subs[s.k];
    const origin = (book.av_origin || {})[s.k];
    if (s.status === 'none' && origin === 'unknown') {
      rows.push(`<div class="av-row">
        <div class="p-main"><div class="p-name">${esc(name)}</div><div class="p-note">가용성 미확인 · 확인 중</div></div>
        <span class="state" style="color:var(--text-3);background:rgba(255,255,255,.05)">미확인</span>
      </div>`);
      return;
    }
    if (s.status === 'on') {
      rows.push(`<div class="av-row">
        <div class="p-main"><div class="p-name">${esc(name)}</div><div class="p-note">${mine ? '내 구독 · 바로 읽을 수 있어요' : '이 구독을 쓰면 바로 읽을 수 있어요'}</div></div>
        <span class="state on">제공 중</span>
        <button class="p-cta ${mine ? 'primary' : ''}" data-act="go" data-plat="${esc(name)}">${mine ? '읽으러 가기' : '보러 가기'}</button>
      </div>`);
    } else if (s.status === 'ending') {
      const key = `${book.id}:${s.k}`;
      const on = !!state.alerts[key];
      rows.push(`<div class="av-row is-ending">
        <div class="p-main"><div class="p-name">${esc(name)}</div><div class="p-note warn">${endDateText(s.d)} 종료 · ${daysWord(s.d)}</div></div>
        <span class="state end">종료 임박</span>
        <button class="p-cta ${on ? '' : 'primary'}" data-alert="${key}" data-d="${s.d}">${on ? '알림 켜짐 ✓' : '종료 알림'}</button>
      </div>`);
    } else if (mine) {
      rows.push(`<div class="av-row">
        <div class="p-main"><div class="p-name">${esc(name)}</div><div class="p-note">내 구독이지만 이 책은 제공하지 않아요</div></div>
        <span class="state" style="color:var(--text-3);background:rgba(255,255,255,.05)">미제공</span>
      </div>`);
    }
  });

  const buy = avInfo(book).buy;
  if (buy.length) {
    rows.push(`<div class="av-group-label">구매</div>`);
    buy
      .sort((a, b) => a.price - b.price)
      .forEach((x) => {
        rows.push(`<div class="av-row">
          <div class="p-main"><div class="p-name">${esc(PLATFORMS[x.k].name)}</div><div class="p-note">전자책 정가</div></div>
          <span class="p-price">${x.price.toLocaleString()}원</span>
          <button class="p-cta" data-act="go" data-plat="${esc(PLATFORMS[x.k].name)}">구매</button>
        </div>`);
      });
  }

  const free = avInfo(book).free;
  if (free.length) {
    rows.push(`<div class="av-group-label">무료</div>`);
    free.forEach((x) => {
      if (x.k === 'gongu') {
        rows.push(`<div class="av-row">
          <div class="p-main"><div class="p-name">공개 도서</div><div class="p-note">저작권 만료 · 로그인 없이 읽기</div></div>
          <span class="state free">무료</span>
          <button class="p-cta" data-act="go" data-plat="공개 도서">읽기</button>
        </div>`);
      } else {
        rows.push(`<div class="av-row">
          <div class="p-main"><div class="p-name">도서관 전자책</div><div class="p-note">${x.wait ? `대출 대기 ${x.wait}명` : '지금 바로 대출 가능'}</div></div>
          <span class="state free">${x.wait ? '대기' : '즉시'}</span>
          <button class="p-cta" data-act="go" data-plat="도서관 전자책">대출</button>
        </div>`);
      }
    });
  }

  if (mineEnd.length) {
    rows.push(`<div class="dw-hint" style="margin-top:14px;font-size:11.5px;color:var(--text-3);line-height:1.6">
      ⓘ 종료일은 플랫폼 공지 기준이며, 실제로는 예고 없이 내려갈 수 있어요. 서가록이 매일 확인해 바뀌는 순간 알려드려요.
    </div>`);
  }

  return rows.join('');
}

function drawerHTML(book) {
  const cur = inShelf(book.id);
  const tags = [...(book.tags || []), ...(book.moods || [])].filter(Boolean).slice(0, 6);
  const metaParts = [book.publisher, book.year, book.pages ? `${book.pages}p` : null].filter(Boolean);
  const noticeCount = (book.notices || []).length;
  const hasNotice = Object.values(book.av_origin || {}).some((v) => v === 'notice');

  const unknownSubs = SUB_KEYS.filter((k) => (book.av_origin || {})[k] === 'unknown');
  const availNote = [
    '내가 쓰는 구독은 <b style="color:var(--teal)">초록</b>, 곧 사라지는 책은 <b style="color:var(--red)">빨강</b>으로 표시돼요.',
    book.real
      ? hasNotice
        ? ` · 실제 수집된 종료 공지 <b style="color:var(--gold)">${noticeCount}건</b> 반영`
        : unknownSubs.length
          ? ' · 구독 가용성은 <b style="color:var(--gold)">확인 중</b>이에요 (확인된 공지만 표시)'
          : ' · 확인된 구독 정보가 없어요'
      : '',
  ].join('');

  return `<div class="drawer-top">
      <button class="drawer-close" data-act="close-drawer" aria-label="닫기">
        <svg viewBox="0 0 24 24" width="18" height="18"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
      </button>
    </div>
    <div class="dw-hero">
      <div class="dw-cover">${coverHTML(book)}</div>
      <div class="dw-meta">
        <h2>${esc(book.title)}</h2>
        <p class="dw-author">${esc(book.author)}</p>
        <p class="dw-sub">${esc(metaParts.join(' · '))}</p>
        ${book.real && (book.price || book.rating) ? `<p class="dw-price">${book.price ? `${Number(book.price).toLocaleString()}원` : ''}${book.price && book.rating ? ' · ' : ''}${book.rating ? `★ ${book.rating}` : ''}${book.link ? ` · <a href="${esc(book.link)}" target="_blank" rel="noopener">원본 보기</a>` : ''}</p>` : ''}
        <div class="dw-tags">${tags.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div>
      </div>
    </div>
    ${book.blurb ? `<p class="dw-blurb">${esc(book.blurb)}</p>` : ''}

    <div class="dw-block">
      <h3>어디서 읽을 수 있나 <span class="hint">${avInfo(book).subs.filter((s) => s.status !== 'none').length}개 구독 · 구매 ${avInfo(book).buy.length}곳</span></h3>
      <p class="sub">${availNote}</p>
      <div class="av-table">${avRowHTML(book)}</div>
    </div>

    ${(book.similar || []).length ? `<div class="dw-block">
      <h3>이 책과 비슷한 책 <span class="n">${book.similar.length}권</span></h3>
      <p class="sub">같은 임베딩 공간에서 가까운 순서예요.</p>
      <div class="similar-row">${book.similar.map((x) => `<button class="sim-card" data-book="${esc(x.id)}">
        <span class="sim-cover">${x.cover_url ? `<img src="${esc(x.cover_url)}" alt="" loading="lazy">` : ''}</span>
        <b>${esc(x.title)}</b>
        <span>${esc(x.author || '')}</span>
      </button>`).join('')}</div>
    </div>` : ''}

    <div class="dw-actions">
      <button class="act-btn ${cur === 'want' ? 'is-on' : ''}" data-shelf-set="want">관심 ${cur === 'want' ? '✓' : ''}</button>
      <button class="act-btn ${cur === 'reading' ? 'is-on' : ''}" data-shelf-set="reading">읽는 중 ${cur === 'reading' ? '✓' : ''}</button>
      <button class="act-btn ${cur === 'done' ? 'is-on' : ''}" data-shelf-set="done">완독 ${cur === 'done' ? '✓' : ''}</button>
    </div>

    <div class="dw-note">
      <b>서가록이 이 책을 추적하는 방식</b><br />
      4개 구독사 제공 여부 · 종료 예정 공지 · 도서관 대출 가능 여부를 매일 확인해 바뀌는 순간 알려드려요.
    </div>`;
}

let lastFocused = null;
async function openBook(id) {
  // API 모드에서는 similar(비슷한 책)까지 포함한 상세를 받아서 연다
  if (state.api.on) {
    try {
      const r = await API.book(id);
      const nb = mapApiBook(r);
      cacheBooks([nb]);
      return showDrawer(nb);
    } catch (e) {
      // 상세 실패 시 캐시로 폴백
    }
  }
  let b = lookupBook(id);
  if (!b && state.api.on) {
    try {
      const r = await API.book(id);
      b = mapApiBook(r);
      cacheBooks([b]);
    } catch (e) {
      toast('책 정보를 불러오지 못했어요');
      return;
    }
  }
  if (!b) return;
  return showDrawer(b);
}

function showDrawer(b) {
  state.openId = b.id;
  const root = $('#drawerRoot');
  $('.drawer', root).innerHTML = drawerHTML(b);
  $('.drawer', root).scrollTop = 0;
  root.hidden = false;
  lastFocused = document.activeElement;
  document.body.style.overflow = 'hidden';
  const closeBtn = $('.drawer-close', root);
  if (closeBtn) closeBtn.focus();
}
function refreshDrawer() {
  if (!state.openId) return;
  const b = lookupBook(state.openId);
  if (!b) return;
  const drawer = $('.drawer');
  const sc = drawer.scrollTop;
  drawer.innerHTML = drawerHTML(b);
  drawer.scrollTop = sc;
}
function closeDrawer() {
  state.openId = null;
  $('#drawerRoot').hidden = true;
  document.body.style.overflow = '';
  if (lastFocused && lastFocused.focus) lastFocused.focus();
}

/* ---------------- subs popover ---------------- */
const SUB_DESC = {
  millie: '24만 권 무제한 · 월 9,900원',
  ridiselect: '리디가 고른 도서 · 월 4,900원',
  sam: '교보 · 열람권 또는 무제한',
  willa: '오디오북 중심 · 월 12,500원',
};
function renderSubsOptions() {
  $('#subsOptions').innerHTML = SUB_KEYS.map(
    (k) => `<button class="sub-opt" data-subs-toggle="${k}" aria-pressed="${!!state.subs[k]}">
      <span class="sw"></span>
      <span class="txt"><b>${esc(PLATFORMS[k].name)}</b><span>${SUB_DESC[k]}</span></span>
    </button>`
  ).join('');
}
function toggleSubsPopover(force) {
  const pop = $('#subsPopover');
  const btn = $('#subsBtn');
  const next = force !== undefined ? force : pop.hidden;
  pop.hidden = !next;
  btn.setAttribute('aria-expanded', String(next));
}

/* ---------------- render root ---------------- */
function render() {
  const hero = $('#hero');
  const isExplore = state.tab === 'explore';
  const searching = isExplore && state.query.trim().length > 0;

  hero.classList.toggle('is-hidden', !isExplore);
  hero.classList.toggle('is-compact', searching);

  $$('#nav .tab').forEach((t) => t.classList.toggle('is-on', t.dataset.tab === state.tab));
  const count = shelfCount();
  const sc = $('#shelfCount');
  sc.textContent = String(count);
  sc.hidden = count === 0;
  $('#subsCount').textContent = String(subsOn().length);
  renderSubsOptions();

  const navInput = $('#searchInput');
  if (document.activeElement !== navInput && navInput.value !== state.query) navInput.value = state.query;
  const heroInput = $('#heroSearch');
  if (heroInput && document.activeElement !== heroInput && heroInput.value !== state.query) heroInput.value = state.query;

  const view = $('#view');
  if (isExplore) view.innerHTML = searching ? renderSearch() : renderExplore();
  else if (state.tab === 'shelf') view.innerHTML = renderShelf();
  else view.innerHTML = renderTaste();

  // 백엔드 연결 배지 (기술 정보는 최소화 — 제품 문구 우선)
  const badge = $('#liveIndex');
  if (badge) {
    if (state.api.on) {
      const h = state.api.health || {};
      badge.hidden = false;
      badge.innerHTML = `실시간 색인 연결됨 · 매일 갱신`;
    } else {
      badge.hidden = true;
    }
  }

  // 히어로 색인 카드 (실데이터 요약)
  const card = $('#heroCard');
  if (card) {
    const h = state.api.health || {};
    const books = Number(h.books || 0) || BOOKS.length;
    const notices = Number(state.noticeReal || 0) || (state.notices || []).length;
    const raw = String(h.synced_at || '');
    const m = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
    const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    setTxt('hcBooks', books.toLocaleString());
    setTxt('hcNotices', notices.toLocaleString());
    setTxt('hcDate', m ? `${m[1]}.${m[2]}.${m[3]}` : '데모');
  }
}

/* ---------------- events ---------------- */
function goTab(tab) {
  state.tab = tab;
  if (tab !== 'explore') state.query = '';
  render();
  if (tab === 'shelf') hydrateShelf();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function setQuery(q) {
  state.query = q;
  state.filter = 'all';
  state.tab = 'explore';
  if (state.api.on) scheduleApiSearch();
  render();
  if (document.activeElement) document.activeElement.blur();
  window.scrollTo({ top: Math.min(window.scrollY, 120), behavior: 'smooth' });
}

document.addEventListener('click', (e) => {
  const t = e.target;

  const act = t.closest('[data-act]');
  if (act) {
    const a = act.dataset.act;
    if (a === 'home') { e.preventDefault(); goTab('explore'); return; }
    if (a === 'search') { const el = $('#heroSearch'); setQuery(el.value.trim()); return; }
    if (a === 'clear-query') { setQuery(''); const h = $('#heroSearch'); if (h) h.value = ''; return; }
    if (a === 'clear-collection') { state.collection = null; render(); return; }
    if (a === 'close-drawer') { closeDrawer(); return; }
    if (a === 'open-subs') { toggleSubsPopover(true); return; }
    if (a === 'find-all') { setQuery(''); state.filter = 'all'; render(); window.scrollTo({ top: 0 }); return; }
    if (a === 'go') { toast(`${act.dataset.plat}로 이동합니다 (데모)`); return; }
    if (a === 'taste-reset') { state.taste.answers = []; render(); return; }
  }

  const quick = t.closest('[data-quick]');
  if (quick) { const h = $('#heroSearch'); if (h) h.value = quick.dataset.quick; setQuery(quick.dataset.quick); return; }

  const tl = t.closest('[data-tl]');
  if (tl) {
    const k = tl.dataset.tl;
    state.tlDate = state.tlDate === k ? null : k;
    render();
    const el = document.getElementById('timeline');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }
  const tlClear = t.closest('[data-tl-clear]');
  if (tlClear) { state.tlDate = null; render(); return; }

  const genreEl = t.closest('[data-genre]');
  if (genreEl) {
    const q = genreEl.dataset.genre;
    const h = $('#heroSearch'); if (h) h.value = q;
    setQuery(q);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    return;
  }

  const recentEl = t.closest('[data-recent]');
  if (recentEl) {
    const q = recentEl.dataset.recent;
    const h = $('#heroSearch'); if (h) h.value = q;
    setQuery(q);
    return;
  }

  const recentClear = t.closest('[data-recent-clear]');
  if (recentClear) {
    try { localStorage.removeItem(RECENT_KEY); } catch (e) { }
    renderRecent();
    return;
  }

  const tabEl = t.closest('[data-tab]');
  if (tabEl) { goTab(tabEl.dataset.tab); return; }

  const subToggle = t.closest('[data-subs-toggle]');
  if (subToggle) {
    const k = subToggle.dataset.subsToggle;
    state.subs[k] = !state.subs[k];
    save();
    render();
    return;
  }

  const alertBtn = t.closest('[data-alert]');
  if (alertBtn) {
    e.stopPropagation();
    toggleAlert(alertBtn.dataset.alert, alertBtn.dataset.d);
    return;
  }

  const bookEl = t.closest('[data-book]');
  if (bookEl) { openBook(bookEl.dataset.book); return; }

  const col = t.closest('[data-col]');
  if (col) {
    if (state.api.on) {
      state.tab = 'explore';
      state.query = COLLECTION_QUERY[col.dataset.col] || col.dataset.col;
      state.api.loading = true;
      render();
      runApiSearch();
      return;
    }
    state.collection = col.dataset.col;
    render();
    const el = document.getElementById('collectionResult');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }

  const shelfSet = t.closest('[data-shelf-set]');
  if (shelfSet && state.openId) { toggleShelf(state.openId, shelfSet.dataset.shelfSet); return; }

  const shelfTab = t.closest('[data-shelftab]');
  if (shelfTab) { state.shelfTab = shelfTab.dataset.shelftab; render(); return; }

  const filter = t.closest('[data-filter]');
  if (filter) { state.filter = filter.dataset.filter; render(); return; }

  const modeEl = t.closest('[data-mode]');
  if (modeEl) {
    state.searchMode = modeEl.dataset.mode;
    if (state.api.on && state.query.trim()) {
      state.api.loading = true;
      render();
      runApiSearch();
    } else {
      render();
    }
    return;
  }

  const qopt = t.closest('[data-qopt]');
  if (qopt) {
    state.taste.answers.push(Number(qopt.dataset.qopt));
    // API 모드: 데모 추천 대신, 고른 취향으로 실제 서가를 검색한다
    if (state.api.on && state.taste.answers.length >= TASTE_FLOW.length) {
      state.tab = 'explore';
      state.query = tasteQuery(state.taste.answers);
      state.api.loading = true;
      render();
      runApiSearch();
      return;
    }
    render();
    return;
  }
  const qback = t.closest('[data-qback]');
  if (qback) { state.taste.answers.pop(); render(); return; }

  // 바깥 클릭 시 팝오버 닫기
  if (!t.closest('#subsPopover') && !t.closest('#subsBtn')) toggleSubsPopover(false);
});

document.addEventListener('input', (e) => {
  if (e.target.id === 'searchInput' || e.target.id === 'heroSearch') {
    state.query = e.target.value;
    state.filter = 'all';
    state.tab = 'explore';
    if (state.api.on) scheduleApiSearch();
    render();
  }
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (state.openId) closeDrawer();
    else if (!$('#subsPopover').hidden) toggleSubsPopover(false);
    return;
  }
  if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
    e.preventDefault();
    const h = $('#heroSearch');
    if (h && state.tab === 'explore') h.focus();
    else { const n = $('#searchInput'); if (n) n.focus(); }
  }
  if (e.key === 'Enter' && e.target.id === 'heroSearch') {
    setQuery(e.target.value.trim());
  }
});

/* ---------------- init ---------------- */
load();
$('#quickChips').innerHTML = heroChips();
$('#subsBtn').addEventListener('click', () => toggleSubsPopover());
render();
if (!localStorage.getItem(LS_KEY)) save();

/** 백엔드가 살아있으면 실검색 모드로 전환 (없으면 로컬 데모 유지) */
async function initApi() {
  try {
    const h = await API.health();
    if (h && h.ok) {
      state.api.on = true;
      state.api.health = h;
      document.body.classList.add('has-api');
      // 데이터 기준일 표기 (법적 고지)
      const stamp = document.querySelector('#dataStamp');
      if (stamp) {
        const m = String(h.synced_at || '').match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
        stamp.textContent = m ? `데이터 기준일 ${m[1]} ${m[2]}` : '데이터 기준일 확인 불가';
      }
      try {
        const n = await API.call('/api/notices', { limit: 500 });
        state.notices = (n && n.notices) || [];
        state.noticeReal = (n && n.real) || 0;
      } catch (e) { state.notices = []; }
      render();
      loadDiscover();
      renderRecent();
      if (state.query.trim()) {
        scheduleApiSearch();
        render();
      }
    }
  } catch (e) {
    state.api.on = false;
  }
  state.api.checked = true;
}
// PWA: 홈 화면 추가 지원 (HTTPS/localhost 에서만)
if ('serviceWorker' in navigator && location.protocol !== 'file:') {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => { });
  });
}

setupSuggest('#heroSearch', '#heroSuggest');
setupSuggest('#searchInput', '#navSuggest');
renderRecent();
initApi();
