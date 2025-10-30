# tts_handler.py - FULL-DUPLEX FIXED VERSION
import os
import logging
import time
import threading
import warnings
from RealtimeTTS import SystemEngine, TextToAudioStream

import os
import logging
import time
import threading
from RealtimeTTS import SystemEngine, TextToAudioStream

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

class TTSHandler:
    """TTS with <150ms barge-in using continuous STT monitoring."""
    
    def __init__(self, stt_handler=None):
        try:
            self.engine = SystemEngine()
            self.stream = TextToAudioStream(self.engine)
            
            # CRITICAL: Reference to main STT (must be continuously listening)
            self.main_stt = stt_handler
            if not self.main_stt:
                raise ValueError("STT handler required for barge-in detection")
            
            # State management
            self.is_playing = False
            self.is_barge_in_enabled = True
            self.barge_in_detected = False
            self.stop_event = threading.Event()
            self.state_lock = threading.Lock()
            
            # Real-time monitoring state
            self.last_seen_realtime_text = ""
            self.barge_in_sensitivity = 2  # Minimum chars to trigger (very sensitive)
            
            logger.info("🎤 TTS Handler initialized with AGGRESSIVE barge-in (<150ms)")
        except Exception as e:
            logger.error(f"❌ Error initializing TTS: {e}")
            raise
    
    # def _monitor_barge_in(self):
    #     """
    #     CRITICAL: Aggressively monitor STT real-time transcription during playback.
    #     Triggers stop within 20-50ms of speech detection.
    #     """
    #     try:
    #         if not self.is_barge_in_enabled or not self.main_stt:
    #             return
            
    #         playback_start = time.time()
    #         tts_startup_buffer = 0.15  # Ignore first 150ms (TTS ramp-up)
    #         check_interval = 0.02  # Check every 20ms (aggressive polling)
            
    #         logger.info("👂 Barge-in monitor: ACTIVE")
            
    #         # Reset tracking
    #         self.last_seen_realtime_text = ""
    #         consecutive_detections = 0
    #         min_consecutive = 2  # Need 2 consecutive detections (40ms) to confirm
            
    #         while not self.stop_event.is_set():
    #             with self.state_lock:
    #                 if not self.is_playing:
    #                     break
                
    #             current_time = time.time()
                
    #             # Skip TTS startup buffer
    #             if current_time - playback_start < tts_startup_buffer:
    #                 time.sleep(check_interval)
    #                 continue
                
                # try:
                #     # CRITICAL: Get real-time text from continuously listening STT
                #     current_realtime = self.main_stt.get_realtime_text()
                    
                #     if not current_realtime:
                #         consecutive_detections = 0
                #         time.sleep(check_interval)
                #         continue
                    
                #     # Detect NEW speech (text changed or grew)
                #     if current_realtime != self.last_seen_realtime_text:
                #         new_text = current_realtime[len(self.last_seen_realtime_text):].strip()
                        
                #         # CRITICAL: Very sensitive detection
                #         if len(new_text) >= self.barge_in_sensitivity:
                #             consecutive_detections += 1
                            
                #             logger.debug(f"🎤 Speech fragment detected: '{new_text}' "
                #                        f"(confirmations: {consecutive_detections}/{min_consecutive})")
                            
                #             # Confirm barge-in after multiple detections
                #             if consecutive_detections >= min_consecutive:
                #                 elapsed_ms = (time.time() - playback_start) * 1000
                #                 logger.info(f"🎤 BARGE-IN CONFIRMED at {elapsed_ms:.0f}ms: '{current_realtime}'")
                                
                #                 # STOP IMMEDIATELY
                #                 with self.state_lock:
                #                     self.barge_in_detected = True
                #                     self.stop_event.set()
                                
                #                 if self.stream:
                #                     try:
                #                         self.stream.stop()
                #                         logger.info("🛑 TTS stopped in <150ms")
                #                     except Exception as e:
                #                         logger.error(f"Stop failed: {e}")
                                
                #                 break
                #         else:
                #             consecutive_detections = 0
                        
                #         self.last_seen_realtime_text = current_realtime
                    
                # except Exception as e:
                #     logger.debug(f"Monitor check error: {e}")
                
                # ...existing code...
    def _monitor_barge_in(self):
        """
        CRITICAL: Aggressively monitor STT real-time transcription during playback.
        Triggers stop within 20-50ms of speech detection.
        """
        try:
            if not self.is_barge_in_enabled or not self.main_stt:
                return
            
            playback_start = time.time()
            tts_startup_buffer = 0.15  # Ignore first 150ms (TTS ramp-up)
            check_interval = 0.02  # Check every 20ms (aggressive polling)
            
            logger.info("👂 Barge-in monitor: ACTIVE")
            
            # Reset tracking
            self.last_seen_realtime_text = ""
            consecutive_detections = 0
            min_consecutive = 2  # Need 2 consecutive detections (40ms) to confirm
            
            while not self.stop_event.is_set():
                with self.state_lock:
                    if not self.is_playing:
                        break
                
                current_time = time.time()
                
                # Skip TTS startup buffer
                if current_time - playback_start < tts_startup_buffer:
                    time.sleep(check_interval)
                    continue
                
                try:
                    # Get real-time transcription
                    realtime_text = self.main_stt.get_realtime_text()
                    
                    # Detect new speech (not just continuation)
                    if realtime_text and len(realtime_text) > self.barge_in_sensitivity:
                        if realtime_text != self.last_seen_realtime_text:
                            consecutive_detections += 1
                            
                            # Confirm with consecutive detections
                            if consecutive_detections >= min_consecutive:
                                logger.info(f"🛑 Barge-in detected: {realtime_text[:30]}...")
                                with self.state_lock:
                                    self.barge_in_detected = True
                                self.stop_event.set()
                                break
                        else:
                            consecutive_detections = max(0, consecutive_detections - 1)
                    
                    self.last_seen_realtime_text = realtime_text
                except Exception as e:
                    logger.warning(f"⚠️ Monitor check error: {e}")
                
                time.sleep(check_interval)
            
            logger.info("👂 Barge-in monitor: STOPPED")
            
        except Exception as e:
            logger.error(f"❌ Barge-in monitor crashed: {e}")
    
    def _play_with_monitoring(self, text: str):
        """Play audio while monitoring for barge-in."""
        
        def play_audio():
            try:
                with self.state_lock:
                    self.is_playing = True
                    # self.barge_in_detected = False
                self.stop_event.clear()
                
                # CRITICAL: Start monitor BEFORE audio starts
                monitor_thread = threading.Thread(target=self._monitor_barge_in, daemon=True)
                monitor_thread.start()
                
                # Brief delay to ensure monitor is active
                time.sleep(0.02)
                
                # Play audio (non-blocking thread)
                if self.stream:
                    self.stream.feed(text)
                    self.stream.play_async()
                    # try:
                    #     self.stream.play()
                    # except Exception as e:
                    #         if not self.stop_event.is_set():
                    #                 logger.error(f"❌ Playback error: {e}")
                        
            except Exception as e:
                logger.error(f"❌ Playback thread error: {e}")
            finally:
                with self.state_lock:
                    self.is_playing = False
                self.stop_event.clear()
        
        # Start playback in daemon thread
        self.playback_thread = threading.Thread(target=play_audio, daemon=True)
        self.playback_thread.start()
    
    def speak(self, text: str, voice: str = "default", emotive_tags: str = "", 
              enable_barge_in: bool = True) -> str:
        """Speak with instant barge-in detection."""
        try:
            if not self.engine or not self.stream:
                raise ValueError("TTS not initialized")
            
            self.is_barge_in_enabled = enable_barge_in
            logger.info(f"🗣 Speaking: {text[:50]}... (barge-in: {enable_barge_in})")
            
            if emotive_tags:
                text = f"{text} {emotive_tags}"
            
            if voice != "default":
                try:
                    self.engine.set_voice(voice)
                except Exception as e:
                    logger.warning(f"Voice '{voice}' unavailable: {e}")
            
            # CRITICAL: Clear STT real-time buffer before speaking
            if self.main_stt:
                self.main_stt.clear_realtime_text()
            
            self._play_with_monitoring(text)
            
            return "audio_playing"
            
        except Exception as e:
            logger.error(f"❌ TTS error: {e}")
            return ""
    
    def wait_for_completion(self, timeout: float = 30.0) -> bool:
        """Wait for playback to complete or be interrupted."""
        try:
            start_time = time.time()
            
            while True:
                with self.state_lock:
                    # if not self.is_playing:
                    #     was_interrupted = self.barge_in_detected
                    #     if was_interrupted:
                    #         logger.info("✅ Playback interrupted by user")
                    #     return not was_interrupted
                    
                    # if self.barge_in_detected:
                    #     return False
                    
                    if not self.is_playing:
                        return True
                    if self.barge_in_detected:
                        return False
                
                if time.time() - start_time > timeout:
                    logger.warning("⏰ Playback timeout")
                    return False
                
                time.sleep(0.01)  # 10ms polling
                
        except Exception as e:
            logger.error(f"❌ Wait error: {e}")
            return False
    
    def is_barge_in_detected(self) -> bool:
        """Check if user interrupted playback."""
        with self.state_lock:
            return self.barge_in_detected
    
    def shutdown(self):
        """Clean shutdown."""
        try:
            logger.info("🧹 Shutting down TTS...")
            
            with self.state_lock:
                self.is_playing = False
            self.stop_event.set()
            
            if hasattr(self, 'stream') and self.stream:
                try:
                    self.stream.stop()
                except Exception:
                    pass
                self.stream = None
            
            if hasattr(self, 'engine'):
                self.engine = None
            
            logger.info("✅ TTS shutdown complete")
        except Exception as e:
            logger.error(f"❌ Shutdown error: {e}")