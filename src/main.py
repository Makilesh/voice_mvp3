# main.py - OPTIMIZED VERSION
from stt_handler import STTHandler
from llm_handler import LLMHandler
from tts_handler import TTSHandler
import asyncio
import logging
import warnings
import time

warnings.filterwarnings("ignore", category=DeprecationWarning)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ConversationManager:
    """Manages conversation state and error recovery."""
    
    def __init__(self, max_history: int = 10):
        self.history = []
        self.max_history = max_history
        self.turn_count = 0
        self.error_count = 0
        self.max_consecutive_errors = 3
    
    def add_turn(self, role: str, content: str):
        """Add conversation turn with automatic pruning."""
        self.history.append(f"{role}: {content}")
        if len(self.history) > self.max_history:
            # Keep system prompt + recent history
            self.history = [self.history[0]] + self.history[-(self.max_history-1):]
        self.turn_count += 1
    
    def get_history(self) -> list:
        """Get conversation history."""
        return self.history.copy()
    
    def record_error(self):
        """Track consecutive errors."""
        self.error_count += 1
    
    def reset_errors(self):
        """Reset error counter on success."""
        self.error_count = 0
    
    def should_abort(self) -> bool:
        """Check if too many consecutive errors."""
        return self.error_count >= self.max_consecutive_errors


async def handle_conversation_turn(stt_handler, llm_handler, tts_handler, 
                                   conversation_manager) -> tuple[bool, bool]:
    """
    Handle a single conversation turn with optimized flow.
    
    Returns:
        (should_continue, should_exit)
    """
    try:
        turn_start = time.time()
        
        # Step 1: Get user input (STT)
        logger.info("🎤 Listening for speech...")
        print("\n🎤 Speak now...")
        
        user_text = await stt_handler.get_transcription()
        
        if not user_text:
            logger.warning("⚠️ No speech detected")
            print("❌ No speech detected. Please try again.")
            conversation_manager.record_error()
            return True, False
        
        stt_time = time.time() - turn_start
        print(f"📝 You: {user_text} ({stt_time*1000:.0f}ms)")
        
        # Check for exit commands
        if user_text.strip().lower() in ['quit', 'exit', 'goodbye', 'bye']:
            return False, True
        
        # Add to history
        conversation_manager.add_turn("User", user_text)
        
        # Step 2: Get AI response (LLM)
        llm_start = time.time()
        logger.info("🤖 Generating response...")
        
        response = await llm_handler.process_text_with_history(
            user_text, 
            conversation_manager.get_history()
        )
        
        llm_time = time.time() - llm_start
        
        if not response or len(response.strip()) < 3:
            logger.error("❌ Invalid LLM response")
            response = "I'm sorry, I didn't quite catch that. Could you repeat?"
            conversation_manager.record_error()
        else:
            conversation_manager.reset_errors()
        
        print(f"🤖 Agent: {response} ({llm_time*1000:.0f}ms)")
        conversation_manager.add_turn("Agent", response)
        
        # Step 3: Speak response (TTS)
        tts_start = time.time()
        logger.info("🗣 Speaking response...")
        
        tts_handler.speak(response, enable_barge_in=True)
        
        # Monitor for barge-in during TTS
        barge_in_start_check = time.time()
        last_rt_text = ""
        
        # Poll for real-time transcription while TTS is playing
        while tts_handler.is_playing:
            if time.time() - barge_in_start_check > 0.1:  # Check every 100ms
                rt_text = stt_handler.get_realtime_text()
                if rt_text and rt_text != last_rt_text and len(rt_text) > 2:
                    logger.info(f"🎤 Real-time detected during TTS: {rt_text}")
                    last_rt_text = rt_text
                barge_in_start_check = time.time()
            
            await asyncio.sleep(0.05)  # 50ms polling
        # Wait for completion or barge-in
        completed = tts_handler.wait_for_completion(timeout=30.0)
        
        tts_time = time.time() - tts_start
        total_time = time.time() - turn_start
        
        # Log performance
        logger.info(f"⏱ Turn timing: STT={stt_time*1000:.0f}ms, "
                   f"LLM={llm_time*1000:.0f}ms, TTS={tts_time*1000:.0f}ms, "
                   f"Total={total_time*1000:.0f}ms")
        
        # Check for barge-in
        if tts_handler.is_barge_in_detected():
            print("🎤 You interrupted! Processing your input...")
            conversation_manager.add_turn("System", "[User interrupted]")
            # Continue to next turn (user already spoke)
            return True, False
        
        # Performance warning
        if total_time > 3.0:
            logger.warning(f"⚠️ Slow turn detected: {total_time:.1f}s")
        
        return True, False
        
    except Exception as e:
        logger.error(f"❌ Turn error: {e}", exc_info=True)
        conversation_manager.record_error()
        
        if conversation_manager.should_abort():
            print("❌ Too many errors. Exiting for safety.")
            return False, True
        
        print("❌ An error occurred. Continuing...")
        return True, False


async def main():
    """Main conversation loop with robust error handling."""
    logger.info("🚀 Starting AI Voice Agent...")
    
    stt_handler = None
    tts_handler = None
    
    try:
        # Step 1: Initialize handlers
        logger.info("🔧 Initializing handlers...")
        print("=" * 50)
        print("🎙 Shamla Tech AI Voice Assistant")
        print("=" * 50)
        print("Initializing... Please wait.")
        
        # Initialize STT first (balanced mode for best speed/accuracy)
        stt_handler = STTHandler(mode="balanced")
        await stt_handler.start_listening()
        
        # Initialize LLM
        llm_handler = LLMHandler()
        
        # Initialize TTS with shared STT
        tts_handler = TTSHandler(stt_handler=stt_handler)
        
        # Initialize conversation manager
        conversation_manager = ConversationManager(max_history=12)
        conversation_manager.add_turn(
            "System",
            "You are Alex, an AI voice assistant for Shamla Tech. "
            "Shamla Tech provides AI, blockchain, and cryptocurrency services. "
            "Be warm, helpful, and conversational. Keep responses concise for voice."
        )
        
        print("✅ System ready!")
        
        # Step 2: Welcome message
        welcome = "Hello! Thank you for calling Shamla Tech. I'm Alex, your AI assistant. How can I help you today?"
        print(f"\n🤖 Agent: {welcome}")
        conversation_manager.add_turn("Agent", welcome)
        
        tts_handler.speak(welcome, enable_barge_in=False)  # Don't allow barge-in on welcome
        tts_handler.wait_for_completion(timeout=15.0)
        
        # Step 3: Main conversation loop
        print("\n💡 Tips:")
        print("- Speak naturally and clearly")
        print("- You can interrupt the AI by speaking")
        print("- Say 'quit' or 'goodbye' to exit")
        print()
        
        loop_count = 0
        max_turns = 50  # Safety limit
        
        while loop_count < max_turns:
            loop_count += 1
            
            should_continue, should_exit = await handle_conversation_turn(
                stt_handler, llm_handler, tts_handler, conversation_manager
            )
            
            if should_exit:
                print("\n👋 Thank you for calling Shamla Tech! Have a great day!")
                break
            
            if not should_continue:
                break
            
            # Brief pause between turns
            await asyncio.sleep(0.1)
        
        if loop_count >= max_turns:
            print("\n⏰ Session limit reached. Thank you for using Shamla Tech!")
        
        # Print session stats
        stats = stt_handler.get_performance_stats()
        print(f"\n📊 Session Stats:")
        print(f"   Turns: {conversation_manager.turn_count}")
        print(f"   Transcriptions: {stats['transcription_count']}")
        print(f"   Avg STT Latency: {stats['avg_latency_ms']}ms")
        
        logger.info("✅ Conversation completed successfully")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
        logger.info("User interrupt detected")
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        print("Please check logs and restart the system.")
        
    finally:
        # Step 4: Cleanup (always runs)
        logger.info("🧹 Cleaning up...")
        print("\n🧹 Shutting down...")
        
        try:
            if tts_handler:
                tts_handler.shutdown()
        except Exception as e:
            logger.error(f"TTS cleanup error: {e}")
        
        try:
            if stt_handler:
                await stt_handler.stop_listening()
        except Exception as e:
            logger.error(f"STT cleanup error: {e}")
        
        print("✅ Shutdown complete")
        logger.info("✅ System shutdown complete")


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════╗
║     🎙 Shamla Tech AI Voice Assistant v2.0       ║
║     Optimized for Real-Time Performance           ║
╚═══════════════════════════════════════════════════╝

Prerequisites:
1. Microphone access
2. OPENAI_API_KEY in .env file
3. Python dependencies installed

Starting in 3 seconds...
""")
    
    time.sleep(3)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Startup error: {e}")
        logger.error(f"Startup failed: {e}", exc_info=True)