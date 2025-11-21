from fastapi_utils.tasks import repeat_every
from datetime import datetime, timedelta
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException,  WebSocket
from fastapi.middleware.cors import CORSMiddleware
from app.database import SessionLocal, engine, Base
from app import models, utils
from sqlalchemy.orm import Session
from pydantic import BaseModel
import io
import smtplib
import asyncio

# Pydantic models for API
class MailCreate(BaseModel):
    name: str
    sender: str
    document: str
    recipient: str
    date_sent: str  # ISO format
    status: str = "pending"

class MailStatusUpdate(BaseModel):
    status: str

# Create tables in the database
Base.metadata.create_all(bind=engine)

# Initialize FastAPI
app = FastAPI(title="EKSU Mail Tracking System")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for now
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ✅ Upload Excel or CSV file
# ✅ Upload Excel or CSV file (with full error safety)
@app.post("/upload")
async def upload_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        if not file.filename.endswith((".xlsx", ".csv")):
            raise HTTPException(status_code=400, detail="Upload .xlsx or .csv only")

        content = await file.read()
        filelike = io.BytesIO(content)

        rows = utils.parse_excel_to_rows(filelike)  # Parse Excel/CSV
        utils.simple_match_and_upsert(rows, db)     # Insert/update records safely

        return {"count": len(rows)}

    except Exception as e:
        # Detailed error message instead of generic 500
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


# ✅ Get list of mails
@app.get("/mails")
def list_mails(skip: int = 0, limit: int = 200, db: Session = Depends(get_db)):
    return db.query(models.Mail).order_by(models.Mail.date_sent.desc()).offset(skip).limit(limit).all()

@app.get("/notifications")
def get_notifications(db: Session = Depends(get_db)):
    return db.query(models.Mail).filter(
        models.Mail.notified == True,
        models.Mail.status == "pending"
    ).order_by(models.Mail.date_sent.desc()).all()

@app.put("/mails/{mail_id}/duration")
def update_duration(mail_id: int, hours: int, db: Session = Depends(get_db)):
    mail = db.query(models.Mail).filter(models.Mail.id == mail_id).first()
    if not mail:
        raise HTTPException(status_code=404, detail="Mail not found")

    mail.custom_threshold_hours = hours
    mail.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(mail)
    return {"message": f"Custom threshold updated to {hours} hours", "mail": mail}

@app.get("/overdue-summary")
def get_overdue_summary(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    # Use raw SQL to avoid column issues
    from sqlalchemy import text
    result_incoming = db.execute(text("""
        SELECT COUNT(*) as count FROM mails
        WHERE sender IS NOT NULL AND status = 'pending'
        AND TIMESTAMPDIFF(HOUR, date_sent, NOW()) > 24
    """))
    overdue_incoming = result_incoming.fetchone()[0]

    result_outgoing = db.execute(text("""
        SELECT COUNT(*) as count FROM mails
        WHERE recipient IS NOT NULL AND status = 'pending'
        AND TIMESTAMPDIFF(HOUR, date_sent, NOW()) > 48
    """))
    overdue_outgoing = result_outgoing.fetchone()[0]

    return {"incoming": overdue_incoming, "outgoing": overdue_outgoing}

@app.get("/overdue-mails")
def get_overdue_mails(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    mails = db.query(models.Mail).filter(
        models.Mail.status == "pending",
        ((models.Mail.sender.isnot(None) & ((now - models.Mail.date_sent) > timedelta(hours=24))) |
         (models.Mail.recipient.isnot(None) & ((now - models.Mail.date_sent) > timedelta(hours=48)))),
        (models.Mail.reminder_sent_at.is_(None) | ((now - models.Mail.reminder_sent_at) > timedelta(hours=24)))
    ).all()
    return mails

@app.put("/mails/{mail_id}/reminder-sent")
def mark_reminder_sent(mail_id: int, db: Session = Depends(get_db)):
    # Use raw SQL to avoid column issues
    from sqlalchemy import text
    result = db.execute(text("""
        UPDATE mails SET reminder_sent_at = NOW() WHERE id = :mail_id
    """), {"mail_id": mail_id})
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Mail not found")
    db.commit()
    return {"message": "Reminder sent marked"}

@app.delete("/mails/all")
def delete_all_mails(db: Session = Depends(get_db)):
    db.query(models.Mail).delete()
    db.commit()
    return {"message": "All mails deleted successfully"}

# ✅ Add a single mail
@app.post("/mails")
def create_mail(mail: MailCreate, db: Session = Depends(get_db)):
    try:
        date_sent = datetime.fromisoformat(mail.date_sent.replace('Z', '+00:00'))
        eksu_ref = utils.generate_eksu_ref(db)
        new_mail = models.Mail(
            name=mail.name,
            sender=mail.sender,
            document=mail.document,
            recipient=mail.recipient,
            date_sent=date_sent,
            status=mail.status,
            eksu_ref=eksu_ref
        )
        db.add(new_mail)
        db.commit()
        db.refresh(new_mail)
        return new_mail
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create mail: {str(e)}")

# ✅ Update mail status
@app.put("/mails/{mail_id}/status")
def update_mail_status(mail_id: int, status_update: MailStatusUpdate, db: Session = Depends(get_db)):
    mail = db.query(models.Mail).filter(models.Mail.id == mail_id).first()
    if not mail:
        raise HTTPException(status_code=404, detail="Mail not found")

    mail.status = status_update.status
    mail.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(mail)
    return {"message": "Status updated", "mail": mail}

@app.on_event("startup")
@repeat_every(seconds=3600)  # every 1 hour
def check_pending_mails_task():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        pending_mails = db.query(models.Mail).filter(
            models.Mail.status == "pending",
            models.Mail.notified == False
        ).all()

        for mail in pending_mails:
            threshold_hours = mail.custom_threshold_hours or 48
            time_elapsed = now - mail.date_sent

            if time_elapsed > timedelta(hours=threshold_hours):
                # 🚨 Send system notification here
                print(f"⚠️ Mail '{mail.eksku_ref}' has not been attended to for {threshold_hours} hours!")

                # Mark as notified
                mail.notified = True
                mail.notified_at = datetime.utcnow()
                db.add(mail)
        db.commit()
    finally:
        db.close()


# ✅ Root test endpoint
@app.get("/")
def home():
    return {"message": "EKSU Mail Tracking System API is running successfully!"}

def get_new_alerts_from_db():
    db = SessionLocal()
    try:
        alerts = []
        # Fetch mails that have been notified in the last 10 seconds
        ten_seconds_ago = datetime.utcnow() - timedelta(seconds=10)
        # Use raw SQL to avoid column issues if migration hasn't run
        from sqlalchemy import text
        result = db.execute(text("""
            SELECT id, eksu_ref, sender, recipient, custom_threshold_hours, notified_at
            FROM mails
            WHERE notified = 1 AND notified_at >= :ten_seconds_ago
        """), {"ten_seconds_ago": ten_seconds_ago})

        for row in result:
            alerts.append({
                "ref": row.eksu_ref,
                "message": f"Mail {row.eksu_ref} from {row.sender} to {row.recipient} has not been attended to in {row.custom_threshold_hours or 48} hours.",
                "time": row.notified_at.isoformat() if row.notified_at else None
            })
        return alerts
    finally:
        db.close()


# ✅ WebSocket endpoint for real-time alerts
@app.websocket("/ws/alerts")
async def alerts_ws(websocket: WebSocket):
    await websocket.accept()
    while True:
        alerts = get_new_alerts_from_db()
        if alerts:
            for alert in alerts:
                await websocket.send_json(alert)
        await asyncio.sleep(10)  # check every 10 seconds