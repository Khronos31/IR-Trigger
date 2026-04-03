#pragma once
#include <M5Unified.h>
#include <vector>

class AppDumbPipe {
private:
    std::vector<String> logs;
    const int maxLogs = 5;
    bool screenHidden = false;
    bool needsBackgroundRedraw = true;

public:
    void setup() {
        logs.clear();
        screenHidden = false;
        needsBackgroundRedraw = true;
        addLog("SYS: DUMB PIPE READY");
    }

    void addLog(const String& msg) {
        String logLine = msg;
        if (logLine.length() > 30) {
            logLine = logLine.substring(0, 30);
        }
        
        logs.push_back(logLine);
        if (logs.size() > maxLogs) {
            logs.erase(logs.begin());
        }
    }

    void draw(bool fullDraw = false) {
        if (screenHidden) {
            if (fullDraw || needsBackgroundRedraw) {
                M5.Display.fillScreen(TFT_BLACK);
                needsBackgroundRedraw = false;
            }
            return;
        }
        
        if (fullDraw || needsBackgroundRedraw) {
            M5.Display.fillScreen(TFT_BLACK);
            M5.Display.setCursor(0, 5);
            M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
            M5.Display.setTextSize(2);
            M5.Display.println("[DUMB PIPE]");
            M5.Display.println("-------------");
            
            M5.Display.setCursor(0, M5.Display.height() - 15);
            M5.Display.setTextSize(1);
            M5.Display.println("BtnA: Screen Toggle | BtnB: < BACK");
            needsBackgroundRedraw = false;
        }
        
        M5.Display.setCursor(0, 45);
        M5.Display.setTextSize(1);
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
        
        for(size_t i = 0; i < maxLogs; i++) {
            if (i < logs.size()) {
                String padded = logs[i];
                while(padded.length() < 30) padded += " ";
                M5.Display.println(padded);
            } else {
                M5.Display.println("                              ");
            }
        }
    }

    void loop(bool& returnToMenu) {
        if (M5.BtnB.wasPressed()) {
            returnToMenu = true;
            return;
        }

        if (M5.BtnA.wasPressed()) {
            screenHidden = !screenHidden;
            needsBackgroundRedraw = true;
            draw(true);
        }
    }
};
