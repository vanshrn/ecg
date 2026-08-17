# SPS Configuration Guide

If you want to change the **SPS (Samples Per Second)**, it requires a synchronized update across both the C++ firmware and the Python scripts, because ECG feature extraction heavily relies on exact time-domain math. 

Here is exactly what you need to change and the effects it will have:

## 1. Variables to Change in C++ (Firmware)

### `include/config.h`
*   Change `constexpr int SPS = 360;` to your new rate.
*   Change `constexpr unsigned long SAMPLE_INTERVAL_US = 2777;` to the new microsecond interval (`1,000,000 / SPS`).

### `src/main.cpp` (Notch Filter)
*   The constants `notch_b0`, `notch_b1`, `notch_a1`, etc., are currently hardcoded to filter **50Hz noise specifically at a 360Hz sample rate**. If you change the SPS, you **must recalculate** these IIR filter coefficients for the new Nyquist frequency, otherwise, AC mains noise will bleed into your signal.

### `src/spandan.cpp` (Time Math)
*   There are numerous hardcoded `360` values used to convert milliseconds to array indices (e.g., `(60 * 360) / 1000`). You must replace all instances of `360` with your new SPS value.
*   Update the exact time calculation: `(spandan_globalSampleIdx * 1000000ULL) / 360ULL;`

---

## 2. Variables to Change in Python (Tools)

*   **`generate_spandan_all.py`**: Update `sps=360` in the function signatures so your simulated CSVs are generated at the new rate.
*   **`stream_spandan.py`**: Update `sample_interval = 1.0 / 360.0` so it paces the serial feed correctly. 
*   **`replay_spandan.py`**: Update the `time.sleep(0.004)` (which currently assumes 250Hz) to `1.0 / new_SPS`. You may also want to adjust `MAX_PLOT_SAMPLES` to maintain exactly 2 seconds of visual history (i.e., `2 * SPS`).

---

## What are the Effects of Changing SPS?

1.  **Memory Usage (RAM):** The `ecgBatchBuffer[SPS]` array scales with the sample rate. A higher SPS takes up more RAM per 1-second batch. Furthermore, the `beat_buffer[1024]` ring buffer in `spandan.cpp` will hold a *shorter* duration of time if you increase SPS (1024 samples at 500Hz is only ~2 seconds, which might not be enough to capture a full PQRST block during extreme bradycardia).
2.  **Processing Overhead:** A higher SPS forces the ESP32 to run the DSP pipeline (Low pass, High pass, Notch) and threshold checks much more frequently, leaving less CPU idle time for background tasks like the Wi-Fi API uploads.
3.  **Signal Resolution:** 
    *   **Higher SPS (e.g., 500Hz):** Gives you much smoother curves and far greater accuracy when measuring narrow QRS complexes and exact R-peak amplitudes. 
    *   **Lower SPS (e.g., 200Hz):** Saves memory and network bandwidth, but you risk missing the true apex of sharp R-waves due to undersampling.
