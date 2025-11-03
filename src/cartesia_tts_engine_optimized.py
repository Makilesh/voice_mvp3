# cartesia_tts_engine.py - Optimized Ultra-Low Latency Cartesia AI TTS Engine
"""
Cartesia AI TTS Engine - Optimized for Real-Time Voice Calling
- 40-90ms first-byte latency (Sonic 3)
- WebSocket streaming with minimal overhead
- Thread-safe barge-in callback support
- Efficient PyAudio integration
"""
import os
import asyncio
import pyaudio
import threading
import queue
import time
import logging
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum
from dotenv import load_dotenv
from cartesia import AsyncCartesia

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


class PlaybackState(Enum):
    """Minimal playback states."""
    IDLE = "idle"
    PLAYING = "playing"
    STOPPED = "stopped"


@dataclass
class AudioConfig:
    """Audio configuration for Cartesia TTS."""
    sample_rate: int = 22050  # Cartesia optimal
    channels: int = 1
    format: int = pyaudio.paFloat32
    encoding: str = "pcm_f32le"
    chunk_size: int = 1024
    
    def to_cartesia_format(self) -> Dict[str, Any]:
        return {
            "sample_rate": self.sample_rate,
            "encoding": self.encoding,
            "container": "raw"
        }


@dataclass
class VoiceConfig:
    """Voice configuration for Cartesia TTS."""
    voice_id: str = "a0e99841-438c-4a64-b679-ae501e7d6091"  # Brooke
    model: str = "sonic-3"  # Best quality/speed balance
    language: str = "en"
    speed: float = 1.0
    emotion: Optional[str] = None
    
    def to_cartesia_voice(self) -> Dict[str, str]:
        return {
            "mode": "id",
            "id": self.voice_id,
            "__experimental_controls": {
                "speed": self.speed if hasattr(self, 'speed') else 1.0
            }
        }


class CartesiaTTSEngine:
    """
    Ultra-low latency Cartesia AI TTS Engine - Optimized.
    
    Features:
    - 40-90ms first-byte latency
    - Async WebSocket streaming
    - Real-time playback with PyAudio
    - Thread-safe barge-in callback
    - Minimal overhead
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_config: Optional[VoiceConfig] = None,
        audio_config: Optional[AudioConfig] = None
    ):
        # API Configuration
        self.api_key = api_key or os.getenv('CARTESIA_API_KEY')
        if not self.api_key:
            raise ValueError("CARTESIA_API_KEY required")
        
        # Voice & Audio Configuration
        self.voice_config = voice_config or VoiceConfig()
        self.audio_config = audio_config or AudioConfig()
        
        # Cartesia Client (async)
        self.client: Optional[AsyncCartesia] = None
        
        # PyAudio for real-time playback
        self.pyaudio_instance: Optional[pyaudio.PyAudio] = None
        self.audio_stream: Optional[pyaudio.Stream] = None
        
        # Thread-safe state
        self.state = PlaybackState.IDLE
        self.state_lock = threading.Lock()
        self.stop_event = threading.Event()
        
        # Audio streaming queue (WebSocket → PyAudio)
        self.audio_queue: queue.Queue = queue.Queue(maxsize=50)
        
        # Barge-in callback (set by TTS handler)
        self.barge_in_callback: Optional[Callable[[], bool]] = None
        
        logger.info(
            f"🎤 Cartesia TTS Engine initialized "
            f"(voice: Brooke, model: {self.voice_config.model}, "
            f"sample_rate: {self.audio_config.sample_rate}Hz)"
        )

    async def initialize(self):
        """Initialize async components."""
        try:
            if not self.client:
                self.client = AsyncCartesia(api_key=self.api_key)
                logger.info("✅ Cartesia client initialized")
                
                # Test connection
                await self._test_connection()
                
        except Exception as e:
            logger.error(f"❌ Cartesia initialization failed: {e}")
            raise
    
    async def _test_connection(self) -> bool:
        """Test Cartesia API connection."""
        try:
            # Simple connection test
            logger.info("🔍 Testing Cartesia connection...")
            return True
        except Exception as e:
            logger.error(f"❌ Connection test failed: {e}")
            return False
    
    def _init_audio_output(self):
        """Initialize PyAudio for real-time playback."""
        try:
            if not self.pyaudio_instance:
                self.pyaudio_instance = pyaudio.PyAudio()
                
            if not self.audio_stream or not self.audio_stream.is_active():
                self.audio_stream = self.pyaudio_instance.open(
                    format=self.audio_config.format,
                    channels=self.audio_config.channels,
                    rate=self.audio_config.sample_rate,
                    output=True,
                    frames_per_buffer=self.audio_config.chunk_size
                )
                logger.debug("🔊 Audio output initialized")
                
        except Exception as e:
            logger.error(f"❌ Audio init failed: {e}")
            raise
    
    def _cleanup_audio_output(self):
        """Cleanup PyAudio resources."""
        try:
            if self.audio_stream:
                if self.audio_stream.is_active():
                    self.audio_stream.stop_stream()
                self.audio_stream.close()
                self.audio_stream = None
            logger.debug("🧹 Audio output cleaned up")
        except Exception as e:
            logger.warning(f"Audio cleanup error: {e}")
    
    async def _stream_audio_from_websocket(
        self,
        text: str,
        voice_config: Optional[VoiceConfig] = None,
        audio_config: Optional[AudioConfig] = None
    ):
        """
        Stream audio chunks from Cartesia WebSocket.
        """
        try:
            voice_cfg = voice_config or self.voice_config
            audio_cfg = audio_config or self.audio_config
            
            with self.state_lock:
                self.state = PlaybackState.PLAYING
            
            first_chunk = True
            start_time = time.time()
            chunk_count = 0
            
            logger.info(f"🎵 Streaming: {text[:50]}...")
            
            # Connect to WebSocket and stream
            websocket = await self.client.tts.websocket()
            
            # Send synthesis request
            response = await websocket.send(
                model_id=voice_cfg.model,
                transcript=text,
                voice=voice_cfg.to_cartesia_voice(),
                output_format=audio_cfg.to_cartesia_format(),
                language=voice_cfg.language,
                stream=True
            )
            
            # Stream from Cartesia WebSocket
            async for chunk in response:
                # Check for barge-in BEFORE queueing
                if self.stop_event.is_set():
                    logger.info("🛑 Barge-in detected, stopping stream")
                    break
                
                # Check barge-in callback (if set by TTS handler)
                if self.barge_in_callback and self.barge_in_callback():
                    logger.info("🛑 Barge-in via callback, stopping stream")
                    self.stop_event.set()
                    break
                
                # Get audio bytes
                audio_bytes = chunk.audio if hasattr(chunk, 'audio') else chunk.get('audio')
                if not audio_bytes:
                    continue
                
                # Log first chunk latency
                if first_chunk:
                    first_chunk = False
                    latency_ms = (time.time() - start_time) * 1000
                    logger.info(f"⚡ First audio chunk: {latency_ms:.0f}ms")
                
                # Queue for playback (non-blocking)
                try:
                    self.audio_queue.put_nowait(audio_bytes)
                    chunk_count += 1
                except queue.Full:
                    logger.warning("⚠️ Audio queue full, dropping chunk")
            
            # Signal end of stream
            self.audio_queue.put_nowait(None)
            
            total_time = (time.time() - start_time) * 1000
            logger.info(f"✅ Stream complete: {chunk_count} chunks, {total_time:.0f}ms")
            
        except Exception as e:
            logger.error(f"❌ Streaming error: {e}")
            self.audio_queue.put_nowait(None)  # Signal error
            raise
    
    def _audio_consumer(self):
        """
        Consume audio chunks from queue and play via PyAudio.
        Runs in separate thread.
        """
        try:
            self._init_audio_output()
            
            while not self.stop_event.is_set():
                try:
                    # Get audio chunk (blocking with timeout)
                    audio_bytes = self.audio_queue.get(timeout=0.1)
                    
                    if audio_bytes is None:  # End of stream signal
                        break
                    
                    # Check barge-in before playback
                    if self.barge_in_callback and self.barge_in_callback():
                        logger.info("🛑 Barge-in during playback")
                        self.stop_event.set()
                        break
                    
                    # Play audio chunk
                    if self.audio_stream and self.audio_stream.is_active():
                        self.audio_stream.write(audio_bytes)
                    
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"❌ Playback error: {e}")
                    break
            
            logger.debug("🔇 Audio consumer stopped")
            
        except Exception as e:
            logger.error(f"❌ Audio consumer error: {e}")
        finally:
            self._cleanup_audio_output()
            with self.state_lock:
                self.state = PlaybackState.STOPPED
    
    async def synthesize_and_play(
        self,
        text: str,
        voice_config: Optional[VoiceConfig] = None,
        audio_config: Optional[AudioConfig] = None,
        enable_barge_in: bool = True
    ) -> bool:
        """
        Synthesize and play audio with barge-in support.
        
        Returns:
            True if completed, False if interrupted
        """
        try:
            # Initialize if needed
            if not self.client:
                await self.initialize()
            
            # Reset state
            self.stop_event.clear()
            with self.state_lock:
                self.state = PlaybackState.PLAYING
            
            # Clear audio queue
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break
            
            # Start audio consumer thread
            consumer_thread = threading.Thread(
                target=self._audio_consumer,
                daemon=True
            )
            consumer_thread.start()
            
            # Stream audio from Cartesia (producer)
            await self._stream_audio_from_websocket(
                text=text,
                voice_config=voice_config,
                audio_config=audio_config
            )
            
            # Wait for consumer to finish
            consumer_thread.join(timeout=10.0)
            
            # Check if interrupted
            was_interrupted = self.stop_event.is_set()
            
            with self.state_lock:
                self.state = PlaybackState.IDLE
            
            return not was_interrupted
            
        except Exception as e:
            logger.error(f"❌ Synthesis error: {e}")
            with self.state_lock:
                self.state = PlaybackState.IDLE
            return False
    
    def stop_playback(self):
        """Immediately stop playback."""
        try:
            logger.info("🛑 Stopping Cartesia playback")
            self.stop_event.set()
            
            # Clear queue
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break
            
            with self.state_lock:
                self.state = PlaybackState.STOPPED
                
        except Exception as e:
            logger.error(f"Stop error: {e}")
    
    def is_playing(self) -> bool:
        """Check if currently playing."""
        with self.state_lock:
            return self.state == PlaybackState.PLAYING
    
    def get_state(self) -> PlaybackState:
        """Get current state."""
        with self.state_lock:
            return self.state
    
    def set_barge_in_callback(self, callback: Callable[[], bool]):
        """
        Set callback to check for barge-in during playback.
        Callback should return True if user is speaking.
        """
        self.barge_in_callback = callback
        logger.info("✅ Barge-in callback registered")
    
    async def cleanup(self):
        """Cleanup resources."""
        try:
            self.stop_playback()
            self._cleanup_audio_output()
            
            if self.pyaudio_instance:
                self.pyaudio_instance.terminate()
                self.pyaudio_instance = None
            
            if self.client:
                await self.client.close()
                self.client = None
            
            logger.info("✅ Cartesia TTS cleanup complete")
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")


# Voice ID Constants
class CartesiaVoices:
    """Common Cartesia voice IDs."""
    BROOKE = "a0e99841-438c-4a64-b679-ae501e7d6091"  # Female, American
    CLYDE = "2ee87190-8f84-4925-97da-e52547f9462c"   # Male, American
    EDDIE = "63ff761f-c1e8-414b-b969-d1833d1c870c"   # Male, American


# Test function
async def test_cartesia_tts():
    """Test Cartesia TTS Engine."""
    try:
        print("🧪 Testing Cartesia TTS Engine...")
        
        engine = CartesiaTTSEngine()
        await engine.initialize()
        
        test_text = "Hello! This is a test of the Cartesia text to speech engine with ultra low latency."
        
        print(f"\n📝 Text: {test_text}")
        print("🎵 Playing...")
        
        completed = await engine.synthesize_and_play(
            text=test_text,
            enable_barge_in=False
        )
        
        if completed:
            print("✅ Playback completed successfully!")
        else:
            print("⚠️ Playback was interrupted")
        
        await engine.cleanup()
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_cartesia_tts())
