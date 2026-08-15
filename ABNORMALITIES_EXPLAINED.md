# ECG Abnormalities Explained

This document provides a clinical and algorithmic breakdown of every abnormality detected by the ESP32 ECG Monitor state machine. The abnormalities are ordered roughly by their origin in the heart (Sinus Node -> Atria -> AV Node -> Ventricles) and their severity.

---

## 1. Sinus Node Rhythms (The Natural Pacemaker)

### Normal Sinus Rhythm (NORMAL)
- **Clinical:** The heart is beating at a normal, healthy rate (60-100 BPM) with regular intervals and a visible P-wave before every QRS complex.
- **Algorithm:** `60 <= BPM <= 100`, regular RR intervals, P-wave present, narrow QRS.

### Sinus Arrhythmia (INFO)
- **Clinical:** A completely normal variation in heart rate that matches the patient's breathing cycle (speeds up slightly on inhale, slows down on exhale).
- **Algorithm:** `60 <= BPM <= 100`, P-wave present, narrow QRS, but RR variance is > 20% (irregular).

### Sinus Bradycardia (WARNING)
- **Clinical:** The sinus node is firing correctly, but at an unusually slow rate (< 60 BPM). Common in athletes or during sleep.
- **Algorithm:** `BPM < 50` (we use a stricter threshold to avoid false alarms), P-wave present, regular rhythm.

### Sinus Tachycardia (WARNING)
- **Clinical:** The sinus node is firing correctly, but at an unusually fast rate (> 100 BPM). Usually caused by exercise, stress, or fever.
- **Algorithm:** `BPM > 100`, P-wave present. It ramps up smoothly, unlike Atrial Tachycardia.

### Sinus Pause (WARNING)
- **Clinical:** The sinus node randomly skips a beat or pauses temporarily before resuming normal function. 
- **Algorithm:** The time between two beats (RR gap) exceeds 2.0 seconds.

### Sinus Arrest (CRITICAL)
- **Clinical:** The sinus node completely stops firing for an extended period. If an escape rhythm doesn't take over, the patient will faint.
- **Algorithm:** The time between two beats (RR gap) exceeds 3.0 seconds.

### Asystole (CRITICAL)
- **Clinical:** "Flatline." Complete failure of the heart's electrical system.
- **Algorithm:** The time between two beats (RR gap) exceeds 4.0 seconds, and the rolling BPM falls to 0.

---

## 2. Atrial Rhythms (Upper Chambers)

### PAC / Supraventricular Ectopic (WARNING)
- **Clinical:** A Premature Atrial Contraction (PAC). An irritable spot in the atria fires an electrical signal *before* the sinus node is ready.
- **Algorithm:** A beat arrives early (RR < 85% of baseline), but the QRS is narrow (proving the signal still traveled normally down the AV node).

### Atrial Bigeminy & Trigeminy (WARNING)
- **Clinical:** PACs that occur in a fixed repeating pattern. Bigeminy = Every 2nd beat is a PAC. Trigeminy = Every 3rd beat is a PAC.
- **Algorithm:** The RR history array matches a `short-long-short-long` (Bigeminy) or `normal-short-long` (Trigeminy) pattern, with narrow QRS complexes.

### Atrial Tachycardia (WARNING)
- **Clinical:** An irritable spot in the atria suddenly takes over as the pacemaker, driving the heart at a fast rate.
- **Algorithm:** `BPM > 100`, P-waves present, but the rate jumped *suddenly* (current RR interval is < 75% of the previous RR interval).

### SVT / Supraventricular Tachycardia (WARNING)
- **Clinical:** A generic term for a dangerously fast rhythm originating above the ventricles (often > 160 BPM). P-waves are usually moving so fast they are hidden inside the previous beat's T-wave.
- **Algorithm:** `BPM >= 160`, narrow QRS, P-waves completely hidden/undetectable.

### Atrial Flutter (WARNING)
- **Clinical:** The atria are caught in an electrical loop, firing at ~300 BPM (creating a "sawtooth" baseline). The AV node blocks most of them, letting only every 2nd or 3rd beat through to the ventricles.
- **Algorithm:** `130 <= BPM < 160`, narrow QRS, regular rhythm, no distinct normal P-waves detected.

### Atrial Fibrillation (WARNING)
- **Clinical:** The atria are quivering chaotically instead of beating. The AV node is bombarded with signals and lets them through randomly, creating an "irregularly irregular" pulse.
- **Algorithm:** Highly irregular RR variance, narrow QRS, completely absent P-waves.

---

## 3. AV Blocks & Conduction (The Middle Gateway)

### AV Block 1st Degree (WARNING)
- **Clinical:** The electrical signal is delayed at the AV node, but every signal eventually makes it through. 
- **Algorithm:** The PR interval (time from P-wave to QRS) consistently exceeds 200ms across multiple beats.

### AV Block 2nd Degree - Mobitz I / Wenckebach (WARNING)
- **Clinical:** The delay at the AV node gets longer and longer with every beat, until a beat is finally completely blocked (dropped).
- **Algorithm:** The algorithm detects a dropped beat (a sudden gap 1.6x to 2.4x longer than the baseline RR), AND the PR intervals of the preceding beats were strictly increasing.

### AV Block 2nd Degree - Mobitz II (CRITICAL)
- **Clinical:** The AV node randomly and unexpectedly drops beats without any warning or prior delay. High risk of progressing to complete heart block.
- **Algorithm:** A dropped beat (gap 1.6x to 2.4x longer than baseline RR), but the preceding PR intervals were stable/constant.

### AV Block 3rd Degree / Complete Heart Block (CRITICAL)
- **Clinical:** The atria and ventricles are completely electrically severed. The atria fire at their normal rate (P-waves), while the ventricles fire at their own incredibly slow "escape" rate (~40 BPM) to keep the patient alive.
- **Algorithm:** A perfectly regular, slow ventricular rate (< 50 BPM) with P-waves detected randomly in the background (dissociated).

### Junctional Rhythm (WARNING)
- **Clinical:** Similar to 3rd Degree Block (ventricles pacing themselves at ~40-60 BPM), but the sinus node in the atria is completely dead, so there are zero P-waves anywhere.
- **Algorithm:** A perfectly regular, slow ventricular rate, but the P-wave detector finds absolutely zero P-waves anywhere in the 1.5-second heartbeat cycle.

### Wolff-Parkinson-White (WPW) (WARNING)
- **Clinical:** An extra electrical pathway (Bundle of Kent) connects the atria and ventricles, bypassing the AV node. This causes the ventricles to depolarize early, forming a "Delta wave" (slurred QRS upstroke) and a very short PR interval.
- **Algorithm:** The P-wave is present, but the measured PR interval is critically short (≤ 120ms), and the QRS complex is widened (≥ 100ms) by the Delta wave.

---

## 4. Ventricular Rhythms (Lower Chambers)

### Ventricular Ectopic / PVC (WARNING)
- **Clinical:** A Premature Ventricular Contraction. An irritable spot in the ventricles fires wildly before the normal signal arrives.
- **Algorithm:** A beat arrives early (RR < 85% of baseline) AND the QRS complex is abnormally wide (> 120ms), because the signal did not use the fast electrical highways.

### Ventricular Couplets (CRITICAL)
- **Clinical:** Two PVCs in a row. Very dangerous, as it shows high ventricular irritability.
- **Algorithm:** Two consecutive beats are flagged as wide and premature.

### Ventricular Bigeminy & Trigeminy (CRITICAL)
- **Clinical:** PVCs occurring in a fixed repeating pattern. Bigeminy = Every 2nd beat is a PVC. Trigeminy = Every 3rd beat is a PVC.
- **Algorithm:** Pattern matching on RR history intervals, but specifically requiring the premature beats to have wide QRS complexes.

### Non-Sustained VT (NSVT) (CRITICAL)
- **Clinical:** A run of 3 or more PVCs in a row that stops on its own. A major warning sign for sudden cardiac arrest.
- **Algorithm:** 3 or more consecutive wide, premature beats.

### Ventricular Tachycardia (V-Tach) (CRITICAL)
- **Clinical:** The ventricles take over completely, firing at a dangerously fast rate (> 150 BPM). The heart cannot fill with blood properly. This is a medical emergency.
- **Algorithm:** `BPM >= 150`, extremely wide QRS complexes, regular rhythm.

### Ventricular Fibrillation (V-Fib) (CRITICAL)
- **Clinical:** The ventricles are quivering chaotically. The patient has no pulse and is in cardiac arrest. Requires immediate CPR and defibrillation.
- **Algorithm:** `BPM >= 150`, wide QRS complexes, highly irregular/chaotic RR intervals.
