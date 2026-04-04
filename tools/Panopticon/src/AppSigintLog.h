#pragma once
#include <M5Unified.h>
#include <vector>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include "Config.h"

class AppSigintLog {
private:
    String latestCode = "";
    String currentLogFile = "";
    bool btnALongPressedHandled = false;
    uint32_t visualFeedbackEndTime = 0;
    bool needsBackgroundRedraw = true;

public:
    IRrecv irrecv;
    IRsend irsend;
    decode_results results;
    std::vector<uint16_t> latestRaw;

    AppSigintLog() : irrecv(IR_RX_PIN, 1024, 25, true), irsend(IR_TX_PIN) {}

    void setup() {
        latestCode = "";
        latestRaw.clear();
        btnALongPressedHandled = false;
        visualFeedbackEndTime = 0;
        needsBackgroundRedraw = true;

        pinMode(IR_RX_PIN, INPUT_PULLUP);
        delay(50);
        irrecv.enableIRIn();
        irsend.begin();
    }

    void draw(bool fullDraw = false) {
        if (fullDraw || needsBackgroundRedraw) {
            M5.Display.fillScreen(TFT_BLACK);
            M5.Display.setCursor(0, 5);
            M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
            M5.Display.setTextSize(2);
            M5.Display.println("[SIGINT LOG]");
            M5.Display.println("-------------");
            
            M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
            M5.Display.setCursor(0, M5.Display.height() - 25);
            M5.Display.setTextSize(1);
            M5.Display.println("BtnA_Short: FIRE | BtnA_Long: DEL");
            M5.Display.println("BtnB: < BACK");
            needsBackgroundRedraw = false;
        }
        
        M5.Display.setCursor(0, 45); // Start Y for variables
        M5.Display.setTextSize(2);
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK); // Background overwriting
        M5.Display.println("Latest Signal:               "); 
        if (latestCode.isEmpty()) {
             M5.Display.setTextColor(TFT_DARKGREEN, TFT_BLACK);
             M5.Display.println(" [WAITING...]                ");
        } else {
             M5.Display.setTextColor(TFT_CYAN, TFT_BLACK);
             M5.Display.println(" " + latestCode + "                ");
        }
    }

    void onIrReceived(const String& code, const String& rawJson, const std::vector<uint16_t>& rawVector, uint32_t ts) {
        latestCode = code;
        latestRaw = rawVector;
        draw();
    }

    void loop(bool& returnToMenu) {
        if (M5.BtnB.wasReleased()) {
            returnToMenu = true;
            return;
        }

        // Non-blocking visual feedback clear
        if (visualFeedbackEndTime > 0 && millis() > visualFeedbackEndTime) {
            visualFeedbackEndTime = 0;
            M5.Display.fillCircle(M5.Display.width() - 10, 10, 5, TFT_BLACK);
        }

        // Handle Long Press (Delete Latest)
        if (M5.BtnA.pressedFor(1000)) {
            if (!btnALongPressedHandled) {
                if (!latestCode.isEmpty()) {
                    latestCode = "";
                    draw();
                }
                btnALongPressedHandled = true;
            }
        } 
        // Handle Short Press (Fire Latest)
        else if (M5.BtnA.wasReleased()) {
             if (!btnALongPressedHandled) {
                 if (!latestCode.isEmpty() && latestRaw.size() > 0) {
                     irsend.sendRaw(latestRaw.data(), latestRaw.size(), 38);
                     Serial.printf("SIGINT FIRED: %s\n", latestCode.c_str());
                     M5.Display.fillCircle(M5.Display.width() - 10, 10, 5, TFT_CYAN);
                     visualFeedbackEndTime = millis() + 50;
                 }
             }
             // Reset long press flag on release
             btnALongPressedHandled = false;
        }
    }
};
