from dotenv import load_dotenv
import os
import random
import requests
from PIL import Image
from datetime import datetime
from picamera2 import Picamera2
import time
import audio_control as mpv
import threading

# Serial Handling python Script (Creates a last command global variable that will cancel certain long functions.)
import serialHandle


# Configuration
#load environment variables
load_dotenv()

# Camera Object
picam2 = Picamera2()
# Define a small 480x270 configuration for faster captures and processing
config = picam2.create_still_configuration(main={"size": (480, 270)})
picam2.configure(config)
# Start camera at the beginning and keep it running
picam2.start()

ORIGINALS_DIR = "/home/b-cam/Scripts/blindCam/originals"
RESIZED_DIR = "/home/b-cam/Scripts/blindCam/resized"
AUDIO_DIR = "audio"
URL = os.getenv("URL")
MAX_AUDIO_FILES = 10  # Keep only the last 10 audio recordings

#Global Vars
Volume = 100
#thread interrupting event
interrupt_event = threading.Event()

# Ensure directories exist
for directory in [ORIGINALS_DIR, RESIZED_DIR, AUDIO_DIR]:
    os.makedirs(directory, exist_ok=True)

def capture_image():
    # Clear last command to prevent immediate cancellation
    serialHandle.last_command = None

    """Capture a still image using picamera2 and save to file."""
    global picam2  # Use the initialized camera

    # Capture image directly into numpy array (very fast)
    frame = picam2.capture_array()

    # Save to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_path = f"/home/b-cam/Scripts/blindCam/originals/{timestamp}.jpg"

    # Convert to PIL image and save
    Image.fromarray(frame).save(image_path)
    mpv.play_audio("tempclick.wav")
    print(f"Captured image: {image_path}")
    # Send feedback to Arduino after successful capture
    serialHandle.send_serial_command("FEEDBACK_VIBRATE")  # Arduino will start "loading..." vibration.

    return image_path


def manage_audio_files(directory, max_files=MAX_AUDIO_FILES):
    """Ensures that only the last `max_files` audio recordings are kept, deleting the oldest ones."""
    audio_files = sorted(
        [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(".wav")],
        key=os.path.getmtime  # Sort by modification time (oldest first)
    )

    # If we exceed the limit, delete the oldest files
    while len(audio_files) > max_files:
        oldest_file = audio_files.pop(0)  # Remove and delete the oldest file
        os.remove(oldest_file)
        print(f"Deleted: {oldest_file}")

def send_request(image_path):
    """Sends the image to the server but can be interrupted."""
    if not image_path:
        print("No image captured, skipping request.")
        return

    print(f"Sending image: {image_path} to {URL}")
    mpv.loop_audio("/home/b-cam/Scripts/blindCam/keyboard.wav", 100)

    # Check before sending
    if serialHandle.last_command == "TAKE_PICTURE":
        print("Interrupt detected before sending request. Returning to idle.")
        serialHandle.last_command = None
        return  

    with open(image_path, "rb") as image_file:
        files = {"image": image_file}

        try:
            response = requests.post(URL, files=files, timeout=10)

            # Check if interrupted after sending but before processing response
            if serialHandle.last_command == "TAKE_PICTURE":
                print("Interrupt detected mid-request. Returning to idle.")
                serialHandle.last_command = None
                return

        except requests.RequestException as e:
            print(f"Request failed: {e}")
            return

        if response.status_code == 200:
            new_audio_file = os.path.join(AUDIO_DIR, f"response_{random.randint(1000, 9999)}.wav")

            with open(new_audio_file, "wb") as f:
                f.write(response.content)
                f.flush()
                os.fsync(f.fileno())

            print(f"Audio file saved: {new_audio_file}")

            if serialHandle.last_command == "TAKE_PICTURE":
                print("Interrupt detected before playing audio. Returning to idle.")
                serialHandle.last_command = None
                return

            if not mpv.play_audio(new_audio_file):
                print("Retrying audio playback...")
                time.sleep(0.5)
                mpv.play_audio(new_audio_file, 100)

        else:
            print(f"Failed response: {response.status_code}, {response.text}")


# SERIAL ASSIGNED SPECIFIC FUNCTIONS
def take_picture():
    # Clear the last command so capture_image() doesn’t immediately cancel
    serialHandle.last_command = None  
    
    print ("taking picture..!")

    image_path = capture_image()
    
    # If interrupted, do NOT proceed with sending request
    if serialHandle.last_command == "TAKE_PICTURE":
        print("Another TAKE_PICTURE command received. Restarting capture.")
        serialHandle.last_command = None
        return
    
    send_request(image_path)

def stop_process():
    """Handles the STOP_PROCESS command."""
    interrupt_event.set()
    mpv.kill_audio()
    print("Processes stopped.")


# MAIN LOOP FUNCTION
def main_loop():
    """Main loop for manual commands."""
    print("Listening for commands...")

    try:
        while True:
            command = input("> ").strip().lower()
            if command == "capture":
                print("Manual capture triggered!")
                interrupt_event.clear()
                take_picture()

            elif command == "stop":
                stop_process()

            elif command == "exit":
                print("Exiting...")
                break

            else:
                print("Unknown command. Use 'capture', 'stop', or 'exit'.")

    finally:
        print("Cleaning up resources.")
        serialHandle.stop_serial()

if __name__ == "__main__":
    # Start Serial Listener
    serialHandle.start_serial_listener()

    # Run Main Loop
    main_loop()