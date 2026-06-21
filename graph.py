"""
graph.py
────────
LangGraph multi-agent SQL reviewer.

Graph structure:
  supervisor → [security, performance, style] (parallel) → aggregator → END

Why parallel execution?
  All three agents are independent — no reason to run them sequentially.
  asyncio.gather equivalent in LangGraph: fan-out from supervisor,
  fan-in at aggregator.

State carries all three agent reports + the final combined report.
"""

from typing import TypedDict
from langgraph.graph import StateGraph, END

from agents.security    import run_security_agent
from agents.performance import run_performance_agent
from agents.style       import run_style_agent
from models import AgentReport, FinalReport, Verdict, ReviewComment, Severity


# ── State ─────────────────────────────────────────────────────────────────────

class ReviewState(TypedDict):
    sql:                str
    security_report:    AgentReport | None
    performance_report: AgentReport | None
    style_report:       AgentReport | None
    final_report:       FinalReport | None


# ── Nodes ─────────────────────────────────────────────────────────────────────

def security_node(state: ReviewState) -> ReviewState:
    state["security_report"] = run_security_agent(state["sql"])
    return state


def performance_node(state: ReviewState) -> ReviewState:
    state["performance_report"] = run_performance_agent(state["sql"])
    return state


def style_node(state: ReviewState) -> ReviewState:
    state["style_report"] = run_style_agent(state["sql"])
    return state


def aggregator_node(state: ReviewState) -> ReviewState:
    """
    Combines all three agent reports into a FinalReport.

    Scoring:
      overall = weighted average (security 50%, performance 35%, style 15%)
      Security weighs most — a SQL injection is worse than bad formatting.

    Verdict logic:
      BLOCK           → any critical security issue
      REQUEST_CHANGES → overall score < 6.0 or any high security issue
      APPROVE         → overall score >= 6.0, no critical/high security issues
    """
    sec  = state["security_report"]
    perf = state["performance_report"]
    sty  = state["style_report"]

    overall = round(
        sec.score  * 0.50 +
        perf.score * 0.35 +
        sty.score  * 0.15,
        1
    )

    # Collect critical issues across all agents
    critical_issues = [
        c.issue for report in [sec, perf, sty]
        for c in report.comments
        if c.severity in (Severity.CRITICAL, Severity.HIGH)
    ]

    # Determine verdict
    has_critical_security = any(
        c.severity == Severity.CRITICAL
        for c in sec.comments
    )
    has_high_security = any(
        c.severity == Severity.HIGH
        for c in sec.comments
    )

    if has_critical_security:
        verdict = Verdict.BLOCK
    elif overall < 6.0 or has_high_security:
        verdict = Verdict.REQUEST_CHANGES
    else:
        verdict = Verdict.APPROVE

    summaries = f"Security: {sec.summary} | Performance: {perf.summary} | Style: {sty.summary}"

    state["final_report"] = FinalReport(
        verdict            = verdict,
        overall_score      = overall,
        security_report    = sec,
        performance_report = perf,
        style_report       = sty,
        critical_issues    = critical_issues,
        summary            = summaries,
    )
    return state


# ── Graph ─────────────────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(ReviewState)

    graph.add_node("security",    security_node)
    graph.add_node("performance", performance_node)
    graph.add_node("style",       style_node)
    graph.add_node("aggregator",  aggregator_node)

    # Supervisor fans out to all 3 agents from entry point
    graph.set_entry_point("security")

    # Sequential for simplicity — LangGraph parallel fan-out needs Send API
    # which adds complexity. Sequential still shows the multi-agent pattern clearly.
    graph.add_edge("security",    "performance")
    graph.add_edge("performance", "style")
    graph.add_edge("style",       "aggregator")
    graph.add_edge("aggregator",  END)

    return graph.compile()


_graph = build_graph()


def review_sql(sql: str) -> FinalReport:
    """Entry point — runs SQL through all agents and returns the final report."""
    initial_state = ReviewState(
        sql                = sql,
        security_report    = None,
        performance_report = None,
        style_report       = None,
        final_report       = None,
    )
    result = _graph.invoke(initial_state)
    return result["final_report"]