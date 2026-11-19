import os
import re
import logging
from datetime import datetime
from database import get_db

logger = logging.getLogger("neurorelate.processor")
logging.basicConfig(level=logging.INFO)

CHUNK_SIZE = 600  # characters per chunk
CHUNK_OVERLAP = 100  # character overlap between chunks

def extract_text(file_path, filename):
    """Extract text from PDF, TXT, MD, CSV, JSON, and code files."""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    
    if ext == 'pdf':
        text = ""
        # 1. Try PyMuPDF (fitz)
        try:
            import fitz
            doc = fitz.open(file_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text = page.get_text()
                if page_text:
                    text += f"\n--- Page {page_num + 1} ---\n" + page_text
            doc.close()
            if text.strip():
                return text.strip()
        except Exception as e:
            logger.warning(f"PyMuPDF failed ({e}), attempting PyPDF fallback.")

        # 2. Try pypdf
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            for idx, page in enumerate(reader.pages):
                extracted = page.extract_text()
                if extracted:
                    text += f"\n--- Page {idx + 1} ---\n" + extracted
            if text.strip():
                return text.strip()
        except Exception as e:
            logger.warning(f"pypdf failed ({e}), attempting PyPDF2 fallback.")

        # 3. Try PyPDF2
        try:
            import PyPDF2
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for idx, page in enumerate(reader.pages):
                    extracted = page.extract_text()
                    if extracted:
                        text += f"\n--- Page {idx + 1} ---\n" + extracted
            if text.strip():
                return text.strip()
        except Exception as e:
            logger.error(f"PyPDF2 failed: {e}")

        return text.strip() if text.strip() else "[Warning: No extractable text found in PDF]"

    else:
        # Plaintext formats (.txt, .md, .csv, .json, .py, etc.)
        for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        # Fallback with error replacement
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()

def chunk_text(text, target_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """
    Intelligent paragraph and sentence-aware chunking with sliding window overlap.
    Avoids splitting mid-sentence or mid-word.
    """
    if not text or not text.strip():
        return []

    # Clean redundant whitespace
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Split text into paragraphs first
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If adding this paragraph exceeds target size and current_chunk is not empty
        if len(current_chunk) + len(para) + 2 > target_size and current_chunk:
            chunks.append(current_chunk.strip())
            # Handle overlap: take last 'overlap' chars of previous chunk (up to a word boundary)
            if len(current_chunk) > overlap:
                overlap_text = current_chunk[-overlap:]
                # adjust to first whitespace
                space_idx = overlap_text.find(' ')
                if space_idx != -1:
                    overlap_text = overlap_text[space_idx + 1:]
                current_chunk = overlap_text + "\n" + para
            else:
                current_chunk = para
        else:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para

        # If an individual paragraph itself is bigger than target_size, break it by sentences
        if len(current_chunk) > target_size * 1.5:
            sentences = re.split(r'(?<=[.!?])\s+', current_chunk)
            sub_chunk = ""
            for sent in sentences:
                if len(sub_chunk) + len(sent) + 1 > target_size and sub_chunk:
                    chunks.append(sub_chunk.strip())
                    sub_chunk = sent
                else:
                    sub_chunk = (sub_chunk + " " + sent).strip()
            current_chunk = sub_chunk

    if current_chunk and current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text[:target_size]]

def process_document(file_path, filename):
    """
    Extract text, chunk content, and persist document metadata and chunks
    into the relational database.
    """
    text = extract_text(file_path, filename)
    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else len(text)
    chunks = chunk_text(text)
    chunk_count = len(chunks)

    db = get_db()
    cursor = db.cursor()

    try:
        # Insert document record
        cursor.execute(
            """
            INSERT INTO documents (filename, upload_date, extracted_text, file_size, chunk_count)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (filename, datetime.now(), text, file_size, chunk_count)
        )
        doc_id = cursor.lastrowid

        # Insert chunks
        for idx, chunk in enumerate(chunks, start=1):
            cursor.execute(
                """
                INSERT INTO document_chunks (document_id, chunk_text, chunk_number)
                VALUES (%s, %s, %s)
                """,
                (doc_id, chunk, idx)
            )

        db.commit()
        logger.info(f"Processed document '{filename}' (ID: {doc_id}) into {chunk_count} chunks.")
        return doc_id, chunk_count
    except Exception as e:
        db.rollback()
        logger.error(f"Error processing document {filename}: {e}")
        raise e
    finally:
        cursor.close()
        db.close()

def get_all_documents():
    """Retrieve all documents with metadata ordered by upload date."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT d.id, d.filename, d.upload_date, d.file_size, 
               COUNT(c.id) as chunk_count,
               SUBSTR(d.extracted_text, 1, 200) as preview
        FROM documents d
        LEFT JOIN document_chunks c ON d.id = c.document_id
        GROUP BY d.id
        ORDER BY d.upload_date DESC
    """)
    rows = cursor.fetchall()
    cursor.close()
    db.close()
    return rows

def get_document_by_id(doc_id):
    """Retrieve single document details by ID."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, filename, upload_date, file_size, chunk_count, extracted_text FROM documents WHERE id = %s", (doc_id,))
    row = cursor.fetchone()
    cursor.close()
    db.close()
    return row

def get_document_chunks(doc_id):
    """Retrieve all chunks belonging to a document."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, document_id, chunk_number, chunk_text
        FROM document_chunks
        WHERE document_id = %s
        ORDER BY chunk_number ASC
    """, (doc_id,))
    rows = cursor.fetchall()
    cursor.close()
    db.close()
    return rows

def delete_doc_and_chunks(doc_id):
    """Delete document and cascading chunks, and remove file from disk."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Get filename first to remove file from disk
    cursor.execute("SELECT filename FROM documents WHERE id = %s", (doc_id,))
    doc = cursor.fetchone()
    filename = doc['filename'] if doc else None

    # Deleting document cascades to document_chunks
    cursor.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
    # Explicitly delete chunks in case foreign key cascade isn't enforced
    cursor.execute("DELETE FROM document_chunks WHERE document_id = %s", (doc_id,))
    db.commit()
    cursor.close()
    db.close()

    # Remove physical file if present
    if filename:
        upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
        file_path = os.path.join(upload_dir, filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError as e:
                logger.warning(f"Could not remove physical file {file_path}: {e}")

def get_recent_documents(limit=5):
    """Retrieve recent documents for dashboard."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, filename, upload_date, file_size, chunk_count
        FROM documents
        ORDER BY upload_date DESC
        LIMIT %s
    """, (limit,))
    rows = cursor.fetchall()
    cursor.close()
    db.close()
    return rows

def get_recent_queries(limit=5):
    """Retrieve recent queries for dashboard and history."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, question, answer, source_document, created_at
        FROM query_history
        ORDER BY created_at DESC
        LIMIT %s
    """, (limit,))
    rows = cursor.fetchall()
    cursor.close()
    db.close()
    return rows

def save_query(question, answer, source_document):
    """Save user question and generated answer into query history."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO query_history (question, answer, source_document, created_at)
        VALUES (%s, %s, %s, %s)
        """,
        (question, answer, source_document or "General Knowledge", datetime.now())
    )
    db.commit()
    cursor.close()
    db.close()
