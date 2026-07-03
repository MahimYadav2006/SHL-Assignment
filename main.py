"""
main.py — FastAPI service for the SHL Assessment Recommendation Agent.

Endpoints:
  GET  /health  → {"status": "ok"}
  POST /chat    → Stateless conversation processing
"""
import os
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent import SHLAgent

# ── Logging ─────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Pydantic Models ─────────────────────────────────────────────────────────────

class Message(BaseModel):
    role: str = Field(..., description="Either 'user' or 'assistant'")
    content: str = Field(..., description="The message content")


class ChatRequest(BaseModel):
    messages: List[Message] = Field(..., description="Conversation history")


class Recommendation(BaseModel):
    name: str = Field(..., description="Product name")
    url: str = Field(..., description="SHL catalog URL")
    test_type: str = Field(..., description="Single letter type code (A/B/C/D/E/K/P/S)")


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Agent's conversational response")
    recommendations: List[Recommendation] = Field(
        default_factory=list,
        description="Recommended assessments (1-10 items when available, else empty)"
    )
    end_of_conversation: bool = Field(
        default=False,
        description="True when the user confirms the final shortlist"
    )


# ── FastAPI App ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SHL Assessment Recommendation Agent",
    description="Conversational agent for recommending SHL Individual Test Solutions",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Lazy initialization ────────────────────────────────────────────────────────

_agent: Optional[SHLAgent] = None


def get_agent() -> SHLAgent:
    global _agent
    if _agent is None:
        logger.info("Initializing SHL Agent...")
        _agent = SHLAgent()
        logger.info(f"Agent initialized with {len(_agent.retriever.catalog)} products")
    return _agent


# ── Endpoints ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Readiness probe."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Process a stateless conversation and return the next agent response."""
    try:
        agent = get_agent()

        # Convert Pydantic messages to dicts
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        # Validate messages
        for msg in messages:
            if msg["role"] not in ("user", "assistant"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid role: {msg['role']}. Must be 'user' or 'assistant'."
                )

        logger.info(f"Processing chat with {len(messages)} messages")

        # Get agent response
        result = agent.chat(messages)

        logger.info(
            f"Response: {len(result.get('recommendations', []))} recommendations, "
            f"end_of_conversation={result.get('end_of_conversation', False)}"
        )

        return ChatResponse(
            reply=result["reply"],
            recommendations=[
                Recommendation(**rec) for rec in result.get("recommendations", [])
            ],
            end_of_conversation=result.get("end_of_conversation", False),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing chat: {e}", exc_info=True)
        # Return a graceful fallback
        return ChatResponse(
            reply="I apologize for the technical difficulty. Could you please rephrase your question about SHL assessments?",
            recommendations=[],
            end_of_conversation=False,
        )


# ── Startup Event ───────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Pre-load the agent on startup for faster first response."""
    try:
        get_agent()
        logger.info("SHL Agent ready!")
    except Exception as e:
        logger.warning(f"Agent pre-load failed (will retry on first request): {e}")


# ── Main ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
