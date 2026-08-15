#include "buzzer.h"
#include <Arduino.h>

void setupBuzzer() {
  pinMode(BUZZER_PIN, OUTPUT);
}

void playWifiConnectedTone() {
  Serial.println("[BUZZER] Wi-Fi Connected Chime");
  tone(BUZZER_PIN, 1200, 150);
}

void playWarningAlert() {
  Serial.println("[BUZZER] WARNING Alarm Triggered");
  tone(BUZZER_PIN, 800, 250);
}

void playCriticalAlert() {
  Serial.println("[BUZZER] CRITICAL Alarm Triggered");
  tone(BUZZER_PIN, 2400, 400);
}