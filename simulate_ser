import serial
import time

# Set the same serial port and baud rate as in serialHandle.py
SERIAL_PORT = "/dev/ttyS0"  # Use the same port as the main script
BAUD_RATE = 19200

# Initialize serial connection
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)

def send_command(command):
    """Sends a command to the main script via serial."""
    ser.write((command + "\n").encode('utf-8'))
    print(f"📡 Sent command: {command}")

def manual_input():
    """Allows manual typing of commands for testing."""
    print("🔌 Type a command to send via serial (type 'exit' to quit):")
    while True:
        command = input("> ").strip()
        if command.lower() == "exit":
            break
        send_command(command)
        time.sleep(0.1)  # Small delay to simulate real input

if __name__ == "__main__":
    try:
        manual_input()
    except KeyboardInterrupt:
        print("\n🛑 Exiting simulation.")
    finally:
        ser.close()  # Ensure serial connection is closed properly
