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
BLUE   = (0, 0, 30)      # 예열 표시용
OFF    = (0, 0, 0)

# ===== 공기질 기준값 (MQ-2 일반 기준) =====
THRESHOLD_GOOD     = 5000    # 이하: 정상
THRESHOLD_MODERATE = 15000   # 이하: 약간 오염
THRESHOLD_BAD      = 25000   # 이하: 오염 / 초과: 심각
SENSOR_MAX = 35000           # 게이지 최대 기준

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

# ===== 센서 예열 =====
print("MQ-2 센서 예열 중... (5초)")
clear_leds()
for i in range(5, 0, -1):
    fill_count = (5 - i) * 2 + 2
    for j in range(NUM_LEDS):
        if j < fill_count:
            led[j] = BLUE
        else:
            led[j] = OFF
    led.write()
    print(f"  남은 시간: {i}초")
    time.sleep(1)

clear_leds()
print("측정을 시작합니다!\n")

# ===== 메인 루프 =====
while True:
    # 센서 값 읽기 (0 ~ 65535)
    gas_value = mq2.read_u16()
    
    # 센서 값에 비례한 LED 칸 수 계산 (1~10칸)
    led_count = int((gas_value / SENSOR_MAX) * NUM_LEDS)
    if led_count < 1:
        led_count = 1
    if led_count > NUM_LEDS:
        led_count = NUM_LEDS
    
    # 4단계 공기질 판단
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
    print(f"가스 농도: {gas_value:5d} | LED: {led_count}/10 | 상태: {status}")
    
    time.sleep(1)
