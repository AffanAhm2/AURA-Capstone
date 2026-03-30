# max98357_test.py
import sounddevice as sd
import soundfile as sf
import numpy as np
import sys

def list_devices():
    print("Available audio devices:\n")
    print(sd.query_devices())
    print("\n")

def play_tone(frequency=440, duration=3, sample_rate=44100):
    """Play a sine wave tone through the default audio device"""
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    tone = 0.5 * np.sin(2 * np.pi * frequency * t)
    print(f"Playing {frequency}Hz tone for {duration} seconds...")
    sd.play(tone, sample_rate)
    sd.wait()
    print("Tone playback finished.\n")

def play_wav(file_path):
    """Play a WAV file"""
    try:
        data, samplerate = sf.read(file_path)
        print(f"Playing WAV file: {file_path}")
        sd.play(data, samplerate)
        sd.wait()
        print("WAV playback finished.\n")
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
    except Exception as e:
        print(f"Error playing WAV: {e}")

if __name__ == "__main__":
    print("MAX98357 I2S Amplifier Test\n")
    
    # List devices so you can see your I2S device
    list_devices()
    
    # Optional: set the default output device to your I2S device
    # sd.default.device = 1  # replace 1 with the correct device index from the list above

    # Play a test tone
    play_tone(frequency=440, duration=3)

    # Play WAV file if provided as argument
    if len(sys.argv) > 1:
        wav_file = sys.argv[1]
        play_wav(wav_file)
    else:
        print("No WAV file provided. To play a file: python max98357_test.py yourfile.wav")
