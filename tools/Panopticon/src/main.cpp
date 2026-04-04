#include <M5Unified.h>
#include "AppDumbPipe.h"
#include "AppSniper.h"
#include "AppSigintLog.h"

enum State {
    STATE_MENU,
    STATE_DUMB_PIPE,
    STATE_SNIPER,
    STATE_SIGINT_LOG
};

State currentState = STATE_MENU;
int menuCursor = 0;
const int MENU_ITEMS = 3;
const char* menuNames[] = {"1. Dumb Pipe", "2. Sniper", "3. Sigint Log"};
const State menuStates[] = {STATE_DUMB_PIPE, STATE_SNIPER, STATE_SIGINT_LOG};

bool btnBLongPressedHandled = false;
bool needsMenuRedraw = true;

#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include <IRutils.h>
#include "Config.h"

// Global pointers for ALL hardware and apps to ensure lazy initialization
IRrecv* irrecv = nullptr;
IRsend* irsend = nullptr;
decode_results results;

// Instantiate Apps
AppDumbPipe* appDumbPipe = nullptr;
AppSniper* appSniper = nullptr;
AppSigintLog* appSigintLog = nullptr;

void drawMenu(bool fullDraw = false) {
    if (fullDraw || needsMenuRedraw) {
        M5.Display.fillScreen(TFT_BLACK);
        M5.Display.setCursor(0, 5);
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
        M5.Display.setTextSize(2);
        M5.Display.println(" PANOPTICON OS");
        M5.Display.println("-------------");
        needsMenuRedraw = false;
    }
    
    M5.Display.setCursor(0, 45); // Y offset to avoid overdrawing header
    M5.Display.setTextSize(2);
    for (int i = 0; i < MENU_ITEMS; i++) {
        if (i == menuCursor) {
            M5.Display.setTextColor(TFT_BLACK, TFT_GREEN);
            M5.Display.print("> ");
        } else {
            M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
            M5.Display.print("  ");
        }
        String name = menuNames[i];
        while (name.length() < 15) {
            name += " ";
        }
        M5.Display.println(name);
    }
    
    // Draw connection status at bottom
    M5.Display.setCursor(0, M5.Display.height() - 15);
    M5.Display.setTextSize(1);
    if (WiFi.status() == WL_CONNECTED) {
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
        M5.Display.print("IP: ");
        M5.Display.println(WiFi.localIP().toString() + "        ");
    } else {
        M5.Display.setTextColor(TFT_RED, TFT_BLACK);
        M5.Display.println("Not Connected                   ");
    }
}

#include <WiFi.h>
#include <ESPAsyncWebServer.h>
#include <AsyncJson.h>
#include <ArduinoJson.h>
#include <IRutils.h>

const char* ssid = WIFI_SSID;
const char* password = WIFI_PASSWORD;

AsyncWebServer server(8080);

void setup() {
    auto cfg = M5.config();
    M5.begin(cfg);
    
    M5.Display.setRotation(1); // Set landscape
    M5.Display.setBrightness(128);
    
    M5.Display.fillScreen(TFT_BLACK);
    M5.Display.setCursor(0, 5);
    M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
    M5.Display.setTextSize(2);
    M5.Display.println(" Connecting Wi-Fi...");
    
    // Throw away initial unstable button states (debounce)
    for(int i=0; i<10; i++) {
        M5.update();
        delay(10);
    }

    // Initialize IR hardware centrally with strict stability sequence
    pinMode(IR_RX_PIN, INPUT_PULLUP);
    delay(200); // Completely stabilize physical pin voltage before allowing interrupts

    irrecv = new IRrecv(IR_RX_PIN, 1024, 25, true);
    irsend = new IRsend(IR_TX_PIN);
    irrecv->enableIRIn();
    irsend->begin();

    // Now safely instantiate App classes after OS runtime is fully awake
    appDumbPipe = new AppDumbPipe();
    appSniper = new AppSniper();
    appSigintLog = new AppSigintLog();

    appDumbPipe->init(irsend);
    appSniper->init(irsend);
    appSigintLog->init(irsend);

    WiFi.setHostname("Panopticon");
    WiFi.begin(ssid, password);
    unsigned long lastPrintTime = 0;
    while (WiFi.status() != WL_CONNECTED) {
        M5.update();
        if (M5.BtnB.wasPressed() || M5.BtnC.wasPressed() || M5.BtnA.wasPressed()) {
            WiFi.disconnect();
            Serial.println("\nWiFi Connection Cancelled.");
            M5.Display.println("\nCancelled.");
            delay(500);
            break;
        }
        
        if (millis() - lastPrintTime > 500) {
            M5.Display.print(".");
            Serial.print(".");
            lastPrintTime = millis();
        }
        delay(10);
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi Connected!");
        Serial.print("IP Address: ");
        Serial.println(WiFi.localIP());
    }

    AsyncCallbackJsonWebHandler* handler = new AsyncCallbackJsonWebHandler("/tx", [](AsyncWebServerRequest *request, JsonVariant &json) {
        if (!json.is<JsonObject>() || !json.as<JsonObject>().containsKey("raw")) {
            request->send(400, "text/plain", "Bad Request: Missing 'raw' array");
            return;
        }

        JsonArray rawArr = json["raw"].as<JsonArray>();
        std::vector<uint16_t> tempRaw;
        tempRaw.reserve(rawArr.size());
        for (JsonVariant v : rawArr) {
            tempRaw.push_back(abs(v.as<int>()));
        }

                        if (currentState == STATE_DUMB_PIPE && appDumbPipe) {
                            appDumbPipe->setPendingTx(tempRaw);
                            request->send(200, "text/plain", "OK: Sent to Dumb Pipe");
                        } else if (currentState == STATE_SNIPER && appSniper) {
                            appSniper->loadSignalRaw(tempRaw);
                            
                            // Send "Target_Locked" event to HA with raw array for converter compatibility
                            HTTPClient http;
                            http.begin(WEBHOOK_URL);
                            http.setTimeout(HTTP_TIMEOUT_MS);
                            http.addHeader("Content-Type", "application/json");

                            JsonDocument docOut;
                            docOut["Device"] = "Panopticon_Sniper";
                            docOut["Button"] = "Target_Locked";
                            
                            JsonArray rawArrayOut = docOut["raw"].to<JsonArray>();
                            for (size_t i = 0; i < tempRaw.size(); i++) {
                                rawArrayOut.add(tempRaw[i]);
                            }
                            
                            String payload;
                            serializeJson(docOut, payload);
                            http.POST(payload);
                            http.end();

                            request->send(200, "text/plain", "OK: Loaded into Sniper");
                        } else {
                            request->send(400, "text/plain", "App not ready to receive TX");
                        }
    });

    server.addHandler(handler);
    if (WiFi.status() == WL_CONNECTED) {
        server.begin();
        Serial.println("HTTP Server started on port 8080");
    } else {
        Serial.println("Offline Mode. Server not started.");
    }

    drawMenu(true);
    Serial.println("Panopticon initialized.");
}

void loop() {
    M5.update();
    
    if (currentState == STATE_MENU) {
        // Handle Long Press (Reverse Scroll)
        if (M5.BtnB.pressedFor(500)) {
            if (!btnBLongPressedHandled) {
                menuCursor--;
                if (menuCursor < 0) menuCursor = MENU_ITEMS - 1;
                drawMenu(); // only updates text with bg color
                btnBLongPressedHandled = true;
            }
        } 
        // Handle Short Press (Forward Scroll)
        else if (M5.BtnB.wasReleased() && !btnBLongPressedHandled) {
            menuCursor++;
            if (menuCursor >= MENU_ITEMS) menuCursor = 0;
            drawMenu();
        }

        // Reset long press flag on release
        if (M5.BtnB.isReleased()) {
            btnBLongPressedHandled = false;
        }
        
        // Enter App
        if (M5.BtnA.wasPressed()) {
            currentState = menuStates[menuCursor];
            // Initialize App
            if (currentState == STATE_DUMB_PIPE && appDumbPipe) {
                appDumbPipe->setup();
                appDumbPipe->draw(true);
            } else if (currentState == STATE_SNIPER && appSniper) {
                appSniper->setup();
                appSniper->draw(true);
            } else if (currentState == STATE_SIGINT_LOG && appSigintLog) {
                appSigintLog->setup();
                appSigintLog->draw(true);
            }
        }
    } else {
        bool returnToMenu = false;
        
        // Dispatch to appropriate app loop
        switch (currentState) {
            case STATE_DUMB_PIPE:
                if (appDumbPipe) appDumbPipe->loop(returnToMenu);
                break;
            case STATE_SNIPER:
                if (appSniper) appSniper->loop(returnToMenu);
                break;
            case STATE_SIGINT_LOG:
                if (appSigintLog) appSigintLog->loop(returnToMenu);
                break;
            default:
                break;
        }
        
        // Handle transition back to menu
        if (returnToMenu) {
            currentState = STATE_MENU;
            needsMenuRedraw = true;
            drawMenu(true);
        }
    }

    // --- Centralized IR Receive & Push ---
    if (irrecv && irrecv->decode(&results)) {
        if (results.rawlen >= 10 && results.rawlen <= 1024) { 
            String rawJson;
            rawJson.reserve(results.rawlen * 6 + 10);
            rawJson = "[";
            
            std::vector<uint16_t> rawVector;
            rawVector.reserve(results.rawlen - 1);
            
            for (uint16_t i = 1; i < results.rawlen; i++) {
                uint16_t us = results.rawbuf[i] * kRawTick;
                rawJson += String(us);
                rawVector.push_back(us);
                if (i < results.rawlen - 1) rawJson += ",";
            }
            rawJson += "]";

            String hexCode = resultToHumanReadableBasic(&results);
            if (hexCode.isEmpty() || hexCode == "UNKNOWN") {
                 hexCode = "RAW_" + String(results.rawlen - 1);
            }

            if (currentState == STATE_DUMB_PIPE && appDumbPipe) {
                appDumbPipe->onIrReceived(hexCode, rawJson);
            } else if (currentState == STATE_SIGINT_LOG && appSigintLog) {
                appSigintLog->onIrReceived(hexCode, rawJson, rawVector, millis());
            }
        }
        irrecv->resume();
    }
}
