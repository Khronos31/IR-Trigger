#pragma once
#include <M5Unified.h>
#include <vector>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include <ESPAsyncWebServer.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

const uint16_t IR_TX_PIN = 46;
const uint16_t IR_RX_PIN = 42;
const char* WEBHOOK_URL = "http://192.168.1.X:8123/api/webhook/rx_panopticon";

class AppDumbPipe {
private:
    std::vector<String> logs;
    const int maxLogs = 5;
    bool screenHidden = false;
    bool needsBackgroundRedraw = true;

    IRrecv irrecv;
    IRsend irsend;
    decode_results results;
    AsyncWebServer server;

    std::vector<uint16_t> pendingTxRaw;
    bool hasPendingTx = false;

    bool isServerStarted = false;

public:
    AppDumbPipe() : irrecv(IR_RX_PIN, 1024, 15, true), irsend(IR_TX_PIN), server(8080) {}

    void setup() {
        logs.clear();
        screenHidden = false;
        needsBackgroundRedraw = true;
        
        // Stabilize floating RX pin to prevent infinite dummy interrupt crashes
        pinMode(IR_RX_PIN, INPUT_PULLUP);
        
        irrecv.enableIRIn();
        irsend.begin();

        if (!isServerStarted) {
            server.on("/tx", HTTP_POST, [](AsyncWebServerRequest *request){}, NULL, 
                [this](AsyncWebServerRequest *request, uint8_t *data, size_t len, size_t index, size_t total) {
                    if (index == 0) {
                        JsonDocument doc;
                        DeserializationError error = deserializeJson(doc, data, len);
                        if (!error && doc.containsKey("raw")) {
                            JsonArray rawArr = doc["raw"].as<JsonArray>();
                            std::vector<uint16_t> tempRaw;
                            tempRaw.reserve(rawArr.size());
                            for (JsonVariant v : rawArr) {
                                tempRaw.push_back(abs(v.as<int>())); 
                            }
                            this->pendingTxRaw = tempRaw;
                            this->hasPendingTx = true;
                        }
                        request->send(200, "text/plain", "OK");
                    }
                }
            );
            server.begin();
            isServerStarted = true;
        }

        addLog("SYS: DUMB PIPE READY");
        addLog("HTTP: Port 8080");
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

        // TX Processing
        if (hasPendingTx) {
            irsend.sendRaw(pendingTxRaw.data(), pendingTxRaw.size(), 38);
            addLog("TX: " + String(pendingTxRaw.size()) + " pulses");
            hasPendingTx = false;
            draw();
        }

        // RX Processing
        if (irrecv.decode(&results)) {
            // Ignore noise (very short pulse arrays) to prevent OOM / continuous HTTP requests
            if (results.rawlen > 20) { 
                String rawJson;
                rawJson.reserve(results.rawlen * 6 + 10); // Prevent heap fragmentation (OOM)
                rawJson = "[";
                for (uint16_t i = 1; i < results.rawlen; i++) {
                    rawJson += String(results.rawbuf[i] * kRawTick);
                    if (i < results.rawlen - 1) rawJson += ",";
                }
                rawJson += "]";

                // Post to HA Webhook securely
                HTTPClient http;
                http.begin(WEBHOOK_URL);
                http.addHeader("Content-Type", "application/json");
                
                String payload = "{\"raw\":" + rawJson + "}";
                int httpResponseCode = http.POST(payload);
                http.end();

                addLog("RX: " + String(results.rawlen - 1) + " pulses");
                if (httpResponseCode > 0) {
                    addLog(" -> OK: HTTP " + String(httpResponseCode));
                } else {
                    addLog(" -> ERR: " + http.errorToString(httpResponseCode));
                }
                draw();
            }
            irrecv.resume();
        }
    }
};
