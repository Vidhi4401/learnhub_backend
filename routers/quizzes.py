from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
import models, schemas
from dependencies import get_current_teacher
from groq import Groq
from config import GROQ_API_KEY
import json

router = APIRouter(tags=["Quizzes"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

client = Groq(api_key=GROQ_API_KEY)

@router.post("/api/v1/teacher/quizzes/generate-ai")
def generate_ai_quiz(
    data: schemas.QuizAIRequest,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    try:
        # Validate Topic
        topic = db.query(models.Topic).filter(models.Topic.id == data.topic_id).first()
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")

        prompt = f"""
        Generate a quiz with {data.num_questions} questions for the topic "{topic.title}".
        Quiz Title: {data.title}
        Description: {data.description}
        Difficulty: {data.difficulty}
        
        Respond ONLY with a JSON array of objects. Each object should have:
        - "question_text": string
        - "option_a": string
        - "option_b": string
        - "option_c": string
        - "option_d": string
        - "correct_option": string (must be A, B, C, or D)
        
        Example:
        [
            {{
                "question_text": "What is 2+2?",
                "option_a": "3",
                "option_b": "4",
                "option_c": "5",
                "option_d": "6",
                "correct_option": "B"
            }}
        ]
        """
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an expert educator. Generate quizzes in JSON format."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"} if "llama-3" in "llama-3.3-70b-versatile" else None
        )
        
        content = completion.choices[0].message.content
        # Sometimes it wraps in a root object or just returns the array
        questions_data = json.loads(content)
        if isinstance(questions_data, dict) and "questions" in questions_data:
            questions_data = questions_data["questions"]
        elif isinstance(questions_data, dict):
            # If it returned a dict but not as expected, find any list in it
            for key, value in questions_data.items():
                if isinstance(value, list):
                    questions_data = value
                    break

        # Create the Quiz
        quiz = models.Quiz(topic_id=data.topic_id, title=data.title, num_questions=data.num_questions)
        db.add(quiz)
        db.commit()
        db.refresh(quiz)
        
        # Add Questions
        for q in questions_data:
            question = models.QuizQuestion(
                quiz_id=quiz.id,
                question_text=q.get("question_text"),
                option_a=q.get("option_a"),
                option_b=q.get("option_b"),
                option_c=q.get("option_c"),
                option_d=q.get("option_d"),
                correct_option=q.get("correct_option", "A").upper()
            )
            db.add(question)
        
        db.commit()
        return {"quiz_id": quiz.id, "message": "Quiz generated successfully"}
    except Exception as e:
        print(f"Error generating AI quiz: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to generate quiz: {str(e)}")

from routers.notifications import create_notification

@router.post("/api/v1/teacher/topics/{topic_id}/quizzes")
def create_quiz(
    topic_id: int,
    data: schemas.QuizCreate,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    quiz = models.Quiz(topic_id=topic_id, title=data.title, num_questions=data.num_questions)
    db.add(quiz)
    db.commit()
    db.refresh(quiz)

    # Notify students
    topic = db.query(models.Topic).filter(models.Topic.id == topic_id).first()
    if topic:
        course = db.query(models.Course).filter(models.Course.id == topic.course_id).first()
        enrolled = db.query(models.Enrollment.student_id).filter(
            models.Enrollment.course_id == topic.course_id
        ).all()
        for (sid,) in enrolled:
            create_notification(
                db, sid,
                "New Quiz Available",
                f"A new quiz '{data.title}' is now available in {course.title if course else 'your course'}.",
                "student-quizzes.html"
            )

    return {"quiz_id": quiz.id}


@router.get("/api/v1/topics/{topic_id}/quizzes")
def get_quizzes(topic_id: int, db: Session = Depends(get_db)):
    return db.query(models.Quiz).filter(
        models.Quiz.topic_id == topic_id
    ).all()


@router.get("/api/v1/quizzes/{quiz_id}")
def get_quiz(quiz_id: int, db: Session = Depends(get_db)):
    quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    questions = db.query(models.QuizQuestion).filter(
        models.QuizQuestion.quiz_id == quiz_id
    ).all()
    return {"quiz": quiz, "questions": questions}


@router.put("/api/v1/teacher/quizzes/{quiz_id}")
def update_quiz(
    quiz_id: int,
    data: schemas.QuizUpdate,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    quiz.title = data.title
    db.commit()
    return {"message": "Quiz updated"}


@router.delete("/api/v1/teacher/quizzes/{quiz_id}")
def delete_quiz(
    quiz_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    db.query(models.QuizQuestion).filter(
        models.QuizQuestion.quiz_id == quiz_id
    ).delete()
    db.delete(quiz)
    db.commit()
    return {"message": "Quiz deleted"}


@router.post("/api/v1/teacher/quizzes/{quiz_id}/questions")
def add_question(
    quiz_id: int,
    data: schemas.QuizQuestionCreate,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    question = models.QuizQuestion(
        quiz_id=quiz_id,
        question_text=data.question_text,
        option_a=data.option_a,
        option_b=data.option_b,
        option_c=data.option_c,
        option_d=data.option_d,
        correct_option=data.correct_option.upper()
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return {"question_id": question.id}


@router.get("/api/v1/quizzes/{quiz_id}/questions")
def get_questions(quiz_id: int, db: Session = Depends(get_db)):
    return db.query(models.QuizQuestion).filter(
        models.QuizQuestion.quiz_id == quiz_id
    ).all()


@router.put("/api/v1/teacher/questions/{question_id}")
def update_question(
    question_id: int,
    data: schemas.QuizQuestionUpdate,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    question = db.query(models.QuizQuestion).filter(
        models.QuizQuestion.id == question_id
    ).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    question.question_text  = data.question_text
    question.option_a       = data.option_a
    question.option_b       = data.option_b
    question.option_c       = data.option_c
    question.option_d       = data.option_d
    question.correct_option = data.correct_option.upper()
    db.commit()
    return {"message": "Question updated"}


@router.delete("/api/v1/teacher/questions/{question_id}")
def delete_question(
    question_id: int,
    db: Session = Depends(get_db),
    teacher: models.User = Depends(get_current_teacher)
):
    question = db.query(models.QuizQuestion).filter(
        models.QuizQuestion.id == question_id
    ).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(question)
    db.commit()
    return {"message": "Question deleted"}
