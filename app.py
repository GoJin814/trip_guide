import json
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="춘천 실시간 여행 트래커",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 모바일 화면 공간 최적화 CSS
CSS = """
<style>
    .block-container {padding: 1rem 0.6rem 2rem 0.6rem !important;}
    
    /* 체크박스 기본 여백 축소 */
    .stCheckbox {margin-bottom: 0 !important;}
    .stCheckbox label {font-size: 0.95rem !important; font-weight: 700 !important; cursor: pointer; color: #111827;}
    
    /* 배지 및 Day 인라인 디자인 */
    .badge-inline {
        display: inline-flex;
        align-items: center;
        margin-top: 3px;
        white-space: nowrap;
    }
    .badge {
        display: inline-block;
        padding: 0.15rem 0.45rem;
        border-radius: 9999px;
        font-size: 0.72rem;
        font-weight: 700;
        margin-right: 0.3rem;
    }
    .done {background:#DCFCE7; color:#15803D;}
    .yet  {background:#F1F5F9; color:#64748B;}
    .day-txt {font-size: 0.78rem; color:#64748B; font-weight: 600;}
    
    .tip-txt {
        font-size: 0.8rem;
        color: #4B5563;
        margin-top: 4px;
        padding-left: 2px;
        line-height: 1.3;
    }
    
    /* 카드 컨테이너 내부 여백 슬림화 */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0.6rem 0.75rem !important;
        margin-bottom: 0.45rem !important;
        border-radius: 10px !important;
    }

    /* 우측 상단 수정 버튼 슬림화 */
    div[data-testid="stColumn"]:has(button[key*="btn_edit_"]) button {
        padding: 0.15rem 0.3rem !important;
        height: auto !important;
        min-height: 28px !important;
        border: none !important;
        background: transparent !important;
        font-size: 1.05rem !important;
    }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# 여행 코스 데이터 초기화
DEFAULT_SPOTS = [
    dict(id="legoland", day=1, name="1. 레고랜드 코리아", category="종일",
         lat=37.8845, lon=127.6975, desc="하중도 위치 테마파크 탐방",
         tip="오전 인기 어트랙션 집중 공략"),
    dict(id="soyang_dam", day=2, name="2. 소양호 유람선터미널", category="09:30~10:00",
         lat=37.9547, lon=127.8184, desc="청평사행 도선 승선 (편도 15분)",
         tip="댐 정상 주차장 09:30 전 도착 권장"),
    dict(id="cheongpyeongsa", day=2, name="3. 청평사 경내", category="10:15~11:45",
         lat=37.9877, lon=127.8136, desc="구성폭포 및 오봉산 산책로 관람",
         tip="선착장 ↔ 절 왕복 약 1시간 도보"),
    dict(id="sambath", day=2, name="4. 샘밭막국수", category="12:30~13:30",
         lat=37.9317, lon=127.7656, desc="담백한 전통 메밀막국수 & 편육",
         tip="소양강댐에서 차로 5분 거리 위치"),
    dict(id="cablecar", day=2, name="5. 삼악산 호수케이블카", category="14:00~15:30",
         lat=37.8548, lon=127.6970, desc="국내 최장 3.61km 케이블카 & 의암호 전망",
         tip="의암호 정차장에서 서울/수도권 복귀 직결"),
]

if "spots_data" not in st.session_state:
    st.session_state.spots_data = DEFAULT_SPOTS

if "editing_flags" not in st.session_state:
    st.session_state.editing_flags = {}

for s in st.session_state.spots_data:
    st.session_state.setdefault(f"chk_{s['id']}", False)
    st.session_state.editing_flags.setdefault(s["id"], False)

def set_all(value: bool) -> None:
    for s in st.session_state.spots_data:
        st.session_state[f"chk_{s['id']}"] = value

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
                    '<b style="font-size:13px;color:#1E3A8A;">' + spot.name + '</b><br>' +
                    statusText +
                    '<p style="margin:4px 0;font-size:11px;color:#334155;">' + spot.desc + '</p>' +
                    '<div style="background:#FEF3C7;color:#B45309;padding:2px 5px;border-radius:4px;font-size:10px;">' +
                        '💡 ' + spot.tip +
                    '</div>' +
                '</div>';

            L.marker([spot.lat, spot.lon], { icon: icon })
                .bindPopup(popupContent)
                .addTo(map);
        });

        if (bounds.length > 0) {
            map.fitBounds(bounds, { padding: [30, 30] });
        }

        let userMarker = null;
        let userCircle = null;

        function findMyLocation() {
            const btn = document.getElementById('locBtn');
            if (!navigator.geolocation) {
                alert('위치 서비스를 지원하지 않는 기기입니다.');
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
                        iconSize: [16, 16],
                        iconAnchor: [8, 8]
                    });

                    userMarker = L.marker([lat, lon], { icon: userIcon }).addTo(map);
                    userCircle = L.circle([lat, lon], {
                        radius: accuracy,
                        color: '#3B82F6',
                        weight: 1,
                        fillColor: '#93C5FD',
                        fillOpacity: 0.15
                    }).addTo(map);

                    map.flyTo([lat, lon], 14, { animate: true, duration: 1.0 });
                },
                function(err) {
                    btn.classList.remove('active');
                    alert('위치 정보를 불러올 수 없습니다. 브라우저 위치 권한을 확인해주세요.');
                },
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
            );
        }
    </script>
</body>
</html>
"""

def render_embedded_google_map(spots, done_states: list[bool]) -> None:
    data = [
        {
            "name": s["name"],
            "lat": s["lat"],
            "lon": s["lon"],
            "desc": s.get("desc", ""),
            "tip": s.get("tip", ""),
            "done": d
        }
        for s, d in zip(spots, done_states)
    ]
    spots_json = json.dumps(data, ensure_ascii=False)
    final_html = MAP_TEMPLATE.replace("__SPOTS_JSON__", spots_json)
    components.html(final_html, height=450)

# ---------- 화면 레이아웃 ----------
st.title("🚗 춘천 실시간 여행 트래커")

spots = st.session_state.spots_data
done_flags = [st.session_state.get(f"chk_{s['id']}", False) for s in spots]
n_done = sum(done_flags)

# 지도 상단 배치
total_spots = len(spots) if len(spots) > 0 else 1
st.progress(n_done / total_spots,
            text=f"진행률: {n_done} / {len(spots)} 코스 완료 ({n_done * 100 // total_spots}%)")
render_embedded_google_map(spots, done_flags)

# 상단 액션 바
act_c1, act_c2 = st.columns([1, 1.2])
with act_c1:
    st.button("✅ 전체완료", on_click=set_all, args=(True,), use_container_width=True)
with act_c2:
    with st.popover("➕ 새 일정 추가", use_container_width=True):
        st.markdown("##### 📍 새 장소 등록")
        new_name = st.text_input("장소명", placeholder="예: 구봉산 카페거리")
        new_day = st.selectbox("일차", [1, 2], index=1)
        new_tip = st.text_input("메모/팁", placeholder="예: 전망 좋은 베이커리")
        new_lat = st.number_input("위도(Lat)", value=37.8870, format="%.4f")
        new_lon = st.number_input("경도(Lon)", value=127.7650, format="%.4f")
        
        if st.button("추가하기", use_container_width=True):
            if new_name:
                new_id = f"custom_{len(spots)+1}"
                st.session_state.spots_data.append(dict(
                    id=new_id, day=new_day, name=f"{len(spots)+1}. {new_name}",
                    category="", lat=new_lat, lon=new_lon,
                    desc="사용자 등록 장소", tip=new_tip
                ))
                st.session_state[f"chk_{new_id}"] = False
                st.session_state.editing_flags[new_id] = False
                st.rerun()

st.write("")

# 일정 카드 렌더링
for idx, spot in enumerate(spots):
    sid = spot["id"]
    key = f"chk_{sid}"
    checked = st.session_state.get(key, False)
    is_editing = st.session_state.editing_flags.get(sid, False)
    
    with st.container(border=True):
        # 1. 수정 모드일 때
        if is_editing:
            st.markdown("**✏️ 일정 내용 수정**")
            edit_name = st.text_input("장소명", value=spot["name"], key=f"inp_name_{sid}")
            edit_day = st.selectbox("일차 (Day)", [1, 2], index=0 if spot.get("day", 1) == 1 else 1, key=f"inp_day_{sid}")
            edit_tip = st.text_input("메모/팁", value=spot.get("tip", ""), key=f"inp_tip_{sid}")
            
            b_save, b_cancel = st.columns(2)
            if b_save.button("저장", key=f"save_{sid}", use_container_width=True):
                st.session_state.spots_data[idx]["name"] = edit_name
                st.session_state.spots_data[idx]["day"] = edit_day
                st.session_state.spots_data[idx]["tip"] = edit_tip
                st.session_state.editing_flags[sid] = False
                st.rerun()
            if b_cancel.button("취소", key=f"cancel_{sid}", use_container_width=True):
                st.session_state.editing_flags[sid] = False
                st.rerun()

        # 2. 보기 모드일 때
        else:
            # 헤더 줄: [체크박스] + [장소명] | [대기/완료 + Day N] | [우측 상단 ✏️]
            c_chk, c_badge, c_edit = st.columns([4.2, 2.2, 0.8])
            
            with c_chk:
                st.checkbox(spot["name"], key=key)
            
            with c_badge:
                badge_class = "done" if checked else "yet"
                badge_label = "완료" if checked else "대기"
                st.markdown(
                    f'<div class="badge-inline">'
                    f'<span class="badge {badge_class}">{badge_label}</span>'
                    f'<span class="day-txt">Day {spot["day"]}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
                
            with c_edit:
                if st.button("✏️", key=f"btn_edit_{sid}", help="일정 수정"):
                    st.session_state.editing_flags[sid] = True
                    st.rerun()
            
            # 아래 줄: 팁/설명
            st.markdown(f'<div class="tip-txt">💡 {spot["tip"]}</div>', unsafe_allow_html=True)
