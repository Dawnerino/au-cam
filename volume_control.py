import RPi.GPIO as GPIO
import threading
import time
import subprocess

class VolumeEncoder:
    """Class to handle a rotary encoder for volume control."""
    
    def __init__(self, clk_pin=17, dt_pin=23, button_pin=27, min_volume=50, max_volume=100, step=1):
        """
        Initialize the rotary encoder.
        
        Args:
            clk_pin: GPIO pin for the CLK signal (defaults to GPIO 17)
            dt_pin: GPIO pin for the DT signal (defaults to GPIO 23)
            button_pin: GPIO pin for the push button (defaults to GPIO 27)
            min_volume: Minimum volume level (50-100)
            max_volume: Maximum volume level (50-100)
            step: Step size for volume changes (1)
        """
        # Store pin assignments
        self.clk_pin = clk_pin
        self.dt_pin = dt_pin
        self.button_pin = button_pin
        
        # Volume settings
        self.min_volume = max(50, min(min_volume, 100))
        self.max_volume = max(50, min(max_volume, 100))
        self.step = 1
        
        # Internal state
        self.current_volume = 80  # Default starting volume
        self.last_encoded = 0
        self.last_button_state = 1  # Assume pulled up (1 = not pressed)
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        
        # Initialize GPIO
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.clk_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(self.dt_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(self.button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            
            # Read initial state
            self.last_encoded = (GPIO.input(self.clk_pin) << 1) | GPIO.input(self.dt_pin)
            print(f"Rotary encoder initialized on pins: CLK={clk_pin}, DT={dt_pin}, BTN={button_pin}")
            print(f"Initial volume set to: {self.current_volume}%")
            
            # Set initial system volume
            self.set_system_volume(self.current_volume)
        except Exception as e:
            print(f"Error initializing GPIO: {e}")
            raise
    
    def set_system_volume(self, volume):
        """Set the system volume using amixer."""
        try:
            # Ensure volume is within valid range
            volume = max(self.min_volume, min(volume, self.max_volume))
            
            # Set volume using amixer (for Raspberry Pi)
            subprocess.run(
                ["amixer", "sset", "SoftMaster", f"{volume}%"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
            self.current_volume = volume
            print(f"System volume set to {volume}%")
            return True
        except Exception as e:
            print(f"Error setting system volume: {e}")
            return False
    
    def get_volume(self):
        """Get the current volume level."""
        return self.current_volume
    
    def _read_encoder(self):
        """Read encoder state and update volume accordingly."""
        try:
            # Get the current state
            MSB = GPIO.input(self.clk_pin)
            LSB = GPIO.input(self.dt_pin)
            
            # Convert binary values to a number 0-3
            encoded = (MSB << 1) | LSB
            
            # Check if state changed since last read
            if encoded != self.last_encoded:
                # Determine rotation direction using gray code
                sum = (self.last_encoded << 2) | encoded
                
                # Clockwise (0010, 1011, 1101, 0100) -> 2, 11, 13, 4
                if sum == 2 or sum == 11 or sum == 13 or sum == 4:
                    # Clockwise rotation - increase volume
                    self.adjust_volume(self.step)
                
                # Counter-clockwise (0001, 0111, 1110, 1000) -> 1, 7, 14, 8
                elif sum == 1 or sum == 7 or sum == 14 or sum == 8:
                    # Counter-clockwise rotation - decrease volume
                    self.adjust_volume(-self.step)
                
                # Update last state
                self.last_encoded = encoded
                
                # Short delay for debouncing
                time.sleep(0.001)
                
        except Exception as e:
            print(f"Error reading encoder: {e}")
    
    def _read_button(self):
        """Read button state and toggle mute if pressed."""
        try:
            # Get current button state
            button_state = GPIO.input(self.button_pin)
            
            # Check for button press (transition from 1 to 0)
            if button_state == 0 and self.last_button_state == 1:
                # Button pressed - toggle mute
                if self.current_volume > 50:
                    # Currently unmuted - save volume and mute
                    self._saved_volume = self.current_volume
                    self.set_system_volume(50)
                    print("Muted audio to 50%")
                else:
                    # Currently at minimum - restore saved volume
                    self.set_system_volume(getattr(self, '_saved_volume', 80))
                    print("Unmuted audio")
                
                # Debounce delay
                time.sleep(0.2)
            
            # Update last state
            self.last_button_state = button_state
            
        except Exception as e:
            print(f"Error reading button: {e}")
    
    def adjust_volume(self, change):
        """
        Adjust volume by the specified amount.
        
        Args:
            change: Amount to change volume by (+/-)
        """
        with self.lock:
            new_volume = self.current_volume + change
            self.set_system_volume(new_volume)
    
    def _monitor_loop(self):
        """Main monitoring loop for the encoder."""
        print("Starting volume encoder monitoring loop")
        
        while self.running:
            # Read encoder and button states
            self._read_encoder()
            self._read_button()
            
            # Smaller delay to catch fast rotations
            time.sleep(0.002)
    
    def start(self):
        """Start monitoring the rotary encoder."""
        if self.thread and self.thread.is_alive():
            print("Volume encoder monitoring already running")
            return False
        
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        return True
    
    def stop(self):
        """Stop monitoring the rotary encoder."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        
        # Clean up GPIO
        try:
            GPIO.cleanup(self.clk_pin)
            GPIO.cleanup(self.dt_pin)
            GPIO.cleanup(self.button_pin)
            print("Volume encoder monitoring stopped and pins cleaned up")
        except Exception as e:
            print(f"Error cleaning up GPIO: {e}")
    
    def set_step_size(self, step):
        """Set the step size for volume changes (fixed at 1)."""
        with self.lock:
            # Always use step size of 1, regardless of input
            self.step = 1
            print("Volume step size fixed at 1")
            return self.step

# Singleton instance - will be initialized when module is imported
volume_encoder = None

def init_volume_encoder():
    """Initialize and start the volume encoder."""
    global volume_encoder
    
    if volume_encoder is None:
        try:
            # Create and start the encoder
            volume_encoder = VolumeEncoder()
            volume_encoder.start()
            print("Volume encoder initialized and started")
        except Exception as e:
            print(f"Failed to initialize volume encoder: {e}")
    
    return volume_encoder

def get_volume():
    """Get the current system volume."""
    global volume_encoder
    
    if volume_encoder:
        return volume_encoder.get_volume()
    return 0

def set_volume(volume):
    """Set the system volume directly."""
    global volume_encoder
    
    if volume_encoder:
        return volume_encoder.set_system_volume(volume)
    return False

def cleanup():
    """Stop and clean up the volume encoder."""
    global volume_encoder
    
    if volume_encoder:
        volume_encoder.stop()
        volume_encoder = None
        print("Volume encoder cleaned up")

if __name__ == "__main__":
    # Test the encoder when run directly
    try:
        print("Testing volume encoder. Press Ctrl+C to exit.")
        encoder = init_volume_encoder()
        
        # Keep the main thread alive
        while True:
            time.sleep(1)
            print(f"Current volume: {get_volume()}%")
            
    except KeyboardInterrupt:
        print("Test interrupted")
    finally:
        cleanup()
        print("Test completed")