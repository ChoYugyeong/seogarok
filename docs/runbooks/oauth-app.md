# Google OAuth 앱 운영 런북

프로젝트: `project-40262700-d1b6-4c9f-83d` (OAuth 클라이언트 생성 프로젝트)
클라이언트 유형: 웹 애플리케이션
리디렉션 URI: `https://seogarok.com/api/auth/google/callback`

## 1. 현재 상태 (2026-10-30)

- 동의 화면 게시 상태: **테스트 중(Testing)**
- 테스트 사용자: 미등록 → 로그인/GSC 연결 시 `403 access_denied`
- 해결: 테스트 사용자에 `cho4639@gmail.com` 추가

## 2. 테스트 사용자 추가 (지금)

1. https://console.cloud.google.com/apis/credentials/consent?project=project-40262700-d1b6-4c9f-83d
2. **대상(Audience)** → **테스트 사용자(Test users)** → **ADD USERS**
3. `cho4639@gmail.com` 추가 → 저장
4. 사이트 `로그인` 또는 GSC 연결 링크 재시도

## 3. 공개 로그인 (게시) 전략

| 전략 | 장점 | 단점 |
| --- | --- | --- |
| **A. 기본 스코프만으로 게시** (`openid email profile`) | 검증 없이 게시 가능, 전체 사용자 로그인 가능 | GSC `webmasters.readonly`(민감) 사용 불가 → 색인 API 모니터링은 수동/별도 |
| **B. 민감 스코프 포함 게시** | 로그인 + GSC 자동화 모두 가능 | Google 앱 검증 필요(브랜드·개인정보·데모 영상, 수일~수주) |
| **C. 테스트 유지** | 즉시 사용 가능 | 테스트 사용자만 로그인, **refresh token 7일 만료** |

권장: **A로 게시** → 로그인 공개. GSC 색인 모니터링은
- GSC 화면에서 주 1회 수동 확인, 또는
- 별도 프로젝트에서 검증 후 자동화(추후)

## 4. 게시 절차 (A안)

1. 동의 화면 → **범위(Scopes)** 에서 `openid`, `email`, `profile`만 유지
   - `webmasters.readonly`는 GSC 자동화 전용이므로 공개 앱에서는 제외
2. **게시(App in production)** 클릭
3. 지원 이메일·개인정보처리방침 URL(`https://seogarok.com/privacy.html`)·약관 URL(`https://seogarok.com/terms.html`) 입력 확인
4. 게시 후 로그인 테스트 (시크릿 창, 다른 계정)

## 5. 테스트 모드 주의

- 테스트 모드 refresh token은 **7일 후 만료** → GSC 자동화가 매주 재승인 필요
- `seo-index` 워크플로가 실패하면 토큰 만료 신호 → 연결 링크 재발급:
  ```powershell
  python scripts/gsc_connect_link.py   # 새 링크로 재승인
  python scripts/gsc_fetch_token.py
  pwsh -NoProfile -File scripts/set_gsc_secrets.ps1
  gh workflow run seo-index.yml
  ```
