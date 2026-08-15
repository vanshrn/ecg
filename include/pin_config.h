#ifndef PIN_CONFIG_H
#define PIN_CONFIG_H

#include <Arduino.h>

#define ECG_PIN     34
#define LO_PLUS     33
#define LO_MINUS    32
#define BUZZER_PIN  25

#ifndef LED_BUILTIN
  #define LED_BUILTIN 2
#endif

#endif