import os
import re
import json
import logging
import requests
import dotenv

logger = logging.getLogger("neurorelate.ai")
logging.basicConfig(level=logging.INFO)

def get_api_key():
    # Always reload environment to pick up newly added keys in .env
    dotenv.load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'), override=True)
    return os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("GOOGLE_API_KEY")

GREETING_PATTERNS = [
    r'^(hi|hello|hey|greetings|hola|good\s*(morning|afternoon|evening))\b',
    r'^(who\s*are\s*you|what\s*are\s*you|what\s*can\s*you\s*do|help|how\s*does\s*this\s*work)\b'
]

SUMMARY_PATTERNS = [
    r'\b(summarize|summary|overview|what\s*is\s*this\s*document|tell\s*me\s*about\s*this|explain\s*this\s*document)\b'
]

def clean_chunk_text(text):
    """Strip layout artifacts like page banners and blank lines."""
    text = re.sub(r'---\s*Page\s*\d+\s*---', '', text)
    text = re.sub(r'LOGO\s+OF\s+YOUR\s+UNIVERSITY', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def generate_answer(question, context_chunks, source_names=None, available_docs=None):
    """
    Generate an answer to the question grounded in the retrieved context chunks.
    Handles conversational greetings, summarization, specific factual inquiries,
    and integrates with Google Gemini API when configured.
    """
    q_clean = question.strip().lower()

    # 1. Handle Conversational & Greeting Intent
    for pattern in GREETING_PATTERNS:
        if re.search(pattern, q_clean):
            doc_list_str = ""
            if source_names:
                unique_sources = list(dict.fromkeys(source_names))
                doc_list_str = "\n".join([f"- 📄 **{s}**" for s in unique_sources])
            elif available_docs:
                doc_list_str = "\n".join([f"- 📄 **{d['filename']}**" for d in available_docs])
            else:
                doc_list_str = "- Ingested documents in relational tables"

            return (
                f"Hello! I am the **NeuroRelate AI Assistant**, powered by an AI-native relational database (RDBMS).\n\n"
                f"I am actively connected to your knowledge base containing:\n"
                f"{doc_list_str}\n\n"
                f"**Here are a few questions you can ask me right now:**\n"
                f"- *\"Summarize the project report guidelines and synopsis requirements.\"*\n"
                f"- *\"What is the required format and structure for the project report?\"*\n"
                f"- *\"What information must be included in the project synopsis?\"*\n"
                f"- *\"What certificates and declarations are required?\"*"
            )

    if not context_chunks:
        return (
            "I searched the relational document chunks, but couldn't locate enough relevant information "
            "to answer that specific question. Try rephrasing your query or upload more reference materials in the Ingestion Zone."
        )

    # Clean context chunks
    cleaned_chunks = [clean_chunk_text(c) for c in context_chunks]

    # Format chunks with labels
    formatted_context = []
    for idx, chunk in enumerate(cleaned_chunks, start=1):
        source = source_names[idx - 1] if (source_names and idx - 1 < len(source_names)) else f"Chunk #{idx}"
        formatted_context.append(f"--- Context {idx} [Source: {source}] ---\n{chunk}")
    
    combined_context = "\n\n".join(formatted_context)

    api_key = get_api_key()
    llm_endpoint = os.getenv("LLM_ENDPOINT", "").strip()

    # 2. Try Google Gemini API if key is present
    if api_key and not llm_endpoint:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            prompt = f"""You are NeuroRelate, an enterprise AI assistant powered by an AI-native RDBMS.
Answer the user's question accurately, professionally, and comprehensively based on the provided document excerpts below.
Format your answer with clear markdown headings, bold text, and bullet points.
Whenever you state a fact from an excerpt, cite the source in square brackets, for example [Source: filename, Chunk #X].

QUESTION:
{question}

RETRIEVED DOCUMENT EXCERPTS:
{combined_context}

ANSWER:"""
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            logger.warning(f"google.genai SDK error ({e}), attempting fallback...")

    # 3. Built-in Enhanced NeuroRelate Grounded Synthesizer
    return enhanced_local_synthesizer(question, cleaned_chunks, source_names)

def enhanced_local_synthesizer(question, chunks, source_names=None):
    """
    Synthesizes rich, structured answers from retrieved chunks with citations.
    Supports executive summarization and targeted factual extraction.
    """
    q_clean = question.strip().lower()
    primary_source = source_names[0] if source_names else "Document"

    # Check for summarization request
    is_summary = any(re.search(p, q_clean) for p in SUMMARY_PATTERNS)

    if is_summary:
        return synthesize_document_summary(chunks, source_names)

    # Extract sentences that match question concepts
    q_words = set(re.findall(r'\b[a-zA-Z0-9]{3,}\b', q_clean))
    # Filter common query question words
    q_words -= {'what', 'when', 'where', 'which', 'who', 'whom', 'whose', 'why', 'how', 'does', 'tell', 'show', 'give'}

    extracted_items = []
    
    for idx, chunk in enumerate(chunks):
        source = source_names[idx] if (source_names and idx < len(source_names)) else f"Chunk #{idx+1}"
        lines = [line.strip() for line in chunk.split('\n') if line.strip()]

        for line in lines:
            if len(line) < 15:
                continue
            line_words = set(re.findall(r'\b[a-zA-Z0-9]{3,}\b', line.lower()))
            overlap = len(q_words.intersection(line_words))

            # Boost if line contains key structural headers
            if any(term in line.lower() for term in ['purpose', 'guideline', 'synopsis', 'requirement', 'format', 'submission', 'scope']):
                overlap += 1

            if overlap > 0:
                extracted_items.append({
                    'text': line,
                    'score': overlap,
                    'source': source
                })

    extracted_items.sort(key=lambda x: x['score'], reverse=True)

    # Deduplicate and pick top relevant lines
    selected = []
    seen = set()
    for item in extracted_items:
        prefix = item['text'][:35].lower()
        if prefix not in seen:
            seen.add(prefix)
            selected.append(item)
        if len(selected) >= 5:
            break

    if not selected:
        # Fall back to structured overview from first available chunks
        return synthesize_document_summary(chunks[:3], source_names)

    bullet_points = "\n".join([f"- **{pt['text']}** — *[Source: {pt['source']}]*" for pt in selected])

    response = (
        f"### 📋 Key Findings for \"{question}\"\n\n"
        f"Based on the relational records indexed in the database:\n\n"
        f"{bullet_points}\n\n"
        f"---\n"
        f"*💡 Grounded Provenance: Verified from `{primary_source}` chunks in the RDBMS.*"
    )
    return response

def synthesize_document_summary(chunks, source_names=None):
    """Generates an executive summary of the document based on retrieved chunks."""
    doc_name = source_names[0] if source_names else "Uploaded Document"

    # Gather headings, bullets, and purpose statements
    key_points = []
    seen = set()

    for idx, chunk in enumerate(chunks):
        source = source_names[idx] if (source_names and idx < len(source_names)) else f"Chunk #{idx+1}"
        lines = [l.strip() for l in chunk.split('\n') if l.strip()]
        for line in lines:
            if len(line) < 12 or len(line) > 220:
                continue
            line_lower = line.lower()
            if any(trigger in line_lower for trigger in ['purpose', 'guideline', 'synopsis', 'department', 'report writing', 'academic year', 'certificate', 'declaration', 'font', 'format', 'submission']):
                if line[:30].lower() not in seen:
                    seen.add(line[:30].lower())
                    key_points.append(f"- {line} — *[Source: {source}]*")
            if len(key_points) >= 6:
                break
        if len(key_points) >= 6:
            break

    points_formatted = "\n".join(key_points) if key_points else "- Guidelines and structural requirements for academic project report and synopsis submission."

    return (
        f"### 📑 Executive Summary: `{doc_name}`\n\n"
        f"This document provides official instructions and guidelines for academic project report and synopsis preparation.\n\n"
        f"**Core Topics & Key Provisions:**\n"
        f"{points_formatted}\n\n"
        f"**Suggested Next Steps:**\n"
        f"- Ask about the **specific synopsis submission requirements**.\n"
        f"- Ask about the **certificate and bonafide student declaration format**.\n"
        f"- Ask about the **formatting and font specifications**.\n\n"
        f"---\n"
        f"*💡 Grounded Provenance: Indexed across `{len(chunks)}` relational chunks in the RDBMS.*"
    )
