import json
import os
from pathlib import Path
import langcodes
import threading
import unicodedata
from datetime import date
from flask import (
    Flask, render_template, request,
    redirect, url_for, jsonify, g, current_app
)
from progress_store import JsonProgressStore
from vocabulary_entries import vocabulary_entry
from diagnostics import init_diagnostics, install_process_hooks
app = Flask(__name__)
init_diagnostics(app)
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
app.config["PROGRESS_STORE"] = JsonProgressStore(DATA_DIR / "progress")
app.config["LEARNER_ID_RESOLVER"] = lambda: "local-user"
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
                "english": definitions.get(key, ""),
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
        entry = vocabulary_entry(translated)
        if not (concept_id and english and entry):
            continue
        word = entry["translation"]
        vocabulary["words"][word] = {
            "english": english,
            "image": concept.get("image", ""),
            **entry,
        }
    # 4. Normalize vocabulary for the existing templates.
    vocabulary = normalize_vocabulary(vocabulary)
    language_cache[key] = vocabulary
    return vocabulary


def get_lesson_words(level):
    """Word-card data from one level's expanded teaching steps."""
    words = {}
    for step in level.get("steps", []):
        if step.get("type") != "word":
            continue
        key = step.get("key")
        if not key:
            continue
        english = step.get("english") or step.get("definition", "")
        if key not in words or (not words[key]["english"] and english):
            words[key] = {
                "english": english,
                "image": "",
                "phrase": step.get("phrase", ""),
                "translation": step.get("translation", ""),
            }
    return words


def get_all_lesson_words():
    """English definitions from ALL levels in the selected language.

    Used by lesson word cards and drills; independent vocabulary games
    continue using their separate concept-based vocabulary data.
    """
    words = {}
    for level in get_levels()["levels"]:
        for key, details in get_lesson_words(level).items():
            if key not in words or (not words[key]["english"] and details["english"]):
                words[key] = details
    return words


def get_levels():
    if not hasattr(g, "language_data"):
        g.language_data = load_language_data(
            current_language()
        )
    return g.language_data["levels"]
def get_vocabulary():
    return load_vocabulary_data(current_language())

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
def default_progress():
    levels = get_levels()["levels"]
    return {
        "schema_version": 2,
        "course": {},
        "daily_dose": {"number": 0, "word_ids": [], "completed": False},
        "mastery": {},
        "level_id": (
            levels[0]["id"]
            if levels else None
        ),
        "step_index": 0,
        "words": {},
        "vocabulary_words": {},
        "games": {},
        "completed_levels": [],
        "study": {
            "daily_goal_minutes": 120,
            "total_seconds": 0,
            "days": {}
        }
    }
def get_progress():
    p = current_app.config["PROGRESS_STORE"].load(
        current_app.config["LEARNER_ID_RESOLVER"](), current_language(), default_progress()
    )
    defaults = default_progress()
    for key, value in defaults.items():
        if key not in p:
            p[key] = value
    for key, value in defaults["study"].items():
        p["study"].setdefault(key, value)
    return p
def save_progress(p):
    with progress_lock:
        current_app.config["PROGRESS_STORE"].save(
            current_app.config["LEARNER_ID_RESOLVER"](), current_language(), p
        )

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
    return get_progress().get("course", {}).get(previous_id, {}).get("passed", False)
def level_status(
    level_id,
    completed_levels
):
    if get_progress().get("course", {}).get(level_id, {}).get("passed", False):
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
            progress_info = "Start lesson"
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
    for card in levels_view:
        state = p.get("course", {}).get(card["id"], {})
        if card["status"] != "locked":
            card["progress_info"] = ("Final test passed" if state.get("passed") else
                                     "Continue vocabulary / test" if state.get("lesson_done") else
                                     "Start / continue lesson")
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
    if step.get("type") == "win":
        record = p.setdefault("course", {}).setdefault(level_id, {})
        record["lesson_done"] = True
        save_progress(p)
        return redirect(url_for("course.overview", level_id=level_id))
    return render_template(
        "level.html",
        level=level,
        step=step,
        step_index=idx,
        total_steps=len(steps),
        vocab=get_all_lesson_words(),
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
    if not p.get("course", {}).get(p["level_id"], {}).get("passed", False):
        return redirect(url_for("course.overview", level_id=p["level_id"]))
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
# DAILY DOSE — 10 WORDS PER LEVEL, 3 CONSECUTIVE RECALLS
# ============================================================


def dose_catalog():
    """Read concepts in source order, with translations for this language."""
    raw = load_json(DATA_DIR / "concepts.json", {})
    translations = load_json(
        DATA_DIR / "languages" / "vocabulary" / f"{current_language()}.json", {}
    )
    if isinstance(raw, dict):
        raw = raw.get("concepts", raw)
    if isinstance(translations, dict):
        translations = translations.get("translations", translations)
    if not isinstance(translations, dict):
        return {}
    if isinstance(raw, dict):
        items = [dict(details, id=cid) for cid, details in raw.items()
                 if isinstance(details, dict)]
    elif isinstance(raw, list):
        items = raw
    else:
        items = []

    catalog = {}
    folder = app.config.get("VOCABULARY_IMAGE_FOLDER", "images/vocabulary")
    for item in items:
        if not isinstance(item, dict):
            continue
        cid = item.get("id")
        english = item.get("label") or item.get("english")
        translated = translations.get(cid) if isinstance(cid, str) else None
        entry = vocabulary_entry(translated)
        if not (cid and english and entry):
            continue
        image = str(item.get("image") or "").strip()
        catalog[cid] = {
            "id": cid,
            "english": str(english),
            "tagalog": entry["translation"],
            **entry,
            "image_url": url_for("static", filename=f"{folder}/{image}") if image else "",
        }
    return catalog


def dose_normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


@app.route("/daily-dose")
def daily_dose_page():
    return redirect(url_for("course.overview", level_id=get_progress()["level_id"]))


@app.route("/daily-dose/answer", methods=["POST"])
def daily_dose_answer():
    return jsonify(ok=False, error="Use the level Daily Dose activity"), 410

# ============================================================
# VOCABULARY GAME HELPERS
# ============================================================

# ============================================================
# WORD SHOOTER
# ============================================================
# ============================================================
# WORD SHOOTER — SHARED 10-WORD LEVELS, INDEPENDENT PROGRESS
# ============================================================


@app.route("/word-shooter")
def word_shooter():
    return redirect(url_for("course.shooter", level_id=get_progress()["level_id"]))


@app.route("/word-shooter-answer", methods=["POST"])
def word_shooter_answer():
    return jsonify(ok=False, error="Use the level practice activity"), 410
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
    fresh = default_progress()
    fresh["course"] = p.get("course", {})
    fresh["study"] = study
    fresh["daily_dose"] = p.get("daily_dose", {})
    fresh["mastery"] = p.get("mastery", {})
    fresh["vocabulary_words"] = p.get("vocabulary_words", {})
    # Preserve existing game progress.
    fresh["games"] = p.get("games", {})
    save_progress(fresh)
    return redirect(url_for("menu"))

@app.route("/despacio")
def despacio_home():
    return render_template("despacio_home.html")

# ============================================================
# START APPLICATION
# ============================================================
from course import register_course
register_course(app, globals())
from word_match import register_word_match
register_word_match(app, globals())
if __name__ == "__main__":
    install_process_hooks(app)
    for language in LANGUAGES:
        try:
            validate_levels(language)
        except FileNotFoundError as exc:
            print(f"Warning: {exc}")
    app.logger.info("application_starting")
    app.run(debug=os.environ.get("APP_DEBUG", "0") == "1")
