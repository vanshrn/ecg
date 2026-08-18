import pandas as pd
import matplotlib.pyplot as plt
from scipy import signal
import os
import sys
import numpy as np

# Add the directory containing main.py to sys.path so we can import it
sys.path.append(r"D:\code playground\PlatformIO\Projects\ecg_monitor\12_lead_ecg")
from main import apply_ecg_filters

def main():
    target_dir = r"D:\code playground\PlatformIO\Projects\ecg_monitor\12_lead_ecg\readings\test_20260818_132154"
    l1_path = os.path.join(target_dir, "Lead_I.csv")
    
    df = pd.read_csv(l1_path)
    # We will plot the Raw column after passing it through apply_ecg_filters
    # to show the original unsynced recording in high quality.
    l1_raw = df['Raw'].values
    l1_filt = apply_ecg_filters(l1_raw, fs=250)
    
    # Detrend
    l1_filt = signal.detrend(l1_filt, type='linear')
    # (Polarity left intact)
        
    t = [i / 250.0 for i in range(len(l1_filt))]
    
    plt.figure(figsize=(12, 4))
    plt.plot(t, l1_filt, color='blue', linewidth=1.5)
    plt.title("Original Unsynced Lead I (Raw Recording from Sensor)")
    plt.xlabel("Time (seconds)")
    plt.ylabel("Amplitude")
    plt.grid(True, which='both', linestyle='--', alpha=0.6)
    
    out_path = os.path.join(target_dir, "Lead_I_original.png")
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    print(f"Saved original Lead I plot to: {out_path}")

if __name__ == "__main__":
    main()
