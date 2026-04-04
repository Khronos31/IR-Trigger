#pragma once
#include <M5Unified.h>
#include <vector>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include <ESPAsyncWebServer.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "Config.h"

class AppDumbPipe {
private:
    std::vector<String> logs;
    const int maxLogs = 3; // Reduced max logs for larger font
    bool screenHidden = false;
    bool needsBackgroundRedraw = true;

    IRsend* irsend = nullptr;
    std::vector<uint16_t> pendingTxRaw;
    String pendingTxCodeStr = ""; // Holds beautiful string like "NEC_LIKE 0x12345678"
    bool hasPendingTx = false;

public:
    AppDumbPipe() {}

    void init(IRsend* tx) {
        irsend = tx;
    }

    void setPendingTx(const std::vector<uint16_t>& raw, const String& codeStr = "") {
        pendingTxRaw = raw;
        pendingTxCodeStr = codeStr;
        hasPendingTx = true;
    }

    void setup() {
        logs.clear();
        screenHidden = false;
        needsBackgroundRedraw = true;
        
        addLog("SYS: DUMB PIPE READY");
    }

    void addLog(const String& msg) {
        String logLine = msg;
        if (logLine.length() > 20) { // Limit length for larger font without wrapping
            logLine = logLine.substring(0, 20);
        }
        
        logs.push_back(logLine);
        if (logs.size() > maxLogs) {
            logs.erase(logs.begin());
        }
    }

    void draw(bool fullDraw = false) {
        if (screenHidden) {
            if (fullDraw || needsBackgroundRedraw) {
                M5.Display.fillScreen(TFT_BLACK);
                needsBackgroundRedraw = false;
            }
            return;
        }
        
        if (fullDraw || needsBackgroundRedraw) {
            M5.Display.fillScreen(TFT_BLACK);
            M5.Display.setCursor(0, 5);
            M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
            M5.Display.setTextSize(2);
            M5.Display.println("[DUMB PIPE]");
            M5.Display.println("-------------");
            
            M5.Display.setCursor(0, M5.Display.height() - 15);
            M5.Display.setTextSize(1);
            M5.Display.println("BtnA: Screen Toggle | BtnB: < BACK");
            needsBackgroundRedraw = false;
        }
        
        M5.Display.setCursor(0, 40);
        M5.Display.setTextSize(1.5); // Larger font for better readability
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
        
        for(size_t i = 0; i < maxLogs; i++) {
            if (i < logs.size()) {
                String padded = logs[i];
                while(padded.length() < 20) padded += " ";
                M5.Display.println(padded);
            } else {
                M5.Display.println("                    "); // 20 spaces
            }
        }
    }

    void loop(bool& returnToMenu) {
        if (M5.BtnB.wasReleased()) {
            returnToMenu = true;
            return;
        }

        if (M5.BtnA.wasPressed()) {
            screenHidden = !screenHidden;
            needsBackgroundRedraw = true;
            draw(true);
        }

        // TX Processing
        if (hasPendingTx) {
            if (irsend) {
                irsend->sendRaw(pendingTxRaw.data(), pendingTxRaw.size(), 38);
                
                String logStr = "TX: ";
                if (!pendingTxCodeStr.isEmpty() && !pendingTxCodeStr.startsWith("RAW_")) {
                    logStr += pendingTxCodeStr;
                } else {
                    logStr += String(pendingTxRaw.size()) + " pls";
                }
                addLog(logStr);
            }
            hasPendingTx = false;
            draw();
        }
    }

    void onIrReceived(const String& hexCode, const String& rawJson) {
        String logStr = "RX: ";
        if (!hexCode.isEmpty() && !hexCode.startsWith("RAW_")) {
            logStr += hexCode;
        } else {
            // Count pulses directly from JSON array or rely on the length passed in hexCode (e.g. RAW_67)
            logStr += hexCode.startsWith("RAW_") ? hexCode : "Unknown";
            logStr.replace("RAW_", "");
            logStr += " pls";
        }

        addLog(logStr);
        draw();

        // Async Post to HA Webhook via global queue
        String payload = "{\"raw\":" + rawJson + "}";
        enqueueWebhook(payload);
    }
};
