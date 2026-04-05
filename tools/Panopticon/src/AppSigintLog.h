#pragma once
#include <M5Unified.h>
#include <vector>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include "Config.h"
#include "AppInterface.h"
#include <LittleFS.h>

class AppSigintLog : public AppInterface {
private:
    String latestCode = "";
    String currentLogFile = "";
    bool btnALongPressedHandled = false;
    uint32_t visualFeedbackEndTime = 0;
    bool needsBackgroundRedraw = true;
    IRsend* irsend = nullptr;
    IRrecv* irrecv = nullptr;

    // Buffer to hold log entries in memory before flushing to disk
    std::vector<String> sessionLogsBuffer;

public:
    std::vector<uint16_t> latestRaw;

    AppSigintLog() {}

    virtual const char* getName() const override {
        return "3. Sigint Log";
    }

    virtual void init(IRsend* tx, IRrecv* rx) override {
        irsend = tx;
        irrecv = rx;
    }

    virtual void setup() override {
        latestCode = "";
        latestRaw.clear();
        sessionLogsBuffer.clear();
        btnALongPressedHandled = false;
        visualFeedbackEndTime = 0;
        needsBackgroundRedraw = true;

        // Generate a unique filename based on uptime/RTC for this session
        // Using millis() to ensure uniqueness if RTC is not synced
        currentLogFile = "/sigint_" + String(millis()) + ".txt";
        
        // Touch the file to create it
        File file = LittleFS.open(currentLogFile, FILE_WRITE);
        if (file) {
            file.close();
            DEBUG_PRINTLN("Created new log file: " + currentLogFile);
        } else {
            DEBUG_PRINTLN("Failed to create log file: " + currentLogFile);
        }
    }

    void flushLogsToDisk() {
        if (!currentLogFile.isEmpty() && !sessionLogsBuffer.empty()) {
            File file = LittleFS.open(currentLogFile, FILE_APPEND);
            if (file) {
                for (const String& entry : sessionLogsBuffer) {
                    file.print(entry);
                }
                file.close();
                DEBUG_PRINTF("Flushed %d logs to %s\n", sessionLogsBuffer.size(), currentLogFile.c_str());
            } else {
                DEBUG_PRINTLN("Failed to append to log file: " + currentLogFile);
            }
            sessionLogsBuffer.clear(); // Clear buffer after flush
        }
    }

    virtual void draw(bool fullDraw = false) override {
        if (fullDraw || needsBackgroundRedraw) {
            M5.Display.fillScreen(TFT_BLACK);
            M5.Display.setCursor(0, 5);
            M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
            M5.Display.setTextSize(2);
            M5.Display.println("[SIGINT LOG]");
            M5.Display.println("-------------");
            needsBackgroundRedraw = false;
        }
        
        M5.Display.setCursor(0, 35); // Start Y slightly higher
        M5.Display.setTextSize(2);
        M5.Display.setTextColor(TFT_GREEN, TFT_BLACK); // Background overwriting
        M5.Display.println("Latest Signal:               "); 

        if (latestCode.isEmpty()) {
             M5.Display.setTextColor(TFT_DARKGREEN, TFT_BLACK);
             M5.Display.println(" [WAITING...]                ");
             // Clear the second line just in case
             M5.Display.println("                             ");
        } else {
             M5.Display.setTextColor(TFT_CYAN, TFT_BLACK);

             String mainStr = latestCode;
             String bitStr = "";

             // Extract bit info (e.g., "(48bit)") if present at the end
             int parenIdx = latestCode.lastIndexOf('(');
             if (parenIdx > 0 && latestCode.endsWith(")")) {
                 mainStr = latestCode.substring(0, parenIdx - 1); // remove the space before '('
                 bitStr = latestCode.substring(parenIdx);
             }

             // Increase truncation limit by 4 characters as per user request (allow wider display)
             if (mainStr.length() > 18) {
                 int len = mainStr.length();
                 mainStr = mainStr.substring(0, 9) + ".." + mainStr.substring(len - 7);
             }
             
             // First line: Main HEX Code
             String paddedMain = " " + mainStr;
             while (paddedMain.length() < 19) paddedMain += " "; // Clear trailing garbage
             M5.Display.println(paddedMain);

             // Second line: Bit info (Right-aligned to match 1st line)
             if (!bitStr.isEmpty()) {
                 M5.Display.setTextColor(TFT_YELLOW, TFT_BLACK); // Highlight bit info
                 // Pad with spaces on the left so that the total length is 19 characters, matching the first line
                 String paddedBit = bitStr;
                 while (paddedBit.length() < 19) {
                     paddedBit = " " + paddedBit;
                 }
                 M5.Display.println(paddedBit);
             } else {
                 M5.Display.println("                   "); // 19 spaces to clear
             }
        }
    }

    virtual void onIrReceived(const String& code, const String& rawJson, const std::vector<uint16_t>& rawVector, uint32_t ts) override {
        latestCode = code;
        latestRaw = rawVector;
        draw();

        // Buffer the entry instead of writing immediately
        String logEntry = "{\"code\":\"" + code + "\",\"raw\":" + rawJson + ",\"ts\":" + String(ts) + "}\n";
        sessionLogsBuffer.push_back(logEntry);
        
        // Safety flush if buffer gets too large (e.g., > 20 entries)
        if (sessionLogsBuffer.size() > 20) {
            flushLogsToDisk();
        }
    }

    virtual void loop(bool& returnToMenu) override {
        if (M5.BtnB.wasReleased()) {
            flushLogsToDisk(); // Save all remaining buffered logs before exiting
            returnToMenu = true;
            return;
        }

        // Non-blocking visual feedback clear
        if (visualFeedbackEndTime > 0 && millis() > visualFeedbackEndTime) {
            visualFeedbackEndTime = 0;
            M5.Display.fillCircle(M5.Display.width() - 10, 10, 5, TFT_BLACK);
        }

        // Handle Long Press (Delete Latest)
        if (M5.BtnA.pressedFor(1000)) {
            if (!btnALongPressedHandled) {
                if (!latestCode.isEmpty()) {
                    latestCode = "";
                    draw();
                    
                    // Remove the last received signal from the log buffer
                    if (!sessionLogsBuffer.empty()) {
                        sessionLogsBuffer.pop_back();
                        DEBUG_PRINTLN("Latest signal deleted from buffer.");
                    }
                }
                btnALongPressedHandled = true;
            }
        } 
        // Handle Short Press (Fire Latest)
        else if (M5.BtnA.wasReleased()) {
             if (!btnALongPressedHandled) {
                 if (!latestCode.isEmpty() && latestRaw.size() > 0) {
                     if (irsend) {
                         // Disable RX to prevent self-feedback loop
                         if (irrecv) {
                             irrecv->disableIRIn();
                         }

                         // Yield CPU to background tasks (like WiFi) before engaging heavy RMT transmission
                         delay(20);
                         
                         irsend->sendRaw(latestRaw.data(), latestRaw.size(), 38);
                         DEBUG_PRINTF("SIGINT FIRED: %d pulses\n", latestRaw.size());
                         
                         // Block the main thread (UI drawing) while RMT interrupts are busy transmitting.
                         delay(latestRaw.size() + 20);

                         // Re-enable RX safely
                         if (irrecv) {
                             irrecv->enableIRIn();
                         }
                     }
                     M5.Display.fillCircle(M5.Display.width() - 10, 10, 5, TFT_CYAN);
                     visualFeedbackEndTime = millis() + 50;
                 }
             }
             // Reset long press flag on release
             btnALongPressedHandled = false;
        }
    }
};
