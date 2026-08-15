import os
import numpy as np
import pandas as pd

SPANDAN_DIR = "spandan"
os.makedirs(SPANDAN_DIR, exist_ok=True)

def create_ecg_csv(filename, samples, sps=360):
    df = pd.DataFrame({
        'Index': np.arange(len(samples)),
        'Time_ms': (np.arange(len(samples)) * (1000.0 / sps)).astype(int),
        'Raw': np.round(samples).astype(int),
        'Filtered': np.round(samples).astype(int)
    })
    filepath = os.path.join(SPANDAN_DIR, filename)
    df.to_csv(filepath, index=False)
    print(f"[GENERATED] {filepath} ({len(samples)} samples, ~{len(samples)/sps:.1f}s)")

def generate_lead2_beat(bpm, sps=360):
    rr_sec = 60.0 / bpm
    n_samples = max(int(rr_sec * sps), 10)
    signal = np.full(n_samples, 2048.0)
    
    # R-peak center
    r_idx = min(int(0.3 * sps), n_samples - int(0.2 * sps))
    
    # --- P Wave ---
    p_offset = int(0.16 * sps) # 160ms PR interval
    p_idx = r_idx - p_offset
    p_width = int(0.045 * sps)
    p_amp = 50.0 
    for i in range(-p_width, p_width):
        if 0 <= p_idx + i < n_samples:
            signal[p_idx + i] += p_amp * np.exp(- (i / (p_width/2.2))**2)
            
    # --- Q Wave ---
    # Negative deflection right before R wave
    q_offset = int(0.02 * sps)
    q_idx = r_idx - q_offset
    q_width = int(0.015 * sps)
    q_amp = -40.0
    for i in range(-q_width, q_width):
        if 0 <= q_idx + i < n_samples:
            signal[q_idx + i] += q_amp * np.exp(- (i / (q_width/2.2))**2)

    # --- R Wave ---
    r_width = int(0.025 * sps)
    r_amp = 600.0
    for i in range(-r_width, r_width):
        if 0 <= r_idx + i < n_samples:
            signal[r_idx + i] += r_amp * np.exp(- (i / (r_width/2.2))**2)

    # --- S Wave ---
    # Deeper negative deflection right after R wave
    s_offset = int(0.025 * sps)
    s_idx = r_idx + s_offset
    s_width = int(0.02 * sps)
    s_amp = -150.0
    for i in range(-s_width, s_width):
        if 0 <= s_idx + i < n_samples:
            signal[s_idx + i] += s_amp * np.exp(- (i / (s_width/2.2))**2)
            
    # --- T Wave ---
    t_offset = int(0.20 * sps)
    t_idx = r_idx + t_offset
    t_width = int(0.07 * sps)
    t_amp = 110.0 
    for i in range(-t_width, t_width):
        if 0 <= t_idx + i < n_samples:
            signal[t_idx + i] += t_amp * np.exp(- (i / (t_width/2.2))**2)
            
    # Add a tiny bit of baseline wander and noise to make it realistic
    noise = np.random.normal(0, 3.0, n_samples)
    
    return signal + noise

if __name__ == "__main__":
    sps = 360
    duration_sec = 10.0
    total_samples = int(duration_sec * sps)
    
    # 1. Sinus Tachycardia Lead II (120 BPM)
    signal = []
    while len(signal) < total_samples:
        signal.extend(generate_lead2_beat(bpm=120, sps=sps))
    create_ecg_csv("Sinus tachycardia.csv", signal[:total_samples], sps)

    # 2. Sinus Bradycardia Lead II (40 BPM)
    signal = []
    while len(signal) < total_samples:
        signal.extend(generate_lead2_beat(bpm=40, sps=sps))
    create_ecg_csv("sinus_bradycardia_10s.csv", signal[:total_samples], sps)
