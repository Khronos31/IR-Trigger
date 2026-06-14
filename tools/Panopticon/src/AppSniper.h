#pragma once
#include <M5Unified.h>
#include <vector>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include "Config.h"
#include "AppInterface.h"

// Forward declaration of enqueue helper from main.cpp
void enqueueWebhook(const String& payload);

class AppSniper : public AppInterface {
private:
    std::vector<uint16_t> loadedRaw;
    bool hasLoadedRaw = false;
    bool needsBackgroundRedraw = true;
    uint32_t visualFeedbackEndTime = 0;
    IRsend* irsend = nullptr;
    IRrecv* irrecv = nullptr;

public:
    AppSniper() {}

    virtual const char* getName() const override {
        return "2. Sniper";
    }

    virtual void init(IRsend* tx, IRrecv* rx) override {
        irsend = tx;
        irrecv = rx;
    }

    virtual void setup() override {
        loadedRaw.clear();
        hasLoadedRaw = false;
        needsBackgroundRedraw = true;
        visualFeedbackEndTime = 0;
    }

    virtual void draw(bool fullDraw = false) override {
        if (fullDraw || needsBackgroundRedraw) {
            M5.Display.fillScreen(TFT_BLACK);
            M5.Display.setCursor(0, 5);
            M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
            M5.Display.setTextSize(2);
            M5.Display.println("[SNIPER]");
            M5.Display.println("-------------");
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

    virtual void onTxReceived(const std::vector<uint16_t>& raw, const String& displayCode) override {
        loadedRaw = raw;
        hasLoadedRaw = true;
        needsBackgroundRedraw = true;

        // Automatically trigger webhook to notify Home Assistant that the sniper is locked and loaded
        JsonDocument docOut;
        docOut["Device"] = "Panopticon_Sniper";
        docOut["Button"] = "Target_Locked";
        JsonArray rawArrayOut = docOut["raw"].to<JsonArray>();
        for (size_t k = 0; k < raw.size(); k++) {
            rawArrayOut.add(raw[k]);
        }
        
        String payload;
        serializeJson(docOut, payload);
        enqueueWebhook(payload);
    }

    virtual void loop(bool& returnToMenu) override {
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
                    // Use the centralized DRY function for sending IR signals safely
                    safe_ir_send(irsend, irrecv, loadedRaw);
                    DEBUG_PRINTF("SNIPER FIRED: %d pulses\n", loadedRaw.size());
                }
                hasLoadedRaw = false; 
                
                // Flash screen red and set timer
                M5.Display.fillScreen(TFT_RED);
                visualFeedbackEndTime = millis() + 50;
            }
        }
    }
};
