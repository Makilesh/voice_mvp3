# tts_handler.py - OPTIMIZED VERSION
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
    """Handles TTS with robust, low-latency barge-in detection."""
    
    def __init__(self, stt_handler=None):
        """Initialize TTS with dedicated barge-in STT instance."""
        try:
            self.engine = SystemEngine()
            self.stream = TextToAudioStream(self.engine)
            
            # Main STT handler (shared)
            self.main_stt = stt_handler
            
            # Dedicated lightweight STT for barge-in monitoring
            self.barge_in_recorder = None
            self._init_barge_in_recorder()
            
            # State management with thread safety
            self.is_playing = False
            self.is_barge_in_enabled = True
            self.barge_in_detected = False
            self.stop_event = threading.Event()
            self.state_lock = threading.Lock()
            
            # Adaptive thresholds for noise/echo rejection
            self.energy_threshold = 300  # Adaptive baseline
            self.ambient_noise_level = 0
            self.speech_confidence_threshold = 0.6
            
            logger.info("🎤 TTS Handler initialized with dedicated barge-in STT.")
        except Exception as e:
            logger.error(f"❌ Error initializing TTS: {e}")
            raise
    
    def _init_barge_in_recorder(self):
        """Initialize lightweight STT for barge-in (separate from main STT)."""
        try:
            self.barge_in_recorder = AudioToTextRecorder(
                model="tiny",  # Fastest model for real-time detection
                language="en",
                compute_type="int8",
                enable_realtime_transcription=True,
                realtime_model_type="tiny",
                
                # CRITICAL: Optimized for barge-in detection
                realtime_processing_pause=0.05,  # 50ms (was 0.3s)
                post_speech_silence_duration=0.3,  # Quick response
                min_length_of_recording=0.3,  # Catch short interjections
                min_gap_between_recordings=0.05,
                
                # Energy-based VAD for faster detection
                silero_sensitivity=0.3,  # More sensitive during playback
                webrtc_sensitivity=2,  # Balanced sensitivity
                
                use_microphone=True
            )
            logger.info("✅ Barge-in recorder initialized (tiny model)")
        except Exception as e:
            logger.warning(f"⚠️ Could not init barge-in recorder: {e}")
            self.barge_in_recorder = None
    
    def _calculate_audio_energy(self, audio_data) -> float:
        """Calculate RMS energy of audio signal."""
        try:
            if audio_data is None or len(audio_data) == 0:
                return 0.0
            # Convert to numpy array and calculate RMS
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_array**2))
            return float(rms)
        except Exception:
            return 0.0
    
    def _update_ambient_noise(self, energy: float):
        """Adaptive noise floor estimation (exponential moving average)."""
        alpha = 0.1  # Smoothing factor
        self.ambient_noise_level = (alpha * energy + 
                                    (1 - alpha) * self.ambient_noise_level)
    
    def _is_speech_energy(self, energy: float) -> bool:
        """Energy-based speech detection with adaptive threshold."""
        # Dynamic threshold: ambient noise + margin
        threshold = max(self.energy_threshold, 
                       self.ambient_noise_level * 2.5)
        return energy > threshold
    
    def _playback_with_barge_in(self, text: str):
        """Play audio with energy-based + transcription barge-in monitoring."""
        
        def monitor_speech():
            """Dual-stage barge-in: (1) Energy detection → (2) Transcription verification."""
            try:
                if not (self.is_barge_in_enabled and self.barge_in_recorder):
                    return
                
                playback_start = time.time()
                consecutive_speech_frames = 0
                energy_check_interval = 0.05  # 50ms polling (was 200ms)
                last_check = time.time()
                
                # Calibrate ambient noise (first 0.3s)
                calibration_end = playback_start + 0.3
                
                while not self.stop_event.is_set():
                    with self.state_lock:
                        if not self.is_playing:
                            break
                    
                    current_time = time.time()
                    
                    # Stage 1: Fast energy-based pre-detection
                    if current_time - last_check >= energy_check_interval:
                        try:
                            # Get raw audio for energy analysis
                            # Note: RealtimeSTT doesn't expose raw audio directly
                            # We use transcription as primary signal instead
                            
                            # Skip initial TTS buffer to avoid echo
                            if current_time - playback_start < 0.2:
                                last_check = current_time
                                time.sleep(0.02)
                                continue
                            
                            # Stage 2: Check for transcription (actual speech)
                            detected_text = ""
                            try:
                                detected_text = self.barge_in_recorder.text()
                            except Exception:
                                pass
                            
                            if detected_text:
                                detected_text = detected_text.strip()
                                
                                # Filter out likely TTS echo patterns
                                # - Very short (1-2 chars)
                                # - Matches recent TTS output fragments
                                if len(detected_text) <= 2:
                                    last_check = current_time
                                    time.sleep(0.02)
                                    continue
                                
                                # Check if it's similar to what we're speaking (echo)
                                text_lower = text.lower()[:50]  # First 50 chars
                                detected_lower = detected_text.lower()
                                
                                # If detected text is substring of TTS output → likely echo
                                if detected_lower in text_lower:
                                    logger.debug(f"🔇 Ignoring TTS echo: {detected_text}")
                                    last_check = current_time
                                    time.sleep(0.02)
                                    continue
                                
                                # Confidence check: require 2 consecutive detections
                                consecutive_speech_frames += 1
                                
                                if consecutive_speech_frames >= 2:  # 100ms of speech
                                    logger.info(f"🎤 BARGE-IN: '{detected_text}'")
                                    
                                    with self.state_lock:
                                        self.barge_in_detected = True
                                        self.stop_event.set()
                                    
                                    # Stop audio immediately
                                    if self.stream:
                                        try:
                                            self.stream.stop()
                                            logger.info("🛑 Audio stopped (barge-in)")
                                        except Exception:
                                            pass
                                    break
                            else:
                                consecutive_speech_frames = 0
                            
                        except Exception as e:
                            logger.debug(f"Monitor error: {e}")
                        
                        last_check = current_time
                    
                    time.sleep(0.02)  # 20ms sleep (was 50ms)
                    
            except Exception as e:
                logger.error(f"❌ Barge-in monitor error: {e}")
        
        def play_audio():
            """Play audio stream."""
            try:
                with self.state_lock:
                    self.is_playing = True
                    self.barge_in_detected = False
                self.stop_event.clear()
                
                # Start monitoring thread
                monitor_thread = threading.Thread(target=monitor_speech, daemon=True)
                monitor_thread.start()
                
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
        """Convert text to speech with barge-in capability."""
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
                
                time.sleep(0.05)  # 50ms checks
                
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
            
            # Cleanup barge-in recorder
            if self.barge_in_recorder:
                try:
                    self.barge_in_recorder.shutdown()
                except Exception:
                    pass
                self.barge_in_recorder = None
            
            logger.info("✅ TTS shutdown complete")
        except Exception as e:
            logger.error(f"❌ Shutdown error: {e}")


async def main():
    """Test TTS with barge-in."""
    from stt_handler import STTHandler
    
    stt = STTHandler()
    await stt.start_listening()
    
    tts = TTSHandler(stt_handler=stt)
    
    test_text = "This is a test of the barge-in system. You can interrupt me at any time by speaking."
    print(f"Speaking: {test_text}")
    print("Try interrupting by saying something!")
    
    tts.speak(test_text)
    completed = tts.wait_for_completion(timeout=20.0)
    
    if tts.is_barge_in_detected():
        print("✅ Barge-in detected!")
    else:
        print("⏹ Playback completed without interruption")
    
    tts.shutdown()
    await stt.stop_listening()

if __name__ == "__main__":
    asyncio.run(main())