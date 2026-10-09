import json

import os

import threading

from datetime import date

from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__)

# Protect progress.json from overlapping requests.

progress_lock = threading.RLock()

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
SENTENCES = load_json("sentences.json", {"sentences": []})

COLORS = load_json("games/colors.json", {"colors": []})


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
        "sentences": {},

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

    # Automatically add sentence tracking to old progress.json files
    if "sentences" not in p:
        p["sentences"] = {}
        save_progress(p)

    return p

def save_progress(p):

    """Atomically replace progress.json so interrupted/concurrent writes cannot corrupt it."""

    temp_path = "progress.json.tmp"

    with progress_lock:

        with open(temp_path, "w", encoding="utf-8") as f:

            json.dump(p, f, indent=2, ensure_ascii=False)

            f.flush()

            os.fsync(f.fileno())

        os.replace(temp_path, "progress.json")

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











# ============================================================
# COLOR MEMORY GAME
# ============================================================

@app.route("/games/colors")
def colors_page():
    return render_template(
        "games/color-game.html",
        colors=COLORS["colors"]
    )


@app.route("/games/colors/answer", methods=["POST"])
def colors_answer():
    data = request.get_json(silent=True) or {}

    color_id = data.get("color_id")
    user_answer = data.get("answer", "")

    color = next(
        (c for c in COLORS["colors"] if c["id"] == color_id),
        None
    )

    if not color:
        return jsonify({
            "ok": False,
            "error": "Color not found"
        }), 404

    if not isinstance(user_answer, str):
        return jsonify({
            "ok": False,
            "error": "Answer must be text"
        }), 400

    expected = color["tagalog"].strip().casefold()
    received = user_answer.strip().casefold()

    correct = received != "" and received == expected

    with progress_lock:
        p = get_progress()

        games = p.setdefault("games", {})
        colors_progress = games.setdefault("colors", {})

        stats = colors_progress.setdefault(color_id, {
            "correct": 0,
            "wrong": 0,
            "wrong_streak": 0
        })

        if correct:
            stats["correct"] += 1
            stats["wrong_streak"] = 0
        else:
            stats["wrong"] += 1
            stats["wrong_streak"] += 1

        save_progress(p)

        mastered = sum(
            colors_progress.get(c["id"], {}).get("correct", 0) >= 3
            for c in COLORS["colors"]
        )

    return jsonify({
        "ok": True,
        "correct": correct,
        "answer": color["tagalog"],
        "stats": stats,
        "mastered": mastered,
        "total": len(COLORS["colors"])
    })


@app.route("/games/colors/reset", methods=["POST"])
def colors_reset():
    with progress_lock:
        p = get_progress()

        p.setdefault("games", {})["colors"] = {}

        save_progress(p)

    return jsonify({
        "ok": True,
        "mastered": 0,
        "total": len(COLORS["colors"])
    })











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

@app.route("/restaurant")

def restaurant_game():

    return render_template(

        "games/restaurant/restaurant-game.html"

    )

@app.route("/word-snake")

def word_snake():

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

    # Keep the game pool manageable

    game_words = game_words[:30]

    return render_template(

        "word-snake.html",

        game_words=game_words

    )

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

# ============================================================
# SENTENCE PRACTICE
# ============================================================

SENTENCE_MASTERY_CORRECT = 5
SENTENCE_MASTERY_ACCURACY = 0.80

def normalize_sentence(text):
    if not isinstance(text, str):
        return ""
    text = text.strip().lower()
    for char in ".,!?;:\"'“”‘’":
        text = text.replace(char, "")
    return " ".join(text.split())

def sentence_is_mastered(stats):
    return stats.get("correct", 0) >= 1



def get_sentence_mastery(progress):
    sentence_progress = progress.get("sentences", {})
    mastered = 0
    for sentence in SENTENCES.get("sentences", []):
        stats = sentence_progress.get(sentence.get("id"), {})
        if sentence_is_mastered(stats):
            mastered += 1
    return mastered

def find_sentence(sentence_id):
    for sentence in SENTENCES.get("sentences", []):
        if sentence.get("id") == sentence_id:
            return sentence
    return None

@app.route("/sentences")
def sentence_practice():
  return render_template("games/sentence-practice/sentence-practice.html")

@app.route("/sentence-next")
def sentence_next():
    with progress_lock:
        p = get_progress()
        p.setdefault("sentences", {})
        sentences = SENTENCES.get("sentences", [])
        total = len(sentences)

        if total == 0:
            return jsonify({"ok": False, "complete": True, "mastered": 0, "total": 0})

        mastered = get_sentence_mastery(p)
        candidates = []

        for index, sentence in enumerate(sentences):
            sentence_id = sentence.get("id")
            stats = p["sentences"].get(sentence_id, {
                "correct": 0, "wrong": 0, "wrong_streak": 0
            })

            if sentence_is_mastered(stats):
                continue

            correct = stats.get("correct", 0)
            wrong = stats.get("wrong", 0)
            attempts = correct + wrong
            score = (-1000 + index) if attempts == 0 else ((wrong * 2) - correct)
            candidates.append({
                "sentence": sentence, "stats": stats, "score": score, "index": index
            })

        if not candidates:
            return jsonify({
                "ok": True, "complete": True, "mastered": mastered, "total": total
            })

        unseen = [
            item for item in candidates
            if item["stats"].get("correct", 0) + item["stats"].get("wrong", 0) == 0
        ]

        if unseen:
            chosen = unseen[0]
        else:
            candidates.sort(key=lambda item: item["score"], reverse=True)
            chosen = candidates[0]

        sentence = chosen["sentence"]
        return jsonify({
            "ok": True,
            "complete": False,
            "sentence": {
                "id": sentence.get("id"),
                "english": sentence.get("english", ""),
                "tagalog": sentence.get("tagalog", ""),
                "image": sentence.get("image", ""),
                "number": chosen["index"] + 1
            },
            "mastered": mastered,
            "total": total
        })

@app.route("/sentence-answer", methods=["POST"])
def sentence_answer():
    data = request.get_json(silent=True) or {}
    sentence_id = data.get("sentence_id")
    user_answer = data.get("answer", "")

    if not sentence_id:
        return jsonify({"ok": False, "error": "Missing sentence_id"}), 400

    sentence = find_sentence(sentence_id)
    if not sentence:
        return jsonify({"ok": False, "error": "Sentence not found"}), 404

    expected = normalize_sentence(sentence.get("tagalog", ""))
    received = normalize_sentence(user_answer)
    correct = received != "" and received == expected

    with progress_lock:
        p = get_progress()
        p.setdefault("sentences", {})
        stats = p["sentences"].setdefault(sentence_id, {
            "correct": 0, "wrong": 0, "wrong_streak": 0
        })

        if correct:
            stats["correct"] = stats.get("correct", 0) + 1
            stats["wrong_streak"] = 0
        else:
            stats["wrong"] = stats.get("wrong", 0) + 1
            stats["wrong_streak"] = stats.get("wrong_streak", 0) + 1

        save_progress(p)
        mastered = get_sentence_mastery(p)
        total = len(SENTENCES.get("sentences", []))

    return jsonify({
        "ok": True,
        "correct": correct,
        "answer": sentence.get("tagalog", ""),
        "stats": {
            "correct": stats["correct"],
            "wrong": stats["wrong"],
            "wrong_streak": stats["wrong_streak"]
        },
        "sentence_mastered": sentence_is_mastered(stats),
        "mastered": mastered,
        "total": total
    })

@app.route("/sentence-reset", methods=["POST"])
def sentence_reset():
    with progress_lock:
        p = get_progress()
        p["sentences"] = {}
        save_progress(p)

    return jsonify({
        "ok": True,
        "mastered": 0,
        "total": len(SENTENCES.get("sentences", []))
    })

# ---------------- STUDY TIMER ----------------

# ---------------- STUDY TIMER ----------------

@app.route("/study-time", methods=["GET"])

def study_time():

    with progress_lock:

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

    try:

        seconds = int(data.get("seconds", 0))

    except (TypeError, ValueError):

        seconds = 0

    # Only accept small timer updates

    seconds = max(0, min(seconds, 60))

    with progress_lock:

        p = get_progress()

        today = date.today().isoformat()

        # Make sure study structure exists

        if "study" not in p:

            p["study"] = {

                "daily_goal_minutes": 120,

                "total_seconds": 0,

                "days": {}

            }

        if "days" not in p["study"]:

            p["study"]["days"] = {}

        if "total_seconds" not in p["study"]:

            p["study"]["total_seconds"] = 0

        p["study"]["days"][today] = (

            p["study"]["days"].get(today, 0)

            + seconds

        )

        p["study"]["total_seconds"] += seconds

        save_progress(p)

        today_seconds = p["study"]["days"][today]

        total_seconds = p["study"]["total_seconds"]

    return jsonify({

        "ok": True,

        "today_seconds": today_seconds,

        "total_seconds": total_seconds,

    })

@app.route("/study-goal", methods=["POST"])

def study_goal():

    data = request.get_json(silent=True) or {}

    try:

        minutes = int(data.get("minutes", 120))

    except (TypeError, ValueError):

        minutes = 120

    # 5 minutes minimum, 8 hours maximum

    minutes = max(5, min(minutes, 480))

    with progress_lock:

        p = get_progress()

        # Make sure study structure exists

        if "study" not in p:

            p["study"] = {

                "daily_goal_minutes": 120,

                "total_seconds": 0,

                "days": {}

            }

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
    sentences = p.get("sentences", {})

    save_progress({

        "level_id": LEVELS["levels"][0]["id"],

        "step_index": 0,

        "words": {},
        "sentences": sentences,

        "completed_levels": [],

        "study": study,

    })

    return redirect(url_for("menu"))





# ============================================================
# WORD RAIN GAME
# ============================================================

WORD_RAIN_MASTERY = 3
WORD_RAIN_MAX_ANSWER_LENGTH = 120


def word_rain_normalize(value):
    """Normalize a translation for comparison."""
    import unicodedata

    value = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(
        value.strip().lower().rstrip(".!?").split()
    )


def word_rain_translations(english):
    """Support translations such as 'want / like'."""
    import re

    if isinstance(english, list):
        parts = english
    else:
        parts = re.split(r"[/;,]", str(english or ""))

    return {
        word_rain_normalize(part)
        for part in parts
        if word_rain_normalize(part)
    }


def word_rain_vocabulary():
    """Convert the existing VOCAB dictionary for Word Rain."""
    result = []

    for tagalog, details in VOCAB.get("words", {}).items():
        if not isinstance(details, dict):
            continue

        english = details.get("english")

        if not english or not tagalog:
            continue

        result.append({
            "id": tagalog,
            "tagalog": tagalog,
            "english": english
        })

    return result


def word_rain_required(level):
    """Level 1: 10, Level 2: 15, Level 3: 20, etc."""
    return 10 + (level - 1) * 5


def word_rain_start_index(level):
    """Number of unique words assigned to earlier levels."""
    n = level - 1
    return n * (20 + (n - 1) * 5) // 2


def word_rain_level_words(vocabulary, level):
    start = word_rain_start_index(level)
    end = start + word_rain_required(level)
    return vocabulary[start:end]


def word_rain_store(progress):
    """Get Word Rain progress without affecting other games."""
    games = progress.setdefault("games", {})

    return games.setdefault("word_rain", {
        "words": {},
        "highest_unlocked_level": 1,
        "best_score": 0
    })


def word_rain_level_mastered(store, vocabulary, level):
    level_words = word_rain_level_words(vocabulary, level)

    if len(level_words) < word_rain_required(level):
        return False

    saved_words = store.get("words", {})

    return all(
        saved_words.get(word["id"], {}).get("correct", 0)
        >= WORD_RAIN_MASTERY
        for word in level_words
    )


def word_rain_unlock_levels(store, vocabulary):
    """Unlock consecutive levels when all their words are mastered."""
    level = 1

    while word_rain_level_mastered(store, vocabulary, level):
        next_level = level + 1

        if (
            len(word_rain_level_words(vocabulary, next_level))
            < word_rain_required(next_level)
        ):
            break

        level = next_level

    store["highest_unlocked_level"] = level
    return level


# ------------------------------------------------------------
# GET: WORD RAIN GAME
# ------------------------------------------------------------

@app.route("/games/word-rain")
def word_rain_game():

    vocabulary = word_rain_vocabulary()

    with progress_lock:
        progress = get_progress()
        store = word_rain_store(progress)

        level = word_rain_unlock_levels(store, vocabulary)
        save_progress(progress)

        saved_words = dict(store.get("words", {}))

    return render_template(
        "games/word-rain.html",
        words=vocabulary,
        level=level,
        word_progress=saved_words
    )


# ------------------------------------------------------------
# POST: SAVE TRANSLATION ANSWER OR MISSED WORD
# ------------------------------------------------------------

@app.route("/games/word-rain/answer", methods=["POST"])
def word_rain_answer():

    data = request.get_json(silent=True) or {}

    word_id = str(data.get("word_id", ""))
    answer = word_rain_normalize(data.get("answer", ""))
    missed = data.get("missed") is True

    try:
        level = int(data.get("level", 1))
    except (TypeError, ValueError):
        return jsonify(
            ok=False,
            error="Invalid level"
        ), 400

    if level < 1:
        return jsonify(
            ok=False,
            error="Invalid level"
        ), 400

    # A missed falling word has no typed answer.
    # Normal submissions must include a translation.
    if (
        (not missed and not answer)
        or len(answer) > WORD_RAIN_MAX_ANSWER_LENGTH
    ):
        return jsonify(
            ok=False,
            error="Invalid translation"
        ), 400

    vocabulary = word_rain_vocabulary()
    level_words = word_rain_level_words(vocabulary, level)

    word = next(
        (item for item in level_words if item["id"] == word_id),
        None
    )

    if word is None:
        return jsonify(
            ok=False,
            error="Word does not belong to this level"
        ), 400

    # Missed words are always incorrect.
    # Otherwise accept any valid English translation.
    correct = (
        not missed
        and answer in word_rain_translations(word["english"])
    )

    with progress_lock:
        progress = get_progress()
        store = word_rain_store(progress)

        unlocked = word_rain_unlock_levels(store, vocabulary)

        if level > unlocked:
            return jsonify(
                ok=False,
                error="Level is locked"
            ), 403

        saved_words = store.setdefault("words", {})

        stats = saved_words.setdefault(word_id, {
            "correct": 0,
            "wrong": 0,
            "wrong_streak": 0
        })

        if correct:
            if stats["correct"] < WORD_RAIN_MASTERY:
                stats["correct"] += 1

            stats["wrong_streak"] = 0
        else:
            stats["wrong"] += 1
            stats["wrong_streak"] += 1

        mastered = stats["correct"] >= WORD_RAIN_MASTERY

        level_complete = word_rain_level_mastered(
            store,
            vocabulary,
            level
        )

        unlocked = word_rain_unlock_levels(store, vocabulary)

        save_progress(progress)

        saved_stats = dict(stats)

    return jsonify(
        ok=True,
        correct=correct,
        missed=missed,
        word_id=word_id,
        answer=word["english"],
        stats=saved_stats,
        mastered=mastered,
        level_complete=level_complete,
        highest_unlocked_level=unlocked
    )


# ------------------------------------------------------------
# POST: RESET WORD RAIN ONLY
# ------------------------------------------------------------

@app.route("/games/word-rain/reset", methods=["POST"])
def word_rain_reset():

    with progress_lock:
        progress = get_progress()

        games = progress.setdefault("games", {})

        games["word_rain"] = {
            "words": {},
            "highest_unlocked_level": 1,
            "best_score": 0
        }

        save_progress(progress)

    return jsonify(
        ok=True,
        level=1,
        message="Word Rain progress reset"
    )


if __name__ == "__main__":
    app.run(debug=True)
