import re

with open('test_full_demo.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Replace the chunks content access
old1 = "    check(\"Document has chunks\", len(chunks) > 0, f\"got {len(chunks)} chunks\")\n    if chunks:\n        c0 = chunks[0]\n        preview = c0.get(\"content_preview\", \"\")\n        print(f\"  Chunk 0 ({len(preview)} chars): {preview[:80]}...\")\n        print(f\"  Embedding vector: {len(c0.get('embedding', []))} dims\")"

# The actual content in the file might be different
# Let me find what's there
idx = content.find('chunks[0]')
print(f"First 'chunks[0]' at position {idx}")
if idx >= 0:
    context = content[idx-100:idx+100]
    print(f"Context: {repr(context)}")

# Find content access patterns
for m in re.finditer(r"chunks\[0\]\['content'\]", content):
    start = max(0, m.start() - 50)
    end = min(len(content), m.end() + 50)
    print(f"\nFound at {m.start()}:")
    print(repr(content[start:end]))

print("\n--- File content ---")
print(content)
