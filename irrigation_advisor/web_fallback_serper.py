import os
import requests
import google.generativeai as genai


class SerperWebFallbackEngine:
    def __init__(self, gemini_api_key, serper_api_key):
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash")
        self.serper_api_key = serper_api_key

    def search_google(self, query):
        url = "https://google.serper.dev/search"

        payload = {
            "q": query,
            "num": 5
        }

        headers = {
            "X-API-KEY": self.serper_api_key,
            "Content-Type": "application/json"
        }

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            return ""

        data = response.json()

        snippets = []
        for item in data.get("organic", []):
            snippets.append(item.get("snippet", ""))

        return "\n".join(snippets)

    def summarize(self, query, web_data):
        prompt = f"""
A farmer asked:

{query}

Using the following Google search information,
give a clear, practical and simple answer for a farmer.
Avoid technical jargon. Keep it concise.

Web Information:
{web_data}
"""

        response = self.model.generate_content(prompt)
        return response.text

    def query(self, query):
        web_data = self.search_google(query)

        if not web_data.strip():
            return "Sorry, I could not find reliable information online."

        return self.summarize(query, web_data)