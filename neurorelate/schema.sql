CREATE TABLE IF NOT EXISTS documents (id INT AUTO_INCREMENT PRIMARY KEY, filename VARCHAR(255), upload_date DATETIME, extracted_text LONGTEXT);
CREATE TABLE IF NOT EXISTS document_chunks (id INT AUTO_INCREMENT PRIMARY KEY, document_id INT, chunk_text TEXT, chunk_number INT, FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS query_history (id INT AUTO_INCREMENT PRIMARY KEY, question TEXT, answer TEXT, source_document VARCHAR(255), created_at DATETIME);
