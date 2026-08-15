#include <Arduino.h>
#include "../src/network.h"
#include "../src/config.h"

// Dummy buffer to simulate a batch of ECG data (360 samples)
int testEcgBuffer[360];

void setup() {
  Serial.begin(115200);
  
  // Fill the test buffer with a dummy sine wave pattern
  for (int i = 0; i < 360; i++) {
    testEcgBuffer[i] = 2048 + (int)(500.0 * sin(i * 0.1));
  }

  // Initialize the dedicated Wi-Fi FreeRTOS background task
  initNetworkTask();

  Serial.println("\n--- [TEST API READY] ---");
  Serial.println("Attempting to connect to Wi-Fi and upload a test packet every 5 seconds.");
}

void loop() {
  // Wait 5 seconds between tests
  delay(5000);
  
  Serial.println("\n[TEST] Queueing API Upload...");
  
  // Test uploading a Normal Sinus Rhythm packet
  upload1SecBatchToAPI(testEcgBuffer, 360, false, "NORMAL", "Normal Sinus Rhythm");
  
  delay(5000);
  
  Serial.println("\n[TEST] Queueing API Upload with Abnormality...");
  
  // Test uploading an abnormality packet
  upload1SecBatchToAPI(testEcgBuffer, 360, false, "CRITICAL", "Ventricular Tachycardia");
}
