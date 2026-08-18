import serial
import time
import threading
import collections
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np

# Configuration constants for the hardware connection
# Adjust COM_PORT to match the ESP32 connection (e.g., /dev/ttyUSB0 on Linux)
COM_PORT = 'COM5'
BAUD_RATE = 115200

def record_lead(lead_name, duration=10):
    """
    Records ECG data from the serial port for a specific lead and plots it in real-time.
    
    Args:
        lead_name (str): The name of the lead being recorded (e.g., 'Lead_I', 'V1').
        duration (int): How long to record the data in seconds.
        
    Returns:
        tuple: (raw_data_array, filtered_data_array) as numpy arrays.
    """
    # Create fixed-size buffers for the live plot to maintain a rolling window of ~2 seconds
    MAX_PLOT_SAMPLES = 500 
    raw_buffer = collections.deque([0]*MAX_PLOT_SAMPLES, maxlen=MAX_PLOT_SAMPLES)
    filt_buffer = collections.deque([2048]*MAX_PLOT_SAMPLES, maxlen=MAX_PLOT_SAMPLES)
    
    # Lists to store the entire recording history
    full_raw = []
    full_filt = []
    
    running = True
    
    def handle_serial():
        """
        Background thread function to read data from the serial port without blocking the GUI.
        """
        try:
            ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
            
            # Hardware Initialization Delay:
            # We wait 3 seconds before capturing data because the ESP32 digital filters 
            # (especially high-pass filters) take time to settle after connection. 
            # Without this, the first few seconds of data will be wildly distorted.
            time.sleep(3.0)
            ser.reset_input_buffer()
            start_time = time.time()
            
            # Continuously read from the serial port until the duration is reached
            while running and (time.time() - start_time < duration):
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    raw_val = None
                    filt_val = None
                    
                    # Parse different possible serial formats coming from the ESP32
                    
                    # Format 1: Basic text markers "R:val" and "F:val"
                    if line.startswith('R:'):
                        try:
                            raw_val = float(line.split(':')[1])
                            next_line = ser.readline().decode('utf-8', errors='ignore').strip()
                            if next_line.startswith('F:'):
                                filt_val = float(next_line.split(':')[1])
                        except:
                            pass
                            
                    # Format 2: Arduino Serial Plotter standard format ">raw:val" and ">filtered:val"
                    elif line.startswith('>raw:') or line.lower().startswith('raw:'):
                        try:
                            raw_val = float(line.split(':')[1])
                            next_line = ser.readline().decode('utf-8', errors='ignore').strip()
                            if next_line.startswith('>filtered:') or next_line.lower().startswith('filtered:'):
                                filt_val = float(next_line.split(':')[1])
                            else:
                                filt_val = raw_val
                        except:
                            pass
                            
                    # Format 3: Simple comma-separated values "raw,filtered"
                    else:
                        try:
                            parts = line.split(',')
                            raw_val = float(parts[0])
                            filt_val = float(parts[1]) if len(parts) > 1 else raw_val 
                        except:
                            pass
                            
                    # If parsing was successful, append the values to both the plot buffers and full arrays
                    if raw_val is not None:
                        raw_buffer.append(raw_val)
                        full_raw.append(raw_val)
                        if filt_val is not None:
                            filt_buffer.append(filt_val)
                            full_filt.append(filt_val)
            ser.close()
        except Exception as e:
            print(f"\n[Serial Error]: {e}")
            
    # Launch the serial reader in a separate background daemon thread.
    # This is required because matplotlib's live plotting requires control of the main thread.
    t = threading.Thread(target=handle_serial, daemon=True)
    t.start()
    
    # Initialize real-time matplotlib plots
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6))
    fig.canvas.manager.set_window_title(f'Recording {lead_name} (Duration: {duration}s)')
    
    line_raw, = ax1.plot(raw_buffer, color='orange', label='Raw Signal')
    ax1.set_ylabel('ADC Raw')
    ax1.legend(loc='upper right')
    ax1.grid(True, linestyle='--', alpha=0.5)

    line_filt, = ax2.plot(filt_buffer, color='cyan', label='Filtered Signal')
    ax2.set_ylabel('Filtered Signal')
    ax2.legend(loc='upper right')
    ax2.grid(True, linestyle='--', alpha=0.5)
    
    def update_fig(frame):
        """
        Animation callback function called periodically to update the plot data.
        """
        line_raw.set_ydata(raw_buffer)
        line_filt.set_ydata(filt_buffer)
        
        # Dynamic Y-axis scaling:
        # Instead of fixed y-limits, we calculate the min/max of the current data window
        # and dynamically adjust the Y-axis so the ECG graph is never cut off or too squished.
        try:
            r_min, r_max = min(raw_buffer), max(raw_buffer)
            if r_max == r_min: r_max = r_min + 1
            # Add 15% padding above and below the signal
            r_pad = max((r_max - r_min) * 0.15, 50)
            
            # Only update the limits if the signal goes out of bounds or if the padding is highly excessive
            current_r_ylim = ax1.get_ylim()
            if r_min < current_r_ylim[0] + r_pad*0.2 or r_max > current_r_ylim[1] - r_pad*0.2 or (current_r_ylim[1] - current_r_ylim[0]) > (r_max - r_min) * 2.0:
                ax1.set_ylim(r_min - r_pad, r_max + r_pad)

            f_min, f_max = min(filt_buffer), max(filt_buffer)
            if f_max == f_min: f_max = f_min + 1
            f_pad = max((f_max - f_min) * 0.15, 50)
            
            current_f_ylim = ax2.get_ylim()
            if f_min < current_f_ylim[0] + f_pad*0.2 or f_max > current_f_ylim[1] - f_pad*0.2 or (current_f_ylim[1] - current_f_ylim[0]) > (f_max - f_min) * 2.0:
                ax2.set_ylim(f_min - f_pad, f_max + f_pad)
        except Exception:
            pass
            
        return line_raw, line_filt
        
    # Bind the update_fig function to the plot animation loop
    ani = animation.FuncAnimation(fig, update_fig, interval=30, blit=False, cache_frame_data=False)
    
    # Start the non-blocking GUI loop
    plt.show(block=False)
    
    # Wait for the background serial thread to finish its recording duration
    while t.is_alive():
        plt.pause(0.1) # Yield execution to the matplotlib event loop so the window remains responsive
        
        # If the user manually closes the window before the time is up, abort the recording
        if not plt.fignum_exists(fig.number):
            running = False
            break
            
    # Cleanup after recording finishes
    plt.close(fig)
    running = False
    t.join() # Ensure the serial thread has completely shut down
    
    return np.array(full_raw), np.array(full_filt)
