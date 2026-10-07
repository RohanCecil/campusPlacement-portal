from database import init_db, get_db_connection
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def seed_data():
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    # Hash shared mock password
    hashed_password = pwd_context.hash("Password@123")

    # 1. Insert Base Users
    users = [
        ("student.alice@campus.edu", hashed_password, "STUDENT"),
        ("student.bob@campus.edu", hashed_password, "STUDENT"),
        ("recruiter@techcorp.com", hashed_password, "RECRUITER"),
        ("admin@campus.edu", hashed_password, "ADMIN")
    ]
    cursor.executemany("INSERT INTO users (email, password_hash, role) VALUES (?, ?, ?)", users)

    # Retrieve inserted user IDs
    cursor.execute("SELECT id, email FROM users")
    user_map = {row["email"]: row["id"] for row in cursor.fetchall()}

    # 2. Insert Student Profiles
    profiles = [
        (user_map["student.alice@campus.edu"], "Alice Smith", "CSE", 8.8, 2026, "https://drive.google.com/resume_alice.pdf"),
        (user_map["student.bob@campus.edu"], "Bob Jones", "ECE", 6.9, 2026, "https://drive.google.com/resume_bob.pdf")
    ]
    cursor.executemany("""
        INSERT INTO student_profiles (user_id, full_name, branch, cgpa, graduation_year, resume_url)
        VALUES (?, ?, ?, ?, ?, ?)
    """, profiles)

    # 3. Insert Job Postings
    recruiter_id = user_map["recruiter@techcorp.com"]
    jobs = [
        (recruiter_id, "TechCorp Solutions", "Software Engineer Intern", "Full stack Python and React role.", 7.5, "CSE", "APPROVED"),
        (recruiter_id, "TechCorp Solutions", "Hardware Trainee", "Embedded systems intern position.", 7.0, "ECE", "PENDING")
    ]
    cursor.executemany("""
        INSERT INTO job_postings (recruiter_id, company_name, title, description, min_cgpa, allowed_branch, approval_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, jobs)

    conn.commit()
    conn.close()
    print("Mock database populated successfully!")

if __name__ == "__main__":
    seed_data()