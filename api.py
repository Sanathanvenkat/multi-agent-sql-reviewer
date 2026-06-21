"""
api.py
──────
FastAPI app for the multi-agent SQL reviewer.

Endpoints:
  POST /review       — submit raw SQL for review
  POST /review/pr    — submit a GitHub PR URL, reviews all .sql files
  GET  /health       — health check
  GET  /examples     — sample SQL and PR usage

Run:
  uvicorn api:app --reload

Swagger UI:
  http://localhost:8000/docs
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from graph import review_sql
from models import FinalReport
from github_client import fetch_pr, combine_sql_from_pr, PRInfo

app = FastAPI(
    title="Multi-Agent SQL Code Reviewer",
    description=(
        "3 specialist agents review your SQL:\n"
        "- Security Agent (llama-3.3-70b)\n"
        "- Performance Agent (llama-3.3-70b)\n"
        "- Style Agent (llama-3.1-8b)\n\n"
        "Submit raw SQL or a GitHub PR URL containing .sql files."
    ),
    version="1.0.0",
)


# ── Request/Response models ───────────────────────────────────────────────────

class ReviewRequest(BaseModel):
    sql: str = Field(..., description="Raw SQL query or script to review")


class PRReviewRequest(BaseModel):
    pr_url: str = Field(
        ...,
        description="GitHub PR URL e.g. https://github.com/owner/repo/pull/123"
    )


class PRReviewResponse(BaseModel):
    pr_url:      str
    pr_title:    str
    author:      str
    files_reviewed: list[str]
    report:      FinalReport


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "agents": ["security", "performance", "style"]}


@app.post("/review", response_model=FinalReport)
async def review(request: ReviewRequest):
    """
    Submit raw SQL for multi-agent review.
    Returns structured report with per-agent scores and overall verdict.
    """
    if not request.sql.strip():
        raise HTTPException(status_code=422, detail="SQL cannot be empty")
    try:
        return review_sql(request.sql)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review failed: {e}")


@app.post("/review/pr", response_model=PRReviewResponse)
async def review_pr(request: PRReviewRequest):
    """
    Submit a GitHub PR URL to review all .sql files changed in that PR.

    Requires GITHUB_TOKEN in .env with repo scope.

    Example PR URL: https://github.com/owner/repo/pull/123
    """
    try:
        pr = fetch_pr(request.pr_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {e}")

    combined_sql = combine_sql_from_pr(pr)

    try:
        report = review_sql(combined_sql)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review failed: {e}")

    return PRReviewResponse(
        pr_url         = pr.pr_url,
        pr_title       = pr.title,
        author         = pr.author,
        files_reviewed = [f.filename for f in pr.files],
        report         = report,
    )


@app.get("/examples")
async def examples():
    return {
        "raw_sql_examples": {
            "clean": """
SELECT o.order_id, c.customer_name, SUM(oi.quantity * oi.unit_price) AS total
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_date >= '2024-01-01'
GROUP BY o.order_id, c.customer_name
ORDER BY total DESC;
            """.strip(),
            "bad_security": """
DECLARE @query NVARCHAR(500)
SET @query = 'SELECT * FROM users WHERE username = ' + @username
EXEC(@query)
            """.strip(),
            "bad_performance": """
select * from orders, customers
where orders.total > 100
order by orders.created_at
            """.strip(),
        },
        "pr_review_example": {
            "pr_url": "https://github.com/your-username/your-repo/pull/1",
            "note": "PR must contain .sql files. Set GITHUB_TOKEN in .env with repo scope."
        }
    }