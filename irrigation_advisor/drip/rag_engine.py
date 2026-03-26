import fitz  # PyMuPDF
import faiss
import numpy as np
import google.generativeai as genai
from sentence_transformers import SentenceTransformer


class DripRAG:
    def __init__(self, pdf_path, gemini_api_key):
        if not gemini_api_key or not str(gemini_api_key).strip():
            raise ValueError(
                "Gemini API key is missing. Set GEMINI_API_KEY2 in your environment/.env file."
            )

        # -------- Gemini Setup --------
        genai.configure(api_key=gemini_api_key)
        self.llm = genai.GenerativeModel("gemini-2.5-flash")

        # -------- Embedding Model --------
        self.embed_model = SentenceTransformer("all-MiniLM-L6-v2")

        # -------- Load + Index --------
        self.text_chunks = self._load_and_chunk(pdf_path)
        self.index = self._build_faiss_index()

    # ------------------------------
    # Load and Chunk PDF
    # ------------------------------
    def _load_and_chunk(self, pdf_path):
        doc = fitz.open(pdf_path)
        full_text = ""

        for page in doc:
            full_text += page.get_text()

        chunks = []
        chunk_size = 900     # increased size
        overlap = 200        # overlap for semantic continuity

        for i in range(0, len(full_text), chunk_size - overlap):
            chunk = full_text[i:i + chunk_size].strip()
            if len(chunk) > 100:  # avoid tiny noisy chunks
                chunks.append(chunk)

        return chunks

    # ------------------------------
    # Build FAISS index
    # ------------------------------
    def _build_faiss_index(self):
        embeddings = self.embed_model.encode(self.text_chunks)
        embeddings = np.array(embeddings).astype("float32")

        dimension = embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(embeddings)

        return index

    # ------------------------------
    # Expand Query (Semantic Boost)
    # ------------------------------
    def _expand_query(self, question):
        synonyms_map = {
            "advantages": "advantages benefits merits features importance uses",
            "benefits": "benefits advantages merits gains",
            "disadvantages": "disadvantages demerits limitations drawbacks",
            "cost": "cost price expense investment installation amount",
            "maintenance": "maintenance care servicing upkeep management",
            "water saving": "water saving efficiency water conservation",
            "yield": "yield production output crop increase"
        }

        expanded = question.lower()

        for word, expansion in synonyms_map.items():
            if word in expanded:
                expanded += " " + expansion

        return expanded

    # ------------------------------
    # Retrieve + Generate Answer
    # ------------------------------
    def query(self, question, top_k=5):
        # ---- Step 1: Expand question ----
        expanded_question = self._expand_query(question)

        # ---- Step 2: Retrieve relevant chunks ----
        question_embedding = self.embed_model.encode([expanded_question])
        question_embedding = np.array(question_embedding).astype("float32")

        distances, indices = self.index.search(question_embedding, top_k)

        retrieved_chunks = []
        for idx in indices[0]:
            if idx < len(self.text_chunks):
                retrieved_chunks.append(self.text_chunks[idx])

        context = "\n\n".join(retrieved_chunks)

        # ---- Step 3: Gemini Prompt ----
        prompt = f"""
You are an expert drip irrigation advisor helping Indian farmers.

Use ONLY the information provided in the context below.
If the answer is not present in the context, say:
"I do not have enough information in the document."

Context:
{context}

Farmer Question:
{question}

Provide:
- Clear explanation
- Bullet points if needed
- Simple farmer-friendly language
- No assumptions outside context
"""

        # ---- Step 4: Generate response ----
        try:
            response = self.llm.generate_content(prompt)
        except Exception as exc:
            msg = str(exc)
            if "invalid_grant" in msg or "Getting metadata from plugin failed" in msg:
                raise RuntimeError(
                    "Gemini authentication failed. Use a valid API key (GEMINI_API_KEY2) "
                    "and avoid expired/invalid Google ADC credentials."
                ) from exc
            raise

        return response.text
