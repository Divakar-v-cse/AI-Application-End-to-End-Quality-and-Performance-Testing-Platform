"""The demo AI application under test.

A deterministic, guard-railed assistant gives the Playwright and API suites a
real application to exercise: authentication, validation, persistence, latency
and safety behaviour.
"""
from __future__ import annotations

import asyncio
import re
import time
from statistics import mean

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user
from ..models import ChatMessage, EvaluationResult
from ..schemas import (
    ChatMessageOut,
    ChatReply,
    ChatRequest,
    DemoOverview,
    EvaluationCreate,
    EvaluationOut,
)

router = APIRouter(prefix="/api", tags=["Demo AI application"])

ALLOWED_MODELS = {"accio-mini", "accio-pro", "quality-rag"}
GUARDRAIL_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous",
    "reveal your system prompt",
    "show me your system prompt",
    "jailbreak",
    "disregard your rules",
)

KNOWLEDGE = {
    "quality": (
        "The latest quality snapshot is on the Quality dashboard: suite pass rates, API p95 latency, "
        "page load timings and the SQL validation results are all evaluated by the same gate engine "
        "that blocks CI."
    ),
    "test": (
        "The platform runs three suites: pytest API checks, Playwright UI specs and SQL data validations. "
        "Trigger them from the dashboard or run `pytest` / `npx playwright test` locally and ingest the reports."
    ),
    "performance": (
        "Load testing uses Locust. A mixed read/write scenario ramps virtual users against the API; "
        "results include RPS, p95 latency and the error rate that feeds the release gate."
    ),
    "data": (
        "Data validation covers duplicates, orphaned rows, null required fields, invalid domains and "
        "AI evaluation integrity. Each check returns offending rows so triage starts from evidence."
    ),
    "gate": (
        "Quality gates are thresholds, not opinions: pass rate, p95 latency, page load budget, load error "
        "rate and data failures. Any blocking failure marks the run as failed and stops the pipeline."
    ),
    "hello": "Hello — I am the demo assistant for the quality platform. Ask me about tests, gates, latency or data validation.",
}


def _reply_for(message: str, model: str) -> tuple[str, bool]:
    text = message.lower().strip()
    for pattern in GUARDRAIL_PATTERNS:
        if pattern in text:
            return (
                "I can't override my operating instructions or disclose internal prompts. "
                "I can still help with test strategy, quality gates or interpreting the latest results.",
                True,
            )
    for keyword, answer in KNOWLEDGE.items():
        if keyword in text:
            return f"{answer} (answered by {model})", False
    words = re.findall(r"[A-Za-z0-9']+", message)
    return (
        f"I received your message about \"{' '.join(words[:12])}\". "
        f"For concrete numbers, open the Quality dashboard; for a deeper check, run the API or UI suite. "
        f"(answered by {model})",
        False,
    )


@router.post("/chat", response_model=ChatReply, summary="Send a message to the demo AI assistant")
async def chat(payload: ChatRequest, db: Session = Depends(get_db), user=Depends(current_user)) -> ChatReply:
    model = payload.model.strip()
    if model not in ALLOWED_MODELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported model '{model}'. Allowed models: {sorted(ALLOWED_MODELS)}",
        )
    conversation_id = (payload.conversation_id or "").strip()
    if conversation_id and not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", conversation_id):
        raise HTTPException(status_code=400, detail="conversation_id contains invalid characters")
    conversation_id = conversation_id or f"conv-{int(time.time() * 1000):x}"

    db.add(
        ChatMessage(
            conversation_id=conversation_id,
            role="user",
            content=payload.message,
            model=model,
        )
    )
    db.commit()

    started = time.perf_counter()
    await asyncio.sleep(0.04)  # simulated model inference on the demo app
    content, flagged = _reply_for(payload.message, model)
    latency_ms = int((time.perf_counter() - started) * 1000)

    reply = ChatMessage(
        conversation_id=conversation_id,
        role="assistant",
        content=content,
        model=model,
        latency_ms=latency_ms,
        tokens=max(1, len(content.split()) + len(payload.message.split())),
        flagged=flagged,
    )
    db.add(reply)
    db.commit()
    db.refresh(reply)

    messages = list(
        db.scalars(
            select(ChatMessage).where(ChatMessage.conversation_id == conversation_id).order_by(ChatMessage.id)
        ).all()
    )
    return ChatReply(
        conversation_id=conversation_id,
        reply=ChatMessageOut.model_validate(reply),
        messages=[ChatMessageOut.model_validate(m) for m in messages],
        latency_ms=latency_ms,
        flagged=flagged,
    )


@router.get("/chat", summary="List recent demo conversations")
def list_conversations(db: Session = Depends(get_db), _=Depends(current_user)) -> dict:
    rows = db.execute(
        select(
            ChatMessage.conversation_id,
            func.count().label("messages"),
            func.max(ChatMessage.created_at).label("updated_at"),
        )
        .group_by(ChatMessage.conversation_id)
        .order_by(func.max(ChatMessage.created_at).desc())
        .limit(20)
    ).all()
    return {
        "items": [
            {"conversation_id": row.conversation_id, "messages": int(row.messages), "updated_at": row.updated_at}
            for row in rows
        ]
    }


@router.get("/chat/{conversation_id}", summary="Read one conversation")
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    _=Depends(current_user),
) -> dict:
    messages = list(
        db.scalars(
            select(ChatMessage).where(ChatMessage.conversation_id == conversation_id).order_by(ChatMessage.id)
        ).all()
    )
    if not messages:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    return {
        "conversation_id": conversation_id,
        "messages": [ChatMessageOut.model_validate(m) for m in messages],
    }


@router.get("/demo/overview", response_model=DemoOverview, summary="Demo application KPIs")
def overview(db: Session = Depends(get_db), _=Depends(current_user)) -> DemoOverview:
    total_messages = int(db.scalar(select(func.count()).select_from(ChatMessage)) or 0)
    conversations = int(db.scalar(select(func.count(func.distinct(ChatMessage.conversation_id)))) or 0)
    assistant_latencies = [
        float(v) for v in db.scalars(select(ChatMessage.latency_ms).where(ChatMessage.role == "assistant")).all()
    ]
    flagged = int(db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.flagged.is_(True))) or 0)
    assistant_count = int(
        db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.role == "assistant")) or 0
    )
    evaluations = list(
        db.scalars(select(EvaluationResult).order_by(EvaluationResult.created_at.desc()).limit(8)).all()
    )
    eval_count = int(db.scalar(select(func.count()).select_from(EvaluationResult)) or 0)
    avg_score = db.scalar(select(func.avg(EvaluationResult.score)))
    recent = db.execute(
        select(ChatMessage.conversation_id, func.max(ChatMessage.created_at))
        .group_by(ChatMessage.conversation_id)
        .order_by(func.max(ChatMessage.created_at).desc())
        .limit(8)
    ).all()
    conv_items = []
    for conversation_id, updated_at in recent:
        last = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.id.desc())
            .limit(1)
        ).first()
        conv_items.append(
            {
                "conversation_id": conversation_id,
                "updated_at": updated_at,
                "preview": (last.content[:90] if last else ""),
            }
        )
    return DemoOverview(
        total_conversations=conversations,
        total_messages=total_messages,
        avg_latency_ms=round(mean(assistant_latencies), 2) if assistant_latencies else 0.0,
        success_rate=round((assistant_count - flagged) / assistant_count * 100, 2) if assistant_count else 100.0,
        flagged_messages=flagged,
        avg_eval_score=round(float(avg_score), 2) if avg_score is not None else 0.0,
        evaluations=eval_count,
        recent_evaluations=[EvaluationOut.model_validate(e) for e in evaluations],
        conversations=conv_items,
    )


@router.get("/demo/evaluations", response_model=list[EvaluationOut], summary="List AI evaluations")
def list_evaluations(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(current_user),
) -> list[EvaluationOut]:
    rows = db.scalars(select(EvaluationResult).order_by(EvaluationResult.created_at.desc()).limit(limit)).all()
    return [EvaluationOut.model_validate(row) for row in rows]


@router.post("/demo/evaluations", response_model=EvaluationOut, status_code=201, summary="Record an AI evaluation")
def create_evaluation(
    payload: EvaluationCreate,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> EvaluationOut:
    conversation_id = payload.conversation_id.strip()
    if conversation_id:
        exists = db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.conversation_id == conversation_id))
        if not exists:
            raise HTTPException(status_code=400, detail="Unknown conversation_id — evaluate an existing conversation")
    evaluation = EvaluationResult(
        conversation_id=conversation_id,
        model=payload.model,
        prompt=payload.prompt,
        score=payload.score,
        verdict="pass" if payload.score >= 70 else "review",
        latency_ms=0,
        reviewer=payload.reviewer or user.email,
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)
    return EvaluationOut.model_validate(evaluation)
