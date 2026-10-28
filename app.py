import folium
import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(
    page_title="춘천 실시간 여행 트래커",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CSS = """
<style>
    .block-container {padding: 1.5rem 1rem 2rem 1rem !important;}
    .stCheckbox label {font-size: 1.05rem !important; font-weight: 600 !important;}
    .badge {display:inline-block; padding:.2rem .6rem; border-radius:9999px;
            font-size:.8rem; font-weight:700; margin-right:.4rem;}
    .done {background:#DCFCE7; color:#15803D;}
    .yet  {background:#F1F5F9; color:#64748B;}
    .cat  {font-size:.85rem; color:#2563EB; font-weight:600;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

SPOTS = [
    dict(id="legoland", day=1, name="1. 레고랜드 코리아", category="테마파크 (종일)",
         lat=37.8845, lon=127.6975, desc="하중도 위치 테마파크 탐방",
         tip="오전 인기 어트랙션 집중 공략"),
    dict(id="soyang_dam", day=2, name="2. 소양호 유람선터미널", category="유람선 탑승 (09:30~10:00)",
         lat=37.9547, lon=127.8184, desc="청평사행 도선 승선 (편도 15분)",
         tip="댐 정상 주차장 09:30 전 도착 권장"),
    dict(id="cheongpyeongsa", day=2, name="3. 청평사 경내", category="고찰 트레킹 (10:15~11:45)",
         lat=37.9877, lon=127.8136, desc="구성폭포 및 오봉산 산책로 관람",
         tip="선착장 ↔ 절 왕복 약 1시간 도보"),
    dict(id="sambath", day=2, name="4. 샘밭막국수", category="점심 식사 (12:30~13:30)",
         lat=37.9317, lon=127.7656, desc="담백한 전통 메밀막국수 & 편육",
         tip="소양강댐에서 차로 5분 거리 위치"),
    dict(id="cablecar", day=2, name="5. 삼악산 호수케이블카", category="스카이워크 (14:00~15:30)",
         lat=37.8548, lon=127.6970, desc="국내 최장 3.61km 케이블카 & 의암호 전망",
         tip="의암호 정차장에서 서울/수도권 복귀 직결"),
]

KEYS = [f"chk_{s['id']}" for s in SPOTS]
ALL_COORDS = [[s["lat"], s["lon"]] for s in SPOTS]

# 체크박스 key 자체를 단일 상태 저장소로 사용 (별도 dict 불필요)
for k in KEYS:
    st.session_state.setdefault(k, False)


def set_all(value: bool) -> None:
    for k in KEYS:
        st.session_state[k] = value


def build_map(done: list[bool]) -> folium.Map:
    m = folium.Map(location=[37.9150, 127.7550], zoom_start=11, tiles="CartoDB positron")

    folium.PolyLine(ALL_COORDS, color="#94A3B8", weight=3, opacity=0.6,
                    dash_array="6, 6", tooltip="전체 예정 이동 동선").add_to(m)

    visited = [c for c, d in zip(ALL_COORDS, done) if d]
    if len(visited) >= 2:
        folium.PolyLine(visited, color="#2563EB", weight=6, opacity=0.9,
                        tooltip="🚩 완료된 이동 경로").add_to(m)

    for spot, is_done in zip(SPOTS, done):
        status = "🎉 방문 완료" if is_done else "⏳ 예정지"
        popup = (
            f"<div style='font-family:sans-serif;width:180px'>"
            f"<b style='color:#1E3A8A;font-size:14px'>{spot['name']}</b><br>"
            f"<span style='font-size:11px;color:#059669;font-weight:bold'>{status}</span>"
            f"<p style='margin:4px 0;font-size:11px;color:#475569'>{spot['desc']}</p>"
            f"<div style='background:#FEF3C7;color:#B45309;padding:3px;border-radius:4px;"
            f"font-size:10px'>{spot['tip']}</div></div>"
        )
        folium.Marker(
            [spot["lat"], spot["lon"]],
            tooltip=f"{spot['name']} ({status})",
            popup=folium.Popup(popup, max_width=220),
            icon=folium.Icon(color="green" if is_done else "blue",
                             icon="ok-sign" if is_done else "map-marker",
                             prefix="glyphicon"),
        ).add_to(m)
    return m


st.title("🚗 춘천 실시간 여행 트래커")
st.caption("📱 장소 방문을 체크하면 지도에 이동 완료 경로(실선)가 실시간으로 연결됩니다.")

col_map, col_ctrl = st.columns([1.3, 1.0])

with col_ctrl:
    st.subheader("🚩 방문 일정 체크")
    b1, b2 = st.columns(2)
    b1.button("🔄 전체 초기화", on_click=set_all, args=(False,), use_container_width=True)
    b2.button("✅ 모두 완료", on_click=set_all, args=(True,), use_container_width=True)

    for spot, key in zip(SPOTS, KEYS):
        checked = st.session_state[key]
        badge = ('<span class="badge done">✓ 방문 완료</span>' if checked
                 else '<span class="badge yet">대기 중</span>')
        with st.container(border=True):
            st.markdown(
                f'{badge}<small style="color:#64748B">Day {spot["day"]}</small>'
                f'<div class="cat">{spot["category"]}</div>',
                unsafe_allow_html=True,
            )
            st.checkbox(spot["name"], key=key)
            st.caption(f"💡 {spot['tip']}")

done_flags = [st.session_state[k] for k in KEYS]
n_done = sum(done_flags)

with col_map:
    st.progress(n_done / len(SPOTS),
                text=f"진행률: {n_done} / {len(SPOTS)} 코스 완료 ({n_done * 100 // len(SPOTS)}%)")
    # returned_objects=[] → 지도 이동/확대 시 불필요한 앱 재실행 방지
    st_folium(build_map(done_flags), height=480, use_container_width=True,
              returned_objects=[], key="trip_map")
