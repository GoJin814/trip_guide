import copy
import html
import urllib.request
import json
import re
from datetime import datetime
from urllib.parse import quote
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

# ======================================================================
# 데이터 / 저장 로직  (set_page_config 보다 먼저 실행되어야 제목을 불러올 수 있음)
# ======================================================================
DEFAULT_TITLE = "춘천 실시간 여행 트래커"

# 기본 여행 코스 데이터 (장소명, 시간 분리)
DEFAULT_SPOTS = [
    dict(id="legoland", day=1, name="1. 레고랜드 코리아", time="종일",
         lat=37.8845, lon=127.6975, desc="하중도 위치 테마파크 탐방",
         tip="오전 인기 어트랙션 집중 공략"),
    dict(id="soyang_dam", day=2, name="2. 소양호 유람선터미널", time="09:30~10:00",
         lat=37.9547, lon=127.8184, desc="청평사행 도선 승선 (편도 15분)",
         tip="댐 정상 주차장 09:30 전 도착 권장"),
    dict(id="cheongpyeongsa", day=2, name="3. 청평사 경내", time="10:15~11:45",
         lat=37.9877, lon=127.8136, desc="구성폭포 및 오봉산 산책로 관람",
         tip="선착장 ↔ 절 왕복 약 1시간 도보"),
    dict(id="sambath", day=2, name="4. 샘밭막국수", time="12:30~13:30",
         lat=37.9317, lon=127.7656, desc="담백한 전통 메밀막국수 & 편육",
         tip="소양강댐에서 차로 5분 거리 위치"),
    dict(id="cablecar", day=2, name="5. 삼악산 호수케이블카", time="14:00~15:30",
         lat=37.8548, lon=127.6970, desc="국내 최장 3.61km 케이블카 & 의암호 전망",
         tip="의암호 정차장에서 서울/수도권 복귀 직결"),
]


def build_payload() -> dict:
    """현재 화면 상태 → 저장용 dict (여행 제목 + 일정 제목/내용 + 완료 여부)"""
    ss = st.session_state
    return {
        "version": 1,
        "page_title": ss.get("trip_title", DEFAULT_TITLE),
        "saved_at": datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M"),
        "spots": [
            {**s, "done": bool(ss.get(f"chk_{s['id']}", False))}
            for s in ss.spots_data
        ],
    }


def apply_payload(data: dict) -> None:
    """저장된 dict → 화면 상태에 반영. 형식이 잘못되면 예외 발생."""
    ss = st.session_state
    spots, dones, used = [], {}, set()
    for i, s in enumerate(data["spots"]):
        try:
            sid = str(s.get("id") or f"spot_{i + 1}")
            while sid in used:
                sid = f"{sid}_{uuid4().hex[:4]}"
            used.add(sid)
            day = int(s.get("day", 1))
            spots.append(dict(
                id=sid,
                day=max(1, day),
                name=str(s["name"]),
                time=str(s.get("time", "")),
                lat=float(s["lat"]),
                lon=float(s["lon"]),
                desc=str(s.get("desc", "")),
                tip=str(s.get("tip", "")),
            ))
            dones[sid] = bool(s.get("done", False))
        except (KeyError, TypeError, ValueError):
            continue
    if not spots:
        raise ValueError("no valid spots")

    ss.spots_data = spots
    ss.editing_flags = {s["id"]: False for s in spots}
    
    # 동기화 시 백업 키도 함께 업데이트하여 데이터 증발 방지
    for sid, d in dones.items():
        ss[f"chk_{sid}"] = d
        ss[f"backup_chk_{sid}"] = d
        
    # 이전 수정 폼 입력값 초기화
    for k in [k for k in ss.keys() if str(k).startswith(
            ("inp_name_", "inp_time_", "inp_start_", "inp_end_", "inp_day_", "inp_tip_"))]:
        del ss[k]
    ss.trip_title = str(data.get("page_title") or DEFAULT_TITLE)
    ss["title_input"] = ss.trip_title


def save_filename() -> str:
    name = str(st.session_state.get("save_name", "")).strip() or "chuncheon_trip"
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    return name if name.lower().endswith(".json") else f"{name}.json"


# ---- 콜백 ----
def delete_spot(sid: str) -> None:
    ss = st.session_state
    ss.spots_data = [s for s in ss.spots_data if s["id"] != sid]
    ss.editing_flags.pop(sid, None)
    stale = [k for k in ss.keys()
             if k == f"chk_{sid}" or k == f"backup_chk_{sid}" or (str(k).startswith("inp_") and str(k).endswith(f"_{sid}"))]
    for k in stale:
        del ss[k]


def sync_title() -> None:
    # 입력창(title_input) 값을 실제 제목(trip_title)으로 옮김
    st.session_state.trip_title = st.session_state.get("title_input", DEFAULT_TITLE)


def load_from_upload() -> None:
    f = st.session_state.get("upload_file")
    if f is None:
        st.session_state.msg = "⚠️ 불러올 파일을 먼저 선택해 주세요."
        return
    try:
        apply_payload(json.load(f))
        st.session_state.msg = "⬆️ 파일에서 일정을 불러왔어요."
    except Exception:
        st.session_state.msg = "⚠️ 올바른 일정 파일이 아니에요."


# ---- 공유 저장소 (Firebase Realtime Database REST API) ----
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
        method="PUT",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception:
        return False


def canon(payload: dict) -> str:
    """비교용 문자열 (저장 시각은 제외)"""
    return json.dumps({k: v for k, v in payload.items() if k != "saved_at"},
                      ensure_ascii=False, sort_keys=True)


# ---- 세션 초기화 ----
if "spots_data" not in st.session_state:
    st.session_state.spots_data = copy.deepcopy(DEFAULT_SPOTS)
    st.session_state.editing_flags = {}
    st.session_state.trip_title = DEFAULT_TITLE

# 공유 데이터 최초 불러오기
if "synced_json" not in st.session_state:
    st.session_state.synced_json = None
    _ok, _remote = fetch_remote()
    if _ok:
        if _remote is None:
            st.session_state.synced_json = canon(build_payload())
        else:
            try:
                apply_payload(_remote)
                st.session_state.synced_json = canon(build_payload())
            except Exception:
                pass

st.set_page_config(
    page_title=st.session_state.get("trip_title", DEFAULT_TITLE).strip() or DEFAULT_TITLE,
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 모바일/태블릿 최적화 초경량 슬림 스타일
CSS = """
<style>
    .block-container {padding: 1rem 0.6rem 2rem 0.6rem !important;}
    .stCheckbox label {font-size: 0.92rem !important; font-weight: 700 !important; cursor: pointer; color: #111827;}
    .stCheckbox {margin-bottom: 0 !important;}

    /* ---- 일정 카드: 위/아래 여백 균형 ---- */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0.3rem 0.75rem 0.3rem 0.75rem !important;
        margin-bottom: 0.4rem !important;
        border-radius: 10px !important;
    }
    [class*="st-key-card_"] [data-testid="stVerticalBlock"] {gap: 0.3rem !important;}
    [class*="st-key-card_"] [data-testid="stCaptionContainer"] {
        font-size: 0.78rem !important; color: #4B5563 !important; line-height: 1.3 !important;
        padding-left: 2px;
    }

    /* 카드 내부: 모바일에서도 가로 배치 유지 */
    [class*="st-key-card_"] [data-testid="stHorizontalBlock"] {
        flex-direction: row !important; flex-wrap: nowrap !important;
        gap: 0.4rem !important; align-items: flex-start !important;
    }
    [class*="st-key-card_"] [data-testid="stColumn"],
    [class*="st-key-card_"] [data-testid="column"] {min-width: 0 !important;}

    /* 헤더 줄: [체크박스 고정] [장소명(링크) 가변] [✏️][🗑️] 고정폭 */
    [class*="st-key-hdr_"] [data-testid="stHorizontalBlock"] {gap: 0.1rem !important;}
    [class*="st-key-hdr_"] [data-testid="stColumn"]:nth-child(1),
    [class*="st-key-hdr_"] [data-testid="column"]:nth-child(1) {flex: 0 0 1.8rem !important; width: 1.8rem !important;}
    [class*="st-key-hdr_"] [data-testid="stColumn"]:nth-child(2),
    [class*="st-key-hdr_"] [data-testid="column"]:nth-child(2) {flex: 1 1 0 !important; width: auto !important;}
    [class*="st-key-hdr_"] [data-testid="stColumn"]:nth-child(n+3),
    [class*="st-key-hdr_"] [data-testid="column"]:nth-child(n+3) {flex: 0 0 1.2rem !important; width: 1.2rem !important;}
    /* 수정(✏️)과 삭제(🗑️) 사이 간격 */
    [class*="st-key-hdr_"] [data-testid="stColumn"]:nth-child(4),
    [class*="st-key-hdr_"] [data-testid="column"]:nth-child(4) {margin-left: 0.65rem !important;}

    /* 삭제 팝오버 버튼: 화살표 아이콘 제거, 이모지 가운데 정렬 */
    [class*="st-key-btn_del_"] button svg,
    [class*="st-key-btn_del_"] button [data-testid="stIconMaterial"] {display: none !important;}
    [class*="st-key-btn_del_"] button {justify-content: center !important;}

    /* 장소명 링크 (네이버 검색) */
    a.spot-name {color: #1E3A8A; font-weight: 700; font-size: 0.92rem; text-decoration: underline;
                 text-underline-offset: 2px; line-height: 1.5; display: inline-block; margin-top: 0.35rem;}

    /* 수정(✏️) · 삭제(🗑️) 아이콘 버튼 */
    [class*="st-key-btn_edit_"] button, [class*="st-key-btn_del_"] button {
        min-height: 1.9rem !important; height: 1.9rem !important; width: 100% !important;
        padding: 0 !important; border: none !important; background: transparent !important;
    }

    /* 하단 버튼 바: 모바일에서도 한 줄 유지 */
    .st-key-topbar [data-testid="stHorizontalBlock"] {
        flex-direction: row !important; flex-wrap: nowrap !important; gap: 0.4rem !important;
    }
    .st-key-topbar [data-testid="stColumn"], .st-key-topbar [data-testid="column"] {min-width: 0 !important;}
    .st-key-topbar button {padding-left: 0.3rem !important; padding-right: 0.3rem !important; white-space: nowrap;}

    /* 여행 제목 */

    /* 지도: 정사각형 비율 */
    .st-key-mapbox {margin-bottom: 0 !important;}
    /* 진행률 바: 지도와의 간격을 줄이기 위해 위로 당김 */
    .st-key-progress_wrap {margin-top: -2.8rem !important;}
    .st-key-mapbox iframe {width: 100% !important; aspect-ratio: 1 / 1;}
</style>
"""
TIME_SLOTS = [f"{h:02d}:{m:02d}" for h in range(5, 24) for m in (0, 30)]
DAY_PALETTE = [("#EFF6FF", "#60A5FA"), ("#FFF7ED", "#FB923C"), ("#F0FDF4", "#4ADE80"),
               ("#FAF5FF", "#C084FC"), ("#FEF2F2", "#F87171"), ("#FEFCE8", "#FACC15")]


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


def day_color_css() -> str:
    rules = []
    for d in sorted({int(s["day"]) for s in st.session_state.spots_data}):
        bg, bd = DAY_PALETTE[(max(d, 1) - 1) % len(DAY_PALETTE)]
        sel = f'[class*="st-key-card_d{d}_"]'
        rules.append(f'{sel}, {sel} [data-testid="stVerticalBlockBorderWrapper"] '
                     f'{{background:{bg} !important; border-color:{bd} !important;}}')
    return "<style>" + "\n".join(rules) + "</style>"


st.markdown(CSS + day_color_css(), unsafe_allow_html=True)

# ===== 체크박스 리셋 방지 로직 (편집 모드 시 데이터 증발 방지) =====
for s in st.session_state.spots_data:
    sid = s["id"]
    chk_key = f"chk_{sid}"
    bak_key = f"backup_chk_{sid}"
    
    if chk_key in st.session_state:
        st.session_state[bak_key] = st.session_state[chk_key]
    elif bak_key in st.session_state:
        st.session_state[chk_key] = st.session_state[bak_key]
    else:
        st.session_state.setdefault(chk_key, False)
        st.session_state.setdefault(bak_key, False)
        
    st.session_state.editing_flags.setdefault(sid, False)
# =========================================================

# 지도 템플릿
MAP_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        html, body, #map {
            height: 100%;
            width: 100%;
            margin: 0;
            padding: 0;
            border-radius: 12px;
            position: relative;
        }
        .custom-pin {
            border-radius: 50%;
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 11px;
            border: 2px solid white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }
        .pin-done { background-color: #16A34A; }
        .pin-yet { background-color: #2563EB; }

        .location-btn {
            position: absolute;
            top: 10px;
            right: 10px;
            z-index: 1000;
            background: white;
            border: none;
            width: 40px;
            height: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.3);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            outline: none;
        }
        .location-btn svg { width: 22px; height: 22px; fill: #4B5563; }
        .location-btn.active svg { fill: #2563EB; }

        .user-pulse {
            width: 16px;
            height: 16px;
            background-color: #2563EB;
            border: 2px solid white;
            border-radius: 50%;
            box-shadow: 0 0 8px rgba(37,99,235,0.8);
            position: relative;
        }
        .user-pulse::after {
            content: '';
            position: absolute;
            top: -5px;
            left: -5px;
            width: 22px;
            height: 22px;
            border-radius: 50%;
            border: 2px solid #2563EB;
            animation: pulse 1.6s infinite ease-out;
            opacity: 0;
        }
        @keyframes pulse {
            0% { transform: scale(0.5); opacity: 1; }
            100% { transform: scale(1.8); opacity: 0; }
        }
    </style>
</head>
<body>
    <div id="map">
        <button class="location-btn" id="locBtn" onclick="findMyLocation()" title="내 위치로 이동">
            <svg viewBox="0 0 24 24">
                <path d="M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm8.94 3c-.46-4.17-3.77-7.48-7.94-7.94V1h-2v2.06C6.83 3.52 3.52 6.83 3.06 11H1v2h2.06c.46 4.17 3.77 7.48 7.94 7.94V23h2v-2.06c4.17-.46 7.48-3.77 7.94-7.94H23v-2h-2.06zM12 19c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"/>
            </svg>
        </button>
    </div>

    <script>
        const SPOTS = __SPOTS_JSON__;
        const esc = t => String(t == null ? '' : t).replace(/[&<>"']/g,
            c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

        const map = L.map('map', {
            zoomControl: true,
            attributionControl: false
        }).setView([37.9150, 127.7550], 11);

        L.tileLayer('https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', {
            maxZoom: 19
        }).addTo(map);

        const allCoords = SPOTS.map(s => [s.lat, s.lon]);
        if (allCoords.length > 0) {
            L.polyline(allCoords, {
                color: '#64748B',
                weight: 3,
                dashArray: '6, 8',
                opacity: 0.65
            }).addTo(map);
        }

        const visitedCoords = SPOTS.filter(s => s.done).map(s => [s.lat, s.lon]);
        if (visitedCoords.length >= 2) {
            L.polyline(visitedCoords, {
                color: '#2563EB',
                weight: 6,
                opacity: 0.95
            }).addTo(map);
        }

        const bounds = [];
        SPOTS.forEach((spot, i) => {
            bounds.push([spot.lat, spot.lon]);
            const pinClass = spot.done ? 'custom-pin pin-done' : 'custom-pin pin-yet';
            const iconSymbol = spot.done ? '✓' : (i + 1);

            const icon = L.divIcon({
                className: '',
                html: '<div class="' + pinClass + '">' + iconSymbol + '</div>',
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            });

            const statusText = spot.done
                ? "<span style='color:#16A34A;font-weight:bold;'>🎉 방문 완료</span>"
                : "<span style='color:#2563EB;font-weight:bold;'>⏳ 예정지</span>";

            const popupContent =
                '<div style="font-family:-apple-system,BlinkMacSystemFont,sans-serif; min-width:160px;">' +
                    '<b style="font-size:13px;color:#1E3A8A;">' + esc(spot.name) + '</b><br>' +
                    statusText +
