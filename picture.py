import os
import random
import requests
from PIL import Image
from datetime import datetime
from picamera2 import Picamera2
import socket
import json
import time
import audio_control as mpv
import threading
import lgpio
import serial

# Configuration
# Camera Object
picam2 = Picamera2()

# Define a small 800x450 configuration for faster captures
config = picam2.create_still_configuration(main={"size": (960, 540)})
picam2.configure(config)

# Start camera at the beginning and keep it running
picam2.start()
time.sleep(0.5)  # Allow camera warm-up

# GPIO and SERIAL
ser = serial.Serial('/dev/ttyS0', 9600, timeout=1)
ser.flush()
GPIO_CHIP = 0
TRIGGER_PIN = 17  # Use GPIO17 (physical pin 11)
h = lgpio.gpiochip_open(GPIO_CHIP)
lgpio.gpio_claim_input(h, TRIGGER_PIN)
lgpio.gpio_claim_alert(h, TRIGGER_PIN, lgpio.FALLING_EDGE | lgpio.SET_PULL_DOWN)

ORIGINALS_DIR = "/home/b-cam/Scripts/blindCam/originals"
RESIZED_DIR = "/home/b-cam/Scripts/blindCam/resized"
AUDIO_DIR = "audio"
URL = "http://172.22.157.125:6411/process"
MAX_SIZE = 270  # Max pixels on the longest side
MAX_AUDIO_FILES = 10  # Keep only the last 10 audio recordings

#Global Vars
Volume = 100

# Ensure directories exist
for directory in [ORIGINALS_DIR, RESIZED_DIR, AUDIO_DIR]:
    os.makedirs(directory, exist_ok=True)

def capture_image():
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
    return image_path

""" OLD CAPTURE (SLOW)
def capture_image():
    #Captures an image using Picamera2 and saves it to the originals directory.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_path = os.path.join(ORIGINALS_DIR, f"{timestamp}.jpg")
    
    os.system(f"libcamera-jpeg -o {image_path} --nopreview --immediate --quality 60 --width 320 --height 180")
    mpv.play_audio("tempclick.wav")
    print(f"Captured image: {image_path}")
    return image_path
"""

def gpio_callback():
    print("Button pressed! Capturing image...")
    image_path = capture_image()
    print(f"Selected image: {image_path}")
    send_request(image_path, URL, AUDIO_DIR)

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

def send_request(image_path, url, output_directory):
    """Sends the image to the server and saves the response as a new audio file."""
    mpv.loop_audio("/home/b-cam/Scripts/blindCam/keyboard.wav",100)
    resized_image = os.path.join(output_directory, os.path.basename(image_path))
    with open(image_path, "rb") as image_file:
        files = {"image": image_file}
        response = requests.post(url, files=files)
        if response.status_code == 200:
            new_audio_file = os.path.join(output_directory, f"response_{random.randint(1000, 9999)}.wav")
            with open(new_audio_file, "wb") as f:
                f.write(response.content)
                f.flush()
                os.fsync(f.fileno())
                print(f"File is fully written. {new_audio_file}")
            time.sleep(0.5)
            
            if not mpv.play_audio(new_audio_file):
                print("🔄 Retrying audio playback...")
                time.sleep(0.5)
                mpv.play_audio(new_audio_file,80)

            manage_audio_files(output_directory)
        else:
            print(f"Failed to process image: {response.status_code}, {response.text}")

# GPIO monitoring in a separate thread
def monitor_gpio():
    """Monitors GPIO pin for button press."""
    print(f"🚀 Monitoring GPIO pin {TRIGGER_PIN} for button press...")
    try:
        while True:
            if lgpio.gpio_read(h, TRIGGER_PIN) == 1:  # Button press pulls the pin LOW
                gpio_callback()
                time.sleep(0.5)  # Debounce delay
    except KeyboardInterrupt:
        print("🛑 GPIO monitoring stopped.")
    finally:
        lgpio.gpiochip_close(h)
        
# MAIN LOOP FUNCTION
def main_loop():
    """Main loop waiting for user input or GPIO trigger."""
    
    print(f"Listening for commands or GPIO trigger on pin {TRIGGER_PIN}...")

    try:
        while True:
            command = input("> ").strip().lower()
            if command == "capture":
                print("Manual capture triggered!")
                image_path = capture_image()
                send_request(image_path, URL, AUDIO_DIR)
            elif command == "stop":
                mpv.kill_audio()
                print("Audio stopped.")
            elif command == "exit":
                print("Exiting...")
                break
            else:
                print("Unknown command. Use 'capture', 'stop', or 'exit'.")
    finally:
        
        print("GPIO cleaned up.")


# Time to run the script

if __name__ == "__main__":

    # Start GPIO monitoring in a separate thread
    gpio_thread = threading.Thread(target=monitor_gpio, daemon=True)
    gpio_thread.start()


    main_loop()

    # Clean up GPIO on exit
    lgpio.gpiochip_close(h)
