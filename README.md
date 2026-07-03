# SHL Assessment Recommendation Agent

A conversational AI agent that helps recruiters and hiring managers find the right SHL Individual Test Solutions from a catalog of **274 products**.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure LLM (in .env or environment)
# Primary: AWS Bedrock (Claude)
export BEDROCK_API_KEY="your-absk-bearer-token"
export BEDROCK_REGION="us-east-1"
export BEDROCK_MODEL="anthropic.claude-3-5-sonnet-20241022-v1:0"

# Fallback: Gemini
export GEMINI_API_KEYS="your-key-1,your-key-2"

# 3. Start the server
python main.py
```

The server will start at `http://localhost:8000`.

## API Endpoints

### `GET /health`
Returns `{"status": "ok"}` when the service is ready.

### `POST /chat`
Stateless conversation endpoint.

**Request:**
```json
{
  "messages": [
    {"role": "user", "content": "I need to hire a Java developer"},
    {"role": "assistant", "content": "..."},
    {"role": "user", "content": "They should know Spring and AWS"}
  ]
}
```

**Response:**
```json
{
  "reply": "Here are the recommended SHL assessments...",
  "recommendations": [
    {
      "name": "Core Java (Advanced Level) (New)",
      "url": "https://www.shl.com/products/product-catalog/view/core-java-advanced-level-new/",
      "test_type": "K"
    }
  ],
  "end_of_conversation": false
}
```

## Test Type Codes

| Code | Category |
|------|----------|
| A | Ability & Aptitude |
| B | Biodata & Situational Judgment |
| C | Competencies |
| D | Development & 360 |
| E | Assessment Exercises |
| K | Knowledge & Skills |
| P | Personality & Behavior |
| S | Simulations |

## LLM Configuration

The agent uses a 3-tier LLM strategy:

1. **AWS Bedrock (Claude 3.5 Sonnet)** — Primary. Uses ABSK bearer token via REST API.
2. **Gemini REST API** — Fallback. Round-robin key rotation with retry.
3. **Rules-Based Fallback** — Last resort. TF-IDF retrieval + pattern matching.

## Project Structure

```
├── main.py              # FastAPI application
├── agent.py             # Conversational agent (Bedrock + Gemini + fallback)
├── retriever.py         # TF-IDF + keyword hybrid search engine
├── catalog.json         # 274 SHL products with metadata
├── build_catalog.py     # Catalog generator from product slugs
├── evaluate.py          # Evaluation harness for sample conversations
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container deployment
├── APPROACH.md          # Technical approach document
└── GenAI_SampleConversations/  # Ground truth conversations (C1-C10)
```

## Docker Deployment

```bash
docker build -t shl-agent .
docker run -p 8000:8000 -e BEDROCK_API_KEY="your-token" shl-agent
```

## Evaluation

```bash
python evaluate.py          # Summary mode
python evaluate.py -v       # Verbose mode (shows each turn)
```

## Architecture

See [APPROACH.md](APPROACH.md) for detailed technical documentation.
