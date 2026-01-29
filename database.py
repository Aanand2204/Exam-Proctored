import os
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime
import hashlib

load_dotenv()

def get_db():
    try:
        uri = os.getenv("MONGO_URI")
        db_name = os.getenv("DB_NAME", "proctor_exam_db")
        if not uri:
            return None
        client = MongoClient(uri)
        return client[db_name]
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        return None

def register_user(username, password, role="student"):
    db = get_db()
    if db is None: return False
    if db.users.find_one({"username": username}):
        return False # User already exists
    
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    db.users.insert_one({
        "username": username,
        "password": hashed_password,
        "role": role,
        "created_at": datetime.utcnow()
    })
    return True

def authenticate_user(username, password):
    db = get_db()
    if db is None: return None
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    user = db.users.find_one({"username": username, "password": hashed_password})
    return user

def submit_exam(submission):
    db = get_db()
    if db is None: return
    submission['submission_time'] = datetime.utcnow()
    return db.student_submissions.insert_one(submission)

def get_submissions(student_name=None):
    db = get_db()
    if db is None: return []
    query = {}
    if student_name:
        query = {"student_name": student_name}
    submissions = list(db.student_submissions.find(query).sort("submission_time", -1))
    for s in submissions:
        s['id'] = str(s['_id'])
    return submissions

def log_proctoring_event(event):
    db = get_db()
    if db is None: return
    event['timestamp'] = datetime.utcnow()
    return db.proctoring_logs.insert_one(event)
