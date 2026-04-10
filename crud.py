from sqlalchemy.orm import Session
import models
from utils import hash_password


# ✅ CREATE USER
def create_user(db: Session, data):
    user = models.User(
        name=data.name,
        email=data.email,
        password=hash_password(data.password),
        gender=data.gender,
        dob=data.dob,
        tob=data.tob,
        pob=data.pob
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ✅ GET USER
def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()


# ✅ CREATE ATTEMPT
def create_attempt(db: Session, user_id: int):
    attempt = models.TestAttempt(user_id=user_id)
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


# ✅ SAVE ANSWER (SAFE VERSION)
def save_answer(db: Session, data):
    # 🔴 validate attempt exists
    attempt = db.get(models.TestAttempt, data.attempt_id)

    if not attempt:
        raise ValueError("Invalid attempt_id")

    # 🔴 prevent saving after completion
    if attempt.status == "completed":
        raise ValueError("Test already completed")

    ans = models.TestAnswer(**data.dict())
    db.add(ans)
    db.commit()
    return ans


# ✅ COMPLETE TEST + CREATE RESULT (SAFE)
def complete_attempt(db: Session, attempt_id: int, result_type: str):
    attempt = db.get(models.TestAttempt, attempt_id)

    if not attempt:
        return None

    # 🔴 prevent duplicate completion
    if attempt.status == "completed":
        existing = db.query(models.Result).filter(
            models.Result.attempt_id == attempt_id
        ).first()
        return existing

    # ✅ update attempt
    attempt.status = "completed"
    attempt.result_type = result_type

    # 🔴 check if result already exists
    existing = db.query(models.Result).filter(
        models.Result.attempt_id == attempt_id
    ).first()

    if existing:
        return existing

    # ✅ create result
    result = models.Result(
        user_id=attempt.user_id,
        attempt_id=attempt.id,
        personality_type=result_type,
        summary="Generated personality summary..."
    )

    db.add(result)
    db.commit()
    db.refresh(result)

    return result


# ✅ CHECK PAYMENT (STRICT)
def has_paid(db: Session, user_id: int):
    return db.query(models.Payment).filter(
        models.Payment.user_id == user_id,
        models.Payment.status == "success"
    ).first() is not None


# ✅ SAVE RESULT (OPTIONAL UTILITY)
def save_result(db: Session, user_id, attempt_id, personality_type):
    result = models.Result(
        user_id=user_id,
        attempt_id=attempt_id,
        personality_type=personality_type,
        summary="Generated personality summary..."
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result