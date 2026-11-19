import os
import re
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
import dotenv

dotenv.load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

from database import get_db, init_db, get_engine_type
from document_processor import (
    process_document,
    get_all_documents,
    get_document_by_id,
    get_document_chunks,
    delete_doc_and_chunks,
    get_recent_documents,
    get_recent_queries,
    save_query
)
from retrieval import search_documents
from ai_service import generate_answer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'neurorelate-secret-key-12345')
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB max upload

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Context processor to inject database status into all templates
@app.context_processor
def inject_global_data():
    return {
        'db_engine': get_engine_type(),
        'year': datetime.now().year
    }

# ----------------- Page Routes -----------------

@app.route('/')
def home():
    stats = get_dashboard_stats()
    return render_template('index.html', stats=stats)

@app.route('/dashboard')
def dashboard():
    stats = get_dashboard_stats()
    return render_template('dashboard.html', stats=stats)

@app.route('/upload')
def upload_page():
    docs = get_all_documents()
    return render_template('upload.html', documents=docs)

@app.route('/chat')
def chat_page():
    docs = get_all_documents()
    recent_queries = get_recent_queries(limit=6)
    return render_template('chat.html', documents=docs, recent_queries=recent_queries)

@app.route('/search')
def search_page():
    docs = get_all_documents()
    return render_template('search.html', documents=docs)

@app.route('/database')
def database_page():
    docs = get_all_documents()
    return render_template('database.html', documents=docs)

@app.route('/about')
def about_page():
    return render_template('about.html')

# ----------------- REST API Endpoints -----------------

@app.route('/api/documents/upload', methods=['POST'])
def upload_document():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part attached'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'Unsupported file format. Supported: .pdf, .txt, .md, .csv, .json'}), 400

    filename = secure_clean_filename(file.filename)
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)

    try:
        doc_id, chunk_count = process_document(save_path, filename)
        return jsonify({
            'message': f"Document '{filename}' successfully ingested and processed.",
            'doc_id': doc_id,
            'chunk_count': chunk_count,
            'filename': filename
        }), 200
    except Exception as e:
        return jsonify({'error': f"Failed to process document: {str(e)}"}), 500

@app.route('/api/documents', methods=['GET'])
def list_documents():
    docs = get_all_documents()
    return jsonify(docs)

@app.route('/api/documents/<int:doc_id>', methods=['GET'])
def get_document(doc_id):
    doc = get_document_by_id(doc_id)
    if not doc:
        return jsonify({'error': 'Document not found'}), 400
    return jsonify(doc)

@app.route('/api/documents/<int:doc_id>/chunks', methods=['GET'])
def list_document_chunks(doc_id):
    chunks = get_document_chunks(doc_id)
    return jsonify(chunks)

@app.route('/api/documents/<int:doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    try:
        delete_doc_and_chunks(doc_id)
        return jsonify({'message': f'Document {doc_id} and associated chunks deleted successfully.'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/search', methods=['POST'])
def api_search():
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    top_k = int(data.get('top_k', 5))
    doc_id = data.get('doc_id')
    if doc_id:
        try:
            doc_id = int(doc_id)
        except ValueError:
            doc_id = None

    results = search_documents(query, top_k=top_k, doc_id=doc_id)
    return jsonify({'results': results, 'count': len(results)})

@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json() or {}
    question = data.get('question', '').strip()
    doc_id = data.get('doc_id')
    top_k = int(data.get('top_k', 5))

    if not question:
        return jsonify({'error': 'A question is required.'}), 400

    if doc_id:
        try:
            doc_id = int(doc_id)
        except ValueError:
            doc_id = None

    all_docs = get_all_documents()

    # Retrieve relevant document chunks from RDBMS
    chunks = search_documents(question, top_k=top_k, doc_id=doc_id)
    
    if chunks:
        chunk_texts = [c['chunk_text'] for c in chunks]
        source_labels = [f"{c['document_name']} (Chunk #{c['chunk_number']})" for c in chunks]
        primary_source = chunks[0]['document_name']
        all_sources = list(dict.fromkeys([c['document_name'] for c in chunks]))
    else:
        chunk_texts = []
        source_labels = []
        primary_source = all_docs[0]['filename'] if all_docs else "Knowledge Base"
        all_sources = [d['filename'] for d in all_docs] if all_docs else []

    # Generate grounded RAG answer
    answer = generate_answer(question, chunk_texts, source_labels, available_docs=all_docs)

    # Save to query history table in RDBMS
    save_query(question, answer, primary_source)

    return jsonify({
        'answer': answer,
        'source': primary_source,
        'sources': all_sources,
        'chunks': chunks
    })

@app.route('/api/settings/apikey', methods=['POST'])
def update_api_key():
    data = request.get_json() or {}
    key = data.get('api_key', '').strip()
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    
    # Read existing .env
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith('GEMINI_API_KEY=') or line.startswith('LLM_API_KEY='):
            new_lines.append(f"GEMINI_API_KEY={key}\n")
            updated = True
        else:
            new_lines.append(line)
            
    if not updated:
        new_lines.append(f"GEMINI_API_KEY={key}\n")
        
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
        
    os.environ['GEMINI_API_KEY'] = key
    return jsonify({'message': 'API key updated successfully', 'configured': bool(key)})

@app.route('/api/stats', methods=['GET'])
def api_stats():
    return jsonify(get_dashboard_stats())

@app.route('/api/history', methods=['GET'])
def api_history():
    limit = int(request.args.get('limit', 20))
    history = get_recent_queries(limit=limit)
    return jsonify(history)

@app.route('/api/database/tables', methods=['GET'])
def api_database_tables():
    """Returns database schema information and live row counts."""
    db = get_db()
    cur = db.cursor()
    
    tables_info = []
    for table in ['documents', 'document_chunks', 'query_history']:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
        except Exception:
            count = 0
        tables_info.append({'name': table, 'rows': count})
    
    cur.close()
    db.close()
    return jsonify({
        'engine': get_engine_type(),
        'tables': tables_info
    })

@app.route('/api/database/query', methods=['POST'])
def api_database_query():
    """Execute read-only SQL queries to inspect the RDBMS."""
    data = request.get_json() or {}
    raw_query = data.get('query', '').strip()
    
    if not raw_query:
        return jsonify({'error': 'SQL query is empty'}), 400

    # Safety guard: only allow SELECT or EXPLAIN or PRAGMA statements
    first_word = raw_query.split()[0].upper()
    if first_word not in ('SELECT', 'EXPLAIN', 'PRAGMA', 'SHOW', 'DESCRIBE'):
        return jsonify({'error': 'Only read-only queries (SELECT, EXPLAIN) are permitted in the web console.'}), 403

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(raw_query)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        
        # Convert any datetime or non-serializable objects to string
        serialized_rows = []
        for row in rows:
            clean_row = []
            for item in row:
                if isinstance(item, (datetime, bytes)):
                    clean_row.append(str(item))
                elif isinstance(item, str) and len(item) > 400:
                    clean_row.append(item[:400] + '...')
                else:
                    clean_row.append(item)
            serialized_rows.append(clean_row)

        cur.close()
        db.close()
        return jsonify({
            'columns': columns,
            'rows': serialized_rows,
            'row_count': len(serialized_rows)
        })
    except Exception as e:
        cur.close()
        db.close()
        return jsonify({'error': str(e)}), 400

# ----------------- Helpers -----------------

def allowed_file(filename):
    allowed_exts = {'pdf', 'txt', 'md', 'csv', 'json', 'sql', 'py'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_exts

def secure_clean_filename(filename):
    cleaned = re.sub(r'[^a-zA-Z0-9_\.-]', '_', filename)
    return cleaned if cleaned else 'document.txt'

def get_dashboard_stats():
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('SELECT COUNT(*) FROM documents')
        total_docs = cur.fetchone()[0]
    except Exception:
        total_docs = 0

    try:
        cur.execute('SELECT COUNT(*) FROM document_chunks')
        total_chunks = cur.fetchone()[0]
    except Exception:
        total_chunks = 0

    try:
        cur.execute('SELECT COUNT(*) FROM query_history')
        total_queries = cur.fetchone()[0]
    except Exception:
        total_queries = 0

    cur.close()
    db.close()

    recent_docs = get_recent_documents(limit=5)
    recent_queries = get_recent_queries(limit=5)

    return {
        'total_docs': total_docs,
        'total_chunks': total_chunks,
        'total_queries': total_queries,
        'recent_docs': recent_docs,
        'recent_queries': recent_queries,
        'db_engine': get_engine_type().upper()
    }

if __name__ == '__main__':
    init_db()
    port = int(os.getenv('PORT', 5000))
    print(f"\n=======================================================")
    print(f"🚀 NeuroRelate RDBMS & RAG Platform is starting on port {port}")
    print(f"🔗 Access Web UI at: http://127.0.0.1:{port}")
    print(f"📦 Database Engine: {get_engine_type().upper()}")
    print(f"=======================================================\n")
    app.run(host='0.0.0.0', port=port, debug=True)
