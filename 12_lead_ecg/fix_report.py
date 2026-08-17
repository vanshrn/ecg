import os
import numpy as np
from scipy import signal
from main import generate_summary_report

def fix_and_regenerate(folder_path):
    data = {}
    print(f"Reading from {folder_path}...")
    
    # Load all available leads
    for filename in os.listdir(folder_path):
        if filename.endswith(".csv"):
            lead_name = filename.replace(".csv", "")
            filepath = os.path.join(folder_path, filename)
            try:
                data[lead_name] = np.loadtxt(filepath, delimiter=",")
                print(f"Loaded {lead_name}")
            except Exception as e:
                pass
                
    if 'Lead_I' in data and 'Lead_II' in data:
        # To perfectly fix the report, we focus ONLY on the last 4 seconds (1000 samples)
        # which is what the report plots.
        l1_full = data['Lead_I']
        l2_full = data['Lead_II']
        
        max_samples = 1000
        l1 = l1_full[-max_samples:] if len(l1_full) > max_samples else l1_full
        l2 = l2_full[-max_samples:] if len(l2_full) > max_samples else l2_full
        
        length = min(len(l1), len(l2))
        l1 = l1[:length]
        l2 = l2[:length]
        
        # High pass filter for clean correlation
        b, a = signal.butter(1, 0.5 / (250.0 / 2.0), btype='high')
        l1_clean = signal.filtfilt(b, a, l1)
        l2_clean = signal.filtfilt(b, a, l2)
        
        # Cross-correlate to find the exact best alignment for THESE 4 seconds
        corr = signal.correlate(l2_clean, l1_clean, mode='full')
        lags = signal.correlation_lags(len(l2_clean), len(l1_clean), mode='full')
        
        valid_idx = np.where((lags >= -150) & (lags <= 150))[0]
        if len(valid_idx) > 0:
            best_idx = valid_idx[np.argmax(corr[valid_idx])]
            shift = lags[best_idx]
            
            print(f"Refining alignment specifically for the last 4 seconds with shift: {shift}")
            
            if shift > 0:
                l1_aligned = np.pad(l1, (shift, 0), mode='edge')[:length]
                l2_aligned = l2
            elif shift < 0:
                l2_aligned = np.pad(l2, (-shift, 0), mode='edge')[:length]
                l1_aligned = l1
            else:
                l1_aligned = l1
                l2_aligned = l2
        else:
            l1_aligned = l1
            l2_aligned = l2

        # Re-derive the leads
        l3 = l2_aligned - l1_aligned
        avr = -(l1_aligned + l2_aligned) / 2.0
        avl = l1_aligned - (l2_aligned / 2.0)
        avf = l2_aligned - (l1_aligned / 2.0)
        
        # Update data dictionary
        data['Lead_III'] = l3
        data['aVR'] = avr
        data['aVL'] = avl
        data['aVF'] = avf
        
        # Save them back
        np.savetxt(os.path.join(folder_path, "Lead_III.csv"), l3, delimiter=",", fmt="%.4f")
        np.savetxt(os.path.join(folder_path, "aVR.csv"), avr, delimiter=",", fmt="%.4f")
        np.savetxt(os.path.join(folder_path, "aVL.csv"), avl, delimiter=",", fmt="%.4f")
        np.savetxt(os.path.join(folder_path, "aVF.csv"), avf, delimiter=",", fmt="%.4f")

    if len(data) > 0:
        generate_summary_report(data, folder_path)
        print("Report mathematically aligned and regenerated successfully.")

if __name__ == "__main__":
    target_folder = r"D:\code playground\PlatformIO\Projects\ecg_monitor\12_lead_ecg\readings\test_20260817_124409"
    fix_and_regenerate(target_folder)
