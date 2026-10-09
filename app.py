from flask import Flask, render_template, request, jsonify
import sqlite3, os, json, re, random
from datetime import datetime
from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "tutor.db")
BANK_PATH = os.path.join(BASE_DIR, "question_bank.json")
load_dotenv(os.path.join(BASE_DIR, ".env"))

# The template and static files are inside app/templates and app/static.
app = Flask(__name__, template_folder="app/templates", static_folder="app/static")

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
client = OpenAI(api_key=API_KEY) if (API_KEY and OpenAI) else None

with open(BANK_PATH, encoding="utf-8") as f:
    QUESTION_BANK = json.load(f)

LEVELS = ["Foundation", "Beginner", "Intermediate", "Advanced", "Expert"]
SUBJECTS = sorted({q["subject"] for q in QUESTION_BANK})


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER, topic TEXT, question TEXT, answer TEXT,
        confidence INTEGER, ai_score INTEGER, correct INTEGER,
        misconception TEXT, strengths TEXT, analysis TEXT,
        next_step TEXT, mode TEXT, created_at TEXT,
        question_type TEXT DEFAULT 'reasoning', selected_option INTEGER,
        declared_level TEXT DEFAULT '', detected_level TEXT DEFAULT ''
    )""")
    # Upgrade databases created by the original version.
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(attempts)").fetchall()}
    upgrades = {
        "question_type": "TEXT DEFAULT 'reasoning'",
        "selected_option": "INTEGER",
        "declared_level": "TEXT DEFAULT ''",
        "detected_level": "TEXT DEFAULT ''",
    }
    for col, definition in upgrades.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE attempts ADD COLUMN {col} {definition}")
    conn.commit(); conn.close()


def safe_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.M).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try: return json.loads(m.group(0))
            except Exception: pass
    return None


def level_index(level):
    try: return LEVELS.index(level)
    except ValueError: return 0


def infer_level(rows, declared="Foundation"):
    """Infer learning level from evidence, not the learner's self-selected level.
    MCQ correctness, reasoning scores, recent performance and consistency all count.
    """
    if not rows:
        return declared if declared in LEVELS else "Foundation"
    recent = rows[:12]
    scores = [int(r["ai_score"] or 0) for r in recent]
    accuracy = sum(int(r["correct"] or 0) for r in recent) / len(recent)
    avg = sum(scores) / len(scores)
    # Slightly stricter thresholds as the evidence grows.
    if len(recent) < 3:
        if avg >= 85 and accuracy >= .66: return max_level(declared, "Intermediate")
        if avg >= 70: return max_level(declared, "Beginner")
        return "Foundation"
    if avg >= 90 and accuracy >= .80: return "Expert"
    if avg >= 80 and accuracy >= .70: return "Advanced"
    if avg >= 68 and accuracy >= .55: return "Intermediate"
    if avg >= 50 and accuracy >= .40: return "Beginner"
    return "Foundation"


def max_level(a, b):
    return LEVELS[max(level_index(a), level_index(b))]


def question_for_id(qid):
    return next((q for q in QUESTION_BANK if q["id"] == qid), QUESTION_BANK[0])


def public_question(q):
    x = {k: v for k, v in q.items() if k not in {"answer", "explanation"}}
    return x


def history():
    conn = get_db(); rows = conn.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 100").fetchall(); conn.close()
    return [dict(r) for r in rows]


def adaptive_questions(subject, declared_level, qtype="mixed", count=8):
    rows = history()
    detected = infer_level(rows, declared_level)
    subject = subject if subject in SUBJECTS else SUBJECTS[0]
    allowed = {"mcq", "reasoning"} if qtype == "mixed" else {qtype}
    # Start one level around the detected level, but include a neighboring level so the app can calibrate.
    idx = level_index(detected)
    candidate_levels = {LEVELS[idx]}
    if idx > 0: candidate_levels.add(LEVELS[idx-1])
    if idx < len(LEVELS)-1: candidate_levels.add(LEVELS[idx+1])
    candidates = [q for q in QUESTION_BANK if q["subject"] == subject and q["level"] in candidate_levels and q["type"] in allowed]
    # Prefer unseen questions for this learner.
    seen = {r["question_id"] for r in rows if r.get("topic") == subject}
    unseen = [q for q in candidates if q["id"] not in seen]
    pool = unseen or candidates
    random.shuffle(pool)
    result = pool[:count]
    # Ensure both types when mixed is requested.
    if qtype == "mixed" and count >= 4:
        mcq = [q for q in candidates if q["type"] == "mcq" and q["id"] not in seen] or [q for q in candidates if q["type"] == "mcq"]
        reason = [q for q in candidates if q["type"] == "reasoning" and q["id"] not in seen] or [q for q in candidates if q["type"] == "reasoning"]
        random.shuffle(mcq); random.shuffle(reason)
        result = (mcq[:count//2] + reason[:count-count//2])[:count]
        random.shuffle(result)
    return result, detected


def local_reasoning(question, answer, confidence, mode):
    terms = set(re.findall(r"[a-zA-Z]+", answer.lower()))
    subject = question["subject"]
    concept_words = {
        "Python": {"function", "def", "dictionary", "list", "generator", "iterable", "memory", "context"},
        "C": {"pointer", "memory", "address", "malloc", "const", "array", "function"},
        "C++": {"class", "object", "virtual", "inheritance", "raii", "move", "smart"},
        "Java": {"class", "object", "interface", "jvm", "garbage", "collection", "inheritance"},
        "JavaScript": {"promise", "async", "await", "closure", "event", "json", "function"},
        "HTML/CSS": {"html", "semantic", "css", "flexbox", "layout", "selector", "responsive"},
        "SQL": {"select", "where", "join", "group", "index", "transaction", "acid"},
        "DBMS": {"primary", "foreign", "normalization", "table", "transaction", "lock", "deadlock"},
        "Data Structures": {"stack", "queue", "tree", "heap", "graph", "hash", "list"},
        "Algorithms": {"binary", "search", "sort", "complexity", "graph", "dynamic", "dijkstra"},
        "OOP": {"encapsulation", "inheritance", "polymorphism", "composition", "interface", "substitution"},
        "Operating Systems": {"process", "memory", "page", "virtual", "thread", "context", "starvation"},
        "Computer Networks": {"tcp", "udp", "ip", "dns", "network", "subnet", "tls", "packet"},
        "Software Engineering": {"requirement", "testing", "version", "ci", "refactoring", "debt", "design"},
        "Computer Organization": {"cpu", "instruction", "cache", "ram", "pipeline", "isa", "memory"},
        "Compiler Design": {"token", "lexer", "parser", "syntax", "semantic", "ast", "optimization", "ir"},
        "Artificial Intelligence": {"agent", "search", "heuristic", "state", "minimax", "astar", "goal"},
        "Machine Learning": {"training", "test", "validation", "overfit", "regularization", "feature", "leakage"},
        "Deep Learning": {"neural", "activation", "gradient", "backpropagation", "cnn", "dropout", "transfer"},
        "Cloud Computing": {"cloud", "iaas", "container", "serverless", "storage", "scaling", "instance"},
        "Git/GitHub": {"git", "commit", "branch", "merge", "pull", "rebase", "repository"},
        "Cybersecurity": {"security", "phishing", "mfa", "hash", "privilege", "injection", "query"},
        "Web Development": {"http", "api", "rest", "server", "client", "cors", "request"},
        "Data Analytics": {"data", "table", "correlation", "outlier", "distribution", "train", "visual"},
    }.get(subject, set())
    hits = len(terms & concept_words)
    length_bonus = min(25, len(answer.split()))
    score = min(96, 35 + hits * 9 + length_bonus)
    if mode == "teach": score = min(100, score + (8 if len(answer.split()) >= 25 else 0))
    if mode == "devil": score = min(100, score + (8 if "counter" in terms or "however" in terms or "but" in terms else 0))
    correct = score >= 65
    misconception = "No strong misconception detected" if correct else f"Possible gap in the core concept of {subject}"
    confidence_message = "High confidence but weak evidence — review the concept." if confidence >= 80 and not correct else ("You may understand more than your confidence suggests." if confidence <= 35 and correct else "Confidence is reasonably aligned with performance.")
    return {"score": score, "correct": correct, "analysis": "The local adaptive engine evaluated the structure, concept evidence and depth of your explanation. Live semantic evaluation can be enabled with an OpenAI API key.", "strengths": ["You attempted the concept", "You used relevant reasoning evidence" if hits else "You can strengthen your use of subject terminology"], "misconception": misconception, "next_step": "Give one practical example and one counterexample, then explain the trade-off.", "socratic_question": "What evidence in your explanation shows that you understand the underlying idea?", "confidence_message": confidence_message, "ai_used": False}


def ai_reasoning(question, answer, confidence, mode, history_rows, detected_level):
    if not client:
        return local_reasoning(question, answer, confidence, mode)
    history_text = "\n".join([f"- {h['topic']}: score={h['ai_score']}, detected={h.get('detected_level','')}, misconception={h['misconception']}" for h in history_rows[-10:]]) or "No previous attempts."
    prompt = f"""You are the adaptive reasoning engine for a college programming/CS tutor.\nSubject: {question['subject']}\nQuestion level: {question['level']}\nMode: {mode}\nCurrent detected learner level: {detected_level}\nLearner confidence: {confidence}/100\nQuestion: {question['question']}\nLearner answer: {answer}\nRecent evidence:\n{history_text}\n\nEvaluate reasoning, depth, correctness and transfer. Do not simply reveal the answer. Return ONLY JSON with keys: score (0-100 integer), correct (boolean), analysis (2-4 sentences), strengths (array), misconception (string), next_step (string), socratic_question (string), confidence_message (string), mastery_signal (mastered/developing/fragile/misconception), recommended_level (Foundation/Beginner/Intermediate/Advanced/Expert)."""
    try:
        r = client.responses.create(model=MODEL, input=prompt)
        data = safe_json(r.output_text)
        if not data: raise ValueError("AI returned non-JSON")
        data["score"] = max(0, min(100, int(data.get("score", 50))))
        data["correct"] = bool(data.get("correct", data["score"] >= 65))
        data["strengths"] = data.get("strengths", [])[:3]
        data["ai_used"] = True
        return data
    except Exception as exc:
        fallback = local_reasoning(question, answer, confidence, mode)
        fallback["analysis"] += f" Live AI was unavailable, so the safe local backup was used. ({type(exc).__name__})"
        return fallback


@app.get("/")
def index(): return render_template("index.html")

@app.get("/api/status")
def status():
    return jsonify({"ai_enabled": bool(client), "model": MODEL, "message": "Live AI enabled" if client else "Local adaptive engine enabled — add OPENAI_API_KEY in .env for semantic AI."})

@app.get("/api/catalog")
def catalog():
    return jsonify({"subjects": SUBJECTS, "levels": LEVELS, "question_types": ["mixed", "mcq", "reasoning"]})


@app.get("/api/diagnostic")
def diagnostic():
    # A short mixed-level diagnostic deliberately ignores the learner's declared level.
    # It samples one MCQ from each level for the selected subject.
    subject = request.args.get("subject", SUBJECTS[0])
    qs = []
    for level in LEVELS:
        pool = [q for q in QUESTION_BANK if q["subject"] == subject and q["level"] == level and q["type"] == "mcq"]
        if pool: qs.append(random.choice(pool))
    return jsonify({"questions": [public_question(q) for q in qs], "message": "Answer these without relying on your selected level; the tutor will estimate your current level."})

@app.get("/api/questions")
def questions():
    subject = request.args.get("subject", SUBJECTS[0])
    level = request.args.get("level", "Foundation")
    qtype = request.args.get("type", "mixed")
    count = max(1, min(20, int(request.args.get("count", 8))))
    rows = history(); detected = infer_level(rows, level)
    qs, detected = adaptive_questions(subject, level, qtype, count)
    return jsonify({"questions": [public_question(q) for q in qs], "detected_level": detected})

@app.get("/api/adaptive")
def adaptive():
    declared = request.args.get("declared_level", "Foundation")
    subject = request.args.get("subject", SUBJECTS[0])
    qtype = request.args.get("type", "mixed")
    count = max(1, min(20, int(request.args.get("count", 8))))
    qs, detected = adaptive_questions(subject, declared, qtype, count)
    return jsonify({"questions": [public_question(q) for q in qs], "detected_level": detected, "declared_level": declared})

@app.post("/api/analyze")
def analyze():
    data = request.get_json(force=True) or {}
    qid = int(data.get("question_id", 1)); q = question_for_id(qid)
    qtype = str(data.get("question_type", q.get("type", "reasoning")))
    answer = str(data.get("answer", "")).strip()
    confidence = max(0, min(100, int(data.get("confidence", 50))))
    mode = str(data.get("mode", "practice"))
    declared = str(data.get("declared_level", "Foundation"))
    rows = history(); detected_before = infer_level(rows, declared)

    if qtype == "mcq":
        try: selected = int(data.get("selected_option", -1))
        except Exception: selected = -1
        correct = selected == int(q.get("answer", -2))
        score = 100 if correct else 25
        result = {
            "score": score, "correct": correct,
            "analysis": q.get("explanation", "Review why the selected option is or is not correct."),
            "strengths": ["Correct choice — the core concept is understood." if correct else "You completed the multiple-choice check."],
            "misconception": "No strong misconception detected" if correct else f"Review the core concept of {q['subject']} and compare each option carefully.",
            "next_step": "Move to a reasoning question at the detected level and justify your answer with an example.",
            "socratic_question": f"Why is the correct choice stronger than the other options in this {q['subject']} question?",
            "confidence_message": "Confidence is reasonably aligned with performance." if (correct and confidence >= 50) or (not correct and confidence < 70) else "Your confidence and result differ; use the next question to recalibrate.",
            "ai_used": False,
        }
    else:
        if len(answer) < 12:
            return jsonify({"error": "Please give a little more reasoning so the tutor can evaluate your thinking."}), 400
        result = ai_reasoning(q, answer, confidence, mode, rows, detected_before)
        selected = None

    # Predict a level after adding this attempt.
    temp = rows + [{"ai_score": result["score"], "correct": int(result["correct"]), "confidence": confidence}]
    detected_after = infer_level(temp, declared)
    result["detected_level"] = detected_after
    result["declared_level"] = declared
    result["question_type"] = qtype
    result["question_id"] = qid

    conn = get_db(); conn.execute("""INSERT INTO attempts
        (question_id,topic,question,answer,confidence,ai_score,correct,misconception,strengths,analysis,next_step,mode,created_at,question_type,selected_option,declared_level,detected_level)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (qid, q["subject"], q["question"], answer, confidence, result["score"], int(result["correct"]), result.get("misconception",""), json.dumps(result.get("strengths",[])), result.get("analysis",""), result.get("next_step",""), mode, datetime.now().isoformat(timespec="seconds"), qtype, selected, declared, detected_after))
    conn.commit(); conn.close()
    return jsonify(result)

@app.post("/api/hint")
def hint():
    data=request.get_json(force=True) or {}; q=question_for_id(int(data.get("question_id",1)))
    if client:
        try:
            r=client.responses.create(model=MODEL,input=f"Give one Socratic hint for this {q['subject']} question without answering it: {q['question']}. One sentence.")
            return jsonify({"hint":r.output_text.strip(),"ai_used":True})
        except Exception: pass
    return jsonify({"hint":f"Think about the purpose of this {q['subject']} concept, then connect it to a small example. Do not reveal the answer yet.","ai_used":False})

@app.post("/api/generate")
def generate():
    data=request.get_json(force=True) or {}; subject=str(data.get("subject",SUBJECTS[0])); level=str(data.get("level","Intermediate")); misconception=str(data.get("misconception",""))
    if client:
        try:
            prompt=f"Create one original {level} college question for {subject}. Target misconception: {misconception}. Return ONLY JSON with question, subject, level, type (mcq or reasoning), options, answer, why_it_matters, challenge. Do not reveal the answer in why_it_matters."
            r=client.responses.create(model=MODEL,input=prompt); out=safe_json(r.output_text)
            if out: return jsonify({**out,"ai_used":True})
        except Exception: pass
    candidates=[q for q in QUESTION_BANK if q["subject"]==subject and q["level"]==level]
    q=random.choice(candidates or QUESTION_BANK)
    return jsonify({"question":q["question"],"subject":q["subject"],"level":q["level"],"type":q["type"],"options":q.get("options",[]),"why_it_matters":f"Build practical understanding of {subject} at {level} level.","challenge":"Explain your choice and mention one trade-off or counterexample.","ai_used":False})

@app.get("/api/dashboard")
def dashboard():
    rows=history(); total=len(rows); accuracy=round(sum(r["correct"] for r in rows)/total*100) if total else 0
    avg=round(sum(r["confidence"] for r in rows)/total) if total else 0
    declared = rows[0].get("declared_level", "Foundation") if rows else "Foundation"
    detected = infer_level(rows, declared)
    mastery={}
    for r in rows: mastery.setdefault(r["topic"],[]).append(r["ai_score"])
    knowledge=[{"topic":t,"score":round(sum(v)/len(v))} for t,v in mastery.items()]
    mis=[]
    for r in rows:
        m=r["misconception"]
        if m and m != "No strong misconception detected" and m not in mis: mis.append(m)
    return jsonify({"total":total,"accuracy":accuracy,"confidence":avg,"difficulty":detected,"detected_level":detected,"declared_level":declared,"misconceptions":mis[:6],"knowledge_map":knowledge,"ai_enabled":bool(client),"subjects":SUBJECTS})

@app.get("/api/replay")
def replay():
    rows=history()
    for r in rows: r["strengths"]=json.loads(r.get("strengths") or "[]")
    return jsonify(rows)

@app.get("/api/insights")
def insights():
    rows=history()
    if not rows: return jsonify({"summary":"Complete a few attempts to generate your adaptive learning profile.","weakest":"—","strongest":"—","recommendations":[],"detected_level":"Foundation"})
    topics={}
    for r in rows: topics.setdefault(r["topic"],[]).append(r["ai_score"])
    avg={t:round(sum(v)/len(v)) for t,v in topics.items()}; weakest=min(avg,key=avg.get); strongest=max(avg,key=avg.get)
    detected=infer_level(rows, rows[0].get("declared_level","Foundation"))
    return jsonify({"summary":f"Detected level: {detected}. Strongest current area: {strongest} ({avg[strongest]}%). Biggest opportunity: {weakest} ({avg[weakest]}%).","weakest":weakest,"strongest":strongest,"detected_level":detected,"recommendations":[f"Practice {weakest} at {detected} level, then try one level higher after a strong result.","Mix multiple-choice checks with reasoning questions so the system can measure both recognition and explanation.","When confidence is high but scores are low, slow down and test your reasoning with evidence."],"topic_scores":avg})

@app.post("/api/reset")
def reset():
    conn=get_db(); conn.execute("DELETE FROM attempts"); conn.commit(); conn.close(); return jsonify({"success":True})

init_db()
if __name__ == "__main__": app.run(debug=True, host="127.0.0.1", port=5000)
