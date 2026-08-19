import sys
import os
import json
import time
import threading
import collections
from datetime import datetime
import numpy as np
import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from filter import ECGFilter, remove_baseline_wander, final_noise_filter

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
BAUD_RATE   = 115200
SAMPLE_RATE = 250
RECORD_S    = 10
MAX_SAMPLES = SAMPLE_RATE * RECORD_S
RECORD_DIR  = "recordings"

LEADS = [
    "Lead_I", "Lead_II", "V1", "V2", "V3", "V4", "V5", "V6"
]

# ──────────────────────────────────────────────
# AUTO-DETECT PORT
# ──────────────────────────────────────────────
def find_port():
    KEYWORDS = ["CP210", "CH340", "CH341", "FTDI", "USB Serial", "ESP32", "UART"]
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "") + " " + (p.manufacturer or "")
        if any(k.lower() in desc.lower() for k in KEYWORDS):
            return p.device
    ports = serial.tools.list_ports.comports()
    return ports[0].device if ports else None

# ──────────────────────────────────────────────
# RECORDER CLASS
# ──────────────────────────────────────────────
class ECGRecorder:
    def __init__(self, port):
        self.port = port
        self.ser = None
        
        self.is_recording = False
        self.raw_data = []
        self.filtered_data = []
        
        self.buf_raw = collections.deque([0.0] * MAX_SAMPLES, maxlen=MAX_SAMPLES)
        self.buf_filtered = collections.deque([0.0] * MAX_SAMPLES, maxlen=MAX_SAMPLES)
        self.lock = threading.Lock()
        
        self.ecg_filter = ECGFilter(fs=SAMPLE_RATE, lp_cutoff=25.0, notch_freq=50.0, notch_q=50.0)

    def _serial_reader(self):
        try:
            self.ser = serial.Serial(self.port, BAUD_RATE, timeout=1)
        except serial.SerialException as e:
            print(f"\n[ERROR] Could not open {self.port}: {e}")
            self.is_recording = False
            return

        print(f"\n[INFO] Connected to {self.port}. Starting 10-second recording...")
        
        first_sample = True
        while self.is_recording:
            try:
                line = self.ser.readline().decode("ascii", errors="ignore").strip()
            except Exception:
                continue
            
            # We specifically read the raw ADC from L1raw from the ESP32 firmware
            if line.startswith(">L1raw:"):
                try:
                    raw_adc = float(line.split(":")[-1].strip())
                except ValueError:
                    continue
                    
                # Convert ESP32 12-bit ADC counts to actual heart millivolts (mV)
                # ESP32 Vref = 3.3V, Max ADC = 4095, AD8232 Hardware Gain = ~1100
                raw_mv = (raw_adc / 4095.0) * (3.3 / 1100.0) * 1000.0

                if first_sample:
                    self.ecg_filter.reset(raw_mv)
                    first_sample = False

                filtered_mv = self.ecg_filter.process(raw_mv)
                
                with self.lock:
                    self.buf_raw.append(raw_mv)
                    self.buf_filtered.append(filtered_mv)
                    
                    self.raw_data.append(raw_mv)
                    self.filtered_data.append(filtered_mv)
                    
                    # Stop automatically once we hit the target sample count (10 seconds)
                    if len(self.raw_data) >= MAX_SAMPLES:
                        self.is_recording = False

        self.ser.close()

    def record(self, lead_name):
        self.raw_data = []
        self.filtered_data = []
        self.is_recording = True
        
        # Reset filter state to avoid transients
        self.ecg_filter.reset(0)

        # Start serial reading in background
        t = threading.Thread(target=self._serial_reader, daemon=True)
        t.start()

        # ── Setup Matplotlib Live Plot ──
        t_axis = [i / SAMPLE_RATE for i in range(MAX_SAMPLES)]
        fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
        fig.patch.set_facecolor("#0f0f0f")
        
        for ax in (ax_top, ax_bot):
            ax.set_facecolor("#141414")
            ax.tick_params(colors="#aaaaaa")
            ax.yaxis.label.set_color("#aaaaaa")
            ax.margins(y=0.4)
            for spine in ax.spines.values():
                spine.set_edgecolor("#333333")
            ax.grid(True, color="#252525", linewidth=0.6, linestyle="--")

        ax_bot.set_xlabel("Time (s)", color="#aaaaaa")
        ax_top.set_ylabel("Voltage (mV) — Raw", color="#aaaaaa")
        ax_bot.set_ylabel("Voltage (mV) — Filtered", color="#aaaaaa")
        fig.suptitle(f"Recording: {lead_name} (10 seconds)", color="#ffffff", fontsize=13, fontweight="bold")

        (line_raw,) = ax_top.plot(t_axis, list(self.buf_raw), color="#ff6d00", linewidth=1.0)
        (line_filtered,) = ax_bot.plot(t_axis, list(self.buf_filtered), color="#00e5ff", linewidth=1.2)
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        plt.subplots_adjust(hspace=0.08)

        def update(_):
            with self.lock:
                y_raw = list(self.buf_raw)
                done = not self.is_recording

            # Apply the same report pipeline on the buffered raw data for display only — not stored
            raw_arr = np.array(y_raw)
            y_filt = final_noise_filter(remove_baseline_wander(raw_arr))

            line_raw.set_ydata(y_raw)
            line_filtered.set_ydata(y_filt)
            ax_top.relim(); ax_top.autoscale_view(scalex=False)
            ax_bot.relim(); ax_bot.autoscale_view(scalex=False)

            if done:
                plt.close(fig) # Auto-close plot when 10 seconds are up

            return line_raw, line_filtered

        ani = animation.FuncAnimation(fig, update, interval=40, blit=True, cache_frame_data=False)
        plt.show()  # Blocks until plt.close() is called

        t.join(timeout=1.0)

        # Save data
        if len(self.raw_data) >= MAX_SAMPLES:
            self._save_data(lead_name)
            return True
        else:
            print("\n[WARNING] Recording was interrupted before 10 seconds.")
            return False

    def _save_data(self, lead_name):
        folder = os.path.join(RECORD_DIR, lead_name)
        os.makedirs(folder, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(folder, f"{timestamp}.json")
        
        data = {
            "lead": lead_name,
            "timestamp": timestamp,
            "sample_rate": SAMPLE_RATE,
            "samples": len(self.raw_data),
            "raw": self.raw_data,
            "filtered": self.filtered_data
        }
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
            
        print(f"\n[SUCCESS] Saved 10 seconds of data to:\n  {filepath}")

# ──────────────────────────────────────────────
# MAIN MENU
# ──────────────────────────────────────────────
def main():
    port = find_port()
    if not port:
        print("[ERROR] No serial port found. Plug in the ESP32 and try again.")
        sys.exit(1)

    print("=" * 50)
    print("      12-LEAD ECG RECORDER")
    print("=" * 50)
    print(f"Detected ESP32 on port: {port}")

    while True:
        print("\nSelect the lead you are recording:")
        for i, lead in enumerate(LEADS, start=1):
            print(f"  {i}. {lead}")
        print("  0. Exit")
        
        choice = input("\nEnter number (0-12): ").strip()
        
        if choice == "0":
            print("Exiting...")
            break
            
        if not choice.isdigit() or not (1 <= int(choice) <= 12):
            print("Invalid choice. Try again.")
            continue
            
        lead_name = LEADS[int(choice) - 1]
        
        while True:
            print(f"\n--- Recording {lead_name} ---")
            recorder = ECGRecorder(port)
            success = recorder.record(lead_name)
            
            if success:
                retake = input("\nDo you want to retake this lead? (y/n): ").strip().lower()
                if retake != 'y':
                    break  # Go back to main menu
            else:
                retry = input("\nRecording failed/interrupted. Retry? (y/n): ").strip().lower()
                if retry == 'n':
                    break

if __name__ == "__main__":
    main()
