#!/usr/bin/env python3
"""
Debug test to see what STT is detecting during TTS playback.
"""

import asyncio
import time
import logging
from src.stt_handler import STTHandler
from src.tts_handler import TTSHandler

# Configure logging to show debug messages
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def debug_stt_during_tts():
    """Debug STT behavior during TTS playback."""
    print("🔍 Debug Test: STT during TTS")
    print("=" * 40)
    
    stt_handler = None
    tts_handler = None
    
    try:
        # Initialize STT
        print("🎤 Initializing STT...")
        stt_handler = STTHandler(mode="balanced")
        await stt_handler.start_listening()
        print("✅ STT listening continuously")
        
        # Initialize TTS
        print("🗣️ Initializing TTS...")
        tts_handler = TTSHandler(stt_handler=stt_handler)
        print("✅ TTS initialized")
        
        # Test: Speak and monitor STT in detail
        print("\n🎯 Test: Speak and monitor STT")
        print("TTS: 'Hello! This is a test message.'")
        print("Please try to speak while TTS is playing...")
        
        tts_handler.speak("Hello! This is a test message.", enable_barge_in=True)
        
        # Detailed monitoring
        start_time = time.time()
        stt_readings = []
        
        while tts_handler.is_playing and time.time() - start_time < 10:
            # Get STT readings every 100ms
            realtime_text = stt_handler.get_realtime_text()
            current_time = time.time() - start_time
            
            if realtime_text and realtime_text.strip():
                reading = f"{current_time:.2f}s: '{realtime_text.strip()}'"
                if reading not in stt_readings:
                    stt_readings.append(reading)
                    logger.info(f"🎤 STT READING: {reading}")
            
            time.sleep(0.1)
        
        print(f"\n📊 STT Readings during playback:")
        for reading in stt_readings:
            print(f"  {reading}")
        
        print(f"\n📈 Total unique readings: {len(stt_readings)}")
        
        if len(stt_readings) == 0:
            print("❌ No speech detected during TTS")
            print("This could mean:")
            print("1. Microphone is not working")
            print("2. STT is not properly initialized")
            print("3. Audio input issues")
        else:
            print("✅ Speech detected during TTS")
        
        print("\n🎉 Debug test completed!")
        return len(stt_readings) > 0
        
    except Exception as e:
        logger.error(f"❌ Debug test failed: {e}")
        return False
        
    finally:
        # Cleanup
        if stt_handler:
            await stt_handler.stop_listening()
        if tts_handler:
            tts_handler.shutdown()
        print("🧹 Cleanup complete")

if __name__ == "__main__":
    success = asyncio.run(debug_stt_during_tts())
    if success:
        print("\n✅ Debug test found speech during TTS!")
    else:
        print("\n❌ Debug test found no speech during TTS")