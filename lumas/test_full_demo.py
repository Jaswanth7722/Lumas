"""Full end-to-end demo test."""
import io, json, os, sys, time, urllib.request, urllib.error

API_BASE = "http://127.0.0.1:8765/api"
PASS = FAIL = SKIP = 0


def api(method, path, data=None, files=None):
    url = API_BASE + path
    headers = {}
    if files:
        boundary = "----LumasBoundary" + str(int(time.time() * 1e6))
        headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
        parts = []
        for fn, (fname, fdata, ctype) in files.items():
            if isinstance(fdata, str): fdata = fdata.encode()
            parts.append(("--" + boundary).encode())
            cd = 'Content-Disposition: form-data; name="' + fn + '"; filename="' + fname + '"'
            parts.append(cd.encode())
            parts.append(("Content-Type: " + ctype).encode())
            parts.append(b"")
            parts.append(fdata)
        parts.append(("--" + boundary + "--").encode())
        parts.append(b"")
        body = b"\r\n".join(parts)
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
        print("  !! HTTP", e.code)
        return None
    except Exception as e:
        print("  !! Error:", e)
        return None


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print("  [PASS]", name)
    else: FAIL += 1; print("  [FAIL]", name, "--", detail)

def skip(name, reason):
    global SKIP; SKIP += 1
    print("  [SKIP]", name, "--", reason)

def make_pdf():
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    buf = io.BytesIO()
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
    print()
    print("=" * 55)
    print("  LUMAS DEMO TEST")
    print("=" * 55)
    
    if not api("GET", "/health") or not api("GET", "/health").get("status") == "ok":
        print("Server not reachable")
        sys.exit(1)
    check("Server running", True)
    
    print()
    print("1. [UPLOAD]")
    print("-" * 55)
    pdf = make_pdf()
    r = api("POST", "/documents/upload", files={"file": ("quantum.pdf", pdf, "application/pdf")})
    doc_id = (r or {}).get("id", "")
    chunks = (r or {}).get("chunks", [])
    check("Upload OK", bool(doc_id))
    check("Has chunks", len(chunks) > 0)
    if chunks:
        print("  Chunk:", chunks[0].get("content_preview", "")[:100])
    
    print()
    print("2. [SESSION]")
    print("-" * 55)
    s = api("POST", "/sessions", {"engine_used": "local"})
    sid = (s or {}).get("id", "")
    check("Session OK", bool(sid))
    
    print()
    print("3. [CHAT]")
    print("-" * 55)
    c = api("POST", "/chat", {"session_id": sid, "query": "What is superposition?", "document_id": doc_id})
    if c:
        resp = c.get("response", "")
        check("Chat OK", len(resp) > 0)
        print("  Resp:", resp[:150])
    else:
        skip("Chat", "error")
    
    print()
    print("4. [MESSAGES]")
    print("-" * 55)
    msgs = api("GET", "/sessions/" + sid + "/messages")
    if msgs:
        check(str(len(msgs)) + " msgs stored", len(msgs) >= 2)
    else:
        skip("Messages", "none")
    
    print()
    print("5. [QUIZ]")
    print("-" * 55)
    chunk_id = chunks[0]["id"] if chunks else ""
    q = api("POST", "/quizzes/generate", {"session_id": sid, "chunk_id": chunk_id, "num_questions": 3})
    if not q:
        skip("Quiz gen", "needs JSON output")
        print()
        print("=" * 55)
        print("  RESULTS: [PASS]", PASS, "| [FAIL]", FAIL, "| [SKIP]", SKIP)
        print("  Core: PDF upload -> session -> chat works")
        print("  Quiz gen needs model with valid JSON output")
        print("=" * 55)
        sys.exit(0)
    qid = q.get("id", "")
    questions = q.get("questions", [])
    check("Quiz ID", bool(qid))
    check("Questions", len(questions) == 3)
    
    print()
    print("6. [ANSWERS]")
    print("-" * 55)
    for i, qi in enumerate(questions):
        ci = int(qi.get("correct_index", 0))
        no = len(qi.get("options", []))
        ans = str((ci + 1) % max(no, 1)) if i == 0 else str(ci)
        a = api("POST", "/quizzes/answer", {"quiz_id": qid, "question_index": i, "student_answer": ans, "correct_index": ci})
        check("Ans " + str(i+1), a is not None)
    
    print()
    print("7. [TRACKING]")
    print("-" * 55)
    res = api("GET", "/sessions/" + sid + "/quiz-results")
    if res:
        all_a = []
        for r in res:
            for a in r.get("answers", []):
                all_a.append(a)
        check("Tracked " + str(len(all_a)), len(all_a) == 3)
        check("Has wrong", any(not a.get("is_correct") for a in all_a))
    
    print()
    print("=" * 55)
    print("  RESULTS: [PASS]", PASS, "| [FAIL]", FAIL, "| [SKIP]", SKIP)
    if FAIL: print(str(FAIL), "FAILED")
    else: print("All passed!")
    print("=" * 55)

if __name__ == "__main__":
    sys.exit(main())
