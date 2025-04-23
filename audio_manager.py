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
        
        # Check available audio players
        self.has_aplay = self._command_exists("aplay")  # For WAV files
        self.has_mpg123 = self._command_exists("mpg123")  # For MP3 files
        
        # Flag to indicate if MP3 playback is supported
        self.can_play_mp3 = self.has_mpg123
        
        # Log available players
        print(f"Audio players available - aplay: {self.has_aplay}, mpg123: {self.has_mpg123}")
        
        if not (self.has_aplay or self.has_mpg123):
            print("WARNING: No supported audio player found!")
            
    def _command_exists(self, cmd):
        """Check if a command exists on the system."""
        try:
            result = subprocess.run(["which", cmd], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE)
            return result.returncode == 0
        except:
            return False

    def _set_volume(self, volume):
        """Set system volume using amixer (0-100)"""
        try:
            # Ensure volume is within valid range
            volume = max(0, min(100, volume))
            
            # Set volume using amixer (for Raspberry Pi)
            subprocess.run(
                ["amixer", "sset", "SoftMaster", f"{volume}%"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
            print(f"Volume set to {volume}%")
            return True
        except Exception as e:
            print(f"Error setting volume: {e}")
            return False
            
    def play_sound(self, file_path, volume=100, callback=None):
        """Play a sound file once.
        
        Args:
            file_path: Path to audio file (WAV or MP3)
            volume: Volume 0-100
            callback: Optional function to call when playback completes
        """
        # First stop any playing sounds
        self.stop_all_audio()
        
        # Set volume
        self._set_volume(volume)
        
        if not os.path.exists(file_path):
            print(f"ERROR: Audio file not found: {file_path}")
            return False
            
        try:
            # Check file type and select appropriate player
            file_ext = os.path.splitext(file_path.lower())[1]
            
            if file_ext == '.wav':
                if not self.has_aplay:
                    print("ERROR: No WAV player (aplay) available")
                    return False
                    
                player_cmd = ["aplay", file_path]
                
            elif file_ext == '.mp3':
                if not self.has_mpg123:
                    print("ERROR: No MP3 player (mpg123) available")
                    return False
                    
                player_cmd = ["mpg123", "-q", file_path]  # -q for quiet mode
                
            else:
                print(f"ERROR: Unsupported file format: {file_ext}")
                return False
                
            print(f"Playing sound: {file_path} at volume {volume}%")
            proc = subprocess.Popen(player_cmd, 
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
        
        # Set volume
        self._set_volume(volume)
        
        if not os.path.exists(file_path):
            print(f"ERROR: Audio file not found: {file_path}")
            return False
        
        # Check file type and select appropriate player
        file_ext = os.path.splitext(file_path.lower())[1]
        
        if file_ext == '.wav':
            if not self.has_aplay:
                print("ERROR: No WAV player (aplay) available")
                return False
                
            player_cmd = ["aplay", file_path]
            
        elif file_ext == '.mp3':
            if not self.has_mpg123:
                print("ERROR: No MP3 player (mpg123) available")
                return False
                
            player_cmd = ["mpg123", "-q", file_path]  # -q for quiet mode
            
        else:
            print(f"ERROR: Unsupported file format: {file_ext}")
            return False
            
        # Set up loop control
        self.loop_active.set()
        
        # Define the loop function
        def sound_loop():
            print(f"Starting sound loop for {file_path} at volume {volume}%")
            while self.loop_active.is_set():
                try:
                    # Play the sound once
                    proc = subprocess.Popen(player_cmd, 
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
        
        # Kill all audio player instances to be thorough
        try:
            # Kill WAV players
            if self.has_aplay:
                subprocess.run(["pkill", "-f", "aplay"], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE)
                
            # Kill MP3 players
            if self.has_mpg123:
                subprocess.run(["pkill", "-f", "mpg123"], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE)
                
        except Exception as e:
            print(f"Error killing audio processes: {e}")
            
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
        
    def play_sound_and_wait(self, file_path, volume=100):
        """Play a sound and wait for it to finish before returning.
        
        Args:
            file_path: Path to audio file (WAV or MP3)
            volume: Volume 0-100
            
        Returns:
            True if sound was played successfully, False otherwise
        """
        if not os.path.exists(file_path):
            print(f"ERROR: Audio file not found: {file_path}")
            return False
            
        # Create an event to signal completion
        complete_event = threading.Event()
        
        # Define callback for when sound finishes
        def on_complete():
            complete_event.set()
            
        # Play the sound with our callback
        success = self.play_sound(file_path, volume, callback=on_complete)
        
        if success:
            # Wait for sound to complete
            complete_event.wait()
            return True
        else:
            return False

    def send_command(self, command, file_path=None, volume=100):
        """Legacy command interface."""
        if command == AUDIO_CMD_PLAY and file_path:
            return self.play_sound(file_path, volume)
        elif command == AUDIO_CMD_LOOP and file_path:
            return self.loop_sound(file_path, volume)
        elif command == AUDIO_CMD_STOP:
            return self.stop_all_audio()
        return False