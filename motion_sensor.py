import RPi.GPIO as GPIO
import time

SENSOR_PIN = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(SENSOR_PIN, GPIO.IN)

print("RCWL-0516 Radar Sensor Test (Ctrl+C to exit)")

try:
    while True:
        if GPIO.input(SENSOR_PIN) == 1:
            print("Motion detected!")
        time.sleep(0.1)

except KeyboardInterrupt:
    GPIO.cleanup()
