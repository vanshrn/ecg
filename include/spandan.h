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
  int     qrsWidth;
  float   qAmp;
  float   rAmp;
  float   sAmp;
  float   stSegment;
  float   tAmp;
  int     consecutivePVCs;
  int     consecutivePACs;
  bool    isWide;
};

void resetSpandanFilters(int rawSample, unsigned long nowUs);
void processSpandanFeatures(int filteredVal, unsigned long nowUs);

#endif
