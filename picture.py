###################################
# picture.py (Main Script)
###################################
from dotenv import load_dotenv
import os
import random
import requests
from PIL import Image
from datetime import datetime
from picamera2 import Picamera2
import time
import threading

# Our new audio manager
from audio_manager import AudioManager, AUDIO_CMD_PLAY, AUDIO_CMD_LOOP, AUDIO_CMD_STOP

# Serial Handling python Script
import serialHandle

# Load environment variables
load_dotenv()

# Camera Object
picam2 = Picamera2()
config = picam2.create_still_configuration(main={"size": (480, 270)})
picam2.configure(config)
picam2.start()

ORIGINALS_DIR = "/home/b-cam/Scripts/blindCam/originals"
RESIZED_DIR = "/home/b-cam/Scripts/blindCam/resized"
AUDIO_DIR = "audio"
URL = os.getenv("URL")
MAX_AUDIO_FILES = 10

# Global Vars
Volume = 100
interrupt_event = threading.Event()

# Ensure directories exist
for directory in [ORIGINALS_DIR, RESIZED_DIR, AUDIO_DIR]:
    os.makedirs(directory, exist_ok=True)

# Create the AudioManager instance
audio_manager = AudioManager()

def capture_image():
    # Clear last command
    serialHandle.last_command = None

    # Capture
    frame = picam2.capture_array()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_path = os.path.join(ORIGINALS_DIR, f"{timestamp}.jpg")

    Image.fromarray(frame).save(image_path)
    
    # Play shutter sound using AudioManager
    audio_manager.send_command(AUDIO_CMD_PLAY, file_path="tempclick.wav", volume=100)

    print(f"Captured image: {image_path}")
    serialHandle.send_serial_command("FEEDBACK_VIBRATE")  # Vibrate on Arduino

    return image_path

def manage_audio_files(directory, max_files=MAX_AUDIO_FILES):
    """Keeps only last `max_files` .wav files, removes old ones."""
    audio_files = sorted(
        (os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(".wav")),
        key=os.path.getmtime
    )
    while len(audio_files) > max_files:
        oldest_file = audio_files.pop(0)
        os.remove(oldest_file)
        print(f"Deleted old audio: {oldest_file}")

def send_request(image_path):
    """Sends the image to the server, loops keyboard, stops, then plays response."""
    if not image_path:
        print("No image to send, skipping.")
        return

    print(f"Sending image: {image_path} to {URL}")
    audio_manager.send_command(AUDIO_CMD_LOOP, file_path="keyboard.wav", volume=100)

    try:
        with open(image_path, "rb") as f:
            files = {"image": f}
            response = requests.post(URL, files=files, timeout=30)

            if serialHandle.last_command == "TAKE_PICTURE":
                print("Interrupt: stopping request + audio.")
                response.close()
                audio_manager.send_command(AUDIO_CMD_STOP)
                serialHandle.last_command = None
                return

    except requests.RequestException as e:
        print(f"Request failed: {e}")
        audio_manager.send_command(AUDIO_CMD_STOP)
        return

    # After request finishes
    audio_manager.send_command(AUDIO_CMD_STOP)  # stop the loop
    time.sleep(0.2)

    if response.status_code == 200:
        # Save response
        new_audio_file = os.path.join(AUDIO_DIR, f"response_{random.randint(1000, 9999)}.wav")
        with open(new_audio_file, "wb") as af:
            af.write(response.content)
            af.flush()
            os.fsync(af.fileno())

        print(f"Audio file saved: {new_audio_file}")

        if serialHandle.last_command == "TAKE_PICTURE":
            print("Interrupt before playing response. Skipping.")
            audio_manager.send_command(AUDIO_CMD_STOP)
            serialHandle.last_command = None
            return

        # Play response
        audio_manager.send_command(AUDIO_CMD_PLAY, file_path=new_audio_file, volume=100)

    else:
        print(f"Server error: {response.status_code}, {response.text}")

def take_picture():
    """Triggered by TAKE_PICTURE command."""
    serialHandle.last_command = None
    print("Taking picture...")

    image_path = capture_image()
    if serialHandle.last_command == "TAKE_PICTURE":
        print("Another TAKE_PICTURE came in, skipping request.")
        serialHandle.last_command = None
        return

    send_request(image_path)

def stop_process():
    """Triggered by STOP_PROCESS command."""
    interrupt_event.set()
    audio_manager.send_command(AUDIO_CMD_STOP)
    print("Processes stopped.")

def main_loop():
    print("🔄 Running command loop...")

    while True:
        cmd = serialHandle.last_command
        if cmd == "TAKE_PICTURE":
            serialHandle.last_command = None
            take_picture()
        elif cmd == "STOP_PROCESS":
            serialHandle.last_command = None
            stop_process()
        elif cmd == "INCREASE_VOLUME":
            serialHandle.last_command = None
            print("🔊 Increase volume... (not implemented)")
        elif cmd == "DECREASE_VOLUME":
            serialHandle.last_command = None
            print("🔉 Decrease volume... (not implemented)")
        time.sleep(0.1)

if __name__ == "__main__":
    # Start serial listener
    serialHandle.start_serial_listener()
    # Run main loop
    main_loop()
