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
        self.in_playback_mode = False
        
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
    
    # Create a flag to track if we've been interrupted
    interrupted = False

    # Create a function to check for interruptions
    def check_for_interruption():
        # Check if TAKE_PICTURE command was received during processing
        if serialHandle.last_command == "TAKE_PICTURE":
            print("Interrupt detected: cancelling request and audio")
            audio_manager.send_command(AUDIO_CMD_STOP)
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
            
            # Now send the request
            response = requests.post(URL, files=files, timeout=30)
            
            # Check for interruption immediately after response
            if check_for_interruption():
                response.close()
                return

    except requests.RequestException as e:
        print(f"Request failed: {e}")
        audio_manager.send_command(AUDIO_CMD_STOP)
        return

    # After request finishes
    audio_manager.send_command(AUDIO_CMD_STOP)  # stop the loop
    time.sleep(0.5)  # Wait longer to ensure complete stop
    
    # Check for interruption again after request finishes
    if interrupted or check_for_interruption():
        print("Interrupted: skipping response processing")
        return

    if response.status_code == 200:
        # Check if response actually contains audio data
        if not response.content or len(response.content) < 100:
            print(f"WARNING: Empty or too small response from server: {len(response.content)} bytes")
            audio_manager.send_command(AUDIO_CMD_PLAY, file_path="ahh.wav", volume=100)  # Play error sound
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
                        audio_manager.send_command(AUDIO_CMD_PLAY, file_path="ahh.wav", volume=100)
                        return
            
        except Exception as e:
            print(f"ERROR saving audio file: {e}")
            audio_manager.send_command(AUDIO_CMD_PLAY, file_path="ahh.wav", volume=100)  # Play error sound
            return

        # One final check for interruption before playing
        if check_for_interruption():
            print("Interrupted: skipping audio playback")
            return

        # Verify file exists before playing
        if not os.path.exists(new_audio_file) or os.path.getsize(new_audio_file) < 100:
            print(f"WARNING: Audio file missing or too small: {new_audio_file}")
            audio_manager.send_command(AUDIO_CMD_PLAY, file_path="ahh.wav", volume=100)  # Play error sound
            return
        
        # Sleep before playing to ensure previous audio is fully stopped
        time.sleep(0.5)
        
        # Final interruption check before playing
        if check_for_interruption():
            print("Interrupted just before playback: cancelling playback")
            return
            
        # Use a manual approach to play the sound
        print(f"Directly playing the response audio: {new_audio_file}")
        
        # Use AudioManager instead of system call so we can interrupt it
        print(f"Playing response audio using AudioManager: {new_audio_file}")
        
        # Debug audio file before playing
        if os.path.exists(new_audio_file):
            print(f"CONFIRMED: Audio file exists: {new_audio_file} ({os.path.getsize(new_audio_file)} bytes)")
            # Check if the file is readable
            try:
                with open(new_audio_file, 'rb') as test_f:
                    header = test_f.read(12)
                    print(f"Audio file header: {header}")
            except Exception as e:
                print(f"ERROR reading audio file: {e}")
        else:
            print(f"ERROR: Audio file does not exist: {new_audio_file}")
            print(f"Looking in absolute path: {os.path.abspath(new_audio_file)}")
            return  # Don't try to play if the file doesn't exist
        
        print("PLAYING NOW: Sending to audio manager...")
        
        # For large files, bypass AudioManager and use direct system call
        file_size = os.path.getsize(new_audio_file)
        if file_size > 500000:  # >500KB
            print(f"LARGE FILE: Using direct system playback for {new_audio_file} ({file_size} bytes)")
            try:
                import subprocess
                # Start aplay in foreground mode so it's easier to interrupt
                print(f"Starting direct system playback with aplay")
                # Setting audio flag manually since we're bypassing audio_manager
                audio_manager.is_audio_playing.set()
                # Start the process in background
                proc = subprocess.Popen(["aplay", new_audio_file],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
                print(f"DIRECT PLAY: Started aplay process, pid={proc.pid}")
                
                # Create monitor function that uses the global app_state
                def monitor_playback():
                    try:
                        # Use proc from parent scope
                        proc.wait()  # Wait for process to complete
                        print("System audio playback completed naturally")
                        audio_manager.is_audio_playing.clear()  # Clear the flag
                        
                        # Update global state
                        app_state.in_playback_mode = False
                        print("Playback mode reset, ready for new picture")
                    except Exception as e:
                        print(f"Error in monitor thread: {e}")
                
                # Start the monitor thread
                monitor_thread = threading.Thread(target=monitor_playback, daemon=True)
                monitor_thread.start()
            except Exception as e:
                print(f"ERROR starting direct playback: {e}")
        else:
            # For smaller files, use AudioManager
            audio_manager.send_command(AUDIO_CMD_PLAY, file_path=new_audio_file, volume=100)
            
            # Check if playing started
            time.sleep(0.5)
            if audio_manager.is_playing():
                print("SUCCESS: Audio playback started")
            else:
                print("PROBLEM: Audio manager did not start playback")

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
        return False

    # Set the playback mode true as we're about to start a response cycle
    app_state.in_playback_mode = True
    
    send_request(image_path)
    
    # Return True to indicate we've started a capture-to-response cycle
    return True

def stop_process():
    """Triggered by STOP_PROCESS command."""
    interrupt_event.set()
    audio_manager.send_command(AUDIO_CMD_STOP)
    
    # Also kill any system audio processes that might be running
    try:
        # Kill any aplay processes
        subprocess.run(["pkill", "-f", "aplay"], 
                      stdout=subprocess.PIPE, 
                      stderr=subprocess.PIPE)
        print("Killed system audio processes")
    except Exception as e:
        print(f"Error stopping system audio: {e}")
    
    # Reset playback mode flag using the global state object
    app_state.in_playback_mode = False
        
    print("Processes stopped.")

def main_loop():
    print("🔄 Running command loop...")

    while True:
        # Check if playback has naturally ended
        if app_state.in_playback_mode and not audio_manager.is_playing():
            # Check if any aplay processes are still running
            try:
                result = subprocess.run(["pgrep", "-f", "aplay"], 
                                     stdout=subprocess.PIPE, 
                                     stderr=subprocess.PIPE)
                if result.returncode != 0:  # No aplay processes found
                    print("Audio playback has naturally completed")
                    app_state.in_playback_mode = False
            except Exception:
                # If we can't check, assume it might have ended
                pass
                
        cmd = serialHandle.last_command
        if cmd == "TAKE_PICTURE":
            serialHandle.last_command = None
            
            # Check if audio is playing and stop it
            if audio_manager.is_playing() or app_state.in_playback_mode:
                print("Cancelling audio playback")
                audio_manager.send_command(AUDIO_CMD_STOP)
                # Also kill any system audio processes
                try:
                    subprocess.run(["pkill", "-f", "aplay"], 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE)
                    print("Killed system audio processes")
                except Exception as e:
                    print(f"Error stopping system audio: {e}")
                time.sleep(0.2)  # Small delay to ensure audio stops
                
                # Mark that we've left playback mode
                app_state.in_playback_mode = False
                
                # Skip taking a picture since we're just stopping audio
                print("Audio stopped - press button again to take a new picture")
            else:
                # Only take a picture if we're not in playback mode
                print("Taking a new picture...")
                take_picture()
                # Set playback mode flag since we're starting a capture-to-response cycle
                app_state.in_playback_mode = True
                
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
