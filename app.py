import copy
import html
import json
import re
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

# ======================================================================
# 기본 데이터 / 상수
# ======================================================================
DEFAULT_TITLE = "기분 좋은 여행의 시작"
KST = ZoneInfo("Asia/Seoul")
WEEKDAYS = "월화수목금토일"

DEFAULT_SPOTS = [
    dict(id="home", day=1, name="집", time="종일",
         lat=37.3840, lon=126.6470, desc="송도 더샵 그린애비뉴 7단지", tip="여행 시작"),
    dict(id="airport", day=1, name="인천국제공항", time="종일",
         lat=37.4490, lon=126.4510, desc="제1여객터미널", tip="떠날 준비 완료?"),
]

# 지도 컴포넌트 (map_component/index.html)
MAP_COMPONENT = components.declare_component(
    "trip_map", path=str(Path(__file__).parent / "map_component")
)
SORT_COMPONENT = components.declare_component(
    "trip_sort", path=str(Path(__file__).parent / "sort_component")
)

# 구글 장소 검색 기준 (춘천 시내 중심, 반경 30km)
CHUNCHEON_CENTER = (37.8813, 127.7298)
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"

TIME_SLOTS = [f"{h:02d}:{m:02d}" for h in range(5, 24) for m in (0, 30)]
DAY_PALETTE = [("#EFF6FF", "#60A5FA"), ("#FFF7ED", "#FB923C"), ("#F0FDF4", "#4ADE80"),
               ("#FAF5FF", "#C084FC"), ("#FEF2F2", "#F87171"), ("#FEFCE8", "#FACC15")]

# 당겨서 새로고침: 부모 페이지(스트림릿)의 터치를 감시. 지도 iframe의 터치는 메시지로 전달받음.
PTR_JS = """
<script>
(function () {
  var top = window.parent;
  try {
    if (top.__tripPTR) return;
    top.__tripPTR = true;
    var doc = top.document;
    var startY = null, armed = false;
    function atTop() {
      if (doc.querySelector('[role="dialog"]')) return false; // 대화상자 안에서의 스크롤은 제외
      var els = [doc.scrollingElement, doc.body,
        doc.querySelector('[data-testid="stAppViewContainer"]'),
        doc.querySelector('[data-testid="stMain"]'),
        doc.querySelector('[data-testid="stAppViewBlockContainer"]')];
      for (var i = 0; i < els.length; i++) {
        if (els[i] && els[i].scrollTop > 0) return false;
      }
      return top.scrollY <= 0;
    }
    function start(y) { startY = y; armed = atTop(); }
    function move(y) {
      if (startY === null || !armed || y === null) return;
      if (y - startY > 90) { armed = false; top.location.reload(); }
    }
    function end() { startY = null; armed = false; }
    doc.addEventListener('touchstart', function (e) { start(e.touches[0].clientY); }, {passive: true});
    doc.addEventListener('touchmove', function (e) { move(e.touches[0].clientY); }, {passive: true});
    doc.addEventListener('touchend', end, {passive: true});
    top.addEventListener('message', function (e) {
      var d = e.data;
      if (!d) return;
      if (d.type === 'trip-scroll-map') {
        var mb = doc.querySelector('.st-key-mapbox');
        if (mb) { mb.style.scrollMarginTop = '4.5rem'; mb.scrollIntoView({behavior: 'smooth', block: 'start'}); }
        return;
      }
      if (d.type !== 'trip-touch') return;
      if (d.phase === 'start') start(d.y);
      else if (d.phase === 'move') move(d.y);
      else end();
    });
  } catch (err) { /* 부모 페이지 접근이 막히면 당겨서 새로고침만 비활성 */ }
})();
</script>
"""


# ======================================================================
# 시간 / 일차 유틸
# ======================================================================
def time_options(extra=None, with_all_day=False):
    opts = (["종일"] if with_all_day else []) + TIME_SLOTS
    if extra and extra not in opts:
        opts.append(extra)
    return opts


def pick_index(opts, val):
    return opts.index(val) if val in opts else 0


def split_time(t):
    t = (t or "").strip()
    if "~" in t:
        a, b = [x.strip() for x in t.split("~", 1)]
        return a or "09:00", b or "10:00"
    if t in ("", "종일"):
        return "종일", "10:00"
    return t, "10:00"


def make_time(start, end):
    return "종일" if start == "종일" else f"{start}~{end}"


def sort_spots() -> None:
    """일차 → 종일 먼저 → 시작 시간 순으로 정렬"""
    def _key(s):
        start = split_time(s.get("time", ""))[0]
        return (int(s.get("day", 1)), 0 if start == "종일" else 1, start)
    st.session_state.spots_data.sort(key=_key)


def day_label(d: int) -> str:
    """일차 표시: 여행 시작일이 있으면 날짜도 함께 표시"""
    base = f"Day {d}"
    start = st.session_state.get("trip_start_input")
    if isinstance(start, date):
        dt = start + timedelta(days=d - 1)
        base += f" · {dt.month}/{dt.day}"
    return base


def _mins(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _hhmm(v: int) -> str:
    return f"{v // 60:02d}:{v % 60:02d}"


def _is_timed(s: dict) -> bool:
    return bool(s.get("time")) and split_time(s["time"])[0] != "종일"


def apply_reorder(order: list, moved: str) -> None:
    """드래그로 바뀐 순서 적용: 옮긴 일정은 앞뒤 일정 사이 시간(a 규칙)으로, Day는 자리에 맞춤.
    종일 일정은 시간을 바꾸지 않음."""
    ss = st.session_state
    by_id = {s["id"]: s for s in ss.spots_data}
    if set(order) != set(by_id) or moved not in by_id:
        return
    new = [by_id[i] for i in order]
    idx = order.index(moved)
    m = by_id[moved]
    prev = new[idx - 1] if idx > 0 else None
    nxt = new[idx + 1] if idx + 1 < len(new) else None

    if _is_timed(m):
        a, b = split_time(m["time"])
        dur = max(_mins(b) - _mins(a), 30)
        p_end = split_time(prev["time"])[1] if prev and _is_timed(prev) else None
        n_start = split_time(nxt["time"])[0] if nxt and _is_timed(nxt) else None
        if p_end and n_start and _mins(n_start) > _mins(p_end):
            start, end = p_end, n_start                       # 앞 끝 ~ 뒤 시작 사이
        elif p_end:
            start = p_end
            end = _hhmm(min(_mins(start) + dur, 23 * 60 + 30))
        elif n_start:
            end = n_start
            start = _hhmm(max(_mins(end) - dur, 5 * 60))
        else:
            start, end = a, b
        m["time"] = f"{start}~{end}"

    if nxt:
        m["day"] = int(nxt["day"])
    elif prev:
        m["day"] = int(prev["day"])

    ss.spots_data = new  # 드래그한 순서를 그대로 유지 (자동 정렬하지 않음)
    if ss.synced_json is not None and push_remote(build_payload()):
        ss.synced_json = canon(build_payload())


def day_color_css() -> str:
    rules = []
    for d in sorted({int(s["day"]) for s in st.session_state.spots_data}):
        bg, bd = DAY_PALETTE[(max(d, 1) - 1) % len(DAY_PALETTE)]
        sel = f'[class*="st-key-card_d{d}_"]'
        rules.append(f'{sel}, {sel} [data-testid="stVerticalBlockBorderWrapper"] '
                     f'{{background:{bg} !important; border-color:{bd} !important;}}')
    return "<style>" + "\n".join(rules) + "</style>"


# ======================================================================
# 저장 / 불러오기 (세션 상태 <-> dict)
# ======================================================================
def build_payload() -> dict:
    ss = st.session_state
    start = ss.get("trip_start_input")
    return {
        "version": 1,
        "page_title": ss.get("trip_title", DEFAULT_TITLE),
        "start_date": start.isoformat() if isinstance(start, date) else None,
        "saved_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "spots": [{**s, "done": bool(ss.done.get(s["id"], False))} for s in ss.spots_data],
    }


def apply_payload(data: dict) -> None:
    ss = st.session_state
    spots, dones, used = [], {}, set()
    for i, s in enumerate(data["spots"]):
        try:
            sid = str(s.get("id") or f"spot_{i + 1}")
            while sid in used:
                sid = f"{sid}_{uuid4().hex[:4]}"
            used.add(sid)
            spots.append(dict(
                id=sid, day=max(1, int(s.get("day", 1))), name=str(s["name"]), time=str(s.get("time", "")),
                lat=float(s["lat"]), lon=float(s["lon"]), desc=str(s.get("desc", "")), tip=str(s.get("tip", "")),
            ))
            dones[sid] = bool(s.get("done", False))
        except (KeyError, TypeError, ValueError):
            continue
    if not spots:
        raise ValueError("no valid spots")

    ss.spots_data = spots
    ss.done = {s["id"]: dones.get(s["id"], False) for s in spots}
    ss.editing_flags = {s["id"]: False for s in spots}
    # 체크박스/수정 폼의 이전 위젯 상태 제거 (새 값이 반영되도록)
    for k in [k for k in ss.keys() if str(k).startswith(("chk_", "inp_"))]:
        del ss[k]
    ss.trip_title = str(data.get("page_title") or DEFAULT_TITLE)
    ss["title_input"] = ss.trip_title
    try:
        if data.get("start_date"):
            ss["trip_start_input"] = date.fromisoformat(str(data["start_date"]))
    except ValueError:
        pass


def save_filename() -> str:
    name = str(st.session_state.get("save_name", "")).strip() or "chuncheon_trip"
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    return name if name.lower().endswith(".json") else f"{name}.json"


def load_from_upload() -> None:
    f = st.session_state.get("upload_file")
    if f is None:
        st.session_state.msg = "⚠️ 불러올 파일을 먼저 선택해 주세요."
        return
    try:
        apply_payload(json.loads(f.getvalue().decode("utf-8")))
        st.session_state.msg = "⬆️ 파일에서 일정을 불러왔어요."
    except Exception:
        st.session_state.msg = "⚠️ 올바른 일정 파일이 아니에요."
    st.session_state.reload_now = True  # 대화상자를 닫고 화면을 새로 그림


# ---- 콜백 ----
def set_done(sid: str, key: str) -> None:
    st.session_state.done[sid] = bool(st.session_state.get(key, False))


def set_focus(lat: float, lon: float) -> None:
    st.session_state.focus = {"lat": lat, "lon": lon, "nonce": uuid4().hex}


def delete_spot(sid: str) -> None:
    ss = st.session_state
    ss.spots_data = [s for s in ss.spots_data if s["id"] != sid]
    ss.done.pop(sid, None)
    ss.editing_flags.pop(sid, None)
    for k in [k for k in ss.keys() if str(k).startswith(f"chk_{sid}_") or
              (str(k).startswith("inp_") and str(k).endswith(f"_{sid}"))]:
        del ss[k]


def sync_title() -> None:
    st.session_state.trip_title = st.session_state.get("title_input", DEFAULT_TITLE)


# ======================================================================
# 구글 장소 검색 (Places API (New) — Secrets에 GOOGLE_PLACES_API_KEY 필요)
# ======================================================================
def search_places(query: str) -> list:
    try:
        key = str(st.secrets["GOOGLE_PLACES_API_KEY"]).strip()
    except Exception:
        key = ""
    if not key:
        raise RuntimeError("구글 검색을 쓰려면 Streamlit Secrets에 GOOGLE_PLACES_API_KEY를 넣어 주세요.")
    q = query if "춘천" in query else f"춘천 {query}"
    body = {
        "textQuery": q, "languageCode": "ko", "regionCode": "KR", "maxResultCount": 8,
        "locationBias": {"circle": {"center": {"latitude": CHUNCHEON_CENTER[0],
                                               "longitude": CHUNCHEON_CENTER[1]},
                                    "radius": 30000.0}},
    }
    req = urllib.request.Request(
        PLACES_URL, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": key,
                 "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location"},
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = []
    for p in data.get("places", []):
        loc = p.get("location") or {}
        if loc.get("latitude") is None or loc.get("longitude") is None:
            continue
        out.append({
            "name": (p.get("displayName") or {}).get("text", ""),
            "addr": p.get("formattedAddress", ""),
            "lat": float(loc["latitude"]), "lon": float(loc["longitude"]),
        })
    return out


def run_place_search() -> None:
    ss = st.session_state
    ss.place_results, ss.place_msg = [], ""
    ss.pop("place_pick", None)
    q = str(ss.get("place_query", "")).strip()
    if not q:
        ss.place_msg = "검색어를 입력해 주세요."
        return
    try:
        ss.place_results = search_places(q)
        if not ss.place_results:
            ss.place_msg = "검색 결과가 없어요. 다른 검색어로 해 보세요."
    except RuntimeError as e:
        ss.place_msg = str(e)
    except Exception:
        ss.place_msg = "검색에 실패했어요. API 키와 Places API 사용 설정을 확인해 주세요."


def use_place() -> None:
    ss = st.session_state
    results = ss.get("place_results") or []
    if not results:
        return
    i = min(max(int(ss.get("place_pick", 0)), 0), len(results) - 1)
    p = results[i]
    ss.new_name = p["name"]
    ss.new_addr = p["addr"]
    ss.pick_lat = round(p["lat"], 4)
    ss.pick_lon = round(p["lon"], 4)
    ss.pick_key = uuid4().hex  # 좌표 입력칸을 새 값으로 다시 그리기 위한 키


# ======================================================================
# Firebase 실시간 연동 (REST API)
# ======================================================================
SHARED_PATH = "trips/shared"


def db_base_url() -> str:
    try:
        return str(st.secrets["FIREBASE_DB_URL"]).rstrip("/")
    except Exception:
        return ""


def fetch_remote():
    """(성공 여부, 데이터). 네트워크 오류는 (False, None)."""
    base = db_base_url()
    if not base:
        return False, None
    try:
        with urllib.request.urlopen(f"{base}/{SHARED_PATH}.json", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data is None or (isinstance(data, dict) and "spots" in data):
            return True, data
        return False, None
    except Exception:
        return False, None


def push_remote(payload: dict) -> bool:
    base = db_base_url()
    if not base:
        return False
    req = urllib.request.Request(
        f"{base}/{SHARED_PATH}.json",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="PUT", headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception:
        return False


def canon(payload: dict) -> str:
    """비교용 문자열 (저장 시각 제외)"""
    return json.dumps({k: v for k, v in payload.items() if k != "saved_at"},
                      ensure_ascii=False, sort_keys=True)


# ======================================================================
# 세션 초기화
# ======================================================================
@st.cache_resource
def boot_info() -> dict:
    """서버(앱)가 (재)시작될 때 한 번만 만들어지는 정보"""
    return {"seeded": False, "date": datetime.now(KST).date()}


def default_payload() -> dict:
    return {
        "version": 1,
        "page_title": DEFAULT_TITLE,
        "start_date": boot_info()["date"].isoformat(),
        "saved_at": "",
        "spots": [{**s, "done": False} for s in DEFAULT_SPOTS],
    }


def init_state() -> None:
    ss = st.session_state
    boot = boot_info()
    ss.synced_json = None
    if not boot["seeded"]:
        # 앱 재시작 후 첫 접속: 기본 데이터를 공유 저장소에 올리고 사용
        apply_payload(default_payload())
        boot["seeded"] = push_remote(build_payload())
        if boot["seeded"]:
            ss.synced_json = canon(build_payload())
        return
    ok, remote = fetch_remote()
    if ok and remote is not None:
        apply_payload(remote)              # 새로고침: 마지막으로 입력한 내용 불러오기
        ss.synced_json = canon(build_payload())
    elif ok:                               # 공유 저장소가 비어 있음
        apply_payload(default_payload())
        ss.synced_json = canon(build_payload()) if push_remote(build_payload()) else None
    else:                                  # 연결 실패: 임시 표시 후 sync_poll이 재시도
        apply_payload(default_payload())


if "spots_data" not in st.session_state:
    init_state()

st.session_state.setdefault("pick_lat", 37.8870)
st.session_state.setdefault("pick_lon", 127.7650)
st.session_state.setdefault("pick_key", "0")

st.set_page_config(
    page_title=st.session_state.get("trip_title", DEFAULT_TITLE).strip() or DEFAULT_TITLE,
    page_icon="🗺️", layout="wide", initial_sidebar_state="collapsed",
)

# ======================================================================
# CSS
# ======================================================================
CSS = """
<style>
    .block-container {padding: 1.5rem 0.6rem 2rem 0.6rem !important;}
    /* 당겨서 새로고침 방해 요소 제거: 모든 스크롤 영역의 overscroll을 기본값(auto)으로 */
    *, *::before, *::after {overscroll-behavior-y: auto !important;}
    .stCheckbox label {font-size: 0.92rem !important; font-weight: 700 !important; cursor: pointer; color: #111827;}
    .stCheckbox {margin-bottom: 0 !important;}

    div[data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0.3rem 0.75rem 0.3rem 0.75rem !important; margin-bottom: 0.4rem !important; border-radius: 10px !important;
    }
    [class*="st-key-card_"] [data-testid="stVerticalBlock"] {gap: 0.3rem !important;}
    [class*="st-key-card_"] [data-testid="stCaptionContainer"] {
        font-size: 0.78rem !important; color: #4B5563 !important; line-height: 1.3 !important; padding-left: 2px;
    }
    [class*="st-key-card_"] [data-testid="stHorizontalBlock"] {
        flex-direction: row !important; flex-wrap: nowrap !important; gap: 0.4rem !important; align-items: flex-start !important;
    }
    [class*="st-key-card_"] [data-testid="stColumn"], [class*="st-key-card_"] [data-testid="column"] {min-width: 0 !important;}

    [class*="st-key-hdr_"] [data-testid="stHorizontalBlock"] {gap: 0.6rem !important;}
    [class*="st-key-hdr_"] [data-testid="stColumn"]:nth-child(1), [class*="st-key-hdr_"] [data-testid="column"]:nth-child(1) {flex: 0 0 1.0rem !important; width: 1.0rem !important;}
    [class*="st-key-hdr_"] [data-testid="stColumn"]:nth-child(2), [class*="st-key-hdr_"] [data-testid="column"]:nth-child(2) {flex: 1 1 0 !important; width: auto !important;}
    [class*="st-key-hdr_"] [data-testid="stColumn"]:nth-child(n+3), [class*="st-key-hdr_"] [data-testid="column"]:nth-child(n+3) {flex: 0 0 1.2rem !important; width: 1.2rem !important;}
    [class*="st-key-hdr_"] [data-testid="stColumn"]:nth-child(3), [class*="st-key-hdr_"] [data-testid="column"]:nth-child(3) {margin-left: 0.2rem !important;}

    [class*="st-key-btn_del_"] button svg, [class*="st-key-btn_del_"] button [data-testid="stIconMaterial"] {display: none !important;}
    [class*="st-key-btn_del_"] button {justify-content: center !important;}
    a.spot-name {color: #1E3A8A; font-weight: 700; font-size: 0.92rem; text-decoration: underline; text-underline-offset: 2px; line-height: 1.5; display: inline-block; margin-top: 0.35rem;}
    [class*="st-key-btn_edit_"] button, [class*="st-key-btn_del_"] button, [class*="st-key-btn_focus_"] button {min-height: 1.9rem !important; height: 1.9rem !important; width: 100% !important; padding: 0 !important; border: none !important; background: transparent !important;}

    .st-key-mapbox {margin-bottom: 0 !important;}
    /* 지도 iframe: 세로 스와이프는 브라우저(페이지 스크롤/당겨서 새로고침)에 넘김 */
    .st-key-mapbox iframe {touch-action: pan-y !important; display: block;}
    .st-key-progress_row {margin-top: 0 !important;}
    /* 여행 시작일 + 일정 보기: 한 줄 고정 */
    .st-key-daybar [data-testid="stHorizontalBlock"] {flex-direction: row !important; flex-wrap: nowrap !important; gap: 0.4rem !important;}
    .st-key-daybar [data-testid="stColumn"], .st-key-daybar [data-testid="column"] {min-width: 0 !important;}
    .st-key-daybar input {min-height: 2.4rem !important; font-size: 0.85rem !important; padding-left: 0.4rem !important; padding-right: 0.2rem !important;}
    .st-key-daybar [data-testid="stDateInput"] {min-width: 0 !important;}
    .st-key-progress_row [data-testid="stHorizontalBlock"] {flex-direction: row !important; flex-wrap: nowrap !important; gap: 0.5rem !important; align-items: center !important;}
    .st-key-progress_row [data-testid="stColumn"], .st-key-progress_row [data-testid="column"] {min-width: 0 !important;}
    .st-key-progress_row div[data-baseweb="select"] > div {min-height: 2rem !important; font-size: 0.8rem !important;}
</style>
"""
st.markdown(CSS + day_color_css(), unsafe_allow_html=True)
st.components.v1.html(PTR_JS, height=0)

for s in st.session_state.spots_data:
    st.session_state.done.setdefault(s["id"], False)
    st.session_state.editing_flags.setdefault(s["id"], False)

# ---- 지도 이벤트 처리: 클릭 좌표 / 하단 버튼(일정 추가·저장) ----
_pick = st.session_state.get("map_pick")
if isinstance(_pick, dict):
    if _pick.get("action") and _pick.get("nonce") != st.session_state.get("last_action_nonce"):
        st.session_state.last_action_nonce = _pick.get("nonce")
        st.session_state.open_dialog = _pick["action"]
    elif "lat" in _pick and _pick.get("nonce") != st.session_state.get("last_pick_nonce"):
        st.session_state.last_pick_nonce = _pick.get("nonce")
        st.session_state.pick_lat = round(float(_pick["lat"]), 4)
        st.session_state.pick_lon = round(float(_pick["lon"]), 4)
        st.session_state.pick_key = uuid4().hex


# ======================================================================
# 대화상자 (일정 추가 / 저장·불러오기)
# ======================================================================
@st.dialog("➕ 새 장소 추가")
def add_spot_dialog() -> None:
    ss = st.session_state
    st.caption("💡 지도를 누르면 그 위치 좌표가 자동 입력돼요.")
    with st.expander("🔎 구글 지도에서 장소 찾기", expanded=True):
        st.text_input("검색어", placeholder="예: 통나무집 본점", key="place_query")
        st.button("검색", on_click=run_place_search, use_container_width=True)
        if ss.get("place_msg"):
            st.caption(ss.place_msg)
        results = ss.get("place_results") or []
        if results:
            st.radio("검색 결과", options=list(range(len(results))),
                     format_func=lambda i: f"{results[i]['name']} · {results[i]['addr']}", key="place_pick")
            MAP_COMPONENT(spots=[], compact=True,
                          places=[{"name": r["name"], "addr": r["addr"], "lat": r["lat"], "lon": r["lon"]}
                                  for r in results],
                          selected=int(ss.get("place_pick", 0)), key="place_map", default=None)
            st.button("이 장소로 채우기", on_click=use_place, use_container_width=True)

    st.markdown("##### 📍 장소 정보")
    new_name = st.text_input("장소명", key="new_name", placeholder="예: 구봉산 카페거리")
    new_day = st.number_input("일차 (Day)", min_value=1, max_value=99, value=2, step=1, key="new_day")
    new_start = st.selectbox("시작 시간", time_options(with_all_day=True),
                             index=pick_index(time_options(with_all_day=True), "09:00"), key="new_start")
    new_end = st.selectbox("완료 시간", time_options(), index=pick_index(time_options(), "10:00"),
                           key="new_end", disabled=new_start == "종일")
    new_time = make_time(new_start, new_end)
    new_tip = st.text_area("메모/팁 (Enter로 줄바꿈)", placeholder="예: 소양강 조망 카페", height=90, key="new_tip")
    new_lat = st.number_input("위도(Lat)", value=float(ss.pick_lat), format="%.4f", key=f"new_lat_{ss.pick_key}")
    new_lon = st.number_input("경도(Lon)", value=float(ss.pick_lon), format="%.4f", key=f"new_lon_{ss.pick_key}")

    if st.button("추가하기", use_container_width=True, type="primary"):
        if new_start != "종일" and new_end <= new_start:
            st.error("완료 시간은 시작 시간보다 늦어야 해요.")
        elif not new_name:
            st.error("장소명을 입력해 주세요.")
        else:
            new_id = f"custom_{uuid4().hex[:6]}"
            ss.spots_data.append(dict(
                id=new_id, day=new_day, name=new_name, time=new_time,
                lat=new_lat, lon=new_lon, desc=ss.get("new_addr") or "사용자 등록 장소", tip=new_tip))
            ss.done[new_id] = False
            ss.editing_flags[new_id] = False
            ss.new_addr = ""
            sort_spots()
            st.rerun()


@st.dialog("💾 저장 / 불러오기")
def save_dialog() -> None:
    st.text_input("여행 제목", value=st.session_state.get("trip_title", DEFAULT_TITLE),
                  key="title_input", on_change=sync_title)
    if st.button("제목 적용", use_container_width=True):
        sync_title()
        st.rerun()
    st.text_input("저장 파일 이름", value="chuncheon_trip", key="save_name")
    st.caption("이 기기의 다운로드 폴더에 저장돼요. 서버에는 저장되지 않아요.")
    st.download_button("⬇️ 내 기기에 저장",
                       data=json.dumps(build_payload(), ensure_ascii=False, indent=2),
                       file_name=save_filename(), mime="application/json", use_container_width=True)
    st.divider()
    st.file_uploader("⬆️ 백업 파일 선택", type="json", key="upload_file")
    # 콜백으로 실행해야 위젯(제목 입력칸 등)을 그리기 전에 값을 바꿀 수 있음
    st.button("파일에서 불러오기", use_container_width=True, on_click=load_from_upload)
    if st.session_state.pop("reload_now", False):
        st.rerun()


@st.dialog("🔀 일정 순서 변경")
def reorder_dialog() -> None:
    ss = st.session_state
    st.caption("⠿ 손잡이를 끌어 원하는 자리에 놓으세요. 앞뒤 일정 사이 시간으로 자동 조정되고, "
               "Day도 그 자리에 맞춰 바뀌어요. 종일 일정은 시간이 그대로예요.")
    items = [{"id": s["id"], "name": s["name"], "day": int(s["day"]), "time": s.get("time", "")}
             for s in ss.spots_data]
    val = SORT_COMPONENT(items=items, key="sort_pick", default=None)
    if isinstance(val, dict) and val.get("nonce") != ss.get("last_sort_nonce"):
        ss.last_sort_nonce = val.get("nonce")
        apply_reorder(val.get("order", []), val.get("moved", ""))
        ss.msg = "🔀 일정 순서를 바꿨어요."
        st.rerun()  # 대화상자를 닫고 카드 화면을 새로 그림
    if st.button("닫기", use_container_width=True):
        st.rerun()


_pending = st.session_state.pop("open_dialog", None)
if _pending == "add":
    add_spot_dialog()
elif _pending == "save":
    save_dialog()
elif _pending == "reorder":
    reorder_dialog()

# ======================================================================
# 카드 간 공유 동기화
# ======================================================================
@st.fragment(run_every=3)
def sync_poll() -> None:
    """3초마다 공유 데이터 확인 → 다른 기기에서 바뀌었으면 화면 갱신"""
    ok, remote = fetch_remote()
    if not ok:
        return
    ss = st.session_state
    if ss.synced_json is None:  # 처음 연결이 실패했던 경우: 지금 연결되면 맞춰 줌
        if remote is None:
            if push_remote(build_payload()):
                ss.synced_json = canon(build_payload())
        else:
            try:
                apply_payload(remote)
            except Exception:
                return
            ss.synced_json = canon(build_payload())
            st.rerun(scope="app")
        return
    if remote is None:
        if push_remote(build_payload()):
            ss.synced_json = canon(build_payload())
        return
    if canon(remote) != ss.synced_json:
        try:
            apply_payload(remote)
        except Exception:
            return
        ss.synced_json = canon(build_payload())
        st.rerun(scope="app")


sync_poll()

# ======================================================================
# 화면
# ======================================================================
_title = st.session_state.get("trip_title", DEFAULT_TITLE).strip() or DEFAULT_TITLE
st.markdown(f"<div style='font-size: 1.6rem; font-weight: 800; padding-bottom: 0.3rem;'>🚞 {_title}</div>",
            unsafe_allow_html=True)

if st.session_state.get("msg"):
    st.toast(st.session_state.pop("msg"))

# ---- 여행 시작일 + 일차 목록 (타이틀 밑) ----
all_spots = st.session_state.spots_data
_days = sorted({int(s["day"]) for s in all_spots})
_day_opts = [0] + _days  # 0 = 전체
if st.session_state.get("day_filter") not in _day_opts:
    st.session_state.day_filter = 0
sel_day = st.session_state.day_filter
_max_day = max((int(s["day"]) for s in all_spots), default=1)
_trip_len = f"({_max_day - 1}박 {_max_day}일)  "
_row_style = ("height:2.4rem;display:flex;align-items:center;font-size:0.9rem;"
              "font-weight:700;color:#374151;white-space:nowrap;")
with st.container(key="daybar"):
    d_sp, d_lbl, d_date, d_len = st.columns([3, 1.1, 2.7, 1.1])
    with d_lbl:
        st.markdown(f'<div style="{_row_style}justify-content:flex-end;">여행 시작:</div>',
                    unsafe_allow_html=True)
    with d_date:
        st.date_input("여행 시작일", key="trip_start_input", label_visibility="collapsed")
    with d_len:
        st.markdown(f'<div style="{_row_style}color:#2563EB;padding-right:0.9rem;">{_trip_len}</div>', unsafe_allow_html=True)

spots = [s for s in all_spots if sel_day == 0 or int(s["day"]) == sel_day]
done_flags = [st.session_state.done.get(s["id"], False) for s in spots]
n_done = sum(1 for s in all_spots if st.session_state.done.get(s["id"], False))
total_all = len(all_spots) if all_spots else 1

col_map, col_ctrl = st.columns([1.1, 1.2])

with col_ctrl:
    def render_card(spot):
        sid = spot["id"]
        checked = st.session_state.done.get(sid, False)
        # 완료 여부가 바뀌면 키도 바뀌어 체크박스가 새 값으로 다시 그려짐 (다른 기기 변경도 반영)
        key = f"chk_{sid}_{int(checked)}"
        is_editing = st.session_state.editing_flags.get(sid, False)

        with st.container(border=True, key=f"card_d{spot['day']}_{sid}"):
            if is_editing:
                st.markdown("**✏️ 일정 정보 수정**")
                edit_name = st.text_input("장소명", value=spot["name"], key=f"inp_name_{sid}")
                s_start, s_end = split_time(spot.get("time", ""))
                edit_start = st.selectbox("시작 시간", time_options(extra=s_start, with_all_day=True),
                                          index=pick_index(time_options(extra=s_start, with_all_day=True), s_start),
                                          key=f"inp_start_{sid}")
                edit_end = st.selectbox("완료 시간", time_options(extra=s_end),
                                        index=pick_index(time_options(extra=s_end), s_end),
                                        key=f"inp_end_{sid}", disabled=edit_start == "종일")
                edit_time = make_time(edit_start, edit_end)
                edit_day = st.number_input("일차 (Day)", min_value=1, max_value=99,
                                           value=max(1, int(spot.get("day", 1))), step=1, key=f"inp_day_{sid}")
                edit_tip = st.text_area("메모/팁 (Enter로 줄바꿈)", value=spot.get("tip", ""),
                                        key=f"inp_tip_{sid}", height=90)

                b_save, b_cancel = st.columns(2)
                if b_save.button("저장", key=f"save_{sid}", use_container_width=True):
                    if edit_start != "종일" and edit_end <= edit_start:
                        st.error("완료 시간은 시작 시간보다 늦어야 해요.")
                    else:
                        for s in st.session_state.spots_data:  # 정렬 후에도 올바른 항목을 고치도록 id로 찾음
                            if s["id"] == sid:
                                s.update(name=edit_name, time=edit_time, day=edit_day, tip=edit_tip)
                        sort_spots()  # 일차/시간 변경 시 자동 정렬
                        st.session_state.editing_flags[sid] = False
                        st.rerun()
                if b_cancel.button("취소", key=f"cancel_{sid}", use_container_width=True):
                    st.session_state.editing_flags[sid] = False
                    st.rerun()
            else:
                q = quote(re.sub(r"^\d+\.\s*", "", spot["name"]))
                naver_url = f"https://search.naver.com/search.naver?query={q}"
                with st.container(key=f"hdr_{sid}"):
                    c_chk, c_name, c_focus, c_edit, c_del = st.columns([1, 6, 1, 1, 1])
                    with c_chk:
                        st.checkbox(spot["name"], value=checked, key=key, on_change=set_done, args=(sid, key),
                                    label_visibility="collapsed")
                    with c_name:
                        st.markdown(f'<a class="spot-name" href="{naver_url}" target="_blank" rel="noopener">'
                                    f'{html.escape(spot["name"])}</a>', unsafe_allow_html=True)
                    with c_focus:
                        st.button("📍", key=f"btn_focus_{sid}", help="지도에서 이 장소 보기",
                                  on_click=set_focus, args=(spot["lat"], spot["lon"]))
                    with c_edit:
                        if st.button("✏️", key=f"btn_edit_{sid}", help="일정 수정"):
                            st.session_state.editing_flags[sid] = True
                            st.rerun()
                    with c_del:
                        with st.container(key=f"btn_del_{sid}"):
                            with st.popover("🗑️", help="일정 삭제"):
                                st.write(f"‘{spot['name']}’ 일정을 삭제할까요?")
                                st.button("삭제 확인", key=f"del_{sid}", type="primary",
                                          on_click=delete_spot, args=(sid,), use_container_width=True)

                time_part = f"⏱ {spot['time']} &nbsp;" if spot.get("time") else ""
                badge = ('<span style="background:#DCFCE7;color:#15803D;padding:1px 7px;border-radius:9999px;font-weight:700;">🛂 여행 완료</span>'
                         if checked else
                         '<span style="background:#E0F2FE;color:#0369A1;padding:1px 7px;border-radius:9999px;font-weight:700;">🗺️ 여행 전</span>')
                st.markdown(f'<div style="font-size:0.8rem;color:#374151;margin:-4px 0 0 2px;">{time_part}{badge} &nbsp;'
                            f'<b style="color:#6B7280;">Day {spot["day"]}</b></div>', unsafe_allow_html=True)

                tip_lines = [line.strip() for line in spot["tip"].split("\n") if line.strip()]
                if tip_lines:
                    tip_items = "".join(
                        f'<div style="padding-left:0.9em;text-indent:-0.9em;">- {html.escape(line)}</div>'
                        for line in tip_lines)
                    st.markdown(f'<div style="font-size:0.78rem;color:#4B5563;line-height:1.4;padding-left:2px;">'
                                f'{tip_items}</div>', unsafe_allow_html=True)
                st.markdown('<div style="height:1rem;"></div>', unsafe_allow_html=True)

    if not spots:
        st.info("이 날짜에는 아직 일정이 없어요. ‘➕ 일정 추가’로 넣어 보세요.")
    for i in range(0, len(spots), 2):
        row_c1, row_c2 = st.columns(2)
        with row_c1:
            render_card(spots[i])
        if i + 1 < len(spots):
            with row_c2:
                render_card(spots[i + 1])

with col_map:

    map_data = [
        {"name": f"{s['name']} ({s.get('time', '')})" if s.get("time") else s["name"],
         "lat": s["lat"], "lon": s["lon"], "desc": s.get("desc", ""), "tip": s.get("tip", ""), "done": d}
        for s, d in zip(spots, done_flags)
    ]
    with st.container(key="mapbox"):
        MAP_COMPONENT(spots=map_data, focus=st.session_state.get("focus"), key="map_pick", default=None)

    with st.container(key="progress_row"):
        p_c1, p_c2 = st.columns([7, 3])
        with p_c1:
            st.progress(n_done / total_all, text=f"행복 충전율: {n_done * 100 // total_all}%")
        with p_c2:
            st.selectbox("일정 보기", _day_opts,
                         format_func=lambda d: "전체" if d == 0 else day_label(d),
                         key="day_filter", label_visibility="collapsed")

# ======================================================================
# 변경 사항 공유 (값이 실제로 바뀐 경우에만 전송)
# ======================================================================
if st.session_state.synced_json is not None:
    _cur = build_payload()
    _cur_json = canon(_cur)
    if _cur_json != st.session_state.synced_json and push_remote(_cur):
        st.session_state.synced_json = _cur_json
