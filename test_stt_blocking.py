#!/usr/bin/env python3
"""
Test STT using blocking method to see if basic transcription works.
"""

import asyncio
import time
import logging
from src.stt_handler import STTHandler

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_stt_blocking():
    """Test STT using blocking transcription."""
    print("🎤 Testing STT Blocking Method")
    print("=" * 35)
    
    stt_handler = None
    
    try:
        # Initialize STT
        print("🎤 Initializing STT...")
        stt_handler = STTHandler(mode="balanced")
        await stt_handler.start_listening()
        print("✅ STT listening continuously")
        
        print("\n🎯 Test: Please speak something now...")
        print("You have 15 seconds to speak...")
        
        # Try blocking transcription
        start_time = time.time()
        print("🔄 Waiting for speech (blocking)...")
        
        try:
            # This should block until speech is detected
            user_text = await stt_handler.get_transcription()
            
            if user_text:
                print(f"✅ Transcription successful: '{user_text}'")
                return True
            else:
                print("❌ No transcription result")
                return False
                
        except Exception as e:
            print(f"❌ Transcription error: {e}")
            return False
        
    except Exception as e:
        logger.error(f"❌ STT test failed: {e}")
        return False
        
    finally:
        if stt_handler:
            await stt_handler.stop_listening()
        print("🧹 Cleanup complete")

if __name__ == "__main__":
    success = asyncio.run(test_stt_blocking())
    if success:
        print("\n✅ Blocking STT works!")
    else:
        print("\n❌ Blocking STT also has issues")