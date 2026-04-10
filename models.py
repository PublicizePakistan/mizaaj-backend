from sqlalchemy import Column, Integer, String, Date, Time, TIMESTAMP, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)

    gender = Column(String)
    dob = Column(Date)
    tob = Column(Time)
    pob = Column(String)

    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    # ✅ relationships
    attempts = relationship("TestAttempt", back_populates="user")
    payments = relationship("Payment", back_populates="user")
    results = relationship("Result", back_populates="user")


class TestAttempt(Base):
    __tablename__ = "test_attempts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    status = Column(String, default="in_progress")
    result_type = Column(String)

    started_at = Column(TIMESTAMP, default=datetime.utcnow)
    completed_at = Column(TIMESTAMP)

    # ✅ relationships
    user = relationship("User", back_populates="attempts")
    answers = relationship("TestAnswer", back_populates="attempt")
    result = relationship("Result", back_populates="attempt", uselist=False)


class TestAnswer(Base):
    __tablename__ = "test_answers"

    id = Column(Integer, primary_key=True)
    attempt_id = Column(Integer, ForeignKey("test_attempts.id"))

    question_id = Column(Integer)
    selected_option = Column(String)

    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    # ✅ relationship
    attempt = relationship("TestAttempt", back_populates="answers")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    order_id = Column(String, unique=True, index=True)  # 🔥 CRITICAL
    transaction_id = Column(String)

    amount = Column(Integer)
    currency = Column(String, default="PKR")

    status = Column(String, default="pending")  # pending / success / failed

    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    # ✅ relationship
    user = relationship("User", back_populates="payments")


class Result(Base):
    __tablename__ = "results"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    attempt_id = Column(Integer, ForeignKey("test_attempts.id"))

    personality_type = Column(String)
    summary = Column(Text)

    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    # ✅ relationships
    user = relationship("User", back_populates="results")
    attempt = relationship("TestAttempt", back_populates="result")