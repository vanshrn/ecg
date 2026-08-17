import serial
import time
import threading
import collections
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np

# Adjust to your device's configuration
COM_PORT = 'COM5'
BAUD_RATE = 115200

def record_lead(lead_name, duration=10):
    MAX_PLOT_SAMPLES = 500 # Approx 2 seconds at 250Hz
    raw_buffer = collections.deque([0]*MAX_PLOT_SAMPLES, maxlen=MAX_PLOT_SAMPLES)
    filt_buffer = collections.deque([2048]*MAX_PLOT_SAMPLES, maxlen=MAX_PLOT_SAMPLES)
    
    full_raw = []
    full_filt = []
    
    running = True
    
    def handle_serial():
        try:
            ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
            # Wait 3 seconds to let the ESP32 boot and its digital filters settle
            time.sleep(3.0)
            ser.reset_input_buffer()
            start_time = time.time()
            
            while running and (time.time() - start_time < duration):
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    raw_val = None
                    filt_val = None
                    
                    if line.startswith('R:'):
                        try:
                            raw_val = float(line.split(':')[1])
                            next_line = ser.readline().decode('utf-8', errors='ignore').strip()
                            if next_line.startswith('F:'):
                                filt_val = float(next_line.split(':')[1])
                        except:
                            pass
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
                    else:
                        # Fallback for plain numbers
                        try:
                            parts = line.split(',')
                            raw_val = float(parts[0])
                            filt_val = float(parts[1]) if len(parts) > 1 else raw_val 
                        except:
                            pass
                            
                    if raw_val is not None:
                        raw_buffer.append(raw_val)
                        full_raw.append(raw_val)
                        if filt_val is not None:
                            filt_buffer.append(filt_val)
                            full_filt.append(filt_val)
            ser.close()
        except Exception as e:
            print(f"\n[Serial Error]: {e}")
            
    t = threading.Thread(target=handle_serial, daemon=True)
    t.start()
    
    # Plotting
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
        line_raw.set_ydata(raw_buffer)
        line_filt.set_ydata(filt_buffer)
        
        # Dynamic Y-axis scaling for Raw and Filtered signals
        try:
            r_min, r_max = min(raw_buffer), max(raw_buffer)
            if r_max == r_min: r_max = r_min + 1
            r_pad = max((r_max - r_min) * 0.15, 50)
            
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
        
    ani = animation.FuncAnimation(fig, update_fig, interval=30, blit=False, cache_frame_data=False)
    
    plt.show(block=False)
    while t.is_alive():
        plt.pause(0.1)
        if not plt.fignum_exists(fig.number):
            running = False
            break
            
    plt.close(fig)
    running = False
    t.join()
    
    return np.array(full_raw), np.array(full_filt)
