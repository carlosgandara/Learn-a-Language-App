import json
from pathlib import Path
import langcodes
import os
import re
import threading
import unicodedata
from datetime import date
from pathlib import Path
from flask import (
    Flask, render_template, request,
    redirect, url_for, jsonify, g
)
app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LESSONS_DIR = Path(__file__).resolve().parent / "data/languages/lessons"

def discover_languages():
    return {
        folder.name: langcodes.Language.get(folder.name).display_name("en")
        for folder in LESSONS_DIR.iterdir()
        if folder.is_dir() and (folder / "levels.json").is_file()
    }

LANGUAGES = discover_languages()

DEFAULT_LANGUAGE = "tl"
WRONG_THRESHOLD = 3
SENTENCE_MASTERY_CORRECT = 5
SENTENCE_MASTERY_ACCURACY = 0.80
WORD_RAIN_MASTERY = 3
WORD_RAIN_MAX_ANSWER_LENGTH = 120
progress_lock = threading.RLock()
language_cache = {}
# ============================================================
# JSON UTILITIES
# ============================================================
def load_json(path, default):
    path = Path(path)
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(
            data, f,
            indent=2,
            ensure_ascii=False
        )
# ============================================================
# LANGUAGE SELECTION
# ============================================================
def current_language():
    language = request.cookies.get(
        "language", DEFAULT_LANGUAGE
    )
    if language not in LANGUAGES:
        return DEFAULT_LANGUAGE
    return language
def language_name():
    return LANGUAGES[current_language()]
@app.context_processor
def inject_language():
    return {
        "current_language": current_language(),
        "language_name": language_name(),
        "available_languages": LANGUAGES
    }
@app.route("/language/<language>")
def select_language(language):
    if language not in LANGUAGES:
        return "Unsupported language", 404
    response = redirect(url_for("menu"))
    response.set_cookie(
        "language",
        language,
        max_age=31536000,
        httponly=True,
        samesite="Lax"
    )
    return response
# ============================================================
# LESSON ENGINE
# ============================================================
def expand_steps(steps):
    """Expand level-specific teaching steps without using vocabulary files."""
    out = []
    for step in steps:
        if step.get("type") != "teach":
            out.append(step)
            continue
        words = step.get("new_words", [])
        definitions = step.get("word_definitions", {})
        out.append({
            "type": "preview",
            "phrase": step["phrase"],
            "translation": step["translation"],
            "words": words,
        })
        for key in words:
            out.append({
                "type": "word",
                "key": key,
                "phrase": step["phrase"],
                "translation": step["translation"],
                "definition": definitions.get(key, ""),
            })
        out.append({
            "type": "preview",
            "phrase": step["phrase"],
            "translation": step["translation"],
            "words": words,
            "note": step.get("note", "Now you see the pieces."),
        })
    return out

def normalize_vocabulary(raw):
    """
    Accept either the old vocabulary format:
    {"words": {"kape": {"english": "coffee"}}}
    or language mappings:
    {"concept-0001": "kape"}
    Lesson vocabulary remains keyed by the actual
    words used in the lesson's new_words array.
    """
    if not isinstance(raw, dict):
        return {"words": {}}
    if "words" in raw:
        return raw
    return {"words": raw}
def load_language_data(language):
    """Load language levels without opening any vocabulary files."""
    if language not in LANGUAGES:
        raise ValueError("Unsupported language")
    key = ("levels", language)
    if key in language_cache:
        return language_cache[key]
    lesson_path = DATA_DIR / "languages" / "lessons" / language / "levels.json"
    levels = load_json(lesson_path, {"levels": []})
    if not isinstance(levels, dict) or not levels.get("levels"):
        raise FileNotFoundError(f"No lessons found for {language}: {lesson_path}")
    for level in levels["levels"]:
        level["steps"] = expand_steps(level["steps"])
    result = {"levels": levels}
    language_cache[key] = result
    return result


def load_vocabulary_data(language):
    """Load independent vocabulary concepts and translations."""
    if language not in LANGUAGES:
        raise ValueError("Unsupported language")
    key = ("vocabulary", language)
    if key in language_cache:
        return language_cache[key]
    # 2. Load the language's vocabulary.
    vocabulary_path = (
        DATA_DIR / "languages" / "vocabulary" / f"{language}.json"
    )
    translations = load_json(vocabulary_path, {})
    # 3. Load shared English concepts.
    concepts = load_json(
        DATA_DIR / "concepts.json",
        {}
    )
    # Support concepts stored as a dictionary or list.
    if isinstance(concepts, dict):
        concept_items = concepts.get("concepts", concepts)
    else:
        concept_items = concepts
    # Support concept-ID-to-word mappings.
    if isinstance(translations, dict):
        translation_items = translations.get(
            "translations", translations
        )
    else:
        translation_items = {}
    vocabulary = {"words": {}}
    if isinstance(concept_items, dict):
        concept_iter = []
        for concept_id, concept_data in concept_items.items():
            if isinstance(concept_data, dict):
                concept_iter.append({
                    "id": concept_id,
                    **concept_data
                })
    elif isinstance(concept_items, list):
        concept_iter = concept_items
    else:
        concept_iter = []
    for concept in concept_iter:
        if not isinstance(concept, dict):
            continue
        concept_id = concept.get("id")
        english = (
            concept.get("label")
            or concept.get("english")
        )
        translated = (
            translation_items.get(concept_id)
            if isinstance(translation_items, dict)
            else None
        )
        if not (
            concept_id
            and english
            and isinstance(translated, str)
            and translated.strip()
        ):
            continue
        word = translated.strip()
        vocabulary["words"][word] = {
            "english": english,
            "image": concept.get("image", "")
        }
    # 4. Normalize vocabulary for the existing templates.
    vocabulary = normalize_vocabulary(vocabulary)
    language_cache[key] = vocabulary
    return vocabulary


def get_lesson_words(level):
    """Word-card data drawn solely from this level's own teaching steps.

    When a word_definitions mapping is absent, the English field is blank;
    the full phrase translation remains available as contextual guidance.
    """
    words = {}
    for step in level.get("steps", []):
        if step.get("type") != "word":
            continue
        key = step.get("key")
        if not key:
            continue
        words.setdefault(key, {
            "english": step.get("definition", ""),
            "image": "",
            "phrase": step.get("phrase", ""),
            "translation": step.get("translation", ""),
        })
    return words


def get_levels():
    if not hasattr(g, "language_data"):
        g.language_data = load_language_data(
            current_language()
        )
    return g.language_data["levels"]
def get_vocabulary():
    return load_vocabulary_data(current_language())

def get_sentences():
    language = current_language()
    path = (
        DATA_DIR / "lessons" /
        language / "sentences.json"
    )
    if language == "tl" and not path.exists():
        path = BASE_DIR / "sentences.json"
    return load_json(
        path,
        {"sentences": []}
    )
def get_colors():
    language = current_language()
    path = (
        DATA_DIR / "lessons" /
        language / "colors.json"
    )
    if language == "tl" and not path.exists():
        path = BASE_DIR / "games" / "colors.json"
    return load_json(
        path,
        {"colors": []}
    )
def validate_levels(language):
    """Validate level structure only; no vocabulary-file dependency."""
    levels = load_language_data(language)["levels"]["levels"]
    warnings = []
    for level in levels:
        if not level.get("id"):
            warnings.append("Level has no id")
        if not isinstance(level.get("steps"), list) or not level["steps"]:
            warnings.append(f"{level.get('id', 'unknown')}: missing steps")
        for i, step in enumerate(level.get("steps", [])):
            if step.get("type") == "word" and not step.get("key"):
                warnings.append(f"{level.get('id')} step {i}: missing word key")
    if warnings:
        print(f"\n--- {language} level warnings ---")
        for warning in warnings:
            print(" ", warning)
        print(f"{len(warnings)} warning(s).")
    else:
        print(f"{LANGUAGES[language]} levels OK.")

# ============================================================
# PROGRESS STORAGE
# ============================================================
def progress_path():
    """
    Temporary local user.
    Authentication will later provide the user ID.
    """
    return (
        DATA_DIR / "progress" /
        "local-user" /
        f"{current_language()}.json"
    )
def default_progress():
    levels = get_levels()["levels"]
    return {
        "level_id": (
            levels[0]["id"]
            if levels else None
        ),
        "step_index": 0,
        "words": {},
        "vocabulary_words": {},
        "sentences": {},
        "games": {},
        "completed_levels": [],
        "study": {
            "daily_goal_minutes": 120,
            "total_seconds": 0,
            "days": {}
        }
    }
def get_progress():
    p = load_json(
        progress_path(),
        default_progress()
    )
    defaults = default_progress()
    for key, value in defaults.items():
        if key not in p:
            p[key] = value
    for key, value in defaults["study"].items():
        p["study"].setdefault(key, value)
    return p
def save_progress(p):
    """
    Atomically replace the language's progress file.
    """
    path = progress_path()
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )
    temp_path = path.with_suffix(".json.tmp")
    with progress_lock:
        with temp_path.open(
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                p,
                f,
                indent=2,
                ensure_ascii=False
            )
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
# ============================================================
# LEVEL HELPERS
# ============================================================
def get_level(level_id):
    for level in get_levels()["levels"]:
        if level["id"] == level_id:
            return level
    return None
def get_level_index(level_id):
    for i, level in enumerate(
        get_levels()["levels"]
    ):
        if level["id"] == level_id:
            return i
    return -1
def is_level_unlocked(
    level_id,
    completed_levels
):
    i = get_level_index(level_id)
    if i < 0:
        return False
    if i == 0:
        return True
    previous_id = get_levels()[
        "levels"
    ][i - 1]["id"]
    return previous_id in completed_levels
def level_status(
    level_id,
    completed_levels
):
    if level_id in completed_levels:
        return "completed"
    if is_level_unlocked(
        level_id,
        completed_levels
    ):
        return "unlocked"
    return "locked"
def find_first_step_for_word(
    word_key,
    level_id
):
    level = get_level(level_id)
    if not level:
        return None
    first_preview = None
    first_word_step = None
    for i, step in enumerate(level["steps"]):
        if (
            step["type"] == "preview"
            and word_key in step.get("words", [])
        ):
            if first_preview is None:
                first_preview = i
        if (
            step["type"] == "word"
            and step.get("key") == word_key
        ):
            if first_word_step is None:
                first_word_step = i
    if first_preview is not None:
        return first_preview
    return first_word_step
def pick_drill_words(
    progress,
    n=14,
    must_include=None
):
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
    return (
        list(must_include)
        + [
            key for _, key in rows[
                :max(0, n - len(must_include))
            ]
        ]
    )
# ============================================================
# HOME AND MENU
# ============================================================
@app.route("/")
def home():
    return redirect(url_for("menu"))
@app.route("/menu")
def menu():
    p = get_progress()
    completed = p.get(
        "completed_levels", []
    )
    current_id = p["level_id"]
    levels_view = []
    levels = get_levels()["levels"]
    for i, level in enumerate(levels):
        status = level_status(
            level["id"],
            completed
        )
        if (
            level["id"] == current_id
            and status != "completed"
        ):
            progress_info = (
                f"Step {p['step_index'] + 1} "
                f"of {len(level['steps'])}"
            )
        elif status == "completed":
            progress_info = "Completed"
        elif status == "locked":
            previous = levels[i - 1]
            progress_info = (
                f'Complete "{previous["title"]}" '
                f"to unlock"
            )
        else:
            progress_info = ""
        levels_view.append({
            "id": level["id"],
            "title": level["title"],
            "description": level["description"],
            "status": status,
            "progress_info": progress_info,
            "is_current": (
                level["id"] == current_id
            )
        })
    today = date.today().isoformat()
    study = p["study"]
    return render_template(
        "menu.html",
        levels=levels_view,
        study=study,
        today_seconds=study["days"].get(
            today, 0
        )
    )
# ============================================================
# LESSON VIEW
# ============================================================
@app.route("/level/<level_id>")
def level_view(level_id):
    level = get_level(level_id)
    if not level:
        return "Level not found", 404
    p = get_progress()
    completed = p.get(
        "completed_levels", []
    )
    if not is_level_unlocked(
        level_id,
        completed
    ):
        return redirect(url_for("menu"))
    if request.args.get("restart") == "1":
        p["level_id"] = level_id
        p["step_index"] = 0
        save_progress(p)
        return redirect(
            url_for(
                "level_view",
                level_id=level_id
            )
        )
    if p["level_id"] != level_id:
        p["level_id"] = level_id
        p["step_index"] = 0
        save_progress(p)
    steps = level["steps"]
    idx = min(
        p["step_index"],
        len(steps) - 1
    )
    step = dict(steps[idx])
    if step.get("type") == "drill":
        step["words"] = pick_drill_words(
            p,
            n=14,
            must_include=step.get(
                "must_include"
            )
        )
    if (
        step.get("type") == "win"
        and level_id not in completed
    ):
        p["completed_levels"].append(
            level_id
        )
        save_progress(p)
    return render_template(
        "level.html",
        level=level,
        step=step,
        step_index=idx,
        total_steps=len(steps),
        vocab=get_lesson_words(level),
        progress=p
    )
# ============================================================
# ANSWER HANDLING
# ============================================================
@app.route("/answer", methods=["POST"])
def answer():
    data = request.get_json(silent=True) or {}
    word = data.get("word")
    correct = bool(
        data.get("correct", False)
    )
    advance = bool(
        data.get("advance", True)
    )
    with progress_lock:
        p = get_progress()
        p.setdefault("completed_levels", [])
        reload_client = False
        went_back = False
        if word:
            rec = p["words"].setdefault(
                word,
                {
                    "correct": 0,
                    "wrong": 0,
                    "wrong_streak": 0
                }
            )
            if correct:
                rec["correct"] += 1
                rec["wrong_streak"] = 0
            else:
                rec["wrong"] += 1
                rec["wrong_streak"] += 1
                if (
                    advance
                    and rec["wrong_streak"]
                    >= WRONG_THRESHOLD
                ):
                    first = find_first_step_for_word(
                        word,
                        p["level_id"]
                    )
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
        "went_back": went_back
    })
@app.route("/next-level")
def next_level():
    p = get_progress()
    i = get_level_index(p["level_id"])
    levels = get_levels()["levels"]
    if i < 0 or i + 1 >= len(levels):
        return redirect(url_for("menu"))
    next_id = levels[i + 1]["id"]
    p["level_id"] = next_id
    p["step_index"] = 0
    save_progress(p)
    return redirect(
        url_for(
            "level_view",
            level_id=next_id
        )
    )
# ============================================================
# COLOR MEMORY GAME
# ============================================================
@app.route("/games/colors")
def colors_page():
    colors = get_colors()["colors"]
    return render_template(
        "games/color-game.html",
        colors=colors
    )
def color_translation(color):
    language = current_language()
    return str(
        color.get(
            language,
            color.get(
                "answer",
                color.get("tagalog", "")
                if language == "tl"
                else ""
            )
        )
    )
@app.route(
    "/games/colors/answer",
    methods=["POST"]
)
def colors_answer():
    data = request.get_json(silent=True) or {}
    color_id = data.get("color_id")
    user_answer = data.get("answer", "")
    colors = get_colors()["colors"]
    color = next(
        (
            c for c in colors
            if c["id"] == color_id
        ),
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
    expected_text = color_translation(color)
    if not expected_text:
        return jsonify({
            "ok": False,
            "error": "Translation unavailable"
        }), 404
    expected = expected_text.strip().casefold()
    received = user_answer.strip().casefold()
    correct = (
        received != ""
        and received == expected
    )
    with progress_lock:
        p = get_progress()
        games = p.setdefault("games", {})
        colors_progress = games.setdefault(
            "colors", {}
        )
        stats = colors_progress.setdefault(
            color_id,
            {
                "correct": 0,
                "wrong": 0,
                "wrong_streak": 0
            }
        )
        if correct:
            stats["correct"] += 1
            stats["wrong_streak"] = 0
        else:
            stats["wrong"] += 1
            stats["wrong_streak"] += 1
        save_progress(p)
        mastered = sum(
            colors_progress.get(
                c["id"], {}
            ).get("correct", 0) >= 3
            for c in colors
        )
    return jsonify({
        "ok": True,
        "correct": correct,
        "answer": expected_text,
        "stats": stats,
        "mastered": mastered,
        "total": len(colors)
    })
@app.route(
    "/games/colors/reset",
    methods=["POST"]
)
def colors_reset():
    with progress_lock:
        p = get_progress()
        p.setdefault(
            "games", {}
        )["colors"] = {}
        save_progress(p)
    return jsonify({
        "ok": True,
        "mastered": 0,
        "total": len(
            get_colors()["colors"]
        )
    })
# ============================================================
# VOCABULARY GAME HELPERS
# ============================================================
def game_vocabulary():
    """Vocabulary games use only the independent vocabulary dictionary."""
    p = get_progress()
    progress_words = p.get("vocabulary_words", {})
    vocabulary_words = get_vocabulary().get("words", {})
    game_words = []
    for word, vocab in vocabulary_words.items():
        if not isinstance(vocab, dict):
            continue
        english = vocab.get("english")
        if not english:
            continue
        stats = progress_words.get(word, {})
        correct = stats.get("correct", 0)
        wrong = stats.get("wrong", 0)
        attempts = correct + wrong
        game_words.append({
            "answer": word,
            "english": english,
            "correct": correct,
            "wrong": wrong,
            "wrong_streak": stats.get("wrong_streak", 0),
            "accuracy": correct / attempts if attempts else 0,
        })
    game_words.sort(key=lambda item: (item["accuracy"], -item["wrong"]))
    return game_words[:30]

# ============================================================
# WORD SHOOTER
# ============================================================
@app.route("/word-shooter")
def word_shooter():
    return render_template(
        "word-shooter.html",
        game_words=game_vocabulary()
    )
@app.route(
    "/word-shooter-answer",
    methods=["POST"]
)
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
    if word not in get_vocabulary()["words"]:
        return jsonify({
            "ok": False,
            "error": "Unknown word"
        }), 400
    with progress_lock:
        p = get_progress()
        stats = p.setdefault("vocabulary_words", {}).setdefault(
            word,
            {
                "correct": 0,
                "wrong": 0,
                "wrong_streak": 0
            }
        )
        if correct:
            stats["correct"] += 1
            stats["wrong_streak"] = 0
        else:
            stats["wrong"] += 1
            stats["wrong_streak"] += 1
        save_progress(p)
    return jsonify({
        "ok": True,
        "word": word,
        "correct": stats["correct"],
        "wrong": stats["wrong"],
        "wrong_streak": stats["wrong_streak"]
    })
# ============================================================
# WORD SNAKE
# ============================================================
@app.route("/word-snake")
def word_snake():
    return render_template(
        "word-snake.html",
        game_words=game_vocabulary()
    )
# ============================================================
# RESTAURANT GAME
# ============================================================
@app.route("/restaurant")
def restaurant_game():
    return render_template(
        "games/restaurant/restaurant-game.html"
    )
# ============================================================
# SENTENCE PRACTICE
# ============================================================
def normalize_sentence(text):
    if not isinstance(text, str):
        return ""
    text = text.strip().lower()
    for char in ".,!?;:\"'“”‘’":
        text = text.replace(char, "")
    return " ".join(text.split())
def sentence_translation(sentence):
    language = current_language()
    return str(
        sentence.get(
            language,
            sentence.get(
                "answer",
                sentence.get("tagalog", "")
                if language == "tl"
                else ""
            )
        )
    )
def sentence_is_mastered(stats):
    return stats.get("correct", 0) >= 1
def get_sentence_mastery(progress):
    sentence_progress = progress.get(
        "sentences", {}
    )
    mastered = 0
    for sentence in get_sentences().get(
        "sentences", []
    ):
        stats = sentence_progress.get(
            sentence.get("id"), {}
        )
        if sentence_is_mastered(stats):
            mastered += 1
    return mastered
def find_sentence(sentence_id):
    for sentence in get_sentences().get(
        "sentences", []
    ):
        if sentence.get("id") == sentence_id:
            return sentence
    return None
@app.route("/sentences")
def sentence_practice():
    return render_template(
        "games/sentence-practice/"
        "sentence-practice.html"
    )
@app.route("/sentence-next")
def sentence_next():
    with progress_lock:
        p = get_progress()
        p.setdefault("sentences", {})
        sentences = get_sentences().get(
            "sentences", []
        )
        total = len(sentences)
        if total == 0:
            return jsonify({
                "ok": False,
                "complete": True,
                "mastered": 0,
                "total": 0
            })
        mastered = get_sentence_mastery(p)
        candidates = []
        for index, sentence in enumerate(
            sentences
        ):
            sentence_id = sentence.get("id")
            stats = p["sentences"].get(
                sentence_id,
                {
                    "correct": 0,
                    "wrong": 0,
                    "wrong_streak": 0
                }
            )
            if sentence_is_mastered(stats):
                continue
            correct = stats.get("correct", 0)
            wrong = stats.get("wrong", 0)
            attempts = correct + wrong
            score = (
                -1000 + index
                if attempts == 0
                else (wrong * 2) - correct
            )
            candidates.append({
                "sentence": sentence,
                "stats": stats,
                "score": score,
                "index": index
            })
        if not candidates:
            return jsonify({
                "ok": True,
                "complete": True,
                "mastered": mastered,
                "total": total
            })
        unseen = [
            item for item in candidates
            if (
                item["stats"].get("correct", 0)
                + item["stats"].get("wrong", 0)
            ) == 0
        ]
        if unseen:
            chosen = unseen[0]
        else:
            candidates.sort(
                key=lambda item: item["score"],
                reverse=True
            )
            chosen = candidates[0]
        sentence = chosen["sentence"]
        translated = sentence_translation(
            sentence
        )
        return jsonify({
            "ok": True,
            "complete": False,
            "sentence": {
                "id": sentence.get("id"),
                "english": sentence.get(
                    "english", ""
                ),
                # Preserve the existing frontend key.
                "tagalog": translated,
                "answer": translated,
                "image": sentence.get(
                    "image", ""
                ),
                "number": chosen["index"] + 1
            },
            "mastered": mastered,
            "total": total
        })
@app.route(
    "/sentence-answer",
    methods=["POST"]
)
def sentence_answer():
    data = request.get_json(silent=True) or {}
    sentence_id = data.get("sentence_id")
    user_answer = data.get("answer", "")
    if not sentence_id:
        return jsonify({
            "ok": False,
            "error": "Missing sentence_id"
        }), 400
    sentence = find_sentence(sentence_id)
    if not sentence:
        return jsonify({
            "ok": False,
            "error": "Sentence not found"
        }), 404
    translated = sentence_translation(sentence)
    if not translated:
        return jsonify({
            "ok": False,
            "error": "Translation unavailable"
        }), 404
    expected = normalize_sentence(translated)
    received = normalize_sentence(user_answer)
    correct = (
        received != ""
        and received == expected
    )
    with progress_lock:
        p = get_progress()
        p.setdefault("sentences", {})
        stats = p["sentences"].setdefault(
            sentence_id,
            {
                "correct": 0,
                "wrong": 0,
                "wrong_streak": 0
            }
        )
        if correct:
            stats["correct"] += 1
            stats["wrong_streak"] = 0
        else:
            stats["wrong"] += 1
            stats["wrong_streak"] += 1
        save_progress(p)
        mastered = get_sentence_mastery(p)
        total = len(
            get_sentences().get(
                "sentences", []
            )
        )
    return jsonify({
        "ok": True,
        "correct": correct,
        "answer": translated,
        "stats": {
            "correct": stats["correct"],
            "wrong": stats["wrong"],
            "wrong_streak": stats["wrong_streak"]
        },
        "sentence_mastered": (
            sentence_is_mastered(stats)
        ),
        "mastered": mastered,
        "total": total
    })
@app.route(
    "/sentence-reset",
    methods=["POST"]
)
def sentence_reset():
    with progress_lock:
        p = get_progress()
        p["sentences"] = {}
        save_progress(p)
    return jsonify({
        "ok": True,
        "mastered": 0,
        "total": len(
            get_sentences().get(
                "sentences", []
            )
        )
    })
# ============================================================
# STUDY TIMER
# ============================================================
@app.route("/study-time", methods=["GET"])
def study_time():
    with progress_lock:
        p = get_progress()
        study = p["study"]
        today = date.today().isoformat()
        today_seconds = study[
            "days"
        ].get(today, 0)
        goal_seconds = (
            study["daily_goal_minutes"] * 60
        )
    return jsonify({
        "today_seconds": today_seconds,
        "total_seconds": study["total_seconds"],
        "daily_goal_minutes": (
            study["daily_goal_minutes"]
        ),
        "goal_met": (
            today_seconds >= goal_seconds
        )
    })
@app.route("/study-time", methods=["POST"])
def save_study_time():
    data = request.get_json(silent=True) or {}
    try:
        seconds = int(data.get("seconds", 0))
    except (TypeError, ValueError):
        seconds = 0
    seconds = max(0, min(seconds, 60))
    with progress_lock:
        p = get_progress()
        today = date.today().isoformat()
        study = p["study"]
        study["days"][today] = (
            study["days"].get(today, 0)
            + seconds
        )
        study["total_seconds"] += seconds
        save_progress(p)
        today_seconds = study["days"][today]
        total_seconds = study["total_seconds"]
    return jsonify({
        "ok": True,
        "today_seconds": today_seconds,
        "total_seconds": total_seconds
    })
@app.route("/study-goal", methods=["POST"])
def study_goal():
    data = request.get_json(silent=True) or {}
    try:
        minutes = int(
            data.get("minutes", 120)
        )
    except (TypeError, ValueError):
        minutes = 120
    minutes = max(5, min(minutes, 480))
    with progress_lock:
        p = get_progress()
        p["study"][
            "daily_goal_minutes"
        ] = minutes
        save_progress(p)
    return jsonify({
        "ok": True,
        "daily_goal_minutes": minutes
    })
# ============================================================
# RESET LESSON PROGRESS
# ============================================================
@app.route("/reset")
def reset():
    p = get_progress()
    study = p["study"]
    sentences = p.get("sentences", {})
    fresh = default_progress()
    fresh["study"] = study
    fresh["sentences"] = sentences
    fresh["vocabulary_words"] = p.get("vocabulary_words", {})
    # Preserve existing game progress.
    fresh["games"] = p.get("games", {})
    save_progress(fresh)
    return redirect(url_for("menu"))
# ============================================================
# WORD RAIN GAME
# ============================================================
def word_rain_normalize(value):
    value = unicodedata.normalize(
        "NFKC",
        str(value or "")
    )
    return " ".join(
        value.strip().lower()
        .rstrip(".!?").split()
    )
def word_rain_translations(english):
    if isinstance(english, list):
        parts = english
    else:
        parts = re.split(
            r"[/;,]",
            str(english or "")
        )
    return {
        word_rain_normalize(part)
        for part in parts
        if word_rain_normalize(part)
    }
def word_rain_vocabulary():
    result = []
    for word, details in get_vocabulary().get(
        "words", {}
    ).items():
        if not isinstance(details, dict):
            continue
        english = details.get("english")
        if not english or not word:
            continue
        result.append({
            "id": word,
            # Preserve frontend compatibility.
            "tagalog": word,
            "english": english
        })
    return result
def word_rain_required(level):
    return 10 + (level - 1) * 5
def word_rain_start_index(level):
    n = level - 1
    return n * (
        20 + (n - 1) * 5
    ) // 2
def word_rain_level_words(
    vocabulary,
    level
):
    start = word_rain_start_index(level)
    end = start + word_rain_required(level)
    return vocabulary[start:end]
def word_rain_store(progress):
    games = progress.setdefault("games", {})
    return games.setdefault(
        "word_rain",
        {
            "words": {},
            "highest_unlocked_level": 1,
            "best_score": 0
        }
    )
def word_rain_level_mastered(
    store,
    vocabulary,
    level
):
    level_words = word_rain_level_words(
        vocabulary,
        level
    )
    if (
        len(level_words)
        < word_rain_required(level)
    ):
        return False
    saved_words = store.get("words", {})
    return all(
        saved_words.get(
            word["id"], {}
        ).get("correct", 0)
        >= WORD_RAIN_MASTERY
        for word in level_words
    )
def word_rain_unlock_levels(
    store,
    vocabulary
):
    level = 1
    while word_rain_level_mastered(
        store,
        vocabulary,
        level
    ):
        next_level = level + 1
        if (
            len(
                word_rain_level_words(
                    vocabulary,
                    next_level
                )
            )
            < word_rain_required(next_level)
        ):
            break
        level = next_level
    store["highest_unlocked_level"] = level
    return level
@app.route("/games/word-rain")
def word_rain_game():
    vocabulary = word_rain_vocabulary()
    with progress_lock:
        progress = get_progress()
        store = word_rain_store(progress)
        level = word_rain_unlock_levels(
            store,
            vocabulary
        )
        save_progress(progress)
        saved_words = dict(
            store.get("words", {})
        )
    return render_template(
        "games/word-rain.html",
        words=vocabulary,
        level=level,
        word_progress=saved_words
    )
@app.route(
    "/games/word-rain/answer",
    methods=["POST"]
)
def word_rain_answer():
    data = request.get_json(silent=True) or {}
    word_id = str(
        data.get("word_id", "")
    )
    answer = word_rain_normalize(
        data.get("answer", "")
    )
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
    if (
        (not missed and not answer)
        or len(answer)
        > WORD_RAIN_MAX_ANSWER_LENGTH
    ):
        return jsonify(
            ok=False,
            error="Invalid translation"
        ), 400
    vocabulary = word_rain_vocabulary()
    level_words = word_rain_level_words(
        vocabulary,
        level
    )
    word = next(
        (
            item for item in level_words
            if item["id"] == word_id
        ),
        None
    )
    if word is None:
        return jsonify(
            ok=False,
            error=(
                "Word does not belong "
                "to this level"
            )
        ), 400
    correct = (
        not missed
        and answer in word_rain_translations(
            word["english"]
        )
    )
    with progress_lock:
        progress = get_progress()
        store = word_rain_store(progress)
        unlocked = word_rain_unlock_levels(
            store,
            vocabulary
        )
        if level > unlocked:
            return jsonify(
                ok=False,
                error="Level is locked"
            ), 403
        saved_words = store.setdefault(
            "words", {}
        )
        stats = saved_words.setdefault(
            word_id,
            {
                "correct": 0,
                "wrong": 0,
                "wrong_streak": 0
            }
        )
        if correct:
            if (
                stats["correct"]
                < WORD_RAIN_MASTERY
            ):
                stats["correct"] += 1
            stats["wrong_streak"] = 0
        else:
            stats["wrong"] += 1
            stats["wrong_streak"] += 1
        mastered = (
            stats["correct"]
            >= WORD_RAIN_MASTERY
        )
        level_complete = (
            word_rain_level_mastered(
                store,
                vocabulary,
                level
            )
        )
        unlocked = word_rain_unlock_levels(
            store,
            vocabulary
        )
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
@app.route(
    "/games/word-rain/reset",
    methods=["POST"]
)
def word_rain_reset():
    with progress_lock:
        progress = get_progress()
        games = progress.setdefault(
            "games", {}
        )
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
# ============================================================
# START APPLICATION
# ============================================================
if __name__ == "__main__":
    for language in LANGUAGES:
        try:
            validate_levels(language)
        except FileNotFoundError as exc:
            print(f"Warning: {exc}")
    app.run(debug=True)
