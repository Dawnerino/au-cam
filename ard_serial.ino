// pins
const int buttonPin = 2;
const int vibrationPin = 10;
const int playBackPin = 6;
const int prevPin = 5;
const int nextPin = 7;
const int wordCntPin = 4;

// global vars
unsigned long simpleDelay = 0;
int globalVibration = 0;
bool isVibrating = false;
unsigned long lastVibrateTime = 0;
int vibrationStrength = 0;
bool fadeUp = true;
String lastCommand = "";


// ITERATE VIBRATION TO NOT LOCKUP SYSTEM WHEN STEPPING UP AND DOWN 03/12/25

void checkButton() {
    static bool lastButtonState = HIGH;

    bool buttonState = digitalRead(buttonPin);
    if (buttonState == LOW && lastButtonState == HIGH) {
      delay(10);  // Short debounce
        if (digitalRead(buttonPin) == LOW) {  // Confirm it's still pressed
          sendCommand("TAKE_PICTURE");
        }
    }

    lastButtonState = buttonState;
}

void checkDigitalPins() {
    static bool lastPlayBackState = HIGH;
    static bool lastPrevState = HIGH;
    static bool lastNextState = HIGH;
    static bool lastWordCntState = HIGH;

    // Check pin 4 - PLAY_BACK
    bool playBackState = digitalRead(playBackPin);
    if (playBackState == LOW && lastPlayBackState == HIGH) {
        delay(10);  // Short debounce
        if (digitalRead(playBackPin) == LOW) {
            sendCommand("PLAY_BACK");
        }
    }
    lastPlayBackState = playBackState;
    
    // Check pin 5 - PREV
    bool prevState = digitalRead(prevPin);
    if (prevState == LOW && lastPrevState == HIGH) {
        delay(10);  // Short debounce
        if (digitalRead(prevPin) == LOW) {
            sendCommand("PREV");
        }
    }
    lastPrevState = prevState;
    
    // Check pin 6 - NEXT
    bool nextState = digitalRead(nextPin);
    if (nextState == LOW && lastNextState == HIGH) {
        delay(10);  // Short debounce
        if (digitalRead(nextPin) == LOW) { 
            sendCommand("NEXT");
        }
    }
    lastNextState = nextState;
    
    // Check pin 7 - WORD_CNT
    bool wordCntState = digitalRead(wordCntPin);
    if (wordCntState == LOW && lastWordCntState == HIGH) {
        delay(10);  // Short debounce
        if (digitalRead(wordCntPin) == LOW) {
            sendCommand("WORD_CNT");
        }
    }
    lastWordCntState = wordCntState;
}

void checkSerialCommands() {
    if (Serial.available()) {
        String command = Serial.readStringUntil('\n');
        command.trim();
        handleCommand(command);
    }
}

void handleCommand(String command) {
    if (command == "FEEDBACK_VIBRATE") {
        isVibrating = true;
        lastCommand = "FEEDBACK_VIBRATE";
    } else if (command == "STOP_VIBRATION") {
        stopVibration();
    } else if (command == "REQUEST_COMPLETE") {
        triggerVibration(150, 255);
        delay(100);
        triggerVibration(150, 255);
    } else if (command == "READY") {
        triggerVibration(50, 200);
    } else {
        Serial.print("UNKNOWN_COMMAND: ");
        Serial.println(command);
    }
}

void sendCommand(const char* cmd) {
    Serial.println(cmd);
}
/*
void iteVibr() {
  if (globalVibration 
}
*/
void triggerVibration(int x, int y) {
    analogWrite(vibrationPin, y);  // Adjust as needed
    delay(x);  // Vibration duration
    stopVibration();
}

void stopVibration() {
    analogWrite(vibrationPin, 0);
    isVibrating = false;
}

// ::::    ::::      :::     ::::::::::: ::::    :::
// +:+:+: :+:+:+   :+: :+:       :+:     :+:+:   :+:
// +:+ +:+:+ +:+  +:+   +:+      +:+     :+:+:+  +:+
// +#+  +:+  +#+ +#++:++#++:     +#+     +#+ +:+ +#+
// +#+       +#+ +#+     +#+     +#+     +#+  +#+#+#
// #+#       #+# #+#     #+#     #+#     #+#   #+#+#
// ###       ### ###     ### ########### ###    ####
// main
void setup() {
    Serial.begin(19200);
    pinMode(buttonPin, INPUT_PULLUP);
    pinMode(vibrationPin, OUTPUT);
    pinMode(playBackPin, INPUT_PULLUP);
    pinMode(prevPin, INPUT_PULLUP);
    pinMode(nextPin, INPUT_PULLUP);
    pinMode(wordCntPin, INPUT_PULLUP);
    stopVibration();
}

void loop() {
    checkButton();
    checkDigitalPins();
    checkSerialCommands();

    // Handle ongoing vibration loop
    if (isVibrating) {
        unsigned long now = millis();
        if (now - lastVibrateTime > 50) {  // update every 10ms
            lastVibrateTime = now;

            // Fade vibration up/down
            if (fadeUp) {
                vibrationStrength += 10; //steps for vibration
                if (vibrationStrength >= 255) {
                    vibrationStrength = 255;
                    fadeUp = false;
                }
            } else {
                vibrationStrength -= 10; //steps for vibration
                if (vibrationStrength <= 0) {
                    vibrationStrength = 0;
                    fadeUp = true;
                }
            }
            analogWrite(vibrationPin, vibrationStrength);
        }
    }
    delay(5);
}