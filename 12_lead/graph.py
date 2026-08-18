import sys
import threading
import collections
import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from filter import ECGFilter

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
BAUD_RATE   = 115200
SAMPLE_RATE = 250
WINDOW_S    = 10
PORT        = None       # None = auto-detect

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
# RING BUFFERS
# ──────────────────────────────────────────────
MAX_SAMPLES = SAMPLE_RATE * WINDOW_S
buf_raw      = collections.deque([0.0] * MAX_SAMPLES, maxlen=MAX_SAMPLES)
buf_filtered = collections.deque([0.0] * MAX_SAMPLES, maxlen=MAX_SAMPLES)
lock = threading.Lock()

# ──────────────────────────────────────────────
# FILTER INSTANCE
# ──────────────────────────────────────────────
ecg_filter = ECGFilter(fs=SAMPLE_RATE, lp_cutoff=25.0, notch_freq=50.0, notch_q=50.0)

# ──────────────────────────────────────────────
# SERIAL READER THREAD
# ──────────────────────────────────────────────
def serial_reader(port):
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=1)
        print(f"[graph] Connected → {port} @ {BAUD_RATE} baud")
    except serial.SerialException as e:
        print(f"[graph] ERROR: {e}")
        sys.exit(1)

    first_sample = True
    while True:
        try:
            line = ser.readline().decode("ascii", errors="ignore").strip()
        except Exception:
            continue
        
        # The ESP32 sends 4 lines per sample: >L1raw, >L1hp, >L2raw, >L2hp.
        # We only want to plot the raw Lead I signal and locally filter it.
        if line.startswith(">L1raw:"):
            try:
                raw_adc = float(line.split(":")[-1].strip())
            except ValueError:
                continue
                
            # Convert ESP32 12-bit ADC counts to actual heart millivolts (mV)
            # ESP32 Vref = 3.3V, Max ADC = 4095, AD8232 Hardware Gain = ~1100
            raw_mv = (raw_adc / 4095.0) * (3.3 / 1100.0) * 1000.0

            if first_sample:
                ecg_filter.reset(raw_mv)
                first_sample = False

            filtered_mv = ecg_filter.process(raw_mv)
            with lock:
                buf_raw.append(raw_mv)
                buf_filtered.append(filtered_mv)

# ──────────────────────────────────────────────
# PLOT SETUP
# ──────────────────────────────────────────────
t_axis = [i / SAMPLE_RATE for i in range(MAX_SAMPLES)]

fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(14, 7), sharex=True)
fig.patch.set_facecolor("#0f0f0f")

for ax in (ax_top, ax_bot):
    ax.set_facecolor("#141414")
    ax.tick_params(colors="#aaaaaa")
    ax.yaxis.label.set_color("#aaaaaa")
    # Add vertical padding so the waveform doesn't touch the top/bottom edges
    ax.margins(y=0.4)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333333")
    ax.grid(True, color="#252525", linewidth=0.6, linestyle="--")

ax_bot.set_xlabel("Time (s)", color="#aaaaaa")
ax_top.set_ylabel("Voltage (mV) — Raw",      color="#aaaaaa")
ax_bot.set_ylabel("Voltage (mV) — Filtered", color="#aaaaaa")

fig.suptitle("AD8232 — Live ECG", color="#ffffff", fontsize=13, fontweight="bold")

(line_raw,)      = ax_top.plot(t_axis, list(buf_raw),      color="#ff6d00", linewidth=1.0)
(line_filtered,) = ax_bot.plot(t_axis, list(buf_filtered), color="#00e5ff", linewidth=1.2)

plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.subplots_adjust(hspace=0.08)

# ──────────────────────────────────────────────
# ANIMATION UPDATE
# ──────────────────────────────────────────────
def update(_):
    with lock:
        y_raw  = list(buf_raw)
        y_filt = list(buf_filtered)

    line_raw.set_ydata(y_raw)
    line_filtered.set_ydata(y_filt)

    ax_top.relim(); ax_top.autoscale_view(scalex=False)
    ax_bot.relim(); ax_bot.autoscale_view(scalex=False)

    return line_raw, line_filtered

# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
if __name__ == "__main__":
    port = PORT or find_port()
    if not port:
        print("[graph] ERROR: No serial port found.")
        sys.exit(1)

    threading.Thread(target=serial_reader, args=(port,), daemon=True).start()

    ani = animation.FuncAnimation(fig, update, interval=40, blit=True, cache_frame_data=False)
    plt.show()
