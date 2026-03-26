import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY1"))

model = genai.GenerativeModel("gemini-2.5-flash")  
# If you are using 2.0 Flash, change accordingly:
# model = genai.GenerativeModel("gemini-2.0-flash")

def generate_pest_summary(pest_data):

    prompt = f"""
    You are an agricultural expert helping farmers in English.

    Crop: {pest_data['crop']}
    Pest: {pest_data['pest']}
    Symptoms: {pest_data['symptoms']}
    Control: {pest_data['control']}

    Explain in simple farmer-friendly language.

    Format:
    🧠 Simple Summary (5-7 lines)

    🔍 Symptoms (easy explanation)

    🛡️ Control Measures (clear steps)

    Keep response short and practical.
    """

    response = model.generate_content(prompt)

    return response.text