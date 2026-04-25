"""
Advanced Excel export for student reports.
Multi-sheet, fully formatted using xlsxwriter.
"""

import io
from datetime import datetime
import xlsxwriter


# ── Colour palette ────────────────────────────────────────────────────────────
PURPLE      = "#a78bfa"
PURPLE_LIGHT= "#f5f3ff"
DARK        = "#475569"
GREEN       = "#22c55e"
GREEN_LIGHT = "#f0fdf4"
AMBER       = "#f59e0b"
AMBER_LIGHT = "#fffbeb"
RED         = "#ef4444"
RED_LIGHT   = "#fef2f2"
BLUE        = "#3b82f6"
BLUE_LIGHT  = "#eff6ff"
GREY_BG     = "#f8fafc"
BORDER      = "#e2e8f0"
WHITE       = "#ffffff"
MUTED       = "#94a3b8"


def _level_colors(level):
    if level == "Strong":  return (GREEN,  GREEN_LIGHT)
    if level == "Average": return (AMBER,  AMBER_LIGHT)
    return                        (RED,    RED_LIGHT)

def _risk_colors(risk):
    if risk == "Low":    return (GREEN, GREEN_LIGHT)
    if risk == "Medium": return (AMBER, AMBER_LIGHT)
    return                      (RED,   RED_LIGHT)

def _score_color(score):
    if score >= 70: return GREEN
    if score >= 40: return AMBER
    return RED


def build_teacher_report(students: list, teacher_name: str, org_name: str, db, get_student_metrics, models) -> io.BytesIO:
    """
    Multi-sheet teacher Excel export.
    Sheet 1: Summary Dashboard
    Sheet 2: Full Student Directory
    Sheet 3: Per-Course Breakdown
    Sheet 4: Quiz Performance
    Sheet 5: Assignment Performance
    """
    buf = io.BytesIO()
    wb  = xlsxwriter.Workbook(buf, {"in_memory": True})

    # ── Global formats ────────────────────────────────────────────────────────
    F = {}

    F["title"] = wb.add_format({
        "bold": True, "font_size": 20, "font_color": PURPLE,
        "font_name": "Calibri", "valign": "vcenter"
    })
    F["subtitle"] = wb.add_format({
        "font_size": 11, "font_color": MUTED, "font_name": "Calibri"
    })
    F["section_hdr"] = wb.add_format({
        "bold": True, "font_size": 13, "font_color": WHITE,
        "bg_color": PURPLE, "font_name": "Calibri",
        "border": 1, "border_color": PURPLE,
        "valign": "vcenter", "align": "center"
    })
    F["col_hdr"] = wb.add_format({
        "bold": True, "font_size": 10, "font_color": WHITE,
        "bg_color": DARK, "font_name": "Calibri",
        "border": 1, "border_color": DARK,
        "valign": "vcenter", "align": "center", "text_wrap": True
    })
    F["cell"] = wb.add_format({
        "font_size": 10, "font_name": "Calibri",
        "border": 1, "border_color": BORDER,
        "valign": "vcenter"
    })
    F["cell_c"] = wb.add_format({
        "font_size": 10, "font_name": "Calibri",
        "border": 1, "border_color": BORDER,
        "valign": "vcenter", "align": "center"
    })
    F["cell_bold"] = wb.add_format({
        "bold": True, "font_size": 10, "font_name": "Calibri",
        "border": 1, "border_color": BORDER, "valign": "vcenter"
    })

    def score_fmt(score):
        color = _score_color(score)
        return wb.add_format({
            "bold": True, "font_size": 10, "font_name": "Calibri",
            "font_color": color, "bg_color": WHITE,
            "border": 1, "border_color": BORDER,
            "valign": "vcenter", "align": "center"
        })

    def badge_fmt(fg, bg):
        return wb.add_format({
            "bold": True, "font_size": 9, "font_name": "Calibri",
            "font_color": fg, "bg_color": bg,
            "border": 1, "border_color": bg,
            "valign": "vcenter", "align": "center"
        })

    F["green_badge"]  = badge_fmt(GREEN, GREEN_LIGHT)
    F["amber_badge"]  = badge_fmt(AMBER, AMBER_LIGHT)
    F["red_badge"]    = badge_fmt(RED,   RED_LIGHT)
    F["blue_badge"]   = badge_fmt(BLUE,  BLUE_LIGHT)
    F["purple_badge"] = badge_fmt(PURPLE, PURPLE_LIGHT)
    F["alt_row"] = wb.add_format({
        "font_size": 10, "font_name": "Calibri", "bg_color": GREY_BG,
        "border": 1, "border_color": BORDER, "valign": "vcenter"
    })
    F["alt_row_c"] = wb.add_format({
        "font_size": 10, "font_name": "Calibri", "bg_color": GREY_BG,
        "border": 1, "border_color": BORDER, "valign": "vcenter", "align": "center"
    })
    F["stat_num"] = wb.add_format({
        "bold": True, "font_size": 22, "font_color": PURPLE,
        "font_name": "Calibri", "valign": "vcenter", "align": "center"
    })
    F["stat_lbl"] = wb.add_format({
        "font_size": 10, "font_color": MUTED, "font_name": "Calibri",
        "valign": "vcenter", "align": "center"
    })
    F["date_fmt"] = wb.add_format({
        "font_size": 9, "font_color": MUTED, "font_name": "Calibri",
        "align": "right", "italic": True
    })

    # ── Collect full detail per student ──────────────────────────────────────
    detail_rows = []
    quiz_rows   = []
    assign_rows = []

    for s in students:
        metrics, level, risk = get_student_metrics(db, s["id"])

        # Per-course breakdown
        enrollments = db.query(models.Enrollment).filter(models.Enrollment.student_id == s["id"]).all()
        for enr in enrollments:
            course = db.query(models.Course).filter(models.Course.id == enr.course_id).first()
            if not course: continue
            cm, cl, cr = get_student_metrics(db, s["id"], course.id)
            topic_ids = [t[0] for t in db.query(models.Topic.id).filter(models.Topic.course_id == course.id).all()]
            v_total = db.query(models.Video).filter(models.Video.topic_id.in_(topic_ids)).count() if topic_ids else 0
            q_total = db.query(models.Quiz).filter(models.Quiz.topic_id.in_(topic_ids)).count() if topic_ids else 0
            a_total = db.query(models.Assignment).filter(models.Assignment.topic_id.in_(topic_ids)).count() if topic_ids else 0
            detail_rows.append({
                "name": s["name"], "email": s["email"],
                "course": course.title,
                "overall": round(cm["overall_score"], 1),
                "quiz_avg": round(cm["quiz_average"], 1),
                "assign_avg": round(cm["assignment_average"], 1),
                "completion": round(cm["completion_rate"], 1),
                "videos": f"{cm['videos_completed']}/{v_total}",
                "quizzes_done": cm["quizzes_attempted"],
                "quizzes_total": q_total,
                "assigns_done": cm["assignments_submitted"],
                "assigns_total": a_total,
                "level": cl, "risk": cr
            })

        # Quiz history
        attempts = (db.query(models.QuizAttempt, models.Quiz.title, models.Course.title.label("c"))
            .join(models.Quiz, models.QuizAttempt.quiz_id == models.Quiz.id)
            .join(models.Topic, models.Quiz.topic_id == models.Topic.id)
            .join(models.Course, models.Topic.course_id == models.Course.id)
            .filter(models.QuizAttempt.student_id == s["id"])
            .order_by(models.QuizAttempt.attempted_at.desc()).all())
        for att, q_title, c_title in attempts:
            qc = db.query(models.QuizQuestion).filter(models.QuizQuestion.quiz_id == att.quiz_id).count()
            pct = round((att.score / qc) * 100, 1) if qc > 0 else 0
            quiz_rows.append({
                "name": s["name"], "email": s["email"],
                "course": c_title, "quiz": q_title,
                "score": att.score, "total": qc, "pct": pct,
                "date": att.attempted_at.strftime("%b %d, %Y") if att.attempted_at else "—"
            })

        # Assignment history
        subs = (db.query(models.AssignmentSubmission, models.Assignment.title,
                         models.Assignment.total_marks, models.Course.title.label("c"))
            .join(models.Assignment, models.AssignmentSubmission.assignment_id == models.Assignment.id)
            .join(models.Topic, models.Assignment.topic_id == models.Topic.id)
            .join(models.Course, models.Topic.course_id == models.Course.id)
            .filter(models.AssignmentSubmission.student_id == s["id"])
            .order_by(models.AssignmentSubmission.submitted_at.desc()).all())
        for sub, a_title, t_marks, c_title in subs:
            pct = round((sub.obtained_marks / t_marks) * 100, 1) if t_marks and t_marks > 0 else 0
            assign_rows.append({
                "name": s["name"], "email": s["email"],
                "course": c_title, "assignment": a_title,
                "obtained": sub.obtained_marks, "total": t_marks or 0, "pct": pct,
                "date": sub.submitted_at.strftime("%b %d, %Y") if sub.submitted_at else "—"
            })

    generated = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    # ════════════════════════════════════════════════════════════════
    # SHEET 1 — Summary Dashboard
    # ════════════════════════════════════════════════════════════════
    ws1 = wb.add_worksheet("📊 Summary")
    ws1.set_zoom(90)
    ws1.hide_gridlines(2)
    ws1.set_row(0, 40)
    ws1.set_column("A:A", 2)
    ws1.set_column("B:E", 20)

    ws1.merge_range("B2:E2", f"{org_name} — Student Performance Report", F["title"])
    ws1.merge_range("B3:E3", f"Prepared by: {teacher_name}  |  Generated: {generated}", F["subtitle"])

    # Summary stat boxes
    total   = len(students)
    high_r  = sum(1 for s in students if s.get("dropout_risk") == "High")
    strong  = sum(1 for s in students if s.get("learner_level") == "Strong")
    avg_sc  = round(sum(s.get("overall_score", 0) for s in students) / total, 1) if total else 0

    ws1.set_row(4, 50)
    ws1.set_row(5, 30)

    stat_boxes = [
        ("B5:B6", str(total),   "Total Students",   PURPLE),
        ("C5:C6", str(high_r),  "High Risk",        RED),
        ("D5:D6", str(strong),  "Strong Performers",GREEN),
        ("E5:E6", f"{avg_sc}%", "Avg Overall Score",BLUE),
    ]
    for rng, val, lbl, color in stat_boxes:
        top, bot = rng.split(":")
        ws1.merge_range(rng, "")
        ws1.write(top, val, wb.add_format({"bold":True,"font_size":28,"font_color":color,"font_name":"Calibri","valign":"vcenter","align":"center","bg_color":WHITE,"border":2,"border_color":color}))

    # Level distribution
    ws1.merge_range("B8:E8", "Learner Level Distribution", F["section_hdr"])
    ws1.set_row(7, 22)
    levels = {"Strong": 0, "Average": 0, "Weak": 0}
    for s in students:
        lv = s.get("learner_level", "Weak")
        if lv in levels: levels[lv] += 1
    risk_dist = {"High": 0, "Medium": 0, "Low": 0}
    for s in students:
        rk = s.get("dropout_risk", "Low")
        if rk in risk_dist: risk_dist[rk] += 1

    ws1.set_row(8, 20)
    for col, (k, v) in enumerate(levels.items()):
        fg, bg = _level_colors(k)
        ws1.write(8, col+1, k, badge_fmt(fg, bg))
        ws1.write(9, col+1, f"{v} students ({round(v/total*100) if total else 0}%)",
                  wb.add_format({"font_size":10,"font_name":"Calibri","align":"center","valign":"vcenter","bg_color":bg,"border":1,"border_color":bg}))

    ws1.merge_range("B11:E11", "Dropout Risk Distribution", F["section_hdr"])
    ws1.set_row(10, 22)
    for col, (k, v) in enumerate(risk_dist.items()):
        fg, bg = _risk_colors(k)
        ws1.write(11, col+1, k + " Risk", badge_fmt(fg, bg))
        ws1.write(12, col+1, f"{v} students ({round(v/total*100) if total else 0}%)",
                  wb.add_format({"font_size":10,"font_name":"Calibri","align":"center","valign":"vcenter","bg_color":bg,"border":1,"border_color":bg}))

    ws1.merge_range("B14:E14", f"Report covers {len(detail_rows)} course-enrollments · {len(quiz_rows)} quiz attempts · {len(assign_rows)} assignment submissions", F["subtitle"])

    # ════════════════════════════════════════════════════════════════
    # SHEET 2 — Full Student Directory
    # ════════════════════════════════════════════════════════════════
    ws2 = wb.add_worksheet("👥 Student Directory")
    ws2.hide_gridlines(2)
    ws2.freeze_panes(2, 0)
    ws2.set_zoom(90)

    ws2.set_row(0, 30)
    ws2.merge_range("A1:K1", "Student Directory — Full Overview", F["section_hdr"])

    headers2 = ["#", "Student Name", "Email", "Overall Score %", "Quiz Average %",
                "Assignment Avg %", "AI Learner Level", "Dropout Risk", "Enrolled Courses",
                "Quizzes Done", "Assignments Done"]
    widths2  = [4,   24,             28,       15,               14,
                15,                 16,               14,           15,
                13,            15]
    for col, (h, w) in enumerate(zip(headers2, widths2)):
        ws2.write(1, col, h, F["col_hdr"])
        ws2.set_column(col, col, w)
    ws2.set_row(1, 32)

    for row_i, s in enumerate(students, start=2):
        alt = (row_i % 2 == 0)
        base = F["alt_row"] if alt else F["cell"]
        base_c = F["alt_row_c"] if alt else F["cell_c"]

        metrics, level, risk = get_student_metrics(db, s["id"])
        q_done = db.query(models.QuizAttempt).filter(models.QuizAttempt.student_id == s["id"]).count()
        a_done = db.query(models.AssignmentSubmission).filter(models.AssignmentSubmission.student_id == s["id"]).count()

        lf, lb = _level_colors(level)
        rf, rb = _risk_colors(risk)

        ws2.write(row_i, 0,  row_i - 1,                          base_c)
        ws2.write(row_i, 1,  s["name"],                           F["cell_bold"] if not alt else wb.add_format({"bold":True,"font_size":10,"font_name":"Calibri","bg_color":GREY_BG,"border":1,"border_color":BORDER,"valign":"vcenter"}))
        ws2.write(row_i, 2,  s["email"],                          base)
        ws2.write(row_i, 3,  s.get("overall_score", 0),           score_fmt(s.get("overall_score", 0)))
        ws2.write(row_i, 4,  round(metrics["quiz_average"], 1),   score_fmt(round(metrics["quiz_average"], 1)))
        ws2.write(row_i, 5,  round(metrics["assignment_average"],1),score_fmt(round(metrics["assignment_average"],1)))
        ws2.write(row_i, 6,  level,                               badge_fmt(lf, lb))
        ws2.write(row_i, 7,  f"{risk} Risk",                      badge_fmt(rf, rb))
        ws2.write(row_i, 8,  s.get("course_count", 0),            base_c)
        ws2.write(row_i, 9,  q_done,                              base_c)
        ws2.write(row_i, 10, a_done,                              base_c)
        ws2.set_row(row_i, 20)

    # Autofilter
    ws2.autofilter(1, 0, 1 + len(students), len(headers2) - 1)

    # ════════════════════════════════════════════════════════════════
    # SHEET 3 — Per-Course Breakdown
    # ════════════════════════════════════════════════════════════════
    ws3 = wb.add_worksheet("📚 Course Breakdown")
    ws3.hide_gridlines(2)
    ws3.freeze_panes(2, 2)
    ws3.set_zoom(90)

    ws3.set_row(0, 30)
    ws3.merge_range("A1:N1", "Per-Course Student Performance", F["section_hdr"])

    headers3 = ["Student Name", "Email", "Course", "Overall %", "Quiz Avg %", "Assign Avg %",
                "Completion %", "Videos", "Quizzes Done", "Quiz Total",
                "Assigns Done", "Assign Total", "AI Level", "Risk"]
    widths3  = [22, 26, 26, 11, 11, 12, 12, 10, 12, 10, 12, 12, 13, 12]
    for col, (h, w) in enumerate(zip(headers3, widths3)):
        ws3.write(1, col, h, F["col_hdr"])
        ws3.set_column(col, col, w)
    ws3.set_row(1, 32)

    for row_i, r in enumerate(detail_rows, start=2):
        alt   = (row_i % 2 == 0)
        base  = F["alt_row"] if alt else F["cell"]
        base_c= F["alt_row_c"] if alt else F["cell_c"]
        lf, lb = _level_colors(r["level"])
        rf, rb = _risk_colors(r["risk"])

        ws3.write(row_i, 0,  r["name"],        F["cell_bold"] if not alt else wb.add_format({"bold":True,"font_size":10,"font_name":"Calibri","bg_color":GREY_BG,"border":1,"border_color":BORDER,"valign":"vcenter"}))
        ws3.write(row_i, 1,  r["email"],        base)
        ws3.write(row_i, 2,  r["course"],       base)
        ws3.write(row_i, 3,  r["overall"],      score_fmt(r["overall"]))
        ws3.write(row_i, 4,  r["quiz_avg"],     score_fmt(r["quiz_avg"]))
        ws3.write(row_i, 5,  r["assign_avg"],   score_fmt(r["assign_avg"]))
        ws3.write(row_i, 6,  r["completion"],   score_fmt(r["completion"]))
        ws3.write(row_i, 7,  r["videos"],       base_c)
        ws3.write(row_i, 8,  r["quizzes_done"], base_c)
        ws3.write(row_i, 9,  r["quizzes_total"],base_c)
        ws3.write(row_i, 10, r["assigns_done"], base_c)
        ws3.write(row_i, 11, r["assigns_total"],base_c)
        ws3.write(row_i, 12, r["level"],        badge_fmt(lf, lb))
        ws3.write(row_i, 13, f"{r['risk']} Risk",badge_fmt(rf, rb))
        ws3.set_row(row_i, 20)

    ws3.autofilter(1, 0, 1 + len(detail_rows), len(headers3) - 1)

    # ════════════════════════════════════════════════════════════════
    # SHEET 4 — Quiz Performance
    # ════════════════════════════════════════════════════════════════
    ws4 = wb.add_worksheet("🧠 Quiz Performance")
    ws4.hide_gridlines(2)
    ws4.freeze_panes(2, 2)
    ws4.set_zoom(90)

    ws4.set_row(0, 30)
    ws4.merge_range("A1:H1", "Quiz Attempt History — All Students", F["section_hdr"])

    headers4 = ["Student Name", "Email", "Course", "Quiz Title", "Score", "Total Qs", "Percentage %", "Attempted On"]
    widths4  = [22, 26, 24, 28, 9, 9, 13, 16]
    for col, (h, w) in enumerate(zip(headers4, widths4)):
        ws4.write(1, col, h, F["col_hdr"])
        ws4.set_column(col, col, w)
    ws4.set_row(1, 32)

    for row_i, r in enumerate(quiz_rows, start=2):
        alt   = (row_i % 2 == 0)
        base  = F["alt_row"] if alt else F["cell"]
        base_c= F["alt_row_c"] if alt else F["cell_c"]
        ws4.write(row_i, 0, r["name"],   F["cell_bold"] if not alt else wb.add_format({"bold":True,"font_size":10,"font_name":"Calibri","bg_color":GREY_BG,"border":1,"border_color":BORDER,"valign":"vcenter"}))
        ws4.write(row_i, 1, r["email"],  base)
        ws4.write(row_i, 2, r["course"], base)
        ws4.write(row_i, 3, r["quiz"],   base)
        ws4.write(row_i, 4, r["score"],  base_c)
        ws4.write(row_i, 5, r["total"],  base_c)
        ws4.write(row_i, 6, r["pct"],    score_fmt(r["pct"]))
        ws4.write(row_i, 7, r["date"],   base_c)
        ws4.set_row(row_i, 20)

    ws4.autofilter(1, 0, 1 + len(quiz_rows), len(headers4) - 1)

    # ════════════════════════════════════════════════════════════════
    # SHEET 5 — Assignment Performance
    # ════════════════════════════════════════════════════════════════
    ws5 = wb.add_worksheet("📝 Assignment Performance")
    ws5.hide_gridlines(2)
    ws5.freeze_panes(2, 2)
    ws5.set_zoom(90)

    ws5.set_row(0, 30)
    ws5.merge_range("A1:H1", "Assignment Submission History — All Students", F["section_hdr"])

    headers5 = ["Student Name", "Email", "Course", "Assignment Title", "Obtained", "Total Marks", "Percentage %", "Submitted On"]
    widths5  = [22, 26, 24, 30, 10, 11, 13, 16]
    for col, (h, w) in enumerate(zip(headers5, widths5)):
        ws5.write(1, col, h, F["col_hdr"])
        ws5.set_column(col, col, w)
    ws5.set_row(1, 32)

    for row_i, r in enumerate(assign_rows, start=2):
        alt   = (row_i % 2 == 0)
        base  = F["alt_row"] if alt else F["cell"]
        base_c= F["alt_row_c"] if alt else F["cell_c"]
        ws5.write(row_i, 0, r["name"],       F["cell_bold"] if not alt else wb.add_format({"bold":True,"font_size":10,"font_name":"Calibri","bg_color":GREY_BG,"border":1,"border_color":BORDER,"valign":"vcenter"}))
        ws5.write(row_i, 1, r["email"],      base)
        ws5.write(row_i, 2, r["course"],     base)
        ws5.write(row_i, 3, r["assignment"], base)
        ws5.write(row_i, 4, r["obtained"],   base_c)
        ws5.write(row_i, 5, r["total"],      base_c)
        ws5.write(row_i, 6, r["pct"],        score_fmt(r["pct"]))
        ws5.write(row_i, 7, r["date"],       base_c)
        ws5.set_row(row_i, 20)

    ws5.autofilter(1, 0, 1 + len(assign_rows), len(headers5) - 1)

    wb.close()
    buf.seek(0)
    return buf


def build_admin_report(students: list, org_name: str, db, get_student_metrics, models) -> io.BytesIO:
    """
    Admin version — same structure but org-wide, includes teacher info per course.
    """
    # Re-uses the same structure but passes org_name as teacher_name too
    return build_teacher_report(
        students=students,
        teacher_name="Administrator",
        org_name=org_name,
        db=db,
        get_student_metrics=get_student_metrics,
        models=models
    )