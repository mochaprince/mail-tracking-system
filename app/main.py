from fastapi_utils.tasks import repeat_every
from datetime import datetime, timedelta
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException,  WebSocket
from app.database import SessionLocal, engine, Base
from app import models, utils
from sqlalchemy.orm import Session
import io
import smtplib
import asyncio

# Create tables in the database
Base.metadata.create_all(bind=engine)

# Initialize FastAPI
app = FastAPI(title="EKSU Mail Tracking System")

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

        return {"uploaded_rows": len(rows)}

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
        recent_alerts = db.query(models.Mail).filter(
            models.Mail.notified == True,
            models.Mail.notified_at >= ten_seconds_ago
        ).all()

        for mail in recent_alerts:
            alerts.append({
                "ref": mail.eksku_ref,
                "message": f"Mail {mail.eksku_ref} from {mail.sender} to {mail.recipient} has not been attended to in {mail.custom_threshold_hours or 48} hours.",
                "time": mail.notified_at.isoformat() if mail.notified_at else None
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