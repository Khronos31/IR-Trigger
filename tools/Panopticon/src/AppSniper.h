#pragma once
#include <M5Unified.h>

class AppSniper {
private:
    String loadedCommand = "";

public:
    void setup() {
        loadedCommand = "";
    }

    void draw() {
        M5.Display.fillScreen(TFT_BLACK);
        M5.Display.setCursor(0, 5);
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
        M5.Display.setTextSize(2);
        M5.Display.println("[SNIPER]");
        M5.Display.println("-------------");
        
        M5.Display.setTextSize(2);
        M5.Display.println("CHAMBER:");
        if (loadedCommand.isEmpty()) {
             M5.Display.setTextColor(TFT_DARKGREEN, TFT_BLACK);
             M5.Display.println(" [ EMPTY ]");
        } else {
             M5.Display.setTextColor(TFT_RED, TFT_BLACK);
             M5.Display.println(" [" + loadedCommand + "]");
        }
        
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
        M5.Display.setCursor(0, M5.Display.height() - 15);
        M5.Display.setTextSize(1);
        M5.Display.println("BtnA_Short: FIRE | BtnB: < BACK");
    }

    void loadSignal(const String& signal) {
        loadedCommand = signal;
        // TODO: Fire fake Webhook to HA 
        // Example Payload: 
        // {"event":"Target_Locked", "device":"Panopticon_Sniper", "signal": signal}
        draw();
    }

    void loop(bool& returnToMenu) {
        if (M5.BtnB.wasPressed()) {
            returnToMenu = true;
            return;
        }

        // Simulate receiving a command over network to load chamber
        // if (network_cmd_received) loadSignal(received_cmd);

        if (M5.BtnA.wasPressed()) {
            if (!loadedCommand.isEmpty()) {
                // TODO: Fire the actual IR signal
                Serial.printf("SNIPER FIRED: %s\n", loadedCommand.c_str());
                loadedCommand = ""; // Clear chamber after firing
                
                // Visual feedback (Flash Screen Red)
                M5.Display.fillScreen(TFT_RED);
                delay(50);
                draw();
            } else {
                Serial.println("SNIPER: Chamber is empty!");
            }
        }
    }
};
