# Socratic AI Practice Tutor — Adaptive Programming & CS Edition

A Flask + SQLite learning tutor that evaluates reasoning, detects a learner's current level from performance, and adapts practice. It supports both multiple-choice questions and open-ended reasoning.

## New adaptive features

- **24 programming/CS subjects**: Python, C, C++, Java, JavaScript, HTML/CSS, SQL, DBMS, Data Structures, Algorithms, OOP, Operating Systems, Computer Networks, Software Engineering, Computer Organization, Compiler Design, Artificial Intelligence, Machine Learning, Deep Learning, Cloud Computing, Git/GitHub, Cybersecurity, Web Development and Data Analytics.
- **5 learning levels**: Foundation, Beginner, Intermediate, Advanced, Expert.
- **Declared level + detected level**: the learner can select a starting level, but the system does not blindly trust it.
- **5-question level assessment**: samples questions across levels and lets the tutor estimate the learner's current level.
- **Adaptive question selection**: new questions are selected around the detected level and neighboring levels.
- **MCQ + reasoning**: recognition and explanation are measured separately.
- **Socratic, Devil's Advocate and Teach-Back modes**.
- **Knowledge map, misconception fingerprint, replay and AI learning profile**.
- **Local adaptive fallback** works without an OpenAI API key. An API key can be added for semantic AI feedback.
- **432-question bank** with 240 MCQs and 192 reasoning questions.

## Windows setup

1. Install Python 3.11+.
2. Extract the ZIP and open the `socratic` folder in VS Code.
3. Open Terminal → New Terminal.
4. Create a virtual environment:
   ```powershell
   python -m venv venv
   ```
5. Activate it:
   ```powershell
   venv\\Scripts\\Activate.ps1
   ```
   If PowerShell blocks activation:
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   venv\\Scripts\\Activate.ps1
   ```
6. Install packages:
   ```powershell
   pip install -r requirements.txt
   ```
7. Optional live AI: copy `.env.example` to `.env` and add your OpenAI API key.
8. Start the server:
   ```powershell
   python app.py
   ```
9. Open `http://127.0.0.1:5000` in Chrome or Edge.

## Recommended demo flow

1. Click **Assess My Level First**.
2. Answer the five diagnostic MCQs without relying on the selected level.
3. Click **Next** after each answer.
4. After the fifth question, the tutor switches to adaptive practice.
5. Choose **Mixed (MCQ + Reasoning)**.
6. Answer a reasoning question and submit it.
7. Show the **AI-Detected Level** changing as evidence accumulates.
8. Demonstrate Devil's Advocate and Teach-Back.
9. Open Replay and AI Profile.
10. Generate Adaptive Practice from the weakest area.

## Notes

- `data/tutor.db` is created automatically.
- Never share an OpenAI API key in screenshots or GitHub.
- If live AI is unavailable, the application remains usable through the local adaptive engine.
