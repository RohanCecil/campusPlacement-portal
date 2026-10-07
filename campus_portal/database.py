import sqlite3

DB_NAME = "database.db"

def get_db_connection():
    """Establishes a connection to the SQLite database with Row factory enabled."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Returns query results as dictionary-like objects
    return conn

def init_db():
    """Creates tables for users, profiles, jobs, applications, and audit logs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.executescript("""
    PRAGMA foreign_keys = ON;

    DROP TABLE IF EXISTS audit_logs;
    DROP TABLE IF EXISTS applications;
    DROP TABLE IF EXISTS job_postings;
    DROP TABLE IF EXISTS student_profiles;
    DROP TABLE IF EXISTS users;

    -- Base authentication identity
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT CHECK(role IN ('STUDENT', 'RECRUITER', 'ADMIN')) NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- Student Academic Profiles (1-to-1 with users)
    CREATE TABLE student_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        branch TEXT NOT NULL,
        cgpa REAL NOT NULL,
        graduation_year INTEGER NOT NULL,
        resume_url TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    -- Job Postings created by Recruiters
    CREATE TABLE job_postings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recruiter_id INTEGER NOT NULL,
        company_name TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        min_cgpa REAL NOT NULL,
        allowed_branch TEXT NOT NULL,
        approval_status TEXT CHECK(approval_status IN ('PENDING', 'APPROVED', 'REJECTED')) DEFAULT 'PENDING',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (recruiter_id) REFERENCES users(id) ON DELETE CASCADE
    );

    -- Applications linking Students to Approved Jobs
    CREATE TABLE applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        job_id INTEGER NOT NULL,
        status TEXT CHECK(status IN ('APPLIED', 'SHORTLISTED', 'REJECTED', 'SELECTED')) DEFAULT 'APPLIED',
        applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(student_id, job_id),
        FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (job_id) REFERENCES job_postings(id) ON DELETE CASCADE
    );

    -- Administrative Audit Logs for Approvals/Rejections
    CREATE TABLE audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        target_job_id INTEGER NOT NULL,
        reason TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (admin_id) REFERENCES users(id),
        FOREIGN KEY (target_job_id) REFERENCES job_postings(id)
    );
    """)
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database schema initialized successfully.")