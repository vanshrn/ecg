#include "network.h"
#include "config.h"
#include "led_status.h"
#include "buzzer.h"
#include <WiFi.h>
#include <HTTPClient.h>

extern unsigned long sequenceNumber;

struct PayloadQueueItem {
  int data[360];
  bool leadsOff;
  char severity[16];
  char diagnosis[64];
  unsigned long seq;
  unsigned long timestampMs; // Added to log capture time
};

static QueueHandle_t apiQueue = NULL;

void networkWorkerTask(void* pvParameters) {
  PayloadQueueItem item;
  HTTPClient http;

  while (true) {
    if (xQueueReceive(apiQueue, &item, portMAX_DELAY) == pdTRUE) {
      if (WiFi.status() != WL_CONNECTED) {
        connectWiFi();
      }

      if (WiFi.status() == WL_CONNECTED) {
        http.begin(API_ENDPOINT);
        http.addHeader("Content-Type", "application/json");

        String jsonPayload = "{";
        jsonPayload += "\"userId\":\"" + String(USER_ID) + "\",";
        jsonPayload += "\"deviceId\":\"" + String(DEVICE_ID) + "\",";
        jsonPayload += "\"seq\":" + String(item.seq) + ",";
        jsonPayload += "\"sr\":360,";
        jsonPayload += "\"lo\":" + String(item.leadsOff ? "true" : "false") + ",";
        
        jsonPayload += "\"data\":[";
        for (int i = 0; i < 360; i++) {
          jsonPayload += String(item.data[i]);
          if (i < 359) jsonPayload += ",";
        }
        jsonPayload += "],";

        jsonPayload += "\"warnings\":[";
        if (item.leadsOff) {
          jsonPayload += "\"LEADS_DISCONNECTED\"";
        } else if (String(item.severity) != "NORMAL") {
          jsonPayload += "\"" + String(item.severity) + ": " + String(item.diagnosis) + "\"";
        }
        jsonPayload += "]";
        jsonPayload += "}";

        int httpResponseCode = http.POST(jsonPayload);

        // Updated log print to include timestamp in seconds
        Serial.print("[API POST @ ");
        Serial.print(item.timestampMs / 1000);
        Serial.print("s] Seq: #");
        Serial.print(item.seq);
        Serial.print(" | Code: ");
        Serial.print(httpResponseCode);
        if (httpResponseCode >= 200 && httpResponseCode < 300) {
          Serial.println(" [SUCCESS]");
        } else {
          Serial.print(" [ERROR] ");
          Serial.println(http.errorToString(httpResponseCode));
        }

        http.end();
      }
    }
  }
}

void initNetworkTask() {
  apiQueue = xQueueCreate(5, sizeof(PayloadQueueItem));
  xTaskCreatePinnedToCore(
    networkWorkerTask,
    "NetWorker",
    8192,
    NULL,
    1,
    NULL,
    0
  );
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    setLEDConnected(true);
    return;
  }
  
  setLEDConnected(false);
  Serial.print("[WIFI] Connecting to ");
  Serial.println(WIFI_SSID);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 15) {
    vTaskDelay(pdMS_TO_TICKS(500));
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WIFI] Connected Successfully!");
    setLEDConnected(true);
    playWifiConnectedTone();
  } else {
    Serial.println("\n[WIFI] Connection Failed. Operating Offline.");
    setLEDConnected(false);
  }
}

void upload1SecBatchToAPI(int* ecgBatchBuffer, int sps, bool currentLeadsOff, String currentSeverity, String currentDiagnosis) {
  if (apiQueue == NULL) return;

  PayloadQueueItem item;
  memcpy(item.data, ecgBatchBuffer, sps * sizeof(int));
  item.leadsOff = currentLeadsOff;
  item.seq = sequenceNumber++;
  item.timestampMs = millis(); // Captures exact completion time of the batch
  strncpy(item.severity, currentSeverity.c_str(), sizeof(item.severity) - 1);
  strncpy(item.diagnosis, currentDiagnosis.c_str(), sizeof(item.diagnosis) - 1);

  xQueueSend(apiQueue, &item, 0);
}