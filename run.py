#!/usr/bin/env python
import os
import sys

# Ensure neurorelate directory is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
neuro_dir = os.path.join(current_dir, 'neurorelate')
if neuro_dir not in sys.path:
    sys.path.insert(0, neuro_dir)

from app import app, init_db, get_engine_type

if __name__ == '__main__':
    init_db()
    port = int(os.getenv('PORT', 5000))
    print(f"\n=======================================================")
    print(f"🚀 NeuroRelate RDBMS & Enterprise RAG Platform")
    print(f"🔗 Access Web UI at: http://127.0.0.1:{port}")
    print(f"📦 Active Storage Engine: {get_engine_type().upper()}")
    print(f"=======================================================\n")
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
