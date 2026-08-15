// #ifndef ANALYTICS_EVALUATOR_H
// #define ANALYTICS_EVALUATOR_H

// #include <Arduino.h>

// struct PerformanceMetrics
// {
//     float snrDb = 0.0;               // 1. Waveform Accuracy (SNR)
//     float rPeakAccuracy = 0.0;       // 2. R-Peak Detection Accuracy (%)
//     float hrBpm = 0.0;               // 3. Heart Rate (BPM)
//     float baselineWanderMv = 0.0;    // 4a. Baseline Wander (mV)
//     float cmrrEstDb = 86.0;          // 4b. CMRR (dB)
//     float motionArtifactIndex = 0.0; // 5. Motion Artifact Index
// };

// PerformanceMetrics calculateBatchMetrics(
//     const int *rawSignal,
//     const int *cleanSignal,
//     int length,
//     float currentBpm,
//     int peakCount);

// void printMetricsToSerial(unsigned long seq, const PerformanceMetrics &metrics);

// #endif // ANALYTICS_EVALUATOR_H

#ifndef ANALYTICS_EVALUATOR_H
#define ANALYTICS_EVALUATOR_H

#include <Arduino.h>

struct PerformanceMetrics
{
    // 1. Waveform SNR & Accuracy
    float snrDb = 0.0;
    float snrAccuracy = 0.0; // SNR Accuracy (%)

    // 2. R-Peak Detection Accuracy
    float rPeakAccuracy = 0.0; // R-Peak Accuracy (%)

    // 3. Heart Rate & Accuracy
    float hrBpm = 0.0;
    float hrAccuracy = 0.0; // Heart Rate Accuracy (%)

    // 4. Baseline Wander, CMRR & Accuracy
    float baselineWanderMv = 0.0;
    float cmrrEstDb = 86.0;
    float baselineAccuracy = 0.0; // Baseline Wander Accuracy (%)

    // 5. Motion Artifact & Accuracy
    float motionArtifactIndex = 0.0;
    float motionAccuracy = 0.0; // Motion Artifact Accuracy (%)
};

PerformanceMetrics calculateBatchMetrics(
    const int *rawSignal,
    const int *cleanSignal,
    int length,
    float currentBpm,
    int peakCount);

void printMetricsToSerial(unsigned long seq, const PerformanceMetrics &metrics);

#endif // ANALYTICS_EVALUATOR_H