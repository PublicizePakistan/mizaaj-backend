from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
import os
import uuid
import requests
import base64
import hashlib
import hmac

from database import SessionLocal
import models, crud, schemas
from utils import verify_password

app = FastAPI()

# =========================
# 🔐 ENV VARIABLES
# =========================
MERCHANT_ID = os.getenv("MERCHANT_ID")
DATABASE_NAME = os.getenv("DATABASE_NAME")
PAYMENT_SERVICE_ID = os.getenv("PAYMENT_SERVICE_ID")
MERCHANT_USERNAME = os.getenv("MERCHANT_USERNAME")
MERCHANT_PASSWORD = os.getenv("MERCHANT_PASSWORD")
PUBLIC_KEY = os.getenv("PUBLIC_KEY")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

# =========================
# 🌐 CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# 🗄️ DB SESSION
# =========================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# 🔐 AUTH
# =========================
@app.post("/signup")
def signup(data: schemas.SignupSchema, db: Session = Depends(get_db)):
    existing = crud.get_user_by_email(db, data.email)

    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    user = crud.create_user(db, data)
    return {"user_id": user.id}


@app.post("/login")
def login(data: schemas.LoginSchema, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, data.email)

    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {"user_id": user.id}


# =========================
# 🧠 ACCESS CONTROL
# =========================
@app.get("/check-access/{user_id}")
def check_access(user_id: int, db: Session = Depends(get_db)):

    if not crud.has_paid(db, user_id):
        return {"access": "payment"}

    attempt = db.query(models.TestAttempt).filter(
        models.TestAttempt.user_id == user_id,
        models.TestAttempt.status != "completed"
    ).first()

    if attempt:
        return {"access": "test", "attempt_id": attempt.id}

    return {"access": "test", "attempt_id": None}


@app.post("/start-test")
def start_test(user_id: int, db: Session = Depends(get_db)):

    if not crud.has_paid(db, user_id):
        raise HTTPException(status_code=403, detail="Payment required")

    attempt = crud.create_attempt(db, user_id)
    return {"attempt_id": attempt.id}


@app.post("/answer")
def answer(data: schemas.AnswerSchema, db: Session = Depends(get_db)):
    crud.save_answer(db, data)
    return {"message": "Saved"}


@app.post("/complete-test")
def complete_test(attempt_id: int, result_type: str, db: Session = Depends(get_db)):
    result = crud.complete_attempt(db, attempt_id, result_type)

    if not result:
        raise HTTPException(status_code=404, detail="Invalid attempt")

    return {"message": "Completed"}


# =========================
# 💳 CREATE PAYMENT
# =========================
@app.post("/create-payment")
def create_payment(user_id: int, db: Session = Depends(get_db)):

    if crud.has_paid(db, user_id):
        raise HTTPException(status_code=400, detail="Already paid")

    # 🔑 Validate ENV
    if not all([
        MERCHANT_ID,
        DATABASE_NAME,
        PAYMENT_SERVICE_ID,
        MERCHANT_USERNAME,
        MERCHANT_PASSWORD,
        PUBLIC_KEY,
        PRIVATE_KEY
    ]):
        raise HTTPException(status_code=500, detail="Payment config missing")

    amount = int(os.getenv("PAYMENT_AMOUNT", 50))
    order_id = f"ORDER_{uuid.uuid4().hex}"

    # 🔐 Basic Auth
    auth_string = f"{MERCHANT_USERNAME}:{MERCHANT_PASSWORD}"
    auth_base64 = base64.b64encode(auth_string.encode()).decode()

    # 🔐 Signature
    data_to_sign = f"{DATABASE_NAME}|{MERCHANT_ID}|{PAYMENT_SERVICE_ID}|{MERCHANT_PASSWORD}"
    signature_hash = hmac.new(
        PRIVATE_KEY.encode(),
        data_to_sign.encode(),
        hashlib.sha256
    ).hexdigest()

    signature = f"{PUBLIC_KEY}:{signature_hash}"

    url = "https://checkout-ms.dev.dialog-pay.com/api/v1/checkout/session"

    payload = {
        "database_name": DATABASE_NAME,
        "merchant_id": MERCHANT_ID,
        "payment_service_id": PAYMENT_SERVICE_ID,
        "amount": amount,
        "currency": "PKR",
        "order_id": order_id,
        "success_url": "https://mizaaj-frontend.vercel.app/payment-success.html",
        "error_url": "https://mizaaj-frontend.vercel.app/mizaj-payment.html",
        "products": [
            {
                "name": "Mizaaj Personality Test",
                "quantity": 1,
                "price": amount,
                "image": "https://via.placeholder.com/150"
            }
        ]
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth_base64}",
        "x-signature-256": signature
    }

    response = requests.post(url, json=payload, headers=headers)
    data = response.json()

    print("CHECKOUT RESPONSE:", data)

    if response.status_code == 200 and data.get("is_success"):
        return {
            "checkout_url": data["data"]["checkout_url"],
            "order_id": order_id
        }

    raise HTTPException(status_code=400, detail=data)


# =========================
# ✅ VERIFY PAYMENT
# =========================
@app.get("/verify-payment")
def verify_payment(
    merchant_id: str,
    database_name: str,
    order_id: str,
    hash: str,
    user_id: int,
    db: Session = Depends(get_db)
):

    payload = f"{merchant_id}|{database_name}|{order_id}"

    computed_hash = hmac.new(
        PRIVATE_KEY.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()

    # 🔒 secure comparison
    if not hmac.compare_digest(computed_hash, hash):
        raise HTTPException(status_code=400, detail="Invalid payment verification")

    if not crud.has_paid(db, user_id):
        crud.create_payment(db, schemas.PaymentSchema(
            user_id=user_id,
            amount=int(os.getenv("PAYMENT_AMOUNT", 50))
        ))

    return {"message": "Payment verified successfully"}


# =========================
# 📊 RESULT
# =========================
@app.get("/result/{user_id}")
def get_result(user_id: int, db: Session = Depends(get_db)):
    result = db.query(models.Result).filter(
        models.Result.user_id == user_id
    ).first()

    if not result:
        raise HTTPException(status_code=404, detail="No result")

    return {
        "type": result.personality_type,
        "summary": result.summary
    }


# =========================
# 🚀 ROOT
# =========================
@app.get("/")
def root():
    return {"message": "Mizaaj API is running 🚀"}