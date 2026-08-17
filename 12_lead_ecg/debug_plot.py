import os
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal

folder = r"D:\code playground\PlatformIO\Projects\ecg_monitor\12_lead_ecg\readings\test_20260817_143519"
l1 = np.loadtxt(os.path.join(folder, "Lead_I.csv"), delimiter=",")
l2 = np.loadtxt(os.path.join(folder, "Lead_II.csv"), delimiter=",")

def find_r_peaks(data, fs=250):
    b, a = signal.butter(2, [5 / (fs/2), 15 / (fs/2)], btype='bandpass')
    bp = signal.filtfilt(b, a, data)
    diff = np.diff(bp)
    sq = diff ** 2
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

plt.figure(figsize=(10, 8))
plt.subplot(2, 1, 1)
plt.plot(c1[:1000])
plt.plot([p for p in p1 if p < 1000], [c1[p] for p in p1 if p < 1000], 'ro')
plt.title("Lead I with Pan-Tompkins Peaks")

plt.subplot(2, 1, 2)
plt.plot(c2[:1000])
plt.plot([p for p in p2 if p < 1000], [c2[p] for p in p2 if p < 1000], 'ro')
plt.title("Lead II with Pan-Tompkins Peaks")

plt.tight_layout()
plt.savefig(os.path.join(folder, "debug_report2.png"))
