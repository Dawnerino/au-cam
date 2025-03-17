import json
import socket
import time

MPV_SOCKET = "/tmp/mpvsocket"

def send_mpv_command(command):
    """Sends a JSON command to the MPV socket."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(MPV_SOCKET)
            client.sendall(json.dumps(command).encode() + b"\n")
            response = client.recv(1024)
            return json.loads(response)  # Return parsed JSON response
    except Exception as e:
        print(f"Error: {e}")
        return None

def play_audio(file_path):
    """Plays an audio file and waits for playback to start."""
    stop_audio()  # Ensure no other audio is playing
    print(f"Trying to play: {file_path}")

    command = {"command": ["loadfile", file_path]}
    response = send_mpv_command(command)
    print(f"MPV Response: {response}")  # Debugging output

    # Wait for MPV to start playing
    for _ in range(10):  # Try for up to 2 seconds
        time.sleep(0.2)
        if is_playing():
            print("Audio is now playing.")
            return True
    print("Warning: MPV did not start playback.")
    return False

def stop_audio():
    """Stops audio playback."""
    command = {"command": ["stop"]}
    return send_mpv_command(command)

def is_playing():
    """Checks if MPV is actively playing audio."""
    command = {"command": ["get_property", "playback-time"]}
    response = send_mpv_command(command)

    if response and "data" in response and response["data"] > 0:
        return True
    return False

# Example Usage
if __name__ == "__main__":
    audio_file = "/home/b-cam/Scripts/blindCam/audio/response_4872.wav"
    
    print("Playing audio...")
    if play_audio(audio_file):
        print("Waiting for 3 seconds while audio plays...")
        time.sleep(3)  # Let it play for 3 seconds

    print("Stopping audio...")
    print(stop_audio())
