# audio_manager.py
import threading
import subprocess
import time
import os

# Define command types
AUDIO_CMD_PLAY = "play"     # Play a sound once
AUDIO_CMD_LOOP = "loop"     # Loop a sound until stopped
AUDIO_CMD_STOP = "stop"     # Stop any playing sound

class AudioManager:
    def __init__(self):
        # State tracking
        self.is_audio_playing = threading.Event()  # Flag to track if audio is playing
        self.current_audio_pid = None  # Track current audio process ID
        self.in_playback_mode = False  # Track if we're in playback cycle
        
        # For looping sounds
        self.loop_active = threading.Event()
        self.loop_thread = None

    def play_sound(self, file_path, volume=100, callback=None):
        """Play a sound file once.
        
        Args:
            file_path: Path to WAV file
            volume: Volume 0-100
            callback: Optional function to call when playback completes
        """
        # First stop any playing sounds
        self.stop_all_audio()
        
        if not os.path.exists(file_path):
            print(f"ERROR: Audio file not found: {file_path}")
            return False
            
        try:
            print(f"Playing sound: {file_path}")
            proc = subprocess.Popen(["aplay", file_path], 
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            
            # Set state flags
            self.current_audio_pid = proc.pid
            self.is_audio_playing.set()
            
            # Start a monitor thread to reset flags when playback completes
            def monitor_playback():
                try:
                    proc.wait()  # Wait for process to complete
                    print(f"Sound playback of {file_path} completed")
                    self.is_audio_playing.clear()
                    self.current_audio_pid = None
                    
                    # Reset playback mode when audio finishes
                    self.in_playback_mode = False
                    
                    # Call the callback if provided
                    if callback:
                        callback()
                        
                except Exception as e:
                    print(f"Error in monitor thread: {e}")
            
            monitor_thread = threading.Thread(target=monitor_playback, daemon=True)
            monitor_thread.start()
            
            return True
            
        except Exception as e:
            print(f"ERROR playing sound: {e}")
            return False

    def loop_sound(self, file_path, volume=100):
        """Loop a sound until stopped."""
        # First stop any playing sounds
        self.stop_all_audio()
        
        if not os.path.exists(file_path):
            print(f"ERROR: Audio file not found: {file_path}")
            return False
            
        # Set up loop control
        self.loop_active.set()
        
        # Define the loop function
        def sound_loop():
            print(f"Starting sound loop for {file_path}")
            while self.loop_active.is_set():
                try:
                    # Play the sound once
                    proc = subprocess.Popen(["aplay", "-q", file_path], 
                                           stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE)
                    
                    # Update state
                    self.current_audio_pid = proc.pid
                    self.is_audio_playing.set()
                    
                    # Wait for this play to complete
                    proc.wait()
                    
                    # Small delay between loops
                    if self.loop_active.is_set():
                        time.sleep(0.1)
                        
                except Exception as e:
                    print(f"Error in sound loop: {e}")
                    time.sleep(0.5)  # Wait before retry
            
            print("Sound loop terminated")
            
        # Start the loop in a background thread
        self.loop_thread = threading.Thread(target=sound_loop, daemon=True)
        self.loop_thread.start()
        return True

    def stop_all_audio(self):
        """Stop all playing audio."""
        # Clear loop flag if active
        self.loop_active.clear()
        
        # Kill specific process if we know its PID
        if self.current_audio_pid:
            try:
                subprocess.run(["kill", str(self.current_audio_pid)], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE)
                print(f"Killed audio process {self.current_audio_pid}")
            except Exception as e:
                print(f"Error killing process {self.current_audio_pid}: {e}")
        
        # Kill all aplay processes to be thorough
        try:
            subprocess.run(["pkill", "-f", "aplay"], 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
        except Exception as e:
            print(f"Error killing aplay processes: {e}")
            
        # Reset state
        self.is_audio_playing.clear()
        self.current_audio_pid = None
        
        # Small delay to ensure audio is fully stopped
        time.sleep(0.1)
        return True

    def play_error_sound(self):
        """Play the error sound."""
        return self.play_sound("ahh.wav")

    def is_playing(self):
        """Check if audio is currently playing."""
        return self.is_audio_playing.is_set()

    def send_command(self, command, file_path=None, volume=100):
        """Legacy command interface."""
        if command == AUDIO_CMD_PLAY and file_path:
            return self.play_sound(file_path, volume)
        elif command == AUDIO_CMD_LOOP and file_path:
            return self.loop_sound(file_path, volume)
        elif command == AUDIO_CMD_STOP:
            return self.stop_all_audio()
        return False
