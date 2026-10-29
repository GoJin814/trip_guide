import html
import json
import urllib.request
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
from map_comp import MAP_COMPONENT

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="여행 기록", page_icon="📖", layout="wide", initial_sidebar_state="collapsed")

# ======================================================================
# 상수 / 지도 컴포넌트
# ======================================================================
KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parent.parent
RECORD_PATH = "trips/records"
SHARED_PATH = "trips/shared"
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
ORDER_OPTIONS = ["오래된 순", "최신 순"]

# 당겨서 새로고침 (여행 정보 페이지와 동일)
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
      if (doc.querySelector('[role="dialog"]')) return false;
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

CSS = """
<style>
    .block-container {padding: 3.8rem 0.6rem 2rem 0.6rem !important;}
    *, *::before, *::after {overscroll-behavior-y: auto !important;}
    .st-key-mapbox {margin-bottom: 0 !important;}
    .st-key-mapbox iframe {touch-action: pan-y !important; display: block;}
    div[data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0.3rem 0.75rem !important; margin-bottom: 0.4rem !important; border-radius: 10px !important;
    }
    [class*="st-key-rc_"] [data-testid="stVerticalBlock"] {gap: 0.3rem !important;}
    [class*="st-key-rc_"] [data-testid="stHorizontalBlock"] {
        flex-direction: row !important; flex-wrap: nowrap !important; gap: 0.3rem !important; align-items: center !important;
    }
    [class*="st-key-rc_"] [data-testid="stColumn"], [class*="st-key-rc_"] [data-testid="column"] {min-width: 0 !important;}
    [class*="st-key-rc_"] [data-testid="stColumn"]:nth-child(n+2), [class*="st-key-rc_"] [data-testid="column"]:nth-child(n+2) {
        flex: 0 0 1.8rem !important; width: 1.8rem !important;}
    [class*="st-key-rc_"] button {min-height: 1.9rem !important; height: 1.9rem !important; width: 100% !important;
        padding: 0 !important; border: none !important; background: transparent !important;}
    [class*="st-key-rc_"] [data-testid="stMarkdownContainer"] p {margin: 0;}
    .rc-title {font-weight: 800; font-size: 1rem; color: #111827; line-height: 1.4;}
    .rc-line {font-size: 0.92rem; color: #1E3A8A; font-weight: 700; margin-top: 4px;}
    .rc-meta {font-size: 0.8rem; color: #374151; margin-top: 2px;}
    .rc-memo {font-size: 0.78rem; color: #4B5563; line-height: 1.4; margin-top: 4px;}
    .rc-memo div {padding-left: 0.9em; text-indent: -0.9em;}
</style>
"""


# ======================================================================
# 공유 저장소 (Firebase REST)
# ======================================================================
def db_base_url() -> str:
    try:
        return str(st.secrets["FIREBASE_DB_URL"]).rstrip("/")
    except Exception:
        return ""


def fetch_path(path: str):
    """(성공 여부, 데이터)"""
    base = db_base_url()
    if not base:
        return False, None
    try:
        with urllib.request.urlopen(f"{base}/{path}.json", timeout=5) as r:
            return True, json.loads(r.read().decode("utf-8"))
    except Exception:
        return False, None


def push_path(path: str, payload) -> bool:
    base = db_base_url()
    if not base:
        return False
    req = urllib.request.Request(
        f"{base}/{path}.json", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="PUT", headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception:
        return False


# ======================================================================
# 여행 기록 데이터
# ======================================================================
def canon_records(recs: list) -> str:
    return json.dumps(recs, ensure_ascii=False, sort_keys=True)


def parse_records(data) -> list:
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return [r for r in data["records"] if isinstance(r, dict) and r.get("id")]
    return []


def save_records() -> bool:
    ss = st.session_state
    payload = {"version": 1, "saved_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "records": ss.records}
    if push_path(RECORD_PATH, payload):
        ss.rec_synced = canon_records(ss.records)
        ss.rec_dirty = False
        return True
    ss.rec_dirty = True
    return False


def parse_date(v):
    try:
        return date.fromisoformat(str(v))
    except Exception:
        return None


def stay_text(s, e) -> str:
    if not s or not e or e < s:
        return ""
    n = (e - s).days
    return f"{n}박 {n + 1}일"


def fmt_date(d) -> str:
    return f"{d.year}.{d.month:02d}.{d.day:02d}" if d else ""


def sort_records(recs: list, order: str) -> list:
    key = lambda r: (parse_date(r.get("start")) or date.min, str(r.get("id")))
    return sorted(recs, key=key, reverse=(order == "최신 순"))


def _pt(lat, lon):
    return (lat, lon) if lat is not None and lon is not None else None


# ======================================================================
# 장소 검색 (Places API (New) — Secrets의 GOOGLE_PLACES_API_KEY 사용)
# ======================================================================
def search_places(query: str) -> list:
    try:
        key = str(st.secrets["GOOGLE_PLACES_API_KEY"]).strip()
    except Exception:
        key = ""
    if not key:
        raise RuntimeError("구글 검색을 쓰려면 Streamlit Secrets에 GOOGLE_PLACES_API_KEY를 넣어 주세요.")
    body = {"textQuery": query, "languageCode": "ko", "regionCode": "KR", "maxResultCount": 8}
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
        out.append({"name": (p.get("displayName") or {}).get("text", ""),
                    "addr": p.get("formattedAddress", ""),
                    "lat": float(loc["latitude"]), "lon": float(loc["longitude"])})
    return out


def run_search(rid: str) -> None:
    ss = st.session_state
    ss[f"res_{rid}"], ss[f"msg_{rid}"] = [], ""
    ss.pop(f"pick_{rid}", None)
    q = str(ss.get(f"q_{rid}", "")).strip()
    if not q:
        ss[f"msg_{rid}"] = "검색어를 입력해 주세요."
        return
    try:
        res = search_places(q)
        ss[f"res_{rid}"] = res
        if not res:
            ss[f"msg_{rid}"] = "검색 결과가 없어요. 다른 검색어로 해 보세요."
    except RuntimeError as e:
        ss[f"msg_{rid}"] = str(e)
    except Exception:
        ss[f"msg_{rid}"] = "검색에 실패했어요. API 키와 Places API 설정을 확인해 주세요."


def set_endpoint(rid: str, which: str) -> None:
    """검색 결과 중 선택한 장소를 출발지/도착지로 지정"""
    ss = st.session_state
    res = ss.get(f"res_{rid}") or []
    if not res:
        return
    i = min(max(int(ss.get(f"pick_{rid}", 0)), 0), len(res) - 1)
    p = res[i]
    ss[f"{'fn' if which == 'from' else 'tn'}_{rid}"] = p["name"]
    ss.setdefault(f"coord_{rid}", {"from": None, "to": None})[which] = (round(p["lat"], 4), round(p["lon"], 4))


# ======================================================================
# 콜백
# ======================================================================
def set_focus(lat, lon) -> None:
    st.session_state.focus = {"lat": lat, "lon": lon, "nonce": uuid4().hex}


def delete_record(rid: str) -> None:
    ss = st.session_state
    ss.records = [r for r in ss.records if r["id"] != rid]
    save_records()


# ======================================================================
# 입력 대화상자 (추가 / 수정 공용)
# ======================================================================
def open_form(rid: str, rec: dict) -> None:
    ss = st.session_state
    if f"coord_{rid}" not in ss:
        ss[f"coord_{rid}"] = {"from": _pt(rec.get("from_lat"), rec.get("from_lon")),
                              "to": _pt(rec.get("to_lat"), rec.get("to_lon"))}

    with st.expander("🔎 구글 지도에서 장소 찾기", expanded=True):
        st.text_input("검색어", key=f"q_{rid}", placeholder="예: 인천국제공항 제1터미널")
        st.button("검색", key=f"s_{rid}", on_click=run_search, args=(rid,), use_container_width=True)
        if ss.get(f"msg_{rid}"):
            st.caption(ss[f"msg_{rid}"])
        res = ss.get(f"res_{rid}") or []
        if res:
            st.radio("검색 결과", options=list(range(len(res))),
                     format_func=lambda i: f"{res[i]['name']} · {res[i]['addr']}", key=f"pick_{rid}")
            c1, c2 = st.columns(2)
            c1.button("출발지로 지정", key=f"bf_{rid}", on_click=set_endpoint, args=(rid, "from"),
                      use_container_width=True)
            c2.button("도착지로 지정", key=f"bt_{rid}", on_click=set_endpoint, args=(rid, "to"),
                      use_container_width=True)

    title = st.text_input("여정 제목", value=rec.get("trip_title") or ss.get("travel_title") or "",
                          key=f"t_{rid}")
    n1, n2 = st.columns(2)
    from_name = n1.text_input("출발지", value=rec.get("from_name", ""), key=f"fn_{rid}")
    to_name = n2.text_input("도착지", value=rec.get("to_name", ""), key=f"tn_{rid}")
    coord = ss[f"coord_{rid}"]
    st.caption(f"📍 좌표: 출발지 {'설정됨' if coord.get('from') else '없음'} · "
               f"도착지 {'설정됨' if coord.get('to') else '없음'}")

    d1, d2 = st.columns(2)
    s0 = parse_date(rec.get("start")) or datetime.now(KST).date()
    e0 = parse_date(rec.get("end")) or s0
    start = d1.date_input("시작일", value=s0, key=f"ds_{rid}")
    end = d2.date_input("종료일", value=e0, key=f"de_{rid}")
    if stay_text(start, end):
        st.caption(f"🗓️ {stay_text(start, end)}")
    country = st.text_input("나라", value=rec.get("country", "대한민국"), key=f"c_{rid}")
    memo = st.text_area("메모 (Enter로 줄바꿈)", value=rec.get("memo", ""), key=f"m_{rid}", height=90)

    if st.button("저장", key=f"save_{rid}", type="primary", use_container_width=True):
        if not from_name.strip() or not to_name.strip():
            st.error("출발지와 도착지를 입력해 주세요.")
        elif end < start:
            st.error("종료일은 시작일 이후여야 해요.")
        else:
            fc, tc = coord.get("from"), coord.get("to")
            new = dict(
                id=rec.get("id") or uuid4().hex[:8],
                trip_title=title.strip() or "여행",
                from_name=from_name.strip(), from_lat=fc[0] if fc else None, from_lon=fc[1] if fc else None,
                to_name=to_name.strip(), to_lat=tc[0] if tc else None, to_lon=tc[1] if tc else None,
                start=start.isoformat(), end=end.isoformat(),
                country=country.strip(), memo=memo.strip(),
            )
            if rid == "new":
                ss.records = ss.records + [new]
            else:
                ss.records = [new if r["id"] == rid else r for r in ss.records]
            save_records()
            ss.pop(f"coord_{rid}", None)
            ss.msg = "📖 여행 기록을 저장했어요."
            st.rerun()


@st.dialog("➕ 여행 기록 추가")
def add_dialog() -> None:
    open_form("new", {})


@st.dialog("✏️ 여행 기록 수정")
def edit_dialog(rid: str) -> None:
    rec = next((r for r in st.session_state.records if r["id"] == rid), {})
    open_form(rid, rec)


# ======================================================================
# 초기화 / 동기화
# ======================================================================
if "records" not in st.session_state:
    ok, data = fetch_path(RECORD_PATH)
    st.session_state.records = parse_records(data) if ok else []
    st.session_state.rec_synced = canon_records(st.session_state.records) if ok else None
    st.session_state.rec_dirty = False

if "travel_title" not in st.session_state:
    ok, data = fetch_path(SHARED_PATH)
    st.session_state.travel_title = str(data.get("page_title", "")) if ok and isinstance(data, dict) else ""

if st.session_state.get("rec_dirty"):
    save_records()  # 이전 저장이 실패했다면 다시 시도


@st.fragment(run_every=5)
def rec_sync_poll() -> None:
    """다른 기기에서 기록이 바뀌면 화면을 맞춤"""
    ok, data = fetch_path(RECORD_PATH)
    if not ok:
        return
    ss = st.session_state
    remote = parse_records(data)
    if ss.rec_synced is None:
        if not remote and ss.records:
            save_records()
        else:
            ss.records = remote
            ss.rec_synced = canon_records(remote)
            st.rerun(scope="app")
        return
    if canon_records(remote) != ss.rec_synced:
        ss.records = remote
        ss.rec_synced = canon_records(remote)
        st.rerun(scope="app")


st.markdown(CSS, unsafe_allow_html=True)
components.html(PTR_JS, height=0)
rec_sync_poll()

if st.session_state.get("msg"):
    st.toast(st.session_state.pop("msg"))

# ======================================================================
# 화면
# ======================================================================
st.markdown("<div style='font-size:1.6rem;font-weight:800;padding-bottom:0.3rem;'>🌿 행복 충전 기록</div>",
            unsafe_allow_html=True)
st.page_link("app.py", label="🗺️ 여행 정보 페이지로")

order = st.session_state.get("rec_order", ORDER_OPTIONS[0])
recs = sort_records(st.session_state.records, order)

places, routes = [], []
for r in recs:
    info = f"{r.get('trip_title') or ''} · {r.get('start', '')}~{r.get('end', '')}"
    if r.get("from_lat") is not None and r.get("from_lon") is not None:
        places.append({"name": f"출발 · {r['from_name']}", "addr": info,
                       "lat": r["from_lat"], "lon": r["from_lon"]})
    if r.get("to_lat") is not None and r.get("to_lon") is not None:
        places.append({"name": f"도착 · {r['to_name']}", "addr": info,
                       "lat": r["to_lat"], "lon": r["to_lon"]})
    if None not in (r.get("from_lat"), r.get("from_lon"), r.get("to_lat"), r.get("to_lon")):
        routes.append([[r["from_lat"], r["from_lon"]], [r["to_lat"], r["to_lon"]]])

col_map, col_list = st.columns([1.1, 1.2])

with col_map:
    with st.container(key="mapbox"):
        MAP_COMPONENT(spots=[], places=places, routes=routes, distance=True, bar=False,
                      selected=-1, focus=st.session_state.get("focus"), key="rec_map", default=None)
    if not places:
        st.caption("출발지·도착지 좌표가 있는 기록이 지도에 표시돼요.")

with col_list:
    st.selectbox("정렬", ORDER_OPTIONS, key="rec_order", label_visibility="collapsed")
    if st.button("➕ 여행 기록 추가", use_container_width=True):
        add_dialog()

    if not recs:
        st.info("아직 여행 기록이 없어요. ‘➕ 여행 기록 추가’로 남겨 보세요.")

    for rec in recs:
        rid = rec["id"]
        with st.container(border=True, key=f"rc_{rid}"):
            h_title, h_pin, h_edit, h_del = st.columns([8, 1, 1, 1])
            with h_title:
                st.markdown(f'<div class="rc-title">{html.escape(rec.get("trip_title") or "여행")}</div>',
                            unsafe_allow_html=True)
            pin = _pt(rec.get("to_lat"), rec.get("to_lon")) or _pt(rec.get("from_lat"), rec.get("from_lon"))
            with h_pin:
                st.button("📍", key=f"fp_{rid}", help="지도에서 보기", disabled=pin is None,
                          on_click=set_focus, args=(pin[0] if pin else None, pin[1] if pin else None))
            with h_edit:
                if st.button("✏️", key=f"ed_{rid}", help="수정"):
                    edit_dialog(rid)
            with h_del:
                with st.popover("🗑️", help="삭제"):
                    st.write(f"‘{rec.get('trip_title') or '여행'}’ 기록을 삭제할까요?")
                    st.button("삭제 확인", key=f"dl_{rid}", type="primary", on_click=delete_record, args=(rid,),
                              use_container_width=True)

            st.markdown(f'<div class="rc-line">🛫 {html.escape(rec.get("from_name", ""))} &nbsp;→&nbsp; '
                        f'🛬 {html.escape(rec.get("to_name", ""))}</div>', unsafe_allow_html=True)
            s, e = parse_date(rec.get("start")), parse_date(rec.get("end"))
            stay = stay_text(s, e)
            st.markdown(f'<div class="rc-meta">📅 {fmt_date(s)} ~ {fmt_date(e)} '
                        f'{"<b>" + stay + "</b> " if stay else ""}· 🌏 {html.escape(rec.get("country", ""))}</div>',
                        unsafe_allow_html=True)
            memo_lines = [ln.strip() for ln in str(rec.get("memo", "")).split("\n") if ln.strip()]
            if memo_lines:
                items = "".join(f"<div>- {html.escape(ln)}</div>" for ln in memo_lines)
                st.markdown(f'<div class="rc-memo">{items}</div>', unsafe_allow_html=True)
