// k6 부하테스트: 검색 API에 SLO 임계값을 건다.
//   docker compose --profile load run --rm k6 run /scripts/search.js
//   로컬: BASE_URL=http://127.0.0.1:8100 k6 run loadtest/search.js
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = __ENV.BASE_URL || 'http://127.0.0.1:8100';

const QUERIES = [
  '한강', '채식주의자', '김초엽', '우주 과학 소설', 'SF 소설',
  '따뜻한 힐링 소설', '에세이', '인공지능과 미래', '역사 교양', 'shakespeare',
];

export const options = {
  scenarios: {
    search_ramp: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '10s', target: 10 },   // warm-up
        { duration: '30s', target: 25 },   // steady
        { duration: '10s', target: 0 },
      ],
      gracefulRampDown: '5s',
    },
  },
  thresholds: {
    // SLO: 검색 API p95 < 300ms, 에러율 < 1%
    'http_req_failed': ['rate<0.01'],
    'http_req_duration{route:search}': ['p(95)<300', 'p(99)<800'],
    'checks': ['rate>0.99'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(50)', 'p(95)', 'p(99)', 'max'],
};

export default function () {
  const q = QUERIES[Math.floor(Math.random() * QUERIES.length)];
  const res = http.get(
    `${BASE}/api/search?q=${encodeURIComponent(q)}&limit=12`,
    { tags: { route: 'search' } },
  );

  check(res, {
    'status 200': (r) => r.status === 200,
    'has results': (r) => {
      try {
        return JSON.parse(r.body).count >= 0;
      } catch (e) {
        return false;
      }
    },
    'under 300ms': (r) => r.timings.duration < 300,
  });

  if (__VU % 10 === 0) {
    http.get(`${BASE}/healthz`, { tags: { route: 'healthz' } });
  }
  sleep(Math.random() * 0.3 + 0.1);
}
