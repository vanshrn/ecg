#include <Arduino.h>

#define ECG_PIN  34
#define LO_PLUS  33
#define LO_MINUS 32

const int SAMPLE_INTERVAL_US = 4000; // 250 Hz (exact 4ms sample timing)
unsigned long lastSample = 0;

// --- Your Original Proven Filter Constants ---
float emaValue = 0;
const float EMA_ALPHA = 0.18; // Fast low-pass response

float hpPrevRaw = 0;
float hpPrevOut = 0;
const float HP_ALPHA = 0.995; // Flattens baseline without phase distortion

// --- 50Hz Notch Filter (Mains Hum Removal) ---
float notch_x1 = 0, notch_x2 = 0;
float notch_y1 = 0, notch_y2 = 0;
const float notch_b0 = 0.9518, notch_b1 = -0.5883, notch_b2 = 0.9518;
const float notch_a1 = -0.5871, notch_a2 = 0.9025;

bool wasOff = false;

float applyNotch(float x) {
  float y = notch_b0 * x + notch_b1 * notch_x1 + notch_b2 * notch_x2
            - notch_a1 * notch_y1 - notch_a2 * notch_y2;
  notch_x2 = notch_x1; notch_x1 = x;
  notch_y2 = notch_y1; notch_y1 = y;
  return y;
}

int readOversampled(int pin, int samples) {
  long sum = 0;
  for (int i = 0; i < samples; i++) sum += analogRead(pin);
  return (int)(sum / samples);
}

void setup() {
  Serial.begin(115200);
  pinMode(LO_PLUS, INPUT);
  pinMode(LO_MINUS, INPUT);
  analogReadResolution(12);
}

void loop() {
  unsigned long now = micros();
  if (now - lastSample >= (unsigned long)SAMPLE_INTERVAL_US) {
    lastSample = now;

    // Fast lead-off check
    if ((digitalRead(LO_PLUS) == 1) || (digitalRead(LO_MINUS) == 1)) {
      wasOff = true;
      Serial.print(">raw:0\n>filtered:0\n");
      return;
    }

    int raw = readOversampled(ECG_PIN, 4);

    // Reset filter states immediately on reconnect to prevent startup spikes
    if (wasOff) {
      emaValue = raw; 
      hpPrevRaw = raw; 
      hpPrevOut = 0;
      notch_x1 = notch_x2 = notch_y1 = notch_y2 = 0;
      wasOff = false;
    }

    // Stage 1: Low-pass EMA (fast & zero lag)
    emaValue = (EMA_ALPHA * raw) + ((1 - EMA_ALPHA) * emaValue);

    // Stage 2: High-pass (removes baseline drift)
    float hpOut = HP_ALPHA * (hpPrevOut + emaValue - hpPrevRaw);
    hpPrevRaw = emaValue;
    hpPrevOut = hpOut;

    // Stage 3: 50Hz Notch filter
    float notchOut = applyNotch(hpOut);

    // Center output at 2048
    int output = (int)(notchOut + 2048);
    output = constrain(output, 0, 4095);

    // Fast Teleplot stream
    Serial.print(">raw:");
    Serial.print(raw);
    Serial.print("\n>filtered:");
    Serial.println(output);
  }
}