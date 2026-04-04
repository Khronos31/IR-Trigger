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
    const int maxLogs = 6; // Restored to more lines for 2-line display
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
        // Truncate cleanly with "..." if the hex code is incredibly long (e.g. 88bit+ air conditioners)
        if (logLine.length() > 30) {
            logLine = logLine.substring(0, 24) + "...";
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
            
            M5.Display.setCursor(0, M5.Display.height() - 15);
            M5.Display.setTextSize(1);
            M5.Display.println("BtnA: Screen Toggle | BtnB: < BACK");
            needsBackgroundRedraw = false;
        }
        
        M5.Display.setCursor(0, 45);
        M5.Display.setTextSize(1); // Restored original size to fit more info
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
        
        for(size_t i = 0; i < maxLogs; i++) {
            if (i < logs.size()) {
                String padded = logs[i];
                while(padded.length() < 30) padded += " ";
                M5.Display.println(padded);
            } else {
                M5.Display.println("                              "); // 30 spaces
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
                
                if (!pendingTxCodeStr.isEmpty() && !pendingTxCodeStr.startsWith("RAW-")) {
                    int delimIdx = pendingTxCodeStr.indexOf('-');
                    if (delimIdx < 0) delimIdx = pendingTxCodeStr.indexOf(' ');
                    
                    if (delimIdx > 0) {
                        String prefix = pendingTxCodeStr.substring(0, delimIdx);
                        String hexPart = pendingTxCodeStr.substring(delimIdx + 1);
                        
                        addLog("TX: " + prefix);
                        
                        // Handle extremely long hex strings by splitting or truncating
                        if (hexPart.length() > 16) {
                            addLog("    " + hexPart.substring(0, 13) + "...");
                        } else {
                            addLog("    " + hexPart);
                        }
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
        if (!hexCode.isEmpty() && !hexCode.startsWith("RAW-")) {
            int delimIdx = hexCode.indexOf('-');
            if (delimIdx < 0) delimIdx = hexCode.indexOf(' ');
            
            if (delimIdx > 0) {
                String prefix = hexCode.substring(0, delimIdx);
                String hexPart = hexCode.substring(delimIdx + 1);
                
                addLog("RX: " + prefix);
                if (hexPart.length() > 16) {
                    addLog("    " + hexPart.substring(0, 13) + "...");
                } else {
                    addLog("    " + hexPart);
                }
            } else {
                addLog("RX: " + hexCode);
            }
        } else {
            String countStr = hexCode.startsWith("RAW-") ? hexCode : "Unknown";
            countStr.replace("RAW-", "");
            addLog("RX: " + countStr + " pls");
        }
        draw();

        // Async Post to HA Webhook via global queue
        String payload = "{\"raw\":" + rawJson + "}";
        enqueueWebhook(payload);
    }
};
