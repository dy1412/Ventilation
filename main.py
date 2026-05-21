from machine import Pin, ADC
from neopixel import NeoPixel
import time

# ===== WS2813 네오픽셀 설정 (특별 타이밍!) =====
TIMING = (280, 515, 515, 745)
NUM_LEDS = 10
led = NeoPixel(Pin(16), NUM_LEDS, timing=TIMING)

# ===== MQ-2 센서 설정 =====
mq2 = ADC(Pin(26))

# ===== 색상 정의 (R, G, B) =====
GREEN  = (0, 50, 0)      # 🟢 정상 (좋음)
YELLOW = (50, 40, 0)     # 🟡 약간 오염 (보통)
ORANGE = (60, 20, 0)     # 🟠 오염 (나쁨)
RED    = (60, 0, 0)      # 🔴 심각 (매우 나쁨)
BLUE   = (0, 0, 30)      # 예열 및 영점 조절 표시용
OFF    = (0, 0, 0)

# ===== 이동 평균 필터 설정 =====
WINDOW_SIZE = 5
readings = []

# ===== 전역 변수 초기화 =====
baseline_gas = 0             # 자동 학습할 기준값 (깨끗한 상태의 수치)
THRESHOLD_GOOD = 0
THRESHOLD_MODERATE = 0
THRESHOLD_BAD = 0
SENSOR_MAX = 0

# ===== LED 전체 끄기 =====
def clear_leds():
    for i in range(NUM_LEDS):
        led[i] = OFF
    led.write()

# ===== 게이지 형태로 LED 표시 =====
def show_gauge(count, color):
    for i in range(NUM_LEDS):
        if i < count:
            led[i] = color
        else:
            led[i] = OFF
    led.write()

# ===== 위험 시 깜빡임 효과 =====
def blink_warning(count, color, times=3):
    for _ in range(times):
        show_gauge(count, color)
        time.sleep(0.3)
        clear_leds()
        time.sleep(0.3)
    show_gauge(count, color)

# ===== [핵심] 센서 예열 및 자동 영점 조절 기능 =====
def auto_calibration():
    global baseline_gas, THRESHOLD_GOOD, THRESHOLD_MODERATE, THRESHOLD_BAD, SENSOR_MAX
    
    print("=========================================")
    print("MQ-2 센서 예열 및 자동 영점 조절(Auto-Cal) 시작")
    print("=========================================")
    
    clear_leds()
    calibration_sum = 0
    sample_count = 0
    
    # 5초 동안 예열하며 주변 환경 데이터 수집
    for i in range(5, 0, -1):
        # 파란색 LED가 채워지며 예열 표시
        fill_count = (5 - i) * 2 + 2
        for j in range(NUM_LEDS):
            if j < fill_count:
                led[j] = BLUE
            else:
                led[j] = OFF
        led.write()
        
        # 1초마다 센서값을 5번씩 샘플링하여 누적
        for _ in range(5):
            calibration_sum += mq2.read_u16()
            sample_count += 1
            time.sleep(0.2)
            
        print(f"  진행 중... 남은 시간: {i}초 (수집된 샘플 수: {sample_count}개)")
    
    # 누적된 값의 평균을 내어 기준값(영점)으로 설정
    baseline_gas = int(calibration_sum / sample_count)
    print("\n-----------------------------------------")
    print(f"⚡ 영점 설정 완료! 기준 가스 농도: {baseline_gas}")
    
    # 현재 장소의 기준값을 중심으로 4단계 임계값 동적 설정
    THRESHOLD_GOOD     = baseline_gas + 3000   # 기준값 + 3000 이하는 좋음
    THRESHOLD_MODERATE = baseline_gas + 12000  # 기준값 + 12000 이하는 보통
    THRESHOLD_BAD      = baseline_gas + 22000  # 기준값 + 22000 이하는 나쁨 (그 이상은 매우 나쁨)
    SENSOR_MAX         = baseline_gas + 30000  # 게이지가 가득 차는 최대 기준
    
    print(f"  - 🟢 좋음 기준: {THRESHOLD_GOOD} 이하")
    print(f"  - 🟡 보통 기준: {THRESHOLD_MODERATE} 이하")
    print(f"  - 🟠 나쁨 기준: {THRESHOLD_BAD} 이하")
    print(f"  - 🔴 매우나쁨 기준: {THRESHOLD_BAD} 초과")
    print("=========================================\n")
    
    clear_leds()
    time.sleep(1)

# ===== 초기화 실행 =====
auto_calibration()
print("측정을 시작합니다!\n")

# ===== 메인 루프 =====
while True:
    # 1. 센서 raw 값 읽기 (0 ~ 65535)
    raw_gas_value = mq2.read_u16()
    
    # 2. 이동 평균 필터 적용 (값 안정화)
    readings.append(raw_gas_value)
    if len(readings) > WINDOW_SIZE:
        readings.pop(0)
    gas_value = int(sum(readings) / len(readings))
    
    # 3. 기준값(영점) 대비 상대값으로 LED 게이지 칸 수 계산
    # (센서 수치가 baseline_gas보다 낮아질 경우 음수가 되는 것을 방지하기 위해 max() 사용)
    val_diff = max(0, gas_value - baseline_gas)
    range_diff = max(1, SENSOR_MAX - baseline_gas) # 0으로 나누기 방지
    
    led_count = int((val_diff / range_diff) * NUM_LEDS)
    
    # LED 칸 수 제약 조건 (최소 1칸 ~ 최대 10칸)
    if led_count < 1:
        led_count = 1
    if led_count > NUM_LEDS:
        led_count = NUM_LEDS
    
    # 4. 동적 임계값에 따른 4단계 공기질 판단
    if gas_value < THRESHOLD_GOOD:
        # 🟢 정상 (좋음)
        show_gauge(led_count, GREEN)
        status = "🟢 좋음 (정상)"
        
    elif gas_value < THRESHOLD_MODERATE:
        # 🟡 약간 오염 (보통)
        show_gauge(led_count, YELLOW)
        status = "🟡 보통 (약간 오염)"
        
    elif gas_value < THRESHOLD_BAD:
        # 🟠 오염 (나쁨)
        show_gauge(led_count, ORANGE)
        status = "🟠 나쁨 (환기 권장)"
        
    else:
        # 🔴 심각 (매우 나쁨) - 깜빡임
        blink_warning(led_count, RED, times=3)
        status = "🔴 매우 나쁨 (즉시 환기!)"
    
    # 시리얼 모니터 출력
    print(f"기준(영점): {baseline_gas:5d} | 현재값: {gas_value:5d} | LED: {led_count}/10 | 상태: {status}")
    
    time.sleep(1)
