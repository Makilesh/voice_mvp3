# llm_handler.py - OPTIMIZED VERSION (Faster, No Quality Loss) lossss
import os
import logging
import asyncio
import httpx
import random
import re
from dotenv import load_dotenv
from typing import Dict

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConversationalPersonality:
    """Manages personality traits and natural language variations."""
    
    FILLERS = {
        'thinking': ['Um,', 'Well,', 'Let me think,', 'Hmm,'],
        'transition': ['So,', 'Actually,', 'Right,'],
        'agreement': ['Absolutely,', 'Yeah,', 'For sure,']
    }
    
    ERROR_RESPONSES = [
        "Oops, I'm having a bit of trouble. Give me a moment?",
        "Hmm, something's not working right. Can you try again?",
        "I'm hitting a snag here. Could you rephrase that?"
    ]
    
    CONTINUERS = [
        "Anything else I can help with?",
        "What else can I do for you?",
        "Does that help?"
    ]
    
    @staticmethod
    def add_natural_pause(text: str, probability: float = 0.12) -> str:
        """Adds occasional filler words (reduced frequency)."""
        if random.random() > probability or not text:
            return text
        
        category = random.choice(list(ConversationalPersonality.FILLERS.keys()))
        filler = random.choice(ConversationalPersonality.FILLERS[category])
        
        if category in ['thinking', 'transition']:
            return f"{filler} {text}"
        else:
            sentences = text.split('. ')
            if len(sentences) > 1:
                return '. '.join(sentences[:1]) + f" {filler}. " + '. '.join(sentences[1:])
        return text
    
    @staticmethod
    def get_random_error() -> str:
        return random.choice(ConversationalPersonality.ERROR_RESPONSES)
    
    @staticmethod
    def add_continuer(text: str, probability: float = 0.25) -> str:
        """Occasionally adds follow-up question."""
        if random.random() > probability or '?' in text:
            return text
        continuer = random.choice(ConversationalPersonality.CONTINUERS)
        return f"{text} {continuer}"


class SentimentAnalyzer:
    """Simple sentiment detection for tone adjustment."""
    
    POSITIVE_WORDS = ['great', 'awesome', 'excellent', 'love', 'fantastic', 'happy', 'thanks', 'perfect']
    NEGATIVE_WORDS = ['frustrated', 'annoyed', 'upset', 'confused', 'problem', 'issue', 'broken', 'help']
    URGENT_WORDS = ['urgent', 'asap', 'quickly', 'immediately', 'emergency', 'now']
    
    @staticmethod
    def analyze(text: str) -> Dict:
        """Returns sentiment and intensity."""
        text_lower = text.lower()
        
        positive_count = sum(1 for word in SentimentAnalyzer.POSITIVE_WORDS if word in text_lower)
        negative_count = sum(1 for word in SentimentAnalyzer.NEGATIVE_WORDS if word in text_lower)
        urgent_count = sum(1 for word in SentimentAnalyzer.URGENT_WORDS if word in text_lower)
        
        if urgent_count > 0:
            sentiment = 'urgent'
        elif negative_count > positive_count:
            sentiment = 'negative'
        elif positive_count > negative_count:
            sentiment = 'positive'
        else:
            sentiment = 'neutral'
        
        return {
            'sentiment': sentiment,
            'intensity': max(positive_count, negative_count, urgent_count),
            'has_question': '?' in text
        }


class LLMHandler:
    """Handles text processing with optimized async calls."""
    
    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            logger.error("❌ OPENAI_API_KEY not found")
            raise ValueError("OpenAI API key required")
        
        self.base_url = "https://api.openai.com/v1/chat/completions"
        self.personality = ConversationalPersonality()
        self.sentiment_analyzer = SentimentAnalyzer()
        
        # Async HTTP client (reusable connection pool)
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=5.0),  # Reduced from 15s
            limits=httpx.Limits(max_keepalive_connections=5)
        )
        
        self.interaction_count = 0
        
        logger.info("🤖 LLM Handler initialized (optimized mode)")
    
    async def process_text(self, text: str) -> str:
        """Process text with sentiment-aware response (FAST mode)."""
        try:
            sentiment = self.sentiment_analyzer.analyze(text)
            processed_text = self._preprocess_transcription(text)
            system_prompt = self._build_dynamic_system_prompt(sentiment)
            
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": processed_text}
                ],
                "temperature": self._get_dynamic_temperature(sentiment),
                "max_tokens": 100,  # ⚡ REDUCED from 150 (voice should be concise)
                "top_p": 0.9,
                "frequency_penalty": 0.3,
                "presence_penalty": 0.2
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            logger.info(f"🤖 Processing [{sentiment['sentiment']}]: {text[:50]}...")
            
            # CRITICAL: Use async HTTP client
            response = await self.client.post(
                self.base_url, 
                json=payload, 
                headers=headers
            )
            response.raise_for_status()
            
            result = response.json()
            response_text = result['choices'][0]['message']['content'].strip()
            
            # Post-process
            response_text = self._post_process_response(response_text, sentiment)
            
            logger.info(f"📝 Response: {response_text[:100]}...")
            return response_text
            
        except httpx.TimeoutException:
            logger.error("❌ API timeout")
            return "I'm sorry, my response is taking too long. Could you try again?"
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ API error {e.response.status_code}")
            return self.personality.get_random_error()
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            return self.personality.get_random_error()

    async def process_text_with_history(self, text: str, conversation_history: list) -> str:
        """Process with context awareness (optimized for voice)."""
        try:
            self.interaction_count += 1
            
            sentiment = self.sentiment_analyzer.analyze(text)
            processed_text = self._preprocess_transcription(text)
            
            # Build messages
            system_prompt = self._build_dynamic_system_prompt(sentiment, has_history=True)
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add conversation history (last 6 exchanges for speed)
            for i, exchange in enumerate(conversation_history[-6:]):
                if exchange.startswith("System:"):
                    continue  # Skip system messages in history
                
                if exchange.startswith("User:"):
                    messages.append({"role": "user", "content": exchange[5:].strip()})
                elif exchange.startswith("Agent:"):
                    messages.append({"role": "assistant", "content": exchange[6:].strip()})
            
            messages.append({"role": "user", "content": processed_text})
            
            payload = {
                "model": "gpt-4o-mini",
                "messages": messages,
                "temperature": self._get_dynamic_temperature(sentiment),
                "max_tokens": 120,  # ⚡ REDUCED from 200 (faster without quality loss)
                "top_p": 0.9,
                "frequency_penalty": 0.35,  # Higher to avoid repetition
                "presence_penalty": 0.25
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            logger.info(f"🤖 Processing with history [{sentiment['sentiment']}]")
            
            # Async call
            response = await self.client.post(
                self.base_url,
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            result = response.json()
            response_text = result['choices'][0]['message']['content'].strip()
            
            response_text = self._post_process_response(response_text, sentiment)
            
            return response_text
            
        except Exception as e:
            logger.error(f"❌ Error with history: {e}")
            return self.personality.get_random_error()

    def _preprocess_transcription(self, text: str) -> str:
        """Pre-process transcription."""
        if not text:
            return text
        
        processed = text
        
        # Fix company name
        shamla_pattern = re.compile(r'\b(sham[bl]a\s*tech?|sham[bl]a)\b', re.IGNORECASE)
        processed = shamla_pattern.sub('Shamla Tech', processed)
        
        # Common contractions
        contractions = {
            r'\bwanna\b': 'want to',
            r'\bgonna\b': 'going to',
            r'\bgotta\b': 'got to',
        }
        
        for pattern, replacement in contractions.items():
            processed = re.sub(pattern, replacement, processed, flags=re.IGNORECASE)
        
        return processed.strip()

    def _build_dynamic_system_prompt(self, sentiment: Dict, has_history: bool = False) -> str:
        """Creates adaptive system prompts (OPTIMIZED for voice)."""
        
        base = """You are Alex, a warm AI voice assistant for Shamla Tech.

VOICE GUIDELINES:
- Keep responses SHORT (1-2 sentences for simple queries, 3 max for complex)
- Use contractions (I'm, you're, that's)
- Be conversational and natural
- No lists or bullet points (this is voice!)

About Shamla Tech:
- AI solutions, blockchain, cryptocurrency services
- Cutting-edge tech team

CRITICAL: Your response will be spoken aloud. Keep it concise and natural."""
        
        # Tone modifiers (shortened)
        if sentiment['sentiment'] == 'urgent':
            tone = "\nTONE: User seems urgent - be direct and efficient."
        elif sentiment['sentiment'] == 'negative':
            tone = "\nTONE: User seems frustrated - be patient and reassuring."
        elif sentiment['sentiment'] == 'positive':
            tone = "\nTONE: User is happy - match their energy!"
        else:
            tone = "\nTONE: Standard friendly conversation."
        
        history_note = ""
        if has_history:
            history_note = "\nNote: Reference previous conversation naturally when relevant."
        
        return base + tone + history_note
    
    def _get_dynamic_temperature(self, sentiment: Dict) -> float:
        """Adjusts creativity based on context."""
        if sentiment['sentiment'] == 'urgent':
            return 0.6  # More focused
        elif sentiment['sentiment'] == 'positive':
            return 0.85  # More playful
        else:
            return 0.75  # Balanced
    
    def _post_process_response(self, response_text: str, sentiment: Dict) -> str:
        """Enhances response with natural touches."""
        if not response_text:
            return response_text
        
        # Clean prefixes
        cleaned = self._clean_prefixes(response_text)
        
        # Add occasional filler (less likely for urgent)
        filler_prob = 0.03 if sentiment['sentiment'] == 'urgent' else 0.12
        cleaned = self.personality.add_natural_pause(cleaned, filler_prob)
        
        # Add continuer
        continuer_prob = 0.1 if sentiment['has_question'] else 0.25
        cleaned = self.personality.add_continuer(cleaned, continuer_prob)
        
        # Clean spacing and capitalization
        cleaned = " ".join(cleaned.split())
        if cleaned and cleaned[0].islower():
            cleaned = cleaned[0].upper() + cleaned[1:]
        
        return cleaned.strip()
    
    def _clean_prefixes(self, text: str) -> str:
        """Remove bot-like prefixes."""
        prefixes = [
            "agent:", "assistant:", "ai:", "alex:", "bot:"
        ]
        
        text_lower = text.lower()
        for prefix in prefixes:
            if text_lower.startswith(prefix):
                return text[len(prefix):].strip()
        
        return text
    
    async def shutdown(self):
        """Close HTTP client."""
        try:
            await self.client.aclose()
            logger.info("✅ LLM Handler shutdown")
        except Exception as e:
            logger.error(f"❌ Shutdown error: {e}")


async def main():
    """Example usage."""
    llm = LLMHandler()
    response = await llm.process_text("Hello, tell me about Shamla Tech")
    print(f"Response: {response}")
    await llm.shutdown()

if __name__ == "__main__":
    asyncio.run(main())