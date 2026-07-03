"""
evaluate.py — Replay sample conversations against the agent to validate behavior.

Usage: python evaluate.py [--verbose]
"""
import json
import re
import sys
from pathlib import Path
from agent import SHLAgent

CONV_DIR = Path(__file__).parent / "GenAI_SampleConversations"

# Ground truth: expected product names for each conversation (from sample traces)
GROUND_TRUTH = {
    "C1": {
        "expected_products": [
            "Occupational Personality Questionnaire OPQ32r",
            "OPQ Universal Competency Report 2.0",
            "OPQ Leadership Report",
        ],
        "scenario": "Senior leadership selection",
    },
    "C2": {
        "expected_products": [
            "Smart Interview Live Coding",
            "Linux Programming (General)",
            "Networking and Implementation (New)",
            "SHL Verify Interactive G+",
            "Occupational Personality Questionnaire OPQ32r",
        ],
        "scenario": "Senior Rust engineer for networking infrastructure",
    },
    "C3": {
        "expected_products": [
            "SVAR Spoken English (US) (New)",
            "Contact Center Call Simulation (New)",
            "Entry Level Customer Serv - Retail & Contact Center",
            "Customer Service Phone Simulation",
        ],
        "scenario": "Contact center agent screening",
    },
    "C4": {
        "expected_products": [
            "SHL Verify Interactive – Numerical Reasoning",
            "Financial Accounting (New)",
            "Basic Statistics (New)",
            "Graduate Scenarios",
            "Occupational Personality Questionnaire OPQ32r",
        ],
        "scenario": "Graduate financial analyst hiring",
    },
    "C5": {
        "expected_products": [
            "Global Skills Assessment",
            "Global Skills Development Report",
            "Occupational Personality Questionnaire OPQ32r",
            "OPQ MQ Sales Report",
            "Sales Transformation 2.0 - Individual Contributor",
        ],
        "scenario": "Sales organization re-skilling audit",
    },
    "C6": {
        "expected_products": [
            "Manufac. & Indust. - Safety & Dependability 8.0",
            "Workplace Health and Safety (New)",
        ],
        "scenario": "Chemical plant operator safety hiring",
    },
    "C7": {
        "expected_products": [
            "HIPAA (Security)",
            "Medical Terminology (New)",
            "Microsoft Word 365 - Essentials (New)",
            "Dependability and Safety Instrument (DSI)",
            "Occupational Personality Questionnaire OPQ32r",
        ],
        "scenario": "Bilingual healthcare admin staff (South Texas)",
    },
    "C8": {
        "expected_products": [
            "Microsoft Excel 365 (New)",
            "Microsoft Word 365 (New)",
            "MS Excel (New)",
            "MS Word (New)",
            "Occupational Personality Questionnaire OPQ32r",
        ],
        "scenario": "Admin assistant Excel/Word screening",
    },
    "C9": {
        "expected_products": [
            "Core Java (Advanced Level) (New)",
            "Spring (New)",
            "SQL (New)",
            "Amazon Web Services (AWS) Development (New)",
            "Docker (New)",
            "SHL Verify Interactive G+",
            "Occupational Personality Questionnaire OPQ32r",
        ],
        "scenario": "Senior full-stack engineer (backend-leaning)",
    },
    "C10": {
        "expected_products": [
            "SHL Verify Interactive G+",
            "Graduate Scenarios",
        ],
        "scenario": "Graduate management trainee scheme",
    },
}


def parse_conversation(filepath: Path) -> list:
    """Extract user turns from a sample conversation markdown file."""
    text = filepath.read_text()
    user_turns = []
    # Match **User** followed by > quoted text
    for match in re.finditer(r'\*\*User\*\*\s*\n\s*>\s*(.+)', text):
        user_turns.append(match.group(1).strip())
    return user_turns


def evaluate_conversation(agent: SHLAgent, conv_id: str, user_turns: list, verbose: bool = False) -> dict:
    """Replay a conversation and evaluate the agent's responses."""
    messages = []
    results = []
    
    for i, turn_text in enumerate(user_turns):
        messages.append({"role": "user", "content": turn_text})
        response = agent.chat(messages)
        
        turn_result = {
            "turn": i + 1,
            "user": turn_text,
            "reply_length": len(response["reply"]),
            "num_recommendations": len(response["recommendations"]),
            "rec_names": [r["name"] for r in response["recommendations"]],
            "end_of_conversation": response["end_of_conversation"],
        }
        results.append(turn_result)
        
        if verbose:
            print(f"  Turn {i+1}: User: {turn_text[:80]}...")
            print(f"    Reply: {response['reply'][:150]}...")
            print(f"    Recs: {len(response['recommendations'])}")
            if response["recommendations"]:
                for r in response["recommendations"]:
                    print(f"      - {r['name']} ({r['test_type']})")
            print(f"    End: {response['end_of_conversation']}")
            print()
        
        # Add assistant response to history for next turn
        messages.append({"role": "assistant", "content": response["reply"]})
    
    return {
        "conv_id": conv_id,
        "turns": results,
        "total_turns": len(results),
    }


def score_conversation(eval_result: dict, ground_truth: dict = None) -> dict:
    """Score a conversation evaluation."""
    turns = eval_result["turns"]
    score = {
        "conv_id": eval_result["conv_id"],
        "total_turns": eval_result["total_turns"],
        "has_clarification": any(t["num_recommendations"] == 0 for t in turns[:-1]) if len(turns) > 1 else False,
        "has_recommendations": any(t["num_recommendations"] > 0 for t in turns),
        "final_end": turns[-1]["end_of_conversation"] if turns else False,
    }
    
    if ground_truth:
        expected = set(ground_truth["expected_products"])
        final_recs = set()
        for t in reversed(turns):
            if t["num_recommendations"] > 0:
                final_recs = set(t["rec_names"])
                break
        
        recall = len(expected & final_recs) / len(expected) if expected else 0
        precision = len(expected & final_recs) / len(final_recs) if final_recs else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        score["expected_products"] = list(expected)
        score["retrieved_products"] = list(final_recs)
        score["recall"] = round(recall, 3)
        score["precision"] = round(precision, 3)
        score["f1"] = round(f1, 3)
        score["matched"] = list(expected & final_recs)
        score["missed"] = list(expected - final_recs)
    
    return score


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    
    print("=" * 60)
    print("SHL Agent Evaluation")
    print("=" * 60)
    
    agent = SHLAgent()
    print(f"Catalog: {len(agent.retriever.catalog)} products\n")
    
    conv_files = sorted(CONV_DIR.glob("C*.md"))
    if not conv_files:
        print("No conversation files found!")
        return
    
    all_scores = []
    
    for filepath in conv_files:
        conv_id = filepath.stem
        user_turns = parse_conversation(filepath)
        
        if not user_turns:
            print(f"[{conv_id}] No user turns found, skipping")
            continue
        
        print(f"[{conv_id}] {len(user_turns)} turns")
        if conv_id in GROUND_TRUTH:
            print(f"  Scenario: {GROUND_TRUTH[conv_id]['scenario']}")
        
        eval_result = evaluate_conversation(agent, conv_id, user_turns, verbose=verbose)
        gt = GROUND_TRUTH.get(conv_id)
        score = score_conversation(eval_result, gt)
        all_scores.append(score)
        
        # Print summary
        print(f"  Clarification: {'✓' if score['has_clarification'] else '✗'}")
        print(f"  Recommendations: {'✓' if score['has_recommendations'] else '✗'}")
        print(f"  Final End: {'✓' if score['final_end'] else '✗'}")
        if "f1" in score:
            print(f"  Recall: {score['recall']:.0%} | Precision: {score['precision']:.0%} | F1: {score['f1']:.0%}")
            if score["missed"]:
                print(f"  Missed: {score['missed']}")
        print()
    
    # Overall summary
    print("=" * 60)
    print("OVERALL SUMMARY")
    print("=" * 60)
    n = len(all_scores)
    print(f"Conversations evaluated: {n}")
    print(f"Clarification rate: {sum(1 for s in all_scores if s['has_clarification'])}/{n}")
    print(f"Recommendation rate: {sum(1 for s in all_scores if s['has_recommendations'])}/{n}")
    
    scored = [s for s in all_scores if "f1" in s]
    if scored:
        avg_recall = sum(s["recall"] for s in scored) / len(scored)
        avg_f1 = sum(s["f1"] for s in scored) / len(scored)
        print(f"Avg Recall (ground truth): {avg_recall:.0%}")
        print(f"Avg F1 (ground truth): {avg_f1:.0%}")


if __name__ == "__main__":
    main()
