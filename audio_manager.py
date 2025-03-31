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
        
        # Check available players
        self._check_players()
        
    def _check_players(self):
        """Check which audio players are available on the system."""
        self.has_aplay = self._command_exists("aplay")
        self.has_mpg123 = self._command_exists("mpg123")
        
        # Log available players
        print(f"Audio players available - aplay: {self.has_aplay}, mpg123: {self.has_mpg123}")
        
        if not (self.has_aplay or self.has_mpg123):
            print("WARNING: No supported audio players found!")
            
    def _command_exists(self, cmd):
        """Check if a command exists on the system."""
        try:
            result = subprocess.run(["which", cmd], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE)
            return result.returncode == 0
        except:
            return False
            
    def _get_player_cmd(self, file_path):
        """Determine the appropriate player command for the file type."""
        file_lower = file_path.lower()
        
        if file_lower.endswith(".mp3"):
            if self.has_mpg123:
                return ["mpg123", "-q", file_path]
            else:
                print("ERROR: No MP3 player available")
                return None
        elif file_lower.endswith(".wav"):
            if self.has_aplay:
                return ["aplay", file_path]
            elif self.has_mpg123:
                # mpg123 can also play WAV files as fallback
                return ["mpg123", "-q", file_path]
            else:
                print("ERROR: No WAV player available")
                return None
        else:
            # For unknown extensions, try to guess based on file header
            try:
                with open(file_path, "rb") as f:
                    header = f.read(12)
                    if header.startswith(b'RIFF'):  # WAV file
                        if self.has_aplay:
                            return ["aplay", file_path]
                        elif self.has_mpg123:
                            return ["mpg123", "-q", file_path]
                    elif header.startswith(b'\xff\xfb') or header.startswith(b'ID3'):  # MP3 file
                        if self.has_mpg123:
                            return ["mpg123", "-q", file_path]
            except Exception as e:
                print(f"Error examining audio file: {e}")
                
            # Default fallback
            if self.has_mpg123:
                return ["mpg123", "-q", file_path]
            elif self.has_aplay:
                return ["aplay", file_path]
                
            print(f"ERROR: Unsupported audio format: {file_path}")
            return None

    def play_sound(self, file_path, volume=100, callback=None):
        """Play a sound file once.
        
        Args:
            file_path: Path to audio file (WAV or MP3)
            volume: Volume 0-100
            callback: Optional function to call when playback completes
        """
        # First stop any playing sounds
        self.stop_all_audio()
        
        if not os.path.exists(file_path):
            print(f"ERROR: Audio file not found: {file_path}")
            return False
            
        try:
            # Get the appropriate player command
            player_cmd = self._get_player_cmd(file_path)
            if not player_cmd:
                print(f"ERROR: No suitable player for {file_path}")
                return False
                
            print(f"Playing sound: {file_path} using {player_cmd[0]}")
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
        
        if not os.path.exists(file_path):
            print(f"ERROR: Audio file not found: {file_path}")
            return False
        
        # Get the appropriate player command
        player_cmd = self._get_player_cmd(file_path)
        if not player_cmd:
            print(f"ERROR: No suitable player for {file_path}")
            return False
            
        # Set up loop control
        self.loop_active.set()
        
        # Define the loop function
        def sound_loop():
            print(f"Starting sound loop for {file_path} using {player_cmd[0]}")
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
        
        # Kill all audio players to be thorough
        players_to_kill = []
        if self.has_aplay:
            players_to_kill.append("aplay")
        if self.has_mpg123:
            players_to_kill.append("mpg123")
            
        for player in players_to_kill:
            try:
                subprocess.run(["pkill", "-f", player], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE)
            except Exception as e:
                print(f"Error killing {player} processes: {e}")
            
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