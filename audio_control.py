import sounddevice as sd
import numpy as np
import wave
import threading
import time
import os

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

    # Reshape if stereo
    if channels == 2:
        audio_data = audio_data.reshape(-1, 2)

    return audio_data, sample_rate

def play_audio(file_path, volume=100):
    """Plays a WAV file once with error handling and volume control."""
    global current_thread, is_looping, current_audio

    stop_audio()  # Stop any previous playback

    if not os.path.exists(file_path):
        print(f"❌ ERROR: Audio file not found: {file_path}")
        return False

    try:
        audio_data, sample_rate = load_wav(file_path)

        # Apply volume (scale samples but prevent clipping)
        audio_data = np.clip(audio_data * (volume / 100), -32768, 32767).astype(np.int16)

        def playback():
            sd.stop()  # Ensure no old playback is running
            time.sleep(0.1)  # Small delay to let stop take effect
            sd.play(audio_data, samplerate=sample_rate)
            sd.wait()

        current_audio = audio_data
        is_looping = False

        current_thread = threading.Thread(target=playback, daemon=True)
        current_thread.start()

        time.sleep(0.1)  # Ensure thread starts before returning
        print(f"✅ Playing {file_path} at {volume}% volume")
        return True

    except Exception as e:
        print(f"❌ ERROR: Failed to play {file_path}: {e}")
        return False

def loop_audio(file_path, volume=100):
    """Loops a WAV file until stopped."""
    global current_thread, is_looping, current_audio

    stop_audio()

    audio_data, sample_rate = load_wav(file_path)

    # Apply volume (scale samples)
    audio_data = (audio_data * (volume / 100)).astype(np.int16)

    def playback():
        while is_looping:
            sd.play(audio_data, samplerate=sample_rate)
            sd.wait()

    current_audio = audio_data
    is_looping = True

    current_thread = threading.Thread(target=playback, daemon=True)
    current_thread.start()

    print(f"Looping {file_path} at {volume}% volume")

def stop_audio():
    """Stops any currently playing audio."""
    global current_thread, is_looping

    is_looping = False
    if current_thread and current_thread.is_alive():
        sd.stop()
        current_thread.join(timeout=1)
        current_thread = None
    print("Audio stopped")

def kill_audio():
    """Alias to stop_audio."""
    stop_audio()

def is_playing():
    """Checks if audio is currently playing."""
    global current_thread

    if current_thread and current_thread.is_alive():
        return True
    return False

def unpause_audio():
    """There is no pause in sounddevice; this is a no-op to match your previous interface."""
    pass


# Example usage
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
