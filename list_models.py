import google.generativeai as genai
import os

# --- Get API Key ---
# This is a placeholder. In a real scenario, you would replace this with your actual key.
# For the purpose of listing models, a valid key is required.
# I will inform the user about this.
api_key = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")

if api_key == "YOUR_GEMINI_API_KEY":
    print("Please set the GEMINI_API_KEY environment variable to your actual API key.")
else:
    genai.configure(api_key=api_key)

    print("Available models:")
    for model in genai.list_models():
        if 'generateContent' in model.supported_generation_methods:
            print(model.name)