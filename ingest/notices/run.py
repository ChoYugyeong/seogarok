"""CLI: 종료 예정 공지 수집 → 정규화 → JSONL + 보고서.

사용 예:
  cd C:\\Dev\\seoga
  python -m ingest.notices.run --out data/notices.jsonl --report
  python -m ingest.notices.run --self-test
  python -m ingest.notices.run --out data/notices.jsonl --report --no-fixtures --refresh
  python -m ingest.notices.run --report --verify-blocked   # 차단 플랫폼 현재 상태 재확인(선택)

정책:
  * 공개·비로그인 GET 만 사용, 요청 간격 ≥1초, 설명형 UA, 원본 캐시(_cache/)
  * robots.txt Disallow 는 요청하지 않음(HttpClient 가 강제)
  * 실수집 불가 플랫폼은 source_kind="fixture" 로 명시(절대 실데이터로 위장하지 않음)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .base import (
    CONFIDENCES,
    CACHE_DIR,
    MIN_INTERVAL_SEC,
    PLATFORMS,
    PROJECT_ROOT,
    SOURCE_KINDS,
    STATUSES,
    USER_AGENT,
    CollectorReport,
    HttpClient,
    Notice,
    load_jsonl,
    make_notice,
    now_iso,
    validate_notices,
    write_jsonl,
)
from .crema import CremaCollector
from .match import (
    load_data_js_catalog,
    match_many,
    match_stats,
    normalize_author,
    normalize_isbn,
    normalize_title,
    title_similarity,
)
from .millie import MillieCollector
from .ridi import RidiSelectCollector
from .sam import SamCollector
from .willa import WillaCollector

COLLECTOR_CLASSES = (
    MillieCollector,
    RidiSelectCollector,
    SamCollector,
    WillaCollector,
    CremaCollector,
)

EXIT_OK = 0
EXIT_FAIL = 1


# ---------------------------------------------------------------------------
# 수집
# ---------------------------------------------------------------------------


def run_collectors(
    *,
    client: HttpClient,
    platforms: list[str],
    with_fixtures: bool,
    verify_blocked: bool = False,
) -> tuple[list[Notice], list[CollectorReport], list[dict[str, Any]]]:
    notices: list[Notice] = []
    reports: list[CollectorReport] = []
    probes: list[dict[str, Any]] = []

    for cls in COLLECTOR_CLASSES:
        if platforms and cls.platform not in platforms:
            continue
        collector = cls(client)
        try:
            collected = collector.collect()
        except Exception as exc:  # noqa: BLE001 - 한 플랫폼 실패가 전체를 막지 않는다
            reports.append(
                CollectorReport(
                    platform=cls.platform,
                    reachable=False,
                    public_notice_page=False,
                    collected=0,
                    source_kinds=[],
                    status="error",
                    note=f"{exc.__class__.__name__}: {exc}",
                    endpoints=[{"url": url} for url in cls.endpoints],
                )
            )
            continue

        if not with_fixtures:
            collected = [n for n in collected if n.source_kind != "fixture"]
        reports.append(collector.report(collected))

        if verify_blocked and hasattr(collector, "probe_blocked"):
            try:
                probes.append({"platform": cls.platform, **collector.probe_blocked()})
            except Exception as exc:  # noqa: BLE001
                probes.append(
                    {"platform": cls.platform, "error": f"{exc.__class__.__name__}: {exc}"}
                )
        notices.extend(collected)
    return notices, reports, probes


def dedupe(notices: Iterable[Notice]) -> list[Notice]:
    """동일 공지 중복만 제거한다.

    제목 정규화 키를 쓰면 'iamfoodstylist Vol.06' 처럼 판본/권차만 다른
    서로 다른 작품이 합쳐지므로, 원본 식별자(source_url/book_seq)를 키에 포함한다.
    """
    seen: set[tuple[str, str, str, str]] = set()
    out: list[Notice] = []
    for notice in notices:
        key = (notice.platform, notice.source_url, notice.ends_at or "", notice.title)
        if key in seen:
            continue
        seen.add(key)
        out.append(notice)
    return out


def sort_notices(notices: Iterable[Notice]) -> list[Notice]:
    return sorted(notices, key=lambda n: (n.platform, n.ends_at or "9999-12-31", n.title))


# ---------------------------------------------------------------------------
# 보고
# ---------------------------------------------------------------------------


def build_report(
    notices: list[Notice],
    reports: list[CollectorReport],
    *,
    out_path: Path,
    probes: list[dict[str, Any]] | None = None,
    catalog=None,
) -> dict[str, Any]:
    real = [n for n in notices if n.source_kind != "fixture"]
    fixtures = [n for n in notices if n.source_kind == "fixture"]
    by_platform: dict[str, dict[str, int]] = {}
    for notice in notices:
        entry = by_platform.setdefault(notice.platform, {"real": 0, "fixture": 0})
        entry["fixture" if notice.source_kind == "fixture" else "real"] += 1
    match_summary = None
    if catalog:
        matched = match_many((n.to_dict() for n in real), catalog)
        match_summary = match_stats(matched)

    return {
        "generated_at": now_iso(),
        "version": __version__,
        "out_path": str(out_path),
        "total": len(notices),
        "real_collected": len(real),
        "fixture": len(fixtures),
        "by_platform": by_platform,
        "match_against_data_js": match_summary,
        "catalog_size": len(catalog) if catalog else 0,
        "platforms": [dataclasses.asdict(report) for report in reports],
        "blocked_probes": probes or [],
        "schema": {
            "fields": list(Notice.__dataclass_fields__),
            "platforms": list(PLATFORMS),
            "source_kinds": list(SOURCE_KINDS),
            "statuses": list(STATUSES),
            "confidences": list(CONFIDENCES),
        },
    }


def print_report(report: dict[str, Any]) -> None:
    print("=" * 100)
    print(f"서가(seoga) 종료 예정 공지 수집 보고서  v{report['version']}  {report['generated_at']}")
    print("=" * 100)
    header = f"{'platform':<12}{'status':<12}{'real':>6}{'fixture':>9}  {'source_kind':<20}note"
    print(header)
    print("-" * 100)
    for entry in report["platforms"]:
        kinds = ",".join(entry["source_kinds"]) or "-"
        note = entry["note"]
        if len(note) > 110:
            note = note[:107] + "..."
        print(
            f"{entry['platform']:<12}{entry['status']:<12}{entry['collected']:>6}"
            f"{entry['fixture_count']:>9}  {kinds:<20}{note}"
        )
    print("-" * 100)
    print(
        f"TOTAL lines={report['total']}  real={report['real_collected']}  "
        f"fixture={report['fixture']}  -> {report['out_path']}"
    )
    match_summary = report.get("match_against_data_js")
    if match_summary:
        print(
            f"data.js 카탈로그({report['catalog_size']}권) 매칭: "
            f"{match_summary['matched']}/{match_summary['total']} "
            f"({match_summary['match_rate'] * 100:.1f}%)"
        )
    if report.get("blocked_probes"):
        print("\n차단 플랫폼 현재 상태 재확인:")
        for probe in report["blocked_probes"]:
            print(f"  - {probe}")
    print("\n[정직성] real 컬럼 = 실제 HTTP 수집 건수. fixture = 데모/차단 플랫폼 자리표시자(실공지 아님).")


# ---------------------------------------------------------------------------
# self-test (네트워크 없이 스키마/정규화/매칭/픽스처 검증)
# ---------------------------------------------------------------------------


def run_self_tests(out_path: Path) -> int:
    failures: list[str] = []
    passes: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            passes.append(name)
            print(f"PASS  {name}" + (f"  ({detail})" if detail else ""))
        else:
            failures.append(name)
            print(f"FAIL  {name}" + (f"  ({detail})" if detail else ""))

    # 1) 스키마: 정상 1건
    good = make_notice(
        "millie",
        "소년이 온다",
        author="한강",
        isbn13="9788936434120",
        ends_at="2026-11-20",
        status="ending",
        source_url="https://example.com/book/1",
        source_kind="notice_page",
        confidence="high",
        raw_note="service_limit_date=2026-11-20",
    )
    check("schema.valid_example", good.is_valid(), str(good.problems()))

    # 2) 스키마: 잘못된 값 거부
    bad_cases = {
        "platform": dataclasses.replace(good, platform="aladin"),
        "source_kind": dataclasses.replace(good, source_kind="scraped_api"),
        "status": dataclasses.replace(good, status="maybe"),
        "confidence": dataclasses.replace(good, confidence="certain"),
        "ends_at_format": dataclasses.replace(good, ends_at="2026/11/20"),
        "ends_at_real_date": dataclasses.replace(good, ends_at="2026-02-31"),
        "title_empty": dataclasses.replace(good, title="  "),
        "isbn": dataclasses.replace(good, isbn13="123"),
        "collected_at_tz": dataclasses.replace(good, collected_at="2026-10-27T10:00:00"),
    }
    bad_ok = all(not case.is_valid() for case in bad_cases.values())
    broken = [name for name, case in bad_cases.items() if case.is_valid()]
    check("schema.reject_invalid", bad_ok, f"허용된 잘못된 케이스={broken}")

    # 3) JSONL 왕복
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "notices.jsonl"
        write_jsonl(tmp_path, [good])
        rows = load_jsonl(tmp_path)
        back = Notice(**rows[0])
        check("jsonl.roundtrip", back.is_valid() and back.to_dict() == good.to_dict())

    # 4) 제목 정규화
    title_cases = [
        ("소년이 온다 (개정판)", "소년이 온다"),
        ("소년이 온다 - 한강", "소년이 온다"),
        ("구의 증명: 최진영 장편소설", "구의 증명"),
        ("채식주의자 [리커버판]", "채식주의자"),
        ("  해리   포터와 마법사의 돌  ", "해리 포터와 마법사의 돌"),
        ("미술관에 간 인문학자(출간 10주년 기념 리커버판)", "미술관에 간 인문학자"),
        ("달러구트 꿈 백화점 1권", "달러구트 꿈 백화점"),
    ]
    failed = [(raw, normalize_title(raw), want) for raw, want in title_cases if normalize_title(raw) != want]
    check("normalize.title", not failed, f"실패={failed}")

    # 5) 저자 정규화
    author_cases = [
        ("한강 지음", "한강"),
        ("김현학, iamfoodstylist 편집부 (엮은이)", "김현학"),
        ("최진영 저", "최진영"),
        ("한강 (지은이)", "한강"),
        ("", ""),
    ]
    failed = [(raw, normalize_author(raw), want) for raw, want in author_cases if normalize_author(raw) != want]
    check("normalize.author", not failed, f"실패={failed}")

    # 6) ISBN 정규화
    check(
        "normalize.isbn",
        normalize_isbn("978-89-364-3412-0") == "9788936434120"
        and normalize_isbn("9788936434121") == "9788936434121"
        and normalize_isbn("123") is None,
    )

    # 7) data.js 카탈로그 파싱(읽기 전용)
    data_js = PROJECT_ROOT / "data.js"
    catalog = []
    if data_js.exists():
        catalog = load_data_js_catalog(data_js)
        check("data.js.parsed", len(catalog) >= 30, f"{len(catalog)}권")
        check(
            "data.js.fields",
            all(book.id and book.title and book.author for book in catalog)
            and len({book.id for book in catalog}) == len(catalog),
        )
        check(
            "data.js.av",
            any(entry.get("s") == "ending" for book in catalog for entry in book.av.values()),
            "종료 예정 데모 표기 존재",
        )
    else:
        check("data.js.parsed", False, "data.js 없음")

    # 8) 퍼지 매칭
    if catalog:
        sample = catalog[0]
        variants = [
            sample.title,
            sample.title + " (개정판)",
            sample.title + " - 부제",
            sample.title.replace(" ", ""),
            sample.title + " [리커버판]",
        ]
        results = [match_many([{"title": v, "author": sample.author}], catalog)[0]["match"] for v in variants]
        ok = all(r is not None and r["book_id"] == sample.id for r in results)
        check("match.exact_and_variants", ok, sample.title)
        typo = sample.title[:-1] + ("가" if sample.title[-1] != "가" else "나")
        fuzzy = match_many([{"title": typo, "author": sample.author}], catalog)[0]["match"]
        check("match.fuzzy_typo", fuzzy is not None, f"{typo!r} -> {(fuzzy or {}).get('book_id')}")
        check(
            "match.similarity",
            0.0 <= title_similarity("소년이 온다", "소년이 온다 (개정판)") <= 1.0
            and title_similarity("전혀 다른 제목", "채식주의자") < 0.6,
        )

    # 9) fixture 안전성: fixture 는 절대 종료일을 날조하지 않는다
    from .base import fixture_notices, load_demo_catalog

    demo = load_demo_catalog()
    fixture_rows = []
    for platform in ("ridiselect", "sam", "willa", "crema"):
        fixture_rows.extend(fixture_notices(platform, demo, limit=3))
    check(
        "fixture.no_invented_dates",
        all(row.ends_at is None for row in fixture_rows),
        f"fixture {len(fixture_rows)}건 전부 ends_at=None",
    )
    check(
        "fixture.marked",
        all(row.source_kind == "fixture" and "FIXTURE" in row.raw_note and row.confidence == "low" for row in fixture_rows),
        "source_kind/raw_note/confidence 표기",
    )
    check("fixture.valid_schema", all(row.is_valid() for row in fixture_rows), str([r.problems() for r in fixture_rows]))

    # 10) 수집기 계약
    contract_errors: list[str] = []
    for cls in COLLECTOR_CLASSES:
        collector = cls(client=HttpClient(min_interval=MIN_INTERVAL_SEC))
        if cls.platform not in PLATFORMS:
            contract_errors.append(f"{cls.__name__}: platform={cls.platform}")
        if cls.source_kind not in SOURCE_KINDS:
            contract_errors.append(f"{cls.__name__}: source_kind={cls.source_kind}")
        if not cls.endpoints:
            contract_errors.append(f"{cls.__name__}: endpoints 비어있음")
        if cls.blocked and not hasattr(collector, "collect_from_partner_api"):
            contract_errors.append(f"{cls.__name__}: 제휴 API 어댑터 없음")
    check("collectors.contract", not contract_errors, str(contract_errors))
    adapter_required = [cls for cls in COLLECTOR_CLASSES if cls.blocked or cls.platform in ("sam", "crema")]
    check(
        "collectors.partner_adapter_skeleton",
        all(hasattr(cls(), "collect_from_partner_api") for cls in adapter_required),
        f"{len(adapter_required)}개 수집기(실수집 불가) 어댑터 메서드 보유",
    )

    # 11) HTTP 정책 상수
    check("http.user_agent", USER_AGENT.startswith("seoga-research-bot/") and "contact" in USER_AGENT, USER_AGENT)
    check("http.rate_limit", MIN_INTERVAL_SEC >= 1.0, f"min_interval={MIN_INTERVAL_SEC}s")
    check("http.cache_dir", CACHE_DIR.name == "_cache", str(CACHE_DIR))

    # 12) --out 기존 파일이 있으면 실제 산출물도 검증
    if out_path.exists():
        rows = load_jsonl(out_path)
        notices = [Notice(**row) for row in rows]
        errors = validate_notices(notices)
        check("out.existing_jsonl_valid", not errors, f"{out_path} {len(notices)}줄 / {errors[:3]}")
        keys = set(rows[0].keys()) if rows else set(Notice.__dataclass_fields__)
        check("out.schema_fields", keys == set(Notice.__dataclass_fields__), str(sorted(keys)))
    else:
        print(f"INFO  out 파일 없음(생략): {out_path}")

    print("-" * 100)
    print(f"SELFTEST  pass={len(passes)}  fail={len(failures)}")
    if failures:
        print("FAILED:", ", ".join(failures))
        return EXIT_FAIL
    print("SELFTEST OK")
    return EXIT_OK


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m ingest.notices.run",
        description="서가(seoga) 구독 플랫폼 종료 예정 공지 수집·정규화",
    )
    parser.add_argument("--out", default="data/notices.jsonl", help="출력 JSONL 경로")
    parser.add_argument("--report", action="store_true", help="수집 보고서 출력")
    parser.add_argument("--report-json", default=None, help="보고서를 JSON 파일로도 저장")
    parser.add_argument("--self-test", action="store_true", help="오프라인 스키마/정규화/매칭 self-test")
    parser.add_argument("--refresh", action="store_true", help="원본 캐시 무시하고 재요청")
    parser.add_argument("--no-fixtures", action="store_true", help="fixture 행 제외(실수집만)")
    parser.add_argument(
        "--platforms",
        default="",
        help="쉼표 구분 수집 대상 (millie,ridiselect,sam,willa,crema)",
    )
    parser.add_argument("--verify-blocked", action="store_true", help="차단 플랫폼 현재 HTTP 상태 재확인")
    parser.add_argument("--cache-dir", default=str(CACHE_DIR), help="원본 응답 캐시 디렉토리")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = PROJECT_ROOT / out_path

    if args.self_test:
        return run_self_tests(out_path)

    platforms = [item.strip() for item in args.platforms.split(",") if item.strip()]
    unknown = [item for item in platforms if item not in PLATFORMS]
    if unknown:
        print(f"ERROR: 알 수 없는 platform: {unknown} (가능: {PLATFORMS})", file=sys.stderr)
        return EXIT_FAIL

    client = HttpClient(cache_dir=Path(args.cache_dir), refresh=args.refresh)
    notices, reports, probes = run_collectors(
        client=client,
        platforms=platforms,
        with_fixtures=not args.no_fixtures,
        verify_blocked=args.verify_blocked,
    )
    notices = sort_notices(dedupe(notices))

    errors = validate_notices(notices)
    if errors:
        print("ERROR: 스키마 검증 실패", file=sys.stderr)
        for error in errors[:10]:
            print("  " + error, file=sys.stderr)
        return EXIT_FAIL

    count = write_jsonl(out_path, notices)

    catalog = None
    data_js = PROJECT_ROOT / "data.js"
    if data_js.exists():
        try:
            catalog = load_data_js_catalog(data_js)
        except Exception:  # noqa: BLE001 - 매칭 리포트는 부가 기능
            catalog = None

    report = build_report(notices, reports, out_path=out_path, probes=probes, catalog=catalog)
    if args.report:
        print_report(report)
    else:
        print(f"OK: {count}줄 -> {out_path} (real={report['real_collected']}, fixture={report['fixture']})")

    if args.report_json:
        report_path = Path(args.report_json)
        if not report_path.is_absolute():
            report_path = PROJECT_ROOT / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report json -> {report_path}")

    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
