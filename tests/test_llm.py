from unittest import TestCase
from unittest.mock import patch, MagicMock
from src.llm_handler import enqueue_text
from src.tts_handler import TTSHandler

class TestLLMHandler(TestCase):
    """Unit tests for the LLM handler functionality."""

    @patch('src.llm_handler.requests.post')
    def test_enqueue_text_success(self, mock_post):
        """Test successful enqueue of text to LLM."""
        # Arrange
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Test response"}
        mock_post.return_value = mock_response

        # Act
        result = enqueue_text("Hello, this is a test message.")

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result['response'], "Test response")
        mock_post.assert_called_once()

    @patch('src.llm_handler.requests.post')
    def test_enqueue_text_failure(self, mock_post):
        """Test enqueue of text to LLM when the request fails."""
        # Arrange
        mock_post.side_effect = Exception("Network error")

        # Act
        result = enqueue_text("This will fail.")

        # Assert
        self.assertIsNone(result)
        mock_post.assert_called_once()

    @patch('src.tts_handler.TTSHandler.speak')
    def test_tts_handler_integration(self, mock_speak):
        """Test integration of TTS handler with LLM."""
        # Arrange
        tts_handler = TTSHandler()
        mock_speak.return_value = True

        # Act
        success = tts_handler.speak("Hello, this is a test for TTS.")

        # Assert
        self.assertTrue(success)
        mock_speak.assert_called_once_with("Hello, this is a test for TTS.")

    def test_invalid_text(self):
        """Test enqueue with invalid text."""
        result = enqueue_text("")
        self.assertIsNone(result)

        result = enqueue_text("   ")
        self.assertIsNone(result)