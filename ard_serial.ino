const int buttonPin = 2;
const int vibrationPin = 5;
unsigned long simpleDelay = 0;
int globalVibration = 0;
int lastCommand;


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

void checkSerialCommands() {
    if (Serial.available()) {
        String command = Serial.readStringUntil('\n');
        command.trim();
        Serial.println(command);
        handleCommand(command);
    }
}

void handleCommand(String command) {
    if (command == "FEEDBACK_VIBRATE") {
        isVibrating = true;
        lastCommand = "FEEDBACK_VIBRATE";
    } else if (command == "STOP_VIBRATION") {
        stopVibration();
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
void triggerVibration() {
    analogWrite(vibrationPin, 100);  // Adjust as needed
    delay(500);  // Vibration duration
    stopVibration();
}

void stopVibration() {
    analogWrite(vibrationPin, 0);
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
    stopVibration();
}

void loop() {
    checkButton();
    checkSerialCommands();


    // Handle ongoing vibration loop
    if (isVibrating) {
        unsigned long now = millis();
        if (now - lastVibrateTime > 10) {  // update every 10ms
            lastVibrateTime = now;

            // Fade vibration up/down
            if (fadeUp) {
                vibrationStrength += 15;
                if (vibrationStrength >= 255) {
                    vibrationStrength = 255;
                    fadeUp = false;
                }
            } else {
                vibrationStrength -= 15;
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