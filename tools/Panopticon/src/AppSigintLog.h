#pragma once
#include <M5Unified.h>

class AppSigintLog {
private:
    String latestCode = "";
    String currentLogFile = "";

public:
    void setup() {
        latestCode = "";
        
        // TODO: Generate currentLogFile timestamp and open LittleFS/SD Card
        // Example: 
        // time_t now; time(&now);
        // currentLogFile = "/sigint_log_" + String(now) + ".json";
        // File f = LittleFS.open(currentLogFile, "w");
    }

    void draw() {
        M5.Display.fillScreen(TFT_BLACK);
        M5.Display.setCursor(0, 5);
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
        M5.Display.setTextSize(2);
        M5.Display.println("[SIGINT LOG]");
        M5.Display.println("-------------");
        
        M5.Display.setTextSize(2);
        M5.Display.println("Latest Signal:");
        if (latestCode.isEmpty()) {
             M5.Display.setTextColor(TFT_DARKGREEN, TFT_BLACK);
             M5.Display.println(" [WAITING...]");
        } else {
             M5.Display.setTextColor(TFT_CYAN, TFT_BLACK);
             M5.Display.println(" " + latestCode);
        }
        
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
        M5.Display.setCursor(0, M5.Display.height() - 25);
        M5.Display.setTextSize(1);
        M5.Display.println("BtnA_Short: FIRE | BtnA_Long: DEL");
        M5.Display.println("BtnB: < BACK");
    }

    void onIrReceived(const String& code, const String& rawArray, uint32_t ts) {
        latestCode = code;
        
        // Form JSON payload
        String jsonLog = "{\"code\":\"" + code + "\", \"raw\":[" + rawArray + "], \"ts\":" + String(ts) + "}\n";
        
        // TODO: Append to file
        // File f = LittleFS.open(currentLogFile, "a");
        // if(f) { f.print(jsonLog); f.close(); }
        
        draw();
    }

    void loop(bool& returnToMenu) {
        if (M5.BtnB.wasPressed()) {
            returnToMenu = true;
            return;
        }

        // Handle Long Press (Delete Latest)
        if (M5.BtnA.pressedFor(1000)) {
            if (!latestCode.isEmpty()) {
                latestCode = "";
                // TODO: Delete from log file logically if required
                
                M5.Display.fillScreen(TFT_DARKGREEN);
                delay(100);
                draw();
            }
            while (M5.BtnA.isPressed()) M5.update(); // Block until release
        } 
        // Handle Short Press (Fire Latest)
        else if (M5.BtnA.wasReleased()) {
             if (!latestCode.isEmpty()) {
                 // TODO: Generate and Fire IR signal via internal logic
                 Serial.printf("SIGINT FIRED: %s\n", latestCode.c_str());
                 
                 // Visual feedback
                 M5.Display.fillCircle(M5.Display.width() - 10, 10, 5, TFT_CYAN);
                 delay(50);
                 draw();
             }
        }
    }
};
