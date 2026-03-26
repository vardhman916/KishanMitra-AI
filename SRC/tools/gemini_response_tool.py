#SRC/tools/gemini_response_tool.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()


def _j(d: Dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False)


def _build_prompt(
    query: str,
    intent: str,
    evidence_lines: List[str],
    schemes: Optional[List[Dict[str, str]]] = None,
    sources: Optional[List[str]] = None,
) -> str:
    prompt = f"""
You are an agriculture assistant for Indian farmers.

RULES (VERY IMPORTANT):
- Use ONLY the information provided below.
- Do NOT add new facts.
- Do NOT guess.
- If information is insufficient, clearly say so.
- Be simple and practical.

Farmer Question:
{query}

Detected Intent:
{intent}
""".strip()

    if schemes:
        prompt += "\n\nAvailable Scheme Options (from search results):\n"
        for i, s in enumerate(schemes, 1):
            prompt += f"{i}. {s.get('name')}\n   Link: {s.get('url')}\n   Info: {s.get('evidence')}\n"

    if evidence_lines:
        prompt += "\n\nExtracted Evidence from Pages:\n"
        for e in evidence_lines:
            prompt += f"- {e}\n"

    if sources:
        prompt += "\n\nSources:\n"
        for s in sources:
            prompt += f"- {s}\n"

    prompt += """

Now produce the FINAL ANSWER in this format:

1) Short Answer (2–3 lines, farmer-friendly)
2) Details (bullet points)
3) Important Links
4) What farmer should do next

Keep language simple and avoid long paragraphs.
"""
    return prompt.strip()


@dataclass
class GeminiResponseTool:
    """
    Final answer generator using Gemini.
    Input = summary/evidence already extracted by your browsing tool.
    """

    name: str = "gemini_response_tool"
    model_name: str = "gemini-2.5-flash"

    def run(self, inputs: Dict[str, Any]) -> str:
        api_key = os.getenv("GEMINI_API_KEY6", "").strip()
        if not api_key:
            return _j({
                "tool": self.name,
                "status": "error",
                "message": "GEMINI_API_KEY not set in .env",
                "missing_data": ["set_GEMINI_API_KEY"],
                "data": {}
            })

        query = inputs.get("query")
        if not query:
            return _j({
                "tool": self.name,
                "status": "missing_data",
                "message": "query is required.",
                "missing_data": ["query"],
                "data": {}
            })

        intent = inputs.get("intent", "general")
        evidence_lines = inputs.get("evidence_lines", []) or []
        schemes = inputs.get("schemes")
        sources = inputs.get("sources", []) or []

        genai.configure(api_key=api_key)
        prompt = _build_prompt(
            query=query,
            intent=intent,
            evidence_lines=evidence_lines,
            schemes=schemes,
            sources=sources
        )

        try:
            model = genai.GenerativeModel(self.model_name)
            resp = model.generate_content(prompt)
            answer = (resp.text or "").strip()

            return _j({
                "tool": self.name,
                "status": "ok",
                "message": "Final answer generated using Gemini (grounded in evidence).",
                "missing_data": [],
                "data": {"answer": answer},
                "sources": sources
            })

        except Exception as e:
            return _j({
                "tool": self.name,
                "status": "error",
                "message": f"Gemini generation failed: {e}",
                "missing_data": ["gemini_generation_failed"],
                "data": {}
            })
