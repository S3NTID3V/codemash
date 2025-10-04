import google.generativeai as genai
import os
import json

class GeminiClient:
    """
    A client for interacting with the Google Gemini API.
    Includes mock responses for testing.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        if not api_key or api_key == "YOUR_GEMINI_API_KEY":
            if api_key != "DUMMY_KEY_FOR_TESTING":
                raise ValueError("Gemini API key is not configured.")

        if self.api_key != "DUMMY_KEY_FOR_TESTING":
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-pro')

    def generate_response(self, prompt: str) -> str:
        """
        Generates a response. Returns a mock response if using a dummy key.
        """
        if self.api_key == "DUMMY_KEY_FOR_TESTING":
            return self._get_mock_response(prompt)

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"An error occurred while communicating with the Gemini API: {e}"

    def _get_mock_response(self, prompt: str) -> str:
        """
        Returns a deterministic mock response based on the prompt content for testing.
        """
        if "generate the next logical task" in prompt:
            return json.dumps({
                "task_description": "Mock task: Implement the user login page.",
                "coding_prompt": "Create a new Streamlit page for user login with username and password fields."
            })
        elif "A task was marked as completed" in prompt:
            return json.dumps({
                "verified": True,
                "feedback": "This looks great. Well done."
            })
        return "This is a generic mock response for other queries."


def get_gemini_client(api_key: str = None):
    """
    Factory function to create and get a GeminiClient instance.
    """
    if api_key:
        return GeminiClient(api_key)

    api_key_env = os.getenv("GEMINI_API_KEY")
    if api_key_env:
        return GeminiClient(api_key_env)

    raise ValueError("API Key for Gemini not found or provided.")