"""
✨ 팝업 핑 (Popup Ping) - 지금 뜨는 핫플
=========================================

## 🔐 secrets.toml 설정 방법 (구글 시트 URL)

### 1) 로컬 실행
프로젝트 폴더에 `.streamlit/secrets.toml` 파일을 만들고 아래처럼 적어요.

```toml
[connections.gsheets]
spreadsheet = "https://docs.google.com/spreadsheets/d/여기에_시트_ID/edit?usp=sharing"
```

- 시트 우측 상단 **공유 → 일반 액세스 → "링크가 있는 모든 사용자" / 역할 "뷰어"** 로 바꿔야 해요.
- 시트 첫 번째 탭(워크시트)을 읽어요. 컬럼(1행)은 아래 9개 이름 그대로!
  `장소명 | 카테고리 | 시작일 | 종료일 | 주소 | 위도 | 경도 | 참고_링크 | 이미지_URL`
- 날짜는 `2026-10-01`, `2026.10.01`, `2026/10/1` 다 OK. 시작일/종료일이 비어 있으면 "상시"로 처리해요.

### 2) Streamlit Community Cloud 배포
앱 설정 → **Settings → Secrets** 에 위 내용(`[connections.gsheets]` 포함)을 그대로 붙여넣기.
(`secrets.toml` 파일은 GitHub에 절대 올리지 마세요! `.gitignore`에 들어 있어요.)

### 3) secrets가 없으면?
`sample_data.csv` 로 **데모 모드**가 켜져요. 디자인 확인용!
"""

from __future__ import annotations

import html
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import pydeck as pdk
import streamlit as st

# ──────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="✨ 팝업 핑 (Popup Ping) - 지금 뜨는 핫플",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="collapsed",
)

COLUMNS = ["장소명", "카테고리", "시작일", "종료일", "주소", "위도", "경도", "참고_링크", "이미지_URL"]
SAMPLE_CSV = Path(__file__).parent / "sample_data.csv"
KST = timezone(timedelta(hours=9))
PAGE_SIZE = 9
SEOUL = (37.5563, 126.9910)

CAT_EMOJI = {"팝업스토어": "🛍️", "카페": "☕", "전시": "🖼️", "맛집": "🍜", "포토부스": "📸", "체험": "🎡",
             "캐릭터": "🧸", "뷰티": "💄", "패션": "👗", "푸드": "🍜", "셀럽": "🎤",
             "라이프스타일": "🏡", "키즈/반려동물": "🐶", "디지털/테크": "💻"}
STATUS_RGB = {"open": [255, 46, 147], "soon": [123, 92, 255], "ended": [160, 158, 178]}
GRADIENTS = [
    "linear-gradient(135deg,#FFD1EC,#C9B8FF)",
    "linear-gradient(135deg,#E6FFB0,#9BF0E1)",
    "linear-gradient(135deg,#FFE0B8,#FF9DC6)",
    "linear-gradient(135deg,#C9D6FF,#F0C8FF)",
]

# ──────────────────────────────────────────────
# 스타일 (HTML/CSS 주입)
# ──────────────────────────────────────────────
CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');
:root{--ink:#14141A;--pink:#FF2E93;--violet:#7B5CFF;--lime:#C6FF3D;--line:#ECE8FA;--muted:#7A778C;}
.stApp, .stMarkdown, .stMarkdown p, label, button, input{
  font-family:'Pretendard Variable',Pretendard,-apple-system,'Apple SD Gothic Neo','Noto Sans KR',sans-serif;
}
.stApp{
  background:
    radial-gradient(600px 320px at 92% -4%, rgba(255,46,147,.14), transparent 60%),
    radial-gradient(520px 320px at -8% 8%, rgba(123,92,255,.13), transparent 60%),
    #FBFAFF;
}
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"]{display:none !important;}
header[data-testid="stHeader"]{background:transparent;}
.block-container{max-width:1040px;margin:0 auto;padding:1.2rem 1rem 4rem;}

/* hero */
.hero{position:relative;overflow:hidden;padding:22px 20px 22px;border-radius:28px;color:#fff;margin-bottom:14px;
  background:linear-gradient(135deg,#FF2E93 0%,#B24BFF 62%,#7B5CFF 100%);
  box-shadow:0 14px 32px -14px rgba(255,46,147,.6);}
.hero:before{content:"";position:absolute;right:-50px;top:-50px;width:170px;height:170px;border-radius:50%;
  background:var(--lime);opacity:.55;filter:blur(26px);}
.hero .kicker{position:relative;display:inline-block;font-size:11px;font-weight:800;letter-spacing:.09em;
  background:rgba(255,255,255,.22);padding:4px 10px;border-radius:99px;}
.hero .title{position:relative;margin:10px 0 4px;font-size:36px;line-height:1.08;font-weight:900;letter-spacing:-.035em;}
.hero .title em{font-style:normal;background:var(--lime);color:var(--ink);padding:0 8px;border-radius:12px;margin-left:2px;}
.hero .sub{position:relative;margin:0;font-size:14px;font-weight:500;opacity:.94;max-width:70%;}
.sticker{position:absolute;right:16px;bottom:16px;transform:rotate(-6deg);background:var(--lime);color:var(--ink);
  font-weight:900;font-size:13px;line-height:1.25;text-align:center;padding:9px 13px;border-radius:16px;
  box-shadow:0 8px 18px -8px rgba(0,0,0,.35);}
.sticker b{display:block;font-size:22px;letter-spacing:-.02em;}

/* filters */
.st-key-filters{background:#fff;border:1px solid var(--line);border-radius:22px;padding:14px 16px;margin-bottom:14px;
  box-shadow:0 8px 22px -14px rgba(60,40,140,.3);}
.flabel{font-size:12px;font-weight:800;color:var(--muted);letter-spacing:.04em;margin:0 0 -4px;}

/* section title */
.sec{display:flex;align-items:baseline;gap:8px;margin:18px 2px 8px;font-size:19px;font-weight:900;letter-spacing:-.02em;color:var(--ink);}
.sec small{font-size:12px;font-weight:600;color:var(--muted);}

/* map */
.st-key-mapwrap{border-radius:24px;overflow:hidden;border:1px solid var(--line);box-shadow:0 14px 30px -18px rgba(60,40,140,.45);}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin:8px 4px 0;font-size:12px;font-weight:600;color:var(--muted);}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:-1px;}

/* cards */
[class*="st-key-card_"]{background:#fff;border:1px solid var(--line);border-radius:24px;padding:10px 10px 12px;gap:.55rem;
  box-shadow:0 8px 22px -16px rgba(60,40,140,.35);transition:transform .2s ease, box-shadow .2s ease;margin-bottom:6px;}
[class*="st-key-card_"]:hover{transform:translateY(-3px);box-shadow:0 18px 32px -16px rgba(255,46,147,.4);}
.pp-thumb{position:relative;aspect-ratio:4/3;border-radius:18px;background-size:cover;background-position:center;
  display:flex;align-items:center;justify-content:center;overflow:hidden;}
.pp-thumb.ended{filter:grayscale(.9) brightness(.95);}
.pp-emoji{font-size:44px;filter:drop-shadow(0 6px 10px rgba(0,0,0,.15));}
.pp-badge{position:absolute;left:10px;top:10px;font-size:11px;font-weight:800;letter-spacing:.03em;padding:5px 10px;border-radius:99px;}
.b-open{background:var(--lime);color:var(--ink);}
.b-soon{background:var(--violet);color:#fff;}
.b-ended{background:#2B2B33;color:#fff;}
.pp-cat{position:absolute;right:10px;top:10px;font-size:11px;font-weight:700;padding:5px 10px;border-radius:99px;
  background:rgba(255,255,255,.88);color:var(--ink);backdrop-filter:blur(6px);}
[class*="st-key-card_"] [data-testid="stMarkdownContainer"]{margin-bottom:0 !important;}
.pp-body{padding:2px 6px 0;}
/* 카드 높이 통일: 제목·주소는 2줄 고정(넘치면 …), 기간은 1줄 */
.pp-name{font-size:17px;font-weight:800;letter-spacing:-.02em;color:var(--ink);line-height:1.3;margin:2px 0 6px;
  min-height:2.6em;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;}
.pp-meta{font-size:13px;color:var(--muted);margin:2px 0;line-height:1.4;font-weight:500;}
.pp-period{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.pp-addr{min-height:2.8em;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;}
.pp-meta b{color:var(--ink);font-weight:700;}
[class*="st-key-card_"] a{background:var(--ink) !important;border:0 !important;border-radius:999px !important;
  color:#fff !important;font-weight:700;min-height:42px;transition:background .15s ease, transform .1s ease;}
[class*="st-key-card_"] a:hover{background:var(--pink) !important;}
[class*="st-key-card_"] a:active{transform:scale(.97);}
[class*="st-key-card_"] a p, [class*="st-key-card_"] a span{color:#fff !important;}

.count{font-size:13px;font-weight:600;color:var(--muted);margin:2px 4px 4px;}
.count b{color:var(--pink);font-weight:900;}
.empty{text-align:center;padding:42px 12px;background:#fff;border:1px dashed #D9D2F5;border-radius:24px;color:var(--muted);font-weight:600;}
.empty span{display:block;font-size:40px;margin-bottom:6px;}
.foot{text-align:center;font-size:12px;color:var(--muted);margin-top:26px;}

@media (max-width:640px){
  .block-container{padding:.6rem .8rem 3rem;}
  .hero .title{font-size:31px;}
  .hero .sub{max-width:62%;font-size:13px;}
}
</style>
"""


# ──────────────────────────────────────────────
# 데이터 로딩 & 방어 코드
# ──────────────────────────────────────────────
def today_kst() -> date:
    return datetime.now(KST).date()


def parse_date(value) -> date | None:
    """다양한 날짜 표기(2026-10-01 / 2026.10.1 / 2026년 10월 1일 / 20261001 …)를 date로. 실패하면 None."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{8}", text):
        nums = [text[:4], text[4:6], text[6:]]
    else:
        nums = re.findall(r"\d+", text)
    if len(nums) < 3:
        return None
    try:
        y, m, d = (int(n) for n in nums[:3])
        if y < 100:
            y += 2000
        return date(y, m, d)
    except ValueError:
        return None


def safe_url(value) -> str:
    """http(s) 링크만 허용 (javascript: 등 차단)."""
    text = str(value or "").strip()
    return text if re.match(r"^https?://", text, re.I) else ""


def has_sheet_secret() -> bool:
    try:
        return bool(st.secrets["connections"]["gsheets"]["spreadsheet"])
    except Exception:
        return False


class EmptySheet(Exception):
    """시트에 데이터 행이 없을 때."""


class MissingLib(Exception):
    """st-gsheets-connection 패키지가 설치되지 않았을 때."""


@st.cache_data(ttl=600, show_spinner="핫플 불러오는 중… 🔥")
def load_raw() -> tuple[pd.DataFrame, bool]:
    """구글 시트 → DataFrame. secrets가 없으면 샘플 CSV(데모 모드)."""
    if has_sheet_secret():
        try:
            from streamlit_gsheets import GSheetsConnection
        except ImportError as exc:
            raise MissingLib from exc

        conn = st.connection("gsheets", type=GSheetsConnection)
        try:
            df = conn.read(ttl=0)  # 캐싱은 위 @st.cache_data가 담당
        except pd.errors.EmptyDataError:  # 아직 아무것도 안 적힌 빈 시트
            df = pd.DataFrame(columns=COLUMNS)
        if df.dropna(how="all").empty:
            raise EmptySheet  # 예외는 캐시되지 않아서, 데이터를 넣으면 바로 반영돼요
        return df, False
    return pd.read_csv(SAMPLE_CSV, encoding="utf-8-sig"), True


def classify(start: date | None, end: date | None, today: date) -> tuple[str, str]:
    """(상태코드, 뱃지 문구)"""
    if start and today < start:
        return "soon", f"COMING · {start:%m.%d} 오픈"
    if end and today > end:
        return "ended", "ENDED"
    if end is None:
        return "open", "OPEN · 상시"
    left = (end - today).days
    return "open", "OPEN · 오늘 마지막!" if left == 0 else f"OPEN · D-{left}"


def period_text(start: date | None, end: date | None) -> str:
    if start and end:
        return f"{start:%Y.%m.%d} – {end:%Y.%m.%d}"
    if end:
        return f"~ {end:%Y.%m.%d}"
    if start:
        return f"{start:%Y.%m.%d} ~"
    return "상시 운영"


def prepare(raw: pd.DataFrame, today: date) -> pd.DataFrame:
    df = raw.copy()
    df.columns = [str(c).strip() for c in df.columns]
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None

    for col in ("장소명", "카테고리", "주소", "참고_링크", "이미지_URL"):
        df[col] = df[col].fillna("").astype(str).str.strip()
    df = df[df["장소명"] != ""].copy()
    df["카테고리"] = df["카테고리"].replace("", "기타")

    df["시작일"] = df["시작일"].map(parse_date)
    df["종료일"] = df["종료일"].map(parse_date)
    df["위도"] = pd.to_numeric(df["위도"], errors="coerce")
    df["경도"] = pd.to_numeric(df["경도"], errors="coerce")

    # 위도/경도가 뒤바뀐 경우 보정 (위도는 -90~90)
    swapped = (df["위도"].abs() > 90) & (df["경도"].abs() <= 90)
    df.loc[swapped, ["위도", "경도"]] = df.loc[swapped, ["경도", "위도"]].to_numpy()
    df.loc[(df["위도"].abs() > 90) | (df["경도"].abs() > 180), ["위도", "경도"]] = float("nan")

    status = [classify(s, e, today) for s, e in zip(df["시작일"], df["종료일"])]
    df["status"] = [s[0] for s in status]
    df["badge"] = [s[1] for s in status]
    df["period"] = [period_text(s, e) for s, e in zip(df["시작일"], df["종료일"])]

    # 정렬: 진행중(마감 임박순) → 오픈예정(빠른순) → 종료(최근순)
    far = date(2999, 12, 31)
    order = {"open": 0, "soon": 1, "ended": 2}
    df["_o"] = df["status"].map(order)
    df["_k"] = [
        (e or far).toordinal() if st_ == "open" else (s or far).toordinal() if st_ == "soon" else -(e or far).toordinal()
        for s, e, st_ in zip(df["시작일"], df["종료일"], df["status"])
    ]
    return df.sort_values(["_o", "_k"]).drop(columns=["_o", "_k"]).reset_index(drop=True)


# ──────────────────────────────────────────────
# 지도 (pydeck)
# ──────────────────────────────────────────────
def build_map(df: pd.DataFrame) -> pdk.Deck | None:
    geo = df.dropna(subset=["위도", "경도"])
    if geo.empty:
        return None

    data = pd.DataFrame(
        {
            "name": geo["장소명"],
            "cat": geo["카테고리"],
            "badge": geo["badge"],
            "end": geo["종료일"].map(lambda d: f"{d:%Y.%m.%d}까지" if d else "상시 운영"),
            "lat": geo["위도"],
            "lon": geo["경도"],
            "color": geo["status"].map(STATUS_RGB),
        }
    )

    glow = pdk.Layer(
        "ScatterplotLayer", data, pickable=True, get_position="[lon, lat]",
        get_radius=220, radius_min_pixels=20, radius_max_pixels=32,
        get_fill_color="[color[0], color[1], color[2], 70]",
    )
    pin = pdk.Layer(
        "ScatterplotLayer", data, pickable=True, auto_highlight=True, get_position="[lon, lat]",
        get_radius=70, radius_min_pixels=9, radius_max_pixels=14,
        stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=3,
        get_fill_color="[color[0], color[1], color[2], 255]",
    )

    lat_span = float(data["lat"].max() - data["lat"].min())
    lon_span = float(data["lon"].max() - data["lon"].min())
    span = max(lat_span, lon_span, 0.004)
    zoom = min(15.0, max(8.0, math.log2(400 / span)))
    view = pdk.ViewState(
        latitude=float(data["lat"].mean()), longitude=float(data["lon"].mean()), zoom=zoom, pitch=0
    )

    tooltip = {
        "html": (
            "<div style='font-family:Pretendard Variable,sans-serif;padding:2px 2px'>"
            "<div style='font-size:14px;font-weight:800;margin-bottom:3px'>{name}</div>"
            "<div style='font-size:12px;opacity:.85'>{cat} · {badge}</div>"
            "<div style='font-size:12px;margin-top:2px'>🗓 {end}</div></div>"
        ),
        "style": {
            "backgroundColor": "#14141A", "color": "#fff", "borderRadius": "14px",
            "padding": "8px 12px", "boxShadow": "0 8px 20px rgba(0,0,0,.25)",
        },
    }
    return pdk.Deck(
        layers=[glow, pin], initial_view_state=view, tooltip=tooltip,
        map_provider="carto", map_style="light",  # 토큰 필요 없는 깔끔한 라이트 지도
    )


# ──────────────────────────────────────────────
# 카드 (HTML)
# ──────────────────────────────────────────────
def css_url(value: str) -> str:
    url = safe_url(value)
    return quote(url, safe=":/?&=%#@+,;~!*$-._") if url else ""


def card_html(r: dict) -> str:
    name = html.escape(r["장소명"])
    cat = html.escape(r["카테고리"])
    addr = html.escape(r["주소"])
    emoji = CAT_EMOJI.get(r["카테고리"], "✨")
    grad = GRADIENTS[sum(map(ord, r["장소명"])) % len(GRADIENTS)]
    img = css_url(r["이미지_URL"])

    bg = f"url(\"{img}\") center/cover no-repeat, {grad}" if img else grad
    inner = "" if img else f"<span class='pp-emoji'>{emoji}</span>"
    ended = " ended" if r["status"] == "ended" else ""

    return (
        f"<div class='pp-thumb{ended}' style='background:{bg}'>{inner}"
        f"<span class='pp-badge b-{r['status']}'>{html.escape(r['badge'])}</span>"
        f"<span class='pp-cat'>{emoji} {cat}</span></div>"
        f"<div class='pp-body'><div class='pp-name' title='{name}'>{name}</div>"
        f"<div class='pp-meta pp-period'>🗓 <b>{html.escape(r['period'])}</b></div>"
        f"<div class='pp-meta pp-addr' title='{addr}'>📍 {addr or '주소 준비중'}</div></div>"
    )


def render_card(r: dict, idx: int) -> None:
    link = safe_url(r["참고_링크"])
    with st.container(key=f"card_{idx}"):
        st.markdown(card_html(r), unsafe_allow_html=True)
        if link:
            st.link_button("상세보기 →", link, use_container_width=True)
        else:  # 링크가 없으면 네이버 지도 검색으로 대체
            q = quote(f"{r['장소명']} {r['주소']}".strip())
            st.link_button("지도에서 열기 📍", f"https://map.naver.com/p/search/{q}", use_container_width=True)


# ──────────────────────────────────────────────
# 화면
# ──────────────────────────────────────────────
st.markdown(CSS, unsafe_allow_html=True)

try:
    try:
        raw, is_demo = load_raw()
    except EmptySheet:
        raw, is_demo = pd.DataFrame(columns=COLUMNS), False
        st.warning("📭 구글 시트에 팝업 데이터가 아직 없어요. 헤더 아래(2행부터)에 데이터를 붙여넣고 새로고침해 주세요!")
    except MissingLib:
        import sys

        st.error("📦 `st-gsheets-connection` 패키지가 설치되어 있지 않아요.")
        st.markdown("**로컬 실행이라면** 아래 명령을 실행한 뒤 앱을 다시 켜세요. (지금 이 앱을 돌리는 파이썬 기준이에요)")
        st.code(f'"{sys.executable}" -m pip install st-gsheets-connection', language="bash")
        st.markdown(
            "**Streamlit Cloud라면** GitHub 저장소 **맨 위(루트)** 에 `requirements.txt`가 있는지 확인하고 "
            "`st-gsheets-connection` 줄이 들어 있는지 본 뒤, 앱 메뉴에서 **Reboot** 해 주세요."
        )
        st.stop()
except Exception as exc:  # 시트 권한/URL 오류 등
    st.error("구글 시트를 불러오지 못했어요 😢 secrets.toml의 시트 URL과 공유 설정(링크가 있는 모든 사용자 - 뷰어)을 확인해 주세요.")
    with st.expander("에러 자세히 보기"):
        st.code(str(exc))
    st.stop()

today = today_kst()
df_all = prepare(raw, today)
open_count = int((df_all["status"] == "open").sum())

st.markdown(
    f"""<div class="hero"><span class="kicker">LIVE · HOTPLACE RADAR</span>
<div class="title">팝업 <em>핑</em> ✨</div>
<p class="sub">지금 뜨는 팝업·전시·카페, 놓치기 전에 핑! 찍고 가자</p>
<div class="sticker">지금 오픈중<b>{open_count}곳</b></div></div>""",
    unsafe_allow_html=True,
)

if is_demo:
    st.info("🧪 데모 모드: 아직 구글 시트가 연결되지 않아 샘플 데이터를 보여주고 있어요. (secrets.toml 설정 방법은 app.py 상단 참고)")

# 필터 (화면 상단)
categories = sorted(df_all["카테고리"].unique().tolist())
with st.container(key="filters"):
    only_open = st.toggle("🟢 지금 열려있는 팝업만 보기", value=True)
    st.markdown("<div class='flabel'>CATEGORY · 안 고르면 전체</div>", unsafe_allow_html=True)
    if hasattr(st, "pills"):
        picked = st.pills("카테고리 선택", categories, selection_mode="multi", label_visibility="collapsed") or []
    else:
        picked = st.multiselect("카테고리 선택", categories, placeholder="전체", label_visibility="collapsed")

df = df_all
if only_open:
    df = df[df["status"] == "open"]
if picked:
    df = df[df["카테고리"].isin(picked)]
df = df.reset_index(drop=True)

# 필터가 바뀌면 "더 보기" 초기화
sig = (only_open, tuple(sorted(picked)))
if st.session_state.get("sig") != sig:
    st.session_state["sig"] = sig
    st.session_state["limit"] = PAGE_SIZE

# 지도
st.markdown("<div class='sec'>🗺️ 핫플 지도 <small>핀을 탭하면 정보가 떠요</small></div>", unsafe_allow_html=True)
deck = build_map(df)
if deck is None:
    st.markdown("<div class='empty'><span>🫥</span>지도에 표시할 핫플이 없어요</div>", unsafe_allow_html=True)
else:
    with st.container(key="mapwrap"):
        st.pydeck_chart(deck, height=380)
    st.markdown(
        "<div class='legend'>"
        "<span><i style='background:#FF2E93'></i>진행중</span>"
        "<span><i style='background:#7B5CFF'></i>오픈 예정</span>"
        "<span><i style='background:#A09EB2'></i>종료</span></div>",
        unsafe_allow_html=True,
    )

# 갤러리
st.markdown("<div class='sec'>🔥 지금 핫한 곳 <small>마감 임박한 순</small></div>", unsafe_allow_html=True)
st.markdown(f"<div class='count'>총 <b>{len(df)}</b>곳 발견!</div>", unsafe_allow_html=True)

if df.empty:
    st.markdown(
        "<div class='empty'><span>🫥</span>조건에 맞는 핫플이 없어요<br>필터를 바꿔볼까요?</div>",
        unsafe_allow_html=True,
    )
else:
    limit = st.session_state.get("limit", PAGE_SIZE)
    records = df.head(limit).to_dict("records")
    for start in range(0, len(records), 3):  # 데스크톱 3열 / 모바일은 자동으로 1열
        cols = st.columns(3)
        for offset, rec in enumerate(records[start : start + 3]):
            with cols[offset]:
                render_card(rec, start + offset)
    if limit < len(df):
        if st.button(f"더 보기 ({len(df) - limit}곳 남음) 👇", use_container_width=True, type="primary"):
            st.session_state["limit"] = limit + PAGE_SIZE
            st.rerun()

st.markdown(f"<div class='foot'>기준일 {today:%Y.%m.%d} · 10분마다 자동 갱신</div>", unsafe_allow_html=True)
if st.button("🔄 데이터 새로고침"):
    st.cache_data.clear()
    st.rerun()
