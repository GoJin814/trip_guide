import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="춘천 실시간 여행 트래커",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CSS = """
<style>
    .block-container {padding: 1rem 0.7rem 1.5rem 0.7rem !important;}
    [data-testid="stVerticalBlock"] {gap: 0.55rem;}
    /* 버튼 행만 모바일에서도 가로 유지 */
    .st-key-btnrow [data-testid="stHorizontalBlock"] {
        flex-direction: row !important; flex-wrap: nowrap !important; gap: 0.5rem;
    }
    .st-key-btnrow [data-testid="stColumn"], .st-key-btnrow [data-testid="column"] {
        min-width: 0 !important; width: auto !important; flex: 1 1 0 !important;
    }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------- 데이터
DATA_FILE = Path(__file__).with_name("trip_data.json")
COLS = ["완료", "Day", "장소", "시간/분류", "설명", "팁", "위도", "경도"]
TEXT_COLS = ["장소", "시간/분류", "설명", "팁"]

DEFAULTS = [
    dict(완료=False, Day=1, 장소="레고랜드 코리아", **{"시간/분류": "테마파크 (종일)"},
         설명="하중도 위치 테마파크 탐방", 팁="오전 인기 어트랙션 집중 공략", 위도=37.8845, 경도=127.6975),
    dict(완료=False, Day=2, 장소="소양호 유람선터미널", **{"시간/분류": "유람선 09:30~10:00"},
         설명="청평사행 도선 승선 (편도 15분)", 팁="댐 정상 주차장 09:30 전 도착 권장", 위도=37.9547, 경도=127.8184),
    dict(완료=False, Day=2, 장소="청평사 경내", **{"시간/분류": "트레킹 10:15~11:45"},
         설명="구성폭포 및 오봉산 산책로 관람", 팁="선착장 ↔ 절 왕복 약 1시간 도보", 위도=37.9877, 경도=127.8136),
    dict(완료=False, Day=2, 장소="샘밭막국수", **{"시간/분류": "점심 12:30~13:30"},
         설명="담백한 전통 메밀막국수 & 편육", 팁="소양강댐에서 차로 5분 거리", 위도=37.9317, 경도=127.7656),
    dict(완료=False, Day=2, 장소="삼악산 호수케이블카", **{"시간/분류": "스카이워크 14:00~15:30"},
         설명="국내 최장 3.61km 케이블카 & 의암호 전망", 팁="의암호 정차장에서 서울/수도권 복귀 직결",
         위도=37.8548, 경도=127.6970),
]


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reindex(columns=COLS)
    df["완료"] = df["완료"].fillna(False).astype(bool)
    for c in TEXT_COLS:
        df[c] = df[c].fillna("").astype(str)
    df["Day"] = pd.to_numeric(df["Day"], errors="coerce").astype("Int64")
    for c in ("위도", "경도"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.reset_index(drop=True)


def to_json(df: pd.DataFrame) -> str:
    return df.to_json(orient="records", force_ascii=False, indent=1)


def load_df() -> pd.DataFrame:
    try:
        return clean(pd.DataFrame(json.loads(DATA_FILE.read_text("utf-8"))))
    except Exception:
        return clean(pd.DataFrame(DEFAULTS))


def save_df(df: pd.DataFrame) -> None:
    try:
        DATA_FILE.write_text(to_json(df), "utf-8")
    except OSError:
        pass


if "base" not in st.session_state:
    st.session_state.base = load_df()
    st.session_state.saved = st.session_state.base.copy()


def set_all(value: bool) -> None:
    df = st.session_state.cur.copy()
    df["완료"] = value
    st.session_state.base = df
    st.session_state.pop("editor", None)


def restore() -> None:
    f = st.session_state.get("upload")
    if f is None:
        return
    try:
        st.session_state.base = clean(pd.DataFrame(json.load(f)))
        st.session_state.pop("editor", None)
        st.session_state.msg = "✅ 백업을 불러왔습니다."
    except Exception:
        st.session_state.msg = "⚠️ 올바른 백업 파일이 아닙니다."


# ---------------------------------------------------------------- 지도
MAP_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body, #map {height:100%; width:100%; margin:0; padding:0; border-radius:12px;}
  .custom-pin {border-radius:50%; width:26px; height:26px; display:flex; align-items:center;
    justify-content:center; color:#fff; font-weight:bold; font-size:13px; border:2px solid #fff;
    box-shadow:0 2px 5px rgba(0,0,0,.4);}
  .pin-done {background:#16A34A;} .pin-yet {background:#2563EB;}
  .location-btn {position:absolute; top:12px; right:12px; z-index:1000; background:#fff; border:none;
    width:44px; height:44px; border-radius:8px; box-shadow:0 2px 6px rgba(0,0,0,.3);
    display:flex; align-items:center; justify-content:center; cursor:pointer; outline:none;}
  .location-btn:active {background:#F1F5F9;}
  .location-btn svg {width:24px; height:24px; fill:#4B5563;}
  .location-btn.active svg {fill:#2563EB;}
  .user-pulse {width:18px; height:18px; background:#2563EB; border:3px solid #fff; border-radius:50%;
    box-shadow:0 0 10px rgba(37,99,235,.8); position:relative;}
  .user-pulse::after {content:''; position:absolute; top:-6px; left:-6px; width:24px; height:24px;
    border-radius:50%; border:2px solid #2563EB; animation:pulse 1.6s infinite ease-out; opacity:0;}
  @keyframes pulse {0% {transform:scale(.5); opacity:1;} 100% {transform:scale(1.8); opacity:0;}}
</style>
</head>
<body>
<div id="map" style="position:relative">
  <button class="location-btn" id="locBtn" onclick="findMyLocation()" title="내 위치로 이동">
    <svg viewBox="0 0 24 24"><path d="M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm8.94 3c-.46-4.17-3.77-7.48-7.94-7.94V1h-2v2.06C6.83 3.52 3.52 6.83 3.06 11H1v2h2.06c.46 4.17 3.77 7.48 7.94 7.94V23h2v-2.06c4.17-.46 7.48-3.77 7.94-7.94H23v-2h-2.06zM12 19c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"/></svg>
  </button>
</div>
<script>
  const SPOTS = __SPOTS_JSON__;
  const esc = t => String(t == null ? '' : t).replace(/[&<>"']/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  const map = L.map('map', {zoomControl:true, attributionControl:false}).setView([37.9150, 127.7550], 11);
  L.tileLayer('https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', {maxZoom:19}).addTo(map);

  const allCoords = SPOTS.map(s => [s.lat, s.lon]);
  L.polyline(allCoords, {color:'#64748B', weight:3, dashArray:'6, 8', opacity:.65}).addTo(map);
  const visited = SPOTS.filter(s => s.done).map(s => [s.lat, s.lon]);
  if (visited.length >= 2) L.polyline(visited, {color:'#2563EB', weight:6, opacity:.95}).addTo(map);

  SPOTS.forEach((s, i) => {
    const icon = L.divIcon({className:'',
      html:'<div class="custom-pin ' + (s.done ? 'pin-done' : 'pin-yet') + '">' + (s.done ? '✓' : (i + 1)) + '</div>',
      iconSize:[26,26], iconAnchor:[13,13]});
    const status = s.done
      ? "<span style='color:#16A34A;font-weight:bold'>🎉 방문 완료</span>"
      : "<span style='color:#2563EB;font-weight:bold'>⏳ 예정지</span>";
    const popup = '<div style="font-family:-apple-system,sans-serif;min-width:170px">' +
      '<b style="font-size:14px;color:#1E3A8A">' + esc(s.name) + '</b><br>' + status +
      '<div style="font-size:12px;color:#2563EB;margin-top:2px">' + esc(s.cat) + '</div>' +
      '<p style="margin:4px 0;font-size:12px;color:#334155">' + esc(s.desc) + '</p>' +
      (s.tip ? '<div style="background:#FEF3C7;color:#B45309;padding:3px 6px;border-radius:4px;font-size:11px">💡 ' + esc(s.tip) + '</div>' : '') +
      '</div>';
    L.marker([s.lat, s.lon], {icon:icon}).bindPopup(popup).addTo(map);
  });
  if (allCoords.length) map.fitBounds(allCoords, {padding:[35,35]});

  let userMarker = null, userCircle = null;
  function findMyLocation() {
    const btn = document.getElementById('locBtn');
    if (!navigator.geolocation) { alert('이 기기에서는 위치 서비스를 지원하지 않습니다.'); return; }
    btn.classList.add('active');
    navigator.geolocation.getCurrentPosition(function(pos) {
      const lat = pos.coords.latitude, lon = pos.coords.longitude, acc = pos.coords.accuracy;
      if (userMarker) map.removeLayer(userMarker);
      if (userCircle) map.removeLayer(userCircle);
      const ui = L.divIcon({className:'', html:'<div class="user-pulse"></div>', iconSize:[18,18], iconAnchor:[9,9]});
      userMarker = L.marker([lat, lon], {icon:ui}).addTo(map)
        .bindPopup('<b>📍 현재 내 위치</b><br><small>정확도 약 ' + Math.round(acc) + 'm</small>').openPopup();
      userCircle = L.circle([lat, lon], {radius:acc, color:'#3B82F6', weight:1, fillColor:'#93C5FD', fillOpacity:.15}).addTo(map);
      map.flyTo([lat, lon], 14, {animate:true, duration:1.2});
    }, function() {
      btn.classList.remove('active');
      alert('위치 정보를 가져올 수 없습니다. 브라우저의 위치 권한을 확인해 주세요.');
    }, {enableHighAccuracy:true, timeout:10000, maximumAge:0});
  }
</script>
</body>
</html>
"""


def render_map(geo: pd.DataFrame) -> None:
    spots = [
        dict(name=r["장소"], cat=r["시간/분류"], desc=r["설명"], tip=r["팁"],
             lat=float(r["위도"]), lon=float(r["경도"]), done=bool(r["완료"]))
        for r in geo.to_dict("records")
    ]
    payload = json.dumps(spots, ensure_ascii=False).replace("</", "<\\/")
    components.html(MAP_TEMPLATE.replace("__SPOTS_JSON__", payload), height=430)


# ---------------------------------------------------------------- 화면
st.markdown("#### 🚗 춘천 실시간 여행 트래커")

col_map, col_ctrl = st.columns([1.3, 1.0])

with col_ctrl:
    with st.container(key="btnrow"):
        b1, b2 = st.columns(2)
        b1.button("🔄 전체 초기화", on_click=set_all, args=(False,), use_container_width=True)
        b2.button("✅ 모두 완료", on_click=set_all, args=(True,), use_container_width=True)

    detail = st.toggle("📝 설명·팁·좌표까지 편집", value=False)

    edited = st.data_editor(
        st.session_state.base,
        key="editor",
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        column_order=COLS if detail else ["완료", "Day", "장소", "시간/분류"],
        column_config={
            "완료": st.column_config.CheckboxColumn("✓", width="small"),
            "Day": st.column_config.NumberColumn("Day", min_value=1, step=1, format="%d", width="small"),
            "장소": st.column_config.TextColumn("장소", width="medium"),
            "시간/분류": st.column_config.TextColumn("시간/분류", width="medium"),
            "설명": st.column_config.TextColumn("설명", width="large"),
            "팁": st.column_config.TextColumn("💡 팁", width="large"),
            "위도": st.column_config.NumberColumn("위도", format="%.4f", min_value=-90.0, max_value=90.0),
            "경도": st.column_config.NumberColumn("경도", format="%.4f", min_value=-180.0, max_value=180.0),
        },
    )
    edited = clean(edited)
    st.session_state.cur = edited

    # 수정 즉시 자동 저장
    if not edited.equals(st.session_state.saved):
        save_df(edited)
        st.session_state.saved = edited.copy()

    st.caption("셀을 두 번 탭하면 수정 · 맨 아래 빈 줄에서 일정 추가 · 행 선택 후 🗑️로 삭제")

    with st.expander("💾 백업 / 복원"):
        st.download_button("백업 파일 받기", to_json(edited), "trip_data.json",
                           "application/json", use_container_width=True)
        st.file_uploader("백업 파일 선택", type="json", key="upload")
        st.button("불러오기", on_click=restore, use_container_width=True)
        if st.session_state.get("msg"):
            st.info(st.session_state.pop("msg"))

valid = edited[edited["장소"].str.strip() != ""]
geo = valid.dropna(subset=["위도", "경도"])
n_total = len(valid)
n_done = int(valid["완료"].sum())

with col_map:
    st.progress(n_done / n_total if n_total else 0.0,
                text=f"진행률 {n_done} / {n_total} 완료 ({n_done * 100 // n_total if n_total else 0}%)")

    upcoming = valid[~valid["완료"]]
    if len(upcoming):
        r = upcoming.iloc[0]
        tip = f" — 💡 {r['팁']}" if r["팁"] else ""
        st.info(f"👉 다음: **{r['장소']}** · {r['시간/분류']}{tip}")
    elif n_total:
        st.success("🎉 모든 일정을 완료했어요!")

    render_map(geo)
