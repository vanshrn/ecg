#include <Arduino.h>
#include <WiFi.h>

const char* ssid = "Vansh";
const char* password = "67676767";

#ifndef LED_BUILTIN
  #define LED_BUILTIN 2
#endif

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  Serial.println("\n--- [TEST] Starting Wi-Fi Test ---");
  Serial.print("Connecting to: ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\n[SUCCESS] Wi-Fi Connected!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  digitalWrite(LED_BUILTIN, HIGH); // LED turns ON when connected
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("Wi-Fi Status: Connected");
  } else {
    Serial.println("Wi-Fi Status: Disconnected");
    digitalWrite(LED_BUILTIN, LOW);
  }
  delay(3000);
}