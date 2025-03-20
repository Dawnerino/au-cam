import serial
import threading

# Global variable to track last received command
last_command = None  
command_lock = threading.Lock()  

# Initialize serial connection
ser = serial.Serial('/dev/ttyS0', 19200, timeout=1)

# Command handler dictionary
command_handlers = {}

def send_serial_command(command):
    """Sends a command to the Arduino via serial."""
    ser.write((command + "\n").encode('utf-8'))  
    print(f"ARDUINO: {command}")

def handle_serial_command(command):
    """Handles commands received from Arduino using the registered command handlers."""
    global last_command

    with command_lock:
        print(f"RECEIVE: {command}")

        if command in command_handlers:
            last_command = command  
            command_handlers[command]()  # Call the registered function
        else:
            print(f"⚠️ Unknown command: {command}")

def serial_thread():
    """Continuously read from the serial port and execute corresponding commands."""
    global last_command
    print("🔌 Listening for serial commands...")

    while True:
        if ser.in_waiting > 0:
            command = ser.readline().decode('utf-8', errors='ignore').strip()
            if command:
                handle_serial_command(command)

def register_command(command_name, function):
    """Registers a command and its corresponding function."""
    command_handlers[command_name] = function
    print(f"✅ Registered command: {command_name}")

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
        ser = None  
