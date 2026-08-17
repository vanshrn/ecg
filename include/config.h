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
constexpr int SPS = 125;
constexpr unsigned long SAMPLE_INTERVAL_US = 8000; // 125 SPS timing

// DSP Filter Constants
constexpr float EMA_ALPHA = 0.39f;   // Recalculated for ~12.5Hz Low-Pass cutoff at 125 SPS
constexpr float HP_ALPHA = 0.988f;   // Recalculated for ~0.23Hz High-Pass cutoff at 125 SPS

// System Cooldown Timers
constexpr unsigned long ALERT_COOLDOWN_MS = 2000;
constexpr unsigned long NORMAL_PRINT_INTERVAL_MS = 2000;
constexpr unsigned long BUZZER_COOLDOWN_MS = 1500;

#endif