"""
models.py
─────────
Pydantic v2 models for the multi-agent SQL reviewer.

Every agent returns a structured AgentReport.
The aggregator combines them into a FinalReport.
"""

from enum import Enum
from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"
    INFO     = "info"


class ReviewComment(BaseModel):
    severity:    Severity
    category:    str
    issue:       str
    suggestion:  str
    line_hint:   str = ""   # relevant snippet from the SQL


class AgentReport(BaseModel):
    agent:        str
    score:        float = Field(..., ge=0.0, le=10.0)
    comments:     list[ReviewComment]
    summary:      str


class Verdict(str, Enum):
    APPROVE         = "approve"
    REQUEST_CHANGES = "request_changes"
    BLOCK           = "block"


class FinalReport(BaseModel):
    verdict:          Verdict
    overall_score:    float = Field(..., ge=0.0, le=10.0)
    security_report:  AgentReport
    performance_report: AgentReport
    style_report:     AgentReport
    critical_issues:  list[str]
    summary:          str