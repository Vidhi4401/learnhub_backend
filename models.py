from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from database import Base
from sqlalchemy import Boolean
from sqlalchemy import Float

class Organization(Base):
    __tablename__ = "organizations"

    id           = Column(Integer, primary_key=True, index=True)
    name         = Column(String, unique=True)              # real org name — never changes
    platform_name= Column(String, nullable=True)            # editable display name
    logo         = Column(String, nullable=True)            # uploaded logo path
    email        = Column(String, nullable=True)            # org contact email
    status       = Column(Boolean, default=True)            # active/inactive
    signature_url= Column(String, nullable=True)            # NEW: for admin signature
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    name = Column(String)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(String)
    status = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String)
    difficulty = Column(String(50))
    logo = Column(String) 
    status = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    course_id = Column(Integer, ForeignKey("courses.id"))
    order_number = Column(Integer, nullable=False, default=1)

class TopicProgress(Base):
    __tablename__ = "topic_progress"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id"))
    student_id = Column(Integer, ForeignKey("users.id"))
    completed = Column(Boolean, default=False)

class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"))
    course_id = Column(Integer, ForeignKey("courses.id"))
    enrolled_at = Column(DateTime(timezone=True), server_default=func.now())

class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id"))
    title = Column(String)
    description = Column(String)
    total_marks = Column(Integer)
    model_answer = Column(String)
    file_url = Column(String, nullable=True) # For manual PDF upload  

class AssignmentSubmission(Base):
    __tablename__ = "assignment_submissions"

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id"))
    student_id = Column(Integer, ForeignKey("users.id"))
    student_answer = Column(String)
    obtained_marks = Column(Integer, nullable=True)
    feedback = Column(String, nullable=True)
    is_manual_review = Column(Boolean, default=False)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id"))
    title = Column(String)
    num_questions = Column(Integer, nullable=True) # Limit for manual quizzes
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"))
    question_text = Column(String)
    option_a = Column(String)
    option_b = Column(String)
    option_c = Column(String)
    option_d = Column(String)
    correct_option = Column(String)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"))
    student_id = Column(Integer, ForeignKey("users.id"))
    score = Column(Integer)
    attempted_at = Column(DateTime(timezone=True), server_default=func.now())

class QuizAttemptAnswer(Base):
    __tablename__ = "quiz_attempt_answers"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("quiz_attempts.id"))
    question_id = Column(Integer, ForeignKey("quiz_questions.id"))
    selected_option = Column(String, nullable=True) # A, B, C, or D

class VideoProgress(Base):
    __tablename__ = "video_progress"

    id               = Column(Integer, primary_key=True, index=True)
    student_id       = Column(Integer, ForeignKey("users.id"))
    video_id         = Column(Integer, ForeignKey("videos.id"))   # ← was topic_id
    watch_time       = Column(Integer, default=0)                 # ← add this
    watch_percentage = Column(Integer, default=0)
    skip_count       = Column(Integer, default=0)                 # ← add this
    playback_speed   = Column(Float,   default=1.0)      

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id"))
    video_url = Column(String)
    duration = Column(Integer)  # duration in seconds
    created_at = Column(DateTime, server_default=func.now())

class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"))
    course_id = Column(Integer, ForeignKey("courses.id"))
    eligible = Column(Boolean, default=False)
    status = Column(String(20), default="pending") # pending, verified, rejected
    issued = Column(Boolean, default=False)
    issued_at = Column(DateTime)
    request_date = Column(DateTime, server_default=func.now())


class StudentPerformanceSummary(Base):
    __tablename__ = "student_performance_summary"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), unique=True)
    
    # ML Features (11 total)
    overall_score = Column(Float)
    quiz_average = Column(Float)
    assignment_average = Column(Float)
    completion_rate = Column(Float)
    avg_watch_time = Column(Float)
    quiz_attempt_rate = Column(Float)
    assignment_submission_rate = Column(Float)
    
    # Raw Counts
    videos_completed = Column(Integer, default=0)
    quizzes_attempted = Column(Integer, default=0)
    assignments_submitted = Column(Integer, default=0)
    total_course_items = Column(Integer, default=0)

    learner_level = Column(String(20), nullable=True)        # Filtered view (student)
    global_learner_level = Column(String(20), nullable=True) # Always overall (teacher)
    dropout_risk = Column(String(20), nullable=True, default="Low") 
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())

class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    file_url = Column(String)
    course_id = Column(Integer, ForeignKey("courses.id"))
    teacher_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ChatDoubt(Base):
    __tablename__ = "chat_doubts"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"))
    faculty_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Null if AI mode
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)   # Context for AI/Faculty
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True) 
    query = Column(String)
    response = Column(String, nullable=True)                           # Filled by AI or Faculty
    mode = Column(String)                                              # "AI" or "FACULTY"
    is_read_by_student = Column(Boolean, default=False)                # For student notification badge
    is_read_by_faculty = Column(Boolean, default=False)                # For faculty notification badge
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String, nullable=True)
    meeting_link = Column(String)
    meeting_date = Column(DateTime)
    course_id = Column(Integer, ForeignKey("courses.id"))
    teacher_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Notification(Base):
    __tablename__ = "notifications"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"))
    title       = Column(String)
    message     = Column(String)
    link        = Column(String, nullable=True) # Where to redirect on click
    is_read     = Column(Boolean, default=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

class ContactRequest(Base):
    __tablename__ = "contact_requests"

    id = Column(Integer, primary_key=True, index=True)
    org_name = Column(String, unique=True)
    admin_name = Column(String)
    admin_email = Column(String, unique=True)
    admin_password = Column(String)  # hashed
    status = Column(String, default="pending")  # pending, approved, rejected
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    org_name = Column(String)
    admin_name = Column(String)
    email = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
