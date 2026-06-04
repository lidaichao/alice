from pathlib import Path

p = Path(__file__).resolve().parents[1] / "backend" / "ai_bridge.py"
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
out = []
skip = False
for line in lines:
    if line.startswith("        if False and (user_cfg.get(\"engine\")"):
        skip = True
        continue
    if skip:
        if line == '        yield b"data: [DONE]\\n\\n"\n':
            skip = False
        continue
    out.append(line)
p.write_text("".join(out), encoding="utf-8")
print(len(lines), "->", len(out))
