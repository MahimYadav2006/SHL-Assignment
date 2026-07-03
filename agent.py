"""
agent.py — Conversational agent for SHL assessment recommendations.

Uses Groq LLM via OpenAI-compatible REST API,
with a pure rules-based fallback as last resort.
"""
import json
import os
import re
import time
import logging
import requests
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Load .env file
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from retriever import SHLRetriever, TYPE_LABELS

# ── Configuration ───────────────────────────────────────────────────────────────

# Groq configuration (primary)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

# Timeout for LLM calls (stay within 30s evaluator limit)
LLM_TIMEOUT = 25

# ── System Prompt ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an SHL Assessment Recommendation Agent. Your role is to help hiring managers and recruiters find the most appropriate SHL Individual Test Solutions from the SHL product catalog.

## STRICT RULES
1. **ONLY recommend products from the SHL catalog** provided below. Never invent assessments.
2. **NEVER provide general hiring advice**, legal compliance guidance, salary benchmarks, or interview coaching.
3. **Politely refuse out-of-scope requests** and redirect to SHL assessment topics.
4. **Always ground recommendations in the catalog data** provided to you.
5. **Ask clarifying questions** when the user's intent is vague. Key dimensions to clarify:
   - Role/job title and seniority level
   - Required skills/competencies
   - Assessment purpose (selection vs. development)
   - Volume of candidates
   - Language requirements
   - Time constraints
6. **Limit recommendations to 1-10 products**. Never recommend more than 10.
7. **Format recommendations** as Markdown tables when presenting a shortlist.
8. **Compare products using only catalog data**, never from general knowledge.
9. When the user confirms the final shortlist, set end_of_conversation to true.

## RESPONSE FORMAT
You must respond with ONLY a valid JSON object (no markdown code blocks):
{"reply": "Your conversational response (Markdown formatted)", "recommendations": [{"name": "Product Name", "url": "https://www.shl.com/...", "test_type": "K"}], "end_of_conversation": false}

- `recommendations` should be an EMPTY array `[]` when you are still gathering context or refusing out-of-scope queries.
- `recommendations` should contain 1-10 items when you have enough context to commit to a shortlist.
- Each recommendation MUST have `name`, `url`, and `test_type` (single letter: A, B, C, D, E, K, P, S).
- `end_of_conversation` is `true` ONLY when the user explicitly confirms the shortlist is final.

## TEST TYPE CODES
A = Ability & Aptitude, B = Biodata & Situational Judgment, C = Competencies, D = Development & 360, E = Assessment Exercises, K = Knowledge & Skills, P = Personality & Behavior, S = Simulations

## CONVERSATION FLOW
1. **CLARIFY**: Ask 1-2 focused clarifying questions if the query is vague.
2. **RECOMMEND**: Present a shortlist with a Markdown table once you have enough context.
3. **REFINE**: Update the shortlist based on user feedback (add/remove/swap tests).
4. **COMPARE**: When asked to compare products, use only catalog data.
5. **CONFIRM**: When the user agrees with the shortlist, end the conversation.

IMPORTANT: Use ONLY product names and URLs from the catalog data below. Never fabricate."""


class SHLAgent:
    """Conversational agent for SHL assessment recommendations."""

    def __init__(self):
        self.retriever = SHLRetriever()


    # ── Query Extraction ────────────────────────────────────────────────────

    def _extract_query(self, messages: List[Dict]) -> str:
        user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
        return " ".join(user_msgs[-3:]) if user_msgs else ""

    def _extract_constraints(self, messages: List[Dict]) -> Dict:
        full_text = " ".join(m["content"] for m in messages).lower()
        constraints = {}
        dur_match = re.search(r"(?:under|less than|max|within)\s*(\d+)\s*min", full_text)
        if dur_match:
            constraints["max_duration"] = int(dur_match.group(1))
        for pat, lang in {"spanish": "Spanish", "french": "French", "german": "German",
                           "portuguese": "Portuguese", "chinese": "Chinese"}.items():
            if pat in full_text:
                constraints["language"] = lang; break
        if "remote" in full_text:
            constraints["remote_only"] = True
        return constraints

    def _retrieve(self, messages: List[Dict], top_k: int = 15) -> List[Dict]:
        query = self._extract_query(messages)
        c = self._extract_constraints(messages)
        return self.retriever.search(
            query=query, top_k=top_k,
            max_duration=c.get("max_duration"),
            language=c.get("language"),
            remote_only=c.get("remote_only", False),
        )


    # ── Prompt Building ─────────────────────────────────────────────────────

    def _build_catalog_context(self, products: List[Dict]) -> str:
        """Build catalog context string for the LLM."""
        return self.retriever.format_product_context(products) or "No matching products found."


    def _build_system_prompt(self, products: List[Dict], turn_count: int) -> str:
        """Build system prompt for Groq with catalog context and turn awareness."""
        catalog_ctx = self._build_catalog_context(products)
        turn_hint = ""
        if turn_count >= 3:
            turn_hint = (
                "\n\n## TURN AWARENESS\n"
                f"This is turn {turn_count} of a maximum 8-turn conversation. "
                "You should prioritize committing to a recommendation shortlist soon "
                "rather than asking more clarifying questions."
            )
        return (
            SYSTEM_PROMPT
            + "\n\n## RELEVANT CATALOG PRODUCTS (use ONLY these for recommendations)\n"
            + catalog_ctx
            + turn_hint
        )


    # ── Groq LLM ────────────────────────────────────────────────────────────

    def _call_groq(self, system_prompt: str, messages: List[Dict]) -> str:
        """Call Groq API using OpenAI compatible endpoint."""
        if not GROQ_API_KEY:
            raise ValueError("No GROQ_API_KEY configured")

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Build messages: system first, then conversation
        openai_msgs = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = "user" if msg["role"] == "user" else "assistant"
            openai_msgs.append({"role": role, "content": msg["content"]})
            
        payload = {
            "model": GROQ_MODEL,
            "messages": openai_msgs,
            "temperature": 0.3,
            "max_tokens": 2048
        }
        
        for attempt in range(2):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=LLM_TIMEOUT)
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
                if resp.status_code == 429:
                    logger.warning(f"Groq rate-limited (attempt {attempt+1}), retrying...")
                    time.sleep(1.0)
                    continue
                resp.raise_for_status()
            except requests.exceptions.Timeout:
                logger.warning(f"Groq timeout (attempt {attempt+1})")
                if attempt < 1:
                    continue
                raise
            except Exception as e:
                logger.error(f"Groq call failed: {e}")
                if attempt < 1:
                    time.sleep(1.0)
                    continue
                raise
        raise RuntimeError("Groq: all retry attempts exhausted")

    # ── Response Parsing ────────────────────────────────────────────────────

    def _parse_response(self, text: str) -> Dict:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r'\{[\s\S]*\}', text)
            if m:
                try: data = json.loads(m.group())
                except: return {"reply": text, "recommendations": [], "end_of_conversation": False}
            else:
                return {"reply": text, "recommendations": [], "end_of_conversation": False}

        recs = data.get("recommendations") or []
        valid = []
        for rec in recs:
            if not isinstance(rec, dict) or not rec.get("name"): continue
            url = rec.get("url", "")
            tt = rec.get("test_type", "")
            product = self.retriever.get_by_name(rec["name"])
            if product:
                url = url or product.get("url", "")
                if not tt or tt not in "ABCDEKPS":
                    tt = product["testTypes"][0] if product.get("testTypes") else "K"
            if not tt or tt not in "ABCDEKPS": tt = "K"
            valid.append({"name": rec["name"], "url": url or "", "test_type": tt})

        return {
            "reply": data.get("reply", "How can I help with SHL assessments?"),
            "recommendations": valid[:10],
            "end_of_conversation": bool(data.get("end_of_conversation", False)),
        }

    # ── Main Chat Method ────────────────────────────────────────────────────

    def chat(self, messages: List[Dict]) -> Dict:
        if not messages:
            return {
                "reply": "Hello! I'm your SHL Assessment Recommendation Agent. I can help you find the right SHL assessments for your hiring needs. What role are you looking to fill?",
                "recommendations": [], "end_of_conversation": False,
            }

        retrieved = self._retrieve(messages, top_k=15)
        user_turn_count = sum(1 for m in messages if m["role"] == "user")

        # Try Groq (primary)
        if GROQ_API_KEY:
            try:
                system = self._build_system_prompt(retrieved, user_turn_count)
                raw = self._call_groq(system, messages)
                logger.info("LLM response from Groq")
                return self._parse_response(raw)
            except Exception as e:
                logger.warning(f"Groq call failed, falling back to rules-based: {e}")

        # Rules-based fallback (last resort)
        logger.warning("All LLMs unavailable, using rules-based fallback")
        return self._fallback(messages, retrieved, "All LLMs unavailable")

    # ── Rules-Based Fallback ────────────────────────────────────────────────

    def _fallback(self, messages: List[Dict], products: List[Dict], error: str) -> Dict:
        """Smart fallback response without LLM."""
        last_msg = messages[-1].get("content", "") if messages else ""
        user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
        turn_count = len(user_msgs)

        # Out-of-scope check
        for pat in [r"salary|compensation", r"legal|compliance|regulation",
                     r"interview\s+(?:question|tip)", r"resume|cv|cover"]:
            if re.search(pat, last_msg, re.I):
                return {
                    "reply": "I can only help with SHL assessment recommendations. For that topic, please reach out to your HR or legal team. How can I help with SHL assessments?",
                    "recommendations": [], "end_of_conversation": False,
                }

        # Clarify on first vague turn
        if turn_count <= 1 and len(last_msg.split()) < 10:
            return {
                "reply": "I'd be happy to help you find the right SHL assessments! To provide the best recommendations, could you tell me:\n\n1. **What role** are you hiring for?\n2. **What seniority level** (entry, mid, senior, executive)?\n3. **What key skills** or competencies are most important?",
                "recommendations": [], "end_of_conversation": False,
            }

        # Confirmation detection
        if any(re.search(p, last_msg, re.I) for p in
               [r"(?:looks?|that'?s?)\s*good", r"perfect", r"(?:go|proceed)\s*(?:with|ahead)",
                r"finalize", r"lock.*in", r"yes.+(?:final|done|great)",
                r"confirmed?", r"that(?:'s| is)\s+(?:it|all|fine)"]) and turn_count > 1:
            return {"reply": "Great! Your assessment shortlist has been finalized. Good luck with your hiring process!",
                    "recommendations": [], "end_of_conversation": True}

        if products:
            recs = []
            for p in products[:8]:
                tt = p.get("testTypes", ["K"])[0] if p.get("testTypes") else "K"
                recs.append({"name": p["name"], "url": p.get("url", ""), "test_type": tt})
            rows = "\n".join(
                f"| {r['name']} | {TYPE_LABELS.get(r['test_type'], r['test_type'])} | [Link]({r['url']}) |"
                for r in recs
            )
            return {
                "reply": f"Based on your requirements, here are relevant SHL assessments:\n\n| Assessment | Type | Link |\n|---|---|---|\n{rows}\n\nWould you like me to adjust this shortlist?",
                "recommendations": recs, "end_of_conversation": False,
            }

        return {
            "reply": "I'd like to help you find the right SHL assessments. Could you tell me about the role, seniority level, and key skills needed?",
            "recommendations": [], "end_of_conversation": False,
        }
