# Spandan ECG Abnormality Conditions

This document outlines the diagnostic criteria for various ECG abnormalities as implemented in `spandan.cpp` (`classifySpandanECG` function). The logic relies on extracted features such as BPM, RR Interval irregularity, P-wave presence, PR interval, QRS width, and the relative amplitudes of the Q, R, S, and T waves.

## Base Variables & Thresholds
Before evaluating specific conditions, the algorithm checks several basic morphological features based on amplitude (centered around a 2048 ADC baseline):
*   **ST Elevation (`is_st_elev`)**: `stSegment > +80`
*   **ST Depression (`is_st_dep`)**: `stSegment < -40`
*   **T-Wave Inversion (`is_t_inv`)**: `tAmp < -30`
*   **Pathological Q-Wave (`is_path_q`)**: `qAmp < -80`

## Diagnostic Hierarchy
The conditions are evaluated in a strict top-down order of precedence. The first condition that evaluates to `true` becomes the final diagnosis.

### 1. Rhythm & Rate Abnormalities
*   **Asystole / Arrest** (CRITICAL)
    *   Condition: `BPM == 0`
*   **SVT (Supraventricular Tachycardia)** (CRITICAL)
    *   Condition: `BPM >= 165`
*   **Atrial Flutter** (WARNING)
    *   Condition: `BPM >= 145` (and not caught by SVT)
*   **Atrial Fibrillation** (WARNING)
    *   Condition: `isIrregular == true` AND `pWavePresent == false` AND `BPM > 60`
*   **Atrial Tachycardia** (WARNING)
    *   Condition: `BPM >= 135` AND `pWavePresent == true`
*   **High AV BLOCK / 3rd Degree** (CRITICAL)
    *   Condition: `BPM > 0` AND `BPM <= 38`

### 2. Ectopics & Conduction Blocks
*   **Ventricular Ectopics (PVCs)** (WARNING)
    *   Condition: `consecutivePVCs >= 1` (Premature beat + Wide QRS)
*   **Atrial Ectopics (PACs)** (WARNING)
    *   Condition: `consecutivePACs >= 1` (Premature beat + Narrow QRS)
*   **AV BLOCK (1st/2nd Degree)** (WARNING)
    *   Condition: `pWavePresent == true` AND `prInterval > 220 ms`
*   **WPW Syndrome** (WARNING)
    *   Condition: `isWide == true` (QRS >= 100ms) AND `prInterval < 120 ms` AND `pWavePresent == true`

### 3. Myocardial Infarction (MI) Group
These are evaluated only if **ST Elevation (`stSegment > +80`)** is present (All are CRITICAL):
*   **Inferior Lateral MI**: Pathological Q (`qAmp < -80`) AND T-Inversion (`tAmp < -30`)
*   **Inferior Wall MI**: Pathological Q (`qAmp < -80`) only
*   **Antero Lateral MI**: T-Inversion (`tAmp < -30`) only
*   **Antero Apical MI**: Extremely high R-wave (`rAmp > +650`)
*   **Lateral Wall MI**: Deep S-wave (`sAmp < -300`)
*   **Antero Septal MI**: Default if ST Elevation is present but none of the above specific sub-conditions are met.

### 4. Bundle Branch Blocks & Hypertrophy
*   **Left Bundle Branch Block** (WARNING)
    *   Condition: `isWide == true` AND `tAmp < -30`
*   **Right Bundle Branch Block** (WARNING)
    *   Condition: `isWide == true` AND `tAmp >= -30` AND `sAmp < -60`
*   **Left Ventricular Hypertrophy** (WARNING)
    *   Condition: `rAmp > +800`
*   **Right Ventricular Hypertrophy** (WARNING)
    *   Condition: `sAmp < -250`

### 5. Ischemia & Minor Rhythm Issues
*   **Evolved / Old MI** (WARNING)
    *   Condition: Pathological Q (`qAmp < -80`) AND T-Inversion (`tAmp < -30`) AND NOT ST-Depression (`stSegment >= -40`)
*   **Ischaemic ST-T changes** (WARNING)
    *   Condition: ST-Depression (`stSegment < -40`) OR T-Inversion (`tAmp < -30`)
*   **Sinus Tachycardia** (WARNING)
    *   Condition: `BPM > 100` AND `pWavePresent == true`
*   **Junctional Rhythm** (WARNING)
    *   Condition: `40 < BPM < 60` AND `pWavePresent == false`
*   **Sinus Bradycardia** (WARNING)
    *   Condition: `0 < BPM < 55` AND `pWavePresent == true`

### Default State
If none of the above conditions evaluate to true, the system defaults to:
*   **Normal Sinus Rhythm** (NORMAL)
