import os
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Optional

from pypdf import PdfReader


DATE_PATTERNS = [
    r"\b(\d{4}-\d{2}-\d{2})\b",
    r"\b(\d{2}/\d{2}/\d{4})\b",
    r"\b(\d{2}-\d{2}-\d{4})\b",
]

AMOUNT_PATTERN = r"(?i)(?:total|amount due|invoice total|balance due|paid)?[^\d£$€]{0,10}([£$€]?\s?\d+\.\d{2})"
VAT_PATTERN = r"(?i)vat[^\d£$€]{0,10}([£$€]?\s?\d+\.\d{2})"
INVOICE_PATTERN = r"(?i)(?:invoice\s*(?:number|no|#)?|inv\s*#?)[\s:]*([A-Z0-9\-\/]+)"
DUE_DATE_PATTERN = r"(?i)due date[^\d]{0,10}(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4})"
PAYMENT_REFERENCE_PATTERN = r"(?i)(?:payment reference|reference)[^\w]{0,5}([A-Z0-9\-\/]+)"
JOB_REFERENCE_PATTERN = r"(?i)(?:job|project|site)\s*(?:reference|ref|no|#)?[^\w]{0,5}([A-Z0-9\-\/]+)"


def _read_text(file_path: str, mime_type: str) -> str:
    if mime_type == "text/plain":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
            return handle.read()

    if mime_type == "application/pdf":
        reader = PdfReader(file_path)
        text_chunks = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text_chunks.append(page_text)
        return "\n".join(text_chunks)

    return ""


def _normalise_date(raw_value: Optional[str]) -> Optional[str]:
    if not raw_value:
        return None

    raw_value = raw_value.strip()

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw_value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _clean_amount(raw_value: Optional[str]) -> Optional[str]:
    if not raw_value:
        return None
    cleaned = raw_value.replace("£", "").replace("$", "").replace("€", "").replace(",", "").strip()
    try:
        float(cleaned)
        return f"{float(cleaned):.2f}"
    except ValueError:
        return None


def _detect_currency(text: str) -> Optional[str]:
    if "£" in text:
        return "GBP"
    if "€" in text:
        return "EUR"
    if "$" in text:
        return "USD"
    if re.search(r"\bGBP\b", text, flags=re.I):
        return "GBP"
    if re.search(r"\bEUR\b", text, flags=re.I):
        return "EUR"
    if re.search(r"\bUSD\b", text, flags=re.I):
        return "USD"
    return None


def _first_date(text: str) -> Optional[str]:
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return _normalise_date(match.group(1))
    return None


def _find(pattern: str, text: str, group: int = 1) -> Optional[str]:
    match = re.search(pattern, text)
    if not match:
        return None
    value = match.group(group).strip()
    return value if value else None


def _guess_supplier(text: str, original_filename: str) -> Optional[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:5]:
        if len(line) > 2 and re.search(r"[A-Za-z]", line):
            if not re.search(r"invoice|receipt|statement|tax|vat", line, flags=re.I):
                return line

    filename = os.path.basename(original_filename).lower()
    if "screwfix" in filename:
        return "Screwfix"
    if "holcim" in filename:
        return "Holcim"
    if "addison" in filename:
        return "Addison Lee"
    return None


def _guess_document_type(text: str, original_filename: str) -> str:
    lower_text = text.lower()
    lower_name = original_filename.lower()

    if "invoice" in lower_text or "invoice" in lower_name:
        return "invoice"
    if "receipt" in lower_text or "receipt" in lower_name:
        return "receipt"
    if "statement" in lower_text or "statement" in lower_name:
        return "statement"
    if "credit note" in lower_text or "credit_note" in lower_name:
        return "credit_note"
    if "delivery note" in lower_text or "delivery_note" in lower_name:
        return "delivery_note"
    return "unknown"


def extract_fields(file_path: str, mime_type: str, original_filename: str) -> dict[str, Any]:
    text = _read_text(file_path, mime_type)
    document_type = _guess_document_type(text, original_filename)
    supplier_name = _guess_supplier(text, original_filename)
    issue_date = _first_date(text)
    due_date = _normalise_date(_find(DUE_DATE_PATTERN, text))
    total_amount = _clean_amount(_find(AMOUNT_PATTERN, text))
    vat_amount = _clean_amount(_find(VAT_PATTERN, text))
    currency = _detect_currency(text)
    invoice_number = _find(INVOICE_PATTERN, text)
    payment_reference = _find(PAYMENT_REFERENCE_PATTERN, text)
    possible_job_reference = _find(JOB_REFERENCE_PATTERN, text)

    missing = []
    if not supplier_name:
        missing.append("supplier_name")
    if not issue_date:
        missing.append("issue_date")
    if not total_amount:
        missing.append("total_amount")

    if text.strip() == "":
        confidence = "insufficient"
        confidence_notes = "No readable text could be extracted from the document."
    elif len(missing) == 0:
        confidence = "high"
        confidence_notes = "Supplier, issue date, and total amount are clearly supported by the document."
    elif len(missing) == 1:
        confidence = "medium"
        confidence_notes = f"Most core fields are supported, but {missing[0]} could not be extracted reliably."
    else:
        confidence = "low"
        confidence_notes = f"Some core fields are missing or unclear: {', '.join(missing)}."

    return {
        "supplier_name": supplier_name,
        "invoice_number": invoice_number,
        "document_type": document_type,
        "issue_date": issue_date,
        "due_date": due_date,
        "total_amount": total_amount,
        "vat_amount": vat_amount,
        "currency": currency,
        "payment_reference": payment_reference,
        "possible_job_reference": possible_job_reference,
        "confidence_notes": confidence_notes,
        "extraction_confidence": confidence,
        "raw_extraction_json": {
            "readable_text_excerpt": text[:1000],
        },
    }


def _similarity(a: Optional[str], b: Optional[str]) -> float:
    if not a or not b:
        return 0.0
    a_norm = a.lower().strip()
    b_norm = b.lower().strip()
    if a_norm in b_norm or b_norm in a_norm:
        return 1.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def _date_distance_days(a: Optional[str], b: Optional[str]) -> Optional[int]:
    if not a or not b:
        return None
    try:
        a_date = datetime.strptime(a, "%Y-%m-%d").date()
        b_date = datetime.strptime(b, "%Y-%m-%d").date()
        return abs((a_date - b_date).days)
    except ValueError:
        return None


def suggest_match(extracted_fields: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        return {
            "suggested_transaction_id": None,
            "confidence": "insufficient",
            "ranked_candidates": [],
            "primary_reason": None,
            "uncertainty_notes": "No candidate transactions were available.",
        }

    scored = []
    total_amount = extracted_fields.get("total_amount")
    issue_date = extracted_fields.get("issue_date")
    supplier_name = extracted_fields.get("supplier_name")
    payment_reference = extracted_fields.get("payment_reference")

    for tx in candidates:
        score = 0.0
        reasons = []

        if total_amount:
            amount_difference = abs(float(total_amount) - float(tx["amount"]))
            if amount_difference <= 0.01:
                score += 60
                reasons.append("exact amount match")
            elif amount_difference <= 1.00:
                score += 30
                reasons.append("close amount match")

        if issue_date:
            date_gap = _date_distance_days(issue_date, tx["transaction_date"])
            if date_gap is not None:
                if date_gap <= 3:
                    score += 20
                    reasons.append("close date")
                elif date_gap <= 7:
                    score += 10
                    reasons.append("reasonable date proximity")

        supplier_similarity = _similarity(supplier_name, tx.get("merchant_or_counterparty"))
        if supplier_similarity >= 0.9:
            score += 20
            reasons.append("strong supplier similarity")
        elif supplier_similarity >= 0.7:
            score += 10
            reasons.append("some supplier similarity")

        ref_similarity = _similarity(payment_reference, tx.get("reference"))
        if ref_similarity >= 0.9:
            score += 20
            reasons.append("strong reference similarity")
        elif ref_similarity >= 0.7:
            score += 10
            reasons.append("some reference similarity")

        scored.append(
            {
                "transaction_id": str(tx["id"]),
                "score": score,
                "reason": ", ".join(reasons) if reasons else "weak supporting evidence",
            }
        )

    scored.sort(key=lambda row: row["score"], reverse=True)
    top = scored[0]
    second = scored[1] if len(scored) > 1 else None

    if top["score"] < 40:
        return {
            "suggested_transaction_id": None,
            "confidence": "insufficient",
            "ranked_candidates": [],
            "primary_reason": None,
            "uncertainty_notes": "Not enough confidence to suggest a likely match.",
        }

    if second and abs(top["score"] - second["score"]) <= 10 and top["score"] < 80:
        return {
            "suggested_transaction_id": None,
            "confidence": "insufficient",
            "ranked_candidates": [],
            "primary_reason": None,
            "uncertainty_notes": "More than one candidate transaction looks similarly plausible.",
        }

    if top["score"] >= 80:
        confidence = "high"
    elif top["score"] >= 60:
        confidence = "medium"
    else:
        confidence = "low"

    ranked_candidates = [
        {
            "transaction_id": row["transaction_id"],
            "rank": index + 1,
            "reason": row["reason"],
        }
        for index, row in enumerate(scored[:3])
    ]

    return {
        "suggested_transaction_id": top["transaction_id"],
        "confidence": confidence,
        "ranked_candidates": ranked_candidates,
        "primary_reason": top["reason"],
        "uncertainty_notes": "Suggestion only. Final match requires user confirmation.",
    }