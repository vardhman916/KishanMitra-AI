import fitz  # PyMuPDF
import faiss
import numpy as np
import google.generativeai as genai
from sentence_transformers import SentenceTransformer


class SprinklerRAG:
    def __init__(self, pdf_path, gemini_api_key):
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
        chunk_size = 700

        overlap = 150  # 🔥 important

        for i in range(0, len(full_text), chunk_size - overlap):
            chunks.append(full_text[i:i + chunk_size])

        return chunks

    # ------------------------------
    # Build FAISS index
    # ------------------------------
    def _build_faiss_index(self):
        embeddings = self.embed_model.encode(self.text_chunks)
        dimension = embeddings.shape[1]

        index = faiss.IndexFlatL2(dimension)
        index.add(np.array(embeddings))

        return index

    # ------------------------------
    # Retrieve + Generate Answer
    # ------------------------------
    def query(self, question, top_k=3):
        # ---- Step 1: Retrieve relevant chunks ----
        question_embedding = self.embed_model.encode([question])
        distances, indices = self.index.search(np.array(question_embedding), top_k)

        retrieved_chunks = []
        for idx in indices[0]:
            retrieved_chunks.append(self.text_chunks[idx])

        context = "\n\n".join(retrieved_chunks)

        # ---- Step 2: Build Gemini Prompt ----
        prompt = f"""
You are an expert irrigation advisor helping Indian farmers.

Use ONLY the information provided in the context below.
If the answer is not present in the context, say:
"I do not have enough information in the document."

Context:
{context}

Farmer Question:
{question}

Provide a clear, structured, and easy-to-understand answer.
"""

        # ---- Step 3: Call Gemini ----
        response = self.llm.generate_content(prompt)

        return response.text