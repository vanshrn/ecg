#ifndef ECG_PROCESSOR_H
#define ECG_PROCESSOR_H

#include <Arduino.h>

struct ECGFeatures {
  float bpm = 0;
  int rrInterval = 0;
  float rrVariance = 0.0;
  bool isIrregular = false;
  bool pWavePresent = false;
  int prInterval = 0;
  int qrsWidth = 0;            // real time-domain measurement (ms)
  int consecutivePVCs = 0;
  int consecutivePACs = 0;     // new: tracks consecutive premature atrial complexes
};

// Extern State Variables (Non-const)
extern bool isLiveMode;
extern bool wasOff;
extern bool currentLeadsOff;
extern int leadOffConsecutiveCounter;
extern String currentSeverity;
extern String currentDiagnosis;
extern ECGFeatures features;

extern float emaValue;
extern float hpPrevRaw, hpPrevOut;
extern float notch_x1, notch_x2, notch_y1, notch_y2;

extern unsigned long lastAlertTime;
extern unsigned long lastBuzzerAlertTime;

// Core Signal Processing Functions
int readOversampled(int pin, int samples);
float applyNotch(float x);
void classifyECG(ECGFeatures feat);
void processBeatFeatures(int filteredVal, unsigned long nowUs);
void resetECGFilters(int rawSample, unsigned long nowUs);

#endif