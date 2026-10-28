import streamlit as st
import folium
from streamlit_folium import st_folium

# 모바일 반응형 페이지 설정
st.set_page_config(
    page_title="춘천 실시간 여행 트래커",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 모바일 터치 최적화 스타일
st.markdown("""
<style>
    .stCheckbox > label {
        font-size: 1.05rem !important;
        font-weight: 600 !important;
        cursor: pointer;
        padding: 4px 0;
    }
    .status-badge {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 700;
        margin-bottom: 0.3rem;
    }
    .badge-done { background-color: #DCFCE7; color: #15803D; }
    .badge-yet { background-color: #F1F5F9; color: #64748B; }
    .card-box {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 0.8rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
</style>
""", unsafe_allow_html=True)

# 여행 목적지 데이터 (순서대로 배치)
SPOTS = [
    {
        "id": "legoland",
        "day": 1,
        "name": "1. 레고랜드 코리아",
        "category": "테마파크 (종일)",
        "lat": 37.8845,
        "lon": 127.6975,
        "desc": "하중도 위치 테마파크 탐방",
        "tip": "오전 인기 어트랙션 집중 공략"
    },
    {
        "id": "soyang_dam",
        "day": 2,
        "name": "2. 소양호 유람선터미널",
        "category": "유람선 탑승 (09:30~10:00)",
        "lat": 37.9547,
        "lon": 127.8184,
        "desc": "청평사행 도선 승선 (편도 15분)",
        "tip": "댐 정상 주차장 09:30 전 도착 권장"
    },
    {
        "id": "cheongpyeongsa",
        "day": 2,
        "name": "3. 청평사 경내",
        "category": "고찰 트레킹 (10:15~11:45)",
        "lat": 37.9877,
        "lon": 127.8136,
        "desc": "구성폭포 및 오봉산 산책로 관람",
        "tip": "선착장 ↔ 절 왕복 약 1시간 도보"
    },
    {
        "id": "sambath",
        "day": 2,
        "name": "4. 샘밭막국수",
        "category": "점심 식사 (12:30~13:30)",
        "lat": 37.9317,
        "lon": 127.7656,
        "desc": "담백한 전통 메밀막국수 & 편육",
        "tip": "소양강댐에서 차로 5분 거리 위치"
    },
    {
        "id": "cablecar",
        "day": 2,
        "name": "5. 삼악산 호수케이블카",
        "category": "스카이워크 (14:00~15:30)",
        "lat": 37.8548,
        "lon": 127.6970,
        "desc": "국내 최장 3.61km 케이블카 & 의암호 전망",
        "tip": "의암호 정차장에서 서울/수도권 복귀 직결"
    }
]

# 세션 상태 관리
if "completed_spots" not in st.session_state:
    st.session_state.completed_spots = {spot["id"]: False for spot in SPOTS}

st.title("🚗 춘천 실시간 여행 트래커")
st.caption("📱 장소 방문을 체크하면 지도에 이동 완료 경로(실선)가 실시간으로 연결됩니다.")

col_map, col_controls = st.columns([1.3, 1.0])

with col_controls:
    st.subheader("🚩 방문 일정 체크")
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("🔄 전체 초기화", use_container_width=True):
            for s in SPOTS:
                st.session_state.completed_spots[s["id"]] = False
            st.rerun()
    with btn_col2:
        if st.button("✅ 모두 완료", use_container_width=True):
            for s in SPOTS:
                st.session_state.completed_spots[s["id"]] = True
            st.rerun()

    st.write("")
    completed_indices = []
    for idx, spot in enumerate(SPOTS):
        spot_id = spot["id"]
        is_checked = st.session_state.completed_spots[spot_id]
        status_badge = (
            '<span class="status-badge badge-done">✓ 방문 완료</span>' 
            if is_checked else 
            '<span class="status-badge badge-yet">대기 중</span>'
        )

        st.markdown(f"""
        <div class="card-box">
            {status_badge} <small style="color:#64748B;">Day {spot['day']}</small>
            <div style="font-size: 0.85rem; color: #2563EB; font-weight: 600;">{spot['category']}</div>
        </div>
        """, unsafe_allow_html=True)
        
        checked = st.checkbox(spot["name"], value=is_checked, key=f"chk_{spot_id}")
        st.session_state.completed_spots[spot_id] = checked
        if checked:
            completed_indices.append(idx)
        st.caption(f"💡 {spot['tip']}")
        st.write("---")

with col_map:
    progress = len(completed_indices) / len(SPOTS)
    st.progress(progress, text=f"진행률: {len(completed_indices)} / {len(SPOTS)} 코스 완료 ({int(progress*100)}%)")

    # 지도 생성
    m = folium.Map(location=[37.9150, 127.7550], zoom_start=11, tiles="CartoDB positron")

    # 전체 예정 경로 (회색 점선)
    all_coords = [[s["lat"], s["lon"]] for s in SPOTS]
    folium.PolyLine(
        locations=all_coords,
        color="#94A3B8",
        weight=3,
        opacity=0.6,
        dash_array="6, 6",
        tooltip="전체 예정 이동 동선"
    ).add_to(m)

    # 방문 완료된 경로 (파란색 굵은 실선)
    if len(completed_indices) >= 2:
        completed_coords = [all_coords[i] for i in sorted(completed_indices)]
        folium.PolyLine(
            locations=completed_coords,
            color="#2563EB",
            weight=6,
            opacity=0.9,
            tooltip="🚩 완료된 이동 경로"
        ).add_to(m)

    # 마커 표시
    for idx, spot in enumerate(SPOTS):
        is_done = st.session_state.completed_spots[spot["id"]]
        marker_color = "green" if is_done else "blue"
        marker_icon = "ok-sign" if is_done else "map-marker"
        status_text = "🎉 방문 완료" if is_done else "⏳ 예정지"
        
        popup_html = f"""
        <div style='font-family: sans-serif; width: 180px;'>
            <b style='color:#1E3A8A; font-size:14px;'>{spot['name']}</b><br>
            <span style='font-size:11px; color:#059669; font-weight:bold;'>{status_text}</span>
            <p style='margin: 4px 0; font-size:11px; color:#475569;'>{spot['desc']}</p>
            <div style='background:#FEF3C7; color:#B45309; padding:3px; border-radius:4px; font-size:10px;'>
                {spot['tip']}
            </div>
        </div>
        """
        folium.Marker(
            location=[spot["lat"], spot["lon"]],
            tooltip=f"{spot['name']} ({status_text})",
            popup=folium.Popup(popup_html, max_width=220),
            icon=folium.Icon(color=marker_color, icon=marker_icon, prefix="glyphicon")
        ).add_to(m)

    st_folium(m, height=480, use_container_width=True)
