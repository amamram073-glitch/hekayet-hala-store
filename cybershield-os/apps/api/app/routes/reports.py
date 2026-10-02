from io import BytesIO
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.dependencies import audit, manager
from app.models import Asset, Finding, Incident, Organization, Report, Risk
from app.security import Principal, get_principal
from app.services.scoring import calculate_score, score_label

router = APIRouter(tags=["reports"])


def _report_data(db: Session, org_id):
    org = db.get(Organization, org_id)
    assets = db.scalars(select(Asset).where(Asset.organization_id == org_id)).all()
    findings = db.scalars(select(Finding).where(Finding.organization_id == org_id, Finding.status.notin_(["RESOLVED", "FALSE_POSITIVE"]))).all()
    risks = db.scalars(select(Risk).where(Risk.organization_id == org_id, Risk.status == "OPEN")).all()
    incidents = db.scalars(select(Incident).where(Incident.organization_id == org_id, Incident.status.notin_(["RESOLVED", "CLOSED"]))).all()
    score = calculate_score(db, org_id)
    return {"organization": org.name if org else "Organization", "security_score": score,
            "risk_level": score_label(score), "assets": len(assets),
            "authorized_assets": sum(a.authorization_status == "AUTHORIZED" for a in assets),
            "findings": [{"title": f.title, "severity": f.severity, "asset_id": str(f.asset_id)} for f in findings],
            "risks": [{"title": r.title, "score": r.risk_score, "treatment": r.treatment} for r in risks],
            "incidents": [{"title": i.title, "severity": i.severity, "status": i.status} for i in incidents]}


@router.get("/reports")
def list_reports(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    rows = db.scalars(select(Report).where(Report.organization_id == principal.organization_id).order_by(Report.created_at.desc())).all()
    return [{"id": str(r.id), "title": r.title, "report_type": r.report_type, "created_at": r.created_at} for r in rows]


@router.post("/reports", status_code=201)
def create_report(request: Request, payload: dict | None = None, principal: Principal = Depends(manager), db: Session = Depends(get_db)):
    report_type = ((payload or {}).get("report_type") or "EXECUTIVE").upper()
    if report_type not in {"EXECUTIVE", "VULNERABILITY", "ASSET", "INCIDENT", "MONTHLY"}:
        raise HTTPException(status_code=422, detail="Unsupported report type")
    data = _report_data(db, principal.organization_id)
    report = Report(organization_id=principal.organization_id, title=f"{report_type.title()} Security Report",
                    report_type=report_type, data=data, created_by=principal.user.id)
    db.add(report)
    db.flush()
    audit(db, principal, request, "REPORT_GENERATED", "report", str(report.id), {"report_type": report_type})
    db.commit()
    return {"id": str(report.id), "title": report.title, "report_type": report.report_type,
            "created_at": report.created_at, "summary": {k: data[k] for k in ("security_score", "risk_level", "assets")}}


@router.get("/reports/{report_id}/pdf")
def download_report(report_id: str, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    try: rid = UUID(report_id)
    except ValueError: raise HTTPException(status_code=404, detail="Report not found")
    row = db.scalar(select(Report).where(Report.id == rid, Report.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Report not found")
    buf = BytesIO()
    doc = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 60
    doc.setTitle(row.title)
    doc.setFont("Helvetica-Bold", 18)
    doc.drawString(48, y, "CyberShield OS | Security Report")
    y -= 32
    doc.setFont("Helvetica", 12)
    fields = [f"Organization: {row.data.get('organization', '')}", f"Report type: {row.report_type}",
              f"Security score: {row.data.get('security_score')} / 100 ({row.data.get('risk_level')})",
              f"Assets: {row.data.get('assets')}  | Authorized assets: {row.data.get('authorized_assets')}",
              "", "Open findings:"]
    fields += [f"- [{x['severity']}] {x['title']}" for x in row.data.get("findings", [])[:30]] or ["- None recorded"]
    fields += ["", "Open risks:"] + [f"- {x['title']} (score {x['score']})" for x in row.data.get("risks", [])[:20]]
    fields += ["", "Open incidents:"] + [f"- [{x['severity']}] {x['title']} — {x['status']}" for x in row.data.get("incidents", [])[:20]]
    fields += ["", "This report reflects records stored in CyberShield OS at generation time.",
               "It is not a legal certification or independent security audit."]
    for line in fields:
        if y < 52:
            doc.showPage(); y = height - 50; doc.setFont("Helvetica", 10)
        doc.drawString(48, y, line[:110])
        y -= 17
    doc.save()
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="cybershield-{row.id}.pdf"'})
