#pragma once

// Pin configurations for U002 IR Unit
constexpr uint16_t IR_TX_PIN = 9;
constexpr uint16_t IR_RX_PIN = 10;

// Network configurations
constexpr char WEBHOOK_URL[] = "http://192.168.1.130:8123/api/webhook/panopticon";
constexpr uint16_t HTTP_TIMEOUT_MS = 2000;

// Global helper to safely enqueue webhook payloads asynchronously
#include <WString.h>
extern void enqueueWebhook(const String& payload);
