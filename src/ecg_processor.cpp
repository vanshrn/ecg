#include "ecg_processor.h"
#include "pin_config.h"
#include "config.h"
#include "buzzer.h"
#include <Arduino.h>

/* =====================================================================================
   HEADER (ecg_processor.h) ADDITIONS REQUIRED
   -------------------------------------------------------------------------------------
   Add these fields to your ECGFeatures struct (existing fields kept):

     struct ECGFeatures {
       float   bpm;
       int     rrInterval;
       float   rrVariance;
       bool    isIrregular;
       bool    pWavePresent;
       int     prInterval;
       int     qrsWidth;          // now a REAL time-domain measurement (ms)
       int     consecutivePVCs;   // now actually maintained
       int     consecutivePACs;   // new
     };

   Nothing else in the public header needs to change - all new state below is
   file-local (static) to ecg_processor.cpp.
   ===================================================================================== */

// ---------------------------------------------------------------------------
// DSP Variable Definitions (unchanged)
// ---------------------------------------------------------------------------
float emaValue = 2048.0;
float hpPrevRaw = 2048.0, hpPrevOut = 0.0;

float notch_x1 = 0, notch_x2 = 0, notch_y1 = 0, notch_y2 = 0;
const float notch_b0 = 0.9630, notch_b1 = -1.2381, notch_b2 = 0.9630;
const float notch_a1 = -1.2381, notch_a2 = 0.9260;

bool wasOff = false;
bool currentLeadsOff = false;
int leadOffConsecutiveCounter = 0;

// ---------------------------------------------------------------------------
// RR history - widened to 8 beats for more reliable pattern detection,
// and now accessed ONLY through getRR() to fix the circular-buffer bug.
// ---------------------------------------------------------------------------
#define RR_HIST_LEN 8
int rrHistory[RR_HIST_LEN] = {800, 800, 800, 800, 800, 800, 800, 800};
int rrHistIdx = 0;

// Returns the RR interval `beatsAgo` beats back. 0 = most recent beat.
int getRR(int beatsAgo) {
  int idx = ((rrHistIdx - 1 - beatsAgo) % RR_HIST_LEN + RR_HIST_LEN) % RR_HIST_LEN;
  return rrHistory[idx];
}

String currentSeverity = "NORMAL";
String currentDiagnosis = "Normal Sinus Rhythm";

ECGFeatures features;

unsigned long lastBeatTimeUs = 0;
unsigned long lastPWaveTimeUs = 0;
float dynamicThreshold = 2048.0;
bool peakLockout = false;

// ---------------------------------------------------------------------------
// New state for QRS-width timing, PVC/PAC tracking, and AV-block/pause logic
// ---------------------------------------------------------------------------
#define WIDE_QRS_MS            100     // >=100ms QRS is considered "wide" (ventricular)
#define PREMATURE_RATIO        0.85f   // beat is "premature" if RR < 0.85 * running avg
#define SINUS_PAUSE_MS         2200UL  // >2.2s gap -> Sinus Pause
#define SINUS_ARREST_MS        3000UL  // >3.0s gap -> Sinus Arrest
#define ASYSTOLE_MS            4000UL  // >4.0s gap -> Asystole
#define PROLONGED_PR_MS        200     // classic 1st-degree AV block cutoff
#define PROLONGED_PR_PERSIST   3       // consecutive beats required before declaring it
#define QRS_ONSET_OFFSET        55.0f  // amplitude above dynamicThreshold that marks QRS onset/offset
#define P_WAVE_LOW_OFFSET       15.0f
#define P_WAVE_HIGH_OFFSET      45.0f
#define AFLUTTER_MAX_VARIANCE   0.05f  // extremely metronomic -> more flutter-like
#define SVT_MAX_VARIANCE        0.15f  // regular but not metronomic -> more SVT-like
#define ONSET_JUMP_RATIO        0.6f   // RR drops by >40% within 2 beats -> "abrupt" onset (atrial tach)

static bool qrsInProgress = false;
static unsigned long qrsStartUs = 0;
static float latchedQrsEndLevel = 0;
static bool beatPending = false;          // a peak was detected, waiting for QRS offset to finalize+classify
static bool pWaveDetectedThisCycle = false;

static int  consecutivePVCs = 0;
static int  consecutivePACs = 0;

static float runningAvgRR = 800.0f;       // slow-moving "normal beat" RR average, excludes ectopics/pauses
static int   prHistory[3] = {160, 160, 160};
static int   prHistIdx = 0;
static bool  prTrendIncreasing = false;
static int   prolongedPRCount = 0;
int   totalBeatsDetected = 0;

// ---------------------------------------------------------------------------
void applyNotchInit() {} // placeholder kept for header compatibility if referenced elsewhere

float applyNotch(float x) {
  float y = notch_b0 * x + notch_b1 * notch_x1 + notch_b2 * notch_x2
            - notch_a1 * notch_y1 - notch_a2 * notch_y2;
  notch_x2 = notch_x1; notch_x1 = x;
  notch_y2 = notch_y1; notch_y1 = y;
  return y;
}

int readOversampled(int pin, int samples) {
  long sum = 0;
  for (int i = 0; i < samples; i++) sum += analogRead(pin);
  return (int)(sum / samples);
}

void resetECGFilters(int rawSample, unsigned long nowUs) {
  emaValue = rawSample;
  hpPrevRaw = rawSample;
  hpPrevOut = 0;
  notch_x1 = notch_x2 = notch_y1 = notch_y2 = 0;
  lastBeatTimeUs = nowUs;
  wasOff = false;
  currentSeverity = "NORMAL";
  currentDiagnosis = "Normal Sinus Rhythm";

  for (int i = 0; i < RR_HIST_LEN; i++) rrHistory[i] = 800;
  rrHistIdx = 0;
  qrsInProgress = false;
  beatPending = false;
  pWaveDetectedThisCycle = false;
  consecutivePVCs = 0;
  consecutivePACs = 0;
  runningAvgRR = 800.0f;
  for (int i = 0; i < 3; i++) prHistory[i] = 160;
  prHistIdx = 0;
  prTrendIncreasing = false;
  prolongedPRCount = 0;
  totalBeatsDetected = 0;

  Serial.println("[INFO] Monitoring active.");
}

// ---------------------------------------------------------------------------
// Pattern detectors - now use getRR() so they read the actual most-recent
// beats regardless of where rrHistIdx currently points (fixes the old bug).
// ---------------------------------------------------------------------------
bool rrHistory_pattern_bigeminy() {
  // short-normal-short-normal alternation, matching the ectopic count == 1 case
  return (getRR(0) < getRR(1) * PREMATURE_RATIO) &&
         (abs(getRR(1) - getRR(3)) < 60) &&
         (abs(getRR(0) - getRR(2)) < 60);
}

bool rrHistory_pattern_trigeminy() {
  // every 3rd beat premature: getRR(0) and getRR(3) both short
  // getRR(2) is the long compensatory pause, getRR(1) is the normal beat
  return (getRR(0) < getRR(1) * PREMATURE_RATIO) &&
         (getRR(3) < getRR(4) * PREMATURE_RATIO);
}

// ---------------------------------------------------------------------------
// Central classifier - severity-ordered, now covering every entry in SEVERITY
// ---------------------------------------------------------------------------
void classifyECG(ECGFeatures feat) {
  currentDiagnosis = "Normal Sinus Rhythm";
  currentSeverity = "NORMAL";

  unsigned long gapUs = (lastBeatTimeUs > 0) ? (micros() - lastBeatTimeUs) : micros();

  // ---- 1. EXTREME NO-BEAT CONDITIONS ----
  if (feat.bpm == 0 && gapUs > (ASYSTOLE_MS * 1000UL)) {
    currentDiagnosis = "Asystole"; currentSeverity = "CRITICAL";
  }
  else if (feat.bpm == 0 && gapUs > (SINUS_ARREST_MS * 1000UL)) {
    currentDiagnosis = "Sinus Arrest"; currentSeverity = "CRITICAL";
  }
  else if (feat.bpm == 0 && gapUs > (SINUS_PAUSE_MS * 1000UL)) {
    currentDiagnosis = "Sinus Pause"; currentSeverity = "WARNING";
  }

  // ---- 2. PATTERN-BASED RHYTHMS (Overrules isolated beats) ----
  else if (rrHistory_pattern_bigeminy()) {
    if (feat.qrsWidth >= WIDE_QRS_MS) { currentDiagnosis = "Ventricular Bigeminy"; currentSeverity = "CRITICAL"; }
    else { currentDiagnosis = "Atrial Bigeminy"; currentSeverity = "WARNING"; }
  }
  else if (rrHistory_pattern_trigeminy()) {
    if (feat.qrsWidth >= WIDE_QRS_MS) { currentDiagnosis = "Ventricular Trigeminy"; currentSeverity = "CRITICAL"; }
    else { currentDiagnosis = "Atrial Trigeminy"; currentSeverity = "WARNING"; }
  }

  // ---- 2. VENTRICULAR (Wide QRS) ----
  else if (feat.consecutivePVCs >= 3) {
    currentDiagnosis = "Non-Sustained VT (NSVT)"; currentSeverity = "CRITICAL";
  }
  else if (feat.qrsWidth >= WIDE_QRS_MS && feat.bpm >= 150) {
    if (feat.isIrregular) { currentDiagnosis = "Ventricular Fibrillation"; }
    else { currentDiagnosis = "Ventricular Tachycardia"; }
    currentSeverity = "CRITICAL";
  }
  else if (feat.consecutivePVCs == 2) {
    currentDiagnosis = "Ventricular Couplets"; currentSeverity = "CRITICAL";
  }
  else if (feat.consecutivePVCs == 1) {
    currentDiagnosis = "Ventricular Ectopic / PVC"; currentSeverity = "WARNING";
  }

  // ---- 3. AV BLOCK 3RD DEGREE (Complete Heart Block) / JUNCTIONAL ----
  // Must intercept slow, regular(ish) rhythms before AFib gets confused by the transition variance
  else if (getRR(0) > 1200 && getRR(0) < 2500 && getRR(1) > 1200 && getRR(1) < 2500 && abs(getRR(0) - getRR(1)) < 150 && feat.qrsWidth < WIDE_QRS_MS && !feat.pWavePresent) {
    if (!pWaveDetectedThisCycle) {
      currentDiagnosis = "Junctional Rhythm"; currentSeverity = "WARNING";
    } else {
      currentDiagnosis = "AV Block 3rd (Complete)"; currentSeverity = "CRITICAL";
    }
  }

  // ---- 4. ATRIAL / SUPRAVENTRICULAR (Narrow QRS, Abnormal P or Rate) ----
  else if (!feat.pWavePresent && feat.isIrregular && feat.qrsWidth < WIDE_QRS_MS) {
    currentDiagnosis = "Atrial Fibrillation"; currentSeverity = "WARNING";
  }
  else if (feat.bpm >= 130 && !feat.pWavePresent && feat.qrsWidth < WIDE_QRS_MS) {
    if (feat.bpm >= 160) { currentDiagnosis = "SVT"; }
    else { currentDiagnosis = "Atrial Flutter"; }
    currentSeverity = "WARNING";
  }
  else if (feat.bpm > 100 && feat.pWavePresent) {
    if (getRR(0) < (getRR(4) * ONSET_JUMP_RATIO)) { currentDiagnosis = "Atrial Tachycardia"; }
    else { currentDiagnosis = "Sinus Tachycardia"; }
    currentSeverity = "WARNING";
  }
  else if (feat.consecutivePACs >= 1) {
    currentDiagnosis = "PAC (Supraventricular Ectopic)"; currentSeverity = "WARNING";
  }

  // ---- 6. HEART BLOCKS (2nd & 1st Degree) ----
  else if (getRR(0) > (runningAvgRR * 1.6f) && getRR(0) < (runningAvgRR * 2.4f)) {
    if (prTrendIncreasing) {
      currentDiagnosis = "AV Block 2nd (Mobitz I)"; currentSeverity = "WARNING";
    } else {
      currentDiagnosis = "AV Block 2nd (Mobitz II)"; currentSeverity = "CRITICAL";
    }
  }
  else if (feat.pWavePresent && feat.prInterval > 0 && feat.prInterval <= 120 && feat.qrsWidth >= 90) {
    currentDiagnosis = "Wolff-Parkinson-White (WPW)"; currentSeverity = "WARNING";
  }
  else if (feat.pWavePresent && prolongedPRCount >= PROLONGED_PR_PERSIST && !prTrendIncreasing) {
    currentDiagnosis = "AV Block 1st (Prolonged PR)"; currentSeverity = "WARNING";
  }

  // ---- 6. SINUS ANOMALIES ----
  else if (feat.bpm > 0 && feat.bpm < 50 && feat.pWavePresent) {
    currentDiagnosis = "Sinus Bradycardia"; currentSeverity = "WARNING";
  }
  else if (feat.isIrregular && feat.pWavePresent && feat.bpm >= 60 && feat.bpm <= 100) {
    currentDiagnosis = "Sinus Arrhythmia"; currentSeverity = "INFO";
  }

  unsigned long nowMs = millis();
  static String lastDiagnosisStr = "";

  if (currentSeverity != "NORMAL") {
    bool isNewDiagnosis = (currentDiagnosis != lastDiagnosisStr);
    if (nowMs - lastAlertTime >= ALERT_COOLDOWN_MS || isNewDiagnosis) {
      lastAlertTime = nowMs;
      lastDiagnosisStr = currentDiagnosis;
      
      Serial.print("[ABNORMALITY ALERT @ ");
      Serial.print(nowMs / 1000);
      Serial.print("s] ");
      Serial.print(currentSeverity);
      Serial.print(" - ");
      Serial.print(currentDiagnosis);
      Serial.print(" | BPM: ");
      Serial.println(feat.bpm, 1);
    }

    if (nowMs - lastBuzzerAlertTime >= BUZZER_COOLDOWN_MS) {
      lastBuzzerAlertTime = nowMs;
      if (currentSeverity == "CRITICAL") {
        playCriticalAlert();
      } else if (currentSeverity == "WARNING") {
        playWarningAlert();
      }
    }
  }
}

// ---------------------------------------------------------------------------
// processBeatFeatures - called once per sample.
//
// Key change from the original: R-peak detection now only LATCHES the beat
// (timing, RR, rate) and sets beatPending=true. Classification is deferred
// until the QRS complex actually ends (down-crossing), at which point we
// have a REAL time-domain QRS width instead of a 2-level amplitude guess -
// and can decide PVC vs. PAC vs. normal before calling classifyECG().
// ---------------------------------------------------------------------------
void processBeatFeatures(int filteredVal, unsigned long nowUs) {
  dynamicThreshold = (0.985 * dynamicThreshold) + (0.015 * 2048.0);
  float peakTrigger    = dynamicThreshold + 100.0f;
  float qrsOnsetLevel  = dynamicThreshold + QRS_ONSET_OFFSET;
  float pWaveLowLevel  = 2048.0f + P_WAVE_LOW_OFFSET;
  float pWaveHighLevel = 2048.0f + P_WAVE_HIGH_OFFSET;

  // ---- QRS onset (rising edge, before the peak/lockout fires) ----
  if (!qrsInProgress && !peakLockout && filteredVal > qrsOnsetLevel) {
    qrsInProgress = true;
    qrsStartUs = nowUs;
    latchedQrsEndLevel = qrsOnsetLevel;
  }

  // ---- P wave window (before QRS onset, before lockout) ----
  unsigned long timeSinceLastBeat = (lastBeatTimeUs > 0) ? (nowUs - lastBeatTimeUs) : 0;
  
  // Timeout for P-wave if no QRS follows it (e.g., dropped beat in Wenckebach)
  if (pWaveDetectedThisCycle && !qrsInProgress && !peakLockout && (nowUs - lastPWaveTimeUs > 500000)) {
    pWaveDetectedThisCycle = false;
  }

  if (!peakLockout && !qrsInProgress && !pWaveDetectedThisCycle &&
      filteredVal > pWaveLowLevel && filteredVal < pWaveHighLevel &&
      timeSinceLastBeat > 220000) {
    lastPWaveTimeUs = nowUs;
    pWaveDetectedThisCycle = true;
  }

  // ---- R peak detection: latch timing/rate, defer full classification ----
  if (filteredVal > peakTrigger && !peakLockout) {
    if (lastBeatTimeUs > 0) {
      unsigned long rrUs = nowUs - lastBeatTimeUs;

      if (rrUs >= 300000 && rrUs <= 2000000) {
        int rrMs = rrUs / 1000;
        features.rrInterval = rrMs;

        rrHistory[rrHistIdx] = rrMs;
        rrHistIdx = (rrHistIdx + 1) % RR_HIST_LEN;

        long sumRR = 0;
        int validBeats = 0;
        for (int i = 0; i < RR_HIST_LEN; i++) {
          if (rrHistory[i] > 0) { sumRR += rrHistory[i]; validBeats++; }
        }
        float smoothedRR = (validBeats > 0) ? (sumRR / (float)validBeats) : rrMs;
        features.bpm = 60000.0 / smoothedRR;

        float varSum = 0;
        for (int i = 0; i < RR_HIST_LEN; i++) varSum += abs(rrHistory[i] - smoothedRR);
        features.rrVariance = varSum / smoothedRR;
        
        totalBeatsDetected++;
        // Only classify as irregular if we've actually recorded enough real beats to overwrite the fake 800ms pre-fill!
        features.isIrregular = (totalBeatsDetected >= RR_HIST_LEN) && (features.rrVariance > 0.20);

        features.pWavePresent = pWaveDetectedThisCycle &&
                                 (nowUs - lastPWaveTimeUs) < 300000 &&
                                 (nowUs - lastPWaveTimeUs) > 60000;
        features.prInterval = features.pWavePresent
                                 ? (int)((nowUs - lastPWaveTimeUs) / 1000)
                                 : 0;

        // Track PR trend (for AV block Mobitz I) only on non-premature, P-present beats
        bool isPrematureBeat = (rrMs < runningAvgRR * PREMATURE_RATIO);
        if (features.pWavePresent && !isPrematureBeat) {
          int oldestPR = prHistory[prHistIdx];
          int middlePR = prHistory[(prHistIdx + 1) % 3];
          int newestPR = prHistory[(prHistIdx + 2) % 3];
          prTrendIncreasing = (oldestPR < middlePR) && (middlePR < newestPR);

          prHistory[prHistIdx] = features.prInterval;
          prHistIdx = (prHistIdx + 1) % 3;

          if (features.prInterval > PROLONGED_PR_MS) {
            prolongedPRCount++;
          } else {
            prolongedPRCount = 0;
          }
        }
        
        // UPDATE AVG RR: 
        // 1. If it's a normal beat OR
        // 2. If consecutive beats are fast (tachycardia onset) so we don't get stuck forever
        bool isDroppedBeat = (rrMs > runningAvgRR * 1.5f);
        if ((!isPrematureBeat && !isDroppedBeat) || (abs(rrMs - rrHistory[(rrHistIdx - 2 + RR_HIST_LEN) % RR_HIST_LEN]) < 40)) {
          runningAvgRR = (0.85f * runningAvgRR) + (0.15f * rrMs);
        }

        beatPending = true; // qrsWidth + PVC/PAC decision happens at QRS offset below
      }
    }

    dynamicThreshold = (float)filteredVal;
    lastBeatTimeUs = nowUs;
    peakLockout = true;
  }

  // ---- QRS timeout (if triggered by a P-wave or noise but no QRS peak followed) ----
  if (qrsInProgress && !beatPending && (nowUs - qrsStartUs > 200000)) {
    qrsInProgress = false; // Reset falsely triggered QRS onset
  }

  // ---- End of QRS (falling edge or timeout AFTER peak) ----
  if (qrsInProgress && beatPending && !peakLockout) {
    if (filteredVal < latchedQrsEndLevel || (nowUs - qrsStartUs > 200000)) {
      unsigned long widthUs = nowUs - qrsStartUs;
      features.qrsWidth = (int)(widthUs / 1000);
      qrsInProgress = false;

      if (features.qrsWidth < 0 || features.qrsWidth > 300) {
        features.qrsWidth = 60; // fallback if messy
      }

      int rrMs = features.rrInterval;
      if (rrMs >= 300 && rrMs <= 2000) {
        // PVC/PAC logic
        bool isPremature = (features.rrInterval < runningAvgRR * PREMATURE_RATIO);
        bool isWide       = (features.qrsWidth >= WIDE_QRS_MS);

        if (isPremature && isWide) {
          consecutivePVCs++;
          consecutivePACs = 0;
        } else if (isPremature && !isWide) {
          consecutivePACs++;
          consecutivePVCs = 0;
        } else {
          consecutivePVCs = 0;
          consecutivePACs = 0;
        }

        features.consecutivePVCs = consecutivePVCs;
        features.consecutivePACs = consecutivePACs;

        classifyECG(features);
        beatPending = false;
      }
    }
  }

  // ---- lockout release, ready for next cycle ----
  if (peakLockout) {
    if (filteredVal < (dynamicThreshold - 80.0) || filteredVal < 2100) {
      peakLockout = false;
      pWaveDetectedThisCycle = false;
    }
  }

  // ---- No-beat tiers: only start timer after at least one beat has been seen ----
  unsigned long gapUs = nowUs - lastBeatTimeUs;
  if (lastBeatTimeUs > 0 && gapUs > (SINUS_PAUSE_MS * 1000UL) && !beatPending && !qrsInProgress) {
    features.bpm = 0;
    classifyECG(features);
  }
}