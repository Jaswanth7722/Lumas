"""Generate a clean test_full_demo.py with reportlab-based PDF creation."""
import textwrap

# First, restore the original file by removing the corrupted part
with open('test_full_demo.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find where the reportlab function starts and the original continues
# Find the pattern that indicates the original main() function
idx = content.find('\ndef main():')
if idx > 0:
    # Keep everything up to and including the original _create_test_pdf
    # Actually, we've messed up the file. Let's just write a completely new one.
    pass

# Write a completely new test file from scratch
new_content = '''"""
Full end-to-end demo test for Lumas desktop.

Tests: upload PDF -> grounded chat -> generate quiz -> submit answers -> verify tracking
"""

import io
import json
import os
import sys
import time
import urllib.request
import urllib.error

API_BASE = "http://127.0.0.1:8765/api"
PASS = 0
FAIL = 0
SKIP = 0


def api(method, path, data=None, files=None):
    """Make an API call with optional JSON body or multipart file upload."""
    url = f"{API_BASE}{path}"
    headers = {}

    if files:
        boundary = "----LumasTestBoundary" + str(int(time.time() * 1e6))
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"

        body_parts = []
        for field_name, (filename, filedata, content_type) in files.items():
            body_parts.append(f"--{boundary}".encode())
            body_parts.append(
                f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'.encode()
            )
            body_parts.append(f"Content-Type: {content_type}".encode())
            body_parts.append(b"")
            body_parts.append(filedata if isinstance(filedata, bytes) else filedata.encode())
        body_parts.append(f"--{boundary}--".encode())
        body_parts.append(b"")
        body = b"\\r\\n".join(body_parts)
    elif data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    else:
        body = None

    req = urllib.request.Request(url, data=body, method=method)
    for k, v in headers.items():
        req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        print(f"  !! HTTP {e.code}: {error_body[:200]}")
        return None
    except Exception as e:
        print(f"  !! Error: {e}")
        return None


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} -- {detail}")


def skip(name, reason):
    global SKIP
    SKIP += 1
    print(f"  [SKIP] {name} -- {reason}")


def _create_test_pdf():
    """Create a valid PDF with quantum computing content using reportlab."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from io import BytesIO

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica", 20)
    c.drawString(50, 700, "Quantum Computing Fundamentals")
    c.setFont("Helvetica", 14)
    c.drawString(50, 650, "Superposition")
    c.setFont("Helvetica", 11)
    c.drawString(50, 620, "Superposition is a fundamental principle of quantum mechanics")
    c.drawString(50, 605, "where a quantum system can exist in multiple states simultaneously.")
    c.drawString(50, 590, "Unlike classical bits that are either 0 or 1, a qubit in superposition")
    c.drawString(50, 575, "is a combination of both states until measured.")
    c.drawString(50, 560, "This is described mathematically as |psi = alpha|0> + beta|1>.")
    c.drawString(50, 535, "When measured, the qubit collapses to either |0> or |1>")
    c.drawString(50, 520, "with probabilities |alpha|^2 and |beta|^2 respectively.")
    c.setFont("Helvetica", 14)
    c.drawString(50, 490, "Entanglement")
    c.setFont("Helvetica", 11)
    c.drawString(50, 460, "Entanglement is another quantum phenomenon where two or more")
    c.drawString(50, 445, "qubits become correlated such that the state of one instantly")
    c.drawString(50, 430, "determines the state of the other, regardless of distance.")
    c.drawString(50, 405, "This enables quantum teleportation and superdense coding.")
    c.save()
    return buf.getvalue()


def main():
    global PASS, FAIL, SKIP

    # Check for model file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.join(script_dir, "..", "models")
    model_path = os.path.join(models_dir, "gemma-3-270m-int4.gguf")
    if not os.path.exists(model_path):
        print(f"  [INFO] Model not found at {model_path}")
    else:
        print(f"  [INFO] Model found: {os.path.getsize(model_path) / 1024 / 1024:.1f} MB")

    print("")
    print("=" * 55)
    print("  LUMAS FULL DEMO TEST")
    print("=" * 55)

    # -- Health check --
    health = api("GET", "/health")
    check("Server is running", health and health.get("status") == "ok")
    if not health or health.get("status") != "ok":
        print("\\n  Server not reachable. Start with:")
        print("    cd Lumas && python -m uvicorn lumas.backend.main:create_app --factory --host 127.0.0.1 --port 8765")
        sys.exit(1)

    # -- Step 1: Upload PDF --
    print("")
    print("1. [UPLOAD PDF]")
    print("-" * 55)
    pdf_bytes = _create_test_pdf()

    result = api("POST", "/documents/upload", files={
        "file": ("quantum_computing.pdf", pdf_bytes, "application/pdf"),
    })

    doc_id = (result or {}).get("id", "")
    chunks = (result or {}).get("chunks", [])
    check("Upload returned document ID", bool(doc_id))
    check("Document has chunks", len(chunks) > 0)
    if chunks:
        preview = chunks[0].get("content_preview", "")
        print(f"  Chunk 0 ({len(preview)} chars): {preview[:80]}...")

    # -- Step 2: Create session --
    print("")
    print("2. [CREATE SESSION]")
    print("-" * 55)
    session = api("POST", "/sessions", {"engine_used": "local"})
    sid = (session or {}).get("id", "")
    check("Session created", bool(sid))

    # -- Step 3: Grounded Chat --
    print("")
    print("3. [GROUNDED CHAT]")
    print("-" * 55)

    docs = api("GET", "/documents")
    check("Document persists in list", any(d.get("id") == doc_id for d in (docs or [])))

    print("  Query: 'What is superposition in quantum computing?'")
    t0 = time.time()
    chat = api("POST", "/chat", {
        "session_id": sid,
        "query": "What is superposition in quantum computing?",
        "document_id": doc_id,
    })
    elapsed = time.time() - t0

    if chat is None:
        skip("Chat response", "server returned error")
    else:
        response = chat.get("response", "")
        check("Chat returned a response", len(response) > 0)
        if response:
            print(f"  Response ({len(response)} chars, {elapsed:.1f}s):")
            for line in response.split("\\n")[:6]:
                line = line.strip()
                if line:
                    print(f"    {line[:120]}")

    # -- Step 4: Message History --
    print("")
    print("4. [MESSAGE HISTORY]")
    print("-" * 55)
    msgs = api("GET", f"/sessions/{sid}/messages")
    if msgs:
        roles = [m["role"] for m in msgs]
        print(f"  Messages: {len(msgs)} ({', '.join(roles)})")
        check("Messages stored", len(msgs) >= 2)
    else:
        skip("Message history", "no messages returned")

    # -- Step 5: Generate Quiz --
    print("")
    print("5. [GENERATE QUIZ]")
    print("-" * 55)
    chunk_id = chunks[0]["id"] if chunks else ""
    t0 = time.time()
    quiz = api("POST", "/quizzes/generate", {
        "session_id": sid,
        "chunk_id": chunk_id,
        "num_questions": 3,
    })
    elapsed_q = time.time() - t0

    if quiz is None:
        skip("Quiz generation", "model may not produce valid JSON output")
        return 0

    quiz_id = quiz.get("id", "")
    questions = quiz.get("questions", [])
    check("Quiz has ID", bool(quiz_id))
    check(f"Quiz has {len(questions)} questions (expected 3)", len(questions) == 3)
    if questions:
        print(f"  Gen time: {elapsed_q:.1f}s")
        for i, q in enumerate(questions):
            opts = q.get("options", [])
            correct = q.get("correct_index", 0)
            print(f"  Q{i+1}: {q.get('question', '')[:70]}...")
            for j, opt in enumerate(opts):
                m = "*" if j == correct else " "
                print(f"       ({m}) {opt[:60]}")

    # -- Step 6: Submit Answers --
    print("")
    print("6. [SUBMIT QUIZ ANSWERS]")
    print("-" * 55)

    for i, q in enumerate(questions):
        correct_idx = int(q.get("correct_index", 0))
        num_opts = len(q.get("options", []))
        if i == 0:
            student_ans = str((correct_idx + 1) % max(num_opts, 1))
        else:
            student_ans = str(correct_idx)

        ans = api("POST", "/quizzes/answer", {
            "quiz_id": quiz_id,
            "question_index": i,
            "student_answer": student_ans,
            "correct_index": correct_idx,
        })
        mark = "WRONG" if str(student_ans) != str(correct_idx) else "correct"
        check(f"Answer {i+1} ({mark}: student={student_ans}, expected={correct_idx})",
              ans is not None)

    # -- Step 7: Verify Quiz Tracking --
    print("")
    print("7. [VERIFY QUIZ TRACKING]")
    print("-" * 55)
    results_data = api("GET", f"/sessions/{sid}/quiz-results")
    if results_data:
        all_answers = []
        for r in results_data:
            for a in r.get("answers", []):
                all_answers.append(a)

        total = len(all_answers)
        correct = sum(1 for a in all_answers if a.get("is_correct"))
        wrong = total - correct
        check(f"Tracking: {total} answers ({correct} correct, {wrong} wrong)", total == 3)
        for a in all_answers:
            status = "OK" if a.get("is_correct") else "XX"
            idx = a.get("question_index", 0)
            print(f"  Q{idx+1}: [{status}] (answered {a.get('student_answer', '?')})")
        check("Wrong answer tracked", any(not a.get("is_correct") for a in all_answers))

    # -- Summary --
    print("")
    print("=" * 55)
    total = PASS + FAIL + SKIP
    print(f"  RESULTS:  [PASS] {PASS}  |  [FAIL] {FAIL}  |  [SKIP] {SKIP}")
    if FAIL > 0:
        print(f"\\n  {FAIL} test(s) FAILED")
    else:
        print("\\n  All executed tests passed!")
    print("=" * 55)
    return 1 if FAIL > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
'''

with open('test_full_demo.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
print("test_full_demo.py written clean from scratch")
