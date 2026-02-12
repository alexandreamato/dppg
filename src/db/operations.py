"""CRUD operations for D-PPG Manager database."""

import zlib
import struct
from datetime import date, datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from .schema import Patient, Exam, ExamChannel, Settings, get_engine, get_session
from ..models import PPGBlock
from ..analysis import calculate_parameters


class DatabaseOps:
    """Database operations wrapper."""

    def __init__(self, db_path=None):
        self.engine = get_engine(db_path)
        self.session = get_session(self.engine)

    def close(self):
        self.session.close()

    # ---- Settings ----

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.session.query(Settings).filter_by(key=key).first()
        return row.value if row else default

    def set_setting(self, key: str, value: str):
        row = self.session.query(Settings).filter_by(key=key).first()
        if row:
            row.value = value
        else:
            self.session.add(Settings(key=key, value=value))
        self.session.commit()

    def get_all_settings(self) -> dict:
        rows = self.session.query(Settings).all()
        return {r.key: r.value for r in rows}

    # ---- Patients ----

    def add_patient(self, last_name: str, first_name: str, **kwargs) -> Patient:
        patient = Patient(last_name=last_name, first_name=first_name, **kwargs)
        self.session.add(patient)
        self.session.commit()
        return patient

    def update_patient(self, patient_id: int, **kwargs):
        patient = self.session.query(Patient).get(patient_id)
        if patient:
            for k, v in kwargs.items():
                setattr(patient, k, v)
            patient.updated_at = datetime.now()
            self.session.commit()

    def delete_patient(self, patient_id: int):
        patient = self.session.query(Patient).get(patient_id)
        if patient:
            self.session.delete(patient)
            self.session.commit()

    def get_patient(self, patient_id: int) -> Optional[Patient]:
        return self.session.query(Patient).get(patient_id)

    def search_patients(self, query: str = "") -> List[Patient]:
        q = self.session.query(Patient)
        if query:
            pattern = f"%{query}%"
            q = q.filter(
                (Patient.last_name.ilike(pattern)) |
                (Patient.first_name.ilike(pattern)) |
                (Patient.id_number.ilike(pattern))
            )
        return q.order_by(Patient.last_name, Patient.first_name).all()

    def list_patients(self) -> List[Patient]:
        return self.session.query(Patient).order_by(Patient.last_name, Patient.first_name).all()

    # ---- Exams ----

    def add_exam(self, patient_id: int, exam_date: date = None,
                 complaints: str = "", diagnosis_text: str = "") -> Exam:
        exam = Exam(
            patient_id=patient_id,
            exam_date=exam_date or date.today(),
            complaints=complaints,
            diagnosis_text=diagnosis_text,
        )
        self.session.add(exam)
        self.session.commit()
        return exam

    def update_exam(self, exam_id: int, **kwargs):
        exam = self.session.query(Exam).get(exam_id)
        if exam:
            for k, v in kwargs.items():
                setattr(exam, k, v)
            exam.updated_at = datetime.now()
            self.session.commit()

    def delete_exam(self, exam_id: int):
        exam = self.session.query(Exam).get(exam_id)
        if exam:
            self.session.delete(exam)
            self.session.commit()

    def get_exam(self, exam_id: int) -> Optional[Exam]:
        return self.session.query(Exam).get(exam_id)

    def list_exams(self, patient_id: int) -> List[Exam]:
        return (self.session.query(Exam)
                .filter_by(patient_id=patient_id)
                .order_by(Exam.exam_date.desc())
                .all())

    # ---- Exam Channels ----

    def add_channel_from_block(self, exam_id: int, block: PPGBlock) -> ExamChannel:
        """Save a PPGBlock as an ExamChannel in the database."""
        # Compress samples
        samples_bytes = struct.pack(f"<{len(block.samples)}H", *block.samples)
        samples_blob = zlib.compress(samples_bytes)

        # Calculate parameters
        params = calculate_parameters(block)

        channel = ExamChannel(
            exam_id=exam_id,
            label_byte=block.label_byte,
            label_desc=block.label_desc,
            exam_number=block.exam_number,
            sample_count=len(block.samples),
            samples_blob=samples_blob,
            hw_baseline=block.hw_baseline,
            hw_peak_index=block.hw_peak_index,
            hw_end_index=block.hw_end_index,
            hw_amplitude=block.hw_amplitude,
            hw_To_samples=block.hw_To_samples,
            hw_Th_samples=block.hw_Th_samples,
            hw_Ti=block.hw_Ti,
            hw_Fo_x100=block.hw_Fo_x100,
            hw_flags=block.hw_flags,
            To=params.To if params else None,
            Th=params.Th if params else None,
            Ti=params.Ti if params else None,
            Vo=params.Vo if params else None,
            Fo=params.Fo if params else None,
            peak_index=params.peak_index if params else None,
            baseline_value=params.baseline_value if params else None,
            peak_value=params.peak_value if params else None,
        )
        self.session.add(channel)
        self.session.commit()
        return channel

    def get_channel_samples(self, channel: ExamChannel) -> List[int]:
        """Decompress and return samples from an ExamChannel."""
        if not channel.samples_blob:
            return []
        raw = zlib.decompress(channel.samples_blob)
        count = len(raw) // 2
        return list(struct.unpack(f"<{count}H", raw))

    def channel_to_block(self, channel: ExamChannel) -> PPGBlock:
        """Convert an ExamChannel back to a PPGBlock for analysis/display."""
        samples = self.get_channel_samples(channel)
        block = PPGBlock(channel.label_byte, samples, channel.exam_number)
        block.hw_baseline = channel.hw_baseline
        block.hw_peak_index = channel.hw_peak_index
        block.hw_end_index = channel.hw_end_index
        block.hw_amplitude = channel.hw_amplitude
        block.hw_To_samples = channel.hw_To_samples
        block.hw_Th_samples = channel.hw_Th_samples
        block.hw_Ti = channel.hw_Ti
        block.hw_Fo_x100 = channel.hw_Fo_x100
        block.hw_flags = channel.hw_flags
        return block
