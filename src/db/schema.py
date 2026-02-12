"""SQLAlchemy models for D-PPG Manager database."""

import os
from datetime import datetime, date

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Text, Date, DateTime,
    ForeignKey, LargeBinary, UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "dppg_manager.db")


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(String)


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True)
    last_name = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    date_of_birth = Column(Date)
    gender = Column(String(1))  # M/F
    id_number = Column(String)
    insurance = Column(String)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    exams = relationship("Exam", back_populates="patient", cascade="all, delete-orphan",
                         order_by="Exam.exam_date.desc()")

    @property
    def full_name(self):
        return f"{self.last_name}, {self.first_name}"


class Exam(Base):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    exam_date = Column(Date, nullable=False, default=date.today)
    complaints = Column(Text)
    diagnosis_text = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    patient = relationship("Patient", back_populates="exams")
    channels = relationship("ExamChannel", back_populates="exam", cascade="all, delete-orphan",
                            order_by="ExamChannel.label_byte.desc()")


class ExamChannel(Base):
    __tablename__ = "exam_channels"

    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)

    # Identification
    label_byte = Column(Integer, nullable=False)
    label_desc = Column(String)
    exam_number = Column(Integer)
    sample_count = Column(Integer)
    samples_blob = Column(LargeBinary)  # zlib-compressed 16-bit LE samples

    # Hardware metadata
    hw_baseline = Column(Integer)
    hw_peak_index = Column(Integer)
    hw_end_index = Column(Integer)
    hw_amplitude = Column(Integer)
    hw_To_samples = Column(Integer)
    hw_Th_samples = Column(Integer)
    hw_Ti = Column(Integer)
    hw_Fo_x100 = Column(Integer)
    hw_flags = Column(Integer)

    # Calculated parameters
    To = Column(Float)
    Th = Column(Float)
    Ti = Column(Float)
    Vo = Column(Float)
    Fo = Column(Float)
    peak_index = Column(Integer)
    baseline_value = Column(Float)
    peak_value = Column(Float)

    exam = relationship("Exam", back_populates="channels")


def get_engine(db_path=None):
    path = db_path or DB_PATH
    engine = create_engine(f"sqlite:///{path}", echo=False)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine=None):
    if engine is None:
        engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()
