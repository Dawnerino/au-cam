###################################
# picture.py (BACKUP SCRIPT THAT RUNS ALL SERVER LOGIC LOCALLY)
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
from gtts import gTTS
import tempfile
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

print(OPENAI_API_KEY)

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
            
        # Step 3: Convert text to speech using Google TTS
        try:
            # Check if AudioManager can handle MP3 files directly
            if hasattr(audio_manager, 'can_play_mp3') and audio_manager.can_play_mp3:
                # Create MP3 file directly
                mp3_filename = os.path.join(AUDIO_DIR, f"response_{random.randint(1000, 9999)}.mp3")
                tts = gTTS(text=generated_text, lang='en', slow=False)
                tts.save(mp3_filename)
                final_audio = mp3_filename
                print(f"Created MP3 audio file: {mp3_filename}")
            else:
                # Fallback to WAV conversion if MP3 not supported
                # Use gTTS to convert text to speech
                tts = gTTS(text=generated_text, lang='en', slow=False)
                
                # Create temporary MP3 file
                temp_mp3 = os.path.join(AUDIO_DIR, "temp_speech.mp3")
                tts.save(temp_mp3)
                
                # Convert MP3 to WAV using pydub
                audio = AudioSegment.from_mp3(temp_mp3)
                
                # Create final optimized WAV
                final_wav = os.path.join(AUDIO_DIR, f"response_{random.randint(1000, 9999)}.wav")
                
                # Convert to smaller WAV directly when exporting from MP3
                audio = audio.set_frame_rate(22050).set_channels(1).set_sample_width(2)
                audio.export(final_wav, format="wav")
                
                # Clean up temporary file
                os.remove(temp_mp3)
                final_audio = final_wav
                print(f"Created WAV audio file: {final_wav}")
            
        except Exception as e:
            print(f"Error generating speech with Google TTS: {e}")
            audio_manager.stop_all_audio()
            audio_manager.play_error_sound()
            return
    
    except Exception as e:
        print(f"General error during processing: {e}")
        audio_manager.stop_all_audio()
        audio_manager.play_error_sound()
        return

    # After all processing finishes
    print("Processing completed, stopping keyboard sound")
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
    
    if audio_manager.play_sound(final_audio, callback=on_audio_complete):
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