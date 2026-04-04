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
    const int maxLogs = 8; // Restored to more lines for 2-line display
    bool screenHidden = false;
    bool needsBackgroundRedraw = true;

    IRsend* irsend = nullptr;
    std::vector<uint16_t> pendingTxRaw;
    String pendingTxCodeStr = ""; // Holds beautiful string like "SWITCHBOT 0x12345678"
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
        // Truncate in the middle with "..." if the hex code is incredibly long (e.g. 88bit+ air conditioners)
        if (logLine.length() > 35) {
            int len = logLine.length();
            logLine = logLine.substring(0, 15) + "..." + logLine.substring(len - 17);
        }
        
        logs.push_back(logLine);
        while (logs.size() > maxLogs) {
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
            needsBackgroundRedraw = false;
        }
        
        M5.Display.setCursor(0, 45);
        M5.Display.setTextSize(1); // Restored original size to fit more info
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
        
        for(size_t i = 0; i < maxLogs; i++) {
            if (i < logs.size()) {
                String padded = logs[i];
                while(padded.length() < 35) padded += " ";
                M5.Display.println(padded);
            } else {
                M5.Display.println("                                   "); // 35 spaces
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
                
                if (!pendingTxCodeStr.isEmpty() && !pendingTxCodeStr.startsWith("RAW_")) {
                    int spaceIdx = pendingTxCodeStr.indexOf(' ');
                    if (spaceIdx > 0) {
                        addLog("TX: " + pendingTxCodeStr.substring(0, spaceIdx));
                        addLog("    " + pendingTxCodeStr.substring(spaceIdx + 1));
                    } else {
                        addLog("TX: " + pendingTxCodeStr);
                    }
                } else {
                    addLog("TX: " + String(pendingTxRaw.size()) + " pls");
                }
            }
            hasPendingTx = false;
            draw();
        }
    }

    void onIrReceived(const String& hexCode, const String& rawJson) {
        if (!hexCode.isEmpty() && !hexCode.startsWith("RAW_")) {
            int spaceIdx = hexCode.indexOf(' ');
            if (spaceIdx > 0) {
                addLog("RX: " + hexCode.substring(0, spaceIdx));
                addLog("    " + hexCode.substring(spaceIdx + 1));
            } else {
                addLog("RX: " + hexCode);
            }
        } else {
            String countStr = hexCode.startsWith("RAW_") ? hexCode : "Unknown";
            countStr.replace("RAW_", "");
            addLog("RX: " + countStr + " pls");
        }
        draw();

        // Async Post to HA Webhook via global queue
        String payload = "{\"raw\":" + rawJson + "}";
        enqueueWebhook(payload);
    }
};
