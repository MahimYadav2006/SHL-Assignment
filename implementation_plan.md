# SHL Assessment Recommender Agent — Implementation Plan

## Overview
Build a conversational AI agent that recommends SHL assessments to hiring managers/recruiters through multi-turn dialogue. The agent uses a scraped SHL product catalog, FAISS vector search for retrieval, and Gemini for conversational intelligence.

## Architecture

```
┌─────────────────────────────────────────────┐
│              FastAPI Service                 │
│  GET /health  →  {"status": "ok"}           │
│  POST /chat   →  stateless conversation     │
├─────────────────────────────────────────────┤
│           Agent Logic Layer                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
│  │ Classify  │→ │ Retrieve │→ │ Generate  │ │
│  │  Intent   │  │ Products │  │  Reply    │ │
│  └──────────┘  └──────────┘  └───────────┘ │
├─────────────────────────────────────────────┤
│         Retrieval Layer                      │
│  FAISS Vector Index + BM25 Keyword Search   │
│  Over 400+ Individual Test Solutions        │
├─────────────────────────────────────────────┤
│         Data Layer                           │
│  catalog.json — scraped SHL product data    │
└─────────────────────────────────────────────┘
```

## Parts

### Part 1: Catalog Scraping
- Scrape all Individual Test Solutions from SHL product catalog
- Extract: name, URL, test_type, duration, languages, description, keys/categories
- Store as catalog.json

### Part 2: Retrieval Engine
- Build FAISS index over catalog embeddings
- BM25 keyword search as secondary retriever
- Hybrid scoring for product matching

### Part 3: Conversational Agent
- Gemini-powered intent classification + response generation
- Conversation state machine: CLARIFY → RECOMMEND → REFINE → COMPARE
- Scope enforcement (SHL assessments only)
- Prompt engineering for grounded recommendations

### Part 4: FastAPI Service
- POST /chat with exact schema compliance
- GET /health endpoint
- Stateless — full conversation history in each request
- <30s response time, <8 turns per conversation

### Part 5: Evaluation & Testing
- Test against all 10 sample conversations
- Recall@10 measurement
- Behavior probe testing (off-topic refusal, vague query handling, etc.)

### Part 6: Deployment
- Deploy to Render/Railway/HuggingFace Spaces
- Approach document (2 pages max)
