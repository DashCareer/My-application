"""
MBTI Personality Test — 20 questions across 4 dimensions, 16 types.

Scoring:
- Each question has a `direction` letter (E/S/T/J).
- Answer value 0–3 maps to weight -2, -1, +1, +2.
- A positive weight increases the direction letter; a negative weight increases its opposite.
"""

QUESTIONS = [
    # E/I — 5 questions, direction=E (agree = extraverted)
    {"id": 1, "text": "I feel energized after spending time with a large group of people.", "dim": "EI", "dir": "E"},
    {"id": 2, "text": "I prefer working in quiet, solo focus over noisy team environments.", "dim": "EI", "dir": "I"},
    {"id": 3, "text": "I think out loud and process ideas best by talking them through.", "dim": "EI", "dir": "E"},
    {"id": 4, "text": "I need plenty of alone time to recharge after social events.", "dim": "EI", "dir": "I"},
    {"id": 5, "text": "I would rather meet new people than spend the evening reading.", "dim": "EI", "dir": "E"},

    # S/N — 5 questions, direction varies (S = sensing, N = intuition)
    {"id": 6, "text": "I trust concrete facts and lived experience more than theories.", "dim": "SN", "dir": "S"},
    {"id": 7, "text": "I enjoy thinking about future possibilities and abstract ideas.", "dim": "SN", "dir": "N"},
    {"id": 8, "text": "I notice small practical details others tend to overlook.", "dim": "SN", "dir": "S"},
    {"id": 9, "text": "I often see patterns and connections between unrelated things.", "dim": "SN", "dir": "N"},
    {"id": 10, "text": "I prefer step-by-step instructions over open-ended exploration.", "dim": "SN", "dir": "S"},

    # T/F — 5 questions, direction varies (T = thinking, F = feeling)
    {"id": 11, "text": "When making decisions, logic matters more to me than feelings.", "dim": "TF", "dir": "T"},
    {"id": 12, "text": "I care deeply about how my choices affect the people around me.", "dim": "TF", "dir": "F"},
    {"id": 13, "text": "I value being objective even if it feels harsh.", "dim": "TF", "dir": "T"},
    {"id": 14, "text": "I am quick to empathize when someone is going through a hard time.", "dim": "TF", "dir": "F"},
    {"id": 15, "text": "I would rather be respected for being competent than liked for being warm.", "dim": "TF", "dir": "T"},

    # J/P — 5 questions, direction varies (J = judging, P = perceiving)
    {"id": 16, "text": "I like to make detailed plans and stick to them.", "dim": "JP", "dir": "J"},
    {"id": 17, "text": "I keep my options open and decide things at the last minute.", "dim": "JP", "dir": "P"},
    {"id": 18, "text": "I feel anxious when things are disorganized or undecided.", "dim": "JP", "dir": "J"},
    {"id": 19, "text": "I thrive on spontaneity and adapt easily to unexpected changes.", "dim": "JP", "dir": "P"},
    {"id": 20, "text": "Deadlines and structure help me do my best work.", "dim": "JP", "dir": "J"},
]

# Likert weights for answer values 0,1,2,3
WEIGHTS = {0: -2, 1: -1, 2: 1, 3: 2}

OPPOSITES = {"E": "I", "I": "E", "S": "N", "N": "S", "T": "F", "F": "T", "J": "P", "P": "J"}


def score_answers(answers: list[int]) -> str:
    """Return the 4-letter MBTI type."""
    if len(answers) != len(QUESTIONS):
        raise ValueError("Expected 20 answers")
    totals = {"E": 0, "I": 0, "S": 0, "N": 0, "T": 0, "F": 0, "J": 0, "P": 0}
    for q, val in zip(QUESTIONS, answers):
        weight = WEIGHTS.get(val, 0)
        if weight >= 0:
            totals[q["dir"]] += weight
        else:
            totals[OPPOSITES[q["dir"]]] += -weight
    # Build type per dimension; tie-breaker favors the first letter listed
    return (
        ("E" if totals["E"] >= totals["I"] else "I")
        + ("S" if totals["S"] >= totals["N"] else "N")
        + ("T" if totals["T"] >= totals["F"] else "F")
        + ("J" if totals["J"] >= totals["P"] else "P")
    )


TYPES = {
    "INTJ": {
        "name": "Architect",
        "summary": "Strategic, independent thinkers who design long-term plans others find hard to see.",
        "strengths": ["Systems thinking", "Decisive under uncertainty", "Self-driven"],
        "careers": ["Strategy Consultant", "Software Architect", "Investment Analyst", "Research Scientist", "Product Lead"],
    },
    "INTP": {
        "name": "Logician",
        "summary": "Curious problem-solvers who pull apart complex ideas for the joy of understanding them.",
        "strengths": ["Analytical depth", "Pattern recognition", "Open-minded"],
        "careers": ["Software Engineer", "Data Scientist", "Mathematician", "UX Researcher", "Philosopher"],
    },
    "ENTJ": {
        "name": "Commander",
        "summary": "Confident leaders who turn ambitious visions into concrete results.",
        "strengths": ["Strategic command", "High accountability", "Persuasive"],
        "careers": ["CEO / Founder", "Management Consultant", "Corporate Lawyer", "VP of Operations", "Venture Capitalist"],
    },
    "ENTP": {
        "name": "Debater",
        "summary": "Inventive originators who challenge convention and spark new ideas in everyone around them.",
        "strengths": ["Idea generation", "Quick-witted", "Comfortable with debate"],
        "careers": ["Entrepreneur", "Product Manager", "Trial Lawyer", "Creative Director", "Growth Marketer"],
    },
    "INFJ": {
        "name": "Advocate",
        "summary": "Insightful idealists driven by a quiet sense of purpose and a desire to help others grow.",
        "strengths": ["Empathy", "Long-term vision", "Strong values"],
        "careers": ["Therapist / Counsellor", "Writer", "UX Designer", "Non-Profit Leader", "Teacher / Mentor"],
    },
    "INFP": {
        "name": "Mediator",
        "summary": "Creative idealists guided by personal values and a love of authentic self-expression.",
        "strengths": ["Creative writing", "Empathy", "Authentic voice"],
        "careers": ["Author / Poet", "Counsellor", "Filmmaker", "Graphic Designer", "Social Worker"],
    },
    "ENFJ": {
        "name": "Protagonist",
        "summary": "Charismatic mentors who inspire others to grow and align around a common cause.",
        "strengths": ["Coaching", "Emotional intelligence", "Inspiring communication"],
        "careers": ["Head of People / HR", "Teacher", "Politician", "Brand Marketer", "Executive Coach"],
    },
    "ENFP": {
        "name": "Campaigner",
        "summary": "Enthusiastic free spirits who connect dots between people and possibilities with infectious energy.",
        "strengths": ["Storytelling", "Networking", "Big-picture optimism"],
        "careers": ["Founder", "Marketing Lead", "Journalist", "Event Producer", "UX Designer"],
    },
    "ISTJ": {
        "name": "Logistician",
        "summary": "Reliable, detail-oriented operators who keep systems running with quiet excellence.",
        "strengths": ["Discipline", "Reliability", "Attention to detail"],
        "careers": ["Accountant", "Project Manager", "Auditor", "Civil Engineer", "Operations Manager"],
    },
    "ISFJ": {
        "name": "Defender",
        "summary": "Warm, conscientious protectors who quietly support the people and systems they care about.",
        "strengths": ["Loyalty", "Service-orientation", "Practical care"],
        "careers": ["Nurse / Healthcare", "Office Manager", "Librarian", "Customer Success Manager", "Primary Teacher"],
    },
    "ESTJ": {
        "name": "Executive",
        "summary": "Decisive organizers who turn group goals into structured plans and deliverables.",
        "strengths": ["Operational rigor", "Leadership", "Clarity"],
        "careers": ["Operations Director", "Military Officer", "Financial Controller", "Judge", "Hospital Administrator"],
    },
    "ESFJ": {
        "name": "Consul",
        "summary": "Warm, organized hosts who keep teams and communities running smoothly.",
        "strengths": ["Coordination", "Social warmth", "Practical action"],
        "careers": ["Event Manager", "Healthcare Administrator", "Sales Director", "Recruiter", "Public Relations"],
    },
    "ISTP": {
        "name": "Virtuoso",
        "summary": "Hands-on problem-solvers who learn by tinkering and stay calm under pressure.",
        "strengths": ["Mechanical insight", "Calm in chaos", "Practical creativity"],
        "careers": ["Mechanical Engineer", "Pilot / Pilot", "Surgeon", "Cybersecurity Analyst", "Carpenter / Craftsman"],
    },
    "ISFP": {
        "name": "Adventurer",
        "summary": "Sensitive artists who live by their values and find beauty in the everyday.",
        "strengths": ["Aesthetic sensibility", "Authentic expression", "Adaptable"],
        "careers": ["Visual Artist", "Photographer", "Veterinarian", "Interior Designer", "Musician"],
    },
    "ESTP": {
        "name": "Entrepreneur",
        "summary": "Energetic risk-takers who thrive on action, deal-making, and solving problems in real time.",
        "strengths": ["Negotiation", "Risk tolerance", "Quick reflexes"],
        "careers": ["Sales Executive", "Entrepreneur / Trader", "Paramedic", "Detective", "Real Estate Developer"],
    },
    "ESFP": {
        "name": "Entertainer",
        "summary": "Playful, generous performers who bring energy and warmth to every room they enter.",
        "strengths": ["Charisma", "Improvisation", "People skills"],
        "careers": ["Performer / Actor", "Hospitality Manager", "Sales", "Event Host", "Children's Educator"],
    },
}


def get_result(mbti: str) -> dict:
    data = TYPES.get(mbti, {})
    return {"type": mbti, **data}


def all_questions() -> list[dict]:
    """Return questions stripped of scoring direction (frontend doesn't need it)."""
    return [{"id": q["id"], "text": q["text"]} for q in QUESTIONS]
