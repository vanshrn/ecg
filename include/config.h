#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// User & Device Identity
extern const char* USER_ID;
extern const char* DEVICE_ID;

// Network Configurations
extern const char* WIFI_SSID;
extern const char* WIFI_PASSWORD;
extern const char* API_ENDPOINT;

// System Configurations
constexpr int SPS = 360;
constexpr unsigned long SAMPLE_INTERVAL_US = 2777; // 360 SPS timing

// DSP Filter Constants
constexpr float EMA_ALPHA = 0.22f;
constexpr float HP_ALPHA = 0.996f;

// System Cooldown Timers
constexpr unsigned long ALERT_COOLDOWN_MS = 2000;
constexpr unsigned long NORMAL_PRINT_INTERVAL_MS = 2000;
constexpr unsigned long BUZZER_COOLDOWN_MS = 1500;

#endif