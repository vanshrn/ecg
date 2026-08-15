#include <Arduino.h>
#include "spandan.h"
#include "ecg_processor.h" // keep for notch filter
#include "pin_config.h"

// Variables for recorded mode
static bool recordedMode = false;
static int injectedRawSample = 2048;
static unsigned long virtual_time_us = 0;
static unsigned long lastSample = 0;
const unsigned long SAMPLE_INTERVAL_US = 2777; // 360 Hz

// Mock functions for missing buzzer links
void playCriticalAlert() {}
void playWarningAlert() {}

void handleSerialCommands() {
  while (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) continue;

    if (line.equalsIgnoreCase("mode recorded")) {
      recordedMode = true;
      virtual_time_us = micros();
      resetSpandanFilters(2048, virtual_time_us);
      Serial.println("\n[SYSTEM MODE] Switched to RECORDED CSV Feed Input.");
    } else if (line.equalsIgnoreCase("mode live")) {
      recordedMode = false;
      Serial.println("[SYSTEM MODE] Switched to LIVE Sensor Input.");
    } else if (recordedMode) {
      int commaIdx = line.indexOf(',');
      if (commaIdx > 0) {
        String valStr = line.substring(commaIdx + 1);
        injectedRawSample = valStr.toInt();
        
        // Advance virtual time by exactly 1 sample at 360Hz (2777 microseconds)
        virtual_time_us += 2777;
        
        // Process synchronously to guarantee mathematical perfection (no jitter/aliasing)
        processSpandanFeatures(injectedRawSample, virtual_time_us);
      }
    }
  }
}

void setup() {
  Serial.setRxBufferSize(4096);
  Serial.begin(115200);
  Serial.println("\n--- [SPANDAN TEST SYSTEM READY] Monitoring for Abnormalities ---");
}

const float EMA_ALPHA = 0.22;
const float HP_ALPHA = 0.996;


void loop() {
  handleSerialCommands();
  
  if (!recordedMode) {
    unsigned long nowUs = micros();
    if (nowUs - lastSample >= SAMPLE_INTERVAL_US) {
      lastSample = nowUs;
      int raw = analogRead(ECG_PIN);
      
      // Stage 1: Low-pass EMA
      emaValue = (EMA_ALPHA * raw) + ((1.0 - EMA_ALPHA) * emaValue);
      // Stage 2: High-pass
      float hpOut = HP_ALPHA * (hpPrevOut + emaValue - hpPrevRaw);
      hpPrevRaw = emaValue; 
      hpPrevOut = hpOut;
      // Stage 3: 50Hz Notch
      float notchOut = applyNotch(hpOut);
      int output = (int)(notchOut + 2048);
      output = constrain(output, 0, 4095);
      
      processSpandanFeatures(output, nowUs);
    }
  }
}
