# 런북: 검색 지연 (`SeogaSearchLatencyP95High`)

> **이 문서가 답하는 질문:** ① 검색 p95가 300ms를 넘을 때 어느 단계(키워드/벡터/융합)가 원인인지 어떻게 3분 안에 가르나? ② 카오스 주입과 실제 성능 저하를 어떻게 구분하나? ③ 어떤 순서로 완화하고, 언제 확장을 결정하나?

관련 알림: `SeogaSearchLatencyP95High`(`route="/api/search"` 5분 p95 > 0.3s, 2m). 관련 문서: [SRE.md](../SRE.md) §9, [chaos-drill.md](chaos-drill.md), [index-stale.md](index-stale.md).

---

## 1. 증상

- Prometheus `/alerts`에 `SeogaSearchLatencyP95High` firing.
- Grafana **Latency p50/p95/p99 (search)** 패널 상승, 사용자 체감 검색 지연.
- k6 실행 중이면 `p(95)<300` threshold 실패.
- API 액세스 로그(JSON)의 `dur_ms`가 이전보다 커짐.

## 2. 분류: 3분 안에 원인 후보 좁히기

```powershell
# 1) 카오스가 켜져 있는가? (게임데이 중이면 정상 동작)
curl.exe -s http://127.0.0.1:8100/api/_chaos
#   {"enabled":true,"latency_ms":0,"error_rate":0} → 주입 없음
#   {"enabled":true,"latency_ms":400,"error_rate":0.3} → 게임데이 진행 중 → §6 리셋
#   {"error":"chaos_disabled",...} 404 → 이 인스턴스는 주입 불가(운영 프로필)

# 2) 단계별 평균 소요 (어디가 느린지)
#    PromQL:
#    sum(rate(seoga_search_stage_seconds_sum[5m])) by (stage)
#      / sum(rate(seoga_search_stage_seconds_count[5m])) by (stage)

# 3) 전략/모드 분포 (exact-first가 늘면 벡터 경로를 덜 타므로 빨라야 정상)
#    sum by (mode, strategy) (rate(seoga_search_queries_total[5m]))

# 4) 인덱스 규모/백엔드
#    seoga_index_documents, seoga_index_vectors, seoga_db_size_bytes
#    seoga_build_info{vector="sqlite-vec"}   (numpy 폴백이면 느릴 수 있음)

# 5) 컨테이너 리소스
docker stats --no-stream seoga-api
```

## 3. 진단 매트릭스

| 관찰 | 유력 원인 | 다음 조치 |
|---|---|---|
| `latency_ms` > 0 | **카오스 주입**(게임데이) | §6 리셋 후 재측정 |
| `vector` stage만 상승 | 벡터 KNN 비용 / 백엔드 폴백 | §4-A |
| `keyword` stage 상승 | FTS5 MATCH 폭증 / DB 락 | §4-B |
| `fuse` stage 상승 | 후보 수 폭증(limit × 4 확대) | §4-C |
| 모든 stage 상승 + CPU 100% | 호스트/컨테이너 리소스 포화 | §5 |
| `seoga_build_info{vector}`가 `numpy` | sqlite-vec 미로드 → brute-force | §4-A |
| `seoga_index_vectors` 급증 | 인덱스 확장에 따른 exact KNN 선형 증가 | §5 |
| 지연 + 5xx 동시 | API 자체 문제일 수 있음 | [api-down.md](api-down.md) |

## 4. 원인별 확인

### A. 벡터 경로 (가장 흔함)
- `seoga_build_info{vector="numpy"}`면 sqlite-vec 로드 실패로 numpy brute-force 중이다. 이 경우 벡터 수에 비례해 급격히 느려진다.
- KNN은 exact라 벡터 수가 늘면 선형 증가한다(측정: 1k 0.94ms / 10k 10.1ms / 50k 48.6ms). `seoga_index_vectors`와 DB 크기(`seoga_db_size_bytes`)를 기준선과 비교한다.
- 조치: 정상 백엔드(`sqlite-vec`)인지 확인, 아니면 이미지 재빌드. 인덱스가 의도보다 크면 재색인 범위 확인([index-stale.md](index-stale.md)).

### B. 키워드 경로
- `keyword` stage가 튀면 FTS5 MATCH 비용이다. `seoga_search_queries_total`에서 `mode="keyword"` 증가 여부 확인.
- DB 락: 서빙 중 쓰기 작업(수동 sync 등)이 겹쳤는지 확인. 서빙 인스턴스와 별도 프로세스에서 `python -m server.sync`를 동시에 돌리지 않는다.
- 조치: 진행 중인 sync/배치를 중단하고 재측정.

### C. 융합 경로
- `fuse`는 후보 수에 비례한다. 벡터 후보가 비정상적으로 많으면 `candidates.vector`가 커진다. `/api/search?q=...&debug=1`로 후보 수를 확인할 수 있다.
- 조치: 벡터 컷오프/백엔드 상태 확인(§4-A).

## 5. 리소스·용량

```powershell
docker stats --no-stream seoga-api
docker compose logs --tail=100 api | Select-String "dur_ms"
```

- API CPU가 100%에 붙으면 지연은 포화의 증상이다. 현재 API는 **단일 프로세스 + 임베딩 인코딩 락(`_lock_encode`)** 구조라 동시성이 늘면 큐잉이 발생한다.
- 완화 우선순위: ① 카오스 리셋 ② 다른 무거운 작업(k6/재색인) 중단 ③ 인스턴스 재기동 ④ 수평 확장(복제 추가) 또는 벡터 백엔드 교체 검토.
- 지속적으로 p95가 SLO를 넘고 인덱스가 커지는 추세면, exact KNN → IVF/HNSW(pgvector, Qdrant) 전환을 검토한다([SRE.md](../SRE.md) §10).

## 6. 카오스 리셋 (게임데이 중이었다면)

```powershell
make reset-chaos
# make가 없거나 스크립트 실행 정책 이슈가 있으면 curl.exe 로 동일하게
curl.exe -s -X POST http://127.0.0.1:8100/api/_chaos -H "Content-Type: application/json" -d '{"latency_ms":0,"error_rate":0}'
```

리셋 후 `GET /api/_chaos`가 `latency_ms:0, error_rate:0`인지 확인한다.

## 7. 복구 검증

- [ ] `SeogaSearchLatencyP95High` resolve, p95 < 300ms가 10분 이상 유지
- [ ] `make smoke` 통과
- [ ] Grafana 지연 패널이 기준선(§9.1의 로컬 인프로세스 값이 아니라 **직전 정상 HTTP p95**)으로 복귀
- [ ] 실패율(`http_req_failed`)이 정상 범위
- [ ] k6 `make load` 시 thresholds 통과 — 2026-10-27 실측: 25 VU × 50s, p95 **4.10ms**, 실패율 **0.00%**, checks **100%** ([SRE.md](../SRE.md) §9.3)

## 8. 후속

- SLO 버짓을 소모했으면 포스트모템 작성: [TEMPLATE.md](../postmortem/TEMPLATE.md).
- 재발 시나리오(벡터 증가/리소스 부족)가 확인되면 [SRE.md](../SRE.md) §12 "실측"에 수치와 함께 기록한다.
- 게임데이였다면 [chaos-drill.md](chaos-drill.md)의 기록 표에 남긴다.
