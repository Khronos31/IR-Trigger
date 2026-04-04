#pragma once
#include <M5Unified.h>
#include <vector>
#include <IRsend.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "Config.h"

class AppSniper {
private:
    std::vector<uint16_t> loadedRaw;
    bool hasLoadedRaw = false;
    bool needsBackgroundRedraw = true;
    uint32_t visualFeedbackEndTime = 0;
    IRsend* irsend = nullptr;

    bool needsTargetLockedPost = false;

public:
    AppSniper() {}

    void init(IRsend* tx) {
        irsend = tx;
    }

    void setup() {
        loadedRaw.clear();
        hasLoadedRaw = false;
        needsBackgroundRedraw = true;
        visualFeedbackEndTime = 0;
        needsTargetLockedPost = false;
    }

    void draw(bool fullDraw = false) {
        if (fullDraw || needsBackgroundRedraw) {
            M5.Display.fillScreen(TFT_BLACK);
            M5.Display.setCursor(0, 5);
            M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
            M5.Display.setTextSize(2);
            M5.Display.println("[SNIPER]");
            M5.Display.println("-------------");
            
            M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
            M5.Display.setCursor(0, M5.Display.height() - 15);
            M5.Display.setTextSize(1);
            M5.Display.println("BtnA_Short: FIRE | BtnB: < BACK");
            needsBackgroundRedraw = false;
        }
        
        M5.Display.setCursor(0, 45); 
        M5.Display.setTextSize(2);
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
        M5.Display.println("CHAMBER:                    "); 
        if (!hasLoadedRaw) {
             M5.Display.setTextColor(TFT_DARKGREEN, TFT_BLACK);
             M5.Display.println(" [ EMPTY ]                  ");
        } else {
             M5.Display.setTextColor(TFT_RED, TFT_BLACK);
             M5.Display.println(" [ LOADED ]                 ");
        }
    }

    void loadSignalRaw(const std::vector<uint16_t>& raw) {
        loadedRaw = raw;
        hasLoadedRaw = true;
        needsBackgroundRedraw = true;
        needsTargetLockedPost = true; // Delegate HTTP POST to main loop
    }

    void loop(bool& returnToMenu) {
        if (needsTargetLockedPost && hasLoadedRaw) {
            needsTargetLockedPost = false;
            
            // Send "Target_Locked" event to HA with raw array for converter compatibility
            HTTPClient http;
            http.begin(WEBHOOK_URL);
            http.setTimeout(HTTP_TIMEOUT_MS);
            http.addHeader("Content-Type", "application/json");

            JsonDocument docOut;
            docOut["Device"] = "Panopticon_Sniper";
            docOut["Button"] = "Target_Locked";
            
            JsonArray rawArrayOut = docOut["raw"].to<JsonArray>();
            for (size_t i = 0; i < loadedRaw.size(); i++) {
                rawArrayOut.add(loadedRaw[i]);
            }
            
            String payload;
            serializeJson(docOut, payload);
            int httpResponseCode = http.POST(payload);
            http.end();

            if (httpResponseCode > 0) {
                Serial.printf("Target Locked POST OK: %d\n", httpResponseCode);
            } else {
                Serial.printf("Target Locked POST ERR: %s\n", http.errorToString(httpResponseCode).c_str());
            }
        }

        if (needsBackgroundRedraw && visualFeedbackEndTime == 0) {
            draw();
        }

        if (M5.BtnB.wasReleased()) {
            returnToMenu = true;
            return;
        }

        if (visualFeedbackEndTime > 0 && millis() > visualFeedbackEndTime) {
            visualFeedbackEndTime = 0;
            // Restore screen if it was flashed red
            draw(true);
        }

        if (M5.BtnA.wasPressed()) {
            if (hasLoadedRaw && visualFeedbackEndTime == 0) {
                if (irsend) {
                    irsend->sendRaw(loadedRaw.data(), loadedRaw.size(), 38);
                    Serial.printf("SNIPER FIRED: %d pulses\n", loadedRaw.size());
                }
                hasLoadedRaw = false; 
                
                // Flash screen red and set timer
                M5.Display.fillScreen(TFT_RED);
                visualFeedbackEndTime = millis() + 50;
            }
        }
    }
};
