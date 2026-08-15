#include "led_status.h"
#include <Arduino.h>

void setupLED() {
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
}

void setLEDConnected(bool connected) {
  digitalWrite(LED_BUILTIN, connected ? HIGH : LOW);
}