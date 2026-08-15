import os
import numpy as np
import pandas as pd
import random

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

def generate_lead2_beat(bpm, sps=360, p_wave=True, pr_delay_ms=160, is_pac=False, is_pvc=False, is_wpw=False, flutter=False, f_freq=250):
    rr_sec = 60.0 / bpm
    n_samples = max(int(rr_sec * sps), 10)
    
    # Ensure R-wave is placed far enough into the buffer to fit the P-wave!
    min_r_time = (pr_delay_ms / 1000.0) + 0.1
    r_idx = int(min_r_time * sps)
    if r_idx > n_samples - int(0.2 * sps):
        r_idx = n_samples - int(0.2 * sps)
        
    signal = np.full(n_samples, 2048.0)
    
    if flutter:
        t = np.arange(n_samples) / sps
        flutter_freq_hz = f_freq / 60.0
        signal += 50.0 * np.sin(2 * np.pi * flutter_freq_hz * t) # Very visible flutter

    # --- P Wave ---
    if p_wave and not flutter and not is_pvc:
        p_offset = int((pr_delay_ms / 1000.0) * sps)
        p_idx = r_idx - p_offset
        p_width = int(0.045 * sps)
        p_amp = -50.0 if is_pac else 60.0 
        for i in range(-p_width, p_width):
            if 0 <= p_idx + i < n_samples:
                signal[p_idx + i] += p_amp * np.exp(- (i / (p_width/2.2))**2)
                
    # --- QRS Complex ---
    if is_wpw:
        # Delta wave
        qrs_start = r_idx - int(0.06 * sps)
        
        # Explicit Q dip at -45ms (16 samples) to guarantee qrsWidth >= 100ms inside C++ 60ms window
        for i in range(-4, 4):
            if 0 <= r_idx - 16 + i < n_samples:
                signal[r_idx - 16 + i] -= 100.0
                
        delta_width = int(0.06 * sps)
        for i in range(-delta_width, 0):
            if 0 <= qrs_start + i < n_samples:
                signal[qrs_start + i] += 250.0 * np.exp(- (i / (delta_width/2.2))**2)
        r_width = int(0.05 * sps)
        r_amp = 700.0
        
        # Explicit deep S dip at +55ms (20 samples) inside 80ms window
        s_width = int(0.02 * sps)
        s_offset = int(0.05 * sps)
        s_amp = -50.0
        for i in range(-4, 4):
            if 0 <= r_idx + 20 + i < n_samples:
                signal[r_idx + 20 + i] -= 150.0
    elif is_pvc:
        # Huge, bizarre wide QRS for PVC
        # Explicit Q-wave at -50ms to ensure C++ measures wide QRS
        q_offset = int(0.05 * sps)
        q_idx = r_idx - q_offset
        for i in range(-5, 5):
            if 0 <= q_idx + i < n_samples:
                signal[q_idx + i] -= 50.0
                
        r_width = int(0.07 * sps)
        r_amp = 800.0
        s_width = int(0.08 * sps)
        s_amp = -600.0
        s_offset = int(0.06 * sps)
    else:
        # Normal QRS
        q_offset = int(0.02 * sps)
        q_idx = r_idx - q_offset
        q_width = int(0.015 * sps)
        for i in range(-q_width, q_width):
            if 0 <= q_idx + i < n_samples:
                signal[q_idx + i] += -50.0 * np.exp(- (i / (q_width/2.2))**2)
        r_width = int(0.025 * sps)
        r_amp = 600.0
        s_offset = int(0.025 * sps)
        s_width = int(0.02 * sps)
        s_amp = -150.0

    for i in range(-r_width, r_width):
        if 0 <= r_idx + i < n_samples:
            actual_r_amp = r_amp * 1.5 if (bpm >= 150 and not is_wpw and not is_pvc) else r_amp
            signal[r_idx + i] += actual_r_amp * np.exp(- (i / (r_width/2.2))**2)

    s_idx = r_idx + s_offset
    for i in range(-s_width, s_width):
        if 0 <= s_idx + i < n_samples:
            signal[s_idx + i] += s_amp * np.exp(- (i / (s_width/2.2))**2)
            
    # --- T Wave ---
    if not flutter:
        # T wave (dynamically shorten QT interval for fast heart rates to prevent T-P overlap)
        t_offset_ms = min(220, (rr_sec * 1000) * 0.45)
        t_offset = int((t_offset_ms / 1000.0) * sps)
        t_idx = r_idx + t_offset
        t_width = int(0.07 * sps)
        t_amp = 110.0
        if is_pvc or is_wpw: 
            t_amp = -150.0 # T wave inversion

        for i in range(-t_width, t_width):
            if 0 <= t_idx + i < n_samples:
                signal[t_idx + i] += t_amp * np.exp(- (i / (t_width/2.2))**2)
            
    return signal

def generate_dataset(name, bpm_list, duration=15.0, **kwargs):
    sps = 360
    total_samples = int(duration * sps)
    signal = []
    bpm_idx = 0
    while len(signal) < total_samples:
        bpm = bpm_list[bpm_idx % len(bpm_list)]
        signal.extend(generate_lead2_beat(bpm=bpm, sps=sps, **kwargs))
        bpm_idx += 1
    create_ecg_csv(f"{name}.csv", signal[:total_samples], sps)

def generate_afib(duration_sec=15.0):
    sps = 360
    total_samples = int(duration_sec * sps)
    signal = []
    while len(signal) < total_samples:
        bpm = random.uniform(80, 150)
        beat = generate_lead2_beat(bpm=bpm, sps=sps, p_wave=False)
        # Fibrillatory noise
        t = np.arange(len(beat)) / sps
        fib_noise = 12.0 * np.sin(2 * np.pi * 5.0 * t) + 8.0 * np.sin(2 * np.pi * 8.0 * t)
        signal.extend(beat + fib_noise)
    create_ecg_csv("Atrial Fibrillation.csv", signal[:total_samples], sps)

def generate_flutter(duration_sec=5.0):
    sps = 360
    total_samples = int(duration_sec * sps)
    signal = []
    bpm = 150
    while len(signal) < total_samples:
        beat = generate_lead2_beat(bpm=bpm, sps=sps, p_wave=False)
        t = np.arange(len(beat)) / sps
        flutter_wave = -60.0 * np.sin(2 * np.pi * 5.0 * t)  # ~300 flutter waves/min
        signal.extend(beat + flutter_wave)
    create_ecg_csv("Atrial Flutter.csv", signal[:total_samples], sps)
    
def generate_3rd_degree_block(duration_sec=5.0):
    sps = 360
    total_samples = int(duration_sec * sps)
    p_samples = np.full(total_samples, 2048.0)
    qrs_samples = np.full(total_samples, 0.0)
    
    p_interval = int((60.0 / 80.0) * sps)
    p_width = int(0.045 * sps)
    for i in range(0, total_samples, p_interval):
        for j in range(-p_width, p_width):
            if 0 <= i + j < total_samples:
                p_samples[i + j] += 60.0 * np.exp(- (j / (p_width/2.2))**2)
                
    qrs_interval = int((60.0 / 35.0) * sps)
    for i in range(int(0.5*sps), total_samples, qrs_interval):
        # Wide QRS
        for j in range(-30, 30):
            if 0 <= i + j < total_samples:
                qrs_samples[i + j] += 500.0 * np.exp(- (j / (30/2.2))**2)
        # Inverted T
        for j in range(-25, 25):
            if 0 <= i + j + 100 < total_samples:
                qrs_samples[i + j + 100] -= 150.0 * np.exp(- (j / (25/2.2))**2)
                
    combined = p_samples + qrs_samples
    create_ecg_csv("High AV BLOCK.csv", combined, sps)
    
def generate_ectopics(name, is_pvc=False, duration_sec=15.0):
    sps = 360
    total_samples = int(duration_sec * sps)
    signal = []
    count = 0
    while len(signal) < total_samples:
        if count % 4 == 2:
            # Truncate the beat before the ectopic so the ectopic is premature
            beat = generate_lead2_beat(bpm=72, sps=sps)
            signal.extend(beat[:200]) # ~550ms instead of 833ms
        elif count % 4 == 3: # Premature beat
            beat = generate_lead2_beat(bpm=110, sps=sps, is_pac=not is_pvc, is_pvc=is_pvc)
            signal.extend(beat)
            pause = np.full(int(0.6 * sps), 2048.0)
            signal.extend(pause)
        else:
            signal.extend(generate_lead2_beat(bpm=72, sps=sps))
        count += 1
    create_ecg_csv(f"{name}.csv", signal[:total_samples], sps)

def generate_mi_beat(bpm, sps=360, mi_type="antero_septal"):
    rr_sec = 60.0 / bpm
    n_samples = max(int(rr_sec * sps), 10)
    signal = np.full(n_samples, 2048.0)
    r_idx = min(int(0.3 * sps), n_samples - int(0.2 * sps))
    
    r_amp = 600.0; q_amp = 0.0; s_amp = -150.0
    t_amp = 110.0; st_elev = 0.0; qrs_wide = False
    
    if mi_type == "antero_septal": st_elev = 200.0
    elif mi_type == "antero_lateral": st_elev = 150.0; t_amp = -300.0
    elif mi_type == "antero_apical": st_elev = 100.0; r_amp = 1400.0
    elif mi_type == "lateral_wall": st_elev = 120.0; s_amp = -600.0
    elif mi_type == "inferior_wall": st_elev = 180.0; q_amp = -400.0
    elif mi_type == "inferior_lateral": st_elev = 140.0; q_amp = -400.0; t_amp = -300.0
    elif mi_type == "evolved_old": q_amp = -400.0; t_amp = -300.0
    elif mi_type == "ischaemic": st_elev = -150.0; t_amp = -300.0

    p_offset = int(0.16 * sps); p_width = int(0.045 * sps)
    for i in range(-p_width, p_width):
        if 0 <= r_idx - p_offset + i < n_samples:
            signal[r_idx - p_offset + i] += 50.0 * np.exp(- (i / (p_width/2.2))**2)

    if q_amp < 0:
        q_width = int(0.035 * sps)
        for i in range(-q_width, q_width):
            if 0 <= r_idx - int(0.04*sps) + i < n_samples:
                signal[r_idx - int(0.04*sps) + i] += q_amp * np.exp(- (i / (q_width/2.2))**2)

    r_width = int(0.045 * sps) if qrs_wide else int(0.025 * sps)
    for i in range(-r_width, r_width):
        if 0 <= r_idx + i < n_samples:
            signal[r_idx + i] += r_amp * np.exp(- (i / (r_width/2.2))**2)

    s_idx = r_idx + int(0.025 * sps)
    s_width = int(0.03 * sps) if qrs_wide else int(0.02 * sps)
    for i in range(-s_width, s_width):
        if 0 <= s_idx + i < n_samples:
            signal[s_idx + i] += s_amp * np.exp(- (i / (s_width/2.2))**2)
            
    t_idx = r_idx + int(0.20 * sps)
    t_width = int(0.07 * sps)
    
    if st_elev != 0:
        for i in range(s_idx + s_width, t_idx):
            if 0 <= i < n_samples: signal[i] += st_elev

    for i in range(-t_width, t_width):
        if 0 <= t_idx + i < n_samples:
            signal[t_idx + i] += t_amp * np.exp(- (i / (t_width/2.2))**2)
            
    return signal

def generate_mi_dataset(filename, mi_type, duration=15.0):
    sps = 360
    total_samples = int(duration * sps)
    signal = []
    while len(signal) < total_samples:
        signal.extend(generate_mi_beat(72, sps, mi_type))
    create_ecg_csv(filename, signal[:total_samples], sps)

def generate_bb_beat(bpm, sps=360, bb_type="lbbb"):
    rr_sec = 60.0 / bpm
    n_samples = max(int(rr_sec * sps), 10)
    signal = np.full(n_samples, 2048.0)
    r_idx = min(int(0.3 * sps), n_samples - int(0.2 * sps))
    
    # P wave
    for i in range(-16, 16):
        if 0 <= r_idx - 60 + i < n_samples: signal[r_idx - 60 + i] += 50.0 * np.exp(- (i / (16/2.2))**2)

    if bb_type == "lbbb":
        # Explicit Q at -50ms and S at +60ms to force wide QRS measurement in C++
        for i in range(-5, 5):
            if 0 <= r_idx - 18 + i < n_samples: signal[r_idx - 18 + i] -= 50.0
            if 0 <= r_idx + 22 + i < n_samples: signal[r_idx + 22 + i] -= 50.0
            
        # Huge wide M-shaped QRS
        for i in range(-25, 25):
            if 0 <= r_idx + i < n_samples:
                val = 400.0 if abs(i) < 5 else 600.0 # Notch in the middle
                signal[r_idx + i] += val * np.exp(- (i / (25/2.2))**2)
        # Inverted T
        for i in range(-25, 25):
            if 0 <= r_idx + 80 + i < n_samples: signal[r_idx + 80 + i] -= 150.0 * np.exp(- (i / (25/2.2))**2)
    elif bb_type == "rbbb":
        # Explicit Q at -40ms to ensure width
        for i in range(-5, 5):
            if 0 <= r_idx - 14 + i < n_samples: signal[r_idx - 14 + i] -= 50.0
            
        # Sharp R, deep wide slurred S at +35 samples (~100ms)
        for i in range(-9, 9):
            if 0 <= r_idx + i < n_samples: signal[r_idx + i] += 500.0 * np.exp(- (i / (9/2.2))**2)
        for i in range(-25, 25):
            if 0 <= r_idx + 35 + i < n_samples: signal[r_idx + 35 + i] -= 250.0 * np.exp(- (i / (25/2.2))**2)
        # Upright T
        for i in range(-25, 25):
            if 0 <= r_idx + 80 + i < n_samples: signal[r_idx + 80 + i] += 180.0 * np.exp(- (i / (25/2.2))**2)

    return signal

def generate_bb_dataset(filename, bb_type, duration=15.0):
    sps = 360
    total_samples = int(duration * sps)
    signal = []
    while len(signal) < total_samples:
        signal.extend(generate_bb_beat(72, sps, bb_type))
    create_ecg_csv(filename, signal[:total_samples], sps)

def generate_hypertrophy_beat(bpm, sps=360, h_type="lvh"):
    rr_sec = 60.0 / bpm
    n_samples = max(int(rr_sec * sps), 10)
    signal = np.full(n_samples, 2048.0)
    r_idx = min(int(0.3 * sps), n_samples - int(0.2 * sps))
    
    # P wave
    for i in range(-16, 16):
        if 0 <= r_idx - 60 + i < n_samples: signal[r_idx - 60 + i] += 50.0 * np.exp(- (i / (16/2.2))**2)

    r_amp = 1800.0 if h_type == "lvh" else 400.0
    for i in range(-9, 9):
        if 0 <= r_idx + i < n_samples: signal[r_idx + i] += r_amp * np.exp(- (i / (9/2.2))**2)

    s_amp = -150.0 if h_type == "lvh" else -1200.0
    for i in range(-9, 9):
        if 0 <= r_idx + 12 + i < n_samples: signal[r_idx + 12 + i] += s_amp * np.exp(- (i / (9/2.2))**2)
            
    if h_type == "lvh":
        # LVH Strain
        for i in range(r_idx + 21, r_idx + 72):
            if 0 <= i < n_samples: signal[i] -= 100.0
        for i in range(-25, 25):
            if 0 <= r_idx + 72 + i < n_samples: signal[r_idx + 72 + i] -= 150.0 * np.exp(- (i / (25/2.2))**2)
    else:
        for i in range(-25, 25):
            if 0 <= r_idx + 72 + i < n_samples: signal[r_idx + 72 + i] += 110.0 * np.exp(- (i / (25/2.2))**2)
            
    return signal

def generate_hypertrophy_dataset(filename, h_type, duration=15.0):
    sps = 360
    total_samples = int(duration * sps)
    signal = []
    while len(signal) < total_samples:
        signal.extend(generate_hypertrophy_beat(72, sps, h_type))
    create_ecg_csv(filename, signal[:total_samples], sps)

if __name__ == "__main__":
    print("Generating Pristine Distinct Spandan Datasets...")
    generate_dataset("Sinus Tachycardia", [120], duration=5.0)
    generate_dataset("Sinus Bradycardia", [40], duration=5.0)
    generate_dataset("Atrial Tachycardia", [140], duration=5.0)
    generate_dataset("SVT", [170], p_wave=False, duration=5.0)
    generate_dataset("Atrial Flutter", [150], flutter=True, f_freq=300, duration=5.0)
    generate_afib()
    generate_dataset("AV BLOCK", [75], pr_delay_ms=350, duration=5.0) # Extremely long PR
    generate_3rd_degree_block(duration_sec=5.0)
    generate_dataset("WPW Syndrome", [75], pr_delay_ms=90, is_wpw=True, duration=5.0)
    generate_dataset("Junctional Rythm", [45], p_wave=False, duration=5.0)
    generate_ectopics("Atrial Ectopics", is_pvc=False)
    generate_ectopics("Ventricular Ectopics", is_pvc=True)
    
    generate_mi_dataset("Antero Septal MI.csv", "antero_septal", duration=5.0)
    generate_mi_dataset("Antero Apical MI.csv", "antero_apical", duration=5.0)
    generate_mi_dataset("Antero Lateral MI.csv", "antero_lateral", duration=5.0)
    generate_mi_dataset("Lateral Wall MI.csv", "lateral_wall", duration=5.0)
    generate_mi_dataset("Inferior Wall MI.csv", "inferior_wall", duration=5.0)
    generate_mi_dataset("Inferior Lateral MI.csv", "inferior_lateral", duration=5.0)
    generate_mi_dataset("Evolved _ Old MI.csv", "evolved_old", duration=5.0)
    generate_mi_dataset("Ischaemic ST-T changes.csv", "ischaemic", duration=5.0)
    
    generate_bb_dataset("Left Bundle Branch Block.csv", "lbbb", duration=5.0)
    generate_bb_dataset("Right Bundle Branch Block.csv", "rbbb", duration=5.0)
    generate_hypertrophy_dataset("Left Ventricular Hypertrophy.csv", "lvh", duration=5.0)
    generate_hypertrophy_dataset("Right Ventricular Hypertrophy.csv", "rvh", duration=5.0)
    print("All pristine datasets generated successfully!")
