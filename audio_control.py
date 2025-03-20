import sounddevice as sd
import numpy as np
import wave
import threading
import time
import os

# Global lock to prevent overlapping audio operations
audio_lock = threading.Lock()

# Global control
current_thread = None
current_audio = None
is_looping = False

def load_wav(file_path):
    """Loads a WAV file into a NumPy array for playback."""
    with wave.open(file_path, 'rb') as wf:
        frames = wf.readframes(wf.getnframes())
        audio_data = np.frombuffer(frames, dtype=np.int16)
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()

    if channels == 2:
        audio_data = audio_data.reshape(-1, 2)

    return audio_data, sample_rate

def _play_audio_impl(file_path, volume=100):
    """Internal function to actually play the audio once."""
    global current_thread, is_looping, current_audio

    # Load & prepare audio data
    audio_data, sample_rate = load_wav(file_path)
    audio_data = np.clip(audio_data * (volume / 100), -32768, 32767).astype(np.int16)

    def playback():
        sd.stop()        # Ensure no old playback is running
        time.sleep(0.1)  # Tiny delay so device can settle
        sd.play(audio_data, samplerate=sample_rate)
        sd.wait()        # Block until playback finishes

    current_audio = audio_data
    is_looping = False

    current_thread = threading.Thread(target=playback, daemon=True)
    current_thread.start()

    time.sleep(0.1)  # Ensure thread truly starts
    print(f"✅ Playing {file_path} at {volume}% volume")
    return True

def play_audio(file_path, volume=100):
    """Plays a WAV file once with error handling and volume control, safely."""
    with audio_lock:
        # Stop old audio first
        _stop_audio_impl()  

        if not os.path.exists(file_path):
            print(f"❌ ERROR: Audio file not found: {file_path}")
            return False

        try:
            return _play_audio_impl(file_path, volume)
        except Exception as e:
            print(f"❌ ERROR: Failed to play {file_path}: {e}")
            return False

def _loop_audio_impl(file_path, volume=100):
    """Internal function to actually loop the audio."""
    global current_thread, is_looping, current_audio

    audio_data, sample_rate = load_wav(file_path)
    audio_data = np.clip(audio_data * (volume / 100), -32768, 32767).astype(np.int16)

    def playback():
        while is_looping:
            sd.stop()
            time.sleep(0.1)
            sd.play(audio_data, samplerate=sample_rate)
            sd.wait()

    current_audio = audio_data
    is_looping = True

    current_thread = threading.Thread(target=playback, daemon=True)
    current_thread.start()

    print(f"🔄 Looping {file_path} at {volume}% volume")

def loop_audio(file_path, volume=100):
    """Loops a WAV file until stopped, ensuring safe concurrency."""
    with audio_lock:
        _stop_audio_impl()  # Stop any previous playback

        if not os.path.exists(file_path):
            print(f"❌ ERROR: Audio file not found: {file_path}")
            return False

        try:
            _loop_audio_impl(file_path, volume)
            return True
        except Exception as e:
            print(f"❌ ERROR: Failed to loop {file_path}: {e}")
            return False

def _stop_audio_impl():
    """Actual logic to stop audio without the global lock."""
    global current_thread, is_looping

    if not is_looping and not (current_thread and current_thread.is_alive()):
        print("🛑 No audio is playing, skipping stop_audio()")
        return

    is_looping = False
    if current_thread and current_thread.is_alive():
        print("🛑 Stopping current audio thread safely...")
        sd.stop()
        current_thread.join(timeout=1)
        current_thread = None
    print("🛑 Audio fully stopped and memory cleaned up")

def stop_audio():
    """Stops any currently playing audio if it's active, safely with lock."""
    with audio_lock:
        _stop_audio_impl()

def kill_audio():
    """Alias to stop_audio."""
    stop_audio()

def is_playing():
    """Checks if audio is currently playing."""
    global current_thread
    with audio_lock:
        if current_thread and current_thread.is_alive():
            return True
        return False

def unpause_audio():
    """No-op to match prior interface."""
    pass

if __name__ == "__main__":
    test_file = "keyboard.wav"

    print("Playing audio once...")
    play_audio(test_file, volume=75)
    time.sleep(2)

    print("Stopping audio...")
    stop_audio()
    time.sleep(1)

    print("Starting loop...")
    loop_audio(test_file, volume=20)
    time.sleep(5)

    print("Stopping loop...")
    stop_audio()
    print("All done.")
