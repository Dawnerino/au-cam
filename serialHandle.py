import serial
import threading

# Global variable to track last received command
last_command = None  # Will be updated dynamically by serial thread

# Initialize serial connection
ser = serial.Serial('/dev/ttyS0', 19200, timeout=1)

def send_serial_command(command):
    """Sends a command to the Arduino via serial."""
    ser.write((command + "\n").encode('utf-8'))  # Send command with newline
    print(f"📡 Sent command to Arduino: {command}")

def handle_serial_command(command):
    """Handles commands received via serial and updates the last command variable."""
    global last_command

    print(f"📡 Received serial command: {command}")
    last_command = command  # Update the last command so the main script can check it

def serial_thread():
    """Continuously read from the serial port and update last_command."""
    global last_command
    print("🔌 Listening for serial commands...")

    while True:
        if ser.in_waiting > 0:
            command = ser.readline().decode('utf-8', errors='ignore').strip()
            if command:
                handle_serial_command(command)

def start_serial_listener():
    """Starts the serial thread and returns the thread object."""
    serial_thread_instance = threading.Thread(target=serial_thread, daemon=True)
    serial_thread_instance.start()
    return serial_thread_instance

def stop_serial():
    """Stops the serial connection."""
    ser.close()
