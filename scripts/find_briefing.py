import os

def find_briefing_logic():
    root = r"c:\Users\emreo\Documents\Gemini"
    for dirpath, dirnames, filenames in os.walk(root):
        if ".venv" in dirpath or ".git" in dirpath:
            continue
        for filename in filenames:
            if filename.endswith(".py"):
                path = os.path.join(dirpath, filename)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                        if "Host A" in content and "Sarah" in content and "Marcus" in content:
                            print(f"FOUND: {path}")
                except:
                    pass

if __name__ == "__main__":
    find_briefing_logic()
