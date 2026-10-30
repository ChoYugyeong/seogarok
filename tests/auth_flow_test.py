# -*- coding: utf-8 -*-
"""구글 로그인 없이 검증하는 인증/서재 동기화 로직 테스트 (로컬 저장소 사용)."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("REPORTS_BUCKET", None)
os.environ["PUSH_CACHE_DIR"] = tempfile.mkdtemp()

from server import auth  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ((" | " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


st = auth.make_state()
gsc_state = "gsc." + auth.make_state()
check("gsc state validation", auth.check_state(gsc_state, gsc_state) and gsc_state.startswith("gsc."))
check("state validation", auth.check_state(st, st) and not auth.check_state(st, st + "x") and not auth.check_state("a.b", "a.b"))

info = {"sub": "test-sub-123", "email": "test@example.com", "name": "테스터", "email_verified": True, "picture": "https://x/y.png"}
user = auth.upsert_user(info)
check("upsert user", user["sub"] == "test-sub-123" and user["email"] == "test@example.com")

sid = auth.new_session(user)
cookie = f"{auth.SESSION_COOKIE}={sid}"
me = auth.current_user(cookie)
check("session lookup", me and me["sub"] == "test-sub-123")

shelf = auth.put_shelf("test-sub-123", {"want": ["yes24:1", "yes24:2"], "reading": ["yes24:3"], "done": [], "pushLeads": [7, 3, 1], "alerts": {"yes24:1": 3}})
check("put shelf", shelf["want"] == ["yes24:1", "yes24:2"] and shelf["pushLeads"] == [7, 3, 1])

merged = auth.merge_shelf("test-sub-123", {"want": ["yes24:2", "yes24:9"], "reading": [], "done": ["yes24:8"]})
check("merge shelf", "yes24:9" in merged["want"] and "yes24:8" in merged["done"])

got = auth.get_shelf("test-sub-123")
check("get shelf", got["reading"] == ["yes24:3"] and got["alerts"].get("yes24:1") == 3)

auth.logout(cookie)
check("logout invalidates", auth.current_user(cookie) is None)

auth.delete_account(user)
check("account deleted", auth.get_shelf("test-sub-123")["want"] == [] and auth.current_user(cookie) is None)

print(f"\nauth flow: {len(fails)} failed")
sys.exit(1 if fails else 0)
