from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .models import Mail
from dateutil import parser
import pandas as pd
import random

# --- EKSU Reference Generator ---
def generate_eksu_ref(db: Session):
    """
    Generates a new EKSU reference like EKSU-20231201-12345
    """
    date_part = datetime.now().strftime("%Y%m%d")
    random_part = str(random.randint(10000, 99999))
    return f"EKSU-{date_part}-{random_part}"

# --- Excel Parsing ---
def parse_excel_to_rows(file_like) -> list:
    try:
        df = pd.read_excel(file_like)
    except Exception:
        df = pd.read_csv(file_like)
    df.columns = [c.strip().lower() for c in df.columns]
    rows = []
    for _, r in df.iterrows():
        date_val = None
        resp_date = None
        if r.get("date"):
            date_val = parser.parse(str(r.get("date")))
        if r.get("response_date") and not pd.isna(r.get("response_date")):
            resp_date = parser.parse(str(r.get("response_date")))
        rows.append({
            "name": r.get("name"),
            "sender": r.get("from") or r.get("sender"),
            "document": r.get("document"),
            "recipient": r.get("to") or r.get("recipient"),
            "date_sent": date_val,
            "status": r.get("status") or "pending",
            "response_date": resp_date
        })
    return rows

# --- Matching + Database Logic ---
def simple_match_and_upsert(rows: list, db: Session):
    """
    For paper mail: matching is done by:
      - If new row has response_date -> treat as incoming reply; try to find earlier pending mail
        from the other party whose document matches (substring) and mark it completed.
      - Otherwise insert new pending mail.
    """
    for r in rows:
        existing = db.query(Mail).filter(
            Mail.sender == r["sender"],
            Mail.recipient == r["recipient"],
            Mail.document == r["document"],
            Mail.date_sent == r["date_sent"]
        ).first()

        if existing:
            if r["response_date"]:
                existing.response_date = r["response_date"]
                existing.status = "completed"
            db.add(existing)
            db.commit()
            continue

        eksu_ref = generate_eksu_ref(db)

        new = Mail(
            name=r["name"],
            sender=r["sender"],
            document=r["document"],
            recipient=r["recipient"],
            date_sent=r["date_sent"],
            status=r["status"],
            response_date=r["response_date"],
            eksu_ref=eksu_ref  # 👈 Add EKSU ref here
        )

        db.add(new)
        db.commit()
        db.refresh(new)

        # ✅ Attempt to match replies
        if r["response_date"]:
            possible = db.query(Mail).filter(
                Mail.sender == r["recipient"],
                Mail.recipient == r["sender"],
                Mail.status == "pending"
            ).order_by(Mail.date_sent.asc()).all()
            for p in possible:
                if p.document and new.document and p.document.lower() in new.document.lower():
                    p.status = "completed"
                    p.response_date = new.date_sent
                    p.matched_to_id = new.id
                    db.add(p)
                    db.commit()
                    break



def check_pending_mails_and_notify(db):
    """
    Checks for mails pending longer than their allowed duration.
    Returns a list of overdue mails.
    """
    now = datetime.utcnow()
    alerts = []

    mails = db.query(Mail).filter(Mail.status != "completed").all()
    for mail in mails:
        threshold = mail.custom_threshold_hours or 48  # Default = 48h
        deadline = mail.date_sent + timedelta(hours=threshold)

        if now > deadline and not mail.notified:
            alerts.append({
                "eksu_ref": mail.eksu_ref,
                "name": mail.name,
                "sender": mail.sender,
                "recipient": mail.recipient,
                "document": mail.document,
                "status": mail.status,
                "message": f"Mail '{mail.document}' from {mail.sender} to {mail.recipient} is overdue ({threshold}h limit)."
            })
            mail.notified = True
            db.commit()

    return alerts