###################################
# picture.py (RUNS ALL LOGIC LOCALLY)
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
import io
import openai
from pydub import AudioSegment

# Import the AudioManager class
from audio_manager import AudioManager

# Serial Handling python Script
import serialHandle

# Load environment variables
load_dotenv()

# Set OpenAI API key
OPENAI_API_KEY = os.environ.get("OPENAI_KEY")
openai.api_key = OPENAI_API_KEY

# Camera Object
picam2 = Picamera2()
config = picam2.create_still_configuration(main={"size": (480, 270)})
picam2.configure(config)
picam2.start()

ORIGINALS_DIR = "/home/b-cam/Scripts/blindCam/originals"
RESIZED_DIR = "/home/b-cam/Scripts/blindCam/resized"
# Make sure audio directory is absolute
AUDIO_DIR = os.path.abspath("audio")  # Convert to absolute path
MAX_AUDIO_FILES = 10

# Debug the path resolution for audio files
print(f"Current working directory: {os.getcwd()}")
print(f"Absolute path to AUDIO_DIR: {AUDIO_DIR}")

# Global Vars
Volume = 100
wordiness = 200
interrupt_event = threading.Event()

# Global state object for tracking playback
class State:
    def __init__(self):
        self.in_playback_mode = False  # True when in a capture-to-response cycle
        self.in_audio_playback_mode = False  # True when in audio playback mode (navigating recordings)
        self.current_audio_pid = None  # Current audio process PID
        self.is_audio_playing = threading.Event()  # Flag to track if audio is playing
        self.current_playback_index = 0  # Index of current audio file during playback navigation
        
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
    audio_manager.play_sound("tempclick.wav", 88)

    print(f"Captured image: {image_path}")
    serialHandle.send_serial_command("FEEDBACK_VIBRATE")  # Vibrate on Arduino

    return image_path

def manage_audio_files(directory, max_files=MAX_AUDIO_FILES):
    """Keeps only last `max_files` audio files (.wav), removes old ones."""
    audio_files = sorted(
        (os.path.join(directory, f) for f in os.listdir(directory) 
         if f.lower().endswith(".wav")),
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

def resize_image(image):
    """Resizes image so that the longest side is 150 pixels while maintaining aspect ratio."""
    max_size = 150
    width, height = image.size

    if width > height:
        new_width = max_size
        new_height = int((max_size / width) * height)
    else:
        new_height = max_size
        new_width = int((max_size / height) * width)

    return image.resize((new_width, new_height), Image.LANCZOS)

def convert_to_small_wav(input_file, output_file):
    """Convert any WAV to a smaller PCM WAV format."""
    print(f"Converting {input_file} to a smaller WAV...")

    # Detect format automatically
    audio = AudioSegment.from_file(input_file, format="wav")  # Auto-detects compressed WAV

    # Reduce sample rate to 22050 Hz, convert to mono, reduce bit depth
    audio = audio.set_frame_rate(22050).set_channels(1).set_sample_width(2)

    # Export to WAV
    audio.export(output_file, format="wav")
    print(f"Converted to smaller WAV: {output_file}")
    return output_file

def send_request(image_path):
    """Performs all processing locally: resizes image, uses OpenAI to analyze, and Google TTS for speech."""
    if not image_path:
        print("No image to send, skipping.")
        return

    print(f"Processing image: {image_path}")
    
    # Start loading sound loop using AudioManager
    audio_manager.loop_sound("sys_aud/loading.wav",80)
    print("Started loading sound loop in background")
    
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
        # Check for interruption before beginning
        if check_for_interruption():
            return
        
        # Start a thread to periodically check for interruptions
        interrupt_check_thread = threading.Thread(
            target=lambda: [time.sleep(0.2), check_for_interruption()] * 150,  # Check every 0.2s for 30s
            daemon=True
        )
        interrupt_check_thread.start()
        
        # Step 1: Load and resize the image
        try:
            image = Image.open(image_path).convert("RGB")
            resized_image = resize_image(image)
            
            # Save resized image temporarily (optional)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            resized_path = os.path.join(RESIZED_DIR, f"{timestamp}_resized.jpg")
            resized_image.save(resized_path, "JPEG")
        except Exception as e:
            print(f"Error processing image: {e}")
            audio_manager.stop_all_audio()
            audio_manager.play_error_sound()
            return

        # Check for interruption after image processing
        if check_for_interruption():
            return
            
        # Step 2: Send to OpenAI API for image description
        try:
            # Create prompt based on wordiness setting
            prompt = f"You are standing in for someone who is blind and cannot see, \
            objectively note everything you see in the image. Don't get too poetic, and don't go over {wordiness} words."
            
            # Create OpenAI client
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            
            # Convert image to base64
            import base64
            with open(resized_path, "rb") as img_file:
                # Encode image properly
                image_data = base64.b64encode(img_file.read()).decode('utf-8')
                
                # Use the API with the encoded image
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "user", 
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
                            ]
                        }
                    ],
                    max_tokens=300,
                )
                
            # Extract generated text
            generated_text = response.choices[0].message.content
            print(f"Generated description: {generated_text}")
            
        except Exception as e:
            print(f"Error analyzing image with OpenAI: {e}")
            audio_manager.stop_all_audio()
            audio_manager.play_error_sound()
            return
            
        # Check for interruption after OpenAI processing
        if check_for_interruption():
            return
            
        # Step 3: Convert text to speech using OpenAI TTS
        try:
            # Create the final WAV file name
            final_wav = os.path.join(AUDIO_DIR, f"response_{random.randint(1000, 9999)}.wav")
            
            # Use OpenAI's Text-to-Speech API with proper streaming
            with client.audio.speech.with_streaming_response.create(
                model="tts-1", # You can also use "tts-1-hd" for higher quality
                voice="nova",  # Options: "alloy", "echo", "fable", "onyx", "nova", "shimmer"
                input=generated_text,
            ) as response:
                # Stream the response to a file
                with open(final_wav, "wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
            
            # Optimize the WAV file if needed using pydub
            try:
                # Load and optimize the audio
                audio = AudioSegment.from_file(final_wav)
                
                # Convert to smaller WAV with optimized settings
                audio = audio.set_frame_rate(22050).set_channels(1).set_sample_width(2)
                
                # Save the optimized version back to the same file
                audio.export(final_wav, format="wav")
                print(f"Optimized WAV file: {final_wav}")
            except Exception as e:
                print(f"Warning: Could not optimize WAV file, using original: {e}")
                # Continue with the original file since it should still work
            
            final_audio = final_wav
            print(f"Created WAV audio file using OpenAI TTS: {final_wav}")
            
        except Exception as e:
            print(f"Error generating speech with OpenAI TTS: {e}")
            audio_manager.stop_all_audio()
            audio_manager.play_error_sound()
            return
    
    except Exception as e:
        print(f"General error during processing: {e}")
        audio_manager.stop_all_audio()
        audio_manager.play_error_sound()
        return

    # After all processing finishes
    print("Processing completed, stopping loading sound")
    audio_manager.stop_all_audio()
    
    # Check for interruption again after processing
    if interrupted or check_for_interruption():
        print("Interrupted: skipping response playback")
        return

    # Verify file exists before playing
    if not os.path.exists(final_audio) or os.path.getsize(final_audio) < 100:
        print(f"WARNING: Audio file missing or too small: {final_audio}")
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
        
    # Send serial command to indicate request is complete and playback starting
    serialHandle.send_serial_command("REQUEST_COMPLETE")
    
    # Play the response audio
    print(f"Playing response audio: {final_audio}")
    
    # Let AudioManager handle all the details
    audio_manager.in_playback_mode = True  # Mark that we're in playback mode
    
    if audio_manager.play_sound(final_audio, 87, callback=on_audio_complete):
        print("SUCCESS: Response audio playback started")
    else:
        print("ERROR: Failed to start response audio playback")
        audio_manager.in_playback_mode = False
        
    # Cleanup photos
    keep_last_10_photos(ORIGINALS_DIR)
    manage_audio_files(AUDIO_DIR)

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

def get_sorted_audio_files():
    """Returns a list of audio files in the AUDIO_DIR sorted by modification time (newest first)."""
    audio_files = []
    try:
        for file in os.listdir(AUDIO_DIR):
            if file.lower().endswith('.wav') and 'response_' in file:
                file_path = os.path.join(AUDIO_DIR, file)
                audio_files.append(file_path)
        
        # Sort by modification time (newest first)
        audio_files.sort(key=os.path.getmtime, reverse=True)
        return audio_files
    except Exception as e:
        print(f"Error getting audio files: {e}")
        return []

def enter_playback_mode():
    """Enter audio file playback navigation mode."""
    print("Entering audio playback mode...")
    app_state.in_audio_playback_mode = True
    
    # Get sorted list of audio files
    audio_files = get_sorted_audio_files()
    
    if not audio_files:
        print("No audio files found to play back")
        audio_manager.play_error_sound()
        app_state.in_audio_playback_mode = False
        serialHandle.send_serial_command("READY")
        return False
    
    # Reset playback index
    app_state.current_playback_index = 0
    
    # Play the first file
    if audio_files:
        print(f"Playing audio file ({app_state.current_playback_index + 1}/{len(audio_files)}): {audio_files[0]}")
        audio_manager.play_sound(audio_files[0],87)
        return True
    return False

def handle_playback_navigation(direction):
    """Handle navigation within playback mode (NEXT or PREV commands)."""
    audio_files = get_sorted_audio_files()
    
    if not audio_files:
        print("No audio files available")
        audio_manager.play_error_sound()
        return
    
    # Update the index based on the direction
    if direction == "NEXT":
        app_state.current_playback_index = (app_state.current_playback_index + 1) % len(audio_files)
    elif direction == "PREV":
        app_state.current_playback_index = (app_state.current_playback_index - 1) % len(audio_files)
    
    # Play the selected file
    file_to_play = audio_files[app_state.current_playback_index]
    print(f"Playing audio file ({app_state.current_playback_index + 1}/{len(audio_files)}): {file_to_play}")
    audio_manager.play_sound(file_to_play, 87)

def exit_playback_mode():
    """Exit audio file playback navigation mode."""
    print("Exiting audio playback mode...")
    app_state.in_audio_playback_mode = False
    audio_manager.stop_all_audio()
    serialHandle.send_serial_command("READY")

def main_loop():
    print("🔄 Running command loop...")

    while True:
        cmd = serialHandle.last_command
        
        # Handle playback mode differently
        if app_state.in_audio_playback_mode:
            if cmd == "TAKE_PICTURE":
                # In playback mode, shutter button exits playback
                serialHandle.last_command = None
                exit_playback_mode()
            elif cmd == "NEXT":
                serialHandle.last_command = None
                handle_playback_navigation("NEXT")
            elif cmd == "PREV":
                serialHandle.last_command = None
                handle_playback_navigation("PREV")
            time.sleep(0.1)
            continue  # Skip the rest of the loop and restart
            
        # Handle normal mode commands
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
            
        elif cmd == "PLAY_BACK":
            serialHandle.last_command = None
            enter_playback_mode()
            
        elif cmd == "WORD_CNT":
            serialHandle.last_command = None 
            # Toggle between wordiness levels
            global wordiness
            if wordiness == 50:
                wordiness = 100
            elif wordiness == 100:
                wordiness = 200
            elif wordiness == 200:
                wordiness = 500
            elif wordiness == 500:
                wordiness = 1000
            else:
                wordiness = 50
            print(f"Set wordiness to: {wordiness}")
            serialHandle.send_serial_command(f"WORDINESS_{wordiness}")
            
        time.sleep(0.1)

if __name__ == "__main__":
    # Start serial listener
    serialHandle.start_serial_listener()
    # Run main loop
    main_loop()