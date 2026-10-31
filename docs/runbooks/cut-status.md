# 절판·품절 상태 감시

## 현실적인 범위

YES24 Open API는 책의 현재 `itemStatus`만 준다. **"곧 절판" 사전 예고 신호는 없다.**
그래서 서가록은 다음 방식으로 정직하게 다룬다.

- 감시 중인 책(내 서재·알림 대상)의 `itemStatus`를 매일 확인
- `판매중 → 품절 / 절판 / 판매중지 / 예약판매`로 **바뀐 순간** 푸시 알림
- 첫 실행은 기준선만 저장하고 알림을 보내지 않음
- 상태를 가져오지 못한 날은 이전 값을 덮어쓰지 않음

> "곧 절판"을 예측하려면 출판사·유통사의 사전 공지 데이터가 필요하다. 확보되면 같은
> 파이프라인에 소스만 추가하면 된다.

## 구성

| 구성 | 역할 |
|---|---|
| `server/status_watch.py` | 구독 watches → YES24 itemDetail 상태 확인 → 변화 저장/푸시 |
| `POST /api/push/status-cron` | cron 실행 엔드포인트 (`X-Cron-Secret`, `dry=1`, `limit=120`) |
| `.github/workflows/status-watch.yml` | 매일 04:20 KST 자동 실행 (dry-run 수동 가능) |
| GCS `status/watch.json` | 마지막으로 확인된 상태 기준선 |

## 수동 확인

```bash
curl -X POST "https://seogarok.com/api/push/status-cron?dry=1&limit=20" \
  -H "X-Cron-Secret: $YES24_API_KEY"
```

응답: `checked`, `changes`, `sent`, `failed`.

## 주의

- 외부 YES24 API 한도(429)에 걸리면 `failed`가 늘고 상태는 갱신되지 않는다.
- 알림은 사용자가 웹푸시를 켜고 해당 책을 감시 목록에 담은 경우에만 발송된다.
