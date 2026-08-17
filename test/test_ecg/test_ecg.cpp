#include <Arduino.h>

#define ECG_PIN   34
#define LO_PLUS   33
#define LO_MINUS  32

// =====================================================
// MODE SELECTION
// =====================================================
bool isLiveMode = true;
int injectedRawSample = 0;

void handleSerialCommands() {
  while (Serial.available() > 0) {
    char buf[64];
    size_t len = Serial.readBytesUntil('\n', buf, sizeof(buf) - 1);
    buf[len] = '\0';
    
    String input = String(buf);
    input.trim();

    if (input.equalsIgnoreCase("mode recorded")) {
      isLiveMode = false;
      Serial.println("\n[SYSTEM MODE] Switched to RECORDED CSV Feed Input.");
    }
    else if (input.equalsIgnoreCase("mode live")) {
      isLiveMode = true;
      Serial.println("\n[SYSTEM MODE] Switched to LIVE ADC Input.");
    }
    else if (!isLiveMode) {
      if (input.startsWith("sample,")) {
        injectedRawSample = input.substring(7).toInt();
      } else {
        injectedRawSample = input.toInt();
      }
    }
  }
}

// =====================================================
// SAMPLING
// =====================================================

const unsigned long SAMPLE_INTERVAL_US = 4000; // 250 Hz
unsigned long lastSample = 0;


// =====================================================
// ECG FILTER SETTINGS
// Approximate ECG monitoring band: 0.5 - 40 Hz
// =====================================================

// -------- High-pass filter --------
// Removes baseline wander / DC drift
float hp_x1 = 0.0;
float hp_y1 = 0.0;

// fc ≈ 0.5 Hz at fs = 250 Hz
const float HP_ALPHA = 0.9875;


// -------- Low-pass filter --------
// Two-stage EMA for smoother ECG while preserving QRS
float lp1 = 0.0;
float lp2 = 0.0;

// Approximate low-pass behaviour for balanced noise reduction
const float LP_ALPHA = 0.45;


// =====================================================
// 50 Hz NOTCH FILTER
// =====================================================

const bool USE_NOTCH = true;

float notch_x1 = 0.0;
float notch_x2 = 0.0;
float notch_y1 = 0.0;
float notch_y2 = 0.0;

// 250 Hz sampling, 50 Hz notch
// Narrow notch around mains frequency
const float b0 = 0.9587;
const float b1 = -0.5922;
const float b2 = 0.9587;

const float a1 = -0.5922;
const float a2 = 0.9174;


// =====================================================
// LEAD-OFF STATE
// =====================================================

bool wasOff = false;


// =====================================================
// NOTCH FUNCTION
// =====================================================

float applyNotch(float x)
{
  float y =
    b0 * x
    + b1 * notch_x1
    + b2 * notch_x2
    - a1 * notch_y1
    - a2 * notch_y2;

  notch_x2 = notch_x1;
  notch_x1 = x;

  notch_y2 = notch_y1;
  notch_y1 = y;

  return y;
}


// =====================================================
// OVERSAMPLED ADC
// =====================================================

int readOversampled(int pin, int samples)
{
  long sum = 0;

  for (int i = 0; i < samples; i++)
  {
    sum += analogRead(pin);
  }

  return (int)(sum / samples);
}


// =====================================================
// RESET FILTERS
// =====================================================

void resetFilters(float value)
{
  hp_x1 = value;
  hp_y1 = 0;

  lp1 = 0;
  lp2 = 0;

  notch_x1 = 0;
  notch_x2 = 0;
  notch_y1 = 0;
  notch_y2 = 0;
}


// =====================================================
// SETUP
// =====================================================

void setup()
{
  Serial.begin(115200);

  pinMode(LO_PLUS, INPUT);
  pinMode(LO_MINUS, INPUT);

  analogReadResolution(12);

  // ESP32 ADC range
  analogSetAttenuation(ADC_11db);

  lastSample = micros();
}


// =====================================================
// MAIN LOOP
// =====================================================

void loop()
{
  handleSerialCommands();

  unsigned long now = micros();

  if ((unsigned long)(now - lastSample) >= SAMPLE_INTERVAL_US)
  {
    lastSample += SAMPLE_INTERVAL_US;


    // =================================================
    // LEADS-OFF DETECTION (Live Mode Only)
    // =================================================

    if (isLiveMode && (digitalRead(LO_PLUS) || digitalRead(LO_MINUS)))
    {
      wasOff = true;

      Serial.println(">off:1");

      return;
    }


    // =================================================
    // READ ECG
    // =================================================

    int rawADC = 0;
    if (isLiveMode) {
      rawADC = readOversampled(ECG_PIN, 4);
    } else {
      rawADC = injectedRawSample;
    }

    float raw = (float)rawADC;


    // =================================================
    // RESET FILTER AFTER ELECTRODE RECONNECT
    // =================================================

    if (wasOff)
    {
      resetFilters(raw);

      wasOff = false;
    }


    // =================================================
    // HIGH-PASS FILTER (Bypassed)
    // Retains raw DC offset for 1:1 coordinate matching
    // =================================================

    float hp = raw;

    hp_x1 = raw;
    hp_y1 = hp;


    // =================================================
    // LOW-PASS FILTER
    // Removes high-frequency noise
    // =================================================

    lp1 =
      LP_ALPHA * hp +
      (1.0 - LP_ALPHA) * lp1;

    lp2 =
      LP_ALPHA * lp1 +
      (1.0 - LP_ALPHA) * lp2;


    // =================================================
    // 50 Hz NOTCH
    // =================================================

    float filtered;

    if (USE_NOTCH)
    {
      filtered = applyNotch(lp2);
    }
    else
    {
      filtered = lp2;
    }


    // =================================================
    // OUTPUT
    // =================================================

    Serial.print(">raw:");
    Serial.print(rawADC);

    Serial.print("\n>filtered:");
    Serial.println(filtered, 2);
  }
}