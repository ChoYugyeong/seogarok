"""공통 기반: 표준 스키마, HTTP 헬퍼(레이트리밋/캐시/robots), Collector 인터페이스.

이 모듈의 HTTP 헬퍼는 아래 원칙을 코드로 강제한다.
  * 설명형 User-Agent: ``seoga-research-bot/0.1 (+contact: demo)``
  * 요청 간격 최소 1초 (robots.txt 의 Crawl-delay 가 더 크면 그 값을 따름)
  * 모든 원본 응답을 ``ingest/notices/_cache/`` 에 원문 그대로 저장
  * robots.txt 를 먼저 확인하고 Disallow 경로는 요청하지 않음
  * 공개 GET 만 사용. 쿠키/로그인/결제 우회 없음.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import re
import time
import urllib.parse
import urllib.robotparser
from pathlib import Path
from typing import Any, Iterable

import requests

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

USER_AGENT = "seoga-research-bot/0.1 (+contact: demo)"

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]  # C:/Dev/seoga
CACHE_DIR = PACKAGE_DIR / "_cache"

MIN_INTERVAL_SEC = 1.0
HTTP_TIMEOUT = 20
MAX_RETRIES = 2

PLATFORMS = ("millie", "ridiselect", "sam", "willa", "crema")
SOURCE_KINDS = ("notice_page", "per_title_page", "search_api", "fixture")
STATUSES = ("ending", "ended", "unknown")
CONFIDENCES = ("high", "medium", "low")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISBN13_RE = re.compile(r"^\d{13}$")


# ---------------------------------------------------------------------------
# 표준 스키마
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Notice:
    """종료 예정 공지 1건 (JSONL 1줄에 대응)."""

    platform: str
    title: str
    author: str | None = None
    isbn13: str | None = None
    ends_at: str | None = None
    status: str = "ending"
    source_url: str = ""
    source_kind: str = "fixture"
    collected_at: str = ""
    confidence: str = "low"
    raw_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    # -- 검증 --------------------------------------------------------------
    def problems(self) -> list[str]:
        errs: list[str] = []
        if self.platform not in PLATFORMS:
            errs.append(f"platform invalid: {self.platform!r}")
        if not (self.title or "").strip():
            errs.append("title empty")
        if self.author is not None and not isinstance(self.author, str):
            errs.append("author must be str|null")
        if self.isbn13 is not None and not ISBN13_RE.match(self.isbn13):
            errs.append(f"isbn13 invalid: {self.isbn13!r}")
        if self.ends_at is not None:
            if not DATE_RE.match(self.ends_at):
                errs.append(f"ends_at not YYYY-MM-DD: {self.ends_at!r}")
            else:
                try:
                    dt.date.fromisoformat(self.ends_at)
                except ValueError:
                    errs.append(f"ends_at not a real date: {self.ends_at!r}")
        if self.status not in STATUSES:
            errs.append(f"status invalid: {self.status!r}")
        if self.source_kind not in SOURCE_KINDS:
            errs.append(f"source_kind invalid: {self.source_kind!r}")
        if self.confidence not in CONFIDENCES:
            errs.append(f"confidence invalid: {self.confidence!r}")
        if not self.source_url:
            errs.append("source_url empty")
        if not _is_iso_datetime(self.collected_at):
            errs.append(f"collected_at not ISO8601 tz-aware: {self.collected_at!r}")
        if len(self.raw_note) > 120:
            errs.append(f"raw_note too long ({len(self.raw_note)} chars)")
        return errs

    def is_valid(self) -> bool:
        return not self.problems()


def _is_iso_datetime(value: str) -> bool:
    try:
        parsed = dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return False
    return parsed.tzinfo is not None


def now_iso() -> str:
    """+09:00 로컬 시각의 ISO8601 문자열."""
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).replace(microsecond=0).isoformat()


def make_notice(
    platform: str,
    title: str,
    *,
    author: str | None = None,
    isbn13: str | None = None,
    ends_at: str | None = None,
    status: str = "ending",
    source_url: str = "",
    source_kind: str = "fixture",
    confidence: str = "low",
    raw_note: str = "",
    collected_at: str | None = None,
) -> Notice:
    return Notice(
        platform=platform,
        title=(title or "").strip(),
        author=(author.strip() if isinstance(author, str) and author.strip() else author),
        isbn13=isbn13 or None,
        ends_at=ends_at or None,
        status=status,
        source_url=source_url,
        source_kind=source_kind,
        collected_at=collected_at or now_iso(),
        confidence=confidence,
        raw_note=raw_note[:120],
    )


def validate_notices(notices: Iterable[Notice]) -> list[str]:
    """전체 검증. 문제 문자열 목록을 반환(빈 리스트 = 통과)."""
    errors: list[str] = []
    for i, notice in enumerate(notices):
        errs = notice.problems()
        if errs:
            errors.append(f"line {i + 1}: {errs}")
    return errors


# ---------------------------------------------------------------------------
# HTTP 헬퍼: robots.txt + 레이트리밋 + 원본 캐시
# ---------------------------------------------------------------------------


class RobotsDenied(RuntimeError):
    """robots.txt 가 해당 URL 수집을 금지한 경우."""


@dataclasses.dataclass
class FetchResult:
    url: str
    status: int
    content_type: str
    text: str
    from_cache: bool
    cache_path: str | None
    fetched_at: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> Any:
        return json.loads(self.text)


class HttpClient:
    """레이트리밋·캐시·robots 를 강제하는 공용 HTTP 클라이언트."""

    def __init__(
        self,
        *,
        cache_dir: Path = CACHE_DIR,
        user_agent: str = USER_AGENT,
        min_interval: float = MIN_INTERVAL_SEC,
        refresh: bool = False,
        timeout: int = HTTP_TIMEOUT,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent
        self.min_interval = max(float(min_interval), MIN_INTERVAL_SEC)
        self.refresh = refresh
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
            }
        )
        self._last_request_at = 0.0
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.requests_made = 0
        self.cache_hits = 0
        self.robots_notes: dict[str, dict[str, Any]] = {}

    # -- robots ------------------------------------------------------------
    def robots_for(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        parsed = urllib.parse.urlsplit(url)
        host_key = f"{parsed.scheme}://{parsed.netloc}"
        if host_key in self._robots:
            return self._robots[host_key]

        robots_url = f"{host_key}/robots.txt"
        parser: urllib.robotparser.RobotFileParser | None = None
        try:
            content = self._request(robots_url, save_key=f"robots/{parsed.netloc}.txt")
            if content.status == 200:
                parser = urllib.robotparser.RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(content.text.splitlines())
                delay = parser.crawl_delay("*")
                if delay:
                    self.robots_notes[host_key] = {"robots_url": robots_url, "status": 200, "crawl_delay": delay}
                else:
                    self.robots_notes[host_key] = {"robots_url": robots_url, "status": 200}
            else:
                self.robots_notes[host_key] = {
                    "robots_url": robots_url,
                    "status": content.status,
                    "note": "robots.txt 없음/접근불가 -> 표준 관례상 전체 허용으로 간주",
                }
        except requests.RequestException as exc:
            self.robots_notes[host_key] = {
                "robots_url": robots_url,
                "status": "error",
                "note": f"robots.txt 조회 실패: {exc.__class__.__name__}",
            }
        self._robots[host_key] = parser
        return parser

    def allowed(self, url: str) -> tuple[bool, str]:
        parser = self.robots_for(url)
        if parser is None:
            return True, "robots.txt 부재/오류: 허용으로 간주"
        allowed = parser.can_fetch(self.user_agent, url)
        # 일반 봇 이름("*") 기준도 함께 확인해 보수적으로 판단한다.
        if not allowed:
            return False, "Disallow (robots.txt)"
        return True, "Allow (robots.txt)"

    # -- 요청 --------------------------------------------------------------
    def fetch(self, url: str, *, check_robots: bool = True, save_key: str | None = None) -> FetchResult:
        if check_robots:
            ok, reason = self.allowed(url)
            if not ok:
                raise RobotsDenied(f"{url}: {reason}")
        return self._request(url, save_key=save_key)

    def _request(self, url: str, *, save_key: str | None = None) -> FetchResult:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        cached = None if self.refresh else self._load_cache(url, digest)
        if cached is not None:
            self.cache_hits += 1
            return cached

        self._throttle()
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                break
            except requests.RequestException as exc:  # pragma: no cover - 네트워크 의존
                last_exc = exc
                if attempt >= MAX_RETRIES:
                    raise
                time.sleep(self.min_interval * (attempt + 1))
        else:  # pragma: no cover
            raise last_exc  # type: ignore[misc]

        self.requests_made += 1
        content_type = resp.headers.get("Content-Type", "")
        encoding = resp.encoding
        if not encoding and "charset=" in content_type:
            encoding = content_type.split("charset=", 1)[1].split(";")[0].strip()
        try:
            text = resp.content.decode(encoding or "utf-8", errors="replace")
        except LookupError:
            text = resp.content.decode("utf-8", errors="replace")

        raw_path = self._save_raw(url, digest, resp.content, resp.headers, resp.status_code, save_key)
        return FetchResult(
            url=resp.url,
            status=resp.status_code,
            content_type=content_type,
            text=text,
            from_cache=False,
            cache_path=str(raw_path) if raw_path else None,
            fetched_at=now_iso(),
        )

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait = self.min_interval + 0.15 - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    # -- 캐시 --------------------------------------------------------------
    def _cache_prefix(self, digest: str) -> Path:
        return self.cache_dir / digest

    def _save_raw(
        self,
        url: str,
        digest: str,
        body: bytes,
        headers: Any,
        status: int,
        save_key: str | None,
    ) -> Path | None:
        ext = _extension_for(headers.get("Content-Type", ""))
        base = self._cache_prefix(digest)
        if save_key:
            base = self.cache_dir / save_key
            base.parent.mkdir(parents=True, exist_ok=True)
            base = base.with_suffix(ext)
        else:
            base = base.with_suffix(ext)
        try:
            base.write_bytes(body)
            meta = {
                "url": url,
                "status": status,
                "status_headers": {k: headers.get(k) for k in ("Content-Type", "Last-Modified", "ETag")},
                "fetched_at": now_iso(),
                "bytes": len(body),
                "sha1": hashlib.sha1(body).hexdigest(),
                "cache_file": base.name,
            }
            base.with_suffix(base.suffix + ".meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:  # pragma: no cover - 디스크 오류
            return None
        return base

    def _load_cache(self, url: str, digest: str) -> FetchResult | None:
        # save_key 로 저장된 robots 파일은 별도 경로라 URL 해시 파일만 탐색한다.
        for ext in (".html", ".json", ".txt", ".xml", ".js"):
            path = self.cache_dir / f"{digest}{ext}"
            meta_path = self.cache_dir / f"{digest}{ext}.meta.json"
            if path.exists() and meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    body = path.read_bytes()
                    text = body.decode("utf-8", errors="replace")
                    return FetchResult(
                        url=url,
                        status=int(meta.get("status", 200) or 200),
                        content_type=str(meta.get("status_headers", {}).get("Content-Type") or ""),
                        text=text,
                        from_cache=True,
                        cache_path=str(path),
                        fetched_at=str(meta.get("fetched_at") or ""),
                    )
                except (OSError, ValueError):
                    continue
        return None


def _extension_for(content_type: str) -> str:
    ct = (content_type or "").lower()
    if "json" in ct:
        return ".json"
    if "html" in ct:
        return ".html"
    if "xml" in ct or "rss" in ct:
        return ".xml"
    if "javascript" in ct or "ecmascript" in ct:
        return ".js"
    return ".txt"


# ---------------------------------------------------------------------------
# Collector 인터페이스
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class CollectorReport:
    """수집기 1개의 실행 결과 메타데이터(보고용)."""

    platform: str
    reachable: bool
    public_notice_page: bool
    collected: int  # 실제 수집 건수(source_kind != fixture)
    source_kinds: list[str]
    status: str  # collected | empty | blocked | error
    note: str = ""
    fixture_count: int = 0
    endpoints: list[dict[str, Any]] = dataclasses.field(default_factory=list)


class CollectorError(RuntimeError):
    """수집기 실행 실패(네트워크/응답 스키마)."""


class Collector:
    """플랫폼별 수집기 공통 인터페이스."""

    platform: str = ""
    source_kind: str = "fixture"
    #: 공개 엔드포인트 목록(README/보고서 생성에 사용)
    endpoints: tuple[str, ...] = ()
    #: robots/보안정책으로 자동 수집이 불가능한 플랫폼이면 True
    blocked: bool = False

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()
        self.last_note: str = ""

    def collect(self) -> list[Notice]:
        raise NotImplementedError

    def report(self, notices: list[Notice], note: str | None = None) -> CollectorReport:
        real = [n for n in notices if n.source_kind != "fixture"]
        fixtures = [n for n in notices if n.source_kind == "fixture"]
        if real:
            status = "collected"
        elif self.blocked:
            status = "blocked"
        else:
            status = "empty"
        return CollectorReport(
            platform=self.platform,
            reachable=self.blocked is False,
            public_notice_page=any(n.source_kind == "notice_page" for n in notices),
            collected=len(real),
            source_kinds=sorted({n.source_kind for n in notices}),
            status=status,
            note=(note if note is not None else self.last_note),
            fixture_count=len(fixtures),
            endpoints=[{"url": url} for url in self.endpoints],
        )


# ---------------------------------------------------------------------------
# Fixture(데모) 헬퍼
# ---------------------------------------------------------------------------

FIXTURE_NOTE = "FIXTURE(데모): 실제 플랫폼 공지 아님 / data.js 데모 카탈로그 참고값"


def load_demo_catalog():
    """읽기 전용 `data.js`(38권 데모 카탈로그)를 파싱. 없으면 빈 목록."""
    from .match import load_data_js_catalog

    path = PROJECT_ROOT / "data.js"
    if not path.exists():
        return []
    try:
        return load_data_js_catalog(path)
    except Exception:  # noqa: BLE001 - 데모 카탈로그는 부가 기능
        return []


def fixture_notices(platform: str, catalog, *, limit: int = 3) -> list[Notice]:
    """실수집 불가 플랫폼용 fixture 행 생성.

    data.js 데모 카탈로그에서 해당 플랫폼 항목이 있는 책만 사용하며,
    종료일(ends_at)은 절대 지어내지 않고 null 로 둔다.
    데모에서 종료 예정(s:'ending')으로 표기된 책을 먼저 사용한다.
    """
    rows: list[Notice] = []
    candidates = sorted(
        (book for book in catalog if (book.av or {}).get(platform)),
        key=lambda book: 0 if (book.av or {}).get(platform, {}).get("s") == "ending" else 1,
    )
    for book in candidates:
        av = (book.av or {}).get(platform) or {}
        if av.get("s") == "ending":
            detail = f"데모 표기: 종료까지 {av.get('d')}일"
            status = "ending"  # 데모 표기 기준이며 ends_at 은 null(날조 금지)
        elif av.get("s") == "on":
            detail = "데모 표기: 구독중"
            status = "unknown"
        else:
            continue
        rows.append(
            make_notice(
                platform,
                book.title,
                author=book.author or None,
                ends_at=None,  # 데모 값으로 날짜를 날조하지 않는다.
                status=status,
                source_url=f"fixture:data.js#{book.id}",
                source_kind="fixture",
                confidence="low",
                raw_note=f"{FIXTURE_NOTE} | {detail}",
            )
        )
        if len(rows) >= limit:
            break
    return rows


# ---------------------------------------------------------------------------
# JSONL 입출력
# ---------------------------------------------------------------------------


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, notices: Iterable[Notice]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    lines: list[str] = []
    for notice in notices:
        lines.append(json.dumps(notice.to_dict(), ensure_ascii=False, sort_keys=False))
        count += 1
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return count
