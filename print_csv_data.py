import sys
import pandas as pd
import time

def print_csv_data(filepath, delay=0.0):
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return

    print(f"Reading {filepath}...")
    print(f"Total samples: {len(df)}")
    print("-" * 30)

    try:
        for idx, row in df.iterrows():
            # CSV has Index, Time_ms, Raw, Filtered
            print(f"Line: {idx + 2:4d} | Index: {int(row['Index']):4d} | Time: {int(row['Time_ms']):5d} ms | Raw: {int(row['Raw']):4d}")
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    file_to_read = "recordings/svt_15s.csv"
    if len(sys.argv) > 1:
        file_to_read = sys.argv[1]
    
    # You can add a small delay like 0.002 to simulate real-time reading
    print_csv_data(file_to_read, delay=0.0)
