from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
import os
import hashlib
import uuid

from database import SessionLocal, engine
import models, crud, schemas
from utils import verify_password

app = FastAPI()

# ✅ ENV VARIABLES (VERY IMPORTANT)
MERCHANT_ID = os.getenv("MERCHANT_ID")
PROVIDER_ID = os.getenv("PROVIDER_ID")
SERVICE_ID = os.getenv("SERVICE_ID")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

# ✅ CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Create tables
@app.on_event("startup")
def on_startup():
    models.Base.metadata.create_all(bind=engine)


# ✅ DB Dependency
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

    payment = crud.has_paid(db, user_id)
    if not payment:
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

    payment = crud.has_paid(db, user_id)
    if not payment:
        raise HTTPException(status_code=403, detail="Payment required")

    attempt = crud.create_attempt(db, user_id)
    return {"attempt_id": attempt.id}


@app.post("/answer")
def answer(data: schemas.AnswerSchema, db: Session = Depends(get_db)):
    try:
        crud.save_answer(db, data)
        return {"message": "Saved"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/complete-test")
def complete_test(attempt_id: int, result_type: str, db: Session = Depends(get_db)):
    result = crud.complete_attempt(db, attempt_id, result_type)

    if not result:
        raise HTTPException(status_code=404, detail="Invalid attempt")

    return {"message": "Completed"}


# =========================
# 💳 PAYMENT (DIALOG PAY)
# =========================

@app.post("/create-payment")
def create_payment(user_id: int, db: Session = Depends(get_db)):

    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid user")

    # 🔐 prevent duplicate payment
    if crud.has_paid(db, user_id):
        raise HTTPException(status_code=400, detail="Already paid")

    # 🔑 check env
    if not all([MERCHANT_ID, PROVIDER_ID, SERVICE_ID, PRIVATE_KEY]):
        raise HTTPException(status_code=500, detail="Payment config missing")

    amount = "2500"
    order_id = f"ORDER_{uuid.uuid4().hex}"

    # 🔐 SIGNATURE (adjust based on gateway docs)
    raw_string = f"{MERCHANT_ID}{PROVIDER_ID}{SERVICE_ID}{order_id}{amount}{PRIVATE_KEY}"
    signature = hashlib.sha256(raw_string.encode()).hexdigest()

    payload = {
        "merchant_id": MERCHANT_ID,
        "provider_id": PROVIDER_ID,
        "service_id": SERVICE_ID,
        "amount": amount,
        "currency": "PKR",
        "order_id": order_id,
        "user_id": user_id,
        "signature": signature,
        "return_url": "https://mizaaj-frontend.vercel.app/payment-success.html"
    }

    # ❗ IMPORTANT: DO NOT call Dialog Pay here
    return {
        "payment_url": "https://checkout-ms.dev.dialog-pay.com",
        "payload": payload
    }


# =========================
# ✅ VERIFY PAYMENT
# =========================

from fastapi import Request

@app.post("/verify-payment")
def verify_payment(request: Request, db: Session = Depends(get_db)):

    data = request.query_params

    # 🔴 Get values from gateway return URL
    transaction_id = data.get("transaction_id")
    status = data.get("status")
    user_id = data.get("user_id")

    if not transaction_id or not user_id:
        raise HTTPException(status_code=400, detail="Invalid payment response")

    # 🔐 OPTIONAL: verify with gateway API (RECOMMENDED)
    # Example (replace with real Dialog Pay endpoint)
    """
    response = requests.get(
        f"https://checkout-ms.dev.dialog-pay.com/status/{transaction_id}",
        headers={"Authorization": f"Bearer {PRIVATE_KEY}"}
    )

    result = response.json()

    if result.get("status") != "success":
        raise HTTPException(status_code=400, detail="Payment not verified")
    """

    # ✅ Basic check (temporary if no API available)
    if status != "success":
        raise HTTPException(status_code=400, detail="Payment failed")

    # 🔒 Prevent duplicate entry
    if crud.has_paid(db, int(user_id)):
        return {"message": "Already verified"}

    # ✅ Save payment
    crud.create_payment(db, schemas.PaymentSchema(
        user_id=int(user_id),
        amount=2500
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


PORT = int(os.environ.get("PORT", 8000))