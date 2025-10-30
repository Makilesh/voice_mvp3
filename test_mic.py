#!/usr/bin/env python3
"""
Simple microphone test to verify audio input works.
"""

import sounddevice as sd
import numpy as np
import time

print("🎤 Testing Microphone")
print("=" * 20)

# Get default input device
default_input = sd.default.device[0]
print(f"Default input device: {default_input}")

# Query the device
device_info = sd.query_devices(default_input)
print(f"Device info: {device_info}")

# Test recording for 3 seconds
print("\n🎯 Testing microphone recording...")
print("Speak for 3 seconds...")

try:
    # Record for 3 seconds
    recording = sd.rec(int(3 * 44100), samplerate=44100, channels=1, dtype='float32')
    sd.wait()  # Wait until recording is finished
    
    # Check if we got any audio
    if np.max(np.abs(recording)) > 0.01:  # If there's significant audio
        print("✅ Microphone is working!")
        print(f"Audio level: {np.max(np.abs(recording)):.4f}")
    else:
        print("❌ No audio detected")
        print("Possible issues:")
        print("1. Microphone muted")
        print("2. Wrong audio device")
        print("3. Microphone permissions")
        
except Exception as e:
    print(f"❌ Error recording: {e}")

print("\n🎤 Test completed!")