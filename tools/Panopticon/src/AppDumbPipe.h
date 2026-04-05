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
#include "AppInterface.h"

class AppDumbPipe : public AppInterface {
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

    virtual const char* getName() const override {
        return "1. Dumb Pipe";
    }

    virtual void init(IRsend* tx) override {
        irsend = tx;
    }

    virtual void onTxReceived(const std::vector<uint16_t>& raw, const String& displayCode) override {
        pendingTxRaw = raw;
        pendingTxCodeStr = displayCode;
        hasPendingTx = true;
    }

    virtual void setup() override {
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

    virtual void draw(bool fullDraw = false) override {
        if (screenHidden) {
            // No drawing updates when screen is effectively turned off (backlight 0)
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

    virtual void loop(bool& returnToMenu) override {
        if (M5.BtnB.wasReleased()) {
            if (screenHidden) {
                M5.Display.setBrightness(128); // Ensure screen comes back on when returning to menu
                screenHidden = false;
            }
            returnToMenu = true;
            return;
        }

        if (M5.BtnA.wasPressed()) {
            screenHidden = !screenHidden;
            if (screenHidden) {
                M5.Display.setBrightness(0); // Turn off backlight completely
            } else {
                M5.Display.setBrightness(128); // Turn backlight back on
                needsBackgroundRedraw = true;
                draw(true);
            }
        }

        // TX Processing
        if (hasPendingTx) {
            if (irsend) {
                // Yield CPU to background tasks (like WiFi) before engaging heavy RMT transmission
                delay(20);
                
                irsend->sendRaw(pendingTxRaw.data(), pendingTxRaw.size(), 38);
                
                // Block the main thread (UI drawing) while RMT interrupts are busy transmitting the long array.
                // Assuming roughly 1ms average per pulse (mark+space pair), pendingTxRaw.size() ms is safe.
                delay(pendingTxRaw.size() + 20);

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

    // Adapt signature to match AppInterface (ignoring rawVector/ts since Dumb Pipe just posts JSON)
    virtual void onIrReceived(const String& hexCode, const String& rawJson, const std::vector<uint16_t>& rawVector, uint32_t ts) override {
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
