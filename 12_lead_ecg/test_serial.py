import serial
import time

try:
    print("Attempting to connect to COM5 at 115200...")
    ser = serial.Serial('COM5', 115200, timeout=1)
    time.sleep(2)
    print("Connected. Reading 10 lines:")
    for _ in range(10):
        line = ser.readline()
        print("Raw bytes:", line)
        print("Decoded:", line.decode('utf-8', errors='ignore').strip())
    ser.close()
except Exception as e:
    print("Error:", e)
    
print("---")
try:
    print("Attempting to connect to COM5 at 9600...")
    ser = serial.Serial('COM5', 9600, timeout=1)
    time.sleep(2)
    print("Connected. Reading 10 lines:")
    for _ in range(10):
        line = ser.readline()
        print("Raw bytes:", line)
        print("Decoded:", line.decode('utf-8', errors='ignore').strip())
    ser.close()
except Exception as e:
    print("Error:", e)
