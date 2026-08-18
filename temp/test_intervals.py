import pandas as pd
import numpy as np
from scipy import signal

def get_intervals(y, fs=250):
    r_est = int(0.4 * fs)
    r_idx = np.argmax(y[r_est-15:r_est+15]) + r_est - 15
    q_idx = np.argmin(y[r_idx-20:r_idx]) + r_idx - 20
    s_idx = np.argmin(y[r_idx:r_idx+35]) + r_idx
    t_idx = np.argmax(y[r_idx+35:r_idx+120]) + r_idx + 35
    p_idx = np.argmax(y[r_idx-65:r_idx-20]) + r_idx - 65
    
    y_sm = signal.savgol_filter(y, window_length=11, polyorder=3)
    
    p_on = p_idx
    while p_on > 0 and y_sm[p_on] > y_sm[p_on-1]: p_on -= 1
        
    q_on = q_idx
    while q_on > p_idx and y_sm[q_on] < y_sm[q_on-1]: q_on -= 1
        
    s_off = s_idx
    while s_off < t_idx and y_sm[s_off] < y_sm[s_off+1]: s_off += 1
        
    t_off = t_idx
    while t_off < len(y_sm)-1 and y_sm[t_off] > y_sm[t_off+1]: t_off += 1
        
    ms = 1000.0 / fs
    pr = (q_on - p_on) * ms
    qrs = (s_off - q_on) * ms
    qt = (t_off - q_on) * ms
    
    return {'P': p_idx, 'Q': q_idx, 'R': r_idx, 'S': s_idx, 'T': t_idx}, pr, qrs, qt

def remove_baseline_wander(data, fs=250):
    b, a = signal.butter(4, 0.67 / (fs / 2.0), btype='high')
    return signal.filtfilt(b, a, data)

def main():
    l1 = pd.read_csv(r"D:\code playground\PlatformIO\Projects\ecg_monitor\12_lead_ecg\readings\test_20260817_195314\Lead_I.csv")['Filtered'].values
    l2 = pd.read_csv(r"D:\code playground\PlatformIO\Projects\ecg_monitor\12_lead_ecg\readings\test_20260817_195314\Lead_II.csv")['Filtered'].values
    
    l1 = remove_baseline_wander(l1)
    l2 = remove_baseline_wander(l2)
    
    # Scale just like main.py
    if np.max(l1) < abs(np.min(l1)): l1 = -l1
    if np.max(l2) < abs(np.min(l2)): l2 = -l2
    l1 = l1 * (1000.0 / max(np.max(l1), 1))
    l2 = l2 * (1400.0 / max(np.max(l2), 1))
    
    r_est = int(0.4 * 250)
    l1 = l1[np.argmax(l1)-100 : np.argmax(l1)+400] # rough crop for testing
    
    # Actually just call get_intervals directly on a segment
    l1_crop = l1[200:200+625] # simulate align_and_crop roughly
    try:
        pts, pr, qrs, qt = get_intervals(l1_crop)
        print(f"Lead I -> P:{pts['P']}, Q:{pts['Q']}, R:{pts['R']}, S:{pts['S']}, T:{pts['T']}")
        print(f"Lead I -> PR: {pr}ms, QRS: {qrs}ms, QT: {qt}ms")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    main()
