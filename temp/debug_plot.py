import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal

def remove_baseline_wander(data, fs=250):
    import scipy.ndimage
    baseline_rough = scipy.ndimage.median_filter(data, size=int(0.2 * fs))
    baseline_smooth = scipy.ndimage.median_filter(baseline_rough, size=int(0.6 * fs))
    return signal.detrend(data - baseline_smooth)

def main():
    l1 = pd.read_csv(r"D:\code playground\PlatformIO\Projects\ecg_monitor\12_lead_ecg\readings\test_20260817_191400\Lead_I.csv")['Filtered'].values
    l2 = pd.read_csv(r"D:\code playground\PlatformIO\Projects\ecg_monitor\12_lead_ecg\readings\test_20260817_191400\Lead_II.csv")['Filtered'].values
    
    l1_clean = remove_baseline_wander(l1)
    l2_clean = remove_baseline_wander(l2)
    
    plt.figure()
    plt.plot(l1_clean, label="Lead I")
    plt.plot(l2_clean, label="Lead II")
    plt.legend()
    plt.savefig(r"D:\code playground\PlatformIO\Projects\ecg_monitor\12_lead_ecg\readings\test_20260817_191400\debug_plot.png")

if __name__ == "__main__":
    main()
