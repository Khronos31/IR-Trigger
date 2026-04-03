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

// Instantiate Apps
AppDumbPipe appDumbPipe;
AppSniper appSniper;
AppSigintLog appSigintLog;

void drawMenu() {
    M5.Display.fillScreen(TFT_BLACK);
    M5.Display.setCursor(0, 5);
    M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
    M5.Display.setTextSize(2);
    M5.Display.println(" PANOPTICON OS");
    M5.Display.println("-------------");
    
    for (int i = 0; i < MENU_ITEMS; i++) {
        if (i == menuCursor) {
            M5.Display.setTextColor(TFT_BLACK, TFT_GREEN);
            M5.Display.print("> ");
        } else {
            M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
            M5.Display.print("  ");
        }
        M5.Display.println(menuNames[i]);
    }
}

void setup() {
    auto cfg = M5.config();
    M5.begin(cfg);
    
    M5.Display.setRotation(1); // Set landscape
    
    drawMenu();
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
                drawMenu();
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
            if (currentState == STATE_DUMB_PIPE) {
                appDumbPipe.setup();
                appDumbPipe.draw();
            } else if (currentState == STATE_SNIPER) {
                appSniper.setup();
                appSniper.draw();
            } else if (currentState == STATE_SIGINT_LOG) {
                appSigintLog.setup();
                appSigintLog.draw();
            }
        }
    } else {
        bool returnToMenu = false;
        
        // Dispatch to appropriate app loop
        switch (currentState) {
            case STATE_DUMB_PIPE:
                appDumbPipe.loop(returnToMenu);
                break;
            case STATE_SNIPER:
                appSniper.loop(returnToMenu);
                break;
            case STATE_SIGINT_LOG:
                appSigintLog.loop(returnToMenu);
                break;
            default:
                break;
        }
        
        // Handle transition back to menu
        if (returnToMenu) {
            currentState = STATE_MENU;
            drawMenu();
        }
    }
}
