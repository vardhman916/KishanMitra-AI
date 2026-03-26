import os
from typing import Optional, List
import json

# If you already have a Gemini wrapper tool, you can plug it here instead.
# This version uses google-generativeai directly.
import google.generativeai as genai


class FertAIExplainerToolV1:
    """
    Takes fertilizer recommendation table (as HTML) + user inputs
    and produces a farmer-friendly explanation in English.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.5-flash"):
        api_key = api_key or os.getenv("GEMINI_API_KEY3")
        if not api_key:
            raise ValueError("Missing GEMINI_API_KEY in environment (.env)")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    @staticmethod
    def _clean_table_text(table_text: str) -> str:
        # Reduce token usage: collapse whitespace, cut very long text
        t = " ".join((table_text or "").split())
        # keep it bounded
        if len(t) > 6000:
            t = t[:6000] + "..."
        return t

    def explain(
        self,
        crop_group: str,
        crop_name: str,
        condition: str,
        plants: float,
        area: float,
        mode: str,
        html_table: str,
    ) -> str:
        table_text = self._clean_table_text(html_table)

        prompt = f"""
You are an experienced Indian agriculture extension officer.

Farmer selected:
- Crop group: {crop_group}
- Crop: {crop_name}
- Condition: {condition}
- Number of plants: {plants}
- Area: {area}
- Mode: {mode} (blanket or soil_test)

Below is the exact Fertilizer Recommendation table HTML from an official calculator.

TASK:
1) Explain what the table means in simple farmer-friendly language.
2) Give a clear "Action Plan" as steps: what to apply, when to apply.
3) Mention totals clearly.
4) Give 3 practical tips (mixing, watering, avoid loss, timing).
5) If any values look zero/unusual, warn the farmer.

Rules:
- Do NOT invent any numbers not present in table.
- If unsure, say "Not available in table".
- Output in short bullets. Keep it crisp.

TABLE HTML:
{table_text}
"""

        resp = self.model.generate_content(prompt)
        return (resp.text or "").strip()
