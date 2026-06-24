#!/usr/bin/env bash
# Usage: bash build/curl_tests.sh
# Requires the server to be running: uvicorn build.app:app --reload

BASE="http://localhost:8000"

echo "=== POST /data/pre-process ==="
curl -s -X POST "$BASE/data/pre-process" \
  -H "Content-Type: application/json" \
  -d '{
    "address": ["src.data.train.csv", "src.data.test.csv", "src.models.model.py"],
    "llm": {
      "model": "gpt-4o-mini",
      "provider": "openai"
    }
  }' | python3 -m json.tool

echo ""
echo "=== POST /data/post-process ==="
curl -s -X POST "$BASE/data/post-process" \
  -H "Content-Type: application/json" \
  -d '{
    "address": ["src.code.processor.py"],
    "raw_data": [1, 2, 3, 4, 5],
    "llm": {
      "model": "gpt-4o-mini",
      "provider": "openai"
    }
  }' | python3 -m json.tool
