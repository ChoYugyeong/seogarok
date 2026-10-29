# emilkowalski/skills 적용 리포트 — seogarok.com

도구: [emilkowalski/skills](https://github.com/emilkowalski/skills)
적용 스킬: `mobile-native`, `review-animations`, `animation-performance`, `emil-design-eng`, `break-ui`
참조: `ui-cheatsheet.md`, `performance-cheatsheet.md`

## 감사로 잡은 것 (Before)

| 문제 | 근거 스킬 | 수정 |
| --- | --- | --- |
| 모바일 입력 15~15.5px → iOS가 페이지 확대 | mobile-native #4 | 모바일 `input/select/textarea` **16px** |
| 탭 시 회청색 하이라이트 | mobile-native #2 | 전역 `-webkit-tap-highlight-color: transparent` + 모든 컨트롤 `:active` 피드백 |
| hover 스타일 34개가 터치에서 눌린 채 남음(sticky hover) | mobile-native #1 / review-animations #8 | **34개 규칙 전부** `@media (hover: hover) and (pointer: fine)` 로 게이팅 |
| 스크롤 체이닝(가로 레일·드로어) | mobile-native | `overscroll-behavior: contain`, `html/body` overscroll-y none, `touch-action: manipulation` |
| 토스트/드로어가 노치·홈 인디케이터와 겹침 | mobile-native | `env(safe-area-inset-bottom)` |
| 버튼 피드백이 `translateY(1px)` | ui-cheatsheet | **`transform: scale(0.97)`** 로 교체 |
| 드로어·토스트·자동완성이 애니메이션 없이 툭 등장 | review-animations #3·#5 | 140~240ms **ease-out 커스텀 커브**(`cubic-bezier(.22,1,.36,1)`), transform/opacity만 |
| 숫자 폭 흔들림 | ui-cheatsheet | 금액·순위·D-day 등 `font-variant-numeric: tabular-nums` |
| 긴 제목/작가가 카드·드로어에서 넘칠 위험 | break-ui | `overflow-wrap: anywhere` + 말줄임 유지 |
| 본문 줄 길이 과다 | ui-cheatsheet | `.dw-blurb/.prose/.legal/.summary` `max-width: 65ch` |
| `transform-origin`/`ease-in`/`transition: all` 위반 | review-animations | 감사 결과 **0건** (기존 상태 양호), 자동완성은 `transform-origin: top center` |
| reduced motion | review-animations #8 | 이동 제거·투명도 유지 (`animation: none !important`) |

## 라이브 검증 (2026-10-30)

| 항목 | 결과 |
| --- | --- |
| 모바일 hover 지원 인식 | `(hover: hover) = false`, `(pointer: coarse) = true` |
| 검색 입력 폰트 | **16px** (iOS 확대 트리거 제거) |
| tap highlight | `rgba(0,0,0,0)` |
| body overscroll | `none` |
| 390px 가로 넘침 | **없음** |
| 드로어 모션 | `seog-panel-in` · **240ms** · `cubic-bezier(0.22,1,0.36,1)` |
| prefers-reduced-motion | 애니메이션 **none** · transform none |
| QA 스위트 | **PASS (0 fails/0 warns)** · p95 **504ms** |
| axe 접근성 | home/search/drawer **0 violations** |

## break-ui 결과

최악값 주입(제목 2회 반복·작가 12인·`1,234,567,890권`·긴 공지 제목) 후 측정:
- 페이지 가로 넘침 없음, 드로어/카드/히어로 오버플로 없음
- `.rank-author`는 말줄임(ellipsis) 처리로 시각적 넘침 없음 — 의도된 동작

## 남은 권장 (실기기)

- iOS Safari / Android Chrome 실기기에서 확인: sticky hover·탭 지연·safe-area·키보드
- 전체화면 셸을 추가할 경우 `100dvh` 사용(현재는 `vh` 의존 없음)
- `overscroll-behavior-y: none`은 **당겨서 새로고침을 끄는** 결정 — 필요 시 `auto`로 완화
- 실기기 햅틱(짧은 진동)은 `navigator.vibrate`로 선택 적용 가능

## 재현

```bash
git clone https://github.com/emilkowalski/skills.git
# skills/mobile-native/SKILL.md, skills/review-animations/SKILL.md,
# skills/animation-performance/SKILL.md, skills/break-ui/SKILL.md 참조
```
