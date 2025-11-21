from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .models import Mail
from dateutil import parser
import pandas as pd
import random

# --- EKSU Reference Generator ---
def generate_eksu_ref(db: Session):
    """
    Generates a new sequential EKSU reference like EKSU0001, EKSU0002, etc.
    """
    # Get the highest existing EKSU ref
    last_ref = db.query(Mail.eksu_ref).filter(Mail.eksu_ref.isnot(None)).order_by(Mail.eksu_ref.desc()).first()
    if last_ref and last_ref[0]:
        # Extract the number part, e.g., from "EKSU0001" get 1
        num_str = last_ref[0][4:]  # Skip "EKSU"
        try:
            num = int(num_str)
            next_num = num + 1
        except ValueError:
            next_num = 1
    else:
        next_num = 1
    return f"EKSU{next_num:04d}"

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
        # Flexible column mapping
        name = r.get("name") or r.get("department") or r.get("dept")
        sender = r.get("sender") or r.get("from") or r.get("sender_email")
        document = r.get("document") or r.get("subject") or r.get("mail_subject")
        recipient = r.get("recipient") or r.get("to") or r.get("receiver") or r.get("recipient_email")
        date_sent = r.get("date") or r.get("date_sent") or r.get("sent_date")
        status = r.get("status") or "pending"
        response_date = r.get("response_date") or r.get("reply_date") or r.get("received_date")

        if date_sent:
            try:
                date_val = parser.parse(str(date_sent))
            except:
                date_val = None
        if response_date and not pd.isna(response_date):
            try:
                resp_date = parser.parse(str(response_date))
            except:
                resp_date = None

        rows.append({
            "name": name,
            "sender": sender,
            "document": document,
            "recipient": recipient,
            "date_sent": date_val,
            "status": status,
            "response_date": resp_date
        })
    return rows

# --- Matching + Database Logic ---
def simple_match_and_upsert(rows: list, db: Session):
    """
    For paper mail: matching is done by:
      - Check for existing mail by sender, recipient, document, date_sent.
      - If exists, update status, response_date if provided.
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
            # Update existing mail
            if r["status"] and r["status"] != existing.status:
                existing.status = r["status"]
            if r["response_date"]:
                existing.response_date = r["response_date"]
                existing.status = "completed"  # Mark as completed if reply
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