#include <M5Unified.h>
#include <vector>
#include "AppInterface.h"
#include "AppDumbPipe.h"
#include "AppSniper.h"
#include "AppSigintLog.h"
#include "AppAPITester.h"
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include <IRutils.h>
#include "Config.h"

// 状態管理（-1 はメニュー、0 以上は apps 配列のインデックス）
int currentAppIndex = -1;
int menuCursor = 0;

bool btnBLongPressedHandled = false;
bool needsMenuRedraw = true;

// Find My Panopticon variables
bool isFindingMe = false;
uint32_t nextBeepTime = 0;

// アプリケーション・プラグイン管理リスト
std::vector<AppInterface*> apps;

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

// -----------------------------------------------------------------------------------------
// Centralized IR Transmission Sequence (Hardware Calibration & Protection)
// -----------------------------------------------------------------------------------------
void safe_ir_send(IRsend* tx, IRrecv* rx, const std::vector<uint16_t>& rawData) {
    if (!tx || rawData.empty()) return;

    // 1. Temporarily disable IR reception to prevent "self-feedback loop" where the ESP32
    //    receives its own bright IR flashes and triggers endless RX interrupts, starving RMT buffers.
    if (rx) {
        rx->disableIRIn();
    }

    // 2. Apply fine-grained hardware calibration for ESP32-S3 + U002 IR Unit.
    //    Analysis shows a physical bias where Marks are shortened by ~30us and Spaces extended by ~30us.
    std::vector<uint16_t> calibratedRaw = rawData;
    for (size_t i = 0; i < calibratedRaw.size(); i++) {
        if (i % 2 == 0) { // Mark (ON)
            calibratedRaw[i] += 30;
        } else {          // Space (OFF)
            if (calibratedRaw[i] > 30) {
                calibratedRaw[i] -= 30;
            }
        }
    }

    // 3. Yield CPU to background tasks (like WiFi) before engaging heavy RMT transmission.
    delay(20);

    // 4. Send the signal via RMT hardware.
    //    ESP32-S3 clock scaling / RMT divider issues cause 38kHz requested to actually output as ~35kHz.
    //    We intentionally request 41kHz here to achieve a ~39kHz carrier frequency in the physical world,
    //    which passes through 38kHz-40kHz bandpass filters much better than 37kHz.
    tx->sendRaw(calibratedRaw.data(), calibratedRaw.size(), 41);

    // 5. Block the main thread (UI drawing) while RMT interrupts are busy transmitting.
    //    This ensures we don't interfere with the RMT buffer refills during long signals (e.g. AC codes).
    //    Average pulse is ~1ms (mark+space), so calibratedRaw.size() ms is a safe blocking window.
    delay(calibratedRaw.size() + 20);

    // 6. Re-enable reception safely.
    if (rx) {
        rx->enableIRIn();
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
    for (size_t i = 0; i < apps.size(); i++) {
        if (i == menuCursor) {
            M5.Display.setTextColor(TFT_BLACK, TFT_GREEN);
            M5.Display.print("> ");
        } else {
            M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
            M5.Display.print("  ");
        }
        String name = apps[i]->getName();
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
#include <LittleFS.h>

const char* ssid = WIFI_SSID;
const char* password = WIFI_PASSWORD;

AsyncWebServer server(8080);

void setup() {
    auto cfg = M5.config();
    M5.begin(cfg);
    
    // Initialize LittleFS for Sigint logging
    if (!LittleFS.begin(true)) {
        Serial.println("LittleFS Mount Failed");
    } else {
        Serial.println("LittleFS Mounted Successfully");
    }

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
    
    // For ESP32, IRsend constructor: IRsend(uint16_t pin, bool inverted = false, bool use_modulation = true)
    // Unfortunately, we cannot dynamically allocate RMT memory blocks via standard IRremoteESP8266 API easily.
    // However, we can ensure the task that sends the IR signal is not preempted by placing the array in contiguous memory.
    irsend = new IRsend(IR_TX_PIN);
    
    // Discard raw captures with less than 20 pulses to improve noise resistance
    irrecv->setUnknownThreshold(20);
    
    irrecv->enableIRIn();
    irsend->begin();

    // Safely instantiate and register all App plugins
    apps.push_back(new AppDumbPipe());
    apps.push_back(new AppSniper());
    apps.push_back(new AppSigintLog());
    apps.push_back(new AppAPITester());

    // Initialize all apps with IR hardware
    for (auto app : apps) {
        app->init(irsend, irrecv);
    }

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

    // ==============================================================================
    // Permanent, Centralized /tx Webhook Handler
    // ==============================================================================
    AsyncCallbackJsonWebHandler* handler = new AsyncCallbackJsonWebHandler("/tx", [](AsyncWebServerRequest *request, JsonVariant &json) {
        if (!json.is<JsonObject>() || !json["raw"].is<JsonArray>()) {
            request->send(400, "text/plain", "Bad Request: Missing 'raw' array");
            return;
        }

        JsonArray rawArr = json["raw"].as<JsonArray>();
        std::vector<uint16_t> tempRaw;
        tempRaw.reserve(rawArr.size());
        
        for (JsonVariant v : rawArr) {
            uint32_t val = abs(v.as<int>()); // safely cast int to avoid negative values
            
            // 1. RMT Crash Protection
            // A pulse of length 0 will crash the RMT driver or cause an infinite loop.
            // It indicates data corruption, so we truncate the array here.
            if (val == 0) {
                DEBUG_PRINTLN("TX Sanitizer: Invalid 0-pulse detected. Truncating payload.");
                break;
            }
            
            // 2. RMT Overflow Protection
            // ESP32 RMT uses 15-bit representation (~32767us max per item).
            // A long gap like 40000us (NEC repeat) or a 65535 overflow will break transmission.
            // Clip to 30000us max to preserve the "gap" nature safely.
            if (val > 30000) {
                val = 30000;
            }
            
            tempRaw.push_back(static_cast<uint16_t>(val));
        }

        // 3. RMT hardware expects Mark and Space to come in pairs (even size).
        if (tempRaw.size() % 2 != 0) {
            tempRaw.push_back(10000); // 10ms dummy space
        }

        // Handle optional "code" parameter for beautiful UI display
        String displayCode = "";
        if (json["code"].is<const char*>()) {
            String incomingCode = json["code"].as<String>();
            int hyphenIdx = incomingCode.indexOf('-');
            if (hyphenIdx > 0) {
                String protocol = incomingCode.substring(0, hyphenIdx);
                String hexVal = incomingCode.substring(hyphenIdx + 1);
                displayCode = protocol + " 0x" + hexVal;
            } else {
                displayCode = incomingCode; 
            }
        }

        // Route the clean, sanitized TX signal to the currently active app
        if (currentAppIndex >= 0 && currentAppIndex < apps.size()) {
            String appName = apps[currentAppIndex]->getName();
            
            // Allow only apps that are designed to receive TX payloads
            if (appName.indexOf("Dumb Pipe") >= 0 || 
                appName.indexOf("API Tester") >= 0 || 
                appName.indexOf("Sniper") >= 0) {
                
                apps[currentAppIndex]->onTxReceived(tempRaw, displayCode);
                request->send(200, "text/plain", "OK: TX Sent to App (" + appName + ")");
                return;
            }
        }

        request->send(400, "text/plain", "App not ready to receive TX");
    });

    server.addHandler(handler);

    // Endpoints for "Find My Panopticon"
    server.on("/beep", HTTP_GET, [](AsyncWebServerRequest *request) {
        isFindingMe = true;
        M5.Speaker.setVolume(64); // Ensure speaker is loud enough
        request->send(200, "text/plain", "BEEPING! Press any button to stop.");
    });
    
    server.on("/found", HTTP_GET, [](AsyncWebServerRequest *request) {
        isFindingMe = false;
        M5.Speaker.stop();
        request->send(200, "text/plain", "Glad you found me!");
    });

    // Endpoint to list saved logs (Sigint & API Tests)
    server.on("/logs", HTTP_GET, [](AsyncWebServerRequest *request) {
        String html = "<html><body><h2>Panopticon Logs</h2><ul>";
        File root = LittleFS.open("/");
        File file = root.openNextFile();
        bool hasLogs = false;
        while (file) {
            String fileName = String(file.name());
            // Remove any leading slash just in case LittleFS provides one
            if (fileName.startsWith("/")) fileName = fileName.substring(1);
            
            if ((fileName.startsWith("sigint_") || fileName.startsWith("tx_test_")) && fileName.endsWith(".txt")) {
                hasLogs = true;
                html += "<li><a href='/download?file=" + fileName + "'>" + fileName + "</a> (" + String(file.size()) + " bytes)</li>";
            }
            file = root.openNextFile();
        }
        if (!hasLogs) {
            html += "<p>No logs found.</p>";
        }
        html += "</ul>";
        html += "<form action='/logs/clear' method='POST'><button type='submit' style='background:red;color:white;'>Clear All Logs</button></form>";
        html += "</body></html>";
        request->send(200, "text/html", html);
    });

    // Endpoint for forced download of log files
    server.on("/download", HTTP_GET, [](AsyncWebServerRequest *request) {
        if (request->hasParam("file")) {
            String fileName = request->getParam("file")->value();
            if (!fileName.startsWith("/")) {
                fileName = "/" + fileName;
            }
            if (LittleFS.exists(fileName)) {
                // Read into memory and force download as attachment
                File file = LittleFS.open(fileName, "r");
                if (file) {
                    String content = file.readString();
                    file.close();
                    
                    AsyncWebServerResponse *response = request->beginResponse(200, "text/plain", content);
                    response->addHeader("Content-Disposition", "attachment; filename=\"" + fileName.substring(1) + "\"");
                    request->send(response);
                } else {
                    request->send(500, "text/plain", "Failed to open file: " + fileName);
                }
            } else {
                request->send(404, "text/plain", "File not found: " + fileName);
            }
        } else {
            request->send(400, "text/plain", "Missing file parameter");
        }
    });

    // Endpoint to clear all logs safely
    server.on("/logs/clear", HTTP_POST, [](AsyncWebServerRequest *request) {
        File root = LittleFS.open("/");
        File file = root.openNextFile();
        std::vector<String> filesToDelete;
        
        while (file) {
            String fileName = String(file.name());
            if ((fileName.startsWith("sigint_") || fileName.startsWith("tx_test_")) && fileName.endsWith(".txt")) {
                if (!fileName.startsWith("/")) fileName = "/" + fileName;
                filesToDelete.push_back(fileName);
            }
            file = root.openNextFile();
        }
        
        for (const String& f : filesToDelete) {
            LittleFS.remove(f);
        }
        
        // Return a script to redirect back to the logs page after clearing
        String html = "<html><body><script>alert('Cleared " + String(filesToDelete.size()) + " log files.'); window.location.href='/logs';</script></body></html>";
        request->send(200, "text/html", html);
    });

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

    // Check for any button press (including power) to stop finding me
    if (isFindingMe && (M5.BtnA.wasPressed() || M5.BtnB.wasPressed() || M5.BtnC.wasPressed() || M5.BtnPWR.wasPressed())) {
        isFindingMe = false;
        M5.Speaker.stop();
    }

    // Continuous non-blocking beep logic
    if (isFindingMe) {
        if (millis() > nextBeepTime) {
            M5.Speaker.tone(2000, 100); // High pitch beep for 100ms
            nextBeepTime = millis() + 500; // Repeat every 500ms
        }
    }
    
    if (currentAppIndex == -1) { // -1 means STATE_MENU
        // Handle Long Press (Reverse Scroll)
        if (M5.BtnB.pressedFor(500)) {
            if (!btnBLongPressedHandled) {
                menuCursor--;
                if (menuCursor < 0) menuCursor = apps.size() - 1;
                drawMenu(); // only updates text with bg color
                btnBLongPressedHandled = true;
            }
        } 
        // Handle Short Press (Forward Scroll)
        else if (M5.BtnB.wasReleased() && !btnBLongPressedHandled) {
            menuCursor++;
            if (menuCursor >= apps.size()) menuCursor = 0;
            drawMenu();
        }

        // Reset long press flag on release
        if (M5.BtnB.isReleased()) {
            btnBLongPressedHandled = false;
        }
        
        // Enter App
        if (M5.BtnA.wasPressed()) {
            if (apps.size() > 0 && menuCursor >= 0 && menuCursor < apps.size()) {
                currentAppIndex = menuCursor;
                apps[currentAppIndex]->setup();
                apps[currentAppIndex]->draw(true);
            }
        }
    } else { // An app is currently active
        bool returnToMenu = false;
        
        if (currentAppIndex >= 0 && currentAppIndex < apps.size()) {
            apps[currentAppIndex]->loop(returnToMenu);
        } else {
            returnToMenu = true; // Failsafe
        }
        
        // Handle transition back to menu
        if (returnToMenu) {
            currentAppIndex = -1;
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

            // Dispatch dynamic onIrReceived to the currently active app plugin
            if (currentAppIndex >= 0 && currentAppIndex < apps.size()) {
                apps[currentAppIndex]->onIrReceived(hexCode, rawJson, rawVector, millis());
            }
        }
        irrecv->resume();
    }
}
