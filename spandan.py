import os
import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt, sawtooth

# --- 1. Simulation Parameters ---
duration_sec = 10.0     # 10 seconds of ECG data
fs = 500                # 500 Hz sampling rate (2 ms step)
total_samples = int(duration_sec * fs)
t = np.linspace(0, duration_sec, total_samples, endpoint=False)
time_ms = (t * 1000).astype(int)

# --- 2. Generate Atrial Flutter Morphology ---
# Continuous ~300 bpm (5 Hz) sawtooth 'F' waves characteristic of Lead II
flutter_freq = 5.0  # 5 Hz = 300 flutter oscillations/min
flutter_waves = -0.18 * sawtooth(2 * np.pi * flutter_freq * t, width=0.35)

clean_ecg = flutter_waves.copy()

def gaussian(x, mu, sigma, amp):
    return amp * np.exp(-((x - mu) ** 2) / (2 * sigma ** 2))

# Ventricular response (regular conduction, ~92 bpm, RR interval ~0.65s)
rr_interval = 0.65
num_beats = int(duration_sec / rr_interval) + 2

for i in range(num_beats):
    beat_center = i * rr_interval + 0.15
    if beat_center > duration_sec + 0.2:
        continue
    
    # Q dip
    q_wave = gaussian(t, beat_center - 0.015, 0.005, -0.08)
    # Sharp narrow R spike
    r_wave = gaussian(t, beat_center, 0.007, 1.10)
    # Small S wave dip
    s_wave = gaussian(t, beat_center + 0.015, 0.008, -0.22)
    # T wave merging with background flutter
    t_wave = gaussian(t, beat_center + 0.12, 0.035, 0.18)
    
    clean_ecg += (q_wave + r_wave + s_wave + t_wave)

# --- 3. Noise and Baseline Drift (Raw) ---
baseline_wander = 0.06 * np.sin(2 * np.pi * 0.3 * t)
noise_50hz = 0.025 * np.sin(2 * np.pi * 50 * t)
gaussian_noise = np.random.normal(0, 0.015, total_samples)

raw_ecg = clean_ecg + baseline_wander + noise_50hz + gaussian_noise

# --- 4. Bandpass Filtering (0.5 Hz - 40 Hz) ---
def bandpass_filter(data, lowcut, highcut, fs, order=3):
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = butter(order, [low, high], btype='band')
    return filtfilt(b, a, data)

filtered_ecg = bandpass_filter(raw_ecg, lowcut=0.5, highcut=40.0, fs=fs)

# --- 5. Export to CSV in 'Spandan' Directory ---
output_dir = "Spandan"
os.makedirs(output_dir, exist_ok=True)
output_filepath = os.path.join(output_dir, "atrial_flutter_10s.csv")

df = pd.DataFrame({
    'Index': np.arange(total_samples),
    'Time_ms': time_ms,
    'Raw': np.round(raw_ecg, 4),
    'Filtered': np.round(filtered_ecg, 4)
})

df.to_csv(output_filepath, index=False)
print(f"Generated {len(df)} samples across {duration_sec}s.")
print(f"Saved dataset to: {output_filepath}")