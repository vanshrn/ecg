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
    avl = round(l1 - 0.5 * l2, 4)      if not hasattr(l1, '__len__') else (l1 - 0.5 * l2).round(4)
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
        "Lead_II": l2_base_removed
    }, fs=FS, master_lead="Lead_II")
    
    l1_aligned = synced_dict["Lead_I"]
    l2_aligned = synced_dict["Lead_II"]
    
    l3_aligned, avr_aligned, avl_aligned, avf_aligned = derive_leads(l1_aligned, l2_aligned)

    leads = {
        "Lead I":   final_noise_filter(l1_aligned),
        "Lead II":  final_noise_filter(l2_aligned),
        "Lead III": final_noise_filter(l3_aligned),
        "aVR":      final_noise_filter(avr_aligned),
        "aVL":      final_noise_filter(avl_aligned),
        "aVF":      final_noise_filter(avf_aligned)
    }

    einthoven_err = np.max(np.abs((leads["Lead I"] + leads["Lead III"]) - leads["Lead II"]))
    goldberger_err = np.max(np.abs(leads["aVR"] + leads["aVL"] + leads["aVF"]))
    print(f"  -> Einthoven's Law Error (L1+L3=L2): {einthoven_err:.2e}")
    print(f"  -> Goldberger Identity Error (aVR+aVL+aVF=0): {goldberger_err:.2e}")
    if einthoven_err < 1e-10 and goldberger_err < 1e-10:
        print("  -> VALIDATION PASSED: Math is perfectly aligned.")

    time_axis = np.arange(len(l1_aligned)) / FS
    
    # Enable interactive matplotlib toolbar and tight layout
    fig, axs = plt.subplots(3, 2, figsize=(14, 8), sharex=True)
    fig.patch.set_facecolor("#f4f4f9") # Light clinical background
    fig.canvas.manager.set_window_title('Dynamic ECG Report')
    fig.suptitle("Clinical 6-Lead ECG Report (Derived & Denoised)", color="#1a1a1a", fontsize=16, fontweight="bold")

    plot_mapping = [
        (axs[0, 0], "Lead I", leads["Lead I"]),
        (axs[0, 1], "aVR", leads["aVR"]),
        (axs[1, 0], "Lead II", leads["Lead II"]),
        (axs[1, 1], "aVL", leads["aVL"]),
        (axs[2, 0], "Lead III", leads["Lead III"]),
        (axs[2, 1], "aVF", leads["aVF"]),
    ]

    for ax, title, data in plot_mapping:
        ax.set_facecolor("#ffffff")
        # Standard clinical ECG pink/red grid style
        ax.grid(True, color="#ffcdd2", linewidth=0.8, linestyle="-", which='major')
        ax.grid(True, color="#ffebee", linewidth=0.4, linestyle="-", which='minor')
        ax.minorticks_on()
        
        ax.plot(time_axis, data, color="#212121", linewidth=1.0)
        ax.set_title(title, color="#b71c1c", fontsize=11, fontweight="bold", loc="left")
        
        # Clinical limits (standard is roughly +/- 1.5 mV for limb leads)
        max_amp = np.max(np.abs(data))
        limit = max(1.0, max_amp * 1.2)
        ax.set_ylim(-limit, limit)
        ax.set_ylabel("mV", fontsize=9)

    axs[2, 0].set_xlabel("Time (seconds)", fontsize=10)
    axs[2, 1].set_xlabel("Time (seconds)", fontsize=10)
    
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    
    plt.show()

if __name__ == "__main__":
    main()
