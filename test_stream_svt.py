import serial
import time
import os
import threading

COM_PORT = "COM5"
BAUD_RATE = 115200

esp32_ready = False

def listen_to_esp32(ser):
    global esp32_ready
    while True:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                print(f"[ESP32] {line}")
                if "RECORDED" in line:
                    esp32_ready = True
        except Exception:
            break

ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
time.sleep(2)

t_listen = threading.Thread(target=listen_to_esp32, args=(ser,), daemon=True)
t_listen.start()

ser.write(b"mode recorded\n")

deadline = time.time() + 10
while time.time() < deadline:
    if esp32_ready:
        break
    time.sleep(0.05)

with open("spandan/SVT.csv", "r") as f:
    lines = f.readlines()

start_idx = 1
for line in lines[start_idx:]:
    start_time = time.perf_counter()
    parts = line.strip().split(",")
    if len(parts) >= 3:
        raw_val = parts[2]
        ser.write(f"sample,{raw_val}\n".encode('utf-8'))
    
    elapsed = time.perf_counter() - start_time
    if elapsed < (1/360.0):
        time.sleep((1/360.0) - elapsed)

time.sleep(2)
