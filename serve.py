"""Single-process production entry point; workers share their cached feeds."""
import os
from waitress import serve
from app import app, start_workers

if __name__ == '__main__':
    start_workers()
    serve(app, host=os.getenv('HOST', '127.0.0.1'), port=int(os.getenv('PORT', '5000')), threads=8)
