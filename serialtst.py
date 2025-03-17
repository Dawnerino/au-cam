import serial
import time

ser = serial.Serial('/dev/ttyS0', 19200, timeout=1)

def send_command(command):
    """Send a command back to the Arduino."""
    ser.write((command + "\n").encode('utf-8'))

def handle_command(command):
    """Handle incoming commands from Arduino."""
    print(f"Received command: {command}")

    if command == "TAKE_PICTURE":
        print("Taking picture...")
        take_picture()
        print("Picture taken. Sending vibration feedback.")
        send_command("FEEDBACK_VIBRATE")

    else:
        print(f"Unknown command from Arduino: {command}")

def take_picture():
    """Simulated picture-taking process — replace with your actual camera code."""
    time.sleep(1)  # Simulate time delay for picture
    print("Picture saved.")

def main():
    print("Listening for commands from Arduino...")
    while True:
        if ser.in_waiting > 0:
            command = ser.readline().decode('utf-8', errors='ignore').strip()
            if command:
                handle_command(command)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
        ser.close()
