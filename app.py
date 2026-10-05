import json
import os
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, jsonify



app = Flask(__name__)

WRONG_THRESHOLD = 3


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


LEVELS = load_json("levels.json", {"levels": []})
VOCAB = load_json("vocabulary.json", {"words": {}})


def expand_steps(steps):
    """Turn each 'teach' step into preview + word steps + repeat preview."""
    out = []
    for step in steps:
        if step.get("type") == "teach":
            new_words = step.get("new_words", [])
            out.append({
                "type": "preview",
                "phrase": step["phrase"],
                "translation": step["translation"],
                "words": new_words,
            })
            for key in new_words:
                out.append({"type": "word", "key": key})
            out.append({
                "type": "preview",
                "phrase": step["phrase"],
                "translation": step["translation"],
                "words": new_words,
                "note": step.get("note", "Now you see the pieces."),
            })
        else:
            out.append(step)
    return out


for lvl in LEVELS["levels"]:
    lvl["steps"] = expand_steps(lvl["steps"])


def validate_levels():
    warnings = []
    for lvl in LEVELS["levels"]:
        seen_words = set()
        for i, step in enumerate(lvl["steps"]):
            if step["type"] == "word":
                key = step["key"]
                if key not in VOCAB["words"]:
                    warnings.append(f"{lvl['id']} step {i}: '{key}' not in vocabulary.json")
                if key in seen_words:
                    warnings.append(f"{lvl['id']} step {i}: '{key}' appears twice")
                seen_words.add(key)
    if warnings:
        print()
        print("--- level warnings ---")
        for w in warnings:
            print("  ", w)
        print("----------------------")
        print(f"{len(warnings)} warning(s). App will still start.")
        print()
    else:
        print("Levels OK.")


validate_levels()


def get_progress():
    p = load_json("progress.json", {
        "level_id": LEVELS["levels"][0]["id"] if LEVELS["levels"] else None,
        "step_index": 0,
        "words": {},
        "completed_levels": [],
        "study": {
            "daily_goal_minutes": 120,
            "total_seconds": 0,
            "days": {}
        }
    })

    # Automatically add study tracking to old progress.json files
    if "study" not in p:
        p["study"] = {
            "daily_goal_minutes": 120,
            "total_seconds": 0,
            "days": {}
        }
        save_json("progress.json", p)

    return p


def save_progress(p):
    save_json("progress.json", p)


def get_level(level_id):
    for lvl in LEVELS["levels"]:
        if lvl["id"] == level_id:
            return lvl
    return None


def get_level_index(level_id):
    for i, lvl in enumerate(LEVELS["levels"]):
        if lvl["id"] == level_id:
            return i
    return -1


def is_level_unlocked(level_id, completed_levels):
    i = get_level_index(level_id)
    if i <= 0:
        return True
    prev_id = LEVELS["levels"][i - 1]["id"]
    return prev_id in completed_levels


def level_status(level_id, completed_levels):
    if level_id in completed_levels:
        return "completed"
    if is_level_unlocked(level_id, completed_levels):
        return "unlocked"
    return "locked"


def find_first_step_for_word(word_key, level_id):
    """First preview that contains this word. Falls back to the word card."""
    level = get_level(level_id)
    if not level:
        return None
    first_preview = None
    first_word_step = None
    for i, step in enumerate(level["steps"]):
        if step["type"] == "preview" and word_key in step.get("words", []):
            if first_preview is None:
                first_preview = i
        if step["type"] == "word" and step.get("key") == word_key:
            if first_word_step is None:
                first_word_step = i
    return first_preview if first_preview is not None else first_word_step


def pick_drill_words(progress, n=14, must_include=None):
    must_include = must_include or []
    rows = []
    for key, rec in progress["words"].items():
        if key in must_include:
            continue
        correct = rec.get("correct", 0)
        wrong = rec.get("wrong", 0)
        if correct + wrong == 0:
            continue
        score = (wrong * 2) - correct
        rows.append((score, key))
    rows.sort(reverse=True)
    picked = list(must_include) + [k for _, k in rows[: n - len(must_include)]]
    return picked


@app.route("/")
def home():
    return redirect(url_for("menu"))


@app.route("/menu")
def menu():
    p = get_progress()
    completed = p.get("completed_levels", [])
    current_id = p["level_id"]

    levels_view = []
    for i, lvl in enumerate(LEVELS["levels"]):
        status = level_status(lvl["id"], completed)

        if lvl["id"] == current_id and status != "completed":
            progress_info = f"Step {p['step_index'] + 1} of {len(lvl['steps'])}"
        elif status == "completed":
            progress_info = "Completed"
        elif status == "locked":
            prev = LEVELS["levels"][i - 1]
            progress_info = f'Complete "{prev["title"]}" to unlock'
        else:
            progress_info = ""

        levels_view.append({
            "id": lvl["id"],
            "title": lvl["title"],
            "description": lvl["description"],
            "status": status,
            "progress_info": progress_info,
            "is_current": lvl["id"] == current_id,
        })

    today = date.today().isoformat()
    study = p["study"]

    return render_template(
        "menu.html",
        levels=levels_view,
        study=study,
        today_seconds=study["days"].get(today, 0)
    )

@app.route("/level/<level_id>")
def level_view(level_id):
    level = get_level(level_id)
    if not level:
        return "Level not found", 404

    p = get_progress()
    completed = p.get("completed_levels", [])
    if not is_level_unlocked(level_id, completed):
        return redirect(url_for("menu"))

    # one-shot reset: ?restart=1 resets and redirects to the clean URL
    if request.args.get("restart") == "1":
        p["level_id"] = level_id
        p["step_index"] = 0
        save_progress(p)
        return redirect(url_for("level_view", level_id=level_id))

    # switching levels: reset to step 0
    if p["level_id"] != level_id:
        p["level_id"] = level_id
        p["step_index"] = 0
        save_progress(p)

    steps = level["steps"]
    idx = min(p["step_index"], len(steps) - 1)
    step = dict(steps[idx])

    if step.get("type") == "drill":
        step["words"] = pick_drill_words(
            p, n=14, must_include=step.get("must_include")
        )

    if step.get("type") == "win" and level_id not in completed:
        p["completed_levels"].append(level_id)
        save_progress(p)

    return render_template(
        "level.html",
        level=level,
        step=step,
        step_index=idx,
        total_steps=len(steps),
        vocab=VOCAB["words"],
        progress=p,
    )



@app.route("/word-shooter")
def word_shooter():
    p = get_progress()

    progress_words = p.get("words", {})
    vocabulary_words = VOCAB.get("words", {})

    game_words = []

    for word, stats in progress_words.items():
        vocab = vocabulary_words.get(word)

        if not vocab:
            continue

        english = vocab.get("english")

        if not english:
            continue

        correct = stats.get("correct", 0)
        wrong = stats.get("wrong", 0)
        wrong_streak = stats.get("wrong_streak", 0)

        attempts = correct + wrong

        if attempts == 0:
            continue

        accuracy = correct / attempts

        game_words.append({
            "answer": word,
            "english": english,
            "correct": correct,
            "wrong": wrong,
            "wrong_streak": wrong_streak,
            "accuracy": accuracy
        })

    # Weakest words first
    game_words.sort(
        key=lambda item: (
            item["accuracy"],
            -item["wrong"]
        )
    )

    # Limit game pool
    game_words = game_words[:30]

    return render_template(
        "word-shooter.html",
        game_words=game_words
    )


@app.route("/word-shooter-answer", methods=["POST"])
def word_shooter_answer():
    data = request.get_json(silent=True) or {}

    word = data.get("word")
    correct = data.get("correct")

    if not word:
        return jsonify({
            "ok": False,
            "error": "Missing word"
        }), 400

    if not isinstance(correct, bool):
        return jsonify({
            "ok": False,
            "error": "Invalid correct value"
        }), 400

    p = get_progress()

    if "words" not in p:
        p["words"] = {}

    if word not in p["words"]:
        p["words"][word] = {
            "correct": 0,
            "wrong": 0,
            "wrong_streak": 0
        }

    stats = p["words"][word]

    if correct:
        stats["correct"] = stats.get("correct", 0) + 1
        stats["wrong_streak"] = 0

    else:
        stats["wrong"] = stats.get("wrong", 0) + 1
        stats["wrong_streak"] = stats.get("wrong_streak", 0) + 1

    save_progress(p)

    return jsonify({
        "ok": True,
        "word": word,
        "correct": stats["correct"],
        "wrong": stats["wrong"],
        "wrong_streak": stats["wrong_streak"]
    })


@app.route("/next-level")
def next_level():
    p = get_progress()
    i = get_level_index(p["level_id"])
    if i < 0 or i + 1 >= len(LEVELS["levels"]):
        return redirect(url_for("menu"))
    nxt = LEVELS["levels"][i + 1]["id"]
    p["level_id"] = nxt
    p["step_index"] = 0
    save_progress(p)
    return redirect(url_for("level_view", level_id=nxt))


@app.route("/answer", methods=["POST"])
def answer():
    data = request.get_json(silent=True) or {}
    word = data.get("word")
    correct = bool(data.get("correct", False))
    advance = bool(data.get("advance", True))
    p = get_progress()
    p.setdefault("completed_levels", [])
    reload_client = False
    went_back = False

    if word:
        rec = p["words"].setdefault(word, {
            "correct": 0, "wrong": 0, "wrong_streak": 0
        })

        if correct:
            rec["correct"] += 1
            rec["wrong_streak"] = 0
        else:
            rec["wrong"] += 1
            rec["wrong_streak"] = rec.get("wrong_streak", 0) + 1

            if advance and rec["wrong_streak"] >= WRONG_THRESHOLD:
                first = find_first_step_for_word(word, p["level_id"])
                if first is not None:
                    p["step_index"] = first
                    rec["wrong_streak"] = 0
                    reload_client = True
                    went_back = True

    if advance and correct:
        p["step_index"] += 1
        reload_client = True

    save_progress(p)
    return jsonify({
        "ok": True,
        "reload": reload_client,
        "went_back": went_back,
    })


# ---------------- STUDY TIMER ----------------

@app.route("/study-time", methods=["GET"])
def study_time():
    p = get_progress()
    study = p["study"]
    today = date.today().isoformat()
    today_seconds = study["days"].get(today, 0)
    goal_seconds = study["daily_goal_minutes"] * 60

    return jsonify({
        "today_seconds": today_seconds,
        "total_seconds": study["total_seconds"],
        "daily_goal_minutes": study["daily_goal_minutes"],
        "goal_met": today_seconds >= goal_seconds,
    })


@app.route("/study-time", methods=["POST"])
def save_study_time():
    data = request.get_json(silent=True) or {}
    seconds = int(data.get("seconds", 0))

    # Only accept small timer updates
    seconds = max(0, min(seconds, 60))

    p = get_progress()
    today = date.today().isoformat()

    p["study"]["days"][today] = p["study"]["days"].get(today, 0) + seconds
    p["study"]["total_seconds"] += seconds

    save_progress(p)

    return jsonify({
        "ok": True,
        "today_seconds": p["study"]["days"][today],
        "total_seconds": p["study"]["total_seconds"],
    })


@app.route("/study-goal", methods=["POST"])
def study_goal():
    data = request.get_json(silent=True) or {}
    minutes = int(data.get("minutes", 120))

    # 5 minutes minimum, 8 hours maximum
    minutes = max(5, min(minutes, 480))

    p = get_progress()
    p["study"]["daily_goal_minutes"] = minutes
    save_progress(p)

    return jsonify({
        "ok": True,
        "daily_goal_minutes": minutes,
    })


@app.route("/reset")
def reset():
    p = get_progress()

    # Keep study history even when learning progress is reset
    study = p["study"]

    save_progress({
        "level_id": LEVELS["levels"][0]["id"],
        "step_index": 0,
        "words": {},
        "completed_levels": [],
        "study": study,
    })

    return redirect(url_for("menu"))


if __name__ == "__main__":
    app.run(debug=True)