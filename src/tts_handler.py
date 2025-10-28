# tts_handler.py
import os
import logging
import asyncio
import time
import threading
import warnings
from RealtimeTTS import SystemEngine, TextToAudioStream

warnings.filterwarnings("ignore", category=DeprecationWarning, message="pkg_resources is deprecated")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TTSHandler:
    """Handles text-to-speech functionality with barge-in capability."""
    
    # FIX 1: Remove duplicate STT, accept it from outside
    def __init__(self, stt_handler=None):
        """Initialize the TTS handler with SystemEngine and optional shared STT."""
        try:
            self.engine = SystemEngine()
            self.stream = TextToAudioStream(self.engine)
            
            # FIX 2: Use shared STT instance instead of creating new one
            self.stt_handler = stt_handler  # Shared with main STT handler
            
            self.is_playing = False
            self.is_barge_in_enabled = True
            self.barge_in_detected = False
            self.playback_thread = None
            self.stop_event = threading.Event()
            
            logger.info("🎤 TTS Handler initialized with shared STT for barge-in.")
        except Exception as e:
            logger.error(f"❌ Error initializing TTS: {e}")
            raise
    
    def _playback_with_barge_in(self, text: str, initial_text_length: int):
        """Play audio while monitoring for speech with REDUCED sensitivity during playback."""
        def monitor_speech():
            """Monitor for user speech with acoustic echo cancellation logic."""
            try:
                if self.is_barge_in_enabled and self.stt_handler:
                    last_check_time = time.time()
                    playback_start = time.time()
                    
                    while not self.stop_event.is_set() and self.is_playing:
                        current_time = time.time()
                        
                        # FIX 3: Slower polling (200ms) to reduce TTS audio pickup
                        if current_time - last_check_time >= 0.2:
                            try:
                                # FIX 4: Only check after initial TTS buffer (avoid echo)
                                # Wait at least 0.5s after playback starts
                                if current_time - playback_start < 0.5:
                                    last_check_time = current_time
                                    continue
                                
                                detected_text = self.stt_handler.recorder.text() if self.stt_handler.recorder else ""
                                
                                # FIX 5: Filter out very short utterances (likely TTS echo)
                                # Only trigger on substantial input (5+ chars)
                                if detected_text and len(detected_text.strip()) >= 5:
                                    logger.info(f"🎤 Barge-in detected: {detected_text}")
                                    self.barge_in_detected = True
                                    self.stop_event.set()
                                    
                                    if self.stream:
                                        try:
                                            self.stream.stop()
                                            logger.info("🛑 Audio stopped due to barge-in")
                                        except Exception:
                                            self.stream = None
                                    break
                            except Exception:
                                pass
                            
                            last_check_time = current_time
                        
                        # FIX 6: Longer sleep to reduce CPU and audio conflicts
                        time.sleep(0.05)
                        
            except Exception as e:
                logger.error(f"❌ Error monitoring speech: {e}")
        
        def play_audio():
            """Play the audio stream."""
            try:
                self.is_playing = True
                self.barge_in_detected = False
                self.stop_event.clear()
                
                monitor_thread = threading.Thread(target=monitor_speech, daemon=True)
                monitor_thread.start()
                
                if self.stream:
                    self.stream.feed(text)
                    try:
                        self.stream.play()
                    except Exception as e:
                        if self.stop_event.is_set():
                            logger.info("🛑 Playback cancelled due to barge-in")
                        else:
                            logger.error(f"❌ Error during playback: {e}")
                
            except Exception as e:
                logger.error(f"❌ Error during playback: {e}")
            finally:
                self.is_playing = False
                self.stop_event.clear()
        
        self.playback_thread = threading.Thread(target=play_audio, daemon=True)
        self.playback_thread.start()
    
    def speak(self, text: str, voice: str = "default", emotive_tags: str = "", enable_barge_in: bool = True) -> str:
        """Convert text to speech with barge-in capability."""
        try:
            if not self.engine or not self.stream:
                raise ValueError("TTS not initialized properly")
            
            self.is_barge_in_enabled = enable_barge_in
            logger.info(f"🗣 Speaking text: {text}")
            
            if emotive_tags:
                text = f"{text} {emotive_tags}"
            
            if voice != "default":
                try:
                    self.engine.set_voice(voice)
                except Exception as e:
                    logger.warning(f"Voice '{voice}' not available, using default: {e}")
            
            # FIX 7: Pass text length for better echo avoidance
            self._playback_with_barge_in(text, len(text))
            
            output_dir = os.path.join("src", "audio", "output")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"{int(time.time())}.wav")
            
            logger.info("✅ Audio playing through system speakers")
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Error during TTS: {e}")
            return ""
    
    def wait_for_completion(self, timeout: float = 30.0) -> bool:
        """Wait for TTS playback to complete or timeout."""
        try:
            if not self.is_playing:
                return True

            start_time = time.time()

            while self.is_playing and not self.barge_in_detected:
                if time.time() - start_time > timeout:
                    logger.warning("⏰ TTS playback timed out")
                    return False
                time.sleep(0.1)

            return not self.barge_in_detected

        except Exception as e:
            logger.error(f"❌ Error waiting for completion: {e}")
            return False
    
    def is_barge_in_detected(self) -> bool:
        """Check if barge-in was detected during playback."""
        return self.barge_in_detected
    
    def shutdown(self):
        """Shutdown the TTS handler and release resources."""
        try:
            if hasattr(self, 'stream'):
                self.stream = None
            if hasattr(self, 'engine'):
                self.engine = None
            logger.info("🎤 TTS Handler shutdown complete.")
        except Exception as e:
            logger.error(f"❌ Error during TTS shutdown: {e}")

async def main():
    """Example usage of TTSHandler"""
    # FIX 8: Import and create shared STT
    from stt_handler import STTHandler
    
    stt = STTHandler()
    await stt.start_listening()
    
    tts_handler = TTSHandler(stt_handler=stt)
    
    test_cases = [
        ("Hello, this is a test message.", "default", ""),
        ("This is a happy message!", "default", ""),
    ]
    
    for text, voice, tags in test_cases:
        print(f"Testing: {text}")
        tts_handler.speak(text, voice, tags)
        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())