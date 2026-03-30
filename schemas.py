from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date, time


class SignupSchema(BaseModel):
    name: str
    email: EmailStr   # ✅ better validation
    password: str
    gender: Optional[str] = None
    dob: Optional[date] = None   # ✅ fixed
    tob: Optional[time] = None   # ✅ fixed
    pob: Optional[str] = None


class LoginSchema(BaseModel):
    email: EmailStr
    password: str


class AnswerSchema(BaseModel):
    attempt_id: int
    question_id: int
    selected_option: str


class PaymentSchema(BaseModel):
    user_id: int
    amount: int
    payment_method: str
    transaction_id: Optional[str] = None  # ✅ added