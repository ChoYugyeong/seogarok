# 보안 · 개인정보 운영 런북

최종 점검: 2026-10-30 (구글 로그인·기기 간 서재 동기화 도입 시점)

## 1. 데이터 맵

| 데이터 | 저장 위치 | 보관 | 접근 권한 |
| --- | --- | --- | --- |
| 구글 계정 정보(sub/email/name/picture) | GCS `auth/users/{sub}.json` (비공개 버킷) | 탈퇴 시까지 | 런타임 SA(seogarok-api) |
| 세션 | GCS `auth/sessions/{sha256(sid)}.json` | 30일 | 런타임 SA |
| 동기화된 내 서재 | GCS `auth/shelves/{sub}.json` | 탈퇴 시까지 | 런타임 SA |
| OAuth 클라이언트/세션 시크릿 | GCS `auth/config.json` (비공개) | 유지 | 런타임 SA |
| 푸시 구독(endpoint·watches) | GCS `push/subs/*.json` | 해지 시까지 | 런타임 SA |
| 익명 통계 이벤트 | GCS `analytics/events/*` | 최대 90일 | 런타임 SA/분석 워크플로 |
| 접속 로그 | Cloud Logging | 최대 30일 | 배포 SA |
| 브라우저 로컬 데이터(localStorage) | 이용자 기기 | 이용자 삭제 시까지 | 이용자만 |

- 버킷 `seogarok-reports`는 **비공개**(allUsers/allAuthenticatedUsers 바인딩 없음, 서울 리전 asia-northeast3)
- 점검 명령:
  ```bash
  gcloud storage buckets get-iam-policy gs://seogarok-reports --format=json | grep -E "allUsers|allAuthenticatedUsers"  # 결과 없어야 함
  gcloud storage ls gs://seogarok-reports/auth/  # 객체 목록(비공개)
  ```

## 2. 인증·세션 보안 (구현 상태)

- Google OAuth **Authorization Code** 흐름, `state`는 HMAC 서명 쿠키로 발급·검증(10분)
- 세션 토큰: 32바이트 랜덤, 서버에는 **SHA-256 해시만** 저장
- 쿠키: `__Host-seogarok_session` — `HttpOnly; Secure; SameSite=Lax; Path=/` (도메인 미설정)
- 로그아웃/계정 삭제 시 세션 삭제, 계정 삭제 시 users/sessions/shelves 즉시 삭제
- OAuth 제공자 토큰은 저장하지 않음, `email_verified=false`는 로그인 거부
- 상태 변경 API: **Origin 검증(교차 출처 403)** + SameSite=Lax
- 인증 API: IP 기준 **30req/분 rate limit**
- 요청 본문 상한 1MB 초과 시 413
- 서재 입력 검증: 문자열 id, 항목당 최대 500개
- HTTP → HTTPS 302 리다이렉트, HSTS 적용

## 3. 비밀 관리

| 비밀 | 저장 | 회전 |
| --- | --- | --- |
| YES24 Open API 키 | Cloud Run Secret(`yes24-api-key`) + GitHub Secret | 유출 시 즉시 재발급 |
| Google OAuth client secret | GCS `auth/config.json` (비공개) | 콘솔에서 재발급 후 config 교체 |
| 세션 서명 시크릿 | GCS `auth/config.json` 내 `session_secret` | **교체 시 전체 세션 무효화**(전체 로그아웃) |
| VAPID 키 | GCS `push/vapid.json` | 교체 시 푸시 재구독 필요 |
| GitHub Actions | Repository Secrets | 유출 시 rotate + audit log |

- `.env`/`data/enrich_cache`/`auth` 객체는 **git 커밋 금지** (`.gitignore` 확인)
- Google OAuth 클라이언트 JSON 파일은 발급 후 안전한 곳에 보관, 저장소에 커밋 금지

## 4. 정보주체 권리(DSR) 처리

1. **열람/삭제 요청**: GitHub Issues 접수 → 7일 내 처리
2. **계정 삭제**: 사이트 내 `내 서재 → 계정 삭제` (즉시 GCS 객체 삭제)
3. **브라우저 데이터**: 이용자가 직접 localStorage/쿠키 삭제
4. 처리 결과 회신 후 이슈 close

## 5. 사고 대응 (개인정보 유출 의심 시)

1. 영향 범위 확인: Cloud Logging/버킷 접근 로그, 비정상 API 호출 여부
2. 즉시 차단: 노출된 비밀 회전(4번 표), 세션 시크릿 교체로 전체 세션 무효화
3. 필요 시 `auth/*` 객체 삭제(전체 계정 초기화) — 삭제 전 백업/법적 검토
4. 정보주체 통지 및 개인정보보호위원회 신고 검토(법령 기준)
5. 재발 방지: 원인 분석 후 런북/코드 반영

## 6. 정기 점검 (월 1회)

- [ ] 버킷 IAM에 공개 바인딩 없는지 확인
- [ ] GitHub Secrets 목록/최근 변경 확인 (`gh secret list`)
- [ ] 의존성 취약점 점검: `pip install pip-audit && pip-audit -r requirements.server.txt`
- [ ] 인증 로그 rate limit/차단 동작 확인 (`/api/auth/google/start` 반복 호출 429)
- [ ] 개인정보처리방침·이용약관 최신성 확인 (privacy.html / terms.html)
- [ ] Google OAuth consent screen의 **개인정보처리방침 URL**(`https://seogarok.com/privacy.html`)·**서비스 약관 URL**(`https://seogarok.com/terms.html`) 최신 여부

## 7. Google OAuth Consent Screen 체크리스트 (1회)

- 앱 이름: 서가록 / 지원 이메일
- **개인정보처리방침 URL**: https://seogarok.com/privacy.html
- **서비스 약관 URL**: https://seogarok.com/terms.html
- 승인된 도메인: `seogarok.com`
- 승인된 리디렉션 URI: `https://seogarok.com/api/auth/google/callback`
- 범위: `openid`, `email`, `profile` (비민감)

## 8. 관련 문서

- 개인정보처리방침: [`privacy.html`](../../privacy.html) · 이용약관: [`terms.html`](../../terms.html) · 데이터 출처: [`legal.html`](../../legal.html)
- 인증 코드: [`server/auth.py`](../../server/auth.py) · 저장소: [`server/store.py`](../../server/store.py)
- 검색 색인 런북: [`search-indexing.md`](search-indexing.md)
