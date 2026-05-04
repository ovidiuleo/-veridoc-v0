import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.ai import extract_fields, suggest_match
from app.db import Base, engine, get_db
from app.models import AuditEvent, Document, ExtractedDocumentFields, MatchDecision, MatchSuggestion, Transaction
from app.sample_data import seed_demo_transactions

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"

UPLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="VeriDoc V0")


def create_audit_event(
    db: Session,
    document_id: int,
    event_type: str,
    actor_user_id: Optional[str],
    payload: Optional[dict[str, Any]] = None,
) -> None:
    db.add(
        AuditEvent(
            document_id=document_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            payload_json=payload or {},
        )
    )
    db.commit()


def search_candidate_transactions(db: Session, extraction: dict[str, Any]) -> list[Transaction]:
    query = db.query(Transaction)

    total_amount = extraction.get("total_amount")
    issue_date = extraction.get("issue_date")

    transactions = query.all()

    if total_amount:
        target_amount = float(total_amount)
        transactions = [
            tx for tx in transactions if abs(float(tx.amount) - target_amount) <= 5.00
        ]

    if issue_date:
        transactions = [
            tx for tx in transactions if tx.transaction_date[:7] == issue_date[:7]
        ] or transactions

    return transactions[:10]


def serialise_document(document: Document) -> dict[str, Any]:
    return {
        "id": document.id,
        "original_filename": document.original_filename,
        "file_url": f"/uploads/{document.stored_filename}",
        "mime_type": document.mime_type,
        "status": document.status,
        "uploaded_by_user_id": document.uploaded_by_user_id,
        "uploaded_at": document.uploaded_at.isoformat(),
    }


def serialise_transaction(tx: Transaction) -> dict[str, Any]:
    return {
        "id": tx.id,
        "transaction_date": tx.transaction_date,
        "amount": tx.amount,
        "direction": tx.direction,
        "description": tx.description,
        "merchant_or_counterparty": tx.merchant_or_counterparty,
        "reference": tx.reference,
        "currency": tx.currency,
    }


def serialise_extraction(extraction: Optional[ExtractedDocumentFields]) -> Optional[dict[str, Any]]:
    if extraction is None:
        return None

    return {
        "supplier_name": extraction.supplier_name,
        "invoice_number": extraction.invoice_number,
        "document_type": extraction.document_type,
        "issue_date": extraction.issue_date,
        "due_date": extraction.due_date,
        "total_amount": extraction.total_amount,
        "vat_amount": extraction.vat_amount,
        "currency": extraction.currency,
        "payment_reference": extraction.payment_reference,
        "possible_job_reference": extraction.possible_job_reference,
        "confidence_notes": extraction.confidence_notes,
        "extraction_confidence": extraction.extraction_confidence,
    }


def serialise_decision(decision: Optional[MatchDecision]) -> Optional[dict[str, Any]]:
    if decision is None:
        return None

    return {
        "decision": decision.decision,
        "transaction_id": decision.transaction_id,
        "decided_by_user_id": decision.decided_by_user_id,
        "decided_at": decision.decided_at.isoformat(),
        "decision_note": decision.decision_note,
    }


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        seed_demo_transactions(db)
    finally:
        db.close()


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/transactions")
def list_transactions(db: Session = Depends(get_db)):
    transactions = db.query(Transaction).order_by(Transaction.transaction_date.desc()).all()
    return [serialise_transaction(tx) for tx in transactions]


@app.get("/api/documents")
def list_documents(db: Session = Depends(get_db)):
    documents = db.query(Document).order_by(Document.uploaded_at.desc()).limit(50).all()
    rows = []

    for document in documents:
        extraction = db.query(ExtractedDocumentFields).filter(
            ExtractedDocumentFields.document_id == document.id
        ).first()

        suggestion = db.query(MatchSuggestion).filter(
            MatchSuggestion.document_id == document.id
        ).order_by(MatchSuggestion.suggested_at.desc()).first()

        decision = db.query(MatchDecision).filter(
            MatchDecision.document_id == document.id
        ).order_by(MatchDecision.decided_at.desc()).first()

        rows.append(
            {
                "document": serialise_document(document),
                "extraction": serialise_extraction(extraction),
                "suggestion": None if suggestion is None else suggestion.raw_suggestion_json,
                "decision": serialise_decision(decision),
            }
        )

    return rows


@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    uploaded_by_user_id: str = Form("demo-user"),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    stored_filename = f"{uuid.uuid4().hex}_{file.filename}"
    storage_path = UPLOADS_DIR / stored_filename

    with storage_path.open("wb") as out_file:
        shutil.copyfileobj(file.file, out_file)

    document = Document(
        original_filename=file.filename,
        stored_filename=stored_filename,
        storage_path=str(storage_path),
        mime_type=file.content_type or "application/octet-stream",
        status="uploaded",
        uploaded_by_user_id=uploaded_by_user_id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    create_audit_event(
        db,
        document.id,
        "document_uploaded",
        uploaded_by_user_id,
        {
            "filename": file.filename,
            "mime_type": document.mime_type,
        },
    )

    extraction_data = extract_fields(
        file_path=str(storage_path),
        mime_type=document.mime_type,
        original_filename=file.filename,
    )

    extraction = ExtractedDocumentFields(
        document_id=document.id,
        document_type=extraction_data["document_type"],
        supplier_name=extraction_data["supplier_name"],
        invoice_number=extraction_data["invoice_number"],
        issue_date=extraction_data["issue_date"],
        due_date=extraction_data["due_date"],
        total_amount=extraction_data["total_amount"],
        vat_amount=extraction_data["vat_amount"],
        currency=extraction_data["currency"],
        payment_reference=extraction_data["payment_reference"],
        possible_job_reference=extraction_data["possible_job_reference"],
        confidence_notes=extraction_data["confidence_notes"],
        extraction_confidence=extraction_data["extraction_confidence"],
        raw_extraction_json=extraction_data["raw_extraction_json"],
    )
    db.add(extraction)
    db.commit()
    db.refresh(extraction)

    create_audit_event(
        db,
        document.id,
        "document_extracted",
        "system",
        {
            "extraction_confidence": extraction.extraction_confidence,
            "supplier_name": extraction.supplier_name,
            "issue_date": extraction.issue_date,
            "total_amount": extraction.total_amount,
        },
    )

    candidate_transactions = search_candidate_transactions(db, extraction_data)
    candidate_payload = [serialise_transaction(tx) for tx in candidate_transactions]

    suggestion_data = suggest_match(extraction_data, candidate_payload)

    suggestion = MatchSuggestion(
        document_id=document.id,
        transaction_id=int(suggestion_data["suggested_transaction_id"]) if suggestion_data["suggested_transaction_id"] else None,
        rank=1,
        suggestion_score=float(suggestion_data.get("suggested_score") or 0.0),
        suggestion_confidence=suggestion_data["confidence"],
        primary_reason=suggestion_data["primary_reason"],
        uncertainty_notes=suggestion_data["uncertainty_notes"],
        raw_suggestion_json=suggestion_data,
    )
    db.add(suggestion)

    if suggestion.transaction_id is not None:
        document.status = "suggested"

    db.commit()
    db.refresh(suggestion)
    db.refresh(document)

    create_audit_event(
        db,
        document.id,
        "match_suggested",
        "system",
        {
            "suggested_transaction_id": suggestion_data["suggested_transaction_id"],
            "confidence": suggestion_data["confidence"],
            "primary_reason": suggestion_data["primary_reason"],
            "uncertainty_notes": suggestion_data["uncertainty_notes"],
        },
    )

    return {
        "document": serialise_document(document),
        "extraction": extraction_data,
        "candidates": candidate_payload,
        "suggestion": suggestion_data,
    }


@app.get("/api/documents/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    extraction = db.query(ExtractedDocumentFields).filter(
        ExtractedDocumentFields.document_id == document_id
    ).first()

    suggestion = db.query(MatchSuggestion).filter(
        MatchSuggestion.document_id == document_id
    ).order_by(MatchSuggestion.suggested_at.desc()).first()

    decision = db.query(MatchDecision).filter(
        MatchDecision.document_id == document_id
    ).order_by(MatchDecision.decided_at.desc()).first()

    return {
        "document": serialise_document(document),
        "extraction": serialise_extraction(extraction),
        "suggestion": None if suggestion is None else suggestion.raw_suggestion_json,
        "decision": serialise_decision(decision),
    }


@app.post("/api/documents/{document_id}/decision")
def record_user_decision(
    document_id: int,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
):
    decision_value = payload.get("decision")
    transaction_id = payload.get("transaction_id")
    decided_by_user_id = payload.get("decided_by_user_id", "demo-user")
    decision_note = payload.get("decision_note")

    if decision_value not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Decision must be approved or rejected.")

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    if decision_value == "approved" and not transaction_id:
        raise HTTPException(status_code=400, detail="Approved decision requires a transaction_id.")

    if transaction_id:
        transaction = db.query(Transaction).filter(Transaction.id == int(transaction_id)).first()
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found.")
    else:
        transaction = None

    latest_suggestion = db.query(MatchSuggestion).filter(
        MatchSuggestion.document_id == document_id
    ).order_by(MatchSuggestion.suggested_at.desc()).first()

    match_decision = MatchDecision(
        document_id=document.id,
        transaction_id=transaction.id if transaction else None,
        decision=decision_value,
        decided_by_user_id=decided_by_user_id,
        based_on_suggestion_id=latest_suggestion.id if latest_suggestion else None,
        decision_note=decision_note,
    )
    db.add(match_decision)

    document.status = "matched" if decision_value == "approved" else "rejected"
    db.commit()
    db.refresh(match_decision)
    db.refresh(document)

    create_audit_event(
        db,
        document.id,
        "match_approved" if decision_value == "approved" else "match_rejected",
        decided_by_user_id,
        {
            "transaction_id": transaction.id if transaction else None,
            "decision_note": decision_note,
        },
    )

    return {
        "document": serialise_document(document),
        "decision": {
            "decision": match_decision.decision,
            "transaction_id": match_decision.transaction_id,
            "decided_by_user_id": match_decision.decided_by_user_id,
            "decided_at": match_decision.decided_at.isoformat(),
            "decision_note": match_decision.decision_note,
        },
    }


@app.get("/api/documents/{document_id}/audit")
def get_audit_trail(document_id: int, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.document_id == document_id)
        .order_by(AuditEvent.occurred_at.asc())
        .all()
    )

    return [
        {
            "event_type": event.event_type,
            "actor_user_id": event.actor_user_id,
            "occurred_at": event.occurred_at.isoformat(),
            "payload_json": event.payload_json,
        }
        for event in events
    ]
