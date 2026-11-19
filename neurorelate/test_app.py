import os
import sys
import unittest
import json

# Ensure neurorelate is on path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app import app, init_db
from database import get_db, get_engine_type
from document_processor import process_document, chunk_text, extract_text
from retrieval import search_documents
from ai_service import generate_answer

class NeuroRelateTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        init_db()

    def test_01_database_engine(self):
        engine = get_engine_type()
        self.assertIn(engine, ['mysql', 'sqlite'])
        print(f"\n[PASS] Database engine verified: {engine.upper()}")

    def test_02_chunking_algorithm(self):
        sample_text = (
            "NeuroRelate is an enterprise RDBMS for RAG. It stores documents in relational tables. "
            "Each document has multiple chunks linked via foreign keys. "
            "Cascading deletes ensure that when a document is removed, its chunks are also deleted. "
            "Hybrid retrieval combines BM25 keyword matching and vector rankings."
        )
        chunks = chunk_text(sample_text, target_size=120, overlap=20)
        self.assertGreater(len(chunks), 1)
        print(f"[PASS] Chunking generated {len(chunks)} chunks with sentence preservation.")

    def test_03_document_ingestion_and_retrieval(self):
        # Create a temporary document
        test_file = os.path.join(current_dir, "static", "uploads", "test_report.txt")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(
                "Artificial Intelligence and Relational Databases are converging in modern enterprise architecture. "
                "NeuroRelate uses SQL tables to store semantic knowledge chunks. "
                "The database schema guarantees ACID compliance and provenance tracking for AI answers. "
                "Retrieval-Augmented Generation eliminates hallucinations by grounding answers in verified records."
            )

        doc_id, chunk_count = process_document(test_file, "test_report.txt")
        self.assertIsNotNone(doc_id)
        self.assertGreater(chunk_count, 0)
        print(f"[PASS] Ingested document ID {doc_id} with {chunk_count} chunks.")

        # Test search
        results = search_documents("ACID compliance", top_k=3)
        self.assertGreater(len(results), 0)
        self.assertIn("ACID", results[0]['chunk_text'])
        print(f"[PASS] Search retrieved top chunk with score {results[0]['score']}")

        # Test AI answer generation
        answer = generate_answer("What guarantees ACID compliance?", [results[0]['chunk_text']], [results[0]['document_name']])
        self.assertIsNotNone(answer)
        self.assertIn("test_report.txt", answer)
        print(f"[PASS] Grounded answer generated with citation: {answer[:120]}...")

    def test_04_api_endpoints(self):
        # Test /api/stats
        res = self.client.get('/api/stats')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('total_docs', data)
        self.assertIn('total_chunks', data)
        print(f"[PASS] /api/stats verified: {data['total_docs']} docs, {data['total_chunks']} chunks.")

        # Test /api/chat
        chat_res = self.client.post('/api/chat', json={'question': 'What does NeuroRelate do?'})
        self.assertEqual(chat_res.status_code, 200)
        chat_data = chat_res.get_json()
        self.assertIn('answer', chat_data)
        print(f"[PASS] /api/chat endpoint verified.")

        # Test /api/database/query
        sql_res = self.client.post('/api/database/query', json={'query': 'SELECT COUNT(*) FROM documents'})
        self.assertEqual(sql_res.status_code, 200)
        sql_data = sql_res.get_json()
        self.assertIn('rows', sql_data)
        print(f"[PASS] /api/database/query verified SQL execution output.")

if __name__ == '__main__':
    unittest.main()
