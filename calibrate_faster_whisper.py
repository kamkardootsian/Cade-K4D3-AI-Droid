import pyaudio
import numpy as np
from faster_whisper import WhisperModel
import threading
import queue
import time  # Added missing import

class WhisperCalibration:
    def __init__(self, model_size="base"):
        self.audio_queue = queue.Queue()
        self.volume_threshold = -30  # Default threshold
        self.is_speaking = False
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        
    def find_audio_device(self):
        """Find and select the correct audio input device"""
        audio = pyaudio.PyAudio()
        
        print("Searching for audio devices...")
        input_devices = []
        
        for i in range(audio.get_device_count()):
            try:
                info = audio.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    input_devices.append((i, info))
                    print(f"Device {i}: {info['name']} (Channels: {info['maxInputChannels']})")
            except:
                continue
        
        # Try to find USB webcam microphone
        webcam_keywords = ['webcam', 'camera', 'usb', 'c922', 'c270', 'logitech']
        for i, info in input_devices:
            if any(keyword in info['name'].lower() for keyword in webcam_keywords):
                print(f"Found webcam microphone: {info['name']}")
                audio.terminate()
                return i
        
        # If no webcam found, use default
        print("Using default input device")
        audio.terminate()
        return None
    
    def calculate_volume(self, audio_data):
        """Calculate volume in dB safely"""
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        if len(audio_array) == 0:
            return -60
        
        try:
            # Use float32 to avoid overflow issues
            audio_float = audio_array.astype(np.float32)
            squared = audio_float ** 2
            mean_squared = np.mean(squared)
            
            # Avoid sqrt of zero or negative numbers
            if mean_squared <= 0:
                return -60
                
            rms = np.sqrt(mean_squared)
            if rms > 0:
                return 20 * np.log10(rms / 32768.0)
            else:
                return -60
        except Exception as e:
            return -60
    
    def test_microphone(self, audio, device_index=None, duration=3):
        """Test if microphone is working"""
        print("Testing microphone...")
        
        try:
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=1024
            )
            
            volumes = []
            start_time = time.time()
            
            while time.time() - start_time < duration:
                try:
                    data = stream.read(1024, exception_on_overflow=False)
                    db = self.calculate_volume(data)
                    volumes.append(db)
                    
                    # Show quick feedback
                    bar = '█' * max(0, min(20, int((db + 60) / 3)))
                    print(f"\rTesting: [{bar:20}] {db:6.1f} dB", end='')
                    
                except IOError as e:
                    if "Input overflowed" in str(e):
                        continue  # Skip overflow errors
                    else:
                        raise e
            
            stream.stop_stream()
            stream.close()
            
            max_volume = max(volumes) if volumes else -60
            print(f"\nMax volume detected: {max_volume:.1f} dB")
            
            return max_volume > -50  # Return True if some audio was detected
            
        except Exception as e:
            print(f"\nMicrophone test failed: {e}")
            return False
    
    def find_optimal_threshold(self, duration=10):
        """Find optimal volume threshold for speech detection"""
        print("Microphone Calibration for faster-whisper")
        print("=" * 50)
        
        # Find the right audio device
        device_index = self.find_audio_device()
        
        audio = pyaudio.PyAudio()
        
        # Test microphone first
        if not self.test_microphone(audio, device_index):
            print("❌ Microphone not working. Please check:")
            print("1. Is your webcam/microphone connected?")
            print("2. Check system audio settings")
            print("3. Try a different USB port")
            audio.terminate()
            return self.volume_threshold
        
        print(f"\nSpeak naturally for {duration} seconds to calibrate...")
        
        try:
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=1024
            )
            
            volumes = []
            start_time = time.time()
            last_update = 0
            
            while time.time() - start_time < duration:
                try:
                    data = stream.read(1024, exception_on_overflow=False)
                    db = self.calculate_volume(data)
                    volumes.append(db)
                    
                    # Update display at reasonable frequency (not every loop)
                    current_time = time.time()
                    if current_time - last_update > 0.1:  # Update every 100ms
                        bar_length = max(0, min(30, int((db + 60) / 2)))
                        bar = '█' * bar_length
                        spaces = ' ' * (30 - bar_length)
                        
                        # Color coding
                        if db > -25:
                            color = '\033[92m'  # Green
                        elif db > -40:
                            color = '\033[93m'  # Yellow
                        else:
                            color = '\033[91m'  # Red
                        
                        reset = '\033[0m'
                        
                        elapsed = time.time() - start_time
                        progress = int((elapsed / duration) * 40)
                        progress_bar = '█' * progress + '░' * (40 - progress)
                        
                        print(f"\rTime: [{progress_bar}] {elapsed:.1f}s | "
                              f"Volume: {color}[{bar}{spaces}]{reset} {db:6.1f} dB", 
                              end='', flush=True)
                        last_update = current_time
                    
                except IOError as e:
                    if "Input overflowed" in str(e):
                        continue  # Skip overflow errors
                    else:
                        print(f"\nAudio error: {e}")
                        break
            
            stream.stop_stream()
            stream.close()
            
        except Exception as e:
            print(f"\nError during calibration: {e}")
        finally:
            audio.terminate()
        
        # Calculate optimal threshold
        if volumes:
            volumes_array = np.array(volumes)
            
            print(f"\n\n{'='*50}")
            print("CALIBRATION RESULTS")
            print(f"{'='*50}")
            print(f"Samples collected: {len(volumes)}")
            print(f"Average volume: {np.mean(volumes_array):.1f} dB")
            print(f"Maximum volume: {np.max(volumes_array):.1f} dB")
            print(f"Minimum volume: {np.min(volumes_array):.1f} dB")
            
            # Filter out complete silence
            speech_volumes = volumes_array[volumes_array > -50]
            
            if len(speech_volumes) > 0:
                # Use 15th percentile as threshold (more conservative than 10th)
                optimal_threshold = np.percentile(speech_volumes, 15)
                self.volume_threshold = float(optimal_threshold)
                
                print(f"\n✅ Speech detected!")
                print(f"Active audio samples: {len(speech_volumes)}")
                print(f"Speech volume range: {np.min(speech_volumes):.1f} to {np.max(speech_volumes):.1f} dB")
                print(f"Optimal threshold: {optimal_threshold:.1f} dB")
                print("Speech will be detected when volume exceeds this threshold")
            else:
                print(f"\n❌ No speech detected")
                print("Background noise level:", f"{np.mean(volumes_array):.1f} dB")
                print("Using default threshold:", f"{self.volume_threshold:.1f} dB")
                print("\nTroubleshooting tips:")
                print("1. Speak louder and closer to the microphone")
                print("2. Check if microphone is muted in system settings")
                print("3. Try using 'pactl list sources short' to check devices")
        else:
            print("\n❌ No audio data collected")
            print("Using default threshold:", f"{self.volume_threshold:.1f} dB")
        
        return self.volume_threshold

# Usage example for calibration
if __name__ == "__main__":
    calibrator = WhisperCalibration()
    threshold = calibrator.find_optimal_threshold(duration=10)
    print(f"\nUse this threshold in your faster-whisper application: {threshold:.1f} dB")
