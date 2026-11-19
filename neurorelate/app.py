import os
from flask import Flask, render_template, request, jsonify, send_from_directory
from database import get_db, init_db
from document_processor import process_document
from retrieval import search_documents, get_recent_documents, get_recent_queries
from ai_service import generate_answer
import dotenv

dotenv.load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'neurorelate', 'static', 'uploads')

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    stats = get_dashboard_stats()
    return render_template('dashboard.html', stats=stats)

@app.route('/upload')
def upload_page():
    return render_template('upload.html')

@app.route('/chat')
def chat_page():
    return render_template('chat.html')

@app.route('/search')
def search_page():
    return render_template('search.html')

@app.route('/database')
def database_page():
    docs = get_all_documents()
    return render_template('database.html', documents=docs)

@app.route('/about')
def about_page():
    return render_template('about.html')

# API endpoints
@app.route('/api/documents/upload', methods=['POST'])
def upload_document():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'Unsupported file type'}), 400
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(save_path)
    # Process document (extract text, chunk, store)
    process_document(save_path, file.filename)
    return jsonify({'message': 'File uploaded and processed'}), 200

@app.route('/api/documents', methods=['GET'])
def list_documents():
    docs = get_all_documents()
    return jsonify(docs)

@app.route('/api/documents/<int:doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    delete_doc_and_chunks(doc_id)
    return jsonify({'message': 'Document deleted'}), 200

@app.route('/api/search', methods=['POST'])
def api_search():
    data = request.get_json()
    query = data.get('query', '')
    results = search_documents(query)
    return jsonify(results)

@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json()
    question = data.get('question', '')
    if not question:
        return jsonify({'error': 'Question required'}), 400
    # Retrieve relevant chunks
    chunks = search_documents(question, top_k=5)
    if not chunks:
        return jsonify({'answer': 'No relevant information found in the uploaded documents.'})
    answer = generate_answer(question, [c['chunk_text'] for c in chunks])
    # Save to query history
    save_query(question, answer, chunks[0]['document_name'])
    return jsonify({'answer': answer, 'source': chunks[0]['document_name']})

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf', 'txt'}

def get_dashboard_stats():
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT COUNT(*) FROM documents')
    total_docs = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM document_chunks')
    total_chunks = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM query_history')
    total_queries = cur.fetchone()[0]
    recent_docs = get_recent_documents(limit=5)
    recent_queries = get_recent_queries(limit=5)
    return {
        'total_docs': total_docs,
        'total_chunks': total_chunks,
        'total_queries': total_queries,
        'recent_docs': recent_docs,
        'recent_queries': recent_queries,
    }

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
