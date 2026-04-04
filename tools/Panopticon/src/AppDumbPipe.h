#pragma once
#include <M5Unified.h>
#include <vector>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include <ESPAsyncWebServer.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "Config.h"

class AppDumbPipe {
private:
    std::vector<String> logs;
    const int maxLogs = 5;
    bool screenHidden = false;
    bool needsBackgroundRedraw = true;

private:
    IRsend* irsend = nullptr;
    std::vector<uint16_t> pendingTxRaw;
    bool hasPendingTx = false;

public:
    AppDumbPipe() {}

    void init(IRsend* tx) {
        irsend = tx;
    }

    void setPendingTx(const std::vector<uint16_t>& raw) {
        pendingTxRaw = raw;
        hasPendingTx = true;
    }

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
        if (M5.BtnB.wasReleased()) {
            returnToMenu = true;
            return;
        }

        if (M5.BtnA.wasPressed()) {
            screenHidden = !screenHidden;
            needsBackgroundRedraw = true;
            draw(true);
        }

        // TX Processing
        if (hasPendingTx) {
            if (irsend) {
                irsend->sendRaw(pendingTxRaw.data(), pendingTxRaw.size(), 38);
                String txSnippet = "TX:[";
                size_t maxTxItems = (pendingTxRaw.size() < 4) ? pendingTxRaw.size() : 4;
                for (size_t i = 0; i < maxTxItems; i++) {
                    txSnippet += String(pendingTxRaw[i]);
                    if (i < 3 && i < pendingTxRaw.size() - 1) txSnippet += ",";
                }
                if (pendingTxRaw.size() > 4) txSnippet += "...]";
                else txSnippet += "]";
                addLog(txSnippet);
            }
            hasPendingTx = false;
            draw();
        }

    }

    void onIrReceived(const String& hexCode, const String& rawJson) {
        // Create snippet for display (e.g. RX:[9000,4500...])
        String rxSnippet = "RX:";
        int snippetLen = (rawJson.length() > 20) ? 20 : rawJson.length();
        rxSnippet += rawJson.substring(0, snippetLen);
        if (rawJson.length() > 20) rxSnippet += "...]";

        // Post to HA Webhook securely
        HTTPClient http;
        http.begin(WEBHOOK_URL);
        http.setTimeout(HTTP_TIMEOUT_MS);
        http.addHeader("Content-Type", "application/json");
        
        String payload = "{\"raw\":" + rawJson + "}";
        int httpResponseCode = http.POST(payload);
        http.end();

        addLog(rxSnippet);
        if (httpResponseCode > 0) {
            addLog(" -> OK: HTTP " + String(httpResponseCode));
        } else {
            addLog(" -> ERR: " + http.errorToString(httpResponseCode));
        }
        draw();
    }
};
