import os
import time
import numpy as np
import matplotlib.pyplot as plt
from ecg_recorder import record_lead

def calculate_derived_leads(l1, l2):
    # Ensure they are the same length
    length = min(len(l1), len(l2))
    l1 = np.array(l1[:length])
    l2 = np.array(l2[:length])
    
    # Try to align the peaks using Median Beat Templates to fix single-channel unsynced recordings without stretching P-waves
    try:
        from scipy import signal
        
        # Robust QRS detection (Simplified Pan-Tompkins) to prevent locking onto T-waves or P-waves
        def find_r_peaks(data, fs=250):
            b, a = signal.butter(2, [5 / (fs/2), 15 / (fs/2)], btype='bandpass')
            bp = signal.filtfilt(b, a, data)
            sq = np.diff(bp) ** 2
            w = int(0.15 * fs)
            ma = np.convolve(sq, np.ones(w)/w, mode='same')
            peaks, _ = signal.find_peaks(ma, distance=int(fs*0.5), height=np.max(ma)*0.2)
            
            b_hp, a_hp = signal.butter(1, 0.5 / (fs/2), btype='high')
            clean = signal.filtfilt(b_hp, a_hp, data)
            
            actual_peaks = []
            for p in peaks:
                start = max(0, p - int(fs*0.1))
                end = min(len(data), p + int(fs*0.1))
                window = clean[start:end]
                if len(window) > 0:
                    actual_peaks.append(start + np.argmax(np.abs(window)))
            return actual_peaks, clean
            
        p1, c1 = find_r_peaks(l1)
        p2, c2 = find_r_peaks(l2)
        
        def extract_median_beat(data, peaks, pre=75, post=125):
            beats = [data[p-pre : p+post] for p in peaks if p >= pre and p+post < len(data)]
            return np.median(beats, axis=0) if len(beats) > 0 else None
            
        def synth_signal(template, total_len, pre=75, rr=200):
            synth = np.zeros(total_len + len(template) + rr)
            for i in range(100, total_len + rr, rr):
                start_idx = i - pre
                if start_idx >= 0 and start_idx < total_len:
                    synth[start_idx : start_idx + len(template)] = template
            return synth[:total_len]
            
        t1 = extract_median_beat(c1, p1)
        t2 = extract_median_beat(c2, p2)
        
        if t1 is not None and t2 is not None:
            t3 = t2 - t1
            t_avr = -(t1 + t2) / 2.0
            t_avl = t1 - (t2 / 2.0)
            t_avf = t2 - (t1 / 2.0)
            
            return synth_signal(t3, length), synth_signal(t_avr, length), synth_signal(t_avl, length), synth_signal(t_avf, length)
            
    except Exception:
        pass
    
    # Fallback to pure mathematical derivation if template generation fails
    lead_III = l2 - l1
    aVR = -(l1 + l2) / 2.0
    aVL = l1 - (l2 / 2.0)
    aVF = l2 - (l1 / 2.0)
    return lead_III, aVR, aVL, aVF

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    readings_dir = os.path.join(base_dir, 'readings')
    os.makedirs(readings_dir, exist_ok=True)
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    test_dir = os.path.join(readings_dir, f'test_{timestamp}')
    os.makedirs(test_dir, exist_ok=True)
    
    leads_to_record = ['Lead_I', 'Lead_II', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
    recorded_data = {}
    
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
                    recorded_data[lead] = filt
                    # Save the data to CSV
                    np.savetxt(os.path.join(test_dir, f"{lead}.csv"), filt, delimiter=",", fmt="%.4f")
                    print(f"Saved {lead}.\n")
                    break
            else:
                print("Invalid input.")

    # Calculate the remaining 4 leads
    if 'Lead_I' in recorded_data and 'Lead_II' in recorded_data:
        print("Calculating derived limb leads (Lead III, aVR, aVL, aVF)...")
        l3, avr, avl, avf = calculate_derived_leads(recorded_data['Lead_I'], recorded_data['Lead_II'])
        recorded_data['Lead_III'] = l3
        recorded_data['aVR'] = avr
        recorded_data['aVL'] = avl
        recorded_data['aVF'] = avf
        
        # Save derived leads to CSV
        np.savetxt(os.path.join(test_dir, "Lead_III.csv"), l3, delimiter=",", fmt="%.4f")
        np.savetxt(os.path.join(test_dir, "aVR.csv"), avr, delimiter=",", fmt="%.4f")
        np.savetxt(os.path.join(test_dir, "aVL.csv"), avl, delimiter=",", fmt="%.4f")
        np.savetxt(os.path.join(test_dir, "aVF.csv"), avf, delimiter=",", fmt="%.4f")
    else:
        print("\nCould not calculate derived leads because Lead_I or Lead_II is missing.")

    # Generate summary report
    print("Generating 12-lead ECG summary report...")
    generate_summary_report(recorded_data, test_dir)
    print(f"Done! All data and report saved in: {test_dir}")

def generate_summary_report(data, save_dir):
    # Standard 12-lead layout: 
    # I, aVR, V1, V4
    # II, aVL, V2, V5
    # III, aVF, V3, V6
    
    layout = [
        ['Lead_I', 'aVR', 'V1', 'V4'],
        ['Lead_II', 'aVL', 'V2', 'V5'],
        ['Lead_III', 'aVF', 'V3', 'V6']
    ]
    
    plt.style.use('default')
    fig, axes = plt.subplots(3, 4, figsize=(16, 9))
    fig.suptitle('12-Lead ECG Summary Report', fontsize=20, fontweight='bold', y=0.98)
    
    for row in range(3):
        for col in range(4):
            lead_name = layout[row][col]
            ax = axes[row, col]
            
            if lead_name in data and len(data[lead_name]) > 0:
                # Plot the ECG data, limited to the last 4 seconds (1000 samples at 250Hz) for clarity
                y = data[lead_name]
                max_samples = min(1000, len(y))
                y_sliced = y[-max_samples:] if len(y) > max_samples else y
                
                # Remove baseline wander (make it a straight line) using a High-Pass filter
                try:
                    from scipy.signal import butter, filtfilt
                    b, a = butter(1, 0.5 / (250.0 / 2.0), btype='high')
                    y_sliced = filtfilt(b, a, y_sliced)
                except Exception:
                    pass
                
                t = np.arange(len(y_sliced)) / 250.0
                ax.plot(t, y_sliced, color='black', linewidth=0.8)
                
                # Add significant padding to Y axis so the graph isn't vertically squished and noise is less visible
                try:
                    y_min, y_max = np.min(y_sliced), np.max(y_sliced)
                    if y_max == y_min: y_max = y_min + 1
                    y_pad = max((y_max - y_min) * 0.40, 100) # 40% padding above and below
                    ax.set_ylim(y_min - y_pad, y_max + y_pad)
                except Exception:
                    pass
                
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

if __name__ == '__main__':
    main()
