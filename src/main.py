# main.py - FULL-
import warnings
import logging

# Suppress unwanted warnings and errors BEFORE any other imports
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")
warnings.filterwarnings("ignore", message="The handle is invalid")
warnings.filterwarnings("ignore", module="RealtimeSTT")
warnings.filterwarnings("ignore", category=UserWarning, module="ctranslate2")
warnings.filterwarnings("ignore", category=UserWarning)  # Catch all UserWarnings

from stt_handler import STTHandler
from llm_handler import LLMHandler
from tts_handler import TTSHandler
import asyncio
import time

warnings.filterwarnings(
    "ignore",
    message="play_async() called while already playing audio, skipping"
)
# Configure logging
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
        self.history.append(f"{role}: {content}")
        if len(self.history) > self.max_history:
            self.history = [self.history[0]] + self.history[-(self.max_history-1):]
        self.turn_count += 1
    
    def get_history(self) -> list:
        return self.history.copy()
    
    def record_error(self):
        self.error_count += 1
    
    def reset_errors(self):
        self.error_count = 0
    
    def should_abort(self) -> bool:
        return self.error_count >= self.max_consecutive_errors


async def handle_conversation_turn(stt_handler, llm_handler, tts_handler, 
                                   conversation_manager) -> tuple[bool, bool]:
    """
    Handle conversation turn with FULL-DUPLEX support.
    """
    try:
        turn_start = time.time()
        
        # Step 1: Get user input using background polling
        logger.info("🎤 Listening for speech...")
        print("\n🎤 Speak now...")
        
        user_text = ""
        max_wait_time = 15.0  # Maximum time to wait for speech
        start_wait = time.time()
        
        # Poll for user speech using background polling
        while time.time() - start_wait < max_wait_time:
            current_time = time.time()
            
            # Get result from background polling
            polling_text = stt_handler.get_barge_in_text()
            if polling_text and len(polling_text.strip()) > 2:
                user_text = polling_text.strip()
                logger.info(f"🎤 Polling detected speech: '{user_text[:30]}...'")
                break
            
            # Debug logging
            if polling_text:
                logger.debug(f"🎤 Polling result: '{polling_text.strip()[:20]}...'")
            
            await asyncio.sleep(0.1)  # Check every 100ms
        
        if not user_text:
            logger.warning("⚠️ No speech detected")
            print("❌ No speech detected. Please try again.")
            conversation_manager.record_error()
            return True, False
        
        stt_time = time.time() - turn_start
        print(f"📝 You: {user_text} ({stt_time*1000:.0f}ms)")
        
        # Check for exit
        if user_text.strip().lower() in ['quit', 'exit', 'goodbye', 'bye']:
            return False, True
        
        conversation_manager.add_turn("User", user_text)
        
        # Step 2: Generate response
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
        
        # Step 3: Speak response with FULL-DUPLEX monitoring
        tts_start = time.time()
        logger.info("🗣 Speaking response (monitoring for barge-in)...")
        
        tts_handler.speak(response, enable_barge_in=True)
        
        # CRITICAL: Wait for completion OR barge-in
        completed = tts_handler.wait_for_completion(timeout=30.0)
        
        tts_time = time.time() - tts_start
        total_time = time.time() - turn_start
        
        logger.info(f"⏱ Turn timing: STT={stt_time*1000:.0f}ms, "
                   f"LLM={llm_time*1000:.0f}ms, TTS={tts_time*1000:.0f}ms, "
                   f"Total={total_time*1000:.0f}ms")
        
        # Step 4: Handle barge-in
        if tts_handler.is_barge_in_detected():
            print("🎤 You interrupted!")
            
            # CRITICAL: Get the interrupting text from polling STT
            interruption_text = stt_handler.get_barge_in_text()
            
            if interruption_text and len(interruption_text) > 2:
                print(f"📝 You said: {interruption_text}")
                
                # CRITICAL: Wait briefly for complete utterance
                await asyncio.sleep(0.3)
                
                # Get full transcription if available
                final_text = stt_handler.get_barge_in_text()
                if final_text and len(final_text) > len(interruption_text):
                    interruption_text = final_text
                
                # Process interruption as new user input
                logger.info(f"Processing interruption: {interruption_text}")
                conversation_manager.add_turn("User", interruption_text)
                
                # Generate response to interruption
                interruption_response = await llm_handler.process_text_with_history(
                    interruption_text,
                    conversation_manager.get_history()
                )
                
                print(f"🤖 Agent: {interruption_response}")
                conversation_manager.add_turn("Agent", interruption_response)
                
                # Speak response (allow barge-in again)
                tts_handler.speak(interruption_response, enable_barge_in=True)
                tts_handler.wait_for_completion(timeout=30.0)
        
        if total_time > 3.0:
            logger.warning(f"⚠️ Slow turn: {total_time:.1f}s")
        
        return True, False
        
    except Exception as e:
        logger.error(f"❌ Turn error: {e}", exc_info=True)
        conversation_manager.record_error()
        
        if conversation_manager.should_abort():
            print("❌ Too many errors. Exiting.")
            return False, True
        
        print("❌ An error occurred. Continuing...")
        return True, False


async def main():
    """Main conversation loop with full-duplex support."""
    logger.info("🚀 Starting AI Voice Agent (FULL-DUPLEX)...")
    
    stt_handler = None
    tts_handler = None
    
    try:
        print("=" * 50)
        print("🎙 Shamla Tech AI Voice Assistant")
        print("=" * 50)
        print("Initializing FULL-DUPLEX mode...")
        
        # Initialize STT (MUST be first - continuous listening)
        stt_handler = STTHandler(mode="balanced")
        await stt_handler.start_listening()
        logger.info("✅ STT: Continuous listening active")
        
        # Start background polling for barge-in detection
        stt_handler.start_polling_for_barge_in()
        logger.info("✅ STT: Background polling active")
        
        # Initialize LLM
        llm_handler = LLMHandler()
        logger.info("✅ LLM: Ready")
        
        # Initialize TTS (requires STT reference)
        tts_handler = TTSHandler(stt_handler=stt_handler)
        logger.info("✅ TTS: Barge-in monitoring active")
        
        # Initialize conversation
        conversation_manager = ConversationManager(max_history=12)
        conversation_manager.add_turn(
            "System",
            "You are Alex, an AI voice assistant for Shamla Tech. "
            "Be warm, helpful, and conversational. Keep responses concise."
        )
        
        print("✅ System ready! Full-duplex mode active.")
        
        # Welcome message - use non-blocking approach to ensure STT stays active
        welcome = "Hello! I'm Alex from Shamla Tech. How can I help you today?"
        print(f"\n🤖 Agent: {welcome}")
        conversation_manager.add_turn("Agent", welcome)
        
        # Speak welcome with barge-in disabled for initial greeting
        # Then start polling after welcome completes
        tts_handler.speak(welcome, enable_barge_in=False)
        tts_handler.wait_for_completion(timeout=15.0)
        
        # Start background polling for barge-in detection after welcome
        stt_handler.start_polling_for_barge_in()
        logger.info("✅ STT: Background polling started for conversation")
        
        print("\n💡 Tips:")
        print("- Speak naturally - I'm always listening")
        print("- You can interrupt me anytime")
        print("- Say 'quit' or 'goodbye' to exit")
        print()
        
        loop_count = 0
        max_turns = 50
        
        while loop_count < max_turns:
            loop_count += 1
            
            should_continue, should_exit = await handle_conversation_turn(
                stt_handler, llm_handler, tts_handler, conversation_manager
            )
            
            if should_exit:
                print("\n👋 Thank you for calling Shamla Tech!")
                break
            
            if not should_continue:
                break
            
            await asyncio.sleep(0.1)
        
        if loop_count >= max_turns:
            print("\n⏰ Session limit reached.")
        
        # Print stats
        stats = stt_handler.get_performance_stats()
        print(f"\n📊 Session Stats:")
        print(f"   Turns: {conversation_manager.turn_count}")
        print(f"   Transcriptions: {stats['transcription_count']}")
        print(f"   Avg STT Latency: {stats['avg_latency_ms']}ms")
        
        logger.info("✅ Conversation completed")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        
    finally:
        logger.info("🧹 Cleaning up...")
        print("\n🧹 Shutting down...")
        
        try:
            if tts_handler:
                tts_handler.shutdown()
        except Exception as e:
            logger.error(f"TTS cleanup error: {e}")
        
        try:
            if stt_handler:
                stt_handler.stop_polling_for_barge_in()
                await stt_handler.stop_listening()
        except Exception as e:
            logger.error(f"STT cleanup error: {e}")
        
        print("✅ Shutdown complete")


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════╗
║     🎙 Shamla Tech AI Voice Assistant v2.1       ║
║     FULL-DUPLEX MODE - Interrupt Anytime          ║
╚═══════════════════════════════════════════════════╝

✅ Microphone stays active during playback
✅ <150ms barge-in response time
✅ True full-duplex conversation

Starting in 3 seconds...
""")
    
    time.sleep(3)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Startup error: {e}")