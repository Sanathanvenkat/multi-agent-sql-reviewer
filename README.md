# Multi-Agent SQL Code Reviewer

3 specialist agents review your SQL independently, then an aggregator combines their findings into a structured verdict.

## Architecture

```
SQL Input
    │
    ▼
┌──────────────────────────────────────────────────┐
│  Security Agent  (llama-3.3-70b)                 │
│  → injection, unsafe EXEC, exposed credentials   │
└──────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────┐
│  Performance Agent  (llama-3.3-70b)              │
│  → SELECT *, cartesian joins, index bypass       │
└──────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────┐
│  Style Agent  (llama-3.1-8b — lighter model)     │
│  → naming, formatting, CTE vs subquery           │
└──────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────┐
│  Aggregator Node                                 │
│  overall = security×0.5 + perf×0.35 + style×0.15│
│  verdict: approve | request_changes | block      │
└──────────────────────────────────────────────────┘
```

## Verdict Logic

| Condition | Verdict |
|---|---|
| Any CRITICAL security issue | `block` |
| Overall score < 6.0 or HIGH security issue | `request_changes` |
| Overall score ≥ 6.0, no critical/high security | `approve` |

## Sample Response

```json
{
  "verdict": "block",
  "overall_score": 2.5,
  "critical_issues": [
    "Dynamic SQL built with string concatenation — SQL injection risk"
  ],
  "security_report": {
    "agent": "Security Agent",
    "score": 1.0,
    "summary": "Critical SQL injection vulnerability via EXEC with user input",
    "comments": [
      {
        "severity": "critical",
        "category": "security",
        "issue": "User input concatenated directly into dynamic SQL",
        "suggestion": "Use parameterized queries or sp_executesql with parameters",
        "line_hint": "SET @query = 'SELECT * FROM users WHERE username = ' + @username"
      }
    ]
  },
  ...
}
```

## Stack

| Component | Tool |
|---|---|
| Agent orchestration | LangGraph |
| Security + Performance | llama-3.3-70b via Groq |
| Style | llama-3.1-8b via Groq (lighter) |
| Structured output | Pydantic v2 |
| API | FastAPI |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # add GROQ_API_KEY
```

## Run

```bash
uvicorn api:app --reload
```

Swagger UI: http://localhost:8000/docs

## Test

```bash
# Get example SQL queries
curl http://localhost:8000/examples

# Review bad SQL
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{"sql": "select * from users, orders where users.id=orders.user_id"}'
```

## Key concepts demonstrated

- **Multi-agent coordination** via LangGraph state graph
- **Specialist agents** — each agent has a focused system prompt and domain
- **Weighted aggregation** — security issues matter more than style
- **Structured handoffs** — each agent returns typed `AgentReport` via Pydantic
- **Model routing** — lighter model for style, stronger for security/performance
- **Fail-safe verdicts** — any critical security issue triggers BLOCK regardless of other scores

## GitHub PR Review

Review actual SQL files in a Pull Request:

```bash
curl -X POST http://localhost:8000/review/pr \
  -H "Content-Type: application/json" \
  -d '{"pr_url": "https://github.com/your-username/your-repo/pull/1"}'
```

Requires `GITHUB_TOKEN` in `.env` with `repo` scope.  
Get one at: github.com/settings/tokens → Generate new token (classic) → tick `repo`

The reviewer:
1. Fetches all `.sql` files changed in the PR via GitHub API
2. Extracts added/modified lines from the diff
3. Runs all 3 agents on the combined SQL
4. Returns report with `files_reviewed` list + full verdict