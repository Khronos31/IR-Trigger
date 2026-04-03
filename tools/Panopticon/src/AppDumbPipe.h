#pragma once
#include <M5Unified.h>
#include <vector>

class AppDumbPipe {
private:
    std::vector<String> logs;
    const int maxLogs = 5;
    bool screenHidden = false;

public:
    void setup() {
        logs.clear();
        screenHidden = false;
        addLog("SYS: DUMB PIPE READY");
    }

    void addLog(const String& msg) {
        String logLine = msg;
        // Truncate if too long (assuming ~25-30 chars fit horizontally at text size 1 or 2)
        if (logLine.length() > 30) {
            logLine = logLine.substring(0, 30);
        }
        
        logs.push_back(logLine);
        if (logs.size() > maxLogs) {
            logs.erase(logs.begin());
        }
    }

    void draw() {
        if (screenHidden) {
            M5.Display.fillScreen(TFT_BLACK);
            return;
        }
        
        M5.Display.fillScreen(TFT_BLACK);
        M5.Display.setCursor(0, 5);
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
        M5.Display.setTextSize(2);
        M5.Display.println("[DUMB PIPE]");
        M5.Display.println("-------------");
        
        M5.Display.setTextSize(1);
        for(size_t i = 0; i < logs.size(); i++) {
            M5.Display.println(logs[i]);
        }
        
        M5.Display.setCursor(0, M5.Display.height() - 15);
        M5.Display.println("BtnA: Screen Toggle | BtnB: < BACK");
    }

    void loop(bool& returnToMenu) {
        if (M5.BtnB.wasPressed()) {
            returnToMenu = true;
            return;
        }

        if (M5.BtnA.wasPressed()) {
            screenHidden = !screenHidden;
            draw();
        }

        // TODO: Implement HTTP POST (Webhook) and AsyncWebServer (RX/TX)
        // Simulate dummy logs for now (replace with actual network triggers later)
        /*
        static uint32_t lastMock = 0;
        if (millis() - lastMock > 5000 && !screenHidden) {
            addLog("RX: RAW_9000,4500,560...");
            draw();
            lastMock = millis();
        }
        */
    }
};
