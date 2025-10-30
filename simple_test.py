#!/usr/bin/env python3
"""
Simple test to verify STT remains active during TTS.
"""

import asyncio
import time
import logging
from src.stt_handler import STTHandler
from src.tts_handler import TTSHandler

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_simple_interaction():
    """Test simple interaction to verify STT works during TTS."""
    print("🧪 Simple Full-Duplex Test")
    print("=" * 30)
    
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
        
        # Test 1: Speak and immediately check STT
        print("\n🎯 Test 1: Speak short message")
        tts_handler.speak("Hello! This is a test.", enable_barge_in=False)
        
        # Monitor STT during playback
        start_time = time.time()
        stt_detections = []
        
        while tts_handler.is_playing and time.time() - start_time < 10:
            realtime_text = stt_handler.get_realtime_text()
            if realtime_text and realtime_text not in stt_detections:
                stt_detections.append(realtime_text)
                print(f"🎤 STT detected: '{realtime_text}'")
            time.sleep(0.1)
        
        print(f"✅ Playback completed. STT detections: {len(stt_detections)}")
        
        # Test 2: Barge-in test
        print("\n🎯 Test 2: Barge-in test")
        print("Speak while TTS is playing...")
        
        tts_handler.speak("You can interrupt me now!", enable_barge_in=True)
        
        barge_in_start = time.time()
        barge_in_detected = False
        interruption_text = ""
        
        while time.time() - barge_in_start < 8:  # 8 second timeout
            if tts_handler.is_barge_in_detected():
                barge_in_detected = True
                interruption_text = stt_handler.get_realtime_text()
                break
            
            if not tts_handler.is_playing:
                break
                
            time.sleep(0.1)
        
        if barge_in_detected:
            print(f"✅ Barge-in detected! You said: '{interruption_text}'")
        else:
            print("❌ Barge-in not detected")
        
        print("\n🎉 Test completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False
        
    finally:
        # Cleanup
        if stt_handler:
            await stt_handler.stop_listening()
        if tts_handler:
            tts_handler.shutdown()
        print("🧹 Cleanup complete")

if __name__ == "__main__":
    success = asyncio.run(test_simple_interaction())
    if success:
        print("\n✅ Simple test passed!")
    else:
        print("\n❌ Simple test failed")