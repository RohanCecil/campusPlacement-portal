from datetime import datetime, timedelta
import jwt
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import List, Optional
from passlib.context import CryptContext
from database import get_db_connection

app = FastAPI(title="Campus Placement Portal API", version="1.0")

SECRET_KEY = "python_campus_portal_secret_key"
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# -------------------------------------------------------------
# PYDANTIC SCHEMAS (Request/Response Models)
# -------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    password: str

class JobCreateRequest(BaseModel):
    company_name: str
    title: str
    description: str
    min_cgpa: float = Field(..., ge=0.0, le=10.0)
    allowed_branch: str  # e.g., 'CSE', 'ECE', or 'ALL'

class ApplyRequest(BaseModel):
    job_id: int

class StatusUpdateRequest(BaseModel):
    application_ids: List[int]
    new_status: str  # 'SHORTLISTED', 'REJECTED', or 'SELECTED'

class AdminModerateRequest(BaseModel):
    job_id: int
    action: str  # 'APPROVED' or 'REJECTED'
    reason: Optional[str] = "N/A"

# -------------------------------------------------------------
# AUTHENTICATION & DEPENDENCY INJECTION
# -------------------------------------------------------------
def get_current_user(authorization: str = Header(...)):
    """Extracts and verifies JWT bearer token from HTTP Request Headers."""
    try:
        scheme, token = authorization.split(" ")
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authorization header scheme")
        
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload  # Contains 'id', 'email', 'role'
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def require_role(allowed_role: str):
    """Enforces Role-Based Access Control (RBAC)."""
    def role_checker(user: dict = Depends(get_current_user)):
        if user["role"] != allowed_role:
            raise HTTPException(status_code=403, detail=f"Forbidden: Access restricted to {allowed_role} role")
        return user
    return role_checker

# -------------------------------------------------------------
# AUTHENTICATION ROUTE
# -------------------------------------------------------------
@app.post("/api/login")
def login(credentials: LoginRequest):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (credentials.email,)).fetchone()
    conn.close()

    if not user or not pwd_context.verify(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token_data = {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "exp": datetime.utcnow() + timedelta(hours=8)
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    return {"token": token, "role": user["role"], "user_id": user["id"]}

# -------------------------------------------------------------
# STUDENT WORKFLOW ROUTES
# -------------------------------------------------------------
@app.get("/api/student/jobs")
def get_approved_jobs(user: dict = Depends(require_role("STUDENT"))):
    """Returns all jobs approved by Placement Cell Admin."""
    conn = get_db_connection()
    jobs = conn.execute("SELECT * FROM job_postings WHERE approval_status = 'APPROVED'").fetchall()
    conn.close()
    return [dict(job) for job in jobs]

@app.post("/api/student/apply")
def apply_to_job(data: ApplyRequest, user: dict = Depends(require_role("STUDENT"))):
    """SERVER-SIDE ELIGIBILITY GATING ROUTE: Validates CGPA & branch before applying."""
    student_id = user["id"]
    conn = get_db_connection()

    # 1. Fetch Student Profile
    profile = conn.execute("SELECT * FROM student_profiles WHERE user_id = ?", (student_id,)).fetchone()
    if not profile:
        conn.close()
        raise HTTPException(status_code=400, detail="Student profile is incomplete")

    # 2. Fetch Job Details
    job = conn.execute("SELECT * FROM job_postings WHERE id = ? AND approval_status = 'APPROVED'", (data.job_id,)).fetchone()
    if not job:
        conn.close()
        raise HTTPException(status_code=404, detail="Approved job opening not found")

    # 3. SERVER-SIDE ELIGIBILITY GATING EVALUATION
    if profile["cgpa"] < job["min_cgpa"]:
        conn.close()
        raise HTTPException(
            status_code=403,
            detail=f"Application blocked: Your CGPA ({profile['cgpa']}) is below required minimum ({job['min_cgpa']})"
        )

    if job["allowed_branch"] != "ALL" and profile["branch"] != job["allowed_branch"]:
        conn.close()
        raise HTTPException(
            status_code=403,
            detail=f"Application blocked: Your branch '{profile['branch']}' is not eligible for this role"
        )

    # 4. Record Application
    try:
        conn.execute("INSERT INTO applications (student_id, job_id) VALUES (?, ?)", (student_id, data.job_id))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="You have already applied for this opening")

    conn.close()
    return {"message": "Application submitted successfully!"}

@app.get("/api/student/applications")
def track_applications(user: dict = Depends(require_role("STUDENT"))):
    """Pipeline tracking view for student applicant."""
    conn = get_db_connection()
    apps = conn.execute("""
        SELECT a.id, a.status, a.applied_at, j.title, j.company_name
        FROM applications a
        JOIN job_postings j ON a.job_id = j.id
        WHERE a.student_id = ?
    """, (user["id"],)).fetchall()
    conn.close()
    return [dict(app_row) for app_row in apps]

# -------------------------------------------------------------
# RECRUITER WORKFLOW ROUTES
# -------------------------------------------------------------
@app.post("/api/recruiter/jobs")
def create_job(data: JobCreateRequest, user: dict = Depends(require_role("RECRUITER"))):
    """Publishes a job posting in PENDING state awaiting admin approval."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO job_postings (recruiter_id, company_name, title, description, min_cgpa, allowed_branch, approval_status)
        VALUES (?, ?, ?, ?, ?, ?, 'PENDING')
    """, (user["id"], data.company_name, data.title, data.description, data.min_cgpa, data.allowed_branch))
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"message": "Job submitted for Admin Approval", "job_id": job_id}

@app.patch("/api/recruiter/applications/status")
def update_application_status(data: StatusUpdateRequest, user: dict = Depends(require_role("RECRUITER"))):
    """Batch updates applicant pipeline statuses."""
    conn = get_db_connection()
    for app_id in data.application_ids:
        conn.execute("UPDATE applications SET status = ? WHERE id = ?", (data.new_status, app_id))
    conn.commit()
    conn.close()
    return {"message": f"Updated {len(data.application_ids)} application(s) to {data.new_status}"}

# -------------------------------------------------------------
# PLACEMENT CELL ADMIN ROUTES
# -------------------------------------------------------------
@app.get("/api/admin/pending-jobs")
def list_pending_jobs(user: dict = Depends(require_role("ADMIN"))):
    """Dedicated portal view of company postings awaiting clearance."""
    conn = get_db_connection()
    jobs = conn.execute("SELECT * FROM job_postings WHERE approval_status = 'PENDING'").fetchall()
    conn.close()
    return [dict(job) for job in jobs]

@app.post("/api/admin/moderate-job")
def moderate_job(data: AdminModerateRequest, user: dict = Depends(require_role("ADMIN"))):
    """Approves or rejects postings and generates an administrative audit trail."""
    conn = get_db_connection()
    try:
        conn.execute("BEGIN TRANSACTION")
        # 1. Update Posting Approval Status
        conn.execute("UPDATE job_postings SET approval_status = ? WHERE id = ?", (data.action, data.job_id))
        
        # 2. Record Administrative Action in Audit Log
        conn.execute("""
            INSERT INTO audit_logs (admin_id, action, target_job_id, reason)
            VALUES (?, ?, ?, ?)
        """, (user["id"], data.action, data.job_id, data.reason))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail="Database transaction failed")
    
    conn.close()
    return {"message": f"Posting {data.job_id} set to {data.action} and logged."}

@app.get("/api/admin/logs")
def view_audit_logs(user: dict = Depends(require_role("ADMIN"))):
    """Retrieves immutable administrative audit trail."""
    conn = get_db_connection()
    logs = conn.execute("""
        SELECT l.id, u.email as admin_email, l.action, l.target_job_id, l.reason, l.timestamp
        FROM audit_logs l
        JOIN users u ON l.admin_id = u.id
    """, ()).fetchall()
    conn.close()
    return [dict(log) for log in logs]