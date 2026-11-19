import os
import fitz  # PyMuPDF
from datetime import datetime
from database import get_db

CHUNK_SIZE = 500  # characters per chunk, simple split

def extract_text(file_path, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    if ext == 'pdf':
        doc = fitz.open(file_path)
        text = ''
        for page in doc:
            text += page.get_text()
        return text
    else:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

def chunk_text(text):
    # Simple chunking by size
    chunks = []
    for i in range(0, len(text), CHUNK_SIZE):
        chunks.append(text[i:i + CHUNK_SIZE])
    return chunks

def process_document(file_path, filename):
    """Extract text, store document and its chunks in the DB."""
    text = extract_text(file_path, filename)
    db = get_db()
    cursor = db.cursor()
    # Insert document metadata
    cursor.execute(
        "INSERT INTO documents (filename, upload_date, extracted_text) VALUES (%s, %s, %s)",
        (filename, datetime.now(), text)
    )
    doc_id = cursor.lastrowid
    # Chunk and insert
    chunks = chunk_text(text)
    for idx, chunk in enumerate(chunks, start=1):
        cursor.execute(
            "INSERT INTO document_chunks (document_id, chunk_text, chunk_number) VALUES (%s, %s, %s)",
            (doc_id, chunk, idx)
        )
    db.commit()
    cursor.close()
    db.close()

def get_all_documents():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, filename, upload_date FROM documents ORDER BY upload_date DESC")
    rows = cursor.fetchall()
    cursor.close()
    db.close()
    return rows

def delete_doc_and_chunks(doc_id):
    db = get_db()
    cursor = db.cursor()
    # Deleting the document will cascade to chunks via FK
    cursor.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
    db.commit()
    cursor.close()
    db.close()
    # Also delete physical file if exists
    upload_dir = os.path.join(os.getcwd(), 'neurorelate', 'static', 'uploads')
    for f in os.listdir(upload_dir):
        if f.startswith(str(doc_id)) or f == str(doc_id):
            try:
                os.remove(os.path.join(upload_dir, f))
            except OSError:
                pass

def get_recent_documents(limit=5):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT filename, upload_date FROM documents ORDER BY upload_date DESC LIMIT %s", (limit,))
    rows = cursor.fetchall()
    cursor.close()
    db.close()
    return rows

def get_recent_queries(limit=5):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT question, answer, created_at FROM query_history ORDER BY created_at DESC LIMIT %s", (limit,))
    rows = cursor.fetchall()
    cursor.close()
    db.close()
    return rows

def save_query(question, answer, source_document):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO query_history (question, answer, source_document, created_at) VALUES (%s, %s, %s, %s)",
        (question, answer, source_document, datetime.now())
    )
    db.commit()
    cursor.close()
    db.close()
