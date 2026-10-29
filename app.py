import json
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="춘천 실시간 여행 트래커",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 모바일 화면 최적화 스타일
CSS = """
<style>
    .block-container {padding: 1.2rem 0.8rem 2rem 0.8rem !important;}
    .stCheckbox label {font-size: 1.05rem !important; font-weight: 600 !important; cursor: pointer;}
    .badge {display:inline-block; padding:.2rem .6rem; border-radius:9999px;
            font-size:.8rem; font-weight:700; margin-right:.4rem;}
    .done {background:#DCFCE7; color:#15803D;}
    .yet  {background:#F1F5F9; color:#64748B;}
    .cat  {font-size:.85rem; color:#2563EB; font-weight:600;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# 여행 코스 데이터
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

# 세션 초기화
for k in KEYS:
    st.session_state.setdefault(k, False)

def set_all(value: bool) -> None:
    for k in KEYS:
        st.session_state[k] = value

# ---------- 웹 임베디드 구글 지도 (API 키 없이 iOS/안드로이드 완벽 지원) ----------
def render_embedded_google_map(done_states: list[bool]) -> None:
    data = [
        {
            "name": s["name"],
            "lat": s["lat"],
            "lon": s["lon"],
            "desc": s["desc"],
            "tip": s["tip"],
            "done": d
        }
        for s, d in zip(SPOTS, done_states)
    ]
    spots_json = json.dumps(data, ensure_ascii=False)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            html, body, #map {{
                height: 100%;
                width: 100%;
                margin: 0;
                padding: 0;
                border-radius: 12px;
            }}
            .custom-pin {{
                border-radius: 50%;
                width: 26px;
                height: 26px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
                font-size: 13px;
                border: 2px solid white;
                box-shadow: 0 2px 5px rgba(0,0,0,0.4);
            }}
            .pin-done {{ background-color: #16A34A; }}
            .pin-yet {{ background-color: #2563EB; }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        <script>
            const SPOTS = {spots_json};

            // 1. 지도 생성
            const map = L.map('map', {{
                zoomControl: true,
                attributionControl: false
            }}).setView([37.9150, 127.7550], 11);

            // 2. 실제 Google Maps 도로 지도 타일 레이어 연동
            L.tileLayer('https://mt1.google.com/vt/lyrs=m&x={{x}}&y={{y}}&z={{z}}', {{
                maxZoom: 19
            }}).addTo(map);

            // 3. 전체 예정 코스 점선 연결
            const allCoords = SPOTS.map(s => [s.lat, s.lon]);
            L.polyline(allCoords, {{
                color: '#64748B',
                weight: 3,
                dashArray: '6, 8',
                opacity: 0.65
            }}).addTo(map);

            // 4. 방문 완료된 구간 실시간 파란색 굵은 실선 연결
            const visitedCoords = SPOTS.filter(s => s.done).map(s => [s.lat, s.lon]);
            if (visitedCoords.length >= 2) {{
                L.polyline(visitedCoords, {{
                    color: '#2563EB',
                    weight: 6,
                    opacity: 0.95
                }}).addTo(map);
            }}

            // 5. 마커 핀 및 상세 팝업창
            const bounds = [];
            SPOTS.forEach((spot, i) => {{
                bounds.push([spot.lat, spot.lon]);
                const pinClass = spot.done ? 'custom-pin pin-done' : 'custom-pin pin-yet';
                const iconSymbol = spot.done ? '✓' : (i + 1);

                const icon = L.divIcon({{
                    className: '',
                    html: `<div class="${{pinClass}}">${{iconSymbol}}</div>`,
                    iconSize: [26, 26],
                    iconAnchor: [13, 13]
                }});

                const statusText = spot.done 
                    ? "<span style='color:#16A34A;font-weight:bold;'>🎉 방문 완료</span>" 
                    : "<span style='color:#2563EB;font-weight:bold;'>⏳ 예정지</span>";

                const popupContent = `
                    <div style="font-family:-apple-system,BlinkMacSystemFont,sans-serif; min-width:170px;">
                        <b style="font-size:14px;color:#1E3A8A;">${{spot.name}}</b><br>
                        ${{statusText}}
                        <p style="margin:4px 0;font-size:12px;color:#334155;">${{spot.desc}}</p>
                        <div style="background:#FEF3C7;color:#B45309;padding:3px 6px;border-radius:4px;font-size:11px;">
                            💡 ${{spot.tip}}
                        </div>
                    </div>
                `;

                L.marker([spot.lat, spot.lon], {{ icon: icon }})
                    .bindPopup(popupContent)
                    .addTo(map);
            }});

            map.fitBounds(bounds, {{ padding: [30, 30] }});
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=490)

# ---------- Streamlit 화면 구성 ----------
st.title("🚗 춘천 실시간 여행 트래커")
st.caption("📱 일정 체크 시 앱 화면 안의 구글 지도에 완료 이동 경로(실선)가 실시간으로 연결됩니다.")

col_map, col_ctrl = st.columns([1.3, 1.0])

done_flags = [st.session_state[k] for k in KEYS]
n_done = sum(done_flags)

# 컨트롤 영역
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

# 지도 영역
with col_map:
    st.progress(n_done / len(SPOTS),
                text=f"진행률: {n_done} / {len(SPOTS)} 코스 완료 ({n_done * 100 // len(SPOTS)}%)")
    render_embedded_google_map(done_flags)
