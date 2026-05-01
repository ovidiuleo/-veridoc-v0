from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="uploaded")
    uploaded_by_user_id = Column(String, nullable=False, default="demo-user")
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    extraction = relationship("ExtractedDocumentFields", back_populates="document", uselist=False)
    suggestions = relationship("MatchSuggestion", back_populates="document")
    decisions = relationship("MatchDecision", back_populates="document")
    audit_events = relationship("AuditEvent", back_populates="document")


class ExtractedDocumentFields(Base):
    __tablename__ = "extracted_document_fields"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, unique=True)
    document_type = Column(String, nullable=True)
    supplier_name = Column(String, nullable=True)
    invoice_number = Column(String, nullable=True)
    issue_date = Column(String, nullable=True)
    due_date = Column(String, nullable=True)
    total_amount = Column(String, nullable=True)
    vat_amount = Column(String, nullable=True)
    currency = Column(String, nullable=True)
    payment_reference = Column(String, nullable=True)
    possible_job_reference = Column(String, nullable=True)
    confidence_notes = Column(Text, nullable=False, default="")
    extraction_confidence = Column(String, nullable=False, default="insufficient")
    raw_extraction_json = Column(JSON, nullable=True)
    extracted_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    document = relationship("Document", back_populates="extraction")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_date = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    direction = Column(String, nullable=False)  # in | out
    description = Column(String, nullable=True)
    merchant_or_counterparty = Column(String, nullable=True)
    reference = Column(String, nullable=True)
    currency = Column(String, nullable=False, default="GBP")

    suggestions = relationship("MatchSuggestion", back_populates="transaction")
    decisions = relationship("MatchDecision", back_populates="transaction")


class MatchSuggestion(Base):
    __tablename__ = "match_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    rank = Column(Integer, nullable=False, default=1)
    suggestion_score = Column(Float, nullable=False, default=0.0)
    suggestion_confidence = Column(String, nullable=False, default="insufficient")
    primary_reason = Column(Text, nullable=True)
    uncertainty_notes = Column(Text, nullable=False, default="")
    suggested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    raw_suggestion_json = Column(JSON, nullable=True)

    document = relationship("Document", back_populates="suggestions")
    transaction = relationship("Transaction", back_populates="suggestions")


class MatchDecision(Base):
    __tablename__ = "match_decisions"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    decision = Column(String, nullable=False)  # approved | rejected
    decided_by_user_id = Column(String, nullable=False, default="demo-user")
    decided_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    based_on_suggestion_id = Column(Integer, ForeignKey("match_suggestions.id"), nullable=True)
    decision_note = Column(Text, nullable=True)

    document = relationship("Document", back_populates="decisions")
    transaction = relationship("Transaction", back_populates="decisions")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    event_type = Column(String, nullable=False)
    actor_user_id = Column(String, nullable=True)
    payload_json = Column(JSON, nullable=True)
    occurred_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    document = relationship("Document", back_populates="audit_events")