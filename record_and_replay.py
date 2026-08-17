import os
import sys

# Set Qt Backend before importing pyplot
import matplotlib
matplotlib.use('QtAgg')

import serial
import time
import threading
import collections
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# --- CONFIGURATION ---
COM_PORT = 'COM5'      # Change to match your ESP32 COM port
BAUD_RATE = 115200
RECORDINGS_DIR = 'recordings'
MAX_PLOT_SAMPLES = 500 # 2 seconds of live data on plot (at 250Hz)

if not os.path.exists(RECORDINGS_DIR):
    os.makedirs(RECORDINGS_DIR)

# Shared Data Buffers for Plotting
raw_buffer = collections.deque([0] * MAX_PLOT_SAMPLES, maxlen=MAX_PLOT_SAMPLES)
filt_buffer = collections.deque([0] * MAX_PLOT_SAMPLES, maxlen=MAX_PLOT_SAMPLES)

recording = False
file_handle = None
current_filename = ""
sample_idx = 0
start_time = 0
running = True
mode = "1"  # "1" = Live Record, "2" = Offline Replay
selected_replay_file = ""
ani = None  # Global reference to prevent garbage collection

# --- LIVE SERIAL STREAM & RECORDING THREAD ---
def handle_recording_stream():
    global recording, file_handle, current_filename, sample_idx, start_time, running

    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        print(f"\n[CONNECTED] Reading live data from {COM_PORT}...")
    except Exception as e:
        print(f"[ERROR] Could not open {COM_PORT}: {e}")
        running = False
        return

    while running:
        if ser.in_waiting > 0:
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line.startswith(">raw:"):
                    raw_val = float(line.split(":")[1])
                    next_line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if next_line.startswith(">filtered:"):
                        filt_val = float(next_line.split(":")[1])

                        # Append to live plot buffers
                        raw_buffer.append(raw_val)
                        filt_buffer.append(filt_val)

                        # Write to CSV if recording
                        if recording and file_handle:
                            time_ms = int((time.time() - start_time) * 1000)
                            file_handle.write(f"{sample_idx},{time_ms},{raw_val},{filt_val}\n")
                            sample_idx += 1
            except Exception:
                pass
    ser.close()


# --- OFFLINE CSV REPLAY THREAD ---
def handle_replay_stream():
    global running, selected_replay_file

    if not os.path.exists(selected_replay_file):
        print(f"[ERROR] File not found: {selected_replay_file}")
        running = False
        return

    print(f"\n[REPLAYING] Playing file: {selected_replay_file} (250 Hz timing)...")
    
    with open(selected_replay_file, "r") as f:
        lines = f.readlines()

    start_idx = 1 if lines[0].startswith("Index") else 0

    while running:
        for line in lines[start_idx:]:
            if not running:
                break
            parts = line.strip().split(",")
            if len(parts) >= 4:
                try:
                    raw_val = float(parts[2])
                    filt_val = float(parts[3])

                    raw_buffer.append(raw_val)
                    filt_buffer.append(filt_val)
                    time.sleep(0.004)  # 4ms delay = 250 Hz replay rate
                except ValueError:
                    continue


# --- TERMINAL CONTROL COMMANDS ---
def command_listener():
    global recording, file_handle, current_filename, sample_idx, start_time, running, mode
    
    if mode == "1":
        print("\n--- CONTROLS (RECORD MODE) ---")
        print("  Type 'start' -> Begin saving CSV to /recordings")
        print("  Type 'stop'  -> Stop saving CSV")
        print("  Type 'exit'  -> Exit program\n")
    else:
        print("\n--- CONTROLS (REPLAY MODE) ---")
        print("  Type 'exit'  -> Exit program\n")

    while running:
        cmd = input().strip().lower()
        if mode == "1":
            if cmd == "start" and not recording:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                current_filename = os.path.join(RECORDINGS_DIR, f"ecg_{timestamp}.csv")
                file_handle = open(current_filename, "w")
                file_handle.write("Index,Time_ms,Raw,Filtered\n")
                recording = True
                sample_idx = 0
                start_time = time.time()
                print(f"\n[>>> RECORDING STARTED >>>] Saving to: {current_filename}")

            elif cmd == "stop" and recording:
                recording = False
                if file_handle:
                    file_handle.close()
                print(f"\n[<<< RECORDING STOPPED <<<] Saved: {current_filename}\n")

        if cmd == "exit":
            running = False
            if recording and file_handle:
                file_handle.close()
            plt.close('all')
            sys.exit(0)


# --- LIVE MATPLOTLIB GUI ---
def run_live_plot():
    global ani
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6))
    
    title_str = 'ECG Live Monitor & Recorder' if mode == "1" else f'ECG Offline Replay: {os.path.basename(selected_replay_file)}'
    fig.canvas.manager.set_window_title(title_str)

    line_raw, = ax1.plot(raw_buffer, color='orange', label='Raw Signal')
    ax1.set_ylabel('ADC Raw')
    ax1.grid(True, linestyle='--', alpha=0.5)
    ax1.legend(loc='upper right')

    line_filt, = ax2.plot(filt_buffer, color='cyan', label='Filtered Signal')
    ax2.set_ylabel('Filtered Signal')
    ax2.set_xlabel('Samples (Rolling 2 Seconds)')
    ax2.grid(True, linestyle='--', alpha=0.5)
    ax2.legend(loc='upper right')

    def update_fig(frame):
        line_raw.set_ydata(raw_buffer)
        line_filt.set_ydata(filt_buffer)
        
        # Dynamic Y-axis scaling for Raw and Filtered signals
        try:
            # Raw Signal Scaling
            r_min, r_max = min(raw_buffer), max(raw_buffer)
            if r_max == r_min: r_max = r_min + 1
            r_pad = max((r_max - r_min) * 0.15, 50) # 15% padding
            
            current_r_ylim = ax1.get_ylim()
            # Update if limits are exceeded or span is too large
            if r_min < current_r_ylim[0] + r_pad*0.2 or r_max > current_r_ylim[1] - r_pad*0.2 or (current_r_ylim[1] - current_r_ylim[0]) > (r_max - r_min) * 2.0:
                ax1.set_ylim(r_min - r_pad, r_max + r_pad)

            # Filtered Signal Scaling
            f_min, f_max = min(filt_buffer), max(filt_buffer)
            if f_max == f_min: f_max = f_min + 1
            f_pad = max((f_max - f_min) * 0.15, 50) # 15% padding
            
            current_f_ylim = ax2.get_ylim()
            # Update if limits are exceeded or span is too large
            if f_min < current_f_ylim[0] + f_pad*0.2 or f_max > current_f_ylim[1] - f_pad*0.2 or (current_f_ylim[1] - current_f_ylim[0]) > (f_max - f_min) * 2.0:
                ax2.set_ylim(f_min - f_pad, f_max + f_pad)
                
        except Exception:
            pass
        
        if mode == "1":
            if recording:
                fig.patch.set_facecolor('#3a1111') # Red background tint when recording
            else:
                fig.patch.set_facecolor('#111111')
        else:
            fig.patch.set_facecolor('#112233')    # Blue background tint in replay mode

        return line_raw, line_filt

    ani = animation.FuncAnimation(fig, update_fig, interval=30, blit=False, cache_frame_data=False)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    print("=========================================")
    print("      ECG MONITOR, RECORDER & REPLAY     ")
    print("=========================================")
    print("1. Live Stream & Record from ESP32")
    print("2. Replay Saved CSV Recording (Offline Testing)")
    
    mode = input("Select mode (1 or 2): ").strip()

    if mode == "1":
        t_stream = threading.Thread(target=handle_recording_stream, daemon=True)
        t_stream.start()
    elif mode == "2":
        files = [f for f in os.listdir(RECORDINGS_DIR) if f.endswith('.csv')]
        if not files:
            print(f"\n[ERROR] No CSV recordings found inside '{RECORDINGS_DIR}/' folder!")
            sys.exit(0)

        print("\nSaved Recordings:")
        for idx, f in enumerate(files):
            print(f"  [{idx}] {f}")

        file_idx = input("\nSelect file index to replay: ").strip()
        if not file_idx.isdigit() or int(file_idx) >= len(files):
            print("Invalid selection.")
            sys.exit(0)

        selected_replay_file = os.path.join(RECORDINGS_DIR, files[int(file_idx)])

        t_stream = threading.Thread(target=handle_replay_stream, daemon=True)
        t_stream.start()
    else:
        print("Invalid choice.")
        sys.exit(0)

    t_cmd = threading.Thread(target=command_listener, daemon=True)
    t_cmd.start()

    run_live_plot()