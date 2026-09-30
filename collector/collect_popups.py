"""
팝업 핑 - 팝업스토어 자동 수집기 (매주 월요일 실행)

수집처: 팝가(popga.co.kr) 사이트맵 → 각 팝업 상세 페이지의 JSON-LD(Event) 정보
        (이름·기간·주소·위도/경도·이미지 가 다 들어 있어서 지오코딩 API가 필요 없어요)

보관 규칙 (실행일 = 오늘 기준)
  1) 진행중이거나 오픈 예정인데 시작일이 "다음 달 말일"까지인 팝업  → 보관
  2) 이미 종료됐지만 시작일이 "지난달"인 팝업                         → 종료 건으로 보관
  3) 그 외(더 오래된 종료 건, 먼 미래 예정 건)                          → 시트에서 삭제

환경변수
  SHEET_ID                  구글 시트 ID (필수, DRY_RUN이면 불필요)
  GOOGLE_SERVICE_ACCOUNT_JSON  서비스 계정 키(JSON 문자열) (필수, DRY_RUN이면 불필요)
  DRY_RUN=1                 시트에 쓰지 않고 collector/out.csv 로만 저장
  REGION_PREFIXES           수집할 지역 접두어, 쉼표 구분 (기본 "서울")
  LOOKBACK_DAYS             사이트맵 lastmod 기준 조회 범위 (기본 150일)
  EXCLUDE_CATEGORIES        제외할 팝가 카테고리 키워드 (기본 "엔터테인먼트,공연,연극,뮤지컬,콘서트")
  MAX_FETCH                 (테스트용) 상세 페이지 최대 조회 수
  CACHE_PATH                상세 페이지 파싱 캐시 (기본 collector/cache.json)
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

BASE = "https://popga.co.kr"
UA = "PopupPingBot/1.0 (personal hobby project; weekly crawl; https://github.com/verb0448/popup-ping)"
KST = timezone(timedelta(hours=9))
COLUMNS = ["장소명", "카테고리", "시작일", "종료일", "주소", "위도", "경도", "참고_링크", "이미지_URL"]

HERE = Path(__file__).parent
CACHE_PATH = Path(os.getenv("CACHE_PATH", HERE / "cache.json"))
REGIONS = tuple(s.strip() for s in os.getenv("REGION_PREFIXES", "서울").split(",") if s.strip())
EXCLUDE_CATEGORIES = tuple(
    s.strip() for s in os.getenv("EXCLUDE_CATEGORIES", "엔터테인먼트,공연,연극,뮤지컬,콘서트").split(",") if s.strip()
)
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "150"))
MAX_FETCH = int(os.getenv("MAX_FETCH", "0")) or None
WORKERS = 4
DELAY = 0.15  # 요청 사이 간격(초) - 사이트에 부담 주지 않기

# 앱에서 쓰는 카테고리로 정리 (앞에 있을수록 우선)
CATEGORY_RULES = [
    ("뷰티", ("뷰티", "화장품", "코스메틱")),
    ("패션", ("패션", "의류", "슈즈", "잡화", "스포츠")),
    ("카페", ("카페", "디저트", "음료", "베이커리")),
    ("푸드", ("푸드", "식품", "F&B", "음식")),
    ("전시", ("전시", "아트", "미술", "갤러리")),
    ("셀럽", ("셀럽", "연예인")),
    ("체험", ("체험", "게임", "테마파크", "이벤트")),
    ("캐릭터", ("캐릭터", "애니", "웹툰", "만화")),
]


# ──────────────────────────────────────────────
# 날짜 유틸
# ──────────────────────────────────────────────
def parse_date(value) -> date | None:
    text = str(value or "").strip()
    nums = re.findall(r"\d+", text)
    if len(nums) < 3:
        return None
    try:
        y, m, d = (int(n) for n in nums[:3])
        return date(y + 2000 if y < 100 else y, m, d)
    except ValueError:
        return None


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return date(y, m + 1, 1)


def keep_window(today: date) -> tuple[date, date]:
    """(지난달 1일, 다음 달 말일)"""
    last_month_start = add_months(month_start(today), -1)
    next_month_end = add_months(month_start(today), 2) - timedelta(days=1)
    return last_month_start, next_month_end


def should_keep(start: date | None, end: date | None, today: date) -> bool:
    """보관 규칙. 날짜를 읽을 수 없는 행은 (수동 입력 보호를 위해) 보관."""
    if start is None and end is None:
        return True
    last_month_start, next_month_end = keep_window(today)
    if end is None or end >= today:  # 진행중 / 예정 / 종료일 미정
        return start is None or start <= next_month_end
    # 이미 종료 → 시작일이 지난달인 것만
    return start is not None and month_start(start) == last_month_start


# ──────────────────────────────────────────────
# 수집
# ──────────────────────────────────────────────
session = requests.Session()
session.headers["User-Agent"] = UA


def http_get(url: str, tries: int = 4) -> str | None:
    for i in range(tries):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                r.encoding = "utf-8"
                return r.text
            if r.status_code in (404, 410):
                return None
        except requests.RequestException:
            pass
        time.sleep(1.5 * (i + 1))
    return None


def list_candidates(today: date) -> list[tuple[str, str]]:
    """사이트맵에서 (팝업ID, lastmod) 목록. lastmod가 최근인 것만."""
    index = http_get(f"{BASE}/sitemap.xml")
    if not index:
        raise RuntimeError("sitemap.xml 을 불러오지 못했어요")
    cutoff = datetime.combine(today, datetime.min.time(), tzinfo=KST) - timedelta(days=LOOKBACK_DAYS)
    out: dict[str, str] = {}
    for loc in re.findall(r"<loc>([^<]*sitemap/\d+\.xml)</loc>", index):
        xml = http_get(loc)
        if not xml:
            continue
        for pid, lastmod in re.findall(r"<loc>%s/popup/(\d+)</loc>\s*<lastmod>([^<]+)</lastmod>" % re.escape(BASE), xml):
            try:
                ts = datetime.fromisoformat(lastmod.replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts >= cutoff:
                out[pid] = lastmod
    return sorted(out.items(), key=lambda kv: int(kv[0]), reverse=True)


def pick_category(names: list[str]) -> str:
    for label, keywords in CATEGORY_RULES:
        if any(k in n for n in names for k in keywords):
            return label
    return names[0] if names else "기타"


def parse_detail(pid: str, page: str) -> dict | None:
    """상세 페이지 → 시트 한 행(dict). 대상 지역이 아니거나 정보가 부족하면 None."""
    ld = None
    for raw in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "Event":
                ld = item
                break
        if ld:
            break
    if not ld:
        return None

    place = ld.get("location") or {}
    addr = (place.get("address") or {}).get("streetAddress") or ""
    geo = place.get("geo") or {}
    if REGIONS and not addr.startswith(REGIONS):
        return None
    try:
        lat, lng = float(geo["latitude"]), float(geo["longitude"])
    except (KeyError, TypeError, ValueError):
        lat = lng = None

    m = re.search(r'\\"categories\\":\[(.*?)\]', page)
    cats = [
        json.loads(f'"{n}"')  # & 같은 이스케이프 복원 (F&B → F&B)
        for n in re.findall(r'\\"name\\":\\"(.*?)\\"', m.group(1))
    ] if m else []
    if any(x in c for c in cats for x in EXCLUDE_CATEGORIES):  # 공연·콘서트 등은 팝업이 아니라서 제외
        return None
    images = ld.get("image") or []
    image = images[0] if isinstance(images, list) and images else (images if isinstance(images, str) else "")

    start, end = parse_date(ld.get("startDate")), parse_date(ld.get("endDate"))
    if not ld.get("name") or (start is None and end is None):
        return None
    return {
        "장소명": str(ld["name"]).strip(),
        "카테고리": pick_category(cats),
        "시작일": start.isoformat() if start else "",
        "종료일": end.isoformat() if end else "",
        "주소": addr,
        "위도": lat if lat is not None else "",
        "경도": lng if lng is not None else "",
        "참고_링크": f"{BASE}/popup/{pid}",
        "이미지_URL": image,
    }


def fetch_one(item: tuple[str, str]) -> tuple[str, str, dict | None, bool]:
    pid, lastmod = item
    time.sleep(DELAY)
    page = http_get(f"{BASE}/popup/{pid}")
    if page is None:
        return pid, lastmod, None, False  # 실패(캐시 안 함)
    return pid, lastmod, parse_detail(pid, page), True


def load_cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def collect(today: date) -> list[dict]:
    candidates = list_candidates(today)
    print(f"사이트맵 후보: {len(candidates)}건 (최근 {LOOKBACK_DAYS}일 내 갱신)")
    cache = load_cache()
    todo = [c for c in candidates if cache.get(c[0], {}).get("lastmod") != c[1]]
    if MAX_FETCH:
        todo = todo[:MAX_FETCH]
    print(f"상세 페이지 조회 필요: {len(todo)}건 (나머지는 캐시 사용)")

    failed = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for n, (pid, lastmod, rec, ok) in enumerate(pool.map(fetch_one, todo), 1):
            if ok:
                cache[pid] = {"lastmod": lastmod, "record": rec}
            else:
                failed += 1
            if n % 200 == 0:
                print(f"  … {n}/{len(todo)}")
    if todo and failed / len(todo) > 0.2:
        raise RuntimeError(f"상세 페이지 조회 실패가 너무 많아요 ({failed}/{len(todo)}) - 시트를 건드리지 않고 종료합니다")

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    live = {pid for pid, _ in candidates}
    cache = {pid: v for pid, v in cache.items() if pid in live}  # 캐시 무한 증가 방지
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return [v["record"] for v in cache.values() if v.get("record")]


# ──────────────────────────────────────────────
# 시트 병합 & 쓰기
# ──────────────────────────────────────────────
def open_worksheet():
    import gspread
    from google.oauth2.service_account import Credentials

    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds).open_by_key(os.environ["SHEET_ID"]).sheet1


def sort_key(rec: dict, today: date):
    start, end = parse_date(rec["시작일"]), parse_date(rec["종료일"])
    far = date(2999, 12, 31)
    if start and start > today:
        return (1, start.toordinal())
    if end and end < today:
        return (2, -end.toordinal())
    return (0, (end or far).toordinal())


def merge(collected: list[dict], existing: list[dict], today: date) -> list[dict]:
    """새로 수집한 것 + 기존 시트 행(수동 입력 포함)을 링크 기준으로 합치고 보관 규칙 적용."""
    merged: dict[str, dict] = {}
    for rec in existing:  # 기존 행 먼저, 같은 링크면 새 수집본이 덮어씀
        key = str(rec.get("참고_링크") or "").strip() or f"row:{rec.get('장소명')}"
        merged[key] = {c: rec.get(c, "") for c in COLUMNS}
    for rec in collected:
        merged[rec["참고_링크"]] = rec
    kept = [
        r for r in merged.values()
        if should_keep(parse_date(r["시작일"]), parse_date(r["종료일"]), today)
    ]
    return sorted(kept, key=lambda r: sort_key(r, today))


def main() -> int:
    today = datetime.now(KST).date()
    dry = os.getenv("DRY_RUN") == "1"
    lm, nme = keep_window(today)
    print(f"기준일 {today} · 보관 범위: 종료건은 {lm:%Y-%m} 시작분만, 예정건은 {nme} 시작분까지 · 지역 {REGIONS}")

    collected = [r for r in collect(today) if should_keep(parse_date(r["시작일"]), parse_date(r["종료일"]), today)]
    print(f"보관 규칙을 통과한 신규 수집: {len(collected)}건")
    if len(collected) < 3:
        print("수집 결과가 너무 적어서 시트를 건드리지 않고 종료합니다.", file=sys.stderr)
        return 1

    existing: list[dict] = []
    ws = None
    if not dry:
        ws = open_worksheet()
        existing = ws.get_all_records()  # 헤더 기준 dict 리스트

    rows = merge(collected, existing, today)
    counts = {"진행중": 0, "예정": 0, "종료": 0}
    for r in rows:
        k = sort_key(r, today)[0]
        counts["진행중" if k == 0 else "예정" if k == 1 else "종료"] += 1
    print(f"최종 {len(rows)}건 → {counts}")

    values = [COLUMNS] + [[r[c] for c in COLUMNS] for r in rows]
    if dry:
        out = HERE / "out.csv"
        with out.open("w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows(values)
        print(f"DRY_RUN: {out} 에 저장했어요 (시트는 그대로)")
        return 0

    # 값을 먼저 쓰고, 남는 아래쪽 행만 지움 (중간에 실패해도 데이터가 통째로 사라지지 않게)
    ws.update(values=values, range_name="A1", value_input_option="RAW")
    ws.batch_clear([f"A{len(values) + 1}:I"])
    print("구글 시트 업데이트 완료 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
