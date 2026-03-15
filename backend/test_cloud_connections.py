#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env')

print("=" * 60)
print("TEST 1: PostgreSQL (Supabase) Connection")
print("=" * 60)
try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine.url import make_url
    db_url = os.getenv('DB_URL')
    parsed = make_url(db_url)
    safe_host = parsed.host or "unknown-host"
    safe_port = parsed.port or "?"
    safe_db = parsed.database or "?"
    print(f"Connecting to: postgresql://***@{safe_host}:{safe_port}/{safe_db}")
    engine = create_engine(db_url)
    with engine.connect() as conn:
        result = conn.execute(text('SELECT 1'))
        print("✅ PostgreSQL (Supabase) Connected!")
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("TEST 2: Qdrant Cloud Connection")
print("=" * 60)
try:
    from qdrant_client import QdrantClient
    qdrant_url = os.getenv('QDRANT_URL')
    qdrant_key = os.getenv('QDRANT_API_KEY')
    print(f"Connecting to: {qdrant_url[:50]}...")
    client = QdrantClient(url=qdrant_url, api_key=qdrant_key, timeout=10.0)
    collections = client.get_collections()
    print(f"✅ Qdrant Cloud Connected! Collections: {len(collections.collections)}")
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("TEST 3: Gemini API")
print("=" * 60)
try:
    import google.generativeai as genai
    api_key = os.getenv('GOOGLE_API_KEY')
    print(f"Configuring Gemini...")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content('Say "Hello from Gemini"')
    print(f"✅ Gemini API Works!")
    print(f"   Response: {response.text[:60]}")
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED!")
print("=" * 60)
