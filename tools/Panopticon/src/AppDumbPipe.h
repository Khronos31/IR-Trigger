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
#include "AppInterface.h"
#include <AsyncJson.h>

// Forward declaration of parsing helper from main.cpp
bool parseAndSanitizeTxJson(JsonVariant& json, std::vector<uint16_t>& outRaw, String& outCode);

class AppDumbPipe : public AppInterface {
private:
    std::vector<String> logs;
    const int maxLogs = 8; // Restored to more lines for 2-line display
    bool screenHidden = false;
    bool needsBackgroundRedraw = true;

    IRsend* irsend = nullptr;
    IRrecv* irrecv = nullptr;
    std::vector<uint16_t> pendingTxRaw;
    String pendingTxCodeStr = ""; // Holds beautiful string like "SWITCHBOT 0x12345678"
    bool hasPendingTx = false;
    
    AsyncCallbackJsonWebHandler* txHandler = nullptr;

public:
    AppDumbPipe() {}

    virtual const char* getName() const override {
        return "1. Dumb Pipe";
    }

    virtual void init(IRsend* tx, IRrecv* rx) override {
        irsend = tx;
        irrecv = rx;
    }

    virtual void onTxReceived(const std::vector<uint16_t>& raw, const String& displayCode) override {
        pendingTxRaw = raw;
        pendingTxCodeStr = displayCode;
        hasPendingTx = true;
    }

    virtual void setup() override {
        logs.clear();
        screenHidden = false;
        needsBackgroundRedraw = true;
        
        addLog("SYS: DUMB PIPE READY");
    }

    virtual void setupWeb(AsyncWebServer* server) override {
        if (txHandler) return; // Safety check
        
        txHandler = new AsyncCallbackJsonWebHandler("/tx", [this](AsyncWebServerRequest *request, JsonVariant &json) {
            std::vector<uint16_t> tempRaw;
            String displayCode;
            
            if (!parseAndSanitizeTxJson(json, tempRaw, displayCode)) {
                request->send(400, "text/plain", "Bad Request: Missing 'raw' array");
                return;
            }
            
            this->onTxReceived(tempRaw, displayCode);
            request->send(200, "text/plain", "OK: TX Loaded into Dumb Pipe");
        });
        
        server->addHandler(txHandler);
    }

    virtual void teardownWeb(AsyncWebServer* server) override {
        if (txHandler) {
            server->removeHandler(txHandler);
            delete txHandler;
            txHandler = nullptr;
        }
    }

    void addLog(const String& msg) {
        String logLine = msg;
        // Truncate in the middle with "..." if the hex code is incredibly long (e.g. 88bit+ air conditioners)
        if (logLine.length() > 35) {
            int len = logLine.length();
            logLine = logLine.substring(0, 15) + "..." + logLine.substring(len - 17);
        }
        
        logs.push_back(logLine);
        while (logs.size() > maxLogs) {
            logs.erase(logs.begin());
        }
    }

    virtual void draw(bool fullDraw = false) override {
        if (screenHidden) {
            // No drawing updates when screen is effectively turned off (backlight 0)
            return;
        }
        
        if (fullDraw || needsBackgroundRedraw) {
            M5.Display.fillScreen(TFT_BLACK);
            M5.Display.setCursor(0, 5);
            M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
            M5.Display.setTextSize(2);
            M5.Display.println("[DUMB PIPE]");
            M5.Display.println("-------------");
            needsBackgroundRedraw = false;
        }
        
        M5.Display.setCursor(0, 45);
        M5.Display.setTextSize(1); // Restored original size to fit more info
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
        
        for(size_t i = 0; i < maxLogs; i++) {
            if (i < logs.size()) {
                String padded = logs[i];
                while(padded.length() < 35) padded += " ";
                M5.Display.println(padded);
            } else {
                M5.Display.println("                                   "); // 35 spaces
            }
        }
    }

    virtual void loop(bool& returnToMenu) override {
        if (M5.BtnB.wasReleased()) {
            if (screenHidden) {
                M5.Display.setBrightness(128); // Ensure screen comes back on when returning to menu
                screenHidden = false;
            }
            returnToMenu = true;
            return;
        }

        if (M5.BtnA.wasPressed()) {
            screenHidden = !screenHidden;
            if (screenHidden) {
                M5.Display.setBrightness(0); // Turn off backlight completely
            } else {
                M5.Display.setBrightness(128); // Turn backlight back on
                needsBackgroundRedraw = true;
                draw(true);
            }
        }

        // TX Processing
        if (hasPendingTx) {
            if (irsend) {
                // 1. Temporarily disable IR reception to prevent "self-feedback loop" where the ESP32
                // receives its own bright IR flashes and triggers endless RX interrupts, starving RMT buffers.
                if (irrecv) {
                    irrecv->disableIRIn();
                }

                // 2. Apply fine-grained hardware calibration for ESP32-S3 + U002 IR Unit
                //    Analysis shows a physical bias where Marks are shortened by ~30us and Spaces extended by ~30us.
                std::vector<uint16_t> calibratedRaw = pendingTxRaw;
                for (size_t i = 0; i < calibratedRaw.size(); i++) {
                    if (i % 2 == 0) { // Mark (ON)
                        calibratedRaw[i] += 30;
                    } else { // Space (OFF)
                        if (calibratedRaw[i] > 30) {
                            calibratedRaw[i] -= 30;
                        }
                    }
                }

                // 3. Yield CPU to background tasks (like WiFi) before engaging heavy RMT transmission
                delay(20);
                
                // 4. Send the signal via RMT hardware
                //    ESP32-S3 clock scaling / RMT divider issues cause 38kHz requested to actually output as ~35kHz.
                //    We intentionally request 41kHz here to achieve a ~39kHz carrier frequency in the physical world,
                //    which passes through 38kHz-40kHz bandpass filters much better than 37kHz.
                irsend->sendRaw(calibratedRaw.data(), calibratedRaw.size(), 41);
                
                // 5. Block the main thread (UI drawing) while RMT interrupts are busy transmitting.
                // This ensures we don't interfere with the RMT buffer refills during long signals (e.g. AC codes).
                // Average pulse is ~1ms (mark+space), so pendingTxRaw.size() ms is a safe blocking window.
                delay(pendingTxRaw.size() + 20);

                // 5. Re-enable reception safely
                if (irrecv) {
                    irrecv->enableIRIn();
                }

                if (!pendingTxCodeStr.isEmpty() && !pendingTxCodeStr.startsWith("RAW_")) {
                    int spaceIdx = pendingTxCodeStr.indexOf(' ');
                    if (spaceIdx > 0) {
                        addLog("TX: " + pendingTxCodeStr.substring(0, spaceIdx));
                        addLog("    " + pendingTxCodeStr.substring(spaceIdx + 1));
                    } else {
                        addLog("TX: " + pendingTxCodeStr);
                    }
                } else {
                    addLog("TX: " + String(pendingTxRaw.size()) + " pls");
                }
            }
            hasPendingTx = false;
            draw();
        }
    }

    // Adapt signature to match AppInterface (ignoring rawVector/ts since Dumb Pipe just posts JSON)
    virtual void onIrReceived(const String& hexCode, const String& rawJson, const std::vector<uint16_t>& rawVector, uint32_t ts) override {
        if (!hexCode.isEmpty() && !hexCode.startsWith("RAW_")) {
            int spaceIdx = hexCode.indexOf(' ');
            if (spaceIdx > 0) {
                addLog("RX: " + hexCode.substring(0, spaceIdx));
                addLog("    " + hexCode.substring(spaceIdx + 1));
            } else {
                addLog("RX: " + hexCode);
            }
        } else {
            String countStr = hexCode.startsWith("RAW_") ? hexCode : "Unknown";
            countStr.replace("RAW_", "");
            addLog("RX: " + countStr + " pls");
        }
        draw();

        // Async Post to HA Webhook via global queue
        String payload = "{\"raw\":" + rawJson + "}";
        enqueueWebhook(payload);
    }
};
