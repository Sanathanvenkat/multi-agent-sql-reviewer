"""
agents/style.py
────────────────
Style Specialist Agent — uses lighter model since style is less critical.

Detects:
- Inconsistent keyword casing (SELECT vs select)
- Missing or inconsistent table aliases
- No comments on complex logic
- Deeply nested subqueries that should be CTEs
- Inconsistent naming conventions (snake_case vs camelCase)
- Magic numbers without explanation
- Long lines without formatting
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

# Lighter model for style — saves quota, style needs less reasoning power
MODEL = "llama-3.1-8b-instant"

SYSTEM_PROMPT = """You are a SQL style and readability specialist.

Focus ONLY on style, readability, and maintainability:
- SQL keyword casing consistency (prefer UPPERCASE keywords)
- Table and column aliasing clarity
- Missing comments on complex logic or business rules
- Deep nesting that could use CTEs instead
- Naming convention consistency
- Line length and formatting
- Magic numbers or hardcoded values without context

Scoring: 10 = clean and readable, 0 = very hard to maintain.

Respond ONLY with JSON, no markdown:
{
  "score": float 0-10,
  "summary": "one line style assessment",
  "comments": [
    {
      "severity": "medium|low|info",
      "category": "style",
      "issue": "what the problem is",
      "suggestion": "how to fix it",
      "line_hint": "relevant SQL snippet"
    }
  ]
}
"""


def run_style_agent(sql: str) -> AgentReport:
    response = _client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"Review this SQL for style issues:\n\n{sql}"},
        ],
        max_tokens=768,
        temperature=0,
    )

    raw     = response.choices[0].message.content
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    match   = re.search(r"\{.*\}", cleaned, re.DOTALL)
    data    = json.loads(match.group()) if match else {"score": 5.0, "summary": "Parse error", "comments": []}

    comments = [
        ReviewComment(
            severity   = c.get("severity", "info"),
            category   = c.get("category", "style"),
            issue      = c.get("issue", ""),
            suggestion = c.get("suggestion", ""),
            line_hint  = c.get("line_hint", ""),
        )
        for c in data.get("comments", [])
    ]

    return AgentReport(
        agent    = "Style Agent",
        score    = round(float(data.get("score", 5.0)), 1),
        comments = comments,
        summary  = data.get("summary", ""),
    )