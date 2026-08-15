#ifndef NETWORK_H
#define NETWORK_H

#include <Arduino.h>

void initNetworkTask();
void connectWiFi();
void upload1SecBatchToAPI(int* ecgBatchBuffer, int sps, bool currentLeadsOff, String currentSeverity, String currentDiagnosis);

#endif