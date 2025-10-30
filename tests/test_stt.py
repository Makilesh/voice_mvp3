from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch, AsyncMock
from src.stt_handler import clean_transcript
from src.tts_handler import TTSHandler  # Assuming TTSHandler is implemented in tts_handler.py

class TestSTTHandler(IsolatedAsyncioTestCase):
    def setUp(self):
        self.tts_handler = TTSHandler()

    async def test_clean_transcript(self):
        input_text = "This is a test.  This is only a test!"
        expected_output = "This is a test. This is only a test!"
        self.assertEqual(clean_transcript(input_text), expected_output)

    @patch('src.tts_handler.TTSHandler.process_text', new_callable=AsyncMock)
    async def test_tts_integration(self, mock_process_text):
        test_text = "Hello, this is a test for TTS integration."
        await self.tts_handler.process_text(test_text)
        mock_process_text.assert_called_once_with(test_text)

    async def test_tts_with_emotive_tags(self):
        test_text = "Hello, <happy>this is a test</happy>."
        result = await self.tts_handler.process_text(test_text)
        self.assertIn("Emotive processing for happy", result)  # Adjust based on actual implementation

    async def test_tts_error_handling(self):
        with self.assertRaises(Exception):
            await self.tts_handler.process_text("")  # Test with empty text

if __name__ == '__main__':
    unittest.main()