from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class RegisterSchema(BaseModel):
    name: str
    email: str
    password: str
    organization_id: int

class LoginSchema(BaseModel):
    email: str
    password: str

class ForgotPasswordSchema(BaseModel):
    email: str

class ResetPasswordSchema(BaseModel):
    token: str
    new_password: str

class CourseCreate(BaseModel):
    title: str
    description: str
    difficulty: Optional[str] = None
    status: Optional[bool] = True

class CourseUpdate(BaseModel):
    title: str
    description: str
    difficulty: Optional[str]
    status: Optional[bool]

class TopicCreate(BaseModel):
    title: str


class TopicUpdate(BaseModel):
    title: str

class VideoCreate(BaseModel):
    video_url: str
    duration: int


class VideoUpdate(BaseModel):
    video_url: str
    duration: int


class AssignmentCreate(BaseModel):
    model_config = {'protected_namespaces': ()}
    title: str
    description: str
    total_marks: int
    model_answer: Optional[str]


class AssignmentUpdate(BaseModel):
    model_config = {'protected_namespaces': ()}
    title: str
    description: str
    total_marks: int
    model_answer: Optional[str]


class QuizCreate(BaseModel):
    title: str
    num_questions: Optional[int] = None


class QuizUpdate(BaseModel):
    title: str
    num_questions: Optional[int] = None

class QuizAIRequest(BaseModel):
    title: str
    description: str
    num_questions: int
    difficulty: str
    topic_id: int

class AssignmentAIRequest(BaseModel):
    title: str
    description: str
    topic_id: int
    difficulty: str
    num_questions: int

class QuizQuestionCreate(BaseModel):
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str


class QuizQuestionUpdate(BaseModel):
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    organization_id: int
    status: bool

    class Config:
        from_attributes = True

# ── New Chat & Doubt Schemas ──
class ChatDoubtCreate(BaseModel):
    query: str
    topic_id: Optional[int] = None
    course_id: Optional[int] = None
    faculty_id: Optional[int] = None
    mode: str # "AI" or "FACULTY"

class ChatDoubtResponse(BaseModel):
    id: int
    query: str
    response: Optional[str] = None
    mode: str
    is_read_by_student: bool
    created_at: datetime
    student_name: Optional[str] = None

    class Config:
        from_attributes = True

class UnreadCountResponse(BaseModel):
    count: int

class FacultyReplySchema(BaseModel):
    doubt_id: int
    response: str
    faculty_id: int

class StudentPerformanceUpdate(BaseModel):
    overall_score: float
    quiz_average: float
    assignment_average: float
    completion_rate: float
    avg_watch_time: float
    quiz_attempt_rate: float
    assignment_submission_rate: float
    videos_completed: int
    quizzes_attempted: int
    assignments_submitted: int
    total_course_items: int
    is_global: Optional[bool] = False # If true, also update global_learner_level (for teacher)

# ── Admin Portal Schemas ──
class TeacherInvite(BaseModel):
    name: str
    email: str
    password: str

class TeacherStatusUpdate(BaseModel):
    is_active: bool

class AdminPasswordReset(BaseModel):
    new_password: str

class AdminAddUserSchema(BaseModel):
    name: str
    email: str
    password: str

class UserCreate(BaseModel):
    name: str
    email: str
    password: str

class AdminProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None

class OrganizationUpdateSchema(BaseModel):
    org_name: Optional[str] = None
    platform_name: Optional[str] = None

class OrganizationCreate(BaseModel):
    name: str
    platform_name: Optional[str] = None
    admin_name: str
    admin_email: str
    admin_password: str

class OrganizationResponse(BaseModel):
    id: int
    name: str
    platform_name: Optional[str] = None
    logo: Optional[str] = None
    email: Optional[str] = None
    status: bool
    signature_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    organization_id: int
    status: bool
    created_at: datetime

    class Config:
        from_attributes = True

class MeetingCreate(BaseModel):
    title: str
    description: Optional[str] = None
    meeting_link: str
    meeting_date: datetime
    course_id: int

class MeetingResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    meeting_link: str
    meeting_date: datetime
    course_id: int
    teacher_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class MessageResponse(BaseModel):
    id: int
    org_name: str
    admin_name: str
    email: str
    created_at: datetime

    class Config:
        from_attributes = True

class ContactRequestCreate(BaseModel):
    org_name: str
    admin_name: str
    admin_email: str
    admin_password: str

class ContactRequestResponse(BaseModel):
    id: int
    org_name: str
    admin_name: str
    admin_email: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

    class Config:
        from_attributes = True