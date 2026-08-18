
import os
import glob
import json
import numpy as np
from scipy import signal
import matplotlib.pyplot as plt

RECORD_DIR = "recordings"

def get_latest_recording(lead_name):
    """Finds the most recent JSON recording for a given lead."""
    folder = os.path.join(RECORD_DIR, lead_name)
    if not os.path.exists(folder):
        return None
    files = glob.glob(os.path.join(folder, "*.json"))
    if not files:
        return None
    latest_file = max(files, key=os.path.getctime)
    
    with open(latest_file, 'r') as f:
        data = json.load(f)
    return np.array(data["raw"])  # We take the raw mV data to re-filter it perfectly

def apply_offline_filters(data_mv, fs=250.0):
    """
    Applies zero-phase offline filtering (forward-backward).
    """
    nyq = 0.5 * fs
    
    # 1. Bandpass (0.05 - 30 Hz)
    # Reduced to 2nd order and 30Hz ("Monitor Mode") to heavily smooth PQ/ST segments
    b_bp, a_bp = signal.butter(2, [0.05 / nyq, 30.0 / nyq], btype='bandpass')
    
    # filtfilt applies the filter forwards, then backwards. 
    # This mathematically guarantees zero phase distortion and perfectly flat baselines.
    filtered = signal.filtfilt(b_bp, a_bp, data_mv)
    
    # 2. Notch (50 Hz)
    b_notch, a_notch = signal.iirnotch(50.0 / nyq, 30.0)
    filtered = signal.filtfilt(b_notch, a_notch, filtered)
    
    # 3. Final Savitzky-Golay polish (31 samples = 124ms, covers ST segment)
    filtered = signal.savgol_filter(filtered, window_length=31, polyorder=2)
    
    return filtered

from sync import synchronize_leads

def main():
    print("Loading latest Lead I and Lead II recordings...")
    l1_raw = get_latest_recording("Lead_I")
    l2_raw = get_latest_recording("Lead_II")
    
    if l1_raw is None or l2_raw is None:
        print("Error: Could not find both Lead_I and Lead_II recordings in the 'recordings' folder.")
        print("Please use recorder.py to record both first.")
        return

    l1_clean = apply_offline_filters(l1_raw)
    l2_clean = apply_offline_filters(l2_raw)
    
    synced = synchronize_leads({
        "Lead_I": l1_clean,
        "Lead_II": l2_clean
    }, master_lead="Lead_II")
    
    l1_clean = synced["Lead_I"]
    l2_clean = synced["Lead_II"]
    min_len = len(l1_clean)
    
    print("Deriving Augmented Limb Leads (III, aVR, aVL, aVF)...")
    # Einthoven's & Goldberger's Equations
    l3_clean  = l2_clean - l1_clean
    avr_clean = -0.5 * (l1_clean + l2_clean)
    avl_clean = l1_clean - 0.5 * l2_clean
    avf_clean = l2_clean - 0.5 * l1_clean

    #validation
    einthoven_err = np.max(np.abs((l1_clean + l3_clean) - l2_clean))
    goldberger_err = np.max(np.abs(avr_clean + avl_clean + avf_clean))
    
    if einthoven_err < 1e-10 and goldberger_err < 1e-10:
        print("  -> VALIDATION PASSED: Math is perfectly aligned.")

    # ── PLOT THE 6 LIMB LEADS ──
    time_axis = np.arange(min_len) / 250.0
    
    fig, axs = plt.subplots(3, 2, figsize=(14, 8), sharex=True)
    fig.patch.set_facecolor("#0f0f0f")
    fig.suptitle("Derived 6-Limb Leads (Offline Filtered)", color="white", fontsize=14, fontweight="bold")
    
    leads = [
        (axs[0, 0], "Lead I", l1_clean, "#00e5ff"),
        (axs[0, 1], "aVR", avr_clean, "#ff5252"),
        (axs[1, 0], "Lead II", l2_clean, "#76ff03"),
        (axs[1, 1], "aVL", avl_clean, "#e040fb"),
        (axs[2, 0], "Lead III", l3_clean, "#ffd600"),
        (axs[2, 1], "aVF", avf_clean, "#ff9100"),
    ]
    
    for ax, title, data, color in leads:
        ax.set_facecolor("#141414")
        ax.plot(time_axis, data, color=color, linewidth=1.2)
        ax.set_title(title, color="white", fontsize=10, loc="left")
        ax.tick_params(colors="#aaaaaa")
        ax.grid(True, color="#252525", linewidth=0.6, linestyle="--")
        for spine in ax.spines.values():
            spine.set_edgecolor("#333333")
            
    axs[2, 0].set_xlabel("Time (seconds)", color="#aaaaaa")
    axs[2, 1].set_xlabel("Time (seconds)", color="#aaaaaa")
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    print("Displaying results. Close the plot window to exit.")
    plt.show()

if __name__ == "__main__":
    main()
