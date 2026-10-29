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
    
