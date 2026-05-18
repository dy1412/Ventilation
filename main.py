from machine import Pin, ADC
from neopixel import NeoPixel
import time

# ===== WS2813 네오픽셀 설정 (특별 타이밍!) =====
TIMING = (280, 515, 515, 745)
NUM_LEDS = 10
led = NeoPixel(Pin(16), NUM_LEDS, timing=TIMING)

# ===== MQ-2 센서 설정 =====
mq2 = ADC(Pin(26))

# ===== 색상 정의 (R, G, B) - 밝기 조절됨 =====
GREEN  = (0, 50, 0)     # 공기 양호
YELLOW = (50, 40, 0)    # 보통
RED    = (50, 0, 0)     # 위험
OFF    = (0, 0, 0)

# ===== 임계값 설정 (더 민감하게 조정!) =====
THRESHOLD_LOW = 8000    # 이 값 이하: 공기 양호
THRESHOLD_HIGH = 20000  # 이 값 이상: 위험
SENSOR_MAX = 30000      # 게이지 최대값 기준

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

# ===== 센서 예열 (5초로 단축) =====
print("MQ-2 센서 예열 중... (5초)")
clear_leds()
for i in range(5, 0, -1):
    # 예열 진행 상황을 파란색으로 표시
    fill_count = (5 - i) * 2 + 2
    for j in range(NUM_LEDS):
        if j < fill_count:
            led[j] = (0, 0, 30)
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
        led_count = 1          # 최소 1칸은 표시
    if led_count > NUM_LEDS:
        led_count = NUM_LEDS   # 최대 10칸
    
    # 상태에 따른 색상 결정 및 표시
    if gas_value < THRESHOLD_LOW:
        # 🟢 공기 양호 - 초록색
        show_gauge(led_count, GREEN)
        status = "🟢 공기 양호"
    elif gas_value < THRESHOLD_HIGH:
        # 🟡 보통 - 노란색
        show_gauge(led_count, YELLOW)
        status = "🟡 보통 (환기 권장)"
    else:
        # 🔴 위험 - 빨간색 깜빡임
        blink_warning(led_count, RED, times=3)
        status = "🔴 위험! (환기 필수)"
    
    # 시리얼 모니터 출력
    print(f"가스 농도: {gas_value:5d} | LED: {led_count}/10 | 상태: {status}")
    
    time.sleep(1)
