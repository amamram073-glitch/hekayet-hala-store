import hashlib
import os
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.dependencies import analyst, audit
from app.models import EvidenceMetadata, Investigation
from app.security import Principal

router = APIRouter(prefix="/investigations", tags=["investigation evidence"])
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024


def _uuid(value: str):
    try: return UUID(value)
    except ValueError: raise HTTPException(status_code=404, detail="Investigation or evidence not found")


def _filename(raw: str | None) -> str:
    name = PurePosixPath((raw or "evidence.bin").replace("\\", "/")).name
    clean = "".join(ch for ch in name if ch.isprintable() and ch not in "\r\n\x00")[:255]
    return clean or "evidence.bin"


@router.post("/{investigation_id}/evidence", status_code=201)
async def upload_evidence(investigation_id: str, request: Request,
    file: UploadFile = File(...), notes: str = Form(default=""),
    principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    iid = _uuid(investigation_id)
    investigation = db.scalar(select(Investigation).where(Investigation.id == iid,
        Investigation.organization_id == principal.organization_id))
    if not investigation: raise HTTPException(status_code=404, detail="Investigation not found")
    if len(notes) > 2000: raise HTTPException(status_code=422, detail="Evidence notes are too long")
    base = Path(settings.evidence_storage_path).resolve()
    try: base.mkdir(parents=True, exist_ok=True)
    except OSError: raise HTTPException(status_code=503, detail="Evidence storage is unavailable")
    file_id = uuid4()
    storage_name = f"{file_id.hex}.evidence"
    target = base / storage_name
    digest = hashlib.sha256()
    total = 0
    try:
        with target.open("xb") as stream:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk: break
                total += len(chunk)
                if total > MAX_EVIDENCE_BYTES:
                    raise HTTPException(status_code=413, detail="Evidence files are limited to 10 MB")
                digest.update(chunk)
                stream.write(chunk)
        if total == 0: raise HTTPException(status_code=422, detail="Evidence file is empty")
        os.chmod(target, 0o600)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except OSError:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="Evidence storage is unavailable")
    finally:
        await file.close()
    row = EvidenceMetadata(organization_id=principal.organization_id,
        investigation_id=iid, uploaded_by_id=principal.user.id,
        filename=_filename(file.filename), media_type=(file.content_type or "application/octet-stream")[:120],
        sha256=digest.hexdigest(), storage_reference=storage_name, notes=notes.strip())
    db.add(row)
    db.flush()
    audit(db, principal, request, "EVIDENCE_UPLOADED", "evidence", str(row.id),
        {"investigation_id": str(iid), "sha256": row.sha256, "size_bytes": total})
    try: db.commit()
    except Exception:
        db.rollback()
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="Evidence metadata could not be saved")
    return {"id": str(row.id), "filename": row.filename, "media_type": row.media_type,
        "size_bytes": total, "sha256": row.sha256, "notes": row.notes, "created_at": row.created_at}


@router.get("/{investigation_id}/evidence/{evidence_id}")
def download_evidence(investigation_id: str, evidence_id: str,
    principal: Principal = Depends(analyst), db: Session = Depends(get_db)):
    iid, eid = _uuid(investigation_id), _uuid(evidence_id)
    row = db.scalar(select(EvidenceMetadata).where(EvidenceMetadata.id == eid,
        EvidenceMetadata.investigation_id == iid,
        EvidenceMetadata.organization_id == principal.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Evidence not found")
    base = Path(settings.evidence_storage_path).resolve()
    target = (base / (row.storage_reference or "")).resolve()
    if target.parent != base or not target.is_file():
        raise HTTPException(status_code=404, detail="Evidence file not found")
    return FileResponse(target, media_type="application/octet-stream",
        filename=_filename(row.filename), headers={"X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store"})
