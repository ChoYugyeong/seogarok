# 커스텀 도메인 연결 (Cloudflare DNS)

**이 문서가 답하는 질문**
1. `*.run.app` 말고 내 도메인으로 서비스하려면?
2. Cloudflare를 켜면 SSL/CDN이 어떻게 되나?
3. 비용은 얼마인가?

---

## 결론 먼저

| 항목 | 내용 |
|---|---|
| 도메인 | **연 1.2~2만원** (Cloudflare Registrar 원가 / Namecheap / 가비아) |
| DNS·SSL·CDN | **Cloudflare 무료 + Cloud Run 관리형 인증서** |
| Cloudflare 프록시(주황 구름) | ⚠️ **끄고(DNS only)** 써야 인증서 발급이 안전하다 |
| Cloudflare 컨테이너/Workers로 이전 | ❌ 불필요 ($5/월, 이득 없음) |

---

## 1. 도메인 구매 (1회)

- **Cloudflare Registrar**: 원가 판매(마진 0), .com 연 $10 남짓
- **Namecheap / 가비아 / 후이즈**: .kr 도메인은 국내 등록업체가 편함
- 구매 후 **네임서버를 Cloudflare로 변경** (Cloudflare → Add site → 안내된 NS 2개 입력)

## 2. 도메인 소유 확인 (Google)

Cloud Run 도메인 매핑은 소유 확인이 필요하다.

```bash
gcloud domains verify example.com
# → Search Console 화면이 열린다. DNS TXT 레코드로 확인
#   (Cloudflare DNS에 TXT 추가 → Verify)
gcloud domains list-user-verified   # 확인
```

## 3. Terraform으로 매핑 생성

```bash
cd terraform
terraform apply -var="custom_domain=seoga.example.com" \
  -var="access_token=$(gcloud auth print-access-token)"
# (CI/ADC 환경에서는 -var access_token 불필요)

terraform output -json custom_domain_records
# 예: [{"name":"seoga.example.com.","type":"CNAME","rrdata":"ghs.googlehosted.com."}]
```

## 4. Cloudflare DNS 레코드 등록

| 타입 | 이름 | 값 | 프록시 |
|---|---|---|---|
| CNAME | `seoga` | `ghs.googlehosted.com` | **DNS only (회색 구름)** |

> ⚠️ **주황 구름(프록시)을 켜면** Cloud Run의 관리형 인증서 발급(HTTP-01)이 실패할 수 있다.
> 인증서가 발급된 뒤에 프록시를 켜도 되지만, 그 시점에도 Cloudflare SSL 모드를 **Full (strict)** 로 두어야 한다.
> CDN/WAF가 꼭 필요하면 도메인 매핑 대신 **Cloudflare Worker 프록시**(무료)로 `*.run.app`을 감싸는 쪽이 안전하다.

## 5. 인증서·반영 대기

- Cloud Run이 관리형 TLS 인증서를 자동 발급한다 (보통 15분~24시간).
- 상태 확인:
  ```bash
  gcloud run domain-mappings list --region asia-northeast3
  gcloud run domain-mappings describe --domain seoga.example.com --region asia-northeast3
  ```

## 6. 검증

```bash
bash scripts/smoke.sh https://seoga.example.com
```

---

## Cloudflare 프록시(CDN/WAF)를 쓰고 싶다면

Cloud Run 도메인 매핑과 Cloudflare 프록시를 같이 쓰면 인증서 이슈가 잦다.
대안은 **Cloudflare Worker**로 `https://seoga.example.com/*` → `https://seogarok-api-*.run.app/*` 프록시:

```js
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    url.hostname = env.ORIGIN_HOST; // seogarok-api-ipampmpkwq-du.a.run.app
    return fetch(new Request(url, request));
  },
};
```

- 무료 플랜: 하루 10만 요청까지
- 단, Cloud Run이 보는 클라이언트 IP가 Cloudflare로 바뀌므로 `X-Forwarded-For` 처리 필요 (로그에는 미기록 상태라 영향 없음)

## 비용 요약

| 항목 | 비용 |
|---|---|
| 도메인 | 연 1.2~2만원 |
| Cloudflare DNS/SSL | 0원 |
| Cloud Run | 요청 시간만 (scale-to-zero) |
| Cloud Run 도메인 매핑 | **무료** |
