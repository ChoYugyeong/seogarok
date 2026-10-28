# YES24 API 키 교체 런북

> 대상: 온디맨드 조회(카탈로그 미수록 책)용 YES24 Open API 키
> 저장 위치: **GCP Secret Manager** `yes24-api-key` (Cloud Run 은 `latest` 버전 참조)
> 평문은 Terraform state·GitHub·이미지에 저장하지 않는다.

## 0. 사전 확인

```bash
gcloud config set project seoga-prod
gcloud secrets versions list yes24-api-key      # 현재 버전 확인
gcloud run services describe seogarok-api \
  --region asia-northeast1 \
  --format="value(spec.template.spec.containers[0].env)"
# YES24_API_KEY 가 value_source.secret_key_ref 로 보이면 정상 (평문 value 아님)
```

## 1. 새 키 발급

1. <https://developers.yes24.com> 로그인 → API 키 재발급
2. 새 키를 안전한 곳(비밀번호 관리자)에 임시 저장 — 채팅/이슈/커밋에 붙이지 않는다

## 2. 새 버전 추가 (무중단)

```bash
# 키를 파일로 저장한 뒤 (예: .tmp_key), 파일은 즉시 삭제
gcloud secrets versions add yes24-api-key --data-file=.tmp_key
rm .tmp_key

gcloud secrets versions list yes24-api-key   # 새 버전이 enabled 인지 확인
```

- Cloud Run 은 `latest` 를 참조하므로 **다음 배포/재시작부터 새 키 사용**
- 즉시 반영하려면 서비스 재배포(빈 커밋 push 또는 `gcloud run services update-traffic` 트리거 아님)

```bash
gcloud run deploy seogarok-api \
  --region asia-northeast1 \
  --image "$(gcloud run services describe seogarok-api --region asia-northeast1 --format='value(spec.template.spec.containers[0].image)')"
# 또는 GitHub Actions deploy-cloudrun 수동 실행
```


> ⚠️ **개행 주의**: 키를 파일로 만들 때 끝에 개행(CR/LF)이 붙으면 Cloud Run 이 환경변수로 주입할 때
> HTTP 헤더 오류(`Invalid header value`)로 온디맨드 조회가 실패한다. 반드시 개행 없이 저장:
> `[IO.File]::WriteAllText(path, key)` (PowerShell) / `printf %s "$KEY" > .tmp_key` (bash)

## 3. 검증

```bash
# 온디맨드 조회가 살아있는지 (카탈로그에 없는 책)
curl -s "https://seogarok.com/api/search?q=%EB%93%84&limit=3" | jq '{count,strategy,first:.results[0].title}'
# 기대: {"count":..., "strategy":"hybrid-live", "first":"듄 신장판 ..."}

# API 에러 모니터링 (키 만료/차단 시 401/403 → on_demand 비활성화됨)
curl -s "https://seogarok.com/api/health" | jq .
```

## 4. 구 버전 비활성화

검증 후 24시간 뒤:

```bash
gcloud secrets versions disable <OLD_VERSION> --secret=yes24-api-key
# 문제가 없으면 파괴
gcloud secrets versions destroy <OLD_VERSION> --secret=yes24-api-key
```

## 5. 롤백

새 키가 문제면 이전 버전으로 되돌린다:

```bash
gcloud secrets versions list yes24-api-key
gcloud run deploy seogarok-api \
  --region asia-northeast1 \
  --image "$(gcloud run services describe seogarok-api --region asia-northeast1 --format='value(spec.template.spec.containers[0].image)')" \
  --update-env-vars "YES24_API_KEY_SENTINEL=1"   # env 변경 트리거
# 이후 Secret Manager 에서 latest 를 이전 버전으로 되돌리려면:
gcloud secrets versions add yes24-api-key --data-file=<이전키파일>
```

> 주의: `latest` 참조는 버전을 "되감기"할 수 없으므로, 이전 키를 새 버전으로 다시 add 해야 한다.

## 6. 주기적 교체 권장 주기

| 항목 | 권장 |
|---|---|
| 정기 교체 | **6개월** |
| 키 노출 의심(채팅/로그/스크린샷) | **즉시** |
| 담당자 변경 | 즉시 |

## 7. 체크리스트

- [ ] 새 키 발급
- [ ] `gcloud secrets versions add` (파일 즉시 삭제)
- [ ] 배포/재시작으로 새 버전 반영
- [ ] `/api/search?q=듄` → `hybrid-live` 확인
- [ ] 24시간 후 구 버전 disable → destroy
- [ ] 비밀번호 관리자·런북 기록 갱신
