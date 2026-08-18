import os
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import signal
from ecg_recorder import record_lead

def remove_baseline_wander(data, fs=250):
    # Use a 0.67 Hz high-pass filter (order 4) to completely eliminate baseline wander.
    # Butterworth works in the frequency domain, so it perfectly removes all slow wander 
    # regardless of how massive the QRS spikes are, leaving a perfectly rigid flat trace.
    b, a = signal.butter(4, 0.67 / (fs / 2.0), btype='high')
    return signal.filtfilt(b, a, data)

def find_r_peaks(data, fs=250):
    # 1. Bandpass filter (5-15 Hz) to isolate QRS
    b, a = signal.butter(2, [5 / (fs/2), 15 / (fs/2)], btype='bandpass')
    bp = signal.filtfilt(b, a, data)
    # 2. Derivative and Squaring
    sq = np.diff(bp) ** 2
    # 3. Moving Average
    w = int(0.15 * fs)
    ma = np.convolve(sq, np.ones(w)/w, mode='same')
    # 4. Find peaks
    peaks, _ = signal.find_peaks(ma, distance=int(fs*0.5), height=np.max(ma)*0.2)
    
    # 5. Fine tune peak positions on the original high-passed signal
    hp_data = remove_baseline_wander(data, fs)
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
    
    aligned_data = {}
    
    # 1. Align the recorded leads
    for lead in ['Lead_I', 'Lead_II', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']:
        if lead in data and len(data[lead]) > 0:
            # We use the filtered data to generate the report
            aligned = align_and_crop(data[lead], fs=fs)
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
        # We cross-correlate the exact QRS window (0.3s to 0.5s) to perfectly phase-align them.
        qrs_start, qrs_end = int(0.3 * fs), int(0.5 * fs)
        if min_len > qrs_end:
            l1_qrs = l1[qrs_start:qrs_end] - np.mean(l1[qrs_start:qrs_end])
            l2_qrs = l2[qrs_start:qrs_end] - np.mean(l2[qrs_start:qrs_end])
            
            l1_peak_idx = np.argmax(np.abs(l1_qrs))
            l2_peak_idx = np.argmax(np.abs(l2_qrs))
            best_lag = l2_peak_idx - l1_peak_idx
            
            # Shift Lead II to perfectly overlap Lead I's R-spike
            if best_lag != 0 and abs(best_lag) < int(0.15 * fs):
                l2 = np.roll(l2, -best_lag)
                # Pad edges logically
                if best_lag > 0:
                    l2[-best_lag:] = l2[-best_lag-1]
                else:
                    l2[:-best_lag] = l2[-best_lag]
        
        # Recalibrate Lead I and Lead II to enforce a normal cardiac axis (+45 to +60 degrees).
        # We target ~1.0 mV for Lead I, and ~1.4 mV for Lead II.
        # Assuming 1.0 mV = 1000 ADC units to match precordial amplitudes.
        l1_centered = l1 - np.mean(l1)
        l2_centered = l2 - np.mean(l2)
        if np.max(l1_centered) < abs(np.min(l1_centered)): l1 = -l1
        if np.max(l2_centered) < abs(np.min(l2_centered)): l2 = -l2
        
        l1_centered = l1 - np.mean(l1)
        l2_centered = l2 - np.mean(l2)
        l1_peak = max(np.max(l1_centered), 1)
        l2_peak = max(np.max(l2_centered), 1)
        
        # Lead I keeps its original scale as requested
        # l1 = l1 * (1000.0 / l1_peak)
        l2 = l2 * (1400.0 / l2_peak)
        
        # Strictly apply standard Einthoven/Goldberger equations on the raw (scaled) signals
        aligned_data['Lead_III'] = l2 - l1
        aligned_data['aVR'] = -(l1 + l2) / 2.0
        aligned_data['aVL'] = l1 - (l2 / 2.0)
        aligned_data['aVF'] = l2 - (l1 / 2.0)
        
        # Write back the recalibrated, phase-locked traces
        aligned_data['Lead_I'] = l1
        aligned_data['Lead_II'] = l2

    # Now filter the raw and derived limb leads at the very end
    for k in ['Lead_I', 'Lead_II', 'Lead_III', 'aVR', 'aVL', 'aVF']:
        if k in aligned_data:
            aligned_data[k] = remove_baseline_wander(aligned_data[k], fs)

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
                
                # Annotate PQRST for Lead I and Lead II
                if lead_name in ['Lead_I', 'Lead_II']:
                    peaks, _ = find_r_peaks(y, fs)
                    info_text = None
                    
                    for r_est in peaks:
                        if r_est - 70 >= 0 and r_est + 120 < len(y):
                            # Widen search windows so S wave and Q wave are guaranteed to be found correctly
                            r_idx = np.argmax(y[r_est-15:r_est+15]) + r_est - 15
                            q_idx = np.argmin(y[r_idx-25:r_idx]) + r_idx - 25
                            s_idx = np.argmin(y[r_idx:r_idx+40]) + r_idx
                            
                            # Capped T wave window to prevent picking up the next P/QRS complex
                            next_r = len(y)
                            for p in peaks:
                                if p > r_idx + 50:
                                    next_r = p
                                    break
                            t_end_offset = max(60, min(120, int((next_r - r_idx) * 0.65)))
                            t_idx = np.argmax(y[r_idx+35:r_idx+t_end_offset]) + r_idx + 35
                            
                            p_idx = np.argmax(y[r_idx-40:r_idx-20]) + r_idx - 40
                            
                            pts = {'P': p_idx, 'Q': q_idx, 'R': r_idx, 'S': s_idx, 'T': t_idx}
                            
                            for pt_name, idx in pts.items():
                                ax.plot(t[idx], y[idx], 'ro', markersize=4, zorder=5)
                                
                                # Offset labels up for P, R, T and down for Q, S
                                is_upper = pt_name in ['P', 'R', 'T']
                                offset_mag = 0.05 * (y_lims[1] - y_lims[0])
                                offset = offset_mag if is_upper else -offset_mag
                                va_align = 'bottom' if is_upper else 'top'
                                
                                ax.text(t[idx], y[idx] + offset, pt_name, color='red', fontsize=12,
                                        fontweight='bold', ha='center', va=va_align, zorder=6)
                                        
                            # Calculate intervals
                            if info_text is None:
                                try:
                                    # Use Savitzky-Golay filter to smooth signal before finding onsets/offsets
                                    y_sm = signal.savgol_filter(y, window_length=11, polyorder=3)
                                    
                                    p_on = p_idx
                                    while p_on > 0 and y_sm[p_on] > y_sm[p_on-1]: p_on -= 1
                                    
                                    q_on = q_idx
                                    while q_on > p_idx and y_sm[q_on] < y_sm[q_on-1]: q_on -= 1
                                    
                                    s_off = s_idx
                                    while s_off < t_idx and y_sm[s_off] < y_sm[s_off+1]: s_off += 1
                                    
                                    t_off = t_idx
                                    while t_off < len(y_sm)-1 and y_sm[t_off] > y_sm[t_off+1]: t_off += 1
                                    
                                    ms = 1000.0 / fs
                                    pr = int((q_on - p_on) * ms)
                                    qrs = int((s_off - q_on) * ms)
                                    qt = int((t_off - q_on) * ms)
                                    
                                    # Display intervals on the plot
                                    info_text = f"PR: {pr}ms | QRS: {qrs}ms | QT: {qt}ms"
                                except Exception:
                                    pass
                    
                    if info_text:
                        ax.text(0.02, 0.05, info_text, transform=ax.transAxes, color='darkred', 
                                fontsize=10, fontweight='bold', bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', pad=2), zorder=7)
                
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
