"""
R. P. Leiby — CTE Blockchain Standards Platform
Backend AI rubric-grading server. Shared by all subject platforms (HVAC, English, etc.).

Only one endpoint matters here: /api/grade-rubric
The static front-end sites (on Netlify) call it to AI-score a custom rubric.
The Anthropic API key lives ONLY on this server (set as the ANTHROPIC_API_KEY
environment variable in Render) — it is never exposed to students or browsers.
"""

import json
import os

import anthropic
from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="CTE Blockchain Standards Platform — AI Grader")

# Allow any front-end origin (Netlify sites, local files) to call this server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "service": "CTE Blockchain AI Grader"}


@app.get("/health")
def health():
    return {"status": "ok", "key_configured": bool(os.environ.get("ANTHROPIC_API_KEY"))}


@app.post("/api/grade-rubric")
async def grade_rubric(
    student_id: str = Form(default="STUDENT"),
    rubric_name: str = Form(...),
    rubric_text: str = Form(...),
    evidence: str = Form(...),
    teacher_id: str = Form(default="TEACHER-01"),
    teacher_comments: str = Form(default=""),
):
    if len(evidence.strip()) < 20:
        raise HTTPException(400, "Student work is too short to grade.")
    if len(rubric_text.strip()) < 10:
        raise HTTPException(400, "Rubric text is too short.")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(500, "Server is missing its ANTHROPIC_API_KEY environment variable.")

    client = anthropic.Anthropic()

    prompt = f"""You are an experienced teacher grading a student's work against a rubric.

RUBRIC NAME: {rubric_name}

RUBRIC:
---
{rubric_text}
---

STUDENT WORK:
---
{evidence}
---

Read the rubric, identify each criterion and its maximum point value, then evaluate
the student's work against each criterion fairly but rigorously.

Return a JSON object with EXACTLY these keys:
- "criteria": array of objects, each with:
    - "name": criterion name (string)
    - "max_points": maximum points (number)
    - "earned_points": points earned (number)
    - "justification": one specific sentence citing the student's work (string)
- "total_earned": sum of earned_points (number)
- "total_possible": sum of max_points (number)
- "percentage": total_earned / total_possible * 100, rounded to 1 decimal (number)
- "letter_grade": Howard County MD scale — A 90-100, B 80-89, C 70-79, D 60-69, F below 60 (string)
- "overall_feedback": 2-3 sentences of constructive, encouraging teacher feedback (string)

Respond with ONLY the JSON object. No markdown, no code fences, no extra text."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        # Strip accidental code fences if the model adds them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        result = json.loads(raw)
    except anthropic.APIError as e:
        raise HTTPException(502, f"AI service error: {e}")
    except json.JSONDecodeError:
        raise HTTPException(502, "AI returned an unexpected format. Please try again.")

    result["rubric_name"] = rubric_name
    result["student_id"] = student_id
    result["teacher_id"] = teacher_id
    result["teacher_comments"] = teacher_comments
    return result
