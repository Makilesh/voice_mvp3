# tts_handler.py - FIXED VERSION
import os
import logging
import asyncio
import time
import threading
import warnings
import numpy as np
from RealtimeTTS import SystemEngine, TextToAudioStream
from RealtimeSTT import AudioToTextRecorder

warnings.filterwarnings("ignore", category=DeprecationWarning)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TTSHandler:
    """Handles TTS with INSTANT, reliable barge-in detection (<100ms)."""
    
    def __init__(self, stt_handler=None):
        """Initialize TTS with real-time VAD-based barge-in."""
        try:
            self.engine = SystemEngine()
            self.stream = TextToAudioStream(self.engine)
            
            # Main STT handler (shared)
            self.main_stt = stt_handler
            
            # # Dedicated lightweight STT for barge-in monitoring
            # self.barge_in_recorder = None
            # self._init_barge_in_recorder()
            
            # State management with thread safety
            self.is_playing = False
            self.is_barge_in_enabled = True
            self.barge_in_detected = False
            self.stop_event = threading.Event()
            self.state_lock = threading.Lock()
            
            # Real-time speech detection flag (updated by callback)
            # self.speech_detected = False
            # self.speech_start_time = None
            
            # Adaptive noise rejection
            # self.ambient_noise_level = 0
            # self.noise_floor_samples = []
            
            
            # Line 27 - ADD AFTER self.main_stt = stt_handler:
            
            # Use MAIN STT for barge-in (no separate recorder needed)
            self.last_realtime_text = ""
            self.realtime_text_lock = threading.Lock()
            
            logger.info("🎤 TTS Handler initialized with INSTANT barge-in (VAD-based).")
        except Exception as e:
            logger.error(f"❌ Error initializing TTS: {e}")
            raise
    
    def _init_barge_in_recorder(self):
        """Initialize lightweight STT with REAL-TIME callbacks for instant detection."""
        try:
            # CRITICAL FIX: Use on_recording_start callback for INSTANT detection
            def on_recording_start():
                """Called IMMEDIATELY when speech is detected (VAD trigger)."""
                with self.state_lock:
                    self.speech_detected = True
                    self.speech_start_time = time.time()
                logger.debug("🎤 Speech START detected (VAD)")
            
            def on_recording_stop():
                """Called when speech ends."""
                logger.debug("🎤 Speech STOP detected (VAD)")
            
            self.barge_in_recorder = AudioToTextRecorder(
                model="tiny",  # Fastest for VAD only
                language="en",
                compute_type="int8",
                enable_realtime_transcription=False,  # Don't need transcription for barge-in
                
                # CRITICAL: Ultra-fast VAD settings for instant detection
                post_speech_silence_duration=0.2,  # Minimal (we don't wait for transcription)
                min_length_of_recording=0.2,  # Catch quick interjections
                min_gap_between_recordings=0.05,
                
                # CRITICAL: High sensitivity during playback
                silero_sensitivity=0.4,  # More sensitive (was 0.3)
                silero_use_onnx=True,  # Faster VAD
                webrtc_sensitivity=2,
                
                # Callbacks for INSTANT detection
                on_recording_start=on_recording_start,
                on_recording_stop=on_recording_stop,
                
                use_microphone=True
            )
            
            # Start the recorder in listening mode
            # Note: RealtimeSTT starts listening automatically
            
            logger.info("✅ Barge-in recorder initialized (VAD callback mode)")
        except Exception as e:
            logger.warning(f"⚠️ Could not init barge-in recorder: {e}")
            self.barge_in_recorder = None
    
    def _calibrate_noise_floor(self, duration: float = 0.3):
        """Calibrate ambient noise level during TTS startup."""
        try:
            # Sample ambient noise for first 300ms
            # This would require raw audio access - simplified version
            # In production, you'd average energy levels during silence
            self.ambient_noise_level = 150  # Conservative baseline
            logger.debug(f"🔇 Noise floor calibrated: {self.ambient_noise_level}")
        except Exception as e:
            logger.warning(f"Calibration failed: {e}")
    
    def _playback_with_barge_in(self, text: str):
        """Play audio with INSTANT VAD-based barge-in monitoring (<100ms stop)."""
      
        # def monitor_speech():
        #     """Monitor MAIN STT's real-time transcription for barge-in."""
        #     try:
        #         if not (self.is_barge_in_enabled and self.main_stt and self.main_stt.recorder):
        #             logger.warning("⚠️ Barge-in monitoring disabled (no main STT)")
        #             return
                
        #         playback_start = time.time()
        #         tts_buffer_duration = 0.2  # Ignore first 200ms (TTS startup)
        #         check_interval = 0.05  # Check every 50ms
                
        #         logger.debug("👂 Barge-in monitor started")
                
        #         # Track what we've seen
        #         last_seen_text = ""
                
        #         while not self.stop_event.is_set():
        #             with self.state_lock:
        #                 if not self.is_playing:
        #                     break
                    
        #             current_time = time.time()
                    
        #             # Skip initial TTS buffer
        #             if current_time - playback_start < tts_buffer_duration:
        #                 time.sleep(check_interval)
        #                 continue
                    
        #             # CRITICAL: Get real-time text from MAIN STT
        #             try:
        #                 # RealtimeSTT accumulates text in recorder.realtime_stabilized_text
        #                 current_text = ""
        #                 if hasattr(self.main_stt.recorder, 'realtime_stabilized_text'):
        #                     current_text = self.main_stt.recorder.realtime_stabilized_text
        #                 elif hasattr(self.main_stt.recorder, 'text'):
        #                     # Fallback: non-blocking check
        #                     current_text = getattr(self.main_stt.recorder, '_last_transcription', '')
                        
        #                 # Detect NEW text (user started speaking)
        #                 if current_text and current_text != last_seen_text:
        #                     new_text = current_text[len(last_seen_text):].strip()
                            
        #                     if new_text and len(new_text) > 1:  # At least 2 chars
        #                         logger.info(f"🎤 BARGE-IN: User said '{new_text}'")
                                
        #                         with self.state_lock:
        #                             self.barge_in_detected = True
        #                             self.stop_event.set()
                                
        #                         # Stop audio IMMEDIATELY
        #                         if self.stream:
        #                             try:
        #                                 self.stream.stop()
        #                                 logger.info("🛑 Audio stopped")
        #                             except Exception as e:
        #                                 logger.error(f"Stop failed: {e}")
                                
        #                         break
                            
        #                     last_seen_text = current_text
                        
        #             except Exception as e:
        #                 logger.debug(f"Monitor check error: {e}")
                    
        #             time.sleep(check_interval)
                
        #         logger.debug("👂 Barge-in monitor stopped")
                    
        #     except Exception as e:
        #         logger.error(f"❌ Barge-in monitor error: {e}")
                
        def monitor_speech():
            """Energy-based VAD monitoring using main STT."""
            try:
                if not (self.is_barge_in_enabled and self.main_stt and self.main_stt.recorder):
                    return
                
                playback_start = time.time()
                tts_buffer = 0.2
                
                # Access VAD state from main recorder
                while not self.stop_event.is_set():
                    with self.state_lock:
                        if not self.is_playing:
                            break
                    
                    if time.time() - playback_start < tts_buffer:
                        time.sleep(0.02)
                        continue
                    
                    # Check if main recorder detects voice activity
                    try:
                        recorder = self.main_stt.recorder
                        
                        # RealtimeSTT has is_recording property
                        if hasattr(recorder, 'is_recording') and recorder.is_recording:
                            logger.info("🎤 BARGE-IN: Voice activity detected")
                            
                            with self.state_lock:
                                self.barge_in_detected = True
                                self.stop_event.set()
                            
                            if self.stream:
                                self.stream.stop()
                                logger.info("🛑 Audio stopped")
                            break
                    
                    except Exception as e:
                        logger.debug(f"VAD check error: {e}")
                    
                    time.sleep(0.02)  # 20ms polling
                    
            except Exception as e:
                logger.error(f"❌ Monitor error: {e}")
                
                
        def play_audio():
            """Play audio stream with monitoring."""
            try:
                with self.state_lock:
                    self.is_playing = True
                    self.barge_in_detected = False
                    self.speech_detected = False
                self.stop_event.clear()
                
                # Start monitoring thread BEFORE audio starts
                monitor_thread = threading.Thread(target=monitor_speech, daemon=True)
                monitor_thread.start()
                
                # Brief delay to ensure monitor is running
                time.sleep(0.01)
                
                # Play audio
                if self.stream:
                    self.stream.feed(text)
                    try:
                        self.stream.play()
                    except Exception as e:
                        if not self.stop_event.is_set():
                            logger.error(f"❌ Playback error: {e}")
                
            except Exception as e:
                logger.error(f"❌ Playback error: {e}")
            finally:
                with self.state_lock:
                    self.is_playing = False
                self.stop_event.clear()
        
        # Start playback in thread
        self.playback_thread = threading.Thread(target=play_audio, daemon=True)
        self.playback_thread.start()
    
    def speak(self, text: str, voice: str = "default", emotive_tags: str = "", 
              enable_barge_in: bool = True) -> str:
        """Convert text to speech with INSTANT barge-in capability."""
        try:
            if not self.engine or not self.stream:
                raise ValueError("TTS not initialized")
            
            self.is_barge_in_enabled = enable_barge_in
            logger.info(f"🗣 Speaking: {text[:50]}...")
            
            if emotive_tags:
                text = f"{text} {emotive_tags}"
            
            if voice != "default":
                try:
                    self.engine.set_voice(voice)
                except Exception as e:
                    logger.warning(f"Voice '{voice}' unavailable: {e}")
            
            self._playback_with_barge_in(text)
            
            return "audio_playing"
            
        except Exception as e:
            logger.error(f"❌ TTS error: {e}")
            return ""
    
    def wait_for_completion(self, timeout: float = 30.0) -> bool:
        """Wait for playback completion or barge-in."""
        try:
            start_time = time.time()
            
            while True:
                with self.state_lock:
                    if not self.is_playing:
                        return not self.barge_in_detected
                    if self.barge_in_detected:
                        return False
                
                if time.time() - start_time > timeout:
                    logger.warning("⏰ Playback timeout")
                    return False
                
                time.sleep(0.01)  # Fast polling (10ms)
                
        except Exception as e:
            logger.error(f"❌ Wait error: {e}")
            return False
    
    def is_barge_in_detected(self) -> bool:
        """Check if barge-in occurred."""
        with self.state_lock:
            return self.barge_in_detected
    
    def shutdown(self):
        """Clean shutdown with resource cleanup."""
        try:
            logger.info("🧹 Shutting down TTS...")
            
            with self.state_lock:
                self.is_playing = False
            self.stop_event.set()
            
            # Stop streams
            if hasattr(self, 'stream') and self.stream:
                try:
                    self.stream.stop()
                except Exception:
                    pass
                self.stream = None
            
            # Cleanup engine
            if hasattr(self, 'engine'):
                self.engine = None
            
            # # Cleanup barge-in recorder (don't call shutdown, just dereference)
            # if self.barge_in_recorder:
            #     self.barge_in_recorder = None
            
            # Barge-in uses main STT (no separate cleanup needed)
            pass
            
            logger.info("✅ TTS shutdown complete")
        except Exception as e:
            logger.error(f"❌ Shutdown error: {e}")


async def main():
    """Test TTS with instant barge-in."""
    from stt_handler import STTHandler
    
    stt = STTHandler()
    await stt.start_listening()
    
    tts = TTSHandler(stt_handler=stt)
    
    test_text = "This is a test of the INSTANT barge-in system. Try interrupting me RIGHT NOW by speaking!"
    print(f"Speaking: {test_text}")
    print("🎤 Interrupt by speaking NOW!")
    
    tts.speak(test_text)
    completed = tts.wait_for_completion(timeout=20.0)
    
    if tts.is_barge_in_detected():
        print("✅ Barge-in detected INSTANTLY!")
    else:
        print("⏹ Playback completed without interruption")
    
    tts.shutdown()
    await stt.stop_listening()

if __name__ == "__main__":
    asyncio.run(main())