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

// Global Webhook Queue (Producer-Consumer)
QueueHandle_t globalWebhookQueue = nullptr;

void globalWebhookTask(void* pvParameters) {
    QueueHandle_t queue = (QueueHandle_t)pvParameters;
    String* payloadPtr;

    while (true) {
        if (xQueueReceive(queue, &payloadPtr, portMAX_DELAY) == pdTRUE) {
            if (payloadPtr) {
                HTTPClient http;
                http.begin(WEBHOOK_URL);
                http.setTimeout(HTTP_TIMEOUT_MS);
                http.addHeader("Content-Type", "application/json");

                int httpResponseCode = http.POST(*payloadPtr);
                http.end();

                if (httpResponseCode <= 0) {
                    Serial.printf("Async Webhook POST ERR: %s\n", http.errorToString(httpResponseCode).c_str());
                }

                delete payloadPtr; // Free memory!
            }
        }
    }
}

// Helper: Safely enqueue a webhook payload
void enqueueWebhook(const String& payload) {
    if (globalWebhookQueue != nullptr) {
        String* payloadPtr = new String(payload);
        if (xQueueSend(globalWebhookQueue, &payloadPtr, 0) != pdTRUE) {
            delete payloadPtr; // Queue full
            Serial.println("Async Webhook POST ERR: Queue Full");
        }
    }
}

// Custom decoder for unknown AEHA-like signals
String decode_custom_aeha(const std::vector<uint16_t>& raw) {
    // Basic AEHA leader is ~3200us ON, ~1600us OFF.
    // Need at least leader (2) + a few bits (e.g. 10 bits = 20)
    if (raw.size() < 22) return "";

    auto check_tolerance = [](uint16_t val, uint16_t expected) {
        return (val >= expected * 0.7) && (val <= expected * 1.3);
    };

    if (!check_tolerance(raw[0], 3200) || !check_tolerance(raw[1], 1600)) {
        return "";
    }

    std::vector<uint8_t> bits;
    bits.reserve(256); // Support arbitrary length (e.g. 88bit+)

    for (size_t i = 2; i < raw.size() - 1; i += 2) {
        uint16_t mark = raw[i];
        uint16_t space = raw[i + 1];

        // Standard AEHA mark is ~400us. We tolerate from ~200us to ~800us.
        if (mark < 200 || mark > 800) {
            break; // Stop at first invalid mark
        }

        // Extremely long space indicates gap/repeat code (end of data)
        if (space > 5000) {
            break;
        }

        // Determine bit based on space length threshold.
        // Standard AEHA: bit0 ~400us, bit1 ~1200us.
        // Threshold around 800us cleanly separates 0 and 1.
        if (space < 800) {
            bits.push_back(0); // Bit 0
        } else {
            bits.push_back(1); // Bit 1
        }
    }

    // Only return if we decoded a reasonable amount of bits (e.g. 16 or more)
    if (bits.size() >= 16) {
        String hexStr = "";
        for (size_t i = 0; i < bits.size(); i += 8) {
            uint8_t byte_val = 0;
            // 8ビットチャンク内で、LSB First (下位ビットから詰める)
            for (size_t b_idx = 0; b_idx < 8 && (i + b_idx) < bits.size(); b_idx++) {
                if (bits[i + b_idx] == 1) {
                    byte_val |= (1 << b_idx);
                }
            }
            char hexByte[3];
            snprintf(hexByte, sizeof(hexByte), "%02X", byte_val);
            hexStr += String(hexByte);
        }
        return "AEHA 0x" + hexStr + " (" + String(bits.size()) + "bit)";
    }
    
    return "";
}

// Custom decoder for unknown NEC-like signals (varying bit lengths)
String decode_custom_switchbot(const std::vector<uint16_t>& raw) {
    // Basic NEC leader is ~9000us ON, ~4500us OFF.
    // Need at least leader (2) + a few bits (e.g. 10 bits = 20)
    if (raw.size() < 22) return "";

    auto check_tolerance = [](uint16_t val, uint16_t expected) {
        return (val >= expected * 0.7) && (val <= expected * 1.3);
    };

    if (!check_tolerance(raw[0], 9000) || !check_tolerance(raw[1], 4500)) {
        return "";
    }

    std::vector<uint8_t> bits;
    bits.reserve(256); // Support arbitrary length

    for (size_t i = 2; i < raw.size() - 1; i += 2) {
        uint16_t mark = raw[i];
        uint16_t space = raw[i + 1];

        // Standard NEC is ~560us, SwitchBot (NEC-L) is ~680us. 
        // We tolerate anything from 300us to 1000us as a valid mark.
        if (mark < 300 || mark > 1000) {
            break; // Stop at first invalid mark
        }

        // Extremely long space indicates gap/repeat code (end of data)
        if (space > 5000) {
            // In typical NEC, the last mark before the gap is just a stop bit, not data.
            break;
        }

        // Determine bit based on space length threshold (typical threshold is ~1200us-1500us)
        // Standard NEC: bit0 ~560, bit1 ~1680. SwitchBot: bit0 ~730, bit1 ~2150.
        // Threshold around 1400us cleanly separates 0 and 1 for both.
        if (space < 1400) {
            bits.push_back(0); // Bit 0
        } else {
            bits.push_back(1); // Bit 1
        }
    }

    // Only return if we decoded a reasonable amount of bits (e.g. 16 or more)
    if (bits.size() >= 16) {
        String hexStr = "";
        for (size_t i = 0; i < bits.size(); i += 8) {
            uint8_t byte_val = 0;
            // 8ビットチャンク内で、LSB First (下位ビットから詰める)
            for (size_t b_idx = 0; b_idx < 8 && (i + b_idx) < bits.size(); b_idx++) {
                if (bits[i + b_idx] == 1) {
                    byte_val |= (1 << b_idx);
                }
            }
            char hexByte[3];
            snprintf(hexByte, sizeof(hexByte), "%02X", byte_val);
            hexStr += String(hexByte);
        }
        return "SWITCHBOT 0x" + hexStr + " (" + String(bits.size()) + "bit)";
    }
    
    return "";
}

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

    // Initialize Global Webhook Queue and Task
    globalWebhookQueue = xQueueCreate(10, sizeof(String*));
    if (globalWebhookQueue != nullptr) {
        // Pin task to Core 0 (Network/Protocol Core) to free up Core 1 (UI/Arduino Core)
        xTaskCreatePinnedToCore(
            globalWebhookTask, "WebhookTask", 4096, (void*)globalWebhookQueue, 1, NULL, 0
        );
    }

    // Initialize IR hardware centrally with strict stability sequence
    pinMode(IR_RX_PIN, INPUT_PULLUP);
    delay(200); // Completely stabilize physical pin voltage before allowing interrupts

    irrecv = new IRrecv(IR_RX_PIN, 1024, 25, true);
    irsend = new IRsend(IR_TX_PIN);
    
    // Discard raw captures with less than 20 pulses to improve noise resistance
    irrecv->setUnknownThreshold(20);
    
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

        // Handle optional "code" parameter for beautiful UI display (e.g., "SWITCHBOT-12345678")
        String displayCode = "";
        if (json.as<JsonObject>().containsKey("code")) {
            String incomingCode = json["code"].as<String>();
            int hyphenIdx = incomingCode.indexOf('-');
            if (hyphenIdx > 0) {
                String protocol = incomingCode.substring(0, hyphenIdx);
                String hexVal = incomingCode.substring(hyphenIdx + 1);
                displayCode = protocol + " 0x" + hexVal;
            } else {
                displayCode = incomingCode; // Fallback
            }
        }

                        if (currentState == STATE_DUMB_PIPE && appDumbPipe) {
                            appDumbPipe->setPendingTx(tempRaw, displayCode);
                            request->send(200, "text/plain", "OK: Sent to Dumb Pipe");
                        } else if (currentState == STATE_SNIPER && appSniper) {
                            appSniper->loadSignalRaw(tempRaw);
                            
                            // Safe async webhook post via global queue
                            JsonDocument docOut;
                            docOut["Device"] = "Panopticon_Sniper";
                            docOut["Button"] = "Target_Locked";
                            JsonArray rawArrayOut = docOut["raw"].to<JsonArray>();
                            for (size_t i = 0; i < tempRaw.size(); i++) {
                                rawArrayOut.add(tempRaw[i]);
                            }
                            
                            String payload;
                            serializeJson(docOut, payload);
                            enqueueWebhook(payload);

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
        // Physical Noise Filter (Squelch)
        // Valid IR signals start with a long leader code (usually >3000us).
        // Discard anything starting with less than 1000us to prevent fake triggers from physical tapping/vibration.
        uint16_t firstPulseUs = (results.rawlen > 1) ? results.rawbuf[1] * kRawTick : 0;
        
        if (results.rawlen >= 10 && results.rawlen <= 1024 && firstPulseUs > 1000) { 
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

            String hexCode = "";
            if (results.decode_type != decode_type_t::UNKNOWN) {
                hexCode = typeToString(results.decode_type) + " 0x" + uint64ToString(results.value, 16);
            } else {
                hexCode = decode_custom_switchbot(rawVector);
                if (hexCode.isEmpty()) {
                    hexCode = decode_custom_aeha(rawVector);
                }
                if (hexCode.isEmpty()) {
                    hexCode = "RAW_" + String(results.rawlen - 1);
                }
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
