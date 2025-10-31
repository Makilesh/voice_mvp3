# tts_handler.py - PIPER ENGINE VERSION
import os
import logging
import time
import threading
import warnings
from RealtimeTTS import PiperEngine, PiperVoice, TextToAudioStream
import sounddevice as sd
import numpy as np

import os
import logging
import time
import threading
from RealtimeTTS import PiperEngine, PiperVoice, TextToAudioStream

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
            # DEBUG: Step 1 - Engine initialization
            logger.info("🔧 DEBUG: Starting PiperEngine initialization...")
            voice_path = "C:\\Users\\Makilesh M\\.local\\share\\piper\\voices\\en_US-lessac-medium.onnx"
            
            # Try creating voice object first
            try:
                self.voice_obj = PiperVoice(voice_path)
                self.engine = PiperEngine()
                self.engine.voice = self.voice_obj
                logger.info("🔧 DEBUG: PiperEngine initialized with voice object")
            except Exception as e:
                logger.warning(f"🔧 DEBUG: Voice object setup failed: {e}")
                # Fallback: try passing voice path directly to engine
                try:
                    self.engine = PiperEngine(voice=voice_path)
                    logger.info("🔧 DEBUG: PiperEngine initialized with voice path directly")
                except Exception as e2:
                    logger.error(f"🔧 DEBUG: Engine initialization failed: {e2}")
                    raise
            
            self.stream = TextToAudioStream(self.engine)
            logger.info("🔧 DEBUG: TextToAudioStream created successfully")
            
            # CRITICAL: Reference to main STT (must be continuously listening)
            self.main_stt = stt_handler
            if not self.main_stt:
                raise ValueError("STT handler required for barge-in detection")
            
            # State management
            self.is_playing = False
            self.is_barge_in_enabled = True
            self.barge_in_detected = False
            self.stop_event = threading.Event()
            self.interrupt_stop_event = threading.Event()
            self.state_lock = threading.Lock()
            
            # Real-time monitoring state
            self.last_seen_realtime_text = ""
            self.barge_in_sensitivity = 1  # Minimum chars to trigger (ultra-sensitive)
            
            # DEBUG: Playback completion tracking
            self.playback_start_time = None
            self.playback_completed = False
            
            # DEBUG: Test basic audio functionality
            logger.info("🔧 DEBUG: Testing basic audio functionality...")
            try:
                test_stream = TextToAudioStream(self.engine)
                test_stream.feed("Testing.")
                logger.info("🔧 DEBUG: Basic audio test successful")
            except Exception as test_e:
                logger.error(f"🔧 DEBUG: Basic audio test failed: {test_e}")
            
            # DEBUG: Check audio devices
            logger.info("🔧 DEBUG: Checking audio devices...")
            try:
                devices = sd.query_devices()
                default_output = sd.default.device[1]
                logger.info(f"🔧 DEBUG: Available audio devices: {len(devices)}")
                logger.info(f"🔧 DEBUG: Default output device: {default_output} - {devices[default_output]['name'] if default_output < len(devices) else 'Unknown'}")
                
                # Test audio device with a simple beep
                logger.info("🔧 DEBUG: Testing audio device with beep...")
                duration = 0.1  # seconds
                sample_rate = 44100
                frequency = 440  # Hz (A4 note)
                
                t = np.linspace(0, duration, int(sample_rate * duration), False)
                tone = np.sin(frequency * 2 * np.pi * t) * 0.5
                
                sd.play(tone, sample_rate)
                sd.wait()  # Wait for playback to finish
                logger.info("🔧 DEBUG: Audio device test beep completed")
                
            except Exception as audio_e:
                logger.error(f"🔧 DEBUG: Audio device test failed: {audio_e}")
                logger.error(f"🔧 DEBUG: This may indicate audio driver issues or system sound problems")
            
            logger.info("🎤 TTS Handler initialized with AGGRESSIVE barge-in (<150ms)")
        except Exception as e:
            logger.error(f"❌ Error initializing TTS: {e}")
            raise
    
  
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
            check_interval = 0.01  # Check every 10ms (ultra-aggressive polling)
            
            logger.info("👂 Barge-in monitor: ACTIVE")
            
            # Reset tracking
            self.last_seen_realtime_text = ""
            consecutive_detections = 0
            min_consecutive = 1  # Need only 1 detection (20ms) to confirm - more aggressive
            
            while not self.stop_event.is_set():
                with self.state_lock:
                    # Only break if explicitly stopped, not if not playing yet
                    if self.stop_event.is_set():
                        break
                
                current_time = time.time()
                
                # Skip TTS startup buffer
                if current_time - playback_start < tts_startup_buffer:
                    time.sleep(check_interval)
                    continue
                
                try:
                    # Get real-time transcription
                    realtime_text = self.main_stt.get_realtime_text()
                    
                    # ULTRA-SENSITIVE: Detect any speech, even single character
                    if realtime_text and len(realtime_text.strip()) > 0:
                        if realtime_text != self.last_seen_realtime_text:
                            consecutive_detections += 1
                            
                            # Confirm with consecutive detections
                            if consecutive_detections >= min_consecutive:
                                logger.info(f"🛑 Barge-in detected: '{realtime_text}'")
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
                    self.barge_in_detected = False
                    if hasattr(self, 'set_tts_active'):
                        self.set_tts_active(True)
                self.stop_event.clear()
                
                # DEBUG-FINAL: Set play start time for debounce timing
                if hasattr(self, 'main_stt') and self.main_stt:
                    self.main_stt.play_start_time = time.time()
                
                # CRITICAL: Start monitor BEFORE audio starts
                monitor_thread = threading.Thread(target=self._monitor_barge_in, daemon=True)
                monitor_thread.start()
                
                # Brief delay to ensure monitor is active
                time.sleep(0.02)
                
                # Play audio (non-blocking thread)
                if self.stream:
                    # DEBUG: Step 2 - Stream preparation
                    logger.info(f"🔧 DEBUG: Preparing stream for text: '{text[:20]}...'")
                    
                    # Clear any existing audio first
                    if hasattr(self.stream, '_audio_queue'):
                        self.stream._audio_queue.clear()
                        logger.info("🔧 DEBUG: Audio queue cleared")
                    
                    # DEBUG: Step 3 - Feed text to stream
                    logger.info("🔧 DEBUG: Calling stream.feed()...")
                    self.stream.feed(text)
                    logger.info("🔧 DEBUG: stream.feed() completed")
                    
                    # MID-CUT-FIX: Sync active on stream start (fixes False mid-play)
                    with self.state_lock:
                        self.is_playing = True
                        self.interrupt_stop_event.clear()
                        if hasattr(self, 'set_tts_active'):
                            self.set_tts_active(True)
                    logger.info("Raw VAD bound: ready for mid-stop")
                    
                    # PIPERENGINE-BARGEIN: Docs silero=0.35 + Event iterate for mid-cut (chunk 00:00.192 → fire/stop, #223)
                    # Piper engine uses play_async() which is non-blocking
                    try:
                        # DEBUG: Step 4 - Call play_async
                        logger.info("🔧 DEBUG: Calling stream.play_async()...")
                        self.stream.play_async()
                        logger.info("🔧 DEBUG: stream.play_async() called successfully - waiting for playback...")
                        
                        # DEBUG: Wait for actual playback completion
                        start_wait = time.time()
                        self.playback_start_time = start_wait
                        self.playback_completed = False
                        
                        logger.info("🔧 DEBUG: Starting playback completion monitoring...")
                        while time.time() - start_wait < 10:  # Wait up to 10 seconds
                            # Check multiple indicators of completion
                            stream_is_playing = getattr(self.stream, 'is_playing', False)
                            queue_has_items = (hasattr(self.stream, '_audio_queue') and
                                             getattr(self.stream, '_audio_queue', None) and
                                             len(self.stream._audio_queue) > 0)
                            
                            logger.info(f"🔧 DEBUG: Playback status - is_playing: {stream_is_playing}, queue_has_items: {queue_has_items}, elapsed: {time.time() - start_wait:.1f}s")
                            
                            # Consider playback complete if:
                            # 1. Stream is not playing AND queue is empty
                            # 2. OR we've waited a reasonable time for short audio
                            if not stream_is_playing and not queue_has_items:
                                logger.info("🔧 DEBUG: Playback completed successfully (stream stopped, queue empty)")
                                self.playback_completed = True
                                break
                            elif time.time() - start_wait > 2:  # For very short audio, assume complete after 2s
                                logger.info("🔧 DEBUG: Playback assumed complete (timeout for short audio)")
                                self.playback_completed = True
                                break
                            
                            time.sleep(0.1)
                        else:
                            logger.warning("🔧 DEBUG: Playback timeout - assuming completed")
                            self.playback_completed = True
                            
                    except Exception as e:
                        logger.error(f"🔧 DEBUG: Error calling play_async(): {e}")
                        # Fallback to synchronous play
                        try:
                            logger.info("🔧 DEBUG: Calling stream.play() as fallback...")
                            self.stream.play()
                            logger.info("🔧 DEBUG: stream.play() completed successfully")
                        except Exception as e2:
                            logger.error(f"🔧 DEBUG: Error calling play(): {e2}")
                else:
                    logger.error("Stream is None - cannot play audio")
                        
            except Exception as e:
                logger.error(f"❌ Playback thread error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                with self.state_lock:
                    self.is_playing = False
                    if hasattr(self, 'set_tts_active'):
                        self.set_tts_active(False)
                self.stop_event.clear()
        
        # Start playback in daemon thread
        self.playback_thread = threading.Thread(target=play_audio, daemon=True)
        self.playback_thread.start()
    
    def speak(self, text: str, voice: str = "default", emotive_tags: str = "",
              enable_barge_in: bool = True) -> str:
        """Speak with instant barge-in detection."""
        try:
            # DEBUG: Step 0 - Input validation
            logger.info(f"🔧 DEBUG: speak() called with text: '{text[:30]}...'")
            
            if not self.engine or not self.stream:
                raise ValueError("TTS not initialized")
            
            # DEBUG: Force test utterance if this is a basic test
            if text == "Testing audio now.":
                logger.info("🔧 DEBUG: Special test utterance detected - adding debug emphasis")
                text = "Testing audio now. This is a test of the PiperEngine audio system."
            
            # Piper-specific debounce handling
            retry_count = 0
            with self.state_lock:
                while (self.is_playing or
                      (hasattr(self.stream, '_audio_queue') and getattr(self.stream, '_audio_queue', None) and len(self.stream._audio_queue) > 0) or
                      (hasattr(self.stream, 'is_playing') and getattr(self.stream, 'is_playing', False))) and retry_count < 5:
                    
                    # Piper doesn't have engine._inLoop
                    queue_len = len(self.stream._audio_queue) if hasattr(self.stream, '_audio_queue') and getattr(self.stream, '_audio_queue', None) else 0
                    is_stream_playing = getattr(self.stream, 'is_playing', False)
                    logger.info(f"🛑 VAD check (active=True, time=N/A) → retry {retry_count}/5, playing={self.is_playing}, queue_len={queue_len}, stream_playing={is_stream_playing}")
                    self.stop_playback()
                    time.sleep(0.2)
                    retry_count += 1
            
            self.is_barge_in_enabled = enable_barge_in
            logger.info(f"🗣 Speaking: {text[:50]}... (barge-in: {enable_barge_in})")
            
            if emotive_tags:
                text = f"{text} {emotive_tags}"
            
            if voice != "default":
                try:
                    # Piper voice configuration
                    if voice == "default":
                        voice_config = "C:\\Users\\Makilesh\\.local\\share\\piper\\voices\\en_US-lessac-medium.onnx"
                    else:
                        voice_config = voice
                    
                    # Reinitialize engine with new voice
                    self.engine = PiperEngine(voice=voice_config)
                    logger.info(f"🎙️ Voice changed to: {voice_config}")
                except Exception as e:
                    logger.warning(f"Voice '{voice}' unavailable: {e}")
                    # Fallback to default
                    try:
                        self.engine = PiperEngine(voice="C:\\Users\\Makilesh\\.local\\share\\piper\\voices\\en_US-lessac-medium.onnx")
                        logger.info("🎙️ Fallback to default voice: en_US-lessac-medium")
                    except Exception as fallback_e:
                        logger.error(f"❌ Failed to set fallback voice: {fallback_e}")
            
            # CRITICAL: Clear STT real-time buffer before speaking
            if self.main_stt:
                self.main_stt.clear_realtime_text()
            
            # DEBUG: Step 1 - Call playback
            logger.info("🔧 DEBUG: Calling _play_with_monitoring()...")
            self._play_with_monitoring(text)
            logger.info("🔧 DEBUG: _play_with_monitoring() returned")
            
            return "audio_playing"
            
        except Exception as e:
            logger.error(f"❌ TTS error: {e}")
            import traceback
            traceback.print_exc()
            return ""
    
    def wait_for_completion(self, timeout: float = 30.0) -> bool:
        """Wait for playback to complete or be interrupted."""
        try:
            start_time = time.time()
            
            while True:
                with self.state_lock:
                    if not self.is_playing:
                        was_interrupted = self.barge_in_detected
                        if was_interrupted:
                            logger.info("✅ Playback interrupted by user")
                        return not was_interrupted
                     
                    if self.barge_in_detected:
                        return False
                     
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
    
    def set_tts_active(self, active: bool):
        """Set TTS active state for conditional VAD triggering."""
        # This will be connected to STT's tts_active flag
        pass
    
    def interrupt_and_stop(self):
        """Thread-safe mid-sentence interrupt for raw VAD."""
        try:
            self.interrupt_stop_event.set()
            
            # Piper-specific interrupt handling
            if hasattr(self, 'stream') and self.stream:
                self.stream.stop()
            
            # Piper engine doesn't have the same stop method as SystemEngine
            # but we can try to interrupt synthesis
            if hasattr(self, 'engine') and self.engine:
                try:
                    # Piper may not have explicit stop, but we can set stop event
                    self.stop_event.set()
                except Exception:
                    pass
            
            logger.info("🛑 Raw mid-cut fired (Piper stream stopped)")
        except Exception as e:
            logger.error(f"Interrupt stop error: {e}")
    
    def stop_playback(self):
        """Immediately stop TTS playback."""
        try:
            if self.stream:
                self.stream.stop()
                # Clear any pending audio queue
                if hasattr(self.stream, '_audio_queue'):
                    self.stream._audio_queue.clear()
                logger.info("🛑 Raw VAD stop fired (mid-TTS, stream aborted)")
            with self.state_lock:
                self.barge_in_detected = True
            self.stop_event.set()
        except Exception as e:
            logger.error(f"Stop playback error: {e}")
    
    def shutdown(self):
        """Clean shutdown."""
        try:
            logger.info("🧹 Shutting down TTS...")
            
            with self.state_lock:
                self.is_playing = False
            self.stop_event.set()
            
            # Piper-specific cleanup
            if hasattr(self, 'stream') and self.stream:
                try:
                    self.stream.stop()
                    # Clear any pending audio queue
                    if hasattr(self.stream, '_audio_queue'):
                        self.stream._audio_queue.clear()
                except Exception as e:
                    logger.warning(f"Stream cleanup error: {e}")
                self.stream = None
            
            # Piper engine cleanup
            if hasattr(self, 'engine'):
                try:
                    # Piper doesn't have explicit stop method like SystemEngine
                    # But we can try to stop any ongoing synthesis
                    if hasattr(self.engine, 'stop'):
                        self.engine.stop()
                except Exception as e:
                    logger.warning(f"Engine cleanup error: {e}")
                self.engine = None
            
            logger.info("✅ TTS shutdown complete")
        except Exception as e:
            logger.error(f"❌ Shutdown error: {e}")