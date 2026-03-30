from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
import os

from database import SessionLocal, engine
import models, crud, schemas
from utils import verify_password

app = FastAPI()

# ✅ CORS (for frontend connection)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # change later for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Create tables on startup (Railway safe)
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


# ✅ SIGNUP
@app.post("/signup")
def signup(data: schemas.SignupSchema, db: Session = Depends(get_db)):
    existing = crud.get_user_by_email(db, data.email)

    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    user = crud.create_user(db, data)
    return {"user_id": user.id}


# ✅ LOGIN
@app.post("/login")
def login(data: schemas.LoginSchema, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, data.email)

    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {"user_id": user.id}


# ✅ CHECK ACCESS (PAYMENT + TEST CONTROL)
@app.get("/check-access/{user_id}")
def check_access(user_id: int, db: Session = Depends(get_db)):

    # 🔴 Check payment
    payment = crud.has_paid(db, user_id)
    if not payment:
        return {"access": "payment"}

    # 🔴 Check ongoing attempt
    attempt = db.query(models.TestAttempt).filter(
        models.TestAttempt.user_id == user_id,
        models.TestAttempt.status != "completed"
    ).first()

    if attempt:
        return {
            "access": "test",
            "attempt_id": attempt.id
        }

    return {
        "access": "test",
        "attempt_id": None
    }


# ✅ START TEST (PROTECTED)
@app.post("/start-test")
def start_test(user_id: int, db: Session = Depends(get_db)):

    # 🔴 Block if not paid
    payment = crud.has_paid(db, user_id)
    if not payment:
        raise HTTPException(status_code=403, detail="Payment required")

    attempt = crud.create_attempt(db, user_id)
    return {"attempt_id": attempt.id}


# ✅ SAVE ANSWER (SAFE)
@app.post("/answer")
def answer(data: schemas.AnswerSchema, db: Session = Depends(get_db)):
    try:
        crud.save_answer(db, data)
        return {"message": "Saved"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ✅ COMPLETE TEST
@app.post("/complete-test")
def complete_test(attempt_id: int, result_type: str, db: Session = Depends(get_db)):
    result = crud.complete_attempt(db, attempt_id, result_type)

    if not result:
        raise HTTPException(status_code=404, detail="Invalid attempt")

    return {"message": "Completed"}


# ✅ PAYMENT
@app.post("/payment")
def payment(data: schemas.PaymentSchema, db: Session = Depends(get_db)):
    crud.create_payment(db, data)
    return {"message": "Payment successful"}


# ✅ GET RESULT
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


# ✅ OPTIONAL: ROOT CHECK (GOOD FOR DEPLOYMENT TEST)
@app.get("/")
def root():
    return {"message": "Mizaaj API is running 🚀"}


# ✅ PORT (Railway uses env PORT)
PORT = int(os.environ.get("PORT", 8000))