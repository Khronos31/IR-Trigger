#pragma once
#include <M5Unified.h>
#include <vector>
#include <IRsend.h>
#include "Config.h"
#include "AppInterface.h"

class AppSniper : public AppInterface {
private:
    std::vector<uint16_t> loadedRaw;
    bool hasLoadedRaw = false;
    bool needsBackgroundRedraw = true;
    uint32_t visualFeedbackEndTime = 0;
    IRsend* irsend = nullptr;

public:
    AppSniper() {}

    virtual const char* getName() const override {
        return "2. Sniper";
    }

    virtual void init(IRsend* tx) override {
        irsend = tx;
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

    void loadSignalRaw(const std::vector<uint16_t>& raw) {
        loadedRaw = raw;
        hasLoadedRaw = true;
        needsBackgroundRedraw = true;
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
