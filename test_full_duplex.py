#!/usr/bin/env python3
"""
Test script to verify full-duplex functionality.
Tests that STT remains active during TTS playback.
"""

import asyncio
import time
import logging
from src.stt_handler import STTHandler
from src.tts_handler import TTSHandler

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_continuous_stt_during_tts():
    """Test that STT remains active during TTS playback."""
    print("🧪 Testing Full-Duplex Functionality")
    print("=" * 50)
    
    stt_handler = None
    tts_handler = None
    
    try:
        # Initialize STT
        print("🎤 Initializing STT...")
        stt_handler = STTHandler(mode="balanced")
        await stt_handler.start_listening()
        print("✅ STT initialized and listening continuously")
        
        # Initialize TTS
        print("🗣️ Initializing TTS...")
        tts_handler = TTSHandler(stt_handler=stt_handler)
        print("✅ TTS initialized")
        
        # Test 1: Initial TTS playback (should not block STT)
        print("\n🎯 Test 1: Initial TTS playback")
        print("Speaking: 'Hello! This is a test message.'")
        
        start_time = time.time()
        tts_handler.speak("Hello! This is a test message.", enable_barge_in=False)
        
        # Monitor STT during TTS playback
        print("Monitoring STT during playback...")
        monitoring_start = time.time()
        stt_text_during_playback = ""
        
        while tts_handler.is_playing:
            # Get real-time text from STT
            current_text = stt_handler.get_realtime_text()
            if current_text and current_text != stt_text_during_playback:
                stt_text_during_playback = current_text
                print(f"🎤 STT detected during playback: '{current_text}'")
            
            time.sleep(0.1)  # Check every 100ms
        
        playback_time = time.time() - start_time
        print(f"✅ Playback completed in {playback_time:.2f}s")
        
        if stt_text_during_playback:
            print(f"⚠️ STT detected text during playback: '{stt_text_during_playback}'")
            print("❌ ISSUE: STT should not detect speech during TTS playback!")
            return False
        else:
            print("✅ Good: No speech detected during TTS playback")
        
        # Test 2: Barge-in functionality
        print("\n🎯 Test 2: Barge-in functionality")
        print("Speak something while TTS is playing to test barge-in...")
        
        tts_handler.speak("You can interrupt me anytime. Try speaking now!", enable_barge_in=True)
        
        barge_in_detected = False
        start_time = time.time()
        
        # Wait for barge-in or timeout
        while time.time() - start_time < 10:  # 10 second timeout
            if tts_handler.is_barge_in_detected():
                barge_in_detected = True
                break
            
            # Check if still playing
            if not tts_handler.is_playing:
                break
                
            time.sleep(0.1)
        
        if barge_in_detected:
            print("✅ Barge-in detected successfully!")
            interrupted_text = stt_handler.get_realtime_text()
            print(f"🎤 Interrupted with: '{interrupted_text}'")
        else:
            print("❌ Barge-in not detected within timeout")
            return False
        
        # Test 3: Multiple rapid interactions
        print("\n🎯 Test 3: Multiple rapid interactions")
        
        for i in range(3):
            print(f"Round {i+1}: Speaking TTS...")
            tts_handler.speak(f"Test message {i+1}. You can interrupt.", enable_barge_in=True)
            
            # Wait a bit then interrupt
            await asyncio.sleep(1)
            
            if tts_handler.is_playing:
                print("🎤 Simulating interruption...")
                # This would normally come from actual speech
                with tts_handler.state_lock:
                    tts_handler.barge_in_detected = True
                    tts_handler.stop_event.set()
                
                if tts_handler.stream:
                    tts_handler.stream.stop()
                
                print("✅ Interruption simulated")
            
            await asyncio.sleep(0.5)
        
        print("\n🎉 All tests passed!")
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
    success = asyncio.run(test_continuous_stt_during_tts())
    if success:
        print("\n✅ Full-duplex functionality verified!")
    else:
        print("\n❌ Issues detected in full-duplex functionality")