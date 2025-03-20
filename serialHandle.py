import serial
import threading
import picture  # Import main script functions

# Global variable to track last received command
last_command = None  # Updated dynamically by serial thread
command_lock = threading.Lock()  # Prevent multiple commands at once

# Initialize serial connection
ser = serial.Serial('/dev/ttyS0', 19200, timeout=1)

def send_serial_command(command):
    """Sends a command to the Arduino via serial."""
    ser.write((command + "\n").encode('utf-8'))  # Send command with newline
    print(f"ARDUINO: {command}")

def handle_serial_command(command):
    """Handles commands received from Arduino and updates the last command variable."""
    global last_command

    with command_lock:
        print(f"RECEIVE: {command}")

        # If TAKE_PICTURE is received while an existing process is running, cancel it.
        if command == "TAKE_PICTURE":
            if last_command == "TAKE_PICTURE":  
                print("Another TAKE_PICTURE received - Interrupting current process!")
            last_command = "TAKE_PICTURE"
            picture.take_picture()  # Call function to take picture or cancel ongoing process (THIS BLOWS MY MIND)

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
    """Stops the serial connection safely."""
    global ser
    if ser:
        print("🛑 Closing serial connection...")
        ser.close()
        ser = None  # Prevent further access
