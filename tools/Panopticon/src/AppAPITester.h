#pragma once
#include <M5Unified.h>
#include <vector>
#include <LittleFS.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include "Config.h"
#include "AppInterface.h"
#include <AsyncJson.h>

// Forward declaration of parsing helper from main.cpp
bool parseAndSanitizeTxJson(JsonVariant& json, std::vector<uint16_t>& outRaw, String& outCode);

class AppAPITester : public AppInterface {
private:
    bool needsBackgroundRedraw = true;
    uint32_t txCount = 0;
    String currentLogFile = "";
    std::vector<String> sessionLogsBuffer;
    
    AsyncCallbackJsonWebHandler* txHandler = nullptr;

public:
    AppAPITester() {}

    virtual const char* getName() const override {
        return "4. API Tester";
    }

    virtual void init(IRsend* tx, IRrecv* rx) override {
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

    virtual void setupWeb(AsyncWebServer* server) override {
        if (txHandler) return;
        
        txHandler = new AsyncCallbackJsonWebHandler("/tx", [this](AsyncWebServerRequest *request, JsonVariant &json) {
            std::vector<uint16_t> tempRaw;
            String displayCode;
            
            if (!parseAndSanitizeTxJson(json, tempRaw, displayCode)) {
                request->send(400, "text/plain", "Bad Request: Missing 'raw' array");
                return;
            }
            
            this->onTxReceived(tempRaw, displayCode);
            request->send(200, "text/plain", "OK: TX Logged by API Tester");
        });
        
        server->addHandler(txHandler);
    }

    virtual void teardownWeb(AsyncWebServer* server) override {
        if (txHandler) {
            server->removeHandler(txHandler);
            delete txHandler;
            txHandler = nullptr;
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
