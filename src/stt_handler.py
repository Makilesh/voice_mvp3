# stt_handler.py old
from datetime import datetime
import logging
import asyncio
import warnings
import concurrent.futures
import re
import threading
import time
from RealtimeSTT import AudioToTextRecorder

from datetime import datetime
import logging
import asyncio
import concurrent.futures
import re
import threading
import time
from RealtimeSTT import AudioToTextRecorder

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

logger = logging.getLogger(__name__)

class STTHandler:
    """Full-duplex STT with continuous real-time transcription."""
    
    CORRECTIONS = {
        r'\b(Shambla Tech|Shambla|Shamlataq|Shamlaq|Shamlata|Samba|Sharma Tech)\b': 'Shamla Tech',
        r'\b(eye services?|I services?|A I services?)\b': 'AI services',
        r'\b(A P I|ay pee eye|a p eye)\b': 'API',
        r'\b(block ?chain)\b': 'blockchain',
        r'\b(crypto ?currency|cripto)\b': 'cryptocurrency',
        r'\bwanna\b': 'want to',
        r'\bgonna\b': 'going to',
        r'\bgotta\b': 'got to',
        r'\blemme\b': 'let me',
    }
    
    def __init__(self, mode: str = "balanced"):
        self.recorder = None
        self.is_listening = False
        self.mode = mode
        self.transcription_count = 0
        self.avg_latency = 0.0
        
        self.model_name = self._select_model(mode)
        
        # CRITICAL: Real-time transcription state (thread-safe)
        self.realtime_text = ""
        self.realtime_lock = threading.Lock()
        
        # CRITICAL: Completed transcription queue (non-blocking)
        self.completed_transcriptions = asyncio.Queue()
        self.last_completed_text = ""
        
        # CRITICAL: Polling state for barge-in detection
        self.polling_text = ""
        self.polling_lock = threading.Lock()
        self.polling_active = False
        self.polling_thread = None
        
        logger.info(f"🎤 STT Handler initialized (FULL-DUPLEX mode: {mode}, model: {self.model_name})")
    
    def _select_model(self, mode: str) -> str:
        models = {
            "fast": "tiny",
            "balanced": "small",
            "accurate": "base"
        }
        return models.get(mode, "small")
    
    def _apply_corrections(self, text: str) -> str:
        if not text:
            return text
        
        original = text
        for pattern, replacement in self.CORRECTIONS.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        if original != text:
            logger.debug(f"🔧 Corrected: '{original}' → '{text}'")
        
        return text.strip()
    
    def _on_realtime_update(self, text: str):
        """CRITICAL: Called continuously during speech (non-blocking)."""
        with self.realtime_lock:
            self.realtime_text = text
        # Debug logging
        if text and text.strip():
            logger.debug(f"🎤 Real-time update: '{text.strip()}'")
    
    def _on_transcription_complete(self, text: str):
        """CRITICAL: Called when speech segment completes (non-blocking)."""
        corrected = self._apply_corrections(text)
        if corrected:
            # Store last completed text (synchronous)
            self.last_completed_text = corrected
            logger.info(f"✅ Completed: {corrected}")
    
    async def start_listening(self):
        """Start CONTINUOUS listening with callbacks."""
        try:
            def init_recorder():
                handler_self = self
                
                def on_realtime_update(text: str):
                    handler_self._on_realtime_update(text)
                
                def on_transcription_complete(text: str):
                    handler_self._on_transcription_complete(text)
                
                logger.info("🎤 Initializing AudioToTextRecorder...")
                
                return AudioToTextRecorder(
                    model=self.model_name,
                    language="en",
                    compute_type="int8",
                    
                    # CRITICAL: Enable real-time callbacks
                    enable_realtime_transcription=True,
                    on_realtime_transcription_update=on_realtime_update,
                    realtime_model_type=self.model_name,
                    
                    # OPTIMIZED timing for real-time detection
                    realtime_processing_pause=0.05,  # Faster processing
                    post_speech_silence_duration=0.15,  # Shorter silence
                    min_length_of_recording=0.2,  # Shorter minimum recording
                    min_gap_between_recordings=0.05,  # Shorter gap
                    pre_recording_buffer_duration=0.1,  # Shorter buffer
                    
                    # VAD settings - more sensitive
                    silero_sensitivity=0.3,  # More sensitive
                    silero_use_onnx=True,
                    webrtc_sensitivity=1,  # More sensitive
                    
                    beam_size=1,  # Faster but less accurate
                    initial_prompt="Shamla Tech, AI, blockchain, cryptocurrency, API",
                    use_microphone=True,
                    
                    # Device settings
                    device=None  # Use default device
                )
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(init_recorder)
                self.recorder = await asyncio.wait_for(
                    asyncio.wrap_future(future), 
                    timeout=30.0
                )
                self.is_listening = True
                logger.info(f"✅ STT listening continuously (model: {self.model_name})")
                
        except asyncio.TimeoutError:
            logger.error("❌ STT initialization timeout")
            raise TimeoutError("STT initialization timed out")
        except Exception as e:
            logger.error(f"❌ STT start error: {e}")
            raise
    
    def get_realtime_text(self) -> str:
        """Get current real-time transcription (INSTANT, non-blocking)."""
        with self.realtime_lock:
            return self.realtime_text
    
    def get_realtime_text_hybrid(self) -> str:
        """Hybrid approach: Check real-time buffer, if empty do quick check."""
        # First check the real-time buffer
        with self.realtime_lock:
            if self.realtime_text and len(self.realtime_text.strip()) > 0:
                return self.realtime_text
        
        # If empty, try a quick non-blocking check
        try:
            # Save current state
            old_last_text = self.last_completed_text
            
            # Try to get a quick transcription with very short timeout
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a task with timeout
                try:
                    # Use a small timeout to check if there's any speech
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(self._quick_speech_check)
                        result = future.result(timeout=0.1)  # 100ms timeout
                        if result:
                            return result
                except:
                    pass
            
            return ""
            
        except Exception as e:
            logger.debug(f"Hybrid check error: {e}")
            return ""
    
    def _quick_speech_check(self) -> str:
        """Quick speech check without blocking."""
        try:
            # Check if we have any recent audio activity
            if hasattr(self, 'recorder') and self.recorder:
                # This is a simplified check - in practice, you might need to
                # check the recorder's internal state
                return self.get_realtime_text()
            return ""
        except:
            return ""
    
    def clear_realtime_text(self):
        """Clear real-time buffer."""
        with self.realtime_lock:
            self.realtime_text = ""
    
    async def get_transcription(self) -> str:
        """
        BLOCKING call to get next completed transcription.
        WARNING: Only use when NOT playing TTS. For full-duplex, use get_realtime_text().
        """
        try:
            if not self.recorder:
                raise ValueError("Recorder not initialized")
            
            start_time = asyncio.get_event_loop().time()
            
            # Clear previous state
            self.last_completed_text = ""
            self.clear_realtime_text()
            
            # CRITICAL: Run blocking .text() in thread pool
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(None, self.recorder.text)
            
            latency = (asyncio.get_event_loop().time() - start_time) * 1000
            
            if text:
                text = self._apply_corrections(text)
                self.transcription_count += 1
                self.avg_latency = (self.avg_latency * (self.transcription_count - 1) + latency) / self.transcription_count
                logger.info(f"📝 [{latency:.0f}ms] {text}")
                return text
            else:
                return ""
                
        except Exception as e:
            logger.error(f"❌ Transcription error: {e}")
            return ""
    
    async def stop_listening(self):
        """Stop listening and cleanup."""
        try:
            # Stop polling if active
            with self.polling_lock:
                self.polling_active = False
            
            if self.polling_thread and self.polling_thread.is_alive():
                self.polling_thread.join(timeout=1.0)
            
            if self.recorder:
                self.recorder = None
            self.is_listening = False
            
            if self.transcription_count > 0:
                logger.info(f"📊 Session stats: {self.transcription_count} transcriptions, "
                          f"avg latency: {self.avg_latency:.0f}ms")
            
            logger.info("🎤 STT stopped")
        except Exception as e:
            logger.error(f"❌ Stop error: {e}")
    
    def start_polling_for_barge_in(self):
        """Start background polling for barge-in detection."""
        with self.polling_lock:
            if self.polling_active:
                return
            
            self.polling_active = True
            self.polling_thread = threading.Thread(target=self._polling_worker, daemon=True)
            self.polling_thread.start()
            logger.info("🎤 Background polling thread started")
    
    def stop_polling_for_barge_in(self):
        """Stop background polling."""
        with self.polling_lock:
            self.polling_active = False
        logger.info("🎤 Background polling thread stopped")
    
    def get_barge_in_text(self) -> str:
        """Get the latest text from polling (for barge-in detection)."""
        with self.polling_lock:
            return self.polling_text
    
    def _polling_worker(self):
        """Background worker for polling STT."""
        try:
            logger.info("🎤 Polling worker started")
            while self.polling_active:
                try:
                    # Use a simpler approach - check if recorder has any activity
                    if hasattr(self, 'recorder') and self.recorder:
                        # Try to get text with reasonable timeout
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # Create a task with reasonable timeout
                                future = asyncio.run_coroutine_threadsafe(
                                    asyncio.wait_for(
                                        self.get_transcription(),
                                        timeout=2.0  # Give it time to detect speech
                                    ),
                                    loop
                                )
                                try:
                                    result = future.result(timeout=3.0)
                                    if result and len(result.strip()) > 0:
                                        with self.polling_lock:
                                            self.polling_text = result.strip()
                                        logger.info(f"🎤 POLLING DETECTED: '{result.strip()}'")
                                    else:
                                        with self.polling_lock:
                                            self.polling_text = ""
                                except asyncio.TimeoutError:
                                    # No speech detected in this cycle
                                    with self.polling_lock:
                                        self.polling_text = ""
                                except Exception as e:
                                    logger.debug(f"Polling future error: {e}")
                                    with self.polling_lock:
                                        self.polling_text = ""
                        except Exception as e:
                            logger.debug(f"Polling error: {e}")
                            with self.polling_lock:
                                self.polling_text = ""
                except Exception as e:
                    logger.error(f"Polling worker error: {e}")
                
                # Small delay between polls
                time.sleep(0.1)
        except Exception as e:
            logger.error(f"Polling worker crashed: {e}")
        finally:
            logger.info("🎤 Polling worker finished")
    
    def get_performance_stats(self) -> dict:
        return {
            "model": self.model_name,
            "transcription_count": self.transcription_count,
            "avg_latency_ms": round(self.avg_latency, 1),
            "is_listening": self.is_listening
        }