#pragma once
#include <M5Unified.h>
#include <vector>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include "Config.h"
#include "AppInterface.h"
#include <AsyncJson.h>

// Forward declaration of parsing helper from main.cpp
bool parseAndSanitizeTxJson(JsonVariant& json, std::vector<uint16_t>& outRaw, String& outCode);

// Forward declaration of enqueue helper from main.cpp
void enqueueWebhook(const String& payload);

class AppSniper : public AppInterface {
private:
    std::vector<uint16_t> loadedRaw;
    bool hasLoadedRaw = false;
    bool needsBackgroundRedraw = true;
    uint32_t visualFeedbackEndTime = 0;
    IRsend* irsend = nullptr;
    IRrecv* irrecv = nullptr;
    
    AsyncCallbackJsonWebHandler* txHandler = nullptr;

public:
    AppSniper() {}

    virtual const char* getName() const override {
        return "2. Sniper";
    }

    virtual void init(IRsend* tx, IRrecv* rx) override {
        irsend = tx;
        irrecv = rx;
    }

    virtual void setup() override {
        loadedRaw.clear();
        hasLoadedRaw = false;
        needsBackgroundRedraw = true;
        visualFeedbackEndTime = 0;
    }

    virtual void setupWeb(AsyncWebServer* server) override {
        if (txHandler) return;
        
        txHandler = new AsyncCallbackJsonWebHandler("/tx", [this](AsyncWebServerRequest *request, JsonVariant &json) {
            std::vector<uint16_t> tempRaw;
            String displayCode;
            
            if (!parseAndSanitizeTxJson(json, tempRaw, displayCode)) {
                request->send(400, "text/plain", "Bad Request: Missing 'raw' array");
                return;
            }
            
            this->onTxReceived(tempRaw, displayCode);
            
            // Safe async webhook post via global queue
            JsonDocument docOut;
            docOut["Device"] = "Panopticon_Sniper";
            docOut["Button"] = "Target_Locked";
            JsonArray rawArrayOut = docOut["raw"].to<JsonArray>();
            for (size_t k = 0; k < tempRaw.size(); k++) rawArrayOut.add(tempRaw[k]);
            
            String payload;
            serializeJson(docOut, payload);
            enqueueWebhook(payload);

            request->send(200, "text/plain", "OK: Loaded into Sniper");
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

    virtual void onTxReceived(const std::vector<uint16_t>& raw, const String& displayCode) override {
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
                    // Disable RX to prevent self-feedback loop during TX
                    if (irrecv) {
                        irrecv->disableIRIn();
                    }

                    std::vector<uint16_t> calibratedRaw = loadedRaw;
                    for (size_t i = 0; i < calibratedRaw.size(); i++) {
                        if (i % 2 == 0) {
                            calibratedRaw[i] += 30;
                        } else {
                            if (calibratedRaw[i] > 30) {
                                calibratedRaw[i] -= 30;
                            }
                        }
                    }

                    // Yield CPU to background tasks (like WiFi) before engaging heavy RMT transmission
                    delay(20);
                    
                    // ESP32-S3 clock scaling / RMT divider issues cause 38kHz requested to actually output as ~35kHz.
                    // We intentionally request 41kHz here to achieve a ~39kHz carrier frequency in the physical world,
                    // which passes through 38kHz-40kHz bandpass filters much better than 37kHz.
                    irsend->sendRaw(calibratedRaw.data(), calibratedRaw.size(), 41);
                    DEBUG_PRINTF("SNIPER FIRED: %d pulses\n", calibratedRaw.size());
                    
                    // Block the main thread (UI drawing) while RMT interrupts are busy transmitting.
                    delay(calibratedRaw.size() + 20);

                    // Re-enable RX
                    if (irrecv) {
                        irrecv->enableIRIn();
                    }
                }
                hasLoadedRaw = false; 
                
                // Flash screen red and set timer
                M5.Display.fillScreen(TFT_RED);
                visualFeedbackEndTime = millis() + 50;
            }
        }
    }
};
