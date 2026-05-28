import network
import socket
import time
import asyncio
import json
from machine import Pin, ADC, PWM
from neopixel import NeoPixel

# ==========================================
# [1] 하드웨어 핀 설정 및 상수 정의
# ==========================================
TIMING = (280, 515, 515, 745)
NUM_LEDS = 10
led = NeoPixel(Pin(16), NUM_LEDS, timing=TIMING)

mq2 = ADC(Pin(26))

buzzer = PWM(Pin(15))
buzzer.duty_u16(0)  # 시작할 때는 부저 무음 설정

# ===== 🌈 단계별 누적식 색상 설계 (배열을 통한 영구 매핑) =====
# 좋음은 2칸(Green), 보통은 3칸(Orange), 나쁨은 3칸(Dark Orange), 매우나쁨은 2칸(Red)
GRADIENT_COLORS = [
    (0, 50, 0), (0, 50, 0),               # 0, 1 : 좋음 2칸 (🟢 Green)
    (50, 20, 0), (50, 20, 0), (50, 20, 0), # 2, 3, 4 : 보통 3칸 (🟡/🟠 Orange)
    (60, 8, 0), (60, 8, 0), (60, 8, 0),   # 5, 6, 7 : 나쁨 3칸 (🟠 Dark Red-Orange)
    (60, 0, 0), (60, 0, 0)                 # 8, 9 : 매우 나쁨 2칸 (🔴 Red)
]

BLUE = (0, 0, 30)     # 예열 및 영점 조절 중 표시용 (단색)
OFF  = (0, 0, 0)

# 이동 평균 필터 설정
WINDOW_SIZE = 5
readings = []

# ==========================================
# [2] Wi-Fi 네트워크 설정 (STA 및 AP 백업 기능)
# ==========================================
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"

my_ip = "0.0.0.0"

# ==========================================
# [3] 전역 가스 센서 변수
# ==========================================
raw_gas_value = 0
gas_value = 0
baseline_gas = 0
THRESHOLD_GOOD = 0
THRESHOLD_MODERATE = 0
THRESHOLD_BAD = 0
SENSOR_MAX = 0
led_count = 1
status = "준비 중..."
is_calibrating = False

# ==========================================
# [4] 기본 하드웨어 동작 함수 (누적 게이지 최적화)
# ==========================================
def clear_leds():
    for i in range(NUM_LEDS):
        led[i] = OFF
    led.write()

def show_gauge(count, color_override=None):
    """
    color_override가 없으면 단계별 고유 색상이 누적(초록->주황->빨강)되어 켜지고,
    예열 중 등 특수 상황에는 color_override(예: BLUE) 단색으로 켜집니다.
    """
    for i in range(NUM_LEDS):
        if i < count:
            if color_override is not None:
                led[i] = color_override
            else:
                led[i] = GRADIENT_COLORS[i] # 누적식 그라데이션 적용!
        else:
            led[i] = OFF
    led.write()

# ==========================================
# [5] 비동기 경보음 및 예열/영점 조절 태스크
# ==========================================
async def async_blink_warning(count, times=1):
    """비동기 방식으로 동작하는 경보음 및 그라데이션 깜빡임 효과"""
    for _ in range(times):
        show_gauge(count)  # 누적 색상으로 켜기
        buzzer.freq(1000)
        buzzer.duty_u16(32768)  # 50% 볼륨 경고음
        await asyncio.sleep(0.3)
        
        clear_leds()
        buzzer.duty_u16(0)
        await asyncio.sleep(0.3)
    show_gauge(count)

async def async_calibration():
    """예열 및 자동 영점조절 (Non-blocking)"""
    global baseline_gas, THRESHOLD_GOOD, THRESHOLD_MODERATE, THRESHOLD_BAD, SENSOR_MAX, status, is_calibrating
    is_calibrating = True
    status = "⚙️ 센서 예열 및 영점 잡는 중..."
    print("-----------------------------------------")
    print("Auto-Calibration 시작 (5초간 데이터 수집)...")
    
    clear_leds()
    calibration_sum = 0
    sample_count = 0
    
    # 5초간 파란색 게이지가 차오르며 영점을 학습함
    for i in range(5, 0, -1):
        fill_count = (5 - i) * 2 + 2
        show_gauge(fill_count, BLUE)
        
        for _ in range(5):
            calibration_sum += mq2.read_u16()
            sample_count += 1
            await asyncio.sleep(0.2)
            
    baseline_gas = int(calibration_sum / sample_count)
    
    # 동적 임계값 설정
    THRESHOLD_GOOD     = baseline_gas + 3000
    THRESHOLD_MODERATE = baseline_gas + 12000
    THRESHOLD_BAD      = baseline_gas + 22000
    SENSOR_MAX         = baseline_gas + 30000
    
    print(f"영점 완료! 기준값: {baseline_gas}")
    clear_leds()
    is_calibrating = False

# ==========================================
# [6] 웹 서비스 제공용 HTML 템플릿 (웹 동기 깜빡임 추가)
# ==========================================
def get_html_page():
    html = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pico 2 W 실시간 공기질 모니터</title>
    <style>
        :root {
            --bg-color: #f1f5f9;       /* 연한 회색 배경 */
            --card-bg: #ffffff;       /* 순백색 카드 */
            --text-main: #0f172a;     /* 짙은 텍스트 */
            --text-sub: #64748b;      /* 부차적인 텍스트 */
            --accent-color: #4f46e5;  /* 세련된 인디고 블루 */
            --border-color: #e2e8f0;  /* 선 디자인 */
        }
        body {
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
            justify-content: center;
        }
        .container {
            max-width: 650px;
            width: 100%;
            background: var(--card-bg);
            padding: 35px;
            border-radius: 20px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.05);
            border: 1px solid var(--border-color);
            box-sizing: border-box;
        }
        h1 {
            font-size: 1.6rem;
            text-align: center;
            margin: 0 0 5px 0;
            color: var(--accent-color);
            font-weight: 800;
        }
        .subtitle {
            text-align: center;
            font-size: 0.95rem;
            color: var(--text-sub);
            margin-bottom: 25px;
        }
        /* 네오픽셀 LED 바 스타일 */
        .neopixel-strip {
            display: flex;
            justify-content: space-between;
            background: #f8fafc;
            padding: 16px;
            border-radius: 14px;
            margin-bottom: 25px;
            border: 1.5px solid var(--border-color);
        }
        .led {
            width: 34px;
            height: 34px;
            border-radius: 50%;
            background-color: #cbd5e1; /* 꺼졌을 때 연회색 */
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
            transition: background-color 0.25s, box-shadow 0.25s;
        }
        
        /* ===== ⚡ [추가됨] 물리 보드의 0.3초 온/오프 깜빡임 속도를 완벽 동기화하는 CSS 애니메이션 ===== */
        @keyframes blink-alert {
            0%, 49% {
                /* 켜진 상태 (기존 자바스크립트가 설정한 그라데이션 컬러 및 섀도우가 유지됨) */
            }
            50%, 100% {
                /* 꺼진 상태 (비활성화 연회색으로 강제 전환) */
                background-color: #cbd5e1 !important;
                box-shadow: inset 0 1px 3px rgba(0,0,0,0.1) !important;
            }
        }
        .led-blink {
            animation: blink-alert 0.6s infinite; /* 0.3초 켜지고 0.3초 꺼지는 총 0.6초 주기 무한 반복 */
        }

        /* 원격 조절 버튼 */
        .control-panel {
            margin-bottom: 25px;
            text-align: center;
        }
        .btn {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #4f46e5, #6366f1);
            border: none;
            color: white;
            font-weight: bold;
            border-radius: 12px;
            cursor: pointer;
            font-size: 1rem;
            box-shadow: 0 4px 12px rgba(79, 70, 229, 0.2);
            transition: transform 0.15s, opacity 0.2s;
        }
        .btn:hover {
            opacity: 0.95;
            transform: translateY(-1px);
        }
        .btn:active {
            transform: translateY(1px);
        }
        .btn:disabled {
            background: #94a3b8;
            box-shadow: none;
            cursor: not-allowed;
        }
        /* 실시간 대시보드 */
        .dashboard {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-bottom: 25px;
        }
        .data-card {
            background: #f8fafc;
            padding: 18px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            border-top: 4px solid var(--accent-color);
        }
        .data-card h3 {
            margin: 0 0 8px 0;
            font-size: 0.85rem;
            color: var(--text-sub);
            font-weight: 600;
            text-transform: uppercase;
        }
        .data-card p {
            margin: 0;
            font-size: 1.4rem;
            font-weight: bold;
            color: var(--text-main);
        }
        /* 실시간 단계 수치 패널 */
        .threshold-panel {
            background: #f8fafc;
            border-radius: 14px;
            border: 1px solid var(--border-color);
            padding: 20px;
            margin-bottom: 25px;
        }
        .threshold-panel h3 {
            margin: 0 0 12px 0;
            font-size: 0.9rem;
            color: var(--text-sub);
            font-weight: bold;
        }
        .threshold-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
        }
        .th-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            background: white;
            border: 1px solid var(--border-color);
            padding: 10px 5px;
            border-radius: 10px;
            font-size: 0.8rem;
        }
        .th-title {
            font-weight: bold;
            margin-bottom: 4px;
        }
        .th-val {
            color: var(--text-sub);
            font-family: monospace;
            font-weight: 600;
        }
        /* 공기 상태 출력 배너 */
        .status-banner {
            text-align: center;
            padding: 18px;
            font-size: 1.25rem;
            font-weight: bold;
            border-radius: 12px;
            transition: all 0.3s ease;
            border: 2px solid var(--border-color);
            background-color: #f8fafc;
            color: var(--text-sub);
        }
        /* 배너 상태별 스타일 클래스 */
        .status-green { background-color: #ecfdf5; border-color: #10b981; color: #047857; }
        .status-yellow { background-color: #fef3c7; border-color: #f59e0b; color: #b45309; }
        .status-orange { background-color: #ffedd5; border-color: #f97316; color: #c2410c; }
        .status-red { background-color: #fee2e2; border-color: #ef4444; color: #b91c1c; }
        .status-blue { background-color: #eff6ff; border-color: #3b82f6; color: #1d4ed8; }
        .status-error { background-color: #fef2f2; border-color: #f87171; color: #991b1b; }
    </style>
</head>
<body>

<div class="container">
    <h1>당곡고 공기질 측정 웹사이트</h1>
    <div class="subtitle">당곡고등학교의 공기질을 측정하여 알려주고 환기를 할지 말지 알려줍니다!</div>

    <!-- 네오픽셀 스트립 -->
    <div class="neopixel-strip" id="ledStrip">
        <div class="led"></div>
        <div class="led"></div>
        <div class="led"></div>
        <div class="led"></div>
        <div class="led"></div>
        <div class="led"></div>
        <div class="led"></div>
        <div class="led"></div>
        <div class="led"></div>
        <div class="led"></div>
    </div>

    <!-- 버튼 영역 -->
    <div class="control-panel">
        <button class="btn" id="calibBtn" onclick="triggerCalibration()">원격 자동 영점 설정 (Auto Calibrate)</button>
    </div>

    <!-- 대시보드 수치 -->
    <div class="dashboard">
        <div class="data-card" style="border-top-color: #10b981;">
            <h3>현재 가스 센서값 (Raw / 필터)</h3>
            <p id="gasValueTxt">가져오는 중...</p>
        </div>
        <div class="data-card" style="border-top-color: #4f46e5;">
            <h3>설정된 기준값 (Baseline)</h3>
            <p id="baselineTxt">가져오는 중...</p>
        </div>
    </div>

    <!-- 판단 기준 기준선 확인 패널 -->
    <div class="threshold-panel">
        <h3>📊 현재 공기질 판단 기준 수치 (가스 센서값 범위)</h3>
        <div class="threshold-grid">
            <div class="th-item" style="border-top: 3px solid #10b981;">
                <span class="th-title" style="color: #047857;">🟢 좋음 (2칸)</span>
                <span class="th-val" id="thGoodTxt">-</span>
            </div>
            <div class="th-item" style="border-top: 3px solid #f59e0b;">
                <span class="th-title" style="color: #b45309;">🟡 보통 (+3칸)</span>
                <span class="th-val" id="thModTxt">-</span>
            </div>
            <div class="th-item" style="border-top: 3px solid #f97316;">
                <span class="th-title" style="color: #c2410c;">🟠 나쁨 (+3칸)</span>
                <span class="th-val" id="thBadTxt">-</span>
            </div>
            <div class="th-item" style="border-top: 3px solid #ef4444;">
                <span class="th-title" style="color: #b91c1c;">🔴 매우나쁨 (+2칸)</span>
                <span class="th-val" id="thVeryBadTxt">-</span>
            </div>
        </div>
    </div>

    <!-- 상태 알림 배너 -->
    <div class="status-banner" id="statusBanner">
        🚦 실시간 센서값 수신 대기 중...
    </div>
</div>

<script>
    const ledElements = document.querySelectorAll('.led');
    const calibBtn = document.getElementById('calibBtn');
    const gasValueTxt = document.getElementById('gasValueTxt');
    const baselineTxt = document.getElementById('baselineTxt');
    const statusBanner = document.getElementById('statusBanner');
    
    const thGoodTxt = document.getElementById('thGoodTxt');
    const thModTxt = document.getElementById('thModTxt');
    const thBadTxt = document.getElementById('thBadTxt');
    const thVeryBadTxt = document.getElementById('thVeryBadTxt');

    const COLOR_OFF = "rgb(203, 213, 225)"; // 비활성화 LED 색상 (연회색)

    // ===== 🌈 누적 게이지 설계와 100% 매치되는 웹 전용 색상 배열 =====
    const cumulativeColors = [
        "rgb(16, 185, 129)", "rgb(16, 185, 129)",                     // 0, 1: 좋음 (🟢 Green)
        "rgb(245, 158, 11)", "rgb(245, 158, 11)", "rgb(245, 158, 11)", // 2, 3, 4: 보통 (🟡/🟠 Orange)
        "rgb(249, 115, 22)", "rgb(249, 115, 22)", "rgb(249, 115, 22)", // 5, 6, 7: 나쁨 (🟠 Dark Orange)
        "rgb(239, 68, 68)", "rgb(239, 68, 68)"                         // 8, 9: 매우나쁨 (🔴 Red)
    ];
    const blueColor = "rgb(59, 130, 246)"; // 예열 중 파란색 단색

    function updateLeds(count, statusStr) {
        // [수정 포인트] 매우 나쁨(🔴)일 때 브라우저 자체적으로 깜빡임 클래스를 주입합니다.
        const isBlinking = statusStr.includes("매우");

        ledElements.forEach((led, idx) => {
            // 이전에 묻어있던 깜빡임 클래스 초기화
            led.classList.remove("led-blink");

            if (idx < count) {
                let color = cumulativeColors[idx];
                if (statusStr.includes("예열") || statusStr.includes("조절") || statusStr.includes("준비")) {
                    color = blueColor;
                }
                led.style.backgroundColor = color;
                led.style.boxShadow = `0 0 14px ${color}, inset 0 2px 3px rgba(255,255,255,0.4)`;
                
                // 매우 나쁨 단계일 경우 동적 깜빡임 클래스 적용!
                if (isBlinking) {
                    led.classList.add("led-blink");
                }
            } else {
                led.style.backgroundColor = COLOR_OFF;
                led.style.boxShadow = "inset 0 1px 3px rgba(0,0,0,0.1)";
            }
        });
    }

    function updateStatusBannerStyle(statusStr) {
        statusBanner.className = "status-banner";
        if (statusStr.includes("좋음")) {
            statusBanner.classList.add("status-green");
        } else if (statusStr.includes("보통")) {
            statusBanner.classList.add("status-yellow");
        } else if (statusStr.includes("나쁨") && !statusStr.includes("매우")) {
            statusBanner.classList.add("status-orange");
        } else if (statusStr.includes("매우")) {
            statusBanner.classList.add("status-red");
        } else if (statusStr.includes("예열") || statusStr.includes("조절")) {
            statusBanner.classList.add("status-blue");
        }
    }

    async function fetchData() {
        try {
            const res = await fetch('/data');
            const data = await res.json();
            
            gasValueTxt.innerText = `${data.raw} / ${data.filtered}`;
            baselineTxt.innerText = data.baseline;
            statusBanner.innerText = "현재 상태: " + data.status;
            
            thGoodTxt.innerText = `0 ~ ${data.th_good}`;
            thModTxt.innerText = `${data.th_good + 1} ~ ${data.th_mod}`;
            thBadTxt.innerText = `${data.th_mod + 1} ~ ${data.th_bad}`;
            thVeryBadTxt.innerText = `> ${data.th_bad}`;
            
            if (data.status.includes("예열") || data.status.includes("조절") || data.status.includes("준비")) {
                calibBtn.disabled = true;
                calibBtn.innerText = "영점 조절 진행 중...";
            } else {
                calibBtn.disabled = false;
                calibBtn.innerText = "원격 자동 영점 설정 (Auto Calibrate)";
            }
            
            updateLeds(data.led_count, data.status);
            updateStatusBannerStyle(data.status);
        } catch (err) {
            console.error("연결 오류:", err);
            statusBanner.innerText = "⚠️ Pico 2 W 서버와 통신할 수 없습니다.";
            statusBanner.className = "status-banner status-error";
        }
    }

    async function triggerCalibration() {
        try {
            calibBtn.disabled = true;
            await fetch('/calibrate');
        } catch (err) {
            console.error("캘리브레이션 요청 실패:", err);
        }
    }

    setInterval(fetchData, 1000);
    fetchData();
</script>
</body>
</html>"""
    return html

# ==========================================
# [7] 센서 측정 및 알고리즘 백그라운드 태스크 (미세 스텝 연산 핵심부!)
# ==========================================
async def sensor_loop():
    global raw_gas_value, gas_value, led_count, status, is_calibrating, readings
    
    # 최초 영점 조절 자동 실행
    await async_calibration()
    
    while True:
        if is_calibrating:
            await asyncio.sleep(0.5)
            continue
            
        raw_gas_value = mq2.read_u16()
        
        # 이동 평균 필터링
        readings.append(raw_gas_value)
        if len(readings) > WINDOW_SIZE:
            readings.pop(0)
        gas_value = int(sum(readings) / len(readings))
        
        # 음수 방지 클램핑 연산
        gas_val_clamped = max(baseline_gas, gas_value)
        
        # ===== 단계 내에서의 미세 수치에 따른 동적 칸수 보간법 =====
        if gas_val_clamped < THRESHOLD_GOOD:
            # 🟢 좋음 구간 (최대 2칸 배정)
            span = THRESHOLD_GOOD - baseline_gas
            span = max(1, span)
            ratio = (gas_val_clamped - baseline_gas) / span
            extra = int(ratio * 2)  # ratio에 따라 0 ~ 1 할당
            led_count = 1 + extra   # 최종 1칸 ~ 2칸 실시간 미세 매핑
            status = "🟢 좋음 (정상)"
            buzzer.duty_u16(0)
            show_gauge(led_count)
            
        elif gas_val_clamped < THRESHOLD_MODERATE:
            # 🟡 보통 구간 (기본 초록색 2칸 유지 + 추가 주황색 최대 3칸 배정)
            span = THRESHOLD_MODERATE - THRESHOLD_GOOD
            span = max(1, span)
            ratio = (gas_val_clamped - THRESHOLD_GOOD) / span
            extra = int(ratio * 3)  # ratio에 따라 보통 구간에서 0 ~ 2칸 추가 점등
            led_count = 2 + 1 + extra # 최종 3칸 ~ 5칸 실시간 미세 매핑
            status = "🟡 보통 (약간 오염)"
            buzzer.duty_u16(0)
            show_gauge(led_count)
            
        elif gas_val_clamped < THRESHOLD_BAD:
            # 🟠 나쁨 구간 (초록 2칸 + 주황 3칸 유지 + 추가 붉은 주황색 최대 3칸 배정)
            span = THRESHOLD_BAD - THRESHOLD_MODERATE
            span = max(1, span)
            ratio = (gas_val_clamped - THRESHOLD_MODERATE) / span
            extra = int(ratio * 3)  # ratio에 따라 나쁨 구간에서 0 ~ 2칸 추가 점등
            led_count = 5 + 1 + extra # 최종 6칸 ~ 8칸 실시간 미세 매핑
            status = "🟠 나쁨 (환기 권장)"
            buzzer.duty_u16(0)
            show_gauge(led_count)
            
        else:
            # 🔴 매우 나쁨 구간 (초록 2칸 + 주황 3칸 + 붉은 주황 3칸 유지 + 추가 빨간색 최대 2칸 배정)
            span = SENSOR_MAX - THRESHOLD_BAD
            span = max(1, span)
            ratio = (gas_val_clamped - THRESHOLD_BAD) / span
            extra = int(ratio * 2)  # 매우 나쁨 구간 내에서 수치에 따라 0 ~ 1칸 추가 점등
            led_count = 8 + 1 + extra # 최종 9칸 ~ 10칸 실시간 미세 매핑
            status = "🔴 매우 나쁨 (즉시 환기!)"
            
            # 위험 상태이므로 경보 비프음과 깜빡임 태스크 실행 (누적 색상 깜빡임)
            await async_blink_warning(led_count)
            
        # 값 강제 클램핑 제한막 (안전 장치)
        led_count = max(1, min(NUM_LEDS, led_count))
        
        print(f"기준(영점): {baseline_gas:5d} | 현재필터값: {gas_value:5d} | 매핑된 LED: {led_count}/10 | 상태: {status}")
        await asyncio.sleep(1.0)

# ==========================================
# [8] 비동기 웹서버 처리 태스크
# ==========================================
async def handle_client(reader, writer):
    global is_calibrating
    try:
        request_line = await reader.readline()
        if not request_line:
            return
            
        request = request_line.decode('utf-8').strip()
        
        while True:
            line = await reader.readline()
            if line == b'\r\n' or line == b'\n' or not line:
                break
                
        parts = request.split(' ')
        if len(parts) < 2:
            return
            
        path = parts[1]
        
        if path == '/':
            html_content = get_html_page()
            response = (
                "HTTP/1.0 200 OK\r\n"
                "Content-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(html_content.encode('utf-8'))}\r\n"
                "Connection: close\r\n\r\n" + html_content
            )
            writer.write(response.encode('utf-8'))
            await writer.drain()
            
        elif path == '/data':
            data = {
                "raw": raw_gas_value,
                "filtered": gas_value,
                "baseline": baseline_gas,
                "status": status,
                "led_count": led_count,
                "th_good": THRESHOLD_GOOD,
                "th_mod": THRESHOLD_MODERATE,
                "th_bad": THRESHOLD_BAD,
                "max": SENSOR_MAX
            }
            json_str = json.dumps(data)
            response = (
                "HTTP/1.0 200 OK\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(json_str.encode('utf-8'))}\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "Connection: close\r\n\r\n" + json_str
            )
            writer.write(response.encode('utf-8'))
            await writer.drain()
            
        elif path == '/calibrate':
            if not is_calibrating:
                asyncio.create_task(async_calibration())
            response = "HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nOK"
            writer.write(response.encode('utf-8'))
            await writer.drain()
            
        else:
            response = "HTTP/1.0 404 Not Found\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n404"
            writer.write(response.encode('utf-8'))
            await writer.drain()
            
    except Exception as e:
        print("Web Server Error:", e)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass

# ==========================================
# [9] Wi-Fi 연결 및 메인 비동기 루프 기동
# ==========================================
def connect_wifi():
    if WIFI_SSID == "YOUR_WIFI_SSID" or WIFI_SSID == "":
        print("Wi-Fi 정보가 비어있습니다. AP 모드를 시작합니다.")
        return start_ap_mode()
        
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    
    print(f"무선 공유기({WIFI_SSID})에 접속 중...")
    max_wait = 10
    while max_wait > 0:
        if wlan.status() == 3:
            break
        max_wait -= 1
        time.sleep(1)
        print(".")
        
    if wlan.status() == 3:
        print("\nWi-Fi 공유기 연결 성공!")
        ip = wlan.ifconfig()[0]
        print("네트워크 IP 주소:", ip)
        return ip
    else:
        print("\nWi-Fi 연결에 실패했습니다. (시간 초과)")
        return start_ap_mode()

def start_ap_mode():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid="Pico2W_Gas_Sensor", password="password123")
    print("\n-----------------------------------------")
    print("📢 Pico 2 W의 자체 핫스팟(AP Mode)이 활성화되었습니다!")
    print(" - 연결할 Wi-Fi 이름(SSID): Pico2W_Gas_Sensor")
    print(" - 비밀번호(PW): password123")
    print(" - 접속할 웹 주소: http://192.168.4.1/")
    print("-----------------------------------------")
    return "192.168.4.1"

async def main():
    global my_ip
    my_ip = connect_wifi()
    
    # 1. 백그라운드 센서 데이터 수집 루프 시작
    asyncio.create_task(sensor_loop())
    
    # 2. 비동기 웹서버 시작 (포트 80)
    print(f"웹서버 기동 중... 브라우저 주소창에 'http://{my_ip}/' 를 입력하세요.")
    server = await asyncio.start_server(handle_client, '0.0.0.0', 80)
    
    # 시스템 실행 무한 유지
    while True:
        await asyncio.sleep(3600)

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("\n시스템이 수동으로 종료되었습니다.")
    clear_leds()
    buzzer.duty_u16(0)
