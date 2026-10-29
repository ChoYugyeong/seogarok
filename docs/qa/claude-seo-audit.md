# claude-seo 적용 감사 리포트 — seogarok.com

도구: [AgriciDaniel/claude-seo](https://github.com/AgriciDaniel/claude-seo) (26 sub-skills · 19 sub-agents, MIT)
실행: `scripts/agentic_check.py`, `scripts/sitemap_discovery.py` + seo-agentic / seo-sitemap / seo-schema / seo-programmatic 스킬 체크리스트

## 1. 감사 전 (Baseline)

`agentic_check.py https://seogarok.com --json`

| 우선순위 | 항목 | 상태 |
| --- | --- | --- |
| P0 | server-rendered (JS 없이 본문) | ✅ pass |
| P0 | robots-reachable | ✅ pass |
| P0 | robots-ai-groups (AI 에이전트 명시 그룹) | ℹ️ info |
| P1 | robots-user-agents | ✅ pass |
| P1 | content-signal | ℹ️ info (없음) |
| P1 | llms-txt | ℹ️ info — **/llms.txt 404** |
| P1 | markdown-delivery | ℹ️ info (alternate·.md 없음) |
| P1 | http-404 | ✅ pass |

`sitemap_discovery.py`: 선언·유효 2개, **sitemap-index 없음**. 경고 0.

## 2. 적용한 수정 (claude-seo 발견 → 구현)

| 발견 | 수정 |
| --- | --- |
| llms.txt 404 | `/llms.txt`(H1+blockquote+링크), `/llms-full.txt` 서버 라우트 신설 |
| Markdown 미지원 | `/index.md`, `/book/{id}.md` + `<link rel="alternate" type="text/markdown">` |
| robots AI 그룹 없음 | GPTBot·OAI-SearchBot·ChatGPT-User·ClaudeBot·Claude-SearchBot·Claude-User·PerplexityBot·Google-Extended·Applebot-Extended·CCBot·Bingbot·Yeti 그룹 명시 |
| Content-Signal 없음 | 그룹별 `Content-Signal: search=yes, ai-input=yes, ai-train=no` |
| sitemap-index 없음 | `/sitemap-index.xml` 라우트 + robots 선언 |
| sitemap lastmod 부정확 | 책 사이트맵의 `lastmod`(출간일 오용) 제거 |
| programmatic thin content | 사이트맵 게이트: `description` 있는 책만(5,000권 유지). 설명 없는 책은 속성 기반 고유 fallback 문단 생성 |
| Schema 보강 | Book: publisher·mainEntityOfPage·numberOfPages · 홈: Organization · 소개: AboutPage |
| GEO citability | 책 랜딩 상단에 **“한 줄 요약”** answer-first 블록(가용성+확인일) |
| QA/모니터링 | `_qa/qa_suite.py`에 llms·Content-Signal·AI 그룹·Markdown 검사, `seo-health` 워크플로 확장 |

## 3. 감사 후 (After)

`agentic_check.py` 결과:

```
P0 pass 3 / 3   (server-rendered, robots-reachable, robots-ai-groups)
P1 pass 5 / 5   (robots-user-agents, content-signal, llms-txt, markdown-delivery, http-404)
P2 info 1       (webmcp-tools — 대화형 도구 없음: 해당 없음)
P3 na 4         (WebMCP 폼·ARD·A2A·UCP — 선택 사항)
llms: status 200, lighthouse pass, llms-full 200
markdown: alternate 200, .md sibling 200
content-signal: 모든 AI 에이전트 그룹에 적용
```

`sitemap_discovery.py`: `sitemap-index.xml`(sitemapindex) + 2개 urlset 모두 200/valid, 경고 0.

## 4. 남은 항목 (선택)

| 항목 | 판단 |
| --- | --- |
| WebMCP tools | 사용자 상호작용 도구(예약·구매)가 없어 **해당 없음** |
| ai-catalog.json / Agentmap (ARD) | 공개 API를 에이전트 카탈로그로 노출하면 가치. `/api/search` 등 이미 공개 — 다음 단계 후보 |
| A2A agent card / UCP | 에이전트 서버·커머스 프로토콜 미지원: 해당 없음 |
| Lighthouse Agentic Browsing fraction | playwright/Lighthouse 실행 필요(CI 미설치). 로컬 ego-browser로 별도 확인 가능 |
| 백링크/E-E-A-T 심화 | seo-backlinks/seo-content 스킬 영역 — GSC 등록 후 데이터 확보 시 |

## 5. 재현 방법

```bash
git clone https://github.com/AgriciDaniel/claude-seo.git
cd claude-seo/scripts
python agentic_check.py https://seogarok.com --json
python sitemap_discovery.py https://seogarok.com --json
```
