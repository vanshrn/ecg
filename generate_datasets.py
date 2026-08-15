import os
import random
import numpy as np
import pandas as pd

RECORDINGS_DIR = "recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

def create_ecg_csv(filename, samples, sps=360):
    df = pd.DataFrame({
        'Index': np.arange(len(samples)),
        'Time_ms': (np.arange(len(samples)) * (1000.0 / sps)).astype(int),
        'Raw': np.round(samples).astype(int),
        'Filtered': np.round(samples).astype(int)
    })
    filepath = os.path.join(RECORDINGS_DIR, filename)
    df.to_csv(filepath, index=False)
    print(f"[GENERATED] {filename} ({len(samples)} samples, ~{len(samples)/sps:.1f}s)")

def generate_beat(bpm=72, p_wave=True, qrs_high=False, pr_delay_ms=160, is_pac=False, is_pvc=False, qrs_present=True, is_wpw=False, sps=360):
    rr_sec = 60.0 / bpm
    n_samples = max(int(rr_sec * sps), 10)
    signal = np.full(n_samples, 2048.0)
    
    # Fix R-peak, but bound it so high BPM rhythms don't cut off their own R-peaks
    r_idx = min(int(0.4 * sps), n_samples - int(0.15 * sps))
    
    # P Wave
    if p_wave and not is_pvc:
        p_offset = int((pr_delay_ms / 1000.0) * sps)
        p_idx = max(0, r_idx - p_offset)
        p_width = int(0.05 * sps)
        p_amp = -45.0 if is_pac else 55.0 
        for i in range(-p_width, p_width):
            if 0 <= p_idx + i < n_samples:
                signal[p_idx + i] += p_amp * np.exp(- (i / (p_width/2.2))**2)
                
    # QRS and T Waves (Only if not a dropped beat)
    if qrs_present:
        # QRS Complex
        if is_wpw:
            r_amp = 750.0
            qrs_width = int(0.10 * sps) # Total width ~100ms, starts 50ms before R-peak
        else:
            r_amp = 750.0 if (qrs_high or is_pvc) else 350.0
            qrs_width = int(0.14 * sps) if (qrs_high or is_pvc) else int(0.06 * sps)
        
        for i in range(-qrs_width, qrs_width):
            if 0 <= r_idx + i < n_samples:
                signal[r_idx + i] += r_amp * np.exp(- (i / (qrs_width/2.2))**2)
                
        # T Wave
        t_idx = r_idx + int(0.22 * sps)
        t_width = int(0.08 * sps)
        t_amp = -120.0 if is_pvc else 90.0 
        for i in range(-t_width, t_width):
            if 0 <= t_idx + i < n_samples:
                signal[t_idx + i] += t_amp * np.exp(- (i / (t_width/2.2))**2)
            
    return signal

if __name__ == "__main__":
    sps = 360
    duration_sec = 15.0
    total_samples = int(duration_sec * sps)
    
    base_signal = []
    
    # Generate 5 seconds of normal beats to cleanly flush the memory buffer
    for _ in range(6):
        base_signal.extend(generate_beat(bpm=75, p_wave=True, pr_delay_ms=160, sps=sps))
        
    # 1. AV Block 2nd Degree (Mobitz Type I / Wenckebach)
    signal = base_signal.copy()
    while len(signal) < total_samples:
        signal.extend(generate_beat(bpm=75, p_wave=True, pr_delay_ms=160, sps=sps))
        signal.extend(generate_beat(bpm=75, p_wave=True, pr_delay_ms=230, sps=sps))
        signal.extend(generate_beat(bpm=75, p_wave=True, pr_delay_ms=300, sps=sps))
        signal.extend(generate_beat(bpm=75, p_wave=True, pr_delay_ms=160, qrs_present=False, sps=sps))
    create_ecg_csv("wenckebach_15s.csv", signal[:total_samples], sps)

    # 2. AV Block 2nd Degree (Mobitz Type II)
    # Pattern: Constant PR interval, but sudden dropped QRS complexes (usually 2:1, 3:1, or 4:1).
    signal = base_signal.copy()
    while len(signal) < total_samples:
        signal.extend(generate_beat(bpm=75, p_wave=True, pr_delay_ms=160, sps=sps))
        signal.extend(generate_beat(bpm=75, p_wave=True, pr_delay_ms=160, sps=sps))
        signal.extend(generate_beat(bpm=75, p_wave=True, pr_delay_ms=160, sps=sps))
        signal.extend(generate_beat(bpm=75, p_wave=True, pr_delay_ms=160, qrs_present=False, sps=sps))
    create_ecg_csv("mobitz2_15s.csv", signal[:total_samples], sps)

    # 3. AV Block 3rd Degree (Complete Heart Block)
    # Pattern: Complete dissociation. P waves fire at 75 BPM, QRS complexes fire at ~40 BPM.
    signal = base_signal.copy()
    
    # We will generate P-waves and QRS waves completely independently to simulate dissociation.
    p_samples = np.full(total_samples - len(signal), 2048.0)
    qrs_samples = np.full(total_samples - len(signal), 0.0)
    
    p_interval = int((60.0 / 80.0) * sps) # 80 BPM atrial rate
    qrs_interval = int((60.0 / 40.0) * sps) # 40 BPM ventricular escape rate
    
    # Generate P-waves
    p_width = int(0.05 * sps)
    for i in range(0, len(p_samples), p_interval):
        for j in range(-p_width, p_width):
            if 0 <= i + j < len(p_samples):
                p_samples[i + j] += 55.0 * np.exp(- (j / (p_width/2.2))**2)
                
    # Generate QRS/T-waves
    qrs_width = int(0.06 * sps)
    t_offset = int(0.22 * sps)
    t_width = int(0.08 * sps)
    
    for i in range(0, len(qrs_samples), qrs_interval):
        # QRS
        for j in range(-qrs_width, qrs_width):
            if 0 <= i + j < len(qrs_samples):
                qrs_samples[i + j] += 350.0 * np.exp(- (j / (qrs_width/2.2))**2)
        # T wave
        for j in range(-t_width, t_width):
            if 0 <= i + t_offset + j < len(qrs_samples):
                qrs_samples[i + t_offset + j] += 90.0 * np.exp(- (j / (t_width/2.2))**2)
                
    combined_dissociation = p_samples + qrs_samples
    signal.extend(combined_dissociation)
    create_ecg_csv("third_degree_block_15s.csv", signal[:total_samples], sps)

    # 4. AV Block 1st Degree (Prolonged PR)
    # Pattern: Normal rhythm but PR interval > 200ms consistently.
    signal = base_signal.copy()
    while len(signal) < total_samples:
        signal.extend(generate_beat(bpm=75, p_wave=True, pr_delay_ms=260, sps=sps))
    create_ecg_csv("first_degree_block_15s.csv", signal[:total_samples], sps)

    # 5. Sinus Bradycardia
    # Pattern: Normal beats, but very slow (<50 BPM). Ramp down slowly so it doesn't look like a dropped beat.
    signal = base_signal.copy()
    current_bpm = 75
    while len(signal) < total_samples:
        current_bpm = max(40, current_bpm - 8)
        signal.extend(generate_beat(bpm=current_bpm, p_wave=True, pr_delay_ms=160, sps=sps))
    create_ecg_csv("sinus_bradycardia_15s.csv", signal[:total_samples], sps)

    # 6. Sinus Tachycardia
    # Pattern: Normal beats, but fast (100-130 BPM)
    signal = base_signal.copy()
    while len(signal) < total_samples:
        signal.extend(generate_beat(bpm=115, p_wave=True, pr_delay_ms=140, sps=sps))
    create_ecg_csv("sinus_tachycardia_15s.csv", signal[:total_samples], sps)

    # 6b. Atrial Tachycardia
    # Pattern: Sudden onset of fast rhythm (130-150 BPM) with P-waves present.
    signal = base_signal.copy()
    while len(signal) < total_samples:
        signal.extend(generate_beat(bpm=140, p_wave=True, pr_delay_ms=130, sps=sps))
    create_ecg_csv("atrial_tachycardia_15s.csv", signal[:total_samples], sps)

    # 7. SVT (Supraventricular Tachycardia)
    # Pattern: Very fast (>160 BPM), narrow QRS, P-waves usually hidden.
    signal = base_signal.copy()
    while len(signal) < total_samples:
        signal.extend(generate_beat(bpm=170, p_wave=False, sps=sps))
    create_ecg_csv("svt_15s.csv", signal[:total_samples], sps)

    # 8. Sinus Arrest
    # Pattern: Normal rhythm, then a massive pause > 3 seconds but < 4 seconds.
    signal = base_signal.copy()
    # The base beat leaves 0.4s after the R-peak, and the next beat has 0.4s before the R-peak.
    # To get a 3.5s R-R gap, we only need an extra 2.7s of flatline.
    signal.extend(np.full(int(2.7 * sps), 2048.0))
    while len(signal) < total_samples:
        signal.extend(generate_beat(bpm=75, p_wave=True, sps=sps))
    create_ecg_csv("sinus_arrest_15s.csv", signal[:total_samples], sps)

    # 9. Atrial Flutter
    # Pattern: Fast rate (130-150 BPM) with no clear distinct P-waves (sawtooth is filtered out in this simple model).
    signal = base_signal.copy()
    while len(signal) < total_samples:
        signal.extend(generate_beat(bpm=145, p_wave=False, sps=sps))
    create_ecg_csv("atrial_flutter_15s.csv", signal[:total_samples], sps)

    # 10. Junctional Rhythm
    # Pattern: Slow, perfectly regular narrow complex (40-60 BPM), but absolutely no P-waves.
    signal = base_signal.copy()
    while len(signal) < total_samples:
        signal.extend(generate_beat(bpm=45, p_wave=False, sps=sps))
    create_ecg_csv("junctional_rhythm_15s.csv", signal[:total_samples], sps)

    # 11. Wolff-Parkinson-White (WPW)
    # Pattern: Short PR interval (< 120ms) with a Delta wave (slurred QRS upstroke) widening the QRS.
    signal = base_signal.copy()
    while len(signal) < total_samples:
        signal.extend(generate_beat(bpm=75, p_wave=True, pr_delay_ms=155, is_wpw=True, sps=sps))
    create_ecg_csv("wpw_15s.csv", signal[:total_samples], sps)
