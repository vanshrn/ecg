import os
import numpy as np
from main import generate_summary_report

def regenerate(folder_path):
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
                print(f"Failed to load {filename}: {e}")
                
    if len(data) > 0:
        generate_summary_report(data, folder_path)
        print("Report regenerated successfully.")
    else:
        print("No data found.")

if __name__ == "__main__":
    target_folder = r"D:\code playground\PlatformIO\Projects\ecg_monitor\12_lead_ecg\readings\test_20260817_124409"
    regenerate(target_folder)
