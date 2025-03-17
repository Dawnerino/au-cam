import lgpio
import time

TRIGGER_PIN = 17
h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_input(h, TRIGGER_PIN)

# Enable pull-up resistor (default HIGH)
lgpio.gpio_claim_input(h, TRIGGER_PIN, lgpio.SET_PULL_UP)

try:
    while True:
        value = lgpio.gpio_read(h, TRIGGER_PIN)
        print(f"GPIO 17 Value: {value}")
        time.sleep(0.5)

except KeyboardInterrupt:
    print("Exiting...")

finally:
    lgpio.gpiochip_close(h)
