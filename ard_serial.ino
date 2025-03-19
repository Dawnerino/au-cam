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
        triggerVibration();
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
    /*
    if (lastCommand == "FEEDBACK_VIBRATE"){
      iteVibr();
    };
    
    if (millis() - simpleDelay >= 8000) { // Update using millis() every 8 seconds
      simpleDelay = millis();
      Serial.println("ping..!");
    }
    */
    delay(5);
}