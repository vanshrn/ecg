#ifndef SPANDAN_H
#define SPANDAN_H

#include <Arduino.h>

struct SpandanFeatures {
  float   bpm;
  int     rrInterval;
  float   rrVariance;
  bool    isIrregular;
  bool    pWavePresent;
  int     prInterval;
  int     qrsWidth;          // real time-domain measurement (ms)
  int     qtInterval;        // QT interval (ms)
  int     qtcInterval;       // Corrected QT (Bazett's formula)
  float   qAmp;
  float   rAmp;
  float   sAmp;
  float   stSegment;
  float   tAmp;
  int     consecutivePVCs;   // tracks consecutive premature ventricular complexes
  int     consecutivePACs;   // tracks consecutive premature atrial complexes
  bool    isWide;
};

extern String spandan_currentSeverity;
extern String spandan_currentDiagnosis;
extern int spandan_totalBeatsDetected;
extern SpandanFeatures spandan_features;

void resetSpandanFilters(int rawSample, unsigned long nowUs);
void processSpandanFeatures(int filteredVal, unsigned long nowUs);
void printWaveformMetricsToSerial(unsigned long seq, const SpandanFeatures &feat);

#endif
