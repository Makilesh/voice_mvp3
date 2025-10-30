from unittest import TestCase
from unittest.mock import patch, MagicMock
from src.tts_handler import TTSHandler

class TestTTSHandler(TestCase):
    """Unit tests for the TTS handler integrating RealTimeTTS Orpheus model."""

    def setUp(self):
        """Set up the TTS handler for testing."""
        self.tts_handler = TTSHandler()

    @patch('src.tts_handler.RealTimeTTS')
    def test_initialize_orpheus(self, mock_realtime_tts):
        """Test initialization of the Orpheus engine."""
        mock_realtime_tts.return_value = MagicMock()
        self.tts_handler.initialize_orpheus()
        mock_realtime_tts.assert_called_once_with(model='orpheus')

    def test_process_text_with_emotive_tags(self):
        """Test processing text with emotive tags."""
        text = "Hello, <happy>world</happy>!"
        expected_output = "Hello, world!"  # Assuming the emotive tags are stripped
        result = self.tts_handler.process_text(text)
        self.assertEqual(result, expected_output)

    @patch('src.tts_handler.RealTimeTTS')
    def test_synthesize_speech(self, mock_realtime_tts):
        """Test speech synthesis from text."""
        mock_tts_instance = mock_realtime_tts.return_value
        mock_tts_instance.synthesize.return_value = "audio_data"
        
        text = "This is a test."
        audio_data = self.tts_handler.synthesize_speech(text)
        
        mock_tts_instance.synthesize.assert_called_once_with(text)
        self.assertEqual(audio_data, "audio_data")

    def tearDown(self):
        """Clean up after tests."""
        self.tts_handler = None

if __name__ == '__main__':
    unittest.main()