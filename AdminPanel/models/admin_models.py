# admin_models.py
from sqlalchemy import Column, Integer, String, DateTime, JSON, Float
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

AdminBase = declarative_base()

class TestSession(AdminBase):
    __tablename__ = "test_sessions"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(100), unique=True) # ID от внешнего API
    user_id = Column(String(100))
    mode = Column(String(20))
    status = Column(String(20), default="pending")
    progress = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    tested_objects = Column(JSON)
    stats = Column(JSON)   # Храним stats из JSON результата
    results = Column(JSON) # Храним полный массив результатов