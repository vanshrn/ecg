import pandas as pd
import numpy as np

def simulate_esp32_detection(csv_path):
    df = pd.read_csv(csv_path)
    raw_samples = df['Raw'].values
    
    # DSP Variables
    emaValue = 2048.0
    EMA_ALPHA = 0.22
    HP_ALPHA = 0.996
    hpPrevRaw = 2048.0
    hpPrevOut = 0.0
    
    notch_x1 = 0; notch_x2 = 0; notch_y1 = 0; notch_y2 = 0
    notch_b0 = 0.9630; notch_b1 = -1.2381; notch_b2 = 0.9630
    notch_a1 = -1.2381; notch_a2 = 0.9260

    dynamicThreshold = 2048.0
    peakLockout = False
    
    qrsInProgress = False
    qrsStartUs = 0
    latchedQrsEndLevel = 0
    beatPending = False
    pWaveDetectedThisCycle = False
    lastBeatTimeUs = 0
    lastPWaveTimeUs = 0
    
    rrHistory = [800]*8
    rrHistIdx = 0
    
    runningAvgRR = 800.0
    consecutivePVCs = 0
    consecutivePACs = 0
    
    SPS = 360
    SAMPLE_INTERVAL_US = 2777
    
    WIDE_QRS_MS = 100
    PREMATURE_RATIO = 0.85
    QRS_ONSET_OFFSET = 55.0
    
    out_features = []
    
    print(f"\n--- Simulating {csv_path} ---")
    
    for i, raw in enumerate(raw_samples):
        nowUs = i * SAMPLE_INTERVAL_US
        
        # DSP Filtering Pipeline
        emaValue = (EMA_ALPHA * raw) + ((1.0 - EMA_ALPHA) * emaValue)
        hpOut = HP_ALPHA * (hpPrevOut + emaValue - hpPrevRaw)
        hpPrevRaw = emaValue
        hpPrevOut = hpOut
        
        # Notch filter
        notchOut = notch_b0 * hpOut + notch_b1 * notch_x1 + notch_b2 * notch_x2 - notch_a1 * notch_y1 - notch_a2 * notch_y2
        notch_x2 = notch_x1
        notch_x1 = hpOut
        notch_y2 = notch_y1
        notch_y1 = notchOut
        
        output = int(notchOut + 2048)
        output = max(0, min(output, 4095))
        filteredVal = output
        
        # Beat processing
        dynamicThreshold = (0.992 * dynamicThreshold) + (0.008 * 2048.0)
        peakTrigger = dynamicThreshold + 100.0
        qrsOnsetLevel = dynamicThreshold + QRS_ONSET_OFFSET
        pWaveLowLevel = dynamicThreshold + 15.0
        pWaveHighLevel = dynamicThreshold + 45.0
        
        if not qrsInProgress and not peakLockout and filteredVal > qrsOnsetLevel:
            qrsInProgress = True
            qrsStartUs = nowUs
            latchedQrsEndLevel = qrsOnsetLevel
            
        if not peakLockout and not qrsInProgress and not pWaveDetectedThisCycle and filteredVal > pWaveLowLevel and filteredVal < pWaveHighLevel:
            lastPWaveTimeUs = nowUs
            pWaveDetectedThisCycle = True
            
        if filteredVal > peakTrigger and not peakLockout:
            if lastBeatTimeUs > 0:
                rrUs = nowUs - lastBeatTimeUs
                if 300000 <= rrUs <= 2000000:
                    rrMs = int(rrUs / 1000)
                    rrHistory[rrHistIdx] = rrMs
                    rrHistIdx = (rrHistIdx + 1) % 8
                    
                    sumRR = 0
                    validBeats = 0
                    for rr in rrHistory:
                        if rr > 0:
                            sumRR += rr
                            validBeats += 1
                    smoothedRR = sumRR / validBeats if validBeats > 0 else rrMs
                    bpm = 60000.0 / smoothedRR
                    
                    varSum = sum([abs(rr - smoothedRR) for rr in rrHistory if rr > 0])
                    rrVariance = varSum / smoothedRR
                    isIrregular = rrVariance > 0.20
                    
                    pWavePresent = pWaveDetectedThisCycle and (nowUs - lastPWaveTimeUs) < 300000
                    
                    isPrematureBeat = rrMs < runningAvgRR * PREMATURE_RATIO
                    if not isPrematureBeat or (abs(rrMs - rrHistory[(rrHistIdx - 2 + 8) % 8]) < 40):
                        runningAvgRR = (0.85 * runningAvgRR) + (0.15 * rrMs)
                        
                    # Save current beat info
                    curr_beat = {
                        'timeMs': nowUs // 1000,
                        'bpm': bpm,
                        'rrInterval': rrMs,
                        'runningAvgRR': runningAvgRR,
                        'peakVal': filteredVal,
                        'thresh': dynamicThreshold
                    }
                    
                    beatPending = True
            
            dynamicThreshold = float(filteredVal)
            lastBeatTimeUs = nowUs
            peakLockout = True
            
        if qrsInProgress and filteredVal < latchedQrsEndLevel:
            widthUs = nowUs - qrsStartUs
            qrsWidth = int(widthUs / 1000)
            qrsInProgress = False
            
            if beatPending:
                if qrsWidth < 20:
                    beatPending = False
                else:
                    isPremature = curr_beat['rrInterval'] < runningAvgRR * PREMATURE_RATIO
                    isWide = qrsWidth >= WIDE_QRS_MS
                    
                    if isPremature and isWide:
                        consecutivePVCs += 1
                        consecutivePACs = 0
                    elif isPremature and not isWide:
                        consecutivePACs += 1
                        consecutivePVCs = 0
                    else:
                        consecutivePVCs = 0
                        consecutivePACs = 0
                    
                    curr_beat['qrsWidth'] = qrsWidth
                    curr_beat['consecutivePVCs'] = consecutivePVCs
                    curr_beat['consecutivePACs'] = consecutivePACs
                    curr_beat['isPremature'] = isPremature
                    curr_beat['isWide'] = isWide
                    out_features.append(curr_beat)
                    print(f"Beat @ {curr_beat['timeMs']}ms: BPM={curr_beat['bpm']:.1f}, RR={curr_beat['rrInterval']}, AvgRR={curr_beat['runningAvgRR']:.1f}, Width={curr_beat['qrsWidth']}, Premature={isPremature}, Wide={isWide}, PVCs={consecutivePVCs}, Peak={curr_beat['peakVal']}, Thresh={curr_beat['thresh']:.1f}")
                    beatPending = False
                
        if peakLockout:
            if filteredVal < (dynamicThreshold - 80.0) or filteredVal < 2100:
                peakLockout = False
                pWaveDetectedThisCycle = False

if __name__ == "__main__":
    simulate_esp32_detection("recordings/ecg_20260813_112508.csv")
