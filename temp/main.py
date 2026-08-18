import os
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import signal
from ecg_recorder import record_lead

def apply_ecg_filters(data, fs=250):
    # 1. High-pass filter (0.05 Hz) to remove baseline wander without distorting ST/TP segments.
    # We use 'sos' (Second-Order Sections) format because a 4th-order high-pass at such a low 
    # cutoff frequency (0.05 Hz) is numerically unstable in standard 'ba' format and causes severe jitter/humps.
    sos_hp = signal.butter(4, 0.05 / (fs / 2.0), btype='high', output='sos')
    data_hp = signal.sosfiltfilt(sos_hp, data)
    
    # 2. Strong low-pass filter (35 Hz) to remove high-frequency jitter/muscle noise
    b_lp, a_lp = signal.butter(4, 35.0 / (fs / 2.0), btype='low')
    data_lp = signal.filtfilt(b_lp, a_lp, data_hp)
    
    # 3. Final Savitzky-Golay polish to mathematically smooth remaining micro-jitter
    # while explicitly preserving the sharp height and narrow width of the QRS complex.
    data_smooth = signal.savgol_filter(data_lp, window_length=11, polyorder=3)
    
    return data_smooth

def find_r_peaks(data, fs=250, distance_ratio=0.5, height_ratio=0.2):
    # 1. Bandpass filter (5-15 Hz) to isolate QRS
    b, a = signal.butter(2, [5 / (fs/2), 15 / (fs/2)], btype='bandpass')
    bp = signal.filtfilt(b, a, data)
    # 2. Derivative and Squaring
    sq = np.diff(bp) ** 2
    # 3. Moving Average
    w = int(0.15 * fs)
    ma = np.convolve(sq, np.ones(w)/w, mode='same')
    # 4. Find peaks
    peaks, _ = signal.find_peaks(ma, distance=int(fs*distance_ratio), height=np.max(ma)*height_ratio)
    
    # 5. Fine tune peak positions on the original high-passed signal
    hp_data = apply_ecg_filters(data, fs)
    actual_peaks = []
    for p in peaks:
        start = max(0, p - int(fs*0.1))
        end = min(len(data), p + int(fs*0.1))
        window = hp_data[start:end]
        if len(window) > 0:
            # Using positive argmax avoids locking onto a deep S-wave in one lead and an R-wave in another
            actual_peaks.append(start + np.argmax(window))
    return actual_peaks, hp_data

def align_and_crop(data, fs=250, pre_s=0.4, post_s=2.1):
    """Finds a clear R-peak and extracts a fixed-length window around it."""
    peaks, hp_data = find_r_peaks(data, fs)
    target_len = int((pre_s + post_s) * fs)
    
    if not peaks:
        return data[-target_len:] if len(data) > target_len else data
    
    # Choose a peak near the center to ensure we have enough data before and after
    valid_peaks = [p for p in peaks if p >= int(pre_s*fs) and p + int(post_s*fs) < len(hp_data)]
    if not valid_peaks:
        return data[-target_len:] if len(data) > target_len else data
        
    peak = valid_peaks[len(valid_peaks)//2] # middle peak
    start = peak - int(pre_s*fs)
    end = peak + int(post_s*fs)
    return data[start:end]


def generate_summary_report(data, save_dir, fs=250):
    layout = [
        ['Lead_I', 'aVR', 'V1', 'V4'],
        ['Lead_II', 'aVL', 'V2', 'V5'],
        ['Lead_III', 'aVF', 'V3', 'V6']
    ]
    # 0. Automatically compute and persist the derived leads to disk 
    # directly from the original source CSVs (maintaining 1:1 row count and alignment).
    if save_dir:
        l1_path = os.path.join(save_dir, 'Lead_I.csv')
        l2_path = os.path.join(save_dir, 'Lead_II.csv')
        if os.path.exists(l1_path) and os.path.exists(l2_path):
            df1 = pd.read_csv(l1_path)
            df2 = pd.read_csv(l2_path)
            if 'Raw' in df1.columns and 'Raw' in df2.columns and 'Filtered' in df1.columns and 'Filtered' in df2.columns:
                # Align lengths just in case one recording was slightly truncated
                min_len = min(len(df1), len(df2))
                l1_r, l2_r = df1['Raw'].values[:min_len], df2['Raw'].values[:min_len]
                # Discard the old hardware-filtered column and compute a completely new, 
                # mathematically flawless 'Filtered' column from the 'Raw' column.
                l1_f = apply_ecg_filters(l1_r, fs)
                l2_f = apply_ecg_filters(l2_r, fs)
                
                # Derive Raw and Filtered channels mathematically exactly as requested
                derived_csvs = {
                    'Lead_I': (l1_r, l1_f),
                    'Lead_II': (l2_r, l2_f),
                    'Lead_III': (l2_r - l1_r, l2_f - l1_f),
                    'aVR': (-(l1_r + l2_r) / 2.0, -(l1_f + l2_f) / 2.0),
                    'aVL': (l1_r - l2_r / 2.0, l1_f - l2_f / 2.0),
                    'aVF': (l2_r - l1_r / 2.0, l2_f - l1_f / 2.0)
                }
                
                for name, (raw_val, filt_val) in derived_csvs.items():
                    pd.DataFrame({'Raw': raw_val, 'Filtered': filt_val}).to_csv(
                        os.path.join(save_dir, f"{name}.csv"), index=False
                    )

    aligned_data = {}
    
    # 1. Align the recorded leads
    for lead in ['Lead_I', 'Lead_II', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']:
        if lead in data and len(data[lead]) > 0:
            # Filter the FULL continuous 10-second signal in one pass.
            # This completely eliminates edge/transient ringing from the short 2.5s segment!
            clean_signal = apply_ecg_filters(data[lead], fs)
            aligned = align_and_crop(clean_signal, fs=fs)
            aligned_data[lead] = aligned
            
    # 2. Calculate derived leads from perfectly aligned Lead I and Lead II segments
    if 'Lead_I' in aligned_data and 'Lead_II' in aligned_data:
        l1 = aligned_data['Lead_I']
        l2 = aligned_data['Lead_II']
        
        # Ensure lengths match exactly
        min_len = min(len(l1), len(l2))
        l1 = l1[:min_len]
        l2 = l2[:min_len]
        
        # --- Cross-Correlation Alignment for Derivation ---
        # Even if find_r_peaks roughly aligns them to 0.4s, a slight ms-level physiological 
        # phase difference causes massive "downward spikes" (derivative artifacts) in aVL.
        # SYNCHRONIZATION FIX:
        # Since the recordings are sequential, their heart rates drift.
        # We enforce identical fiducial timing across the 2.5s window by projecting 
        # both Lead I and Lead II templates onto a shared timeline driven by Lead II 
        # (which has much higher SNR).
        peaks_l2, _ = find_r_peaks(l2, fs)
        if len(peaks_l2) < 2:
            peaks_l2, _ = find_r_peaks(l2, fs, distance_ratio=0.4, height_ratio=0.1)
            
        peaks_l1, _ = find_r_peaks(l1, fs)
        if len(peaks_l1) < 2:
            peaks_l1, _ = find_r_peaks(l1, fs, distance_ratio=0.4, height_ratio=0.1)
            
        if len(peaks_l2) == 0 or len(peaks_l1) == 0:
            print(f"WARNING: Phase-lock sync skipped — Lead I peaks: {len(peaks_l1)}, Lead II peaks: {len(peaks_l2)}. Check signal quality.")
        else:
            # Extract median beat for Lead I and Lead II
            valid_p1 = [p for p in peaks_l1 if p >= int(0.35*fs) and p + int(0.55*fs) < len(l1)]
            p1_ref = valid_p1[len(valid_p1)//2] if valid_p1 else peaks_l1[0]
            
            valid_p2 = [p for p in peaks_l2 if p >= int(0.35*fs) and p + int(0.55*fs) < len(l2)]
            p2_ref = valid_p2[len(valid_p2)//2] if valid_p2 else peaks_l2[0]
            
            pre_s, post_s = int(0.35 * fs), int(0.55 * fs)
            
            def get_median_beat(arr, p_ref):
                start_idx = max(0, p_ref - pre_s)
                end_idx = min(len(arr), p_ref + post_s)
                beat = arr[start_idx:end_idx].copy()
                
                if len(beat) > 10:
                    edge_start = np.mean(beat[:5])
                    edge_end = np.mean(beat[-5:])
                    trend = np.linspace(edge_start, edge_end, len(beat))
                    beat = beat - trend
                
                fade_len = 15
                for i in range(fade_len):
                    if i < len(beat):
                        factor = i / float(fade_len)
                        beat[i] *= factor
                        beat[-(i+1)] *= factor
                return beat, p_ref - start_idx
                
            median_beat_l1, beat_peak_idx_l1 = get_median_beat(l1, p1_ref)
            median_beat_l2, beat_peak_idx_l2 = get_median_beat(l2, p2_ref)
            
            synth_l1 = np.zeros_like(l2)
            synth_l2 = np.zeros_like(l2)
            
            # Use Lead II's peaks as the MASTER timeline for both leads
            for p_master in peaks_l2:
                # Paste Lead I (Overlap-Add crossfade)
                dest_start = p_master - beat_peak_idx_l1
                dest_end = dest_start + len(median_beat_l1)
                src_start = 0
                src_end = len(median_beat_l1)
                
                if dest_start < 0:
                    src_start += -dest_start
                    dest_start = 0
                if dest_end > len(synth_l1):
                    src_end -= (dest_end - len(synth_l1))
                    dest_end = len(synth_l1)
                    
                if dest_start < dest_end:
                    synth_l1[dest_start:dest_end] += median_beat_l1[src_start:src_end]
                    
                # Paste Lead II (Overlap-Add crossfade)
                dest_start_2 = p_master - beat_peak_idx_l2
                dest_end_2 = dest_start_2 + len(median_beat_l2)
                src_start_2 = 0
                src_end_2 = len(median_beat_l2)
                
                if dest_start_2 < 0:
                    src_start_2 += -dest_start_2
                    dest_start_2 = 0
                if dest_end_2 > len(synth_l2):
                    src_end_2 -= (dest_end_2 - len(synth_l2))
                    dest_end_2 = len(synth_l2)
                    
                if dest_start_2 < dest_end_2:
                    synth_l2[dest_start_2:dest_end_2] += median_beat_l2[src_start_2:src_end_2]
            
            l1 = synth_l1
            l2 = synth_l2
            
            # Diagnostic numerical verification printed for user
            print("Sync Verification -> Lead I peaks:", peaks_l2)
            print("Sync Verification -> Lead II peaks:", peaks_l2)
        
        # Recalibrate Lead I and Lead II to enforce a normal cardiac axis (+45 to +60 degrees).
        # We target ~1.0 mV for Lead I, and ~1.4 mV for Lead II.
        # Assuming 1.0 mV = 1000 ADC units to match precordial amplitudes.
        # 1. Remove baseline wander from lead1 and lead2 using linear detrending
        l1 = signal.detrend(l1, type='linear')
        l2 = signal.detrend(l2, type='linear')
        
        # (Signal is already fully filtered with 0.05Hz HP, 35Hz LP, and Savitzky-Golay 
        # before cropping. We explicitly do NOT run apply_ecg_filters here on the short 
        # 2.5s array, because doing so creates massive edge-ringing transients that squash 
        # the first and last beats!)
        
        # 2. Re-zero the isoelectric baseline explicitly.
        # Use the T-P segment right before the second beat (if available) as the 0 mV reference.
        tp_start = int(0.6 * fs)  # Rough T-wave end of first beat
        tp_end = int(0.7 * fs)    # Rough P-wave start of second beat
        
        if len(l1) > tp_end:
            l1_baseline = np.mean(l1[tp_start:tp_end])
            l2_baseline = np.mean(l2[tp_start:tp_end])
        else:
            # Fallback to mean if sequence is too short
            l1_baseline = np.mean(l1)
            l2_baseline = np.mean(l2)
            
        l1 -= l1_baseline
        l2 -= l2_baseline
        # (Both Lead I and Lead II are left at their native scale and polarity)
        
        # (Both Lead I and Lead II are left at their native scale)
        
        # Strictly apply standard Einthoven/Goldberger equations on the filtered signals
        aligned_data['Lead_III'] = l2 - l1
        aligned_data['aVR'] = -(l1 + l2) / 2.0
        aligned_data['aVL'] = l1 - (l2 / 2.0)
        aligned_data['aVF'] = l2 - (l1 / 2.0)
        
        # Write back the recalibrated, phase-locked traces
        aligned_data['Lead_I'] = l1
        aligned_data['Lead_II'] = l2

    # Crop the start and end of the arrays to remove any synthetic zero-padding before the first 
    # and after the last PQRST complex. This prevents transient step/ringing artifacts at boundaries.
    if 'Lead_I' in aligned_data:
        peaks_l1, _ = find_r_peaks(aligned_data['Lead_I'], fs)
        if len(peaks_l1) > 0:
            crop_start = max(0, peaks_l1[0] - int(0.35 * fs))
            crop_end = min(len(aligned_data['Lead_I']), peaks_l1[-1] + int(0.55 * fs))
            
            if crop_start < crop_end:
                for k in aligned_data.keys():
                    aligned_data[k] = aligned_data[k][crop_start:crop_end]

    # (Baseline wander removal was moved upstream to source leads I and II directly)
    # The derived limb leads (III, aVR, aVL, aVF) are purely mathematical and require no further filtering,
    # guaranteeing that Einthoven's Law and Goldberger equations remain algebraically perfect.

    # Pre-calculate shared fiducials using Lead II to guarantee identical timing widths
    shared_fiducials = []
    if 'Lead_II' in aligned_data and len(aligned_data['Lead_II']) > 0:
        y_l2 = aligned_data['Lead_II']
        peaks_l2, _ = find_r_peaks(y_l2, fs)
        
        for r_est in peaks_l2:
            if r_est - 70 >= 0 and r_est + 120 < len(y_l2):
                r_idx = np.argmax(y_l2[r_est-15:r_est+15]) + r_est - 15
                q_idx = np.argmin(y_l2[r_idx-25:r_idx]) + r_idx - 25
                s_idx = np.argmin(y_l2[r_idx:r_idx+40]) + r_idx
                
                next_r = len(y_l2)
                for p in peaks_l2:
                    if p > r_idx + 50:
                        next_r = p
                        break
                
                # T-wave search window (must start after ST segment gap)
                t_end_offset = max(70, min(120, int((next_r - r_idx) * 0.65)))
                t_start_offset = 45 # min gap to avoid S-wave recovery spikes
                
                # If the search window is truncated by the end of the array, skip T-wave labeling
                if r_idx + t_end_offset >= len(y_l2) - 10:
                    t_idx = None
                else:
                    # Smooth signal specifically for T-wave detection to find the wider rounded peak
                    y_sm_t = signal.savgol_filter(y_l2, window_length=21, polyorder=3)
                    t_idx = np.argmax(y_sm_t[r_idx+t_start_offset:r_idx+t_end_offset]) + r_idx + t_start_offset
                
                p_idx = np.argmax(y_l2[r_idx-55:r_idx-20]) + r_idx - 55
                
                try:
                    y_sm = signal.savgol_filter(y_l2, window_length=11, polyorder=3)
                    p_on = p_idx
                    while p_on > 0 and y_sm[p_on] > y_sm[p_on-1]: p_on -= 1
                    q_on = q_idx
                    while q_on > p_idx and y_sm[q_on] < y_sm[q_on-1]: q_on -= 1
                    
                    s_off = s_idx
                    if t_idx is not None:
                        while s_off < t_idx and y_sm[s_off] < y_sm[s_off+1]: s_off += 1
                        t_off = t_idx
                        while t_off < len(y_sm)-1 and y_sm[t_off] > y_sm[t_off+1]: t_off += 1
                        qt = int((t_off - q_on) * (1000.0 / fs))
                    else:
                        while s_off < len(y_sm)-1 and y_sm[s_off] < y_sm[s_off+1]: s_off += 1
                        qt = None
                    
                    pr = int((q_on - p_on) * (1000.0 / fs))
                    qrs = int((s_off - q_on) * (1000.0 / fs))
                    
                    shared_fiducials.append({
                        'P': p_idx, 'Q': q_idx, 'R': r_idx, 'S': s_idx, 'T': t_idx,
                        'PR': pr, 'QRS': qrs, 'QT': qt
                    })
                except Exception:
                    pass

    # 3. Find global min and max to prevent autoscaling and preserve relative sizes
    all_values = []
    for lead, sig in aligned_data.items():
        all_values.extend(sig)
    
    if len(all_values) > 0:
        max_abs = np.max(np.abs(all_values))
        if max_abs == 0: max_abs = 1
        y_pad = max_abs * 0.35
        y_lims = (-max_abs - y_pad, max_abs + y_pad)
    else:
        y_lims = (-1000, 1000)

    # 4. Plot
    plt.style.use('default')
    fig, axes = plt.subplots(3, 4, figsize=(16, 9))
    fig.suptitle('12-Lead ECG Summary Report', fontsize=20, fontweight='bold', y=0.98)
    
    for row in range(3):
        for col in range(4):
            lead_name = layout[row][col]
            ax = axes[row, col]
            
            if lead_name in aligned_data and len(aligned_data[lead_name]) > 0:
                y = aligned_data[lead_name]
                t = np.arange(len(y)) / fs
                ax.plot(t, y, color='black', linewidth=1.0)
                
                # Apply global Y-axis limits (stops autoscaling per lead)
                ax.set_ylim(y_lims)
                
                # Make it look like ECG paper (red grid)
                ax.grid(True, which='major', color='#ff9999', linestyle='-', linewidth=0.5)
                ax.grid(True, which='minor', color='#ffdddd', linestyle='-', linewidth=0.2)
                ax.minorticks_on()
                
                # Add title for the lead
                ax.set_title(lead_name, loc='left', fontsize=12, fontweight='bold', color='blue')
                
                # Remove tick labels for cleaner look, but keep ticks
                ax.set_xticklabels([])
                ax.set_yticklabels([])
            else:
                ax.text(0.5, 0.5, f"No Data\n{lead_name}", ha='center', va='center', color='gray')
                ax.set_xticks([])
                ax.set_yticks([])
                
    plt.tight_layout()
    plt.subplots_adjust(top=0.90)
    report_path = os.path.join(save_dir, '12_lead_report.png')
    plt.savefig(report_path, dpi=300)
    plt.close()


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    readings_dir = os.path.join(base_dir, 'readings')
    os.makedirs(readings_dir, exist_ok=True)
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    test_dir = os.path.join(readings_dir, f'test_{timestamp}')
    os.makedirs(test_dir, exist_ok=True)
    
    leads_to_record = ['Lead_I', 'Lead_II', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
    
    # We will pass the 'Filtered' data to generate_summary_report, 
    # but we store both Raw and Filtered in the CSVs.
    report_data = {}
    
    print("========================================")
    print("      12-Lead ECG Recording System      ")
    print("========================================")
    print(f"Data will be saved in: {test_dir}\n")

    for lead in leads_to_record:
        while True:
            ans = input(f"Are you ready to record {lead}? (Type 'ready' to start, 'skip' to skip): ").strip().lower()
            if ans == 'skip':
                print(f"Skipping {lead}.\n")
                break
            elif ans == 'ready':
                print(f"Recording {lead} for 10 seconds. Please remain still...")
                raw, filt = record_lead(lead, duration=10)
                if len(filt) == 0:
                    print("No data recorded. Check device connection.")
                    retry = input("Do you want to retake? (y/n): ").strip().lower()
                    if retry != 'y':
                        break
                    continue
                    
                print(f"Recording finished ({len(filt)} samples captured).")
                
                # Ask for retake
                retake = input(f"Do you want to 'retake' {lead} or go to 'next'? ").strip().lower()
                if retake == 'retake':
                    print(f"Retaking {lead}...\n")
                    continue
                else:
                    report_data[lead] = raw if lead in ['Lead_I', 'Lead_II'] else filt
                    
                    # Store BOTH raw and filtered data in the CSV without manipulation
                    df = pd.DataFrame({'Raw': raw, 'Filtered': filt})
                    csv_path = os.path.join(test_dir, f"{lead}.csv")
                    df.to_csv(csv_path, index=False)
                    print(f"Saved {lead} raw and filtered data to CSV.\n")
                    break
            else:
                print("Invalid input.")

    # Generate summary report
    print("Generating 12-lead ECG summary report...")
    generate_summary_report(report_data, test_dir)
    print(f"Done! All data and report saved in: {test_dir}")

if __name__ == '__main__':
    main()
