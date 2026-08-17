import os
import numpy as np
from scipy import signal
from main import generate_summary_report

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

def extract_median_beat(data, peaks, pre_samples=75, post_samples=125):
    beats = []
    for p in peaks:
        if p >= pre_samples and p + post_samples < len(data):
            beats.append(data[p - pre_samples : p + post_samples])
    if len(beats) > 0:
        return np.median(beats, axis=0)
    return None

def synthesize_signal(template, total_samples=1000, rr_interval=200):
    synth = np.zeros(total_samples + len(template) + rr_interval)
    pre_samples = 75
    
    for i in range(100, total_samples + rr_interval, rr_interval):
        start_idx = i - pre_samples
        if start_idx >= 0 and start_idx < total_samples:
            synth[start_idx : start_idx + len(template)] = template
    return synth[:total_samples]

def fix_and_regenerate_templates(folder_path):
    data = {}
    for filename in os.listdir(folder_path):
        if filename.endswith(".csv"):
            lead_name = filename.replace(".csv", "")
            filepath = os.path.join(folder_path, filename)
            try:
                data[lead_name] = np.loadtxt(filepath, delimiter=",")
            except Exception:
                pass
                
    if 'Lead_I' in data and 'Lead_II' in data:
        l1 = data['Lead_I']
        l2 = data['Lead_II']
        
        p1, c1 = find_r_peaks(l1)
        p2, c2 = find_r_peaks(l2)
        
        t1 = extract_median_beat(c1, p1, pre_samples=75, post_samples=125)
        t2 = extract_median_beat(c2, p2, pre_samples=75, post_samples=125)
        
        if t1 is not None and t2 is not None:
            t3 = t2 - t1
            t_avr = -(t1 + t2) / 2.0
            t_avl = t1 - (t2 / 2.0)
            t_avf = t2 - (t1 / 2.0)
            
            l3_synth = synthesize_signal(t3)
            avr_synth = synthesize_signal(t_avr)
            avl_synth = synthesize_signal(t_avl)
            avf_synth = synthesize_signal(t_avf)
            
            data['Lead_III'] = l3_synth
            data['aVR'] = avr_synth
            data['aVL'] = avl_synth
            data['aVF'] = avf_synth
            
            np.savetxt(os.path.join(folder_path, "Lead_III.csv"), l3_synth, delimiter=",", fmt="%.4f")
            np.savetxt(os.path.join(folder_path, "aVR.csv"), avr_synth, delimiter=",", fmt="%.4f")
            np.savetxt(os.path.join(folder_path, "aVL.csv"), avl_synth, delimiter=",", fmt="%.4f")
            np.savetxt(os.path.join(folder_path, "aVF.csv"), avf_synth, delimiter=",", fmt="%.4f")

    if len(data) > 0:
        generate_summary_report(data, folder_path)
        print("Report regenerated successfully with Pan-Tompkins peak detection!")

if __name__ == "__main__":
    target_folder = r"D:\code playground\PlatformIO\Projects\ecg_monitor\12_lead_ecg\readings\test_20260817_143519"
    fix_and_regenerate_templates(target_folder)
