import json
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="춘천 실시간 여행 트래커",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 모바일 반응형 스타일
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

# 춘천 여행 목적지 데이터
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

for k in KEYS:
    st.session_state.setdefault(k, False)

def set_all(value: bool) -> None:
    for k in KEYS:
        st.session_state[k] = value

# ---------- 지도 렌더링 템플릿 (f-string 문법 에러 원천 방지) ----------
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
        }
        .pin-done { background-color: #16A34A; }
        .pin-yet { background-color: #2563EB; }
        
        .location-btn {
            position: absolute;
            top: 12px;
            right: 12px;
            z-index: 1000;
            background: white;
            border: none;
            width: 44px;
            height: 44px;
            border-radius: 8px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            outline: none;
        }
        .location-btn:active {
            background: #F1F5F9;
            transform: scale(0.95);
        }
        .location-btn svg {
            width: 24px;
            height: 24px;
            fill: #4B5563;
        }
        .location-btn.active svg {
            fill: #2563EB;
        }

        .user-pulse {
            width: 18px;
            height: 18px;
            background-color: #2563EB;
            border: 3px solid white;
            border-radius: 50%;
            box-shadow: 0 0 10px rgba(37,99,235,0.8);
            position: relative;
        }
        .user-pulse::after {
            content: '';
            position: absolute;
            top: -6px;
            left: -6px;
            width: 24px;
            height: 24px;
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

        const map = L.map('map', {
            zoomControl: true,
            attributionControl: false
        }).setView([37.9150, 127.7550], 11);

        // 구글 지도 타일 레이어
        L.tileLayer('https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', {
            maxZoom: 19
        }).addTo(map);

        // 전체 예정 경로 (점선)
        const allCoords = SPOTS.map(s => [s.lat, s.lon]);
        L.polyline(allCoords, {
            color: '#64748B',
            weight: 3,
            dashArray: '6, 8',
            opacity: 0.65
        }).addTo(map);

        // 완료된 경로 (파란색 실선)
        const visitedCoords = SPOTS.filter(s => s.done).map(s => [s.lat, s.lon]);
        if (visitedCoords.length >= 2) {
            L.polyline(visitedCoords, {
                color: '#2563EB',
                weight: 6,
                opacity: 0.95
            }).addTo(map);
        }

        // 목적지 마커
        const bounds = [];
        SPOTS.forEach((spot, i) => {
            bounds.push([spot.lat, spot.lon]);
            const pinClass = spot.done ? 'custom-pin pin-done' : 'custom-pin pin-yet';
            const iconSymbol = spot.done ? '✓' : (i + 1);

            const icon = L.divIcon({
                className: '',
                html: '<div class="' + pinClass + '">' + iconSymbol + '</div>',
                iconSize: [26, 26],
                iconAnchor: [13, 13]
            });

            const statusText = spot.done 
                ? "<span style='color:#16A34A;font-weight:bold;'>🎉 방문 완료</span>" 
                : "<span style='color:#2563EB;font-weight:bold;'>⏳ 예정지</span>";

            const popupContent = 
                '<div style="font-family:-apple-system,BlinkMacSystemFont,sans-serif; min-width:170px;">' +
                    '<b style="font-size:14px;color:#1E3A8A;">' + spot.name + '</b><br>' +
                    statusText +
                    '<p style="margin:4px 0;font-size:12px;color:#334155;">' + spot.desc + '</p>' +
                    '<div style="background:#FEF3C7;color:#B45309;padding:3px 6px;border-radius:4px;font-size:11px;">' +
                        '💡 ' + spot.tip +
                    '</div>' +
                '</div>';

            L.marker([spot.lat, spot.lon], { icon: icon })
                .bindPopup(popupContent)
                .addTo(map);
        });

        map.fitBounds(bounds, { padding: [35, 35] });

        // 내 위치 기능
        let userMarker = null;
        let userCircle = null;

        function findMyLocation() {
            const btn = document.getElementById('locBtn');
            if (!navigator.geolocation) {
                alert('이 기기/브라우저에서는 위치 서비스를 지원하지 않습니다.');
                return;
            }

            btn.classList.add('active');

            navigator.geolocation.getCurrentPosition(
                function(pos) {
                    const lat = pos.coords.latitude;
                    const lon = pos.coords.longitude;
                    const accuracy = pos.coords.accuracy;

                    if (userMarker) map.removeLayer(userMarker);
                    if (userCircle) map.removeLayer(userCircle);

                    const userIcon = L.divIcon({
                        className: '',
                        html: '<div class="user-pulse"></div>',
                        iconSize: [18, 18],
                        iconAnchor: [9, 9]
                    });

                    userMarker = L.marker([lat, lon], { icon: userIcon }).addTo(map);
                    userMarker.bindPopup("<b>📍 현재 내 위치</b><br><small>정확도 약 " + Math.round(accuracy) + "m</small>").openPopup();

                    userCircle = L.circle([lat, lon], {
                        radius: accuracy,
                        color: '#3B82F6',
                        weight: 1,
                        fillColor: '#93C5FD',
                        fillOpacity: 0.15
                    }).addTo(map);

                    map.flyTo([lat, lon], 14, { animate: true, duration: 1.2 });
                },
                function(err) {
                    btn.classList.remove('active');
                    alert('위치 정보를 가져올 수 없습니다. 브라우저의 위치 권한을 확인해 주세요.');
                },
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
            );
        }
    </script>
</body>
</html>
"""

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
    final_html = MAP_TEMPLATE.replace("__SPOTS_JSON__", spots_json)
    components.html(final_html, height=490)

# ---------- 화면 표시 ----------
st.title("🚗 춘천 실시간 여행 트래커")
st.caption("📱 우측 상단 타겟 버튼(⌖)을 누르면 내 위치 중심으로 이동하며, 일정 체크 시 경로가 연결됩니다.")

col_map, col_ctrl = st.columns([1.3, 1.0])

done_flags = [st.session_state[k] for k in KEYS]
n_done = sum(done_flags)

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

with col_map:
    st.progress(n_done / len(SPOTS),
                text=f"진행률: {n_done} / {len(SPOTS)} 코스 완료 ({n_done * 100 // len(SPOTS)}%)")
    render_embedded_google_map(done_flags)
