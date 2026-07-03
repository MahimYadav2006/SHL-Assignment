# SHL Assessment Recommendation Agent — Approach Document

## 1. Problem Statement

Build a stateless, conversational AI agent that guides recruiters and hiring managers from a vague hiring intent to a validated shortlist of SHL Individual Test Solutions. The agent must:

- Ground all recommendations in the SHL product catalog (274 products)
- Handle multi-turn clarification, refinement, and comparison
- Refuse out-of-scope queries (legal advice, salary, interview tips)
- Output structured JSON with product name, URL, and test type code

## 2. Architecture

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  FastAPI API  │────▶│  SHL Agent      │────▶│  AWS Bedrock     │
│  /health      │     │  (agent.py)     │     │  Claude 3.5      │
│  /chat        │     │                 │     │  (bearer token)  │
└──────────────┘     │  ┌─────────────┐│     └──────────────────┘
                     │  │  Retriever   ││             │
                     │  │  TF-IDF +    ││     ┌───────▼──────────┐
                     │  │  Keyword     ││     │  Gemini REST     │
                     │  │  (274 prods) ││     │  (fallback)      │
                     │  └─────────────┘│     └──────────────────┘
                     └─────────────────┘             │
                                              ┌──────▼──────────┐
                                              │  Rules Fallback  │
                                              │  (last resort)   │
                                              └─────────────────┘
```

### Components

| Component | File | Purpose |
|---|---|---|
| **API Layer** | `main.py` | FastAPI with `/health` and `/chat` endpoints, CORS, Pydantic validation |
| **Agent** | `agent.py` | Orchestrates retrieval → LLM reasoning → response parsing with 3-tier fallback |
| **Retriever** | `retriever.py` | TF-IDF + keyword-boosted hybrid search with metadata filtering |
| **Catalog** | `catalog.json` | 274 SHL products with type codes, durations, languages, descriptions |
| **Catalog Builder** | `build_catalog.py` | Generates catalog from product slugs + curated ground-truth data |

## 3. Key Design Decisions

### 3.1 Hybrid Retrieval (TF-IDF + Keyword Boost)

Pure TF-IDF fails for technology-specific queries (e.g., "Java developer") because many products share generic terms. Our hybrid approach:

1. **TF-IDF** (50-60% weight): Captures semantic similarity via unigram/bigram vectorization
2. **Keyword Boost** (40-50% weight): Strong boost (+0.4) when technology keywords (java, python, aws, etc.) appear directly in the product slug
3. **Adaptive Weighting**: When tech keywords are detected in the query, keyword scores are weighted at 70% to prioritize exact technology matches

### 3.2 Stateless Multi-Turn via Prompt Engineering

The agent is fully stateless — no session storage. Conversation history is passed in each `/chat` request. For Bedrock (Claude), the system prompt and conversation messages are sent separately via the Anthropic Messages API, providing superior instruction following. Turn-count awareness is injected into the system prompt when conversations approach the 8-turn limit.

### 3.3 Three-Tier LLM Strategy

1. **Primary — AWS Bedrock (Claude 3.5 Sonnet)**: Uses ABSK bearer token authentication via direct REST API. Provides excellent instruction following and JSON output.
2. **Fallback — Gemini REST API**: Three API keys rotated round-robin. On 429 (rate limit), the agent immediately tries the next key.
3. **Last Resort — Rules-Based Fallback**: When both LLMs are unavailable, generates responses using the retriever alone with pattern matching.

### 3.4 Smart Fallback

When the LLM is unavailable, the agent:
- Asks clarifying questions on vague first-turn queries
- Presents retrieval results in a Markdown table
- Detects confirmation patterns ("looks good", "perfect") to end conversations
- Refuses out-of-scope queries via regex pattern matching

## 4. Catalog Construction

The SHL product catalog was built from:

1. **253 product URLs** extracted from the Wayback Machine CDX API for `shl.com/products/product-catalog/view/*`
2. **34 curated entries** with verified metadata from the assignment's sample conversations (C1–C10)
3. **Heuristic type inference** for uncurated products based on slug naming patterns (e.g., `-new` → Knowledge, `simulation` → Simulation, `solution` → Personality + Competencies)

### Test Type Distribution

| Code | Category | Count |
|---|---|---|
| A | Ability & Aptitude | 20 |
| B | Biodata & Situational Judgment | 7 |
| C | Competencies | 100 |
| D | Development & 360 | 5 |
| E | Assessment Exercises | 1 |
| K | Knowledge & Skills | 123 |
| P | Personality & Behavior | 125 |
| S | Simulations | 11 |

## 5. Evaluation

Evaluated against all 10 sample conversations (C1–C10) from the assignment with ground truth extracted from each trace's final recommendation table.

## 6. Running the Agent

```bash
# Install dependencies
pip install -r requirements.txt

# Set Bedrock API key (primary LLM)
export BEDROCK_API_KEY="your-bedrock-absk-token"
export BEDROCK_REGION="us-east-1"

# Optional: Gemini fallback keys
export GEMINI_API_KEYS="key1,key2,key3"

# Start server
python main.py
# or: uvicorn main:app --host 0.0.0.0 --port 8000

# Test
curl http://localhost:8000/health
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "I need assessments for a data analyst role"}]}'
```

## 7. Limitations & Future Work

1. **Catalog Depth**: ~21% of products have curated descriptions; the rest rely on name/slug heuristics. Scraping actual SHL product pages would enrich metadata.
2. **Semantic Search**: Replacing TF-IDF with a sentence-transformer embedding model (e.g., `all-MiniLM-L6-v2`) would improve retrieval for paraphrased queries.
3. **Multi-language Support**: Currently English-centric; could be extended with language-specific retrieval paths.
4. **Evaluation**: Expanding ground truth beyond the 10 public traces to holdout conversations would provide more comprehensive benchmarks.
