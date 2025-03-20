import serial
import threading

# Global variable to track last received command
last_command = None  
command_lock = threading.Lock()  

# Initialize serial connection
ser = serial.Serial('/dev/ttyS0', 19200, timeout=1)

def send_serial_command(command):
    """Sends a command to the Arduino via serial."""
    ser.write((command + "\n").encode('utf-8'))  
    print(f"ARDUINO: {command}")

def serial_thread():
    """Continuously read from the serial port and update last_command."""
    global last_command
    print("🔌 Listening for serial commands...")

    while True:
        if ser.in_waiting > 0:
            command = ser.readline().decode('utf-8', errors='ignore').strip()
            if command:
                with command_lock:
                    print(f"📡 RECEIVED: {command}")
                    last_command = command  # Update last command globally

def start_serial_listener():
    """Starts the serial thread."""
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
