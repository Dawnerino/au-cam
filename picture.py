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
import subprocess

# Import the AudioManager class
from audio_manager import AudioManager

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
# Make sure audio directory is absolute
AUDIO_DIR = os.path.abspath("audio")  # Convert to absolute path
URL = os.getenv("URL")
MAX_AUDIO_FILES = 10

# Debug the path resolution for audio files
print(f"Current working directory: {os.getcwd()}")
print(f"Absolute path to AUDIO_DIR: {AUDIO_DIR}")

# Global Vars
Volume = 100
interrupt_event = threading.Event()

# Global state object for tracking playback
class State:
    def __init__(self):
        self.in_playback_mode = False  # True when in a capture-to-response cycle
        self.current_audio_pid = None  # Current audio process PID
        self.is_audio_playing = threading.Event()  # Flag to track if audio is playing
        
app_state = State()

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
    
    # Play shutter sound
    audio_manager.play_sound("tempclick.wav")

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

def keep_last_10_photos(directory):
    """Remove all files in the directory except the 10 most recently modified ones."""
    try:
        # Get list of all files with their full paths
        full_paths = [
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, f))
        ]

        # Sort files by last modified time (most recent last)
        sorted_files = sorted(full_paths, key=os.path.getmtime)

        # Keep only the last 10
        files_to_delete = sorted_files[:-10]

        for file_path in files_to_delete:
            os.remove(file_path)
            print(f"Removed: {file_path}")

        print(f"Kept last 10 files in: {directory}")

    except Exception as e:
        print(f"Error cleaning up photos: {e}")

def send_request(image_path):
    """Sends the image to the server, loops keyboard, stops, then plays response."""
    if not image_path:
        print("No image to send, skipping.")
        return

    print(f"Sending image: {image_path} to {URL}")
    
    # Start keyboard sound loop using AudioManager
    audio_manager.loop_sound("keyboard.wav")
    print("Started keyboard sound loop in background")
    
    # Create a flag to track if we've been interrupted
    interrupted = False

    # Create a function to check for interruptions
    def check_for_interruption():
        # Check if TAKE_PICTURE command was received during processing
        if serialHandle.last_command == "TAKE_PICTURE":
            print("Interrupt detected: cancelling request and audio")
            
            # Stop all audio via AudioManager
            audio_manager.stop_all_audio()
                
            serialHandle.last_command = None
            nonlocal interrupted
            interrupted = True
            return True
        return False

    try:
        # Set up the request but don't send it yet
        with open(image_path, "rb") as f:
            files = {"image": f}
            
            # Check for interruption before sending
            if check_for_interruption():
                return
            
            # Start a thread to periodically check for interruptions
            interrupt_check_thread = threading.Thread(
                target=lambda: [time.sleep(0.2), check_for_interruption()] * 150,  # Check every 0.2s for 30s
                daemon=True
            )
            interrupt_check_thread.start()
            
            # Create a streaming request that can be interrupted
            try:
                # Start the request with stream=True so we can monitor for interruptions
                response = requests.post(URL, files=files, timeout=120, stream=True)
                
                # Check status code before downloading content
                if response.status_code != 200:
                    print(f"Server error: {response.status_code}")
                    # Play error sound
                    audio_manager.stop_all_audio()  # Stop keyboard sound
                    audio_manager.play_error_sound()
                    return
                
                # We'll download the content in chunks while periodically checking for interruptions
                content_chunks = []
                for chunk in response.iter_content(chunk_size=8192):
                    # Check for interruptions after each chunk
                    if check_for_interruption():
                        print("Request interrupted during download, aborting")
                        response.close()
                        return
                    
                    # Store the chunk if we're continuing
                    if chunk:
                        content_chunks.append(chunk)
                        print(f"Downloaded {len(content_chunks)} chunks (~{sum(len(c) for c in content_chunks)/1024:.1f} KB)")
                
                # Combine all chunks to get full content
                full_content = b''.join(content_chunks)
                
                # Store the status code before we close the original response
                status_code = response.status_code
                
                # Create a simple class that just has the content
                class ResponseWrapper:
                    def __init__(self, status_code, content):
                        self.status_code = status_code
                        self.content = content
                    
                    def close(self):
                        pass  # Nothing to close, we already have the content
                
                # Close the original response
                response.close()
                
                # Replace with our simple wrapper
                response = ResponseWrapper(status_code, full_content)
                
            except requests.RequestException as e:
                print(f"Request error during streaming: {e}")
                audio_manager.stop_all_audio()
                return
                
            # Check for interruption now that download is complete
            if check_for_interruption():
                response.close()
                return

    except requests.RequestException as e:
        print(f"Request connection failed: {e}")
        # Stop all audio
        audio_manager.stop_all_audio()
        return

    # After request finishes
    print("Request completed, stopping keyboard sound")
    # Stop all audio via AudioManager
    audio_manager.stop_all_audio()
    
    # Check for interruption again after request finishes
    if interrupted or check_for_interruption():
        print("Interrupted: skipping response processing")
        return

    if response.status_code == 200:
        # Check if response actually contains audio data
        if not response.content or len(response.content) < 100:
            print(f"WARNING: Empty or too small response from server: {len(response.content)} bytes")
            audio_manager.play_error_sound()  # Play error sound
            return
            
        # Check for interruption before saving audio
        if check_for_interruption():
            print("Interrupted: skipping audio save and playback")
            return
            
        # Check if response is actually a WAV file (should start with RIFF header)
        if not response.content.startswith(b'RIFF'):
            print(f"WARNING: Response is not a valid WAV file (no RIFF header)")
            print(f"First 20 bytes of response: {response.content[:20]}")
            audio_manager.send_command(AUDIO_CMD_PLAY, file_path="ahh.wav", volume=100)  # Play error sound
            return
            
        # Check for interruption before saving audio
        if check_for_interruption():
            print("Interrupted: skipping audio save and playback")
            return
            
        # Save response
        random_id = random.randint(1000, 9999)
        # Ensure we're using the absolute path for the audio file
        new_audio_file = os.path.join(AUDIO_DIR, f"response_{random_id}.wav")
        
        # Make sure audio directory exists
        os.makedirs(AUDIO_DIR, exist_ok=True)
        
        try:
            with open(new_audio_file, "wb") as af:
                af.write(response.content)
                af.flush()
                os.fsync(af.fileno())
            
            print(f"Audio file saved: {new_audio_file}, size: {len(response.content)} bytes")
            print(f"File exists check: {os.path.exists(new_audio_file)}")
            
            # Check for interruption after saving
            if check_for_interruption():
                print("Interrupted after saving: skipping validation and playback")
                return
            
            # Check if audio file was correctly saved and is a valid WAV
            if os.path.exists(new_audio_file):
                with open(new_audio_file, "rb") as test_f:
                    header = test_f.read(12)  # Read RIFF header
                    if not header.startswith(b'RIFF'):
                        print(f"WARNING: Saved file does not have a valid WAV header")
                        # Play error sound
                        audio_manager.play_error_sound()
                        return
            
        except Exception as e:
            print(f"ERROR saving audio file: {e}")
            # Play error sound
            audio_manager.play_error_sound()
            return

        # One final check for interruption before playing
        if check_for_interruption():
            print("Interrupted: skipping audio playback")
            return

        # Verify file exists before playing
        if not os.path.exists(new_audio_file) or os.path.getsize(new_audio_file) < 100:
            print(f"WARNING: Audio file missing or too small: {new_audio_file}")
            # Play error sound
            audio_manager.play_error_sound()
            return
        
        # Sleep before playing to ensure previous audio is fully stopped
        time.sleep(0.5)
        
        # Final interruption check before playing
        if check_for_interruption():
            print("Interrupted just before playback: cancelling playback")
            return
            
        # Define callback for when audio completes
        def on_audio_complete():
            print("Audio playback completed - ready for next command")
            # No need to reset mode flag here, AudioManager does it automatically now
            
        # Send serial command to indicate request is complete and playback starting
        serialHandle.send_serial_command("REQUEST_COMPLETE")
        
        # Play the response audio
        print(f"Playing response audio: {new_audio_file}")
        
        # Let AudioManager handle all the details
        audio_manager.in_playback_mode = True  # Mark that we're in playback mode
        
        if audio_manager.play_sound(new_audio_file, callback=on_audio_complete):
            print("SUCCESS: Response audio playback started")
        else:
            print("ERROR: Failed to start response audio playback")
            audio_manager.in_playback_mode = False

    else:
        print(f"Server error: {response.status_code}")
        # Play error sound
        audio_manager.play_error_sound()
    keep_last_10_photos(ORIGINALS_DIR);

def take_picture():
    """Triggered by TAKE_PICTURE command."""
    serialHandle.last_command = None
    print("Taking picture...")

    image_path = capture_image()
    if serialHandle.last_command == "TAKE_PICTURE":
        print("Another TAKE_PICTURE came in, skipping request.")
        serialHandle.last_command = None
        return False

    # Set the playback mode true as we're about to start a response cycle
    audio_manager.in_playback_mode = True
    
    send_request(image_path)
    
    # Return True to indicate we've started a capture-to-response cycle
    return True

def stop_process():
    """Triggered by STOP_PROCESS command."""
    interrupt_event.set()
    
    # Use AudioManager to stop all audio
    audio_manager.stop_all_audio()
    
    # Reset playback mode
    audio_manager.in_playback_mode = False
        
    print("Processes stopped.")

def main_loop():
    print("🔄 Running command loop...")

    while True:
        cmd = serialHandle.last_command
        if cmd == "TAKE_PICTURE":
            serialHandle.last_command = None
            
            # Check if audio is playing and stop it
            if audio_manager.is_playing() or audio_manager.in_playback_mode:
                print("Cancelling audio playback")
                
                # Stop all audio via AudioManager
                audio_manager.stop_all_audio()
                
                # Reset playback mode
                audio_manager.in_playback_mode = False
                
                # Skip taking a picture since we're just stopping audio
                print("Audio stopped - press button again to take a new picture")
            else:
                # Only take a picture if we're not in playback mode
                print("Taking a new picture...")
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
