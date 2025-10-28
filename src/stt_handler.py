#stt_handler.py
from datetime import datetime
import logging
import asyncio
import warnings
import concurrent.futures
import re
from RealtimeSTT import AudioToTextRecorder

warnings.filterwarnings("ignore", category=DeprecationWarning, message="pkg_resources is deprecated")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class STTHandler:
    """Handles speech-to-text with smart corrections."""
    
    # CHANGE 1: Moved corrections to class variables for easy editing
    BRAND_CORRECTIONS = {
        r'\b(Shambla Tech|Shambla|Shamlataq|Shamlaq|Shamlata|Samba)\b': 'Shamla Tech',
    }
    
    TECH_CORRECTIONS = {
        r'\b(eye services|I services)\b': 'AI services',
        r'\b(A P I|ay pee eye)\b': 'API',
    }
    
    CASUAL_CORRECTIONS = {
        r'\bwanna\b': 'want to',
        r'\bgonna\b': 'going to',
        r'\bgotta\b': 'got to',
        r'\blemme\b': 'let me',
        r'\bkinda\b': 'kind of',
        r'\bsorta\b': 'sort of',
    }
    
    def __init__(self):
        self.recorder = None
        self.is_listening = False
        logger.info("🎤 STT Handler initialized.")
    
    def _apply_corrections(self, text: str) -> str:
        """Apply all corrections with word boundaries and case-insensitive matching."""
        # CHANGE 2: Single method handles all corrections
        original = text
        
        # Apply brand corrections
        for pattern, replacement in self.BRAND_CORRECTIONS.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # Apply tech corrections
        for pattern, replacement in self.TECH_CORRECTIONS.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # CHANGE 3: Only apply casual corrections if 2+ casual words detected
        casual_count = sum(1 for p in self.CASUAL_CORRECTIONS.keys() 
                          if re.search(p, text, re.IGNORECASE))
        if casual_count >= 2:
            for pattern, replacement in self.CASUAL_CORRECTIONS.items():
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # CHANGE 4: Log corrections for debugging
        if original != text:
            logger.info(f"🔧 Corrected: '{original}' → '{text}'")
        
        return text
    
    async def start_listening(self):
        """Start continuous audio recording with voice activation."""
        try:
            def init_recorder():
                return AudioToTextRecorder(
                    model="base",
                    language="en",
                    compute_type="int8",
                    enable_realtime_transcription=True,
                    realtime_model_type="base",
                    realtime_processing_pause=0.3,
                    init_realtime_after_seconds=0.1,
                    post_speech_silence_duration=0.8,
                    min_length_of_recording=0.5,
                    min_gap_between_recordings=0.1,
                    use_microphone=True
                )
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(init_recorder)
                self.recorder = await asyncio.wait_for(
                    asyncio.wrap_future(future), timeout=30.0
                )
                self.is_listening = True
                logger.info("🎤 Started continuous listening.")
        except asyncio.TimeoutError:
            logger.error("❌ STT initialization timed out")
            raise TimeoutError("STT initialization timed out")
        except Exception as e:
            logger.error(f"❌ Error starting listening: {e}")
            raise
    
    async def get_transcription(self) -> str:
        """Get transcription with automatic corrections."""
        try:
            if not self.recorder:
                raise ValueError("Recorder not initialized")
            
            text = self.recorder.text()
            
            if text:
                # CHANGE 5: Apply corrections
                text = self._apply_corrections(text).strip()
                logger.info(f"📝 Transcription: {text}")
                return text
            else:
                logger.warning("⚠️ No transcription received")
                return ""
                
        except Exception as e:
            logger.error(f"❌ Error getting transcription: {e}")
            return ""
    
    async def stop_listening(self):
        """Stop continuous audio recording."""
        try:
            if self.recorder:
                self.recorder = None
            self.is_listening = False
            logger.info("🎤 Stopped listening.")
        except Exception as e:
            logger.error(f"❌ Error stopping listening: {e}")

async def main():
    """Test STT functionality."""
    stt_handler = STTHandler()
    await stt_handler.start_listening()
    
    print("Speak now... (Press Enter when done)")
    input()
    
    text = await stt_handler.get_transcription()
    print(f"Transcribed text: {text}")
    
    await stt_handler.stop_listening()

if __name__ == "__main__":
    asyncio.run(main())