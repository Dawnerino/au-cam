# audio_manager.py
import threading
import queue
import sounddevice as sd
import numpy as np
import wave
import time
import os

# Define command types
AUDIO_CMD_PLAY = "play"
AUDIO_CMD_LOOP = "loop"
AUDIO_CMD_STOP = "stop"

class AudioManager:
    def __init__(self):
        # Command queue for the manager thread
        self.command_queue = queue.Queue()
        self.currently_looping = False
        self.active_stream = None
        self.stream_lock = threading.Lock()  # Add lock for stream operations
        self.is_audio_playing = threading.Event()  # Track if audio is playing
        self.audio_thread = threading.Thread(target=self._manager_loop, daemon=True)
        self.audio_thread.start()

    def _manager_loop(self):
        """ Continuously processes commands from the queue. """
        while True:
            command_tuple = self.command_queue.get()
            if command_tuple is None:
                # If we ever decide to exit cleanly, we can break here
                break

            command, file_path, volume = command_tuple

            if command == AUDIO_CMD_STOP:
                self._handle_stop()

            elif command == AUDIO_CMD_PLAY and file_path:
                self._handle_play(file_path, volume)

            elif command == AUDIO_CMD_LOOP and file_path:
                self._handle_loop(file_path, volume)

            self.command_queue.task_done()

    def send_command(self, command, file_path=None, volume=100):
        """
        Public method to queue a command for the audio manager.
        - command: one of (AUDIO_CMD_PLAY, AUDIO_CMD_LOOP, AUDIO_CMD_STOP)
        - file_path: path to WAV file
        - volume: volume 0-100
        """
        self.command_queue.put((command, file_path, volume))

    def _handle_stop(self):
        """Stops any ongoing or looping audio."""
        self.currently_looping = False
        self.is_audio_playing.clear()  # Mark that audio is no longer playing
        
        with self.stream_lock:
            if self.active_stream and self.active_stream.active:
                try:
                    self.active_stream.stop()
                    self.active_stream.close()
                except Exception as e:
                    print(f"Error closing stream: {e}")
                self.active_stream = None
        print("Audio fully stopped.")

    def _handle_play(self, file_path, volume):
        """Plays a file once, in a chunked non-blocking way."""
        print(f"DEBUG: Entering _handle_play({file_path}, volume={volume})")
        self._handle_stop()  # Stop anything that's playing

        if not os.path.exists(file_path):
            print(f"Audio file not found: {file_path}")
            return

        try:
            print(f"DEBUG: About to load WAV file: {file_path}")
            audio_data, sample_rate = self._load_wav(file_path)
            # Apply volume
            audio_data = np.clip(audio_data * (volume / 100), -32768, 32767).astype(np.int16)

            print(f"Playing {file_path} at {volume}% volume")
            
            # Mark that audio is now playing
            self.is_audio_playing.set()

            with self.stream_lock:
                # Create stream
                try:
                    self.active_stream = sd.OutputStream(
                        samplerate=sample_rate,
                        channels=(audio_data.shape[1] if audio_data.ndim > 1 else 1),
                        dtype='int16'
                    )
                    print("DEBUG: Successfully opened stream, starting chunk writes.")
                    self.active_stream.start()
                    stream_active = True
                except Exception as e:
                    print(f"ERROR creating audio stream: {e}")
                    self.is_audio_playing.clear()  # Mark that audio is not playing
                    return

            # Write in small chunks
            chunk_size = 2048
            idx = 0
            total_samples = audio_data.shape[0] if audio_data.ndim == 1 else (audio_data.shape[0] * audio_data.shape[1])

            while idx < total_samples:
                # Check if stream is still valid before writing
                with self.stream_lock:
                    if not self.active_stream or not self.active_stream.active:
                        break
                    
                    end_idx = min(idx + chunk_size, total_samples)

                    if audio_data.ndim == 1:
                        chunk = audio_data[idx:end_idx]
                    else:
                        # shape: (frames, channels)
                        chunk = audio_data[idx:end_idx, :]

                    try:
                        self.active_stream.write(chunk)
                    except Exception as e:
                        print(f"Error writing to stream: {e}")
                        break
                    print(f"DEBUG: Wrote chunk {idx}/{total_samples} to stream")
                
                idx = end_idx

            time.sleep(0.1)  # Let buffer drain
            
            # Only stop if we're still the active stream
            print(f"DEBUG: Audio playback of {file_path} completed successfully")
            with self.stream_lock:
                if self.active_stream and self.active_stream.active:
                    self._handle_stop()  # Stop automatically after single playback
                else:
                    # Just clear the playing flag if the stream was already stopped
                    self.is_audio_playing.clear()
        
        except Exception as e:
            print(f"Error in audio playback: {e}")

    def is_playing(self):
        """Returns True if audio is currently playing."""
        return self.is_audio_playing.is_set()
        
    def _handle_loop(self, file_path, volume):
        """Loops a WAV file until a STOP command is issued."""
        self._handle_stop()
        if not os.path.exists(file_path):
            print(f"Audio file not found: {file_path}")
            return

        try:
            self.currently_looping = True
            self.is_audio_playing.set()  # Mark that audio is now playing
            print(f"Looping {file_path} at {volume}% volume")

            audio_data, sample_rate = self._load_wav(file_path)
            audio_data = np.clip(audio_data * (volume / 100), -32768, 32767).astype(np.int16)

            with self.stream_lock:
                self.active_stream = sd.OutputStream(
                    samplerate=sample_rate,
                    channels=(audio_data.shape[1] if audio_data.ndim > 1 else 1),
                    dtype='int16'
                )
                self.active_stream.start()

            while self.currently_looping:
                chunk_size = 2048
                idx = 0
                total_samples = audio_data.shape[0] if audio_data.ndim == 1 else (audio_data.shape[0]*audio_data.shape[1])
                
                while idx < total_samples and self.currently_looping:
                    with self.stream_lock:
                        if not self.active_stream or not self.active_stream.active:
                            self.currently_looping = False
                            break
                            
                        end_idx = min(idx + chunk_size, total_samples)
                        if audio_data.ndim == 1:
                            chunk = audio_data[idx:end_idx]
                        else:
                            chunk = audio_data[idx:end_idx, :]
                            
                        try:
                            self.active_stream.write(chunk)
                        except Exception as e:
                            print(f"Error writing to stream in loop: {e}")
                            self.currently_looping = False
                            break
                    
                    idx = end_idx

            # After stopping the loop:
            with self.stream_lock:
                if self.active_stream and self.active_stream.active:
                    self._handle_stop()
                    
        except Exception as e:
            print(f"Error in audio loop: {e}")
            self.currently_looping = False

    def _load_wav(self, file_path):
        """Loads a WAV file into NumPy array."""
        try:
            print(f"LOADING AUDIO: Attempting to load {file_path}")
            print(f"LOADING AUDIO: Absolute path: {os.path.abspath(file_path)}")
            
            # Verify file exists
            if not os.path.exists(file_path):
                print(f"ERROR: Audio file does not exist: {file_path}")
                print(f"Checking current directory: {os.getcwd()}")
                return np.zeros(1024, dtype=np.int16), 44100
                
            # Check file size before opening
            file_size = os.path.getsize(file_path)
            print(f"DEBUG: File size of {file_path}: {file_size} bytes")
            
            if file_size > 10000000:  # If file larger than 10MB
                print(f"WARNING: Audio file {file_path} is very large ({file_size} bytes). This might cause issues.")
            
            try:
                # Try first reading the header to check if it's valid
                with open(file_path, 'rb') as f:
                    header = f.read(12)
                    if not header.startswith(b'RIFF'):
                        print(f"ERROR: Not a valid WAV file (no RIFF header): {file_path}")
                        print(f"First bytes: {header}")
                        return np.zeros(1024, dtype=np.int16), 44100
            except Exception as header_e:
                print(f"ERROR reading file header: {header_e}")
                
            try:
                with wave.open(file_path, 'rb') as wf:
                    # Get basic info first
                    channels = wf.getnchannels()
                    sample_rate = wf.getframerate()
                    n_frames = wf.getnframes()
                    print(f"DEBUG: WAV header info - frames: {n_frames}, rate: {sample_rate}Hz, channels: {channels}")
                    
                    # Read data in chunks if file is large
                    if n_frames > 1000000:  # If over ~22 seconds at 44.1kHz
                        print(f"WARNING: Large audio file, reading first 10 seconds only")
                        frames = wf.readframes(441000)  # ~10 seconds of audio at 44.1kHz
                    else:
                        frames = wf.readframes(n_frames)
                        
                    audio_data = np.frombuffer(frames, dtype=np.int16)
            except Exception as wave_e:
                print(f"ERROR parsing WAV file: {wave_e}")
                return np.zeros(1024, dtype=np.int16), 44100

            # Debug information about the loaded audio
            print(f"DEBUG: Loaded audio file {file_path}")
            print(f"DEBUG: Audio length: {len(audio_data)} samples, Sample rate: {sample_rate}Hz, Channels: {channels}")
            
            if len(audio_data) == 0:
                print(f"WARNING: Audio file {file_path} contains no data!")
                # Return minimal valid data to prevent crashes
                return np.zeros(1024, dtype=np.int16), 44100

            if channels == 2:
                audio_data = audio_data.reshape(-1, 2)

            return audio_data, sample_rate
            
        except Exception as e:
            print(f"ERROR: Failed to load audio file {file_path}: {e}")
            # Return minimal valid data to prevent crashes
            return np.zeros(1024, dtype=np.int16), 44100
