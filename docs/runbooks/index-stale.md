# 런북: 인덱스 stale / 준비 실패 (`SeogaNotReady`, `SeogaIndexStale`, `SeogaIndexEmpty`)

> **이 문서가 답하는 질문:** ① `/readyz`가 503인 이유를 "문서 0 / 벡터 0 / 문서≠벡터"로 어떻게 구분하나? ② 재색인은 컨테이너와 로컬에서 각각 무엇을 실행해야 하나? ③ 재색인 후 "언제, 무엇으로" 최신 인덱스가 반영됐다고 검증하나?

관련 알림: `SeogaNotReady`(`seoga_ready == 0`, 1m), `SeogaIndexStale`(`seoga_index_age_seconds > 86400`, 10m), `SeogaIndexEmpty`(`seoga_index_documents == 0`, 1m). 관련 문서: [SRE.md](../SRE.md) §10–§11, [postmortem/2026-10-27-index-stale.md](../postmortem/2026-10-27-index-stale.md).

---

## 1. 증상

- `/readyz`가 **503**이며 응답에 `documents`, `vectors`, `error` 중 하나가 원인을 지시.
- Grafana **Index documents**가 0 또는 기대값(컨테이너 500 / 로컬 전체 4,865)과 불일치.
- `/api/health`의 `books`/`synced_at`이 오래됐거나, 재색인 직후인데도 갱신되지 않음.
- 검색 결과에 방금 적재한 책이 없거나, 이전 카탈로그 결과만 나옴.

## 2. 단일 소스: `/readyz`를 믿어라

`/readyz`는 **DB에서 실제 count를 읽는다**. `/api/health`는 부팅 시 메타 캐시이므로 재색인 후 재기동 전까지 옛 값을 보여준다(2026-10-27 사고의 원인). 두 값이 다르면 **`/readyz`가 진실**이고, `/api/health` 불일치는 "재기동이 필요하다"는 신호다.

```powershell
curl.exe -s http://127.0.0.1:8100/readyz
# 200: {"ready":true,"documents":500,"vectors":500,"embed":"model2vec","index_backend":"sqlite-vec"}
# 503: {"ready":false,"documents":0,"vectors":0,...}   ← 문서/벡터 없음
# 503: {"ready":false,"documents":412,"vectors":4865,...} ← 적재 중단/불일치

curl.exe -s http://127.0.0.1:8100/metrics | Select-String "seoga_(index|ready|db_size)"
```

| 관찰 | 해석 | 조치 |
|---|---|---|
| `documents=0` | DB에 카탈로그가 없음 / DB 경로 오류 | §3-A(컨테이너) 또는 §3-B(로컬) |
| `documents>0`, `vectors=0` | 벡터 적재 단계 실패(모델/임베딩) | §4 |
| `documents≠vectors` | sync 중단(배치 일부 실패) | §4 |
| `ready:true`인데 `/api/health.books`가 옛 값 | 프로세스 메타 캐시 stale | §5 재기동 |
| `seoga_index_age_seconds > 86400` | 컨테이너면 "이미지 빌드 후 24h 경과"일 수 있음 | §6 신선도 해석 |

## 3. 재색인 절차

### A. 컨테이너 스택 (표준: 인덱스는 이미지에 구워짐)

`read_only: true` + `tmpfs /tmp` 구조이므로 **런타임에 DB를 다시 만들지 않는다**. 재색인 = 이미지 재빌드다.

```powershell
# 1) 원본 카탈로그 확인 — 저장소/컨텍스트에는 500권 샘플이 들어있다
Get-Content data\catalog.jsonl | Measure-Object -Line
# 2) 재빌드(빌드 단계에서 server.sync 실행, 500권 인덱스 생성)
docker compose build --no-cache api
docker compose up -d api
# 3) 검증 (§5)
```

> 전체 4,865권 인덱스로 컨테이너를 만들려면 로컬에서 전체 카탈로그를 준비한 뒤 Dockerfile의 SYNC 입력을 전체 파일로 바꾸는 별도 빌드가 필요하다. 현재 저장소 기본 이미지는 500권 샘플 기준이다.

### B. 로컬 호스트 실행 (전체 4,865권)

```powershell
cd C:\Dev\seoga

# 1) 소스 확인 — 카탈로그가 없으면 sync가 seed(38권)로 폴백한다
python -c "import io; print(sum(1 for _ in io.open('data/catalog.jsonl',encoding='utf-8')))"
#    기대: 수집분(예: 4865)  / 0이면 data/catalog.jsonl 이 없는 것 → 수집 파이프라인 산출물 확인

# 2) 재색인 (모델 다운로드 없이 빠르게 하려면 --embed hashing, 품질은 model2vec 권장)
python -m server.sync --catalog data/catalog.jsonl --notices data/notices.jsonl

# 3) 반드시 프로세스 재기동 (AppState가 부팅 시 메타를 캐시한다)
#    기존 서버 중지 후
python -m server.app --port 8100
```

**주의:** `python -m server.sync`는 카탈로그가 없거나 비어 있으면 `data/seed_catalog.jsonl`(38권)로 자동 폴백한다. 재색인 전에 반드시 입력 행 수를 확인하고, sync 로그의 `[sync] catalog=... rows=...`와 `books=`를 읽는다. 38권인데 성공으로 보이는 것이 바로 2026-10-27 사고의 함정이다.

## 4. `vectors`가 0이거나 `documents≠vectors`일 때

1. sync 로그에서 어느 배치에서 멈췄는지 확인(`books=` vs `vectors=`).
2. 디스크 여유 공간 확인 — SQLite WAL이 커지면 쓰기가 실패한다.
   ```powershell
   Get-PSDrive C | Select-Object Used,Free
   Get-ChildItem data\seoga.db* | Select-Object Name,Length
   ```
3. 임베딩 백엔드 확인 — model2vec 로드 실패 시 hashing으로 자동 폴백하므로 "조용히 품질이 달라질" 수 있다. sync 로그의 `[sync] embedder=...`를 확인하고, 의도한 백엔드가 아니면 모델 캐시/네트워크를 점검한 뒤 `--embed model2vec`로 재실행.
4. 재실행 후 다시 `/readyz` 확인. 반복 실패면 DB 파일을 백업한 뒤 재생성(오프라인 가능 시).

## 5. 재기동 후 검증 (필수)

```powershell
make smoke   # 컨테이너 기준. /healthz, /readyz, /metrics, /api/search
```

- [ ] `/readyz` 200 + `ready:true` + `documents == vectors` (컨테이너 500 / 로컬 전체 4,865)
- [ ] `/metrics`: `seoga_ready 1`, `seoga_index_documents`가 기대값과 일치, `seoga_index_vectors` 동일
- [ ] `/api/health.books`/`synced_at`이 새 값(재기동 후) — 이전 값이면 재기동이 안 된 것
- [ ] 검색 스모크: `curl.exe -G --data-urlencode "q=한강" --data-urlencode "mode=hybrid" http://127.0.0.1:8100/api/search` → `count>0`, `strategy` 채워짐
- [ ] Prometheus에서 `SeogaNotReady`/`SeogaIndexEmpty`/`SeogaIndexStale` resolve

## 6. `SeogaIndexStale`의 특수 해석 (immutable 이미지)

`seoga_index_age_seconds`는 DB meta의 `synced_at`(= **이미지 빌드 시점**) 기준이다. 컨테이너를 오래 띄워두면 24h가 지나 `SeogaIndexStale`이 발화할 수 있는데, 이는 인덱스가 깨진 것이 아니라 "배포된 아티팩트가 오래됐다"는 뜻이다.

- 확인: `seoga_build_info`의 `version`과 이미지 빌드 시각(`docker inspect --format '{{.Created}}' seoga-api:local`).
- 조치: 재빌드/재배포로 인덱스를 갱신하거나, 운영 기준상 문제없으면 알림을 acknowledge하고 정기 재배포 주기를 조정한다.
- 로컬 전체 인덱스는 실제 sync 시각이므로 24h 초과는 진짜 stale이다 → §3-B.

## 7. 재발 방지 체크

- 배포 파이프라인에서 **재색인 → 재기동 → `/readyz` 검증**을 한 단위로 묶는다(현재 CI compose-smoke가 `/healthz`·`/metrics`를 검증).
- 인덱스 변경 PR은 `/readyz` 응답의 `documents`를 PR 본문에 첨부한다.
- 카오스/점검 후에는 [chaos-drill.md](chaos-drill.md) 리셋 절차로 상태를 원복한다.
