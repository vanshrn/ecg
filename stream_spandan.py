import serial
import time
import os
import threading

COM_PORT = 'COM5'     # Change to your ESP32 COM port
BAUD_RATE = 115200
RECORDINGS_DIR = 'spandan'

running = True

esp32_ready = False

def listen_to_esp32(ser):
    global running, esp32_ready
    while running:
        if ser.in_waiting > 0:
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    print(f"[ESP32] {line}")
                    if "Switched to RECORDED" in line:
                        esp32_ready = True
            except Exception:
                pass

def stream_file():
    global running
    files = [f for f in os.listdir(RECORDINGS_DIR) if f.endswith('.csv')]
    if not files:
        print(f"[ERROR] No CSV files found in '{RECORDINGS_DIR}/'")
        return

    print("\n--- AVAILABLE RECORDINGS ---")
    for i, f in enumerate(files):
        print(f" [{i}] {f}")
    
    choice = input("\nSelect file index to stream to ESP32: ").strip()
    if not choice.isdigit() or int(choice) >= len(files):
        print("Invalid selection.")
        return

    selected_file = os.path.join(RECORDINGS_DIR, files[int(choice)])

    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        time.sleep(2) # Allow connection to stabilize
        print(f"\n[CONNECTED] Streaming '{selected_file}' to ESP32 on {COM_PORT}...")
    except Exception as e:
        print(f"[ERROR] Could not open {COM_PORT}: {e}")
        return

    # Start background listener thread to display ESP32 response logs
    t_listen = threading.Thread(target=listen_to_esp32, args=(ser,), daemon=True)
    t_listen.start()

    # Switch ESP32 to recorded mode and wait for confirmation before streaming
    global esp32_ready
    esp32_ready = False
    ser.write(b"mode recorded\n")
    print("[WAITING] Waiting for ESP32 to confirm recorded mode...")
    
    deadline = time.time() + 25  # wait up to 25 seconds for Wi-Fi connect
    while time.time() < deadline:
        if esp32_ready:
            print("[READY] ESP32 is ready. Starting stream...\n")
            break
        time.sleep(0.05)

    with open(selected_file, "r") as f:
        lines = f.readlines()

    start_idx = 1 if lines[0].startswith("Index") else 0

    print("[STREAMING DATA] Press Ctrl+C to stop.\n")
    
    # 360 Hz sample interval = ~0.00277 seconds
    sample_interval = 1.0 / 360.0

    try:
        for line in lines[start_idx:]:
            start_time = time.perf_counter()
            parts = line.strip().split(",")
            
            if len(parts) >= 3:
                raw_val = parts[2] # Ingests Raw column
                ser.write(f"sample,{raw_val}\n".encode('utf-8'))

            # High-precision sleep compensation (Busy-wait for sub-millisecond accuracy on Windows)
            elapsed = time.perf_counter() - start_time
            sleep_time = sample_interval - elapsed
            if sleep_time > 0:
                target_time = time.perf_counter() + sleep_time
                while time.perf_counter() < target_time:
                    pass

        print("\n[FINISHED] Completed streaming file.")
        time.sleep(2) # Wait for final API batch upload to print
    except KeyboardInterrupt:
        print("\n[STOPPED] Streaming interrupted.")
    
    # Switch back to live mode and close
    ser.write(b"mode live\n")
    running = False
    time.sleep(0.5)
    ser.close()

if __name__ == "__main__":
    stream_file()