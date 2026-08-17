import os
import numpy as np
from scipy import signal
from scipy.interpolate import interp1d
from main import generate_summary_report

def fix_and_regenerate_dtw(folder_path):
    data = {}
    print(f"Reading from {folder_path}...")
    
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
        l1 = data['Lead_I']
        l2 = data['Lead_II']
        
        # High pass filter for clean peak detection
        b, a = signal.butter(1, 0.5 / (250.0 / 2.0), btype='high')
        l1_clean = signal.filtfilt(b, a, l1)
        l2_clean = signal.filtfilt(b, a, l2)
        
        # Find R-peaks
        distance = int(250 * 0.5) # Max 120 BPM
        peaks1, _ = signal.find_peaks(l1_clean, distance=distance, height=np.max(l1_clean)*0.3)
        peaks2, _ = signal.find_peaks(l2_clean, distance=distance, height=np.max(l2_clean)*0.3)
        
        if len(peaks1) >= 2 and len(peaks2) >= 2:
            print(f"Found {len(peaks1)} peaks in Lead I and {len(peaks2)} peaks in Lead II. Applying Beat-by-Beat Time Warping...")
            min_peaks = min(len(peaks1), len(peaks2))
            p1 = peaks1[:min_peaks]
            p2 = peaks2[:min_peaks]
            
            # Create a time-mapping function that maps Lead II's timeline to Lead I's timeline
            time_map = interp1d(p2, p1, kind='linear', fill_value="extrapolate")
            
            # Generate the new indices for Lead I based on Lead II's timeline
            l2_indices = np.arange(len(l2))
            l1_mapped_indices = time_map(l2_indices)
            
            # Interpolate Lead I's amplitude values at these new stretched/compressed time indices
            l1_interpolator = interp1d(np.arange(len(l1)), l1, kind='linear', bounds_error=False, fill_value=0)
            l1_aligned = l1_interpolator(l1_mapped_indices)
            l2_aligned = l2
        else:
            print("Not enough peaks found for DTW alignment. Falling back to normal.")
            length = min(len(l1), len(l2))
            l1_aligned = l1[:length]
            l2_aligned = l2[:length]

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
        print("Report beat-by-beat warped and regenerated successfully.")

if __name__ == "__main__":
    target_folder = r"D:\code playground\PlatformIO\Projects\ecg_monitor\12_lead_ecg\readings\test_20260817_143519"
    fix_and_regenerate_dtw(target_folder)
