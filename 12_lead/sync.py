import numpy as np
from scipy import signal

def find_r_peaks(data, fs=250.0, distance_ratio=0.5, height_ratio=0.2):
    """
    Standard Pan-Tompkins style R-peak detection.
    """
    # 1. Bandpass filter (5-15 Hz) to isolate QRS
    nyq = 0.5 * fs
    b, a = signal.butter(2, [5.0 / nyq, 15.0 / nyq], btype='bandpass')
    bp = signal.filtfilt(b, a, data)
    
    # 2. Derivative and Squaring
    sq = np.diff(bp) ** 2
    
    # 3. Moving Average
    w = int(0.15 * fs)
    ma = np.convolve(sq, np.ones(w)/w, mode='same')
    
    # 4. Find peaks
    peaks, _ = signal.find_peaks(
        ma, 
        distance=int(fs * distance_ratio), 
        height=np.max(ma) * height_ratio
    )
    
    # 5. Fine tune peak positions on the original signal
    actual_peaks = []
    for p in peaks:
        start = max(0, p - int(fs * 0.1))
        end = min(len(data), p + int(fs * 0.1))
        window = data[start:end]
        if len(window) > 0:
            actual_peaks.append(start + np.argmax(window))
            
    return actual_peaks

def build_template(sig, peaks, pre_samples, mean_rr):
    """
    Extracts individual beats centered around `peaks` and averages them
    to create one clean, noise-free template heartbeat.
    """
    post_samples = mean_rr - pre_samples
    template_len = pre_samples + (post_samples if post_samples > 0 else int(0.55 * len(sig)))
    
    beats = []
    for p in peaks:
        s = p - pre_samples
        e = p + (post_samples if post_samples > 0 else int(0.55 * len(sig)))
        if s >= 0 and e <= len(sig):
            beat = sig[s:e].copy()
            # Apply linear detrending across the entire beat.
            # This ensures both the start (pre-P wave) and end (post-T wave) 
            # are mathematically forced to exactly 0.0, eliminating crossfade ripples.
            start_val = np.mean(beat[:8])
            end_val = np.mean(beat[-8:])
            drift = np.linspace(start_val, end_val, len(beat))
            beat -= drift
            beats.append(beat)
            
    if not beats:
        return np.zeros(template_len)
        
    # Trim all beats to the shortest one before averaging
    min_l = min(len(b) for b in beats)
    stacked = np.array([b[:min_l] for b in beats])
    
    return np.mean(stacked, axis=0)

def tile_template(template, peak_in_template, total_length, mean_rr, synth_peaks):
    """
    Places the template at each synthetic peak position using overlap-add 
    with a Hann window to ensure zero gaps and smooth transitions.
    """
    out = np.zeros(total_length)
    weight = np.zeros(total_length)
    tlen = len(template)
    win = np.hanning(tlen)
    
    for p in synth_peaks:
        start = p - peak_in_template
        end   = start + tlen
        s_src = 0
        e_src = tlen
        if start < 0:
            s_src = -start
            start = 0
        if end > total_length:
            e_src -= (end - total_length)
            end = total_length
            
        seg_len = end - start
        if seg_len > 0:
            out[start:end]    += template[s_src:s_src+seg_len] * win[s_src:s_src+seg_len]
            weight[start:end] += win[s_src:s_src+seg_len]
            
    # Normalize only where we actually placed something
    mask = weight > 1e-6
    out[mask] /= weight[mask]
    return out

def synchronize_leads(lead_dict, fs=250.0, master_lead="Lead_II"):
    """
    Takes a dictionary of independently recorded leads (e.g. Lead_I, Lead_II),
    calculates the Master Clock (mean RR) from the master lead, and rebuilds 
    all leads onto a perfectly synchronized synthetic timeline.
    """
    if master_lead not in lead_dict:
        print(f"WARNING: Master lead '{master_lead}' missing. Cannot phase-lock.")
        return lead_dict

    master_sig = lead_dict[master_lead]
    master_peaks = find_r_peaks(master_sig, fs)
    
    if len(master_peaks) < 2:
        print("WARNING: Not enough peaks in master lead to determine heart rate.")
        return lead_dict

    # 1. Establish Master Clock (mean RR interval)
    mean_rr = int(np.round(np.mean(np.diff(master_peaks))))
    
    # 2. Define synthetic output window (3 beats)
    pre_samples = int(0.35 * fs)   # Isoelectric lead-in
    n_beats = 3
    total_len = pre_samples + n_beats * mean_rr + int(0.55 * fs)
    
    # 3. Create synthetic perfectly-timed peak positions
    synth_peaks = [pre_samples + i * mean_rr for i in range(n_beats)]
    
    
    # 4. Build templates and tile them
    synced_dict = {}
    for name, sig in lead_dict.items():
        # Find this lead's own native peaks so the morphology isn't distorted
        local_peaks = find_r_peaks(sig, fs)
        if len(local_peaks) < 1:
            local_peaks = master_peaks # Fallback, though ideally shouldn't happen
            
        template = build_template(sig, local_peaks, pre_samples, mean_rr)
        
        # Tile it onto the shared synthetic timeline
        tiled = tile_template(template, pre_samples, total_len, mean_rr, synth_peaks)
        synced_dict[name] = tiled
        
    return synced_dict
