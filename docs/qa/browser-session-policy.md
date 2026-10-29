# ego-browser 세션 위생 규칙

> 2026-10-30 정리: 에이전트 스페이스 7개가 쌓여 있었고 전부 `finish()` 처리했다.
> 원인: QA 스크립트마다 `taskSpace("<새 이름>")`으로 새 공간을 만들고 종료하지 않음.

## 규칙

1. **목표당 TaskSpace 1개** — QA/검증은 `taskSpace("seogarok-qa")` 하나를 재사용한다.
   (`taskSpace(name)`은 같은 이름이면 새로 만들지 않고 재개한다.)
2. **항상 finish** — 스크립트 끝에 `await task.finish({ keep: [] })`를 호출한다.
   성공/예외 무관하게 `try/finally`로 감싼다.
3. **페이지 재사용** — 항상 `task.page("p1")`에 `goto()`로 이동하고 `newPage()`는 쓰지 않는다.
4. **디버깅용 새 스페이스 금지** — 같은 스페이스 안에서 재시도한다.
5. **사용자 소유 스페이스는 건드리지 않는다** (`ownership: "user"`).
6. 실패로 프로세스가 죽었을 때는 `listTaskSpaces()`로 남은 `ownership: "agent"` 공간을 확인하고
   `taskSpace(id).finish({ keep: [] })`로 정리한다.

## 템플릿

```js
// _qa/ego_template.mjs
const task = await taskSpace("seogarok-qa"); // 재사용
const page = task.page("p1");
try {
  await page.goto("https://seogarok.com/", { waitUntil: "domcontentloaded", timeout: 60000 });
  // ... 작업 ...
  console.log(JSON.stringify(await page.evaluate(() => document.title)));
} finally {
  await task.finish({ keep: [] }); // 공간/페이지 정리
}
```

## 상태 확인

```js
const spaces = await listTaskSpaces();
console.log(spaces.filter((s) => s.ownership === "agent"));
```
