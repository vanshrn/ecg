#include <Arduino.h>
#include "ecg_processor.h"
#include "pin_config.h"

int injectedRawSample = 2048;
bool isLiveMode = false;
unsigned long lastAlertTime = 0;
unsigned long lastBuzzerAlertTime = 0;
unsigned long lastSample = 0;
const unsigned long SAMPLE_INTERVAL_US = 2777; // 360 Hz

// Mock functions for missing buzzer links
void playCriticalAlert() {}
void playWarningAlert() {}

void handleSerialCommands() {
  while (Serial.available() > 0) {
    char buf[64];
    size_t len = Serial.readBytesUntil('\n', buf, sizeof(buf) - 1);
    buf[len] = '\0';
    
    String input = String(buf);
    input.trim();

    if (input.equalsIgnoreCase("mode recorded")) {
      resetECGFilters(2048, micros());
      Serial.println("\n[SYSTEM MODE] Switched to RECORDED CSV Feed Input.");
    }
    else {
      int val = 0;
      if (input.startsWith("sample,")) {
        val = input.substring(7).toInt();
      } else {
        val = input.toInt();
      }
      
      if (val > 0) {
        injectedRawSample = val;
      }
    }
  }
}

void setup() {
  Serial.setRxBufferSize(4096);
  Serial.begin(115200);
  Serial.println("\n--- [TEST ALERT SYSTEM READY] Monitoring for Abnormalities (No API) ---");
}

const float EMA_ALPHA = 0.22;
const float HP_ALPHA = 0.996;

void loop() {
  handleSerialCommands();
  unsigned long nowUs = micros();
  
  if (nowUs - lastSample >= SAMPLE_INTERVAL_US) {
    lastSample = nowUs;

    // Stage 1: Low-pass EMA (fast & zero lag)
    emaValue = (EMA_ALPHA * injectedRawSample) + ((1.0 - EMA_ALPHA) * emaValue);

    // Stage 2: High-pass (removes baseline drift)
    float hpOut = HP_ALPHA * (hpPrevOut + emaValue - hpPrevRaw);
    hpPrevRaw = emaValue; 
    hpPrevOut = hpOut;

    // Stage 3: 50Hz Notch filter
    float notchOut = applyNotch(hpOut);

    int output = (int)(notchOut + 2048);
    output = constrain(output, 0, 4095);

    // Run the robust DSP and detection pipeline
    processBeatFeatures(output, nowUs);
  }
}
