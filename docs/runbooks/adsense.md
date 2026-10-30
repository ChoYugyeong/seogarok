# AdSense 런북

## 1. 준비 (사용자)

1. https://adsense.google.com 가입 → 사이트 추가 `seogarok.com`
2. **소유 확인**: AdSense가 준 스니펫 또는 meta 태그
   - meta: `<meta name="google-adsense-account" content="ca-pub-XXXXXXXX" />`
   - 또는 AdSense 코드 스니펫(스크립트)
3. 사이트 심사 통과까지 **2일~4주** (콘텐츠 품질·정책·트래픽)
4. 게시자 ID(`ca-pub-...`) 확보 → 배포 환경변수 `ADSENSE_CLIENT`에 설정

## 2. 이 저장소에 이미 구현된 것

- `ads.txt`: `server/api.py` 라우트 — `ADSENSE_CLIENT` env가 있을 때만 응답
- 동의 배너: `ads.js` — **동의 후에만** AdSense 스크립트 로드(쿠키/광고 미리 로드 없음)
- 정책: `privacy.html`·`legal.html`에 AdSense 쿠키/맞춤형 광고/철회 경로 반영
- `index.html`: `seogarok-adsense-client` / `google-adsense-account` meta 자리

## 3. 활성화 순서

1. `index.html`의 meta 두 곳 값 채우기:
   ```html
   <meta name="seogarok-adsense-client" content="ca-pub-XXXXXXXXXXXXXXXX" />
   <meta name="google-adsense-account" content="ca-pub-XXXXXXXXXXXXXXXX" />
   ```
2. Cloud Run env `ADSENSE_CLIENT=ca-pub-...` 추가 (ads.txt용)
   ```bash
   gcloud run services update seogarok-api --region asia-northeast1 \
     --update-env-vars ADSENSE_CLIENT=ca-pub-XXXXXXXXXXXXXXXX
   ```
3. 배포 후 확인
   - `https://seogarok.com/ads.txt` → `google.com, pub-..., DIRECT, f08c47fec0942fa0`
   - 사이트 첫 방문 시 동의 배너 표시 → "광고 허용" 시 AdSense 스크립트 로드
4. AdSense 콘솔에서 **Auto ads** 켜기(권장) 또는 광고 단위 코드를 추가 배치

## 4. 정책 체크리스트

- [ ] 개인정보처리방침에 광고 쿠키·제3자(Google) 고지 (완료)
- [ ] 동의 전 광고 스크립트/쿠키 미로드 (완료)
- [ ] `ads.txt` 공개 (게시자 ID 설정 시)
- [ ] 콘텐츠: 16,000+ 책 랜딩, thin 페이지 noindex, 개인정보/약관/문의 존재
- [ ] 광고 클릭 유도·오해성 배치 금지, 모바일 광고가 하단 내비를 가리지 않게 확인

## 5. 주의

- AdSense 심사 중에는 결제/광고 코드를 넣지 않아도 됨(사이트 확인용 meta만).
- 승인 전에는 동의 배너가 뜨지 않는다(클라이언트 ID가 비어 있으므로).
- 광고 수익화와 별개로 기존 익명 통계는 쿠키를 쓰지 않는다.

## 활성화 기록 (2026-10-30)

- 게시자 ID: `ca-pub-5571356208554399`
- Cloud Run env `ADSENSE_CLIENT=ca-pub-5571356208554399` 설정 완료
- `https://seogarok.com/ads.txt` → `google.com, pub-5571356208554399, DIRECT, f08c47fec0942fa0`
- `index.html`: `seogarok-adsense-client` · `google-adsense-account` meta 반영
- 라이브: 동의 배너 → "광고 허용" 시 AdSense 스크립트 로드, "필수만" 시 미로드
- 광고 게재는 AdSense 사이트 심사/승인 후 시작됨 (승인 전에는 스크립트만 로드)

## 고정 광고 슬롯 (홈/책 상세)

승인 후 광고 단위를 만들고 슬롯 ID를 env로 넣으면 **재배포 없이** 활성화된다.

1. AdSense → 광고 → 광고 단위 → **디스플레이 광고** 2개 생성
   - 이름 예: `seogarok-home-feed`, `seogarok-book-detail`
   - 반응형 선택
2. 각 단위의 **data-ad-slot 숫자**(10자리) 확인
3. Cloud Run env 설정:
   ```bash
   gcloud run services update seogarok-api --region asia-northeast1 \
     --update-env-vars ADSENSE_SLOT_HOME=1234567890,ADSENSE_SLOT_BOOK=0987654321
   ```
4. 확인
   - `https://seogarok.com/api/ads/config` → `{"client":"...","slots":{"home":"...","book":"..."}}`
   - 홈 하단·책 상세 하단에 "광고" 라벨 + 반응형 슬롯 표시 (동의 후)
5. 슬롯을 끄려면 env를 빈 값으로 업데이트하거나 제거.

**정책**: 고정 슬롯은 홈(콘텐츠 하단)과 책 상세(관련 책 아래)에만 배치. 로그인·개인정보·약관·문의 페이지에는 넣지 않는다.
