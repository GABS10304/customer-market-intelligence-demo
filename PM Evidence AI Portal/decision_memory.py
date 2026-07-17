import os
from datetime import datetime

BASE_PATH = "pm_brain"


def ensure_dirs():
    os.makedirs(os.path.join(BASE_PATH, "decisions"), exist_ok=True)
    os.makedirs(os.path.join(BASE_PATH, "hypotheses"), exist_ok=True)


# ========================
# DECISION SPEICHERN
# ========================
def save_decision(data):
    ensure_dirs()

    slug = data["slug"]
    file_path = os.path.join(BASE_PATH, "decisions", f"{slug}.md")

    content = f"""# decision: {slug}

created_at: {datetime.now().date()}
status: active
decision: {data['decision']}

## context
- problem_cluster: {data['problem']}
- frequency: {data.get('frequency', 'n/a')}
- source: {data.get('source', 'unknown')}

## reasoning
{data['reasoning']}

## evidence
{chr(10).join(["- " + e for e in data.get("evidence", [])])}

## risks
{data.get('risks', '-')}

## reopen_if
{data.get('reopen', '-')}

## owner
pm: Gabriel Strecker
"""

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path


# ========================
# HYPOTHESE SPEICHERN
# ========================
def save_hypothesis(data):
    ensure_dirs()

    slug = data["slug"]
    file_path = os.path.join(BASE_PATH, "hypotheses", f"{slug}.md")

    content = f"""# hypothesis: {slug}

created_at: {datetime.now().date()}
status: open

## hypothesis
{data['text']}

## evidence
{chr(10).join(["- " + e for e in data.get("evidence", [])])}

## confidence
{data.get('confidence', 'medium')}

## test_plan
{data.get('test_plan', '-')}

## success_metric
{data.get('success_metric', '-')}

## owner
pm: Gabriel Strecker
"""

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path