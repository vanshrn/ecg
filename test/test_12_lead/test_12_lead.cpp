/**
 * test_12_lead.cpp
 *
 * Dual AD8232 acquisition for 12-lead ECG derivation.
 *
 *  - Reads Lead I (AD8232 #1) and Lead II (AD8232 #2) simultaneously at 250 Hz.
 *  - Applies ONLY a first-order IIR high-pass to remove baseline wander (≈ 0.05 Hz).
 *    No low-pass, no notch, no oversampling averaging — raw signal is preserved.
 *  - Outputs each sample as:
 *      >L1raw:<int>  >L1hp:<float>  >L2raw:<int>  >L2hp:<float>
 *    so the Python recorder can parse and save Raw + Filtered columns for both leads.
 *
 * Wiring (adjust pins to match your board):
 *   AD8232 #1 (Lead I)  OUTPUT → GPIO 34   LO+ → GPIO 33   LO- → GPIO 32
 *
 * Sampling: 250 Hz (4000 µs interval), hardware timer based.
 */

#include <Arduino.h>

// =============================================================
// PIN ASSIGNMENTS
// =============================================================

// AD8232 #1 — Lead I (RA → LA)
#define ECG1_PIN    34
#define LO1_PLUS    33
#define LO1_MINUS   32


// =============================================================
// SAMPLING
// =============================================================

const unsigned long SAMPLE_INTERVAL_US = 4000; // 250 Hz
volatile unsigned long lastSample = 0;

// =============================================================
// BASELINE WANDER REMOVAL
// First-order IIR high-pass:  y[n] = α * (y[n-1] + x[n] - x[n-1])
//
// Cutoff frequency: fc = (1 - α) * fs / (2π)
// Target fc ≈ 0.05 Hz at fs = 250 Hz  →  α ≈ 1 - (2π * 0.05 / 250) = 0.99874
//
// This is the minimum necessary processing on-chip:
//   • Removes slow respiratory and motion baseline drift
//   • Preserves DC-free ECG morphology (P, QRS, T intact)
//   • Zero extra amplitude distortion on frequencies > 0.5 Hz
// =============================================================

const float HP_ALPHA = 0.99874f;   // ≈ 0.05 Hz cutoff at 250 Hz

// State for Lead I
float hp1_x_prev = 0.0f;
float hp1_y_prev = 0.0f;


inline float applyHP(float x, float &x_prev, float &y_prev)
{
    float y = HP_ALPHA * (y_prev + x - x_prev);
    x_prev = x;
    y_prev = y;
    return y;
}

void resetHP1(float value)
{
    hp1_x_prev = value;
    hp1_y_prev = 0.0f;
}


// =============================================================
// LEAD-OFF STATE
// =============================================================

bool leadOff1 = false;   // Lead I electrodes detached


// =============================================================
// SETUP
// =============================================================

void setup()
{
    Serial.begin(115200);

    // Lead I
    pinMode(LO1_PLUS,  INPUT);
    pinMode(LO1_MINUS, INPUT);


    // 12-bit ADC, full-range attenuation (0–3.3 V)
    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);

    lastSample = micros();

    Serial.println(">boot:ok");
}


// =============================================================
// MAIN LOOP
// =============================================================

void loop()
{
    unsigned long now = micros();

    if ((unsigned long)(now - lastSample) < SAMPLE_INTERVAL_US)
        return;

    // Advance deadline by exactly one interval (avoids drift accumulation)
    lastSample += SAMPLE_INTERVAL_US;

    // ---------------------------------------------------------
    // LEAD-OFF DETECTION
    // ---------------------------------------------------------

    bool lo1 = digitalRead(LO1_PLUS) || digitalRead(LO1_MINUS);

    if (lo1 ) {
        // Report which channel(s) are off and skip this sample
        if (lo1) { Serial.println(">off1:1"); leadOff1 = true; }
        return;
    }

    // ---------------------------------------------------------
    // READ RAW ADC
    // ---------------------------------------------------------

    int raw1 = analogRead(ECG1_PIN);

    // ---------------------------------------------------------
    // RESET HIGH-PASS STATE AFTER RECONNECT
    // Primes the filter with the first real sample so it doesn't
    // produce a huge transient spike on reconnect.
    // ---------------------------------------------------------

    if (leadOff1) { resetHP1((float)raw1); leadOff1 = false; }

    // ---------------------------------------------------------
    // BASELINE WANDER REMOVAL ONLY
    // ---------------------------------------------------------

    float hp1 = applyHP((float)raw1, hp1_x_prev, hp1_y_prev);

    // ---------------------------------------------------------
    // OUTPUT — one line per lead per sample
    // Format matches what ecg_recorder.py expects:
    //   >L1raw:<int>\n>L1hp:<float>\n>L2raw:<int>\n>L2hp:<float>
    // ---------------------------------------------------------

    Serial.print(">L1raw:");
    Serial.println(raw1);

    Serial.print(">L1hp:");
    Serial.println(hp1, 2);

}
