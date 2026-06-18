import sys
from pypdf import PdfReader

for path in sys.argv[1:]:
    reader = PdfReader(path)
    out = []
    for i, page in enumerate(reader.pages):
        out.append(f"\n===== PAGE {i+1} =====\n")
        out.append(page.extract_text() or "")
    text = "".join(out)
    target = path.rsplit(".", 1)[0] + ".extracted.txt"
    with open(target, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"{path} -> {target} | pages={len(reader.pages)} chars={len(text)}")
