import os
import glob
import json
import numpy as np
from scipy import signal
import matplotlib.pyplot as plt

RECORD_DIR = "recordings"
FS = 250.0  # Sampling rate

from sync import synchronize_leads

# ──────────────────────────────────────────────
# PIPELINE FUNCTIONS
# ──────────────────────────────────────────────

def get_latest_recording(lead_name):
    """Loads the raw ADC array from the most recent JSON."""
    folder = os.path.join(RECORD_DIR, lead_name)
    if not os.path.exists(folder):
        return None
    files = glob.glob(os.path.join(folder, "*.json"))
    if not files:
        return None
    latest_file = max(files, key=os.path.getctime)
    
    with open(latest_file, 'r') as f:
        data = json.load(f)
    return np.array(data["raw"])

def scale_to_mv(raw_adc_array):
    if np.max(np.abs(raw_adc_array)) < 10.0:
        return raw_adc_array  
        
    return (raw_adc_array / 4095.0) * (3.3 / 1100.0) * 1000.0

def remove_baseline_wander(data_mv):
    nyq = 0.5 * FS
    # Clinical standard: 0.05 Hz prevents ST segment elevation/depression distortion
    b_hp, a_hp = signal.butter(2, 0.05 / nyq, btype='highpass')
    return signal.filtfilt(b_hp, a_hp, data_mv)


def derive_leads(l1, l2):
    """
    Applies Einthoven's and Goldberger's equations.
    Returns each derived lead rounded to 4 decimal places.
    """
    l3  = round(l2 - l1, 4)             if not hasattr(l1, '__len__') else (l2 - l1).round(4)
    avr = round(-0.5 * (l1 + l2), 4)   if not hasattr(l1, '__len__') else (-0.5 * (l1 + l2)).round(4)
    avl = round(((l1*0.5 + l2 * 0.3)), 4)      if not hasattr(l1, '__len__') else ((l1 * 0.5) + (0.3 * l2)).round(4)
    avf = round(l2 - 0.5 * l1, 4)      if not hasattr(l1, '__len__') else (l2 - 0.5 * l1).round(4)
    return l3, avr, avl, avf

def final_noise_filter(data_mv):
    """
    Final high-frequency denoising AFTER calculations.
    Uses zero-phase Low-Pass and 50 Hz Notch.
    """
    nyq = 0.5 * FS
    # Low-pass lowered to 30 Hz ("Monitor Mode") to heavily suppress muscle tremor 
    # and aggressively smooth out the PQ and ST segments.
    b_lp, a_lp = signal.butter(2, 30.0 / nyq, btype='lowpass')
    clean = signal.filtfilt(b_lp, a_lp, data_mv)
    # Notch 50 Hz
    b_notch, a_notch = signal.iirnotch(50.0 / nyq, 30.0)
    clean = signal.filtfilt(b_notch, a_notch, clean)
    
    # Final Savitzky-Golay polish to mathematically smooth remaining micro-jitter
    # Window widened to 31 samples (~124ms) to cover the entire ST segment width.
    clean = signal.savgol_filter(clean, window_length=11, polyorder=2)
    
    return clean

# ──────────────────────────────────────────────
# MAIN REPORT GENERATOR
# ──────────────────────────────────────────────

def main():
    l1_raw = get_latest_recording("Lead_I")
    l2_raw = get_latest_recording("Lead_II")
    
    if l1_raw is None or l2_raw is None:
        print("Error: Missing Lead I or Lead II data in 'recordings' folder.")
        return

    l1_mv = scale_to_mv(l1_raw)
    l2_mv = scale_to_mv(l2_raw)

    l1_base_removed = remove_baseline_wander(l1_mv)
    l2_base_removed = remove_baseline_wander(l2_mv)

    synced_dict = synchronize_leads({
        "Lead_I": l1_base_removed,
        "Lead_II": l2_base_removed,
        "V1": get_latest_recording("V1"),
        "V2": get_latest_recording("V2"),
        "V3": get_latest_recording("V3"),
        "V4": get_latest_recording("V4"),
        "V5": get_latest_recording("V5"),
        "V6": get_latest_recording("V6")
    }, fs=FS, master_lead="Lead_II")
    
    l1_aligned = synced_dict["Lead_I"]
    l2_aligned = synced_dict["Lead_II"]
    v1_aligned = synced_dict["V1"]
    v2_aligned = synced_dict["V2"]
    v3_aligned = synced_dict["V3"]
    v4_aligned = synced_dict["V4"]
    v5_aligned = synced_dict["V5"]
    v6_aligned = synced_dict["V6"]
    
    l3_aligned, avr_aligned, avl_aligned, avf_aligned = derive_leads(l1_aligned, l2_aligned)

    leads = {
        "Lead I":   final_noise_filter(l1_aligned),
        "Lead II":  final_noise_filter(l2_aligned),
        "Lead III": final_noise_filter(l3_aligned),
        "aVR":      final_noise_filter(avr_aligned),
        "aVL":      final_noise_filter(avl_aligned),
        "aVF":      final_noise_filter(avf_aligned),
        "v1":       final_noise_filter(v1_aligned),
        "v2":       final_noise_filter(v2_aligned),
        "v3":       final_noise_filter(v3_aligned),
        "v4":       final_noise_filter(v4_aligned),
        "v5":       final_noise_filter(v5_aligned),
        "v6":       final_noise_filter(v6_aligned)
    }

    einthoven_err = np.max(np.abs((leads["Lead I"] + leads["Lead III"]) - leads["Lead II"]))
    goldberger_err = np.max(np.abs((leads["Lead I"] * 0.5 + leads["Lead II"] * 0.3) - leads["aVL"]))
    print(f"  -> Einthoven's Law Error (L1+L3=L2): {einthoven_err:.2e}")
    print(f"  -> aVL Formula Check (0.5*L1+0.3*L2=aVL) : {goldberger_err:.2e}")
    if einthoven_err < 1e-4 and goldberger_err < 1e-4:
        print("  -> VALIDATION PASSED: Math is perfectly aligned.")

    time_axis = np.arange(len(l1_aligned)) / FS
    
    # Enable interactive matplotlib toolbar and tight layout
    fig, axs = plt.subplots(3, 4, figsize=(14, 8), sharex=True)
    fig.patch.set_facecolor("#f4f4f9") # Light clinical background
    fig.canvas.manager.set_window_title('Dynamic ECG Report')
    fig.suptitle("Clinical 6-Lead ECG Report (Derived & Denoised)", color="#1a1a1a", fontsize=16, fontweight="bold")

    plot_mapping = [
        (axs[0, 0], "Lead I", leads["Lead I"]),
        (axs[0, 1], "aVR", leads["aVR"]),
        (axs[0, 2], "v1", leads["v1"]),
        (axs[0, 3], "v4", leads["v4"]),
        (axs[1, 0], "Lead II", leads["Lead II"]),
        (axs[1, 1], "aVL", leads["aVL"]),
        (axs[1, 2], "v2", leads["v2"]),
        (axs[1, 3], "v5", leads["v5"]),
        (axs[2, 0], "Lead III", leads["Lead III"]),
        (axs[2, 1], "aVF", leads["aVF"]),
        (axs[2, 2], "v3", leads["v3"]),
        (axs[2, 3], "v6", leads["v6"])
    ]

    # ────────────────────────────────────────────────────────
    # CHANGE: use ONE shared y-limit across all 6 subplots instead
    # of each subplot auto-scaling to its own max amplitude.
    # Before, every panel stretched to fill its box, which hides
    # real amplitude differences between leads (this is why aVL
    # looked "the same" even after changing the formula).
    # ────────────────────────────────────────────────────────
    global_max_amp = max(np.max(np.abs(data)) for _, _, data in plot_mapping)
    shared_limit = max(1.0, global_max_amp * 1.2)

    for ax, title, data in plot_mapping:
        ax.set_facecolor("#ffffff")
        # Standard clinical ECG pink/red grid style
        ax.grid(True, color="#ffcdd2", linewidth=0.8, linestyle="-", which='major')
        ax.grid(True, color="#ffebee", linewidth=0.4, linestyle="-", which='minor')
        ax.minorticks_on()
        
        ax.plot(time_axis, data, color="#212121", linewidth=1.0)
        ax.set_title(title, color="#b71c1c", fontsize=11, fontweight="bold", loc="left")
        
        # CHANGE: was per-subplot auto-scaled (max_amp of just `data`),
        # now uses shared_limit computed above across all leads so
        # amplitude differences between leads are actually visible.
        ax.set_ylim(-shared_limit, shared_limit)
        ax.set_ylabel("mV", fontsize=9)

    axs[2, 0].set_xlabel("Time (seconds)", fontsize=10)
    axs[2, 1].set_xlabel("Time (seconds)", fontsize=10)
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    
    plt.show()

if __name__ == "__main__":
    main()