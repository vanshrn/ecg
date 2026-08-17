#include "spandan.h"
#include <Arduino.h>
#include "config.h"

#define RR_HIST_LEN 8
static int spandan_rrHistory[RR_HIST_LEN] = {0, 0, 0, 0, 0, 0, 0, 0};
static int spandan_rrHistIdx = 0;
int spandan_totalBeatsDetected = 0;

String spandan_currentSeverity = "NORMAL";
String spandan_currentDiagnosis = "Normal Sinus Rhythm";
SpandanFeatures spandan_features;

static unsigned long spandan_lastBeatTimeUs = 0;
static unsigned long spandan_lastAlertTime = 0;
static float spandan_runningAvgRR = 800.0f;
static float spandan_dynamicThreshold = 2048.0f;
static bool spandan_peakLockout = false;
static int spandan_consecutivePVCs = 0;
static int spandan_consecutivePACs = 0;

// Ring buffer for morphological analysis
#define BUF_SIZE 1024 // ~2.8 seconds at 125Hz
static int beat_buffer[BUF_SIZE];
static int buf_idx = 0;
static int spandan_globalSampleIdx = 0;

// State machine for deferred analysis
static bool analysis_pending = false;
static int analysis_r_idx = 0;
static unsigned long analysis_r_time = 0;
static int samples_since_r = 0;

void resetSpandanFilters(int rawSample, unsigned long nowUs) {
  spandan_lastBeatTimeUs = 0;
  spandan_currentSeverity = "NORMAL";
  spandan_currentDiagnosis = "Normal Sinus Rhythm";
  spandan_runningAvgRR = 800.0f;

  for (int i = 0; i < RR_HIST_LEN; i++) spandan_rrHistory[i] = 0;
  spandan_rrHistIdx = 0;
  spandan_totalBeatsDetected = 0;
  spandan_globalSampleIdx = 0;
  buf_idx = 0;
  
  spandan_dynamicThreshold = 2048.0;
  spandan_peakLockout = false;
  spandan_consecutivePVCs = 0;
  spandan_consecutivePACs = 0;
  
  analysis_pending = false;
  samples_since_r = 0;
  for(int i=0; i<BUF_SIZE; i++) beat_buffer[i] = 2048;
  
  Serial.println("[SPANDAN INFO] Advanced Spandan detector active.");
}

// Helper to safely read from ring buffer (0 = oldest, BUF_SIZE-1 = newest)
int getBufVal(int absolute_idx) {
  int actual = absolute_idx % BUF_SIZE;
  if(actual < 0) actual += BUF_SIZE;
  return beat_buffer[actual];
}

void classifySpandanECG(SpandanFeatures feat) {
  spandan_currentDiagnosis = "Normal Sinus Rhythm";
  spandan_currentSeverity = "NORMAL";

  bool is_st_elev = feat.stSegment > 80;
  bool is_st_dep = feat.stSegment < -40;
  bool is_t_inv = feat.tAmp < -30;
  bool is_path_q = feat.qAmp < -80;
  
  if (feat.bpm == 0) {
    spandan_currentDiagnosis = "Asystole / Arrest"; spandan_currentSeverity = "CRITICAL";
  }
  else if (feat.bpm >= 165) {
    spandan_currentDiagnosis = "SVT"; spandan_currentSeverity = "CRITICAL";
  }
  else if (feat.bpm >= 145) {
    spandan_currentDiagnosis = "Atrial Flutter"; spandan_currentSeverity = "WARNING";
  }
  else if (feat.isIrregular && !feat.pWavePresent && feat.bpm > 60) {
    spandan_currentDiagnosis = "Atrial Fibrillation"; spandan_currentSeverity = "WARNING";
  }
  else if (feat.bpm >= 135 && feat.pWavePresent) {
    spandan_currentDiagnosis = "Atrial Tachycardia"; spandan_currentSeverity = "WARNING";
  }
  else if (feat.bpm > 0 && feat.bpm <= 38) {
    spandan_currentDiagnosis = "High AV BLOCK / 3rd Degree"; spandan_currentSeverity = "CRITICAL";
  }
  else if (feat.consecutivePVCs >= 1) {
    spandan_currentDiagnosis = "Ventricular Ectopics"; spandan_currentSeverity = "WARNING";
  }
  else if (feat.consecutivePACs >= 1) {
    spandan_currentDiagnosis = "Atrial Ectopics"; spandan_currentSeverity = "WARNING";
  }
  else if (feat.pWavePresent && feat.prInterval > 220) {
    spandan_currentDiagnosis = "AV BLOCK"; spandan_currentSeverity = "WARNING";
  }
  else if (feat.isWide && feat.prInterval < 120 && feat.pWavePresent) {
    spandan_currentDiagnosis = "WPW Syndrome"; spandan_currentSeverity = "WARNING";
  }
  else if (is_st_elev) {
    if (is_path_q && is_t_inv) spandan_currentDiagnosis = "Inferior Lateral MI";
    else if (is_path_q) spandan_currentDiagnosis = "Inferior Wall MI";
    else if (is_t_inv) spandan_currentDiagnosis = "Antero Lateral MI";
    else if (feat.rAmp > 650) spandan_currentDiagnosis = "Antero Apical MI";
    else if (feat.sAmp < -300) spandan_currentDiagnosis = "Lateral Wall MI";
    else spandan_currentDiagnosis = "Antero Septal MI";
    spandan_currentSeverity = "CRITICAL";
  }
  else if (feat.isWide && feat.tAmp < -30) {
    spandan_currentDiagnosis = "Left Bundle Branch Block"; spandan_currentSeverity = "WARNING";
  }
  else if (feat.isWide && feat.tAmp >= -30 && feat.sAmp < -60) {
    spandan_currentDiagnosis = "Right Bundle Branch Block"; spandan_currentSeverity = "WARNING";
  }
  else if (feat.rAmp > 800) {
    spandan_currentDiagnosis = "Left Ventricular Hypertrophy"; spandan_currentSeverity = "WARNING";
  }
  else if (feat.sAmp < -250) {
    spandan_currentDiagnosis = "Right Ventricular Hypertrophy"; spandan_currentSeverity = "WARNING";
  }
  else if (is_path_q && is_t_inv && !is_st_dep) {
    spandan_currentDiagnosis = "Evolved / Old MI"; spandan_currentSeverity = "WARNING";
  }
  else if (is_st_dep || is_t_inv) {
    spandan_currentDiagnosis = "Ischaemic ST-T changes"; spandan_currentSeverity = "WARNING";
  }
  else if (feat.bpm > 100 && feat.pWavePresent) {
    spandan_currentDiagnosis = "Sinus Tachycardia"; spandan_currentSeverity = "WARNING";
  }
  else if (feat.bpm > 40 && feat.bpm < 60 && !feat.pWavePresent) {
    spandan_currentDiagnosis = "Junctional Rythm"; spandan_currentSeverity = "WARNING";
  }
  else if (feat.bpm > 0 && feat.bpm < 55 && feat.pWavePresent) {
    spandan_currentDiagnosis = "Sinus Bradycardia"; spandan_currentSeverity = "WARNING";
  }
  
  // Output after EVERY beat (one interval) as requested
  unsigned long nowMs = millis();
  
  if (spandan_currentSeverity != "NORMAL") {
    Serial.print("[SPANDAN ALERT @ ");
    Serial.print(nowMs / 1000);
    Serial.print("s] ");
    Serial.print(spandan_currentSeverity);
    Serial.print(" - ");
    Serial.print(spandan_currentDiagnosis);
    Serial.print(" | BPM:");
    Serial.println(feat.bpm, 0);
  }
}

void printWaveformMetricsToSerial(unsigned long seq, const SpandanFeatures &feat) {
    char buf[512];
    snprintf(buf, sizeof(buf),
        "\n==================== WAVEFORM METRICS ===================\n"
        "Sequence Frame      : #%lu\n"
        "1. PR Interval      : %d ms\n"
        "2. QRS Width        : %d ms\n"
        "3. QT Interval      : %d ms\n"
        "4. QTc Interval     : %d ms\n"
        "5. ST Segment Amp   : %.0f ADC\n"
        "6. T-Wave Amp       : %.0f ADC\n"
        "7. R-Peak Amp       : %.0f ADC\n"
        "=========================================================\n",
        seq,
        feat.prInterval,
        feat.qrsWidth,
        feat.qtInterval,
        feat.qtcInterval,
        feat.stSegment,
        feat.tAmp,
        feat.rAmp
    );
    Serial.print(buf);
}

void analyzeBeat() {
  // analysis_r_idx is the THRESHOLD CROSSING point.
  // The true R-peak is a local maximum slightly after the crossing.
  // Scan forward up to 40ms (14 samples) to find the true R peak.
  // Increase to 80ms to ensure we don't fall short if we trigger early on a WPW Delta Wave
  int search_r_samples = (80 * SPS) / 1000;
  float true_r_amp = getBufVal(analysis_r_idx) - 2048.0;
  int true_r_idx = analysis_r_idx;
  for(int i = 1; i <= search_r_samples; i++) {
    float val = getBufVal(analysis_r_idx + i) - 2048.0;
    if (val > true_r_amp) {
      true_r_amp = val;
      true_r_idx = analysis_r_idx + i;
    }
  }
  
  // Now we use true_r_idx as the absolute reference for everything!
  analysis_r_idx = true_r_idx;
  spandan_features.rAmp = true_r_amp;
  
  // Q Amp (min in 60ms before R)
  int search_q_samples = (60 * SPS) / 1000;
  float min_q = 0;
  int q_idx = analysis_r_idx;
  for(int i=1; i<=search_q_samples; i++) {
    float val = getBufVal(analysis_r_idx - i) - 2048.0;
    if(val < min_q) { min_q = val; q_idx = analysis_r_idx - i; }
  }
  spandan_features.qAmp = min_q;
  
  // S Amp (min in 80ms after R)
  int search_s_samples = (80 * SPS) / 1000;
  float min_s = 0;
  int s_idx = analysis_r_idx;
  for(int i=1; i<=search_s_samples; i++) {
    float val = getBufVal(analysis_r_idx + i) - 2048.0;
    if(val < min_s) { min_s = val; s_idx = analysis_r_idx + i; }
  }
  spandan_features.sAmp = min_s;
  
  // QRS Width
  int qrs_start = q_idx;
  while(qrs_start < analysis_r_idx && (getBufVal(qrs_start) - 2048.0) > -15 && (getBufVal(qrs_start) - 2048.0) < 15) qrs_start++;
  int qrs_end = s_idx;
  while(qrs_end > analysis_r_idx && (getBufVal(qrs_end) - 2048.0) > -15 && (getBufVal(qrs_end) - 2048.0) < 15) qrs_end--;
  
  spandan_features.qrsWidth = ((s_idx - q_idx) * 1000) / SPS;
  spandan_features.isWide = (spandan_features.qrsWidth >= 100);
  
  // ST Segment (measure 60ms after S wave)
  int st_measure_idx = s_idx + ((60 * SPS) / 1000);
  spandan_features.stSegment = getBufVal(st_measure_idx) - 2048.0;
  
  // T wave (max absolute value between 120ms and 300ms after R)
  int t_start = analysis_r_idx + ((120 * SPS) / 1000);
  int t_end = analysis_r_idx + ((300 * SPS) / 1000);
  float max_t = 0;
  int t_peak_idx = t_start;
  for(int i=t_start; i<=t_end; i++) {
    float val = getBufVal(i) - 2048.0;
    if(abs(val) > abs(max_t)) {
        max_t = val;
        t_peak_idx = i;
    }
  }
  spandan_features.tAmp = max_t;
  
  // Find End of T-wave for QT Interval
  int t_end_idx = t_peak_idx;
  int max_t_search = t_peak_idx + ((120 * SPS) / 1000);
  while(t_end_idx < max_t_search) {
    float val = getBufVal(t_end_idx) - 2048.0;
    if(abs(val) < 15.0) break;
    t_end_idx++;
  }
  spandan_features.qtInterval = ((t_end_idx - q_idx) * 1000) / SPS;
  
  // Calculate QTc (Bazett's Formula: QTc = QT / sqrt(RR_in_seconds))
  if (spandan_features.rrInterval > 0) {
      float rr_seconds = spandan_features.rrInterval / 1000.0f;
      spandan_features.qtcInterval = (int)(spandan_features.qtInterval / sqrt(rr_seconds));
  } else {
      spandan_features.qtcInterval = 0;
  }
  
  // P wave (max in 400ms to 60ms before R)
  int p_start = analysis_r_idx - ((400 * SPS) / 1000);
  int current_rr_samples = (spandan_features.rrInterval * SPS) / 1000;
  if (current_rr_samples > 0 && current_rr_samples < ((500 * SPS) / 1000)) {
    p_start = analysis_r_idx - ((180 * SPS) / 1000); // Narrow search for tachycardia
  }
  
  int p_end = analysis_r_idx - ((60 * SPS) / 1000);
  float max_p = 0;
  int p_peak_idx = p_start;
  for(int i=p_start; i<=p_end; i++) {
    float val = getBufVal(i) - 2048.0;
    if(val > max_p) { max_p = val; p_peak_idx = i; }
  }
  
  spandan_features.pWavePresent = (max_p > 35.0);
  if (spandan_features.pWavePresent) {
    spandan_features.prInterval = ((analysis_r_idx - p_peak_idx) * 1000) / SPS;
  } else {
    spandan_features.prInterval = 0;
  }
  
  // PVC / PAC Logic
  bool isPremature = (spandan_features.rrInterval < spandan_runningAvgRR * 0.85);
  // Wait until we have established a real running average (not just the initial 800ms)
  if (spandan_totalBeatsDetected > 3) {
    if (isPremature && spandan_features.isWide) {
      spandan_consecutivePVCs++;
      spandan_consecutivePACs = 0;
    } else if (isPremature && !spandan_features.isWide) {
      spandan_consecutivePACs++;
      spandan_consecutivePVCs = 0;
    } else {
      spandan_consecutivePVCs = 0;
      spandan_consecutivePACs = 0;
    }
  }
  spandan_features.consecutivePVCs = spandan_consecutivePVCs;
  spandan_features.consecutivePACs = spandan_consecutivePACs;
  
  classifySpandanECG(spandan_features);
}

void processSpandanFeatures(int filteredVal, unsigned long nowUs) {
  beat_buffer[buf_idx] = filteredVal;
  buf_idx = (buf_idx + 1) % BUF_SIZE;
  spandan_globalSampleIdx++;
  
  spandan_dynamicThreshold = (0.99 * spandan_dynamicThreshold) + (0.01 * 2048.0);
  float peakTrigger = spandan_dynamicThreshold + 150.0f;

  // Strict time-based lockout: 250ms after the last beat
  // Calculate exact theoretical time based on sample count to avoid USB jitter
  unsigned long exactNowUs = (unsigned long)((spandan_globalSampleIdx * 1000000ULL) / (unsigned long long)SPS);
  
  if (spandan_lastBeatTimeUs > 0 && (exactNowUs - spandan_lastBeatTimeUs < 250000)) {
    spandan_peakLockout = true;
  } else {
    spandan_peakLockout = false;
  }

  if (filteredVal > peakTrigger && !spandan_peakLockout) {
    if (spandan_lastBeatTimeUs > 0) {
      unsigned long rrUs = exactNowUs - spandan_lastBeatTimeUs;
      if (rrUs >= 250000 && rrUs <= 2500000) {
        if (spandan_totalBeatsDetected == 0) {
          spandan_totalBeatsDetected++;
          spandan_lastBeatTimeUs = nowUs;
          spandan_dynamicThreshold = (float)filteredVal;
          return; // Skip calculating RR for the very first interval since it's just from boot
        }
        
        int rrMs = rrUs / 1000;
        spandan_features.rrInterval = rrMs;

        spandan_rrHistory[spandan_rrHistIdx] = rrMs;
        spandan_rrHistIdx = (spandan_rrHistIdx + 1) % RR_HIST_LEN;

        long sumRR = 0;
        int validBeats = 0;
        for (int i = 0; i < RR_HIST_LEN; i++) {
          if (spandan_rrHistory[i] > 0) { sumRR += spandan_rrHistory[i]; validBeats++; }
        }
        float smoothedRR = (validBeats > 0) ? (sumRR / (float)validBeats) : rrMs;
        spandan_features.bpm = 60000.0 / smoothedRR;

        float varSum = 0;
        for (int i = 0; i < RR_HIST_LEN; i++) varSum += abs(spandan_rrHistory[i] - smoothedRR);
        spandan_features.rrVariance = varSum / smoothedRR;
        spandan_totalBeatsDetected++;
        spandan_features.isIrregular = (spandan_totalBeatsDetected >= RR_HIST_LEN) && (spandan_features.rrVariance > 0.15);

        spandan_runningAvgRR = smoothedRR;

      if (!analysis_pending) {
        // Trigger deferred analysis
        analysis_pending = true;
        analysis_r_idx = spandan_globalSampleIdx - 1; // Use absolute global index
        analysis_r_time = exactNowUs;
        samples_since_r = 0;
      }
      }
    }
    spandan_dynamicThreshold = (float)filteredVal;
    spandan_lastBeatTimeUs = exactNowUs;
  }
  
  if (analysis_pending) {
    samples_since_r++;
    // Wait until we have 300ms of data AFTER the R-peak to analyze S, ST, and T waves
    if (samples_since_r >= (300 * SPS) / 1000) {
      analyzeBeat();
      analysis_pending = false;
    }
  }
}
