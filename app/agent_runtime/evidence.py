"""Evidence quality assessment for Native Agent decisions."""

from __future__ import annotations

from app.agent_runtime.constants import (
    CONFIDENCE_LOW,
    CONFIDENCE_NONE,
    CONFIDENCE_PARTIAL,
    CONFIDENCE_STRONG,
)
from app.agent_runtime.decision import EvidenceAssessment
from app.agent_runtime.state import EvidenceItem


class EvidenceAssessor:
    """Classify tool evidence before the runtime writes conclusions."""

    def assess(self, evidence: EvidenceItem) -> EvidenceAssessment:
        citation = {
            "source": "tool",
            "tool_name": evidence.tool_name,
            "status": evidence.status,
        }
        if evidence.status in {"timeout", "disabled", "forbidden"} or evidence.error:
            return EvidenceAssessment(
                quality="error",
                summary=f"{evidence.tool_name} 返回 {evidence.status}：{evidence.error or '无详情'}",
                citations=[citation],
                confidence=CONFIDENCE_NONE,
            )
        if evidence.status == "approval_required":
            return EvidenceAssessment(
                quality="partial",
                summary=f"{evidence.tool_name} 需要审批才能采集证据。",
                citations=[citation],
                confidence=CONFIDENCE_LOW,
            )
        if evidence.status == "partial":
            return EvidenceAssessment(
                quality="partial",
                summary=f"{evidence.tool_name} 返回了部分证据。",
                citations=[citation],
                confidence=CONFIDENCE_PARTIAL,
            )
        if evidence.output is None or evidence.output == "":
            return EvidenceAssessment(
                quality="empty",
                summary=f"{evidence.tool_name} 未返回可用证据。",
                citations=[citation],
                confidence=CONFIDENCE_NONE,
            )
        return EvidenceAssessment(
            quality="strong",
            summary=f"{evidence.tool_name} 返回了可用证据。",
            citations=[citation],
            confidence=CONFIDENCE_STRONG,
        )

    def handoff_reason(self, assessment: EvidenceAssessment) -> str:
        if assessment.quality == "empty":
            return "insufficient_evidence"
        if assessment.quality == "conflicting":
            return "conflicting_evidence"
        return "evidence_error"
