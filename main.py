from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
import os, uuid, requests, base64, hashlib, hmac

from database import engine, SessionLocal
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

#FRONTEND_URL = "https://mizaaj-frontend.vercel.app"
FRONTEND_URL = "https://mizaj.pk"
BACKEND_URL = "https://web-production-1f476a.up.railway.app"

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
# 🗄️ DB
# =========================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
def create_tables():
    models.Base.metadata.create_all(bind=engine)

# =========================
# 🔐 AUTH
# =========================
@app.post("/signup")
def signup(data: schemas.SignupSchema, db: Session = Depends(get_db)):
    if crud.get_user_by_email(db, data.email):
        raise HTTPException(400, "Email exists")
    user = crud.create_user(db, data)
    return {"user_id": user.id}

@app.post("/login")
def login(data: schemas.LoginSchema, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, data.email)
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(401, "Invalid credentials")
    return {"user_id": user.id}

# =========================
# 🧠 ACCESS CONTROL
# =========================
@app.get("/check-access/{user_id}")
def check_access(user_id: int, db: Session = Depends(get_db)):
    if not crud.has_paid(db, user_id):
        return {"access": "payment"}
    return {"access": "test"}


# =========================
# 🧪 START TEST
# =========================
@app.post("/start-test")
def start_test(user_id: int, db: Session = Depends(get_db)):

    if not crud.has_paid(db, user_id):
        raise HTTPException(403, "Payment required")

    attempt = crud.create_attempt(db, user_id)
    return {"attempt_id": attempt.id}


# =========================
# 📝 SAVE ANSWER
# =========================
@app.post("/answer")
def answer(data: schemas.AnswerSchema, db: Session = Depends(get_db)):
    try:
        crud.save_answer(db, data)
        return {"message": "Saved"}
    except Exception as e:
        raise HTTPException(400, str(e))


# =========================
# ✅ COMPLETE TEST
# =========================
@app.post("/complete-test")
def complete_test(attempt_id: int, result_type: str, db: Session = Depends(get_db)):

    if not attempt_id or not result_type:
        raise HTTPException(400, "attempt_id and result_type are required")

    result = crud.complete_attempt(db, attempt_id, result_type)

    if not result:
        raise HTTPException(404, "Invalid attempt")

    return {
        "message": "Completed",
        "personality_type": result.personality_type,
        "user_id": result.user_id
    }


# =========================
# 📊 GET RESULT
# =========================
@app.get("/result/{user_id}")
def get_result(user_id: int, db: Session = Depends(get_db)):

    result = db.query(models.Result).filter(
        models.Result.user_id == user_id
    ).first()

    if not result:
        raise HTTPException(404, "No result")

    return {
        "type": result.personality_type,
        "summary": result.summary
    }

# =========================
# 💳 CREATE PAYMENT
# =========================
@app.post("/create-payment")
def create_payment(user_id: int, db: Session = Depends(get_db)):

    if crud.has_paid(db, user_id):
        raise HTTPException(400, "Already paid")

    order_id = f"ORDER-{uuid.uuid4().hex}"
    amount = int(os.getenv("PAYMENT_AMOUNT", 2500))

    # ✅ SAVE PAYMENT FIRST
    payment = models.Payment(
        user_id=user_id,
        order_id=order_id,
        amount=amount,
        status="pending"
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    # 🔐 Signature
    data_to_sign = f"{DATABASE_NAME}|{MERCHANT_ID}|{PAYMENT_SERVICE_ID}|{MERCHANT_PASSWORD}"
    signature_hash = hmac.new(
        PRIVATE_KEY.encode(),
        data_to_sign.encode(),
        hashlib.sha256
    ).hexdigest()

    signature = f"{PUBLIC_KEY}:{signature_hash}"

    # 🔐 Auth
    auth = base64.b64encode(
        f"{MERCHANT_USERNAME}:{MERCHANT_PASSWORD}".encode()
    ).decode()

    payload = {
        "database_name": DATABASE_NAME,
        "merchant_id": MERCHANT_ID,
        "payment_service_id": PAYMENT_SERVICE_ID,
        "amount": amount,
        "currency": "PKR",
        "order_id": order_id,

        "notification_url": f"{BACKEND_URL}/webhook",
        "success_url": f"{FRONTEND_URL}/payment-success.html",
        "error_url": f"{FRONTEND_URL}/payment-error.html",
        "pending_url": f"{FRONTEND_URL}/payment-pending.html",

        "products": [
            {
                "name": "Mizaaj Personality Test",
                "quantity": 1,
                "price": amount,
                "image": "https://dummyimage.com/300x300/000/fff.png"
            }
        ]
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth}",
        "x-signature-256": signature
    }

    try:
        res = requests.post(
            "https://checkout-ms.dialog-pay.com/api/v1/checkout/session",
            json=payload,
            headers=headers,
            timeout=15
        )

        data = res.json()
        print("PAYMENT RESPONSE:", data)

        if not data.get("is_success"):
            raise HTTPException(400, detail=data)

        return {"checkout_url": data["data"]["checkout_url"]}

    except Exception as e:
        print("PAYMENT ERROR:", str(e))
        raise HTTPException(500, "Payment failed")

# =========================
# 🔔 WEBHOOK (PRODUCTION SAFE)
# =========================
@app.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):

    # 🔐 Basic protection
    signature = request.headers.get("x-signature-256")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature")

    data = await request.json()
    print("WEBHOOK:", data)

    order_id = data.get("order_id")
    status = data.get("status")
    transaction_id = data.get("transaction_id")

    payment = db.query(models.Payment).filter(
        models.Payment.order_id == order_id
    ).first()

    if not payment:
        print("❌ Payment not found:", order_id)
        return {"status": "not_found"}

    # ✅ Update payment
    payment.status = status
    payment.transaction_id = transaction_id

    if status == "success":
        print(f"✅ Payment success for user {payment.user_id}")

    elif status == "failed":
        print(f"❌ Payment failed: {order_id}")

    db.commit()

    return {"status": "ok"}

# =========================
# 🚀 ROOT
# =========================
@app.get("/")
def root():
    return {"message": "Mizaaj API running 🚀"}