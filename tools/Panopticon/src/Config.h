#pragma once

// Pin configurations for U002 IR Unit
constexpr uint16_t IR_TX_PIN = 9;
constexpr uint16_t IR_RX_PIN = 10;

// Network configurations
constexpr char WEBHOOK_URL[] = "http://192.168.1.130:8123/api/webhook/panopticon";
constexpr uint16_t HTTP_TIMEOUT_MS = 2000;

// Zero-Cost Abstraction Debug Macros
// Uncomment the next line to enable serial debug output
// #define ENABLE_DEBUG_LOG

#ifdef ENABLE_DEBUG_LOG
    #define DEBUG_PRINTF(...) Serial.printf(__VA_ARGS__)
    #define DEBUG_PRINTLN(x) Serial.println(x)
    #define DEBUG_PRINT(x) Serial.print(x)
#else
    #define DEBUG_PRINTF(...)
    #define DEBUG_PRINTLN(x)
    #define DEBUG_PRINT(x)
#endif

// Global helper to safely enqueue webhook payloads asynchronously
#include <WString.h>
extern void enqueueWebhook(const String& payload);
