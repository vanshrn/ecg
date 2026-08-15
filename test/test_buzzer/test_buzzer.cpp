#include <Arduino.h>

#define BUZZER_PIN 25 // Change to your actual GPIO pin

// --- Sound Patterns ---

// 1. Wi-Fi Connected Tone (Double quick chime)
void playWifiConnectedTone() {
  Serial.println("[BUZZER] Playing Wi-Fi Connected Chime...");
  tone(BUZZER_PIN, 1000, 100); // 1000 Hz for 100ms
  delay(150);
  tone(BUZZER_PIN, 1500, 150); // 1500 Hz for 150ms
  delay(200);
}

// 2. WARNING Alert (Single medium beep)
void playWarningAlert() {
  Serial.println("[BUZZER] Playing WARNING Alert (Atrial Fib / Tachycardia)...");
  tone(BUZZER_PIN, 800, 300); // 800 Hz tone for 300ms
  delay(400);
}

// 3. CRITICAL Alert (Rapid high-pitch alarm pulses)
void playCriticalAlert() {
  Serial.println("[BUZZER] Playing CRITICAL Alarm (VT / VFib / Asystole)...");
  for (int i = 0; i < 3; i++) {
    tone(BUZZER_PIN, 2400, 100); // High pitch 2.4kHz pulse
    delay(120);
  }
  delay(300);
}

void setup() {
  Serial.begin(115200);
  pinMode(BUZZER_PIN, OUTPUT);

  Serial.println("\n=============================================");
  Serial.println("     BUZZER SOUND PATTERN TEST SUITE         ");
  Serial.println("=============================================");
  Serial.println("Testing tones sequentially...");
  delay(1000);

  // Run initial test sequence
  playWifiConnectedTone();
  delay(1000);

  playWarningAlert();
  delay(1000);

  playCriticalAlert();
  
  Serial.println("\nCommands via Serial Monitor:");
  Serial.println("  '1' or 'wifi'     : Play Wi-Fi Connect Sound");
  Serial.println("  '2' or 'warning'  : Play Warning Alert Sound");
  Serial.println("  '3' or 'critical' : Play Critical Alert Sound");
}

void loop() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toLowerCase();

    if (cmd == "1" || cmd == "wifi") {
      playWifiConnectedTone();
    } 
    else if (cmd == "2" || cmd == "warning") {
      playWarningAlert();
    } 
    else if (cmd == "3" || cmd == "critical") {
      playCriticalAlert();
    }
  }
}