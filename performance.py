"""
agents/performance.py
──────────────────────
Performance Specialist Agent.

Detects:
- SELECT * (fetches unnecessary columns)
- Missing WHERE clause on large table queries
- Cartesian joins (missing JOIN condition)
- Correlated subqueries that should be CTEs or JOINs
- N+1 query patterns
- Functions on indexed columns in WHERE (index bypass)
- ORDER BY on non-indexed columns in large result sets
- DISTINCT overuse masking join problems
"""

import os
import json
import re
from openai import OpenAI
from dotenv import load_dotenv
from models import AgentReport, ReviewComment

load_dotenv()

_client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1",
)

MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are a SQL performance specialist reviewing queries for efficiency issues.

Focus ONLY on performance issues:
- SELECT * instead of explicit columns
- Missing or weak WHERE clauses that cause full table scans
- Cartesian joins (cross joins without conditions)
- Correlated subqueries that could be rewritten as JOINs or CTEs
- Functions applied to columns in WHERE clauses (bypasses indexes)
- DISTINCT used to hide duplicate rows from bad joins
- Redundant subqueries that could be CTEs for readability and plan reuse
- ORDER BY without LIMIT on large datasets

Scoring: 10 = highly optimized, 0 = severe performance problems.

Respond ONLY with JSON, no markdown:
{
  "score": float 0-10,
  "summary": "one line performance assessment",
  "comments": [
    {
      "severity": "critical|high|medium|low|info",
      "category": "performance",
      "issue": "what the problem is",
      "suggestion": "how to fix it",
      "line_hint": "relevant SQL snippet"
    }
  ]
}
"""


def run_performance_agent(sql: str) -> AgentReport:
    response = _client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"Review this SQL for performance issues:\n\n{sql}"},
        ],
        max_tokens=1024,
        temperature=0,
    )

    raw     = response.choices[0].message.content
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    match   = re.search(r"\{.*\}", cleaned, re.DOTALL)
    data    = json.loads(match.group()) if match else {"score": 5.0, "summary": "Parse error", "comments": []}

    comments = [
        ReviewComment(
            severity   = c.get("severity", "info"),
            category   = c.get("category", "performance"),
            issue      = c.get("issue", ""),
            suggestion = c.get("suggestion", ""),
            line_hint  = c.get("line_hint", ""),
        )
        for c in data.get("comments", [])
    ]

    return AgentReport(
        agent    = "Performance Agent",
        score    = round(float(data.get("score", 5.0)), 1),
        comments = comments,
        summary  = data.get("summary", ""),
    )