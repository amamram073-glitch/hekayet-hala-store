from uuid import UUID
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import AiConversation, AiMessage, Finding, Incident, Risk
from app.schemas import AiQuestion
from app.security import Principal, get_principal

router = APIRouter(prefix="/ai", tags=["AI security analyst"])


@router.post("/chat")
async def chat(data: AiQuestion, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    if not settings.ai_api_key:
        raise HTTPException(status_code=503, detail="AI provider is not configured. Set AI_API_KEY and AI_API_BASE to enable analysis.")
    conversation = None
    if data.conversation_id:
        try: cid = UUID(data.conversation_id)
        except ValueError: raise HTTPException(status_code=404, detail="Conversation not found")
        conversation = db.scalar(select(AiConversation).where(AiConversation.id == cid,
            AiConversation.organization_id == principal.organization_id, AiConversation.user_id == principal.user.id))
        if not conversation: raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = AiConversation(organization_id=principal.organization_id, user_id=principal.user.id)
        db.add(conversation)
        db.flush()
    findings = db.scalars(select(Finding).where(Finding.organization_id == principal.organization_id,
        Finding.status.in_(["OPEN", "ACKNOWLEDGED", "IN_PROGRESS"])).limit(50)).all()
    risks = db.scalars(select(Risk).where(Risk.organization_id == principal.organization_id, Risk.status == "OPEN").limit(30)).all()
    incidents = db.scalars(select(Incident).where(Incident.organization_id == principal.organization_id,
        Incident.status.in_(["OPEN", "INVESTIGATING", "CONTAINED"])).limit(20)).all()
    context = {"findings": [{"title": f.title, "severity": f.severity, "description": f.description,
                             "remediation": f.remediation, "status": f.status} for f in findings],
               "risks": [{"title": r.title, "score": r.risk_score, "status": r.status} for r in risks],
               "incidents": [{"title": i.title, "severity": i.severity, "status": i.status} for i in incidents]}
    history = db.scalars(select(AiMessage).where(AiMessage.conversation_id == conversation.id)
                         .order_by(AiMessage.created_at.desc()).limit(12)).all()
    messages = [{"role": "system", "content": "You are CyberShield OS Security Analyst. Use only the supplied organization data. Explicitly label observed data, inference, and recommendation. Never claim actions were performed. Do not propose exploitation or dangerous actions. If evidence is absent, say so. Reply in the user's language."},
                {"role": "system", "content": "Organization-scoped records: " + str(context)}]
    messages.extend({"role": m.role, "content": m.content} for m in reversed(history))
    messages.append({"role": "user", "content": data.question})
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(settings.ai_api_base.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {settings.ai_api_key}"},
                json={"model": settings.ai_model, "messages": messages, "temperature": 0.2})
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as error:
        raise HTTPException(status_code=502, detail=f"AI provider request failed ({error.__class__.__name__})")
    db.add_all([AiMessage(conversation_id=conversation.id, role="user", content=data.question),
                AiMessage(conversation_id=conversation.id, role="assistant", content=answer)])
    db.commit()
    return {"conversation_id": str(conversation.id), "answer": answer,
            "data_scope": "current organization only", "executed_actions": []}
