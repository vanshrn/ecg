#include <Arduino.h>
#include "pin_config.h"
#include "config.h"
#include "buzzer.h"
#include "led_status.h"
#include "network.h"
#include "ecg_processor.h"
#include "signal_quality.h"

// Definition of Global Config Variables
const char* USER_ID      = "user_vansh";
const char* DEVICE_ID    = "esp32_ecg_01";
const char* WIFI_SSID     = "Vansh";
const char* WIFI_PASSWORD = "67676767";
const char* API_ENDPOINT  = "https://api-for-ecg.onrender.com/api/ecg";

bool isLiveMode = true; 
unsigned long lastSample = 0;

int ecgBatchBuffer[SPS];
int ecgRawBuffer[SPS];
int batchIndex = 0;
int lastBatchBeats = 0;
unsigned long sequenceNumber = 1;

extern int totalBeatsDetected;

// Timing Globals
unsigned long lastAlertTime = 0;
unsigned long lastNormalPrintTime = 0;
unsigned long lastBuzzerAlertTime = 0;

int injectedRawSample = 2048;

void handleSerialCommands() {
  while (Serial.available() > 0) {
    char buf[64];
    size_t len = Serial.readBytesUntil('\n', buf, sizeof(buf) - 1);
    buf[len] = '\0'; // null terminate
    
    String input = String(buf);
    input.trim();

    if (input.equalsIgnoreCase("mode live")) {
      isLiveMode = true;
      Serial.println("\n[SYSTEM MODE] Switched to LIVE AD8232 Sensor Input.");
    } 
    else if (input.equalsIgnoreCase("mode recorded")) {
      isLiveMode = false;
      resetECGFilters(2048, micros()); // Reset state so no-beat timer starts from NOW
      Serial.println("\n[SYSTEM MODE] Switched to RECORDED CSV Feed Input.");
    }
    else if (!isLiveMode) {
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
  Serial.setRxBufferSize(4096); // Increase buffer so Python data doesn't overflow during Wi-Fi POSTs
  Serial.begin(115200);
  
  setupBuzzer();
  setupLED();

  pinMode(LO_PLUS, INPUT_PULLDOWN);
  pinMode(LO_MINUS, INPUT_PULLDOWN);
  analogReadResolution(12);

  connectWiFi();
  initNetworkTask(); // Initialize background HTTP worker on Core 0

  Serial.println("\n=============================================");
  Serial.println("  ESP32 ECG MONITOR SYSTEM INITIALIZED       ");
  Serial.println("  Controls: ");
  Serial.println("    - Send 'mode live'     : Sensor Input");
  Serial.println("    - Send 'mode recorded' : Stream File Input");
  Serial.println("=============================================\n");
}

void loop() {
  handleSerialCommands();

  unsigned long nowUs = micros();
  
  if (nowUs - lastSample >= SAMPLE_INTERVAL_US) {
    lastSample = nowUs;
    unsigned long nowMs = millis();

    int raw = 0;

    if (isLiveMode) {
      bool rawLeadOff = (digitalRead(LO_PLUS) == 1) || (digitalRead(LO_MINUS) == 1);
      
      if (rawLeadOff) {
        leadOffConsecutiveCounter++;
      } else {
        leadOffConsecutiveCounter = 0;
      }

      if (leadOffConsecutiveCounter >= 15) {
        currentLeadsOff = true;
        wasOff = true;
        currentSeverity = "WARNING";
        currentDiagnosis = "Leads Disconnected";
        
        if (nowMs - lastAlertTime >= ALERT_COOLDOWN_MS) {
          lastAlertTime = nowMs;
          Serial.println("[ALERT] ELECTRODE PADS DISCONNECTED!");
        }
        
        ecgBatchBuffer[batchIndex] = 0;
        batchIndex++;

        if (batchIndex >= SPS) {
          batchIndex = 0;
          upload1SecBatchToAPI(ecgBatchBuffer, SPS, currentLeadsOff, currentSeverity, currentDiagnosis);
        }
        return; 
      }

      currentLeadsOff = false;
      raw = readOversampled(ECG_PIN, 2);
    } else {
      raw = injectedRawSample;
      currentLeadsOff = false;
    }

    if (wasOff) {
      resetECGFilters(raw, nowUs);
    }

    // DSP Filtering Pipeline
    emaValue = (EMA_ALPHA * raw) + ((1.0 - EMA_ALPHA) * emaValue);
    float hpOut = HP_ALPHA * (hpPrevOut + emaValue - hpPrevRaw);
    hpPrevRaw = emaValue; hpPrevOut = hpOut;
    float notchOut = applyNotch(hpOut);

    int output = (int)(notchOut + 2048);
    output = constrain(output, 0, 4095);

    processBeatFeatures(output, nowUs);

    if (currentSeverity == "NORMAL" && (nowMs - lastNormalPrintTime >= NORMAL_PRINT_INTERVAL_MS)) {
      lastNormalPrintTime = nowMs;
      Serial.print("[INFO @ ");
      Serial.print(nowMs / 1000);
      Serial.print("s] Rhythm: NORMAL | BPM: ");
      Serial.println(features.bpm, 1);
    }

    ecgRawBuffer[batchIndex] = raw;
    ecgBatchBuffer[batchIndex] = output;
    batchIndex++;

    if (batchIndex >= SPS) {
      batchIndex = 0;
      
      int peakCount = totalBeatsDetected - lastBatchBeats;
      lastBatchBeats = totalBeatsDetected;
      
      PerformanceMetrics metrics = calculateBatchMetrics(ecgRawBuffer, ecgBatchBuffer, SPS, features.bpm, peakCount);
      printMetricsToSerial(sequenceNumber++, metrics);

      upload1SecBatchToAPI(ecgBatchBuffer, SPS, currentLeadsOff, currentSeverity, currentDiagnosis);
    }
  }
}