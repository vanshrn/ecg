import os
import sys
import pandas as pd
import numpy as np

# Add the directory containing main.py to sys.path so we can import it
sys.path.append(r"D:\code playground\PlatformIO\Projects\ecg_monitor\12_lead_ecg")
from main import generate_summary_report

def main():
    target_dir = r"D:\code playground\PlatformIO\Projects\ecg_monitor\12_lead_ecg\readings\test_20260817_195314"
    
    report_data = {}
    leads = ['Lead_I', 'Lead_II', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
    
    for lead in leads:
        csv_path = os.path.join(target_dir, f"{lead}.csv")
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path)
                if lead in ['Lead_I', 'Lead_II'] and 'Raw' in df.columns:
                    report_data[lead] = df['Raw'].values
                elif 'Filtered' in df.columns:
                    report_data[lead] = df['Filtered'].values
                else:
                    # In case the CSV is just a single column of numbers without a header
                    report_data[lead] = np.loadtxt(csv_path, delimiter=",")
            except Exception as e:
                print(f"Error loading {lead}: {e}")
                
    if report_data:
        print("Generating new summary report...")
        generate_summary_report(report_data, target_dir)
        print("Report regenerated successfully at:", target_dir)
    else:
        print("No data found to regenerate report.")

if __name__ == "__main__":
    main()
