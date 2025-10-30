from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch, AsyncMock
from src.stt_handler import enqueue_text
from src.llm_handler import query_gemini
from src.tts_handler import RealTimeTTSHandler

class TestIntegration(IsolatedAsyncioTestCase):
    def setUp(self):
        self.stt_handler = None  # Initialize STT handler if needed
        self.llm_handler = None  # Initialize LLM handler if needed
        self.tts_handler = RealTimeTTSHandler()  # Initialize TTS handler

    @patch('src.llm_handler.query_gemini', new_callable=AsyncMock)
    @patch('src.stt_handler.enqueue_text', new_callable=AsyncMock)
    async def test_integration(self, mock_enqueue_text, mock_query_gemini):
        # Mock responses
        mock_query_gemini.return_value = {"response": "This is a test response."}
        mock_enqueue_text.return_value = None

        # Simulate STT processing
        test_audio_input = "Hello, this is a test message."
        await enqueue_text(test_audio_input)

        # Simulate LLM processing
        response = await query_gemini(test_audio_input)

        # Simulate TTS processing
        tts_output = await self.tts_handler.speak(response["response"])

        # Assertions
        self.assertIsNotNone(response)
        self.assertIn("response", response)
        self.assertEqual(response["response"], "This is a test response.")
        self.assertTrue(tts_output)  # Assuming speak returns True on success

    async def tearDown(self):
        # Clean up resources if necessary
        pass

if __name__ == '__main__':
    import unittest
    unittest.main()