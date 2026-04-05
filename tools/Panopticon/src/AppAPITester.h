#pragma once
#include <M5Unified.h>
#include <vector>
#include <LittleFS.h>
#include "Config.h"
#include "AppInterface.h"

class AppAPITester : public AppInterface {
private:
    bool needsBackgroundRedraw = true;
    uint32_t txCount = 0;
    String currentLogFile = "";
    std::vector<String> sessionLogsBuffer;

public:
    AppAPITester() {}

    virtual const char* getName() const override {
        return "4. API Tester";
    }

    virtual void init(IRsend* tx) override {
        // Not actually sending IR in this app, just logging TX payloads
    }

    virtual void setup() override {
        txCount = 0;
        sessionLogsBuffer.clear();
        needsBackgroundRedraw = true;

        currentLogFile = "/tx_test_" + String(millis()) + ".txt";
        
        File file = LittleFS.open(currentLogFile, FILE_WRITE);
        if (file) {
            file.close();
            DEBUG_PRINTLN("Created new TX log file: " + currentLogFile);
        } else {
            DEBUG_PRINTLN("Failed to create TX log file: " + currentLogFile);
        }
    }

    void flushLogsToDisk() {
        if (!currentLogFile.isEmpty() && !sessionLogsBuffer.empty()) {
            File file = LittleFS.open(currentLogFile, FILE_APPEND);
            if (file) {
                for (const String& entry : sessionLogsBuffer) {
                    file.print(entry);
                }
                file.close();
                DEBUG_PRINTF("Flushed %d TX logs to %s\n", sessionLogsBuffer.size(), currentLogFile.c_str());
            } else {
                DEBUG_PRINTLN("Failed to append to log file: " + currentLogFile);
            }
            sessionLogsBuffer.clear();
        }
    }

    virtual void draw(bool fullDraw = false) override {
        if (fullDraw || needsBackgroundRedraw) {
            M5.Display.fillScreen(TFT_BLACK);
            M5.Display.setCursor(0, 5);
            M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
            M5.Display.setTextSize(2);
            M5.Display.println("[API TESTER]");
            M5.Display.println("-------------");
            
            M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
            M5.Display.setCursor(0, M5.Display.height() - 15);
            M5.Display.setTextSize(1);
            M5.Display.println("BtnB: < BACK & SAVE");
            needsBackgroundRedraw = false;
        }
        
        M5.Display.setCursor(0, 45); 
        M5.Display.setTextSize(2);
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
        
        M5.Display.printf("TX Logged: %d      \n", txCount);
        M5.Display.println("Waiting for HA... ");
    }

    virtual void onTxReceived(const std::vector<uint16_t>& raw, const String& displayCode) override {
        txCount++;
        
        // Reconstruct JSON array string for logging
        String rawJson;
        rawJson.reserve(raw.size() * 6 + 10);
        rawJson = "[";
        for (size_t i = 0; i < raw.size(); i++) {
            rawJson += String(raw[i]);
            if (i < raw.size() - 1) rawJson += ",";
        }
        rawJson += "]";

        String code = displayCode.isEmpty() ? "UNKNOWN" : displayCode;

        // Buffer the entry
        String logEntry = "{\"code\":\"" + code + "\",\"raw\":" + rawJson + ",\"ts\":" + String(millis()) + "}\n";
        sessionLogsBuffer.push_back(logEntry);
        
        if (sessionLogsBuffer.size() > 10) {
            flushLogsToDisk();
        }

        draw(); // Update count on screen
    }

    virtual void loop(bool& returnToMenu) override {
        if (M5.BtnB.wasReleased()) {
            flushLogsToDisk();
            returnToMenu = true;
            return;
        }
    }
};
