"""
agents/security.py
───────────────────
Security Specialist Agent.

Detects:
- SQL injection patterns (dynamic SQL, string concatenation)
- Hardcoded credentials or sensitive values in queries
- Unsafe use of EXECUTE / EXEC with user input
- Missing parameterization
- Privilege escalation patterns (GRANT, DROP, TRUNCATE in app queries)
"""

import os
import json
import re
from openai import OpenAI
from dotenv import load_dotenv
from models import AgentReport, ReviewComment, Severity

load_dotenv()

_client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1",
)

MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are a SQL security specialist reviewing code for vulnerabilities.

Focus ONLY on security issues:
- SQL injection via string concatenation or dynamic SQL
- Hardcoded passwords, API keys, or sensitive values
- Unsafe EXEC/EXECUTE with non-parameterized input
- Dangerous DDL operations (DROP, TRUNCATE) in application queries
- Overly permissive queries exposing sensitive columns
- Missing input validation patterns

Scoring: 10 = no security issues, 0 = critical vulnerabilities present.

Respond ONLY with JSON, no markdown:
{
  "score": float 0-10,
  "summary": "one line security assessment",
  "comments": [
    {
      "severity": "critical|high|medium|low|info",
      "category": "security",
      "issue": "what the problem is",
      "suggestion": "how to fix it",
      "line_hint": "relevant SQL snippet"
    }
  ]
}
"""


def run_security_agent(sql: str) -> AgentReport:
    response = _client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"Review this SQL for security issues:\n\n{sql}"},
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
            category   = c.get("category", "security"),
            issue      = c.get("issue", ""),
            suggestion = c.get("suggestion", ""),
            line_hint  = c.get("line_hint", ""),
        )
        for c in data.get("comments", [])
    ]

    return AgentReport(
        agent    = "Security Agent",
        score    = round(float(data.get("score", 5.0)), 1),
        comments = comments,
        summary  = data.get("summary", ""),
    )