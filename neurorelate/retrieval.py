import re
import math
from database import get_db
from document_processor import get_recent_documents, get_recent_queries

STOP_WORDS = {
    'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and', 'any', 'are', 'aren\'t',
    'as', 'at', 'be', 'because', 'been', 'before', 'being', 'below', 'between', 'both', 'but', 'by', 'can',
    'cannot', 'could', 'couldn\'t', 'did', 'didn\'t', 'do', 'does', 'doesn\'t', 'doing', 'don\'t', 'down',
    'during', 'each', 'few', 'for', 'from', 'further', 'had', 'hadn\'t', 'has', 'hasn\'t', 'have', 'haven\'t',
    'having', 'he', 'he\'d', 'he\'ll', 'he\'s', 'her', 'here', 'here\'s', 'hers', 'herself', 'him', 'himself',
    'his', 'how', 'how\'s', 'i', 'i\'d', 'i\'ll', 'i\'m', 'i\'ve', 'if', 'in', 'into', 'is', 'isn\'t', 'it',
    'it\'s', 'its', 'itself', 'let\'s', 'me', 'more', 'most', 'mustn\'t', 'my', 'myself', 'no', 'nor', 'not',
    'of', 'off', 'on', 'once', 'only', 'or', 'other', 'ought', 'our', 'ours', 'ourselves', 'out', 'over',
    'own', 'same', 'shan\'t', 'she', 'she\'d', 'she\'ll', 'she\'s', 'should', 'shouldn\'t', 'so', 'some',
    'such', 'than', 'that', 'that\'s', 'the', 'their', 'theirs', 'them', 'themselves', 'then', 'there',
    'there\'s', 'these', 'they', 'they\'d', 'they\'ll', 'they\'re', 'they\'ve', 'this', 'those', 'through',
    'to', 'too', 'under', 'until', 'up', 'very', 'was', 'wasn\'t', 'we', 'we\'d', 'we\'ll', 'we\'re',
    'we\'ve', 'were', 'weren\'t', 'what', 'what\'s', 'when', 'when\'s', 'where', 'where\'s', 'which', 'while',
    'who', 'who\'s', 'whom', 'why', 'why\'s', 'with', 'won\'t', 'would', 'wouldn\'t', 'you', 'you\'d',
    'you\'ll', 'you\'re', 'you\'ve', 'your', 'yours', 'yourself', 'yourselves'
}

# Semantic expansion mapping to bridge user query vocabulary with document vocabulary
SYNONYMS = {
    'summary': ['overview', 'purpose', 'guidelines', 'synopsis', 'project', 'report', 'objective'],
    'summarize': ['overview', 'purpose', 'guidelines', 'synopsis', 'project', 'report', 'introduction'],
    'findings': ['guidelines', 'results', 'conclusions', 'report', 'submission', 'details'],
    'conclusions': ['submission', 'evaluation', 'guidelines', 'summary', 'report'],
    'rules': ['guidelines', 'requirements', 'instructions', 'criteria', 'specifications'],
    'guideline': ['guidelines', 'instructions', 'rules', 'format', 'specifications'],
    'format': ['template', 'structure', 'font', 'spacing', 'sections', 'report', 'synopsis'],
    'structure': ['format', 'sections', 'contents', 'table', 'chapters', 'schema'],
    'risks': ['limitations', 'constraints', 'scope', 'guidelines', 'requirements'],
    'limitations': ['scope', 'constraints', 'guidelines', 'specifications'],
    'architecture': ['design', 'schema', 'relational', 'structure', 'database', 'system'],
    'student': ['name', 'bonafide', 'candidate', 'enrollment', 'roll'],
    'guide': ['professor', 'faculty', 'supervisor', 'hod', 'principal', 'mentor'],
    'author': ['guide', 'student', 'university', 'department', 'hod'],
    'pages': ['page', 'spacing', 'margins', 'font', 'format', 'report'],
}

def tokenize(text):
    """Normalize and extract words from text."""
    if not text:
        return []
    words = re.findall(r'\b[a-zA-Z0-9_\-\.]+\b', text.lower())
    return [w for w in words if w and w not in STOP_WORDS and len(w) > 1]

def search_documents(query, top_k=5, doc_id=None):
    """
    Search document chunks using an enterprise hybrid retrieval algorithm:
    combining exact phrase matching, TF term frequency, coverage scoring,
    and semantic synonym expansion.
    """
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Fetch candidate chunks from RDBMS
    if doc_id:
        cursor.execute("""
            SELECT c.id, c.document_id, c.chunk_text, c.chunk_number, d.filename as document_name
            FROM document_chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.document_id = %s
            ORDER BY c.chunk_number ASC
        """, (doc_id,))
    else:
        cursor.execute("""
            SELECT c.id, c.document_id, c.chunk_text, c.chunk_number, d.filename as document_name
            FROM document_chunks c
            JOIN documents d ON c.document_id = d.id
            ORDER BY c.document_id DESC, c.chunk_number ASC
        """)

    all_chunks = cursor.fetchall()
    cursor.close()
    db.close()

    if not all_chunks:
        return []

    # If query is empty, return initial overview chunks
    if not query or not query.strip():
        results = all_chunks[:top_k]
        for r in results:
            r['score'] = 1.0
            r['matched_terms'] = []
            r['snippet'] = r['chunk_text'][:200] + ("..." if len(r['chunk_text']) > 200 else "")
        return results

    query_raw = query.strip()
    query_lower = query_raw.lower()
    terms = tokenize(query_raw)
    
    # If all terms were filtered as stop words, use raw tokens
    if not terms:
        terms = [w.lower() for w in re.findall(r'\b\w+\b', query_raw) if len(w) > 1]

    # Expand query terms with synonyms
    expanded_terms = set(terms)
    for t in list(terms):
        if t in SYNONYMS:
            expanded_terms.update(SYNONYMS[t])

    scored_results = []
    
    for chunk in all_chunks:
        text = chunk['chunk_text']
        text_lower = text.lower()
        score = 0.0
        matched = []

        # 1. Exact query string match bonus
        if query_lower in text_lower:
            score += 15.0

        # 2. Primary terms frequency & query coverage scoring
        chunk_words = tokenize(text)
        term_freq = {}
        for w in chunk_words:
            term_freq[w] = term_freq.get(w, 0) + 1

        primary_matched_count = 0
        for t in terms:
            if t in term_freq:
                tf = term_freq[t]
                score += (1 + math.log(tf)) * 4.0
                matched.append(t)
                primary_matched_count += 1
            elif t in text_lower:
                score += 2.0
                matched.append(t)
                primary_matched_count += 1

        # 3. Synonym / semantic expansion match bonus
        for exp in expanded_terms:
            if exp not in terms and (exp in term_freq or exp in text_lower):
                score += 1.5
                matched.append(exp)

        # 4. Query coverage bonus (proportion of original query terms found)
        if terms:
            coverage = primary_matched_count / len(terms)
            score += coverage * 8.0

        # 5. Position bonus: First chunks often contain titles, scope, and summaries
        if chunk.get('chunk_number', 99) in (1, 2, 5):
            score += 0.5

        # 6. Length normalization
        score = score / (1.0 + 0.0003 * len(text))

        if score > 0:
            snippet = make_snippet(text, matched if matched else terms)
            scored_results.append({
                'id': chunk['id'],
                'document_id': chunk['document_id'],
                'document_name': chunk['document_name'],
                'chunk_number': chunk['chunk_number'],
                'chunk_text': chunk['chunk_text'],
                'score': round(score, 3),
                'matched_terms': list(set(matched)),
                'snippet': snippet
            })

    # Sort descending by relevance score
    scored_results.sort(key=lambda x: x['score'], reverse=True)

    # If no results matched but documents exist, fall back to leading overview chunks
    if not scored_results and all_chunks:
        for chunk in all_chunks[:top_k]:
            scored_results.append({
                'id': chunk['id'],
                'document_id': chunk['document_id'],
                'document_name': chunk['document_name'],
                'chunk_number': chunk['chunk_number'],
                'chunk_text': chunk['chunk_text'],
                'score': 0.5,
                'matched_terms': [],
                'snippet': chunk['chunk_text'][:200] + "..."
            })

    return scored_results[:top_k]

def make_snippet(text, matched_terms, max_len=200):
    """Generate a clean contextual snippet around matched terms."""
    if not text:
        return ""
    # Clean out raw page banners
    clean_text = re.sub(r'---\s*Page\s*\d+\s*---', '', text).strip()
    if not clean_text:
        clean_text = text

    if not matched_terms:
        return clean_text[:max_len] + ("..." if len(clean_text) > max_len else "")

    text_lower = clean_text.lower()
    first_pos = len(clean_text)
    for term in matched_terms:
        pos = text_lower.find(term)
        if pos != -1 and pos < first_pos:
            first_pos = pos

    if first_pos == len(clean_text) or first_pos < 40:
        start = 0
    else:
        start = max(0, first_pos - 40)
        space = clean_text.find(' ', start)
        if space != -1 and space < first_pos:
            start = space + 1

    end = min(len(clean_text), start + max_len)
    snippet = clean_text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(clean_text):
        snippet = snippet + "..."
    return snippet
