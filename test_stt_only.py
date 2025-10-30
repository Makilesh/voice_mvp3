#!/usr/bin/env python3
"""
Test STT without TTS to verify microphone works.
"""

import asyncio
import time
import logging
from src.stt_handler import STTHandler

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_stt_only():
    """Test STT without any TTS playback."""
    print("🎤 Testing STT Only (No TTS)")
    print("=" * 30)
    
    stt_handler = None
    
    try:
        # Initialize STT
        print("🎤 Initializing STT...")
        stt_handler = STTHandler(mode="balanced")
        await stt_handler.start_listening()
        print("✅ STT listening continuously")
        
        print("\n🎯 Test: Please speak something now...")
        print("You have 10 seconds to speak...")
        
        # Monitor STT for 10 seconds
        start_time = time.time()
        stt_readings = []
        
        while time.time() - start_time < 10:
            realtime_text = stt_handler.get_realtime_text()
            
            if realtime_text and realtime_text.strip():
                reading = realtime_text.strip()
                if reading not in stt_readings:
                    stt_readings.append(reading)
                    print(f"🎤 Detected: '{reading}'")
            
            time.sleep(0.1)
        
        if len(stt_readings) > 0:
            print(f"\n✅ STT detected {len(stt_readings)} unique readings:")
            for i, reading in enumerate(stt_readings, 1):
                print(f"  {i}. '{reading}'")
            return True
        else:
            print("\n❌ No speech detected in 10 seconds")
            print("Possible issues:")
            print("1. Microphone permissions")
            print("2. Microphone hardware")
            print("3. Audio driver issues")
            return False
        
    except Exception as e:
        logger.error(f"❌ STT test failed: {e}")
        return False
        
    finally:
        if stt_handler:
            await stt_handler.stop_listening()
        print("🧹 Cleanup complete")

if __name__ == "__main__":
    success = asyncio.run(test_stt_only())
    if success:
        print("\n✅ STT is working correctly!")
    else:
        print("\n❌ STT has issues that need to be resolved")