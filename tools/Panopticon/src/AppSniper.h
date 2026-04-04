#pragma once
#include <M5Unified.h>

class AppSniper {
private:
    String loadedCommand = "";
    bool needsBackgroundRedraw = true;
    uint32_t visualFeedbackEndTime = 0;

public:
    void setup() {
        loadedCommand = "";
        needsBackgroundRedraw = true;
        visualFeedbackEndTime = 0;
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
        if (loadedCommand.isEmpty()) {
             M5.Display.setTextColor(TFT_DARKGREEN, TFT_BLACK);
             M5.Display.println(" [ EMPTY ]                  ");
        } else {
             M5.Display.setTextColor(TFT_RED, TFT_BLACK);
             M5.Display.println(" [" + loadedCommand + "]               ");
        }
    }

    void loadSignal(const String& signal) {
        loadedCommand = signal;
        draw();
    }

    void loop(bool& returnToMenu) {
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
            if (!loadedCommand.isEmpty() && visualFeedbackEndTime == 0) {
                Serial.printf("SNIPER FIRED: %s\n", loadedCommand.c_str());
                loadedCommand = ""; 
                
                // Flash screen red and set timer
                M5.Display.fillScreen(TFT_RED);
                visualFeedbackEndTime = millis() + 50;
            }
        }
    }
};
