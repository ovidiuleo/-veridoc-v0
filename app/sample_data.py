from sqlalchemy.orm import Session

from app.models import Transaction


DEMO_TRANSACTIONS = [
    {
        "transaction_date": "2026-04-02",
        "amount": 24.10,
        "direction": "out",
        "description": "Screwfix Watford",
        "merchant_or_counterparty": "Screwfix",
        "reference": "CARD-02410",
        "currency": "GBP",
    },
    {
        "transaction_date": "2026-04-02",
        "amount": 84.72,
        "direction": "out",
        "description": "Screwfix Watford",
        "merchant_or_counterparty": "Screwfix",
        "reference": "CARD-08472",
        "currency": "GBP",
    },
    {
        "transaction_date": "2026-04-03",
        "amount": 620.00,
        "direction": "out",
        "description": "Holcim invoice payment",
        "merchant_or_counterparty": "Holcim",
        "reference": "INV-2841",
        "currency": "GBP",
    },
    {
        "transaction_date": "2026-04-05",
        "amount": 180.00,
        "direction": "in",
        "description": "Addison Lee payout",
        "merchant_or_counterparty": "Addison Lee",
        "reference": "AL-180",
        "currency": "GBP",
    },
    {
        "transaction_date": "2026-04-06",
        "amount": 210.00,
        "direction": "in",
        "description": "Addison Lee payout",
        "merchant_or_counterparty": "Addison Lee",
        "reference": "AL-210",
        "currency": "GBP",
    },
]


def seed_demo_transactions(db: Session) -> None:
    existing_count = db.query(Transaction).count()
    if existing_count > 0:
        return

    for row in DEMO_TRANSACTIONS:
        db.add(Transaction(**row))

    db.commit()