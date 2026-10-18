import json
from pathlib import Path
import langcodes
import os
import re
import threading
import unicodedata
from datetime import date
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
        "daily_dose": {"number": 0, "word_ids": [], "completed": False},
        "mastery": {},
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
def synchronize_game_mastery(progress):
    """Unify mastered concept IDs across all four vocabulary games.

    Existing correct/wrong counts stay game-specific. Mastery is shared.
    Legacy Word Rain word keys are migrated before merging.
    """
    catalog = dose_catalog()
    rain = word_rain_store(progress)
    changed = word_rain_migrate_progress(rain, catalog)
    games = progress.setdefault("games", {})
    stores = [
        progress.setdefault("mastery", {}),
        rain.setdefault("words", {}),
        games.setdefault("word_shooter", {}).setdefault("words", {}),
        games.setdefault("word_snake", {}).setdefault("words", {}),
    ]

    for cid in catalog:
        mastered = any(
            bool(store.get(cid, {}).get("mastered", False))
            for store in stores
        ) or word_rain_is_mastered(rain, cid)
        if not mastered:
            continue
        for store in stores:
            stats = store.setdefault(cid, {})
            if not stats.get("mastered", False):
                stats["mastered"] = True
                changed = True
            if stats.get("recall_streak", 0) < 3:
                stats["recall_streak"] = 3
                changed = True
    return changed


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
    if synchronize_game_mastery(p):
        save_progress(p)
    return p
def save_progress(p):
    """
    Atomically replace the language's progress file.
    """
    synchronize_game_mastery(p)
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
# DAILY DOSE — 10 WORDS PER LEVEL, 3 CONSECUTIVE RECALLS
# ============================================================
DAILY_DOSE_SIZE = 10
DAILY_DOSE_RECALL_TARGET = 3


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
        if not (cid and english and isinstance(translated, str) and translated.strip()):
            continue
        image = str(item.get("image") or "").strip()
        catalog[cid] = {
            "id": cid,
            "english": str(english),
            "tagalog": translated.strip(),
            "image_url": url_for("static", filename=f"{folder}/{image}") if image else "",
        }
    return catalog


def dose_stats(progress, concept_id):
    stats = progress.setdefault("mastery", {}).setdefault(concept_id, {})
    for field in ("correct", "wrong", "recall_correct", "recall_wrong", "recall_streak"):
        stats.setdefault(field, 0)
    stats.setdefault("mastered", False)
    return stats


def dose_is_mastered(progress, concept_id):
    return bool(progress.get("mastery", {}).get(concept_id, {}).get("mastered", False))


def dose_levels(catalog):
    words = list(catalog.values())
    return [
        {"number": i // DAILY_DOSE_SIZE + 1,
         "id": f"dose-level-{i // DAILY_DOSE_SIZE + 1}",
         "words": words[i:i + DAILY_DOSE_SIZE]}
        for i in range(0, len(words), DAILY_DOSE_SIZE)
    ]


def dose_level_complete(progress, level):
    return bool(level["words"]) and all(
        dose_is_mastered(progress, word["id"]) for word in level["words"]
    )


def dose_dashboard(progress, catalog):
    levels = dose_levels(catalog)
    cards = []
    previous_complete = True
    current_level = None
    for level in levels:
        total = len(level["words"])
        mastered = sum(dose_is_mastered(progress, word["id"]) for word in level["words"])
        complete = mastered == total
        unlocked = previous_complete
        if unlocked and not complete and current_level is None:
            current_level = level["number"]
        cards.append({
            "number": level["number"], "id": level["id"],
            "total": total, "mastered": mastered,
            "complete": complete, "unlocked": unlocked,
            "status": "completed" if complete else ("unlocked" if unlocked else "locked"),
            "percent": round(mastered * 100 / total) if total else 0,
        })
        previous_complete = complete
    total_words = len(catalog)
    total_mastered = sum(dose_is_mastered(progress, cid) for cid in catalog)
    return {
        "total_words": total_words, "total_levels": len(levels),
        "mastered_words": total_mastered,
        "learning_words": total_words - total_mastered,
        "completed_levels": sum(card["complete"] for card in cards),
        "current_level": current_level if current_level is not None else len(levels),
        "overall_percent": round(total_mastered * 100 / total_words) if total_words else 0,
        "levels": cards,
    }


def dose_normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def dose_apply_result(stats, correct, activity="picture_recall"):
    """Games may record recognition, but only typed recall earns mastery."""
    if correct:
        stats["correct"] = stats.get("correct", 0) + 1
    else:
        stats["wrong"] = stats.get("wrong", 0) + 1
    if activity != "picture_recall":
        return
    if correct:
        stats["recall_correct"] = stats.get("recall_correct", 0) + 1
        if not stats.get("mastered", False):
            stats["recall_streak"] = stats.get("recall_streak", 0) + 1
            if stats["recall_streak"] >= DAILY_DOSE_RECALL_TARGET:
                stats["recall_streak"] = DAILY_DOSE_RECALL_TARGET
                stats["mastered"] = True
    else:
        stats["recall_wrong"] = stats.get("recall_wrong", 0) + 1
        if not stats.get("mastered", False):
            stats["recall_streak"] = 0


@app.route("/daily-dose")
def daily_dose_page():
    catalog = dose_catalog()
    with progress_lock:
        progress = get_progress()
        dashboard = dose_dashboard(progress, catalog)
        requested = request.args.get("level", type=int)
        levels = dose_levels(catalog)
        selected_words = []
        if requested is not None:
            if not 1 <= requested <= len(levels):
                return redirect(url_for("daily_dose_page"))
            if not dashboard["levels"][requested - 1]["unlocked"]:
                return redirect(url_for("daily_dose_page"))
            selected_words = levels[requested - 1]["words"]
        config = {
            "dashboard": dashboard,
            "level": requested,
            "words": selected_words,
            "progress": {
                word["id"]: dict(progress.get("mastery", {}).get(word["id"], {}))
                for word in selected_words
            },
            "settings": {"masteryCorrect": DAILY_DOSE_RECALL_TARGET},
            "urls": {
                "answer": url_for("daily_dose_answer"),
                "dashboard": url_for("daily_dose_page"),
                "menu": url_for("menu"),
            },
        }
    return render_template("daily-dose.html", daily_dose_config=config)


@app.route("/daily-dose/answer", methods=["POST"])
def daily_dose_answer():
    data = request.get_json(silent=True) or {}
    cid, answer, number = data.get("word_id"), data.get("answer"), data.get("level")
    if not (isinstance(cid, str) and isinstance(answer, str)
            and 0 < len(answer) <= 120 and type(number) is int):
        return jsonify(ok=False, error="Invalid answer or level"), 400
    catalog = dose_catalog()
    levels = dose_levels(catalog)
    if not 1 <= number <= len(levels):
        return jsonify(ok=False, error="Invalid level"), 400
    level = levels[number - 1]
    if cid not in {word["id"] for word in level["words"]}:
        return jsonify(ok=False, error="Word does not belong to this level"), 400
    expected = catalog[cid]["tagalog"]
    received = dose_normalize(answer)
    correct = bool(received) and received == dose_normalize(expected)
    with progress_lock:
        progress = get_progress()
        if not dose_dashboard(progress, catalog)["levels"][number - 1]["unlocked"]:
            return jsonify(ok=False, error="Level is locked"), 403
        stats = dose_stats(progress, cid)
        dose_apply_result(stats, correct)
        level_complete = dose_level_complete(progress, level)
        dashboard = dose_dashboard(progress, catalog)
        save_progress(progress)
        saved = dict(stats)
    return jsonify({
        "ok": True, "correct": correct, "answer": expected,
        "stats": saved, "word_mastered": saved["mastered"],
        "level_complete": level_complete, "level": number,
        "dashboard": dashboard,
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
# ============================================================
# WORD SHOOTER — SHARED 10-WORD LEVELS, INDEPENDENT PROGRESS
# ============================================================

WORD_SHOOTER_MASTERY = 3


def shooter_store(progress):
    games = progress.setdefault("games", {})
    return games.setdefault("word_shooter", {"words": {}})


def shooter_word_stats(store, concept_id):
    stats = store.setdefault("words", {}).setdefault(
        concept_id,
        {
            "correct": 0,
            "wrong": 0,
            "wrong_streak": 0,
            "recall_streak": 0,
            "mastered": False,
        },
    )
    for key in ("correct", "wrong", "wrong_streak", "recall_streak"):
        stats.setdefault(key, 0)
    stats.setdefault("mastered", False)
    return stats


def shooter_dashboard(progress, catalog):
    levels = dose_levels(catalog)
    store = shooter_store(progress)
    saved = store.get("words", {})

    cards = []
    previous_complete = True

    for level in levels:
        mastered = sum(
            bool(saved.get(word["id"], {}).get("mastered", False))
            for word in level["words"]
        )
        total = len(level["words"])
        complete = total > 0 and mastered == total

        cards.append({
            "number": level["number"],
            "total": total,
            "mastered": mastered,
            "complete": complete,
            "unlocked": previous_complete,
            "status": (
                "completed" if complete
                else "unlocked" if previous_complete
                else "locked"
            ),
        })
        previous_complete = complete

    return cards


@app.route("/word-shooter")
def word_shooter():
    catalog = dose_catalog()
    levels = dose_levels(catalog)

    with progress_lock:
        progress = get_progress()
        dashboard = shooter_dashboard(progress, catalog)
        store = shooter_store(progress)

        requested = request.args.get("level", type=int)

        if requested is None:
            selected = None
        elif not 1 <= requested <= len(levels):
            return redirect(url_for("word_shooter"))
        elif not dashboard[requested - 1]["unlocked"]:
            return redirect(url_for("word_shooter"))
        else:
            selected = requested

        words = []
        if selected is not None:
            for item in levels[selected - 1]["words"]:
                stats = store["words"].get(item["id"], {})
                words.append({
                    "id": item["id"],
                    "answer": item["tagalog"],
                    "english": item["english"],
                    "correct": stats.get("correct", 0),
                    "wrong": stats.get("wrong", 0),
                    "wrong_streak": stats.get("wrong_streak", 0),
                    "recall_streak": stats.get("recall_streak", 0),
                    "mastered": stats.get("mastered", False),
                })

    return render_template(
        "word-shooter.html",
        game_words=words,
        shooter_levels=dashboard,
        shooter_level=selected,
        shooter_mastery=WORD_SHOOTER_MASTERY,
    )


@app.route("/word-shooter-answer", methods=["POST"])
def word_shooter_answer():
    data = request.get_json(silent=True) or {}

    concept_id = data.get("word_id")
    answer = data.get("answer")
    number = data.get("level")

    if not (
        isinstance(concept_id, str)
        and isinstance(answer, str)
        and type(number) is int
        and 0 < len(answer) <= 120
    ):
        return jsonify(ok=False, error="Invalid answer or level"), 400

    catalog = dose_catalog()
    levels = dose_levels(catalog)

    if not 1 <= number <= len(levels):
        return jsonify(ok=False, error="Invalid level"), 400

    level = levels[number - 1]

    if concept_id not in {word["id"] for word in level["words"]}:
        return jsonify(
            ok=False,
            error="Word does not belong to this level",
        ), 400

    expected = catalog[concept_id]["tagalog"]
    correct = dose_normalize(answer) == dose_normalize(expected)

    with progress_lock:
        progress = get_progress()
        dashboard = shooter_dashboard(progress, catalog)

        if not dashboard[number - 1]["unlocked"]:
            return jsonify(ok=False, error="Level is locked"), 403

        store = shooter_store(progress)
        stats = shooter_word_stats(store, concept_id)

        if correct:
            stats["correct"] += 1
            stats["wrong_streak"] = 0

            if not stats["mastered"]:
                stats["recall_streak"] += 1

                if stats["recall_streak"] >= WORD_SHOOTER_MASTERY:
                    stats["recall_streak"] = WORD_SHOOTER_MASTERY
                    stats["mastered"] = True
        else:
            stats["wrong"] += 1
            stats["wrong_streak"] += 1

            if not stats["mastered"]:
                stats["recall_streak"] = 0

        dashboard = shooter_dashboard(progress, catalog)
        save_progress(progress)

        saved_stats = dict(stats)
        level_card = dict(dashboard[number - 1])

    return jsonify({
        "ok": True,
        "correct": correct,
        "answer": expected,
        "stats": saved_stats,
        "word_mastered": saved_stats["mastered"],
        "level_complete": level_card["complete"],
        "level_progress": level_card,
        "levels": dashboard,
    })

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
        # Recognition practice is recorded but cannot independently
        # qualify a word as mastered: typed recall is required.
        catalog = dose_catalog()
        for cid, item in catalog.items():
            if item["tagalog"] == word and cid in p.get("mastery", {}):
                dose_apply_result(dose_stats(p, cid), correct, "word_shooter")
                break
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

# ============================================================
# WORD SNAKE — LEVELS AND INDEPENDENT MASTERY
# ============================================================

WORD_SNAKE_MASTERY = 3


def word_snake_levels():
    # Uses the same concept ordering as Daily Dose,
    # Word Shooter, and Word Rain.
    return dose_levels(dose_catalog())


def word_snake_store(progress):
    games = progress.setdefault("games", {})
    return games.setdefault("word_snake", {"words": {}})


def word_snake_stats(store, concept_id):
    words = store.setdefault("words", {})
    stats = words.setdefault(concept_id, {})

    stats.setdefault("correct", 0)
    stats.setdefault("wrong", 0)
    stats.setdefault("recall_streak", 0)
    stats.setdefault("mastered", False)

    return stats


def word_snake_mastered(store, concept_id):
    return bool(
        store.get("words", {})
        .get(concept_id, {})
        .get("mastered", False)
    )


def word_snake_level_complete(store, level):
    return bool(level["words"]) and all(
        word_snake_mastered(store, word["id"])
        for word in level["words"]
    )


def word_snake_dashboard(store, levels, progress=None, catalog=None):
    """
    Share unlocked level access with Daily Dose, Word Shooter and Word Rain.
    Keep Word Snake mastery/completion independent.
    """
    shared_highest = 1

    if progress is not None and catalog is not None:
        dose_cards = dose_dashboard(progress, catalog)["levels"]
        shooter_cards = shooter_dashboard(progress, catalog)
        rain_store = word_rain_store(progress)
        rain_cards = word_rain_dashboard(rain_store, catalog)

        for game_cards in (dose_cards, shooter_cards, rain_cards):
            for card in game_cards:
                if card["unlocked"] or card["complete"]:
                    shared_highest = max(shared_highest, card["number"])

        # Include Word Rain's previously recorded highest level.
        shared_highest = max(
            shared_highest,
            int(rain_store.get("highest_unlocked_level", 1)),
        )

    cards = []
    previous_complete = True

    for level in levels:
        words = level["words"]
        mastered = sum(
            word_snake_mastered(store, word["id"])
            for word in words
        )
        complete = len(words) > 0 and mastered == len(words)
        unlocked = (
            level["number"] <= shared_highest
            or previous_complete
            or complete
        )

        cards.append({
            "number": level["number"],
            "total": len(words),
            "mastered": mastered,
            "complete": complete,
            "unlocked": unlocked,
        })

        previous_complete = complete

    return cards


@app.route("/word-snake")
def word_snake():
    levels = word_snake_levels()

    with progress_lock:
        progress = get_progress()
        store = word_snake_store(progress)
        cards = word_snake_dashboard(store, levels, progress, dose_catalog())

        saved = {
            cid: dict(stats)
            for cid, stats in store.get("words", {}).items()
        }

    selected = request.args.get("level", type=int)

    # No level selected: show level menu.
    if selected is None:
        return render_template(
            "word-snake.html",
            level=None,
            cards=cards,
            game_words=[],
            game_progress={},
            mastery_target=WORD_SNAKE_MASTERY,
        )

    if selected < 1 or selected > len(levels):
        return redirect(url_for("word_snake"))

    card = cards[selected - 1]

    if not card["unlocked"]:
        return redirect(url_for("word_snake"))

    chosen = levels[selected - 1]

    words = []

    for word in chosen["words"]:
        cid = word["id"]
        stats = saved.get(cid, {})

        words.append({
            "id": cid,
            "english": word["english"],
            "answer": word["tagalog"],
            "correct": stats.get("correct", 0),
            "wrong": stats.get("wrong", 0),
            "recall_streak": stats.get("recall_streak", 0),
            "mastered": bool(stats.get("mastered", False)),
        })

    return render_template(
        "word-snake.html",
        level=selected,
        cards=cards,
        game_words=words,
        game_progress=saved,
        mastery_target=WORD_SNAKE_MASTERY,
    )


@app.route("/word-snake/answer", methods=["POST"])
def word_snake_answer():
    data = request.get_json(silent=True) or {}

    level_number = data.get("level")
    concept_id = data.get("word_id")
    correct = data.get("correct")
    replay = data.get("replay") is True

    if (
        type(level_number) is not int
        or type(concept_id) is not str
        or type(correct) is not bool
    ):
        return jsonify(
            ok=False,
            error="Invalid answer data"
        ), 400

    levels = word_snake_levels()

    if not 1 <= level_number <= len(levels):
        return jsonify(
            ok=False,
            error="Invalid level"
        ), 400

    level = levels[level_number - 1]

    if not any(
        word["id"] == concept_id
        for word in level["words"]
    ):
        return jsonify(
            ok=False,
            error="Word does not belong to this level"
        ), 400

    with progress_lock:
        progress = get_progress()
        store = word_snake_store(progress)

        cards = word_snake_dashboard(store, levels, progress, dose_catalog())

        if not cards[level_number - 1]["unlocked"]:
            return jsonify(
                ok=False,
                error="Level is locked"
            ), 403

        # Replay is only permitted for completed levels.
        if replay:
            if not word_snake_level_complete(store, level):
                return jsonify(
                    ok=False,
                    error="Replay requires a completed level"
                ), 403

            return jsonify(
                ok=True,
                replay=True,
                correct=correct,
                level_complete=True,
            )

        stats = word_snake_stats(store, concept_id)

        # Completed words retain mastery permanently.
        if not stats["mastered"]:
            if correct:
                stats["correct"] += 1
                stats["recall_streak"] += 1

                if stats["recall_streak"] >= WORD_SNAKE_MASTERY:
                    stats["mastered"] = True
            else:
                stats["wrong"] += 1
                stats["recall_streak"] = 0

        level_complete = word_snake_level_complete(
            store, level
        )

        cards = word_snake_dashboard(store, levels, progress, dose_catalog())

        save_progress(progress)

        result_stats = dict(stats)

    return jsonify(
        ok=True,
        correct=correct,
        stats=result_stats,
        mastered=result_stats["mastered"],
        level_complete=level_complete,
        highest_unlocked_level=max(
            (
                card["number"]
                for card in cards
                if card["unlocked"]
            ),
            default=1,
        ),
    )

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
    fresh["daily_dose"] = p.get("daily_dose", {})
    fresh["mastery"] = p.get("mastery", {})
    fresh["sentences"] = sentences
    fresh["vocabulary_words"] = p.get("vocabulary_words", {})
    # Preserve existing game progress.
    fresh["games"] = p.get("games", {})
    save_progress(fresh)
    return redirect(url_for("menu"))

# ============================================================
# WORD RAIN — SHARED LEVELS, INDEPENDENT MASTERY
# ============================================================

WORD_RAIN_MASTERY = 3
WORD_RAIN_MAX_ANSWER_LENGTH = 120


def word_rain_normalize(value):
    """Normalize typed answers consistently."""
    value = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(
        value.strip().casefold().rstrip(".!?").split()
    )


def word_rain_translations(english):
    """Accept multiple explicitly listed English meanings."""
    if isinstance(english, list):
        parts = english
    else:
        parts = re.split(r"[/;,]", str(english or ""))

    return {
        word_rain_normalize(part)
        for part in parts
        if word_rain_normalize(part)
    }


def word_rain_store(progress):
    games = progress.setdefault("games", {})
    store = games.setdefault("word_rain", {})

    store.setdefault("words", {})
    store.setdefault("highest_unlocked_level", 1)
    store.setdefault("best_score", 0)

    return store


def word_rain_stats(store, concept_id):
    words = store.setdefault("words", {})

    stats = words.setdefault(
        concept_id,
        {
            "correct": 0,
            "wrong": 0,
            "wrong_streak": 0,
            "recall_streak": 0,
            "mastered": False,
        },
    )

    for field in (
        "correct",
        "wrong",
        "wrong_streak",
        "recall_streak",
    ):
        stats.setdefault(field, 0)

    stats.setdefault("mastered", False)

    return stats


def word_rain_migrate_progress(store, catalog):
    """
    Preserve legacy Word Rain progress.

    Older versions keyed stats by translated words.
    New versions use stable concept IDs.

    If multiple concepts share one translation,
    legacy progress cannot identify which concept
    earned it, so it is not assigned ambiguously.
    """
    saved = store.setdefault("words", {})

    translation_ids = {}

    for concept_id, item in catalog.items():
        translation_ids.setdefault(
            word_rain_normalize(item["tagalog"]), []
        ).append(concept_id)

    changed = False

    for translation, ids in translation_ids.items():
        if len(ids) != 1:
            continue

        concept_id = ids[0]

        if concept_id in saved:
            continue

        legacy_key = next(
            (
                key for key in saved
                if key != concept_id
                and word_rain_normalize(key) == translation
            ),
            None,
        )

        if legacy_key is None:
            continue

        old = saved[legacy_key]

        if not isinstance(old, dict):
            continue

        correct = max(0, int(old.get("correct", 0)))
        wrong = max(0, int(old.get("wrong", 0)))

        saved[concept_id] = {
            "correct": correct,
            "wrong": wrong,
            "wrong_streak": max(
                0, int(old.get("wrong_streak", 0))
            ),
            "recall_streak": min(
                correct, WORD_RAIN_MASTERY
            ),
            "mastered": correct >= WORD_RAIN_MASTERY,
        }

        changed = True

    return changed


def word_rain_is_mastered(store, concept_id):
    stats = store.get("words", {}).get(concept_id, {})

    return bool(
        stats.get("mastered", False)
        or stats.get("correct", 0) >= WORD_RAIN_MASTERY
    )


def word_rain_dashboard(store, catalog):
    """
    Uses exactly the same concept groups as
    Daily Dose and Word Shooter.
    """
    levels = dose_levels(catalog)
    cards = []
    previous_complete = True

    for level in levels:
        words = level["words"]
        total = len(words)

        mastered = sum(
            word_rain_is_mastered(store, word["id"])
            for word in words
        )

        complete = total > 0 and mastered == total

        # Completed levels remain replayable.
        unlocked = previous_complete or complete

        cards.append({
            "number": level["number"],
            "total": total,
            "mastered": mastered,
            "complete": complete,
            "unlocked": unlocked,
            "status": (
                "completed" if complete
                else "unlocked" if unlocked
                else "locked"
            ),
        })

        previous_complete = complete

    return cards


def word_rain_game_words(level, store):
    """Provide only the selected level's words."""
    result = []

    for item in level["words"]:
        stats = store.get("words", {}).get(item["id"], {})

        result.append({
            "id": item["id"],
            "tagalog": item["tagalog"],
            "english": item["english"],
            "correct": stats.get("correct", 0),
            "wrong": stats.get("wrong", 0),
            "recall_streak": stats.get("recall_streak", 0),
            "mastered": word_rain_is_mastered(
                store, item["id"]
            ),
        })

    return result


@app.route("/games/word-rain")
def word_rain_game():
    catalog = dose_catalog()
    levels = dose_levels(catalog)

    requested = request.args.get("level", type=int)

    with progress_lock:
        progress = get_progress()
        store = word_rain_store(progress)

        migrated = word_rain_migrate_progress(store, catalog)
        dashboard = word_rain_dashboard(store, catalog)

        if requested is None:
            selected = None
        elif not 1 <= requested <= len(levels):
            return redirect(url_for("word_rain_game"))
        elif not dashboard[requested - 1]["unlocked"]:
            return redirect(url_for("word_rain_game"))
        else:
            selected = requested

        words = []

        if selected is not None:
            words = word_rain_game_words(
                levels[selected - 1], store
            )

        if migrated:
            save_progress(progress)

    return render_template(
        "games/word-rain.html",
        words=words,
        level=selected,
        rain_levels=dashboard,
        word_progress={
            word["id"]: {
                "correct": word["correct"],
                "wrong": word["wrong"],
                "recall_streak": word["recall_streak"],
                "mastered": word["mastered"],
            }
            for word in words
        },
        rain_mastery=WORD_RAIN_MASTERY,
    )


@app.route("/games/word-rain/answer", methods=["POST"])
def word_rain_answer():
    data = request.get_json(silent=True) or {}

    concept_id = data.get("word_id")
    raw_answer = data.get("answer", "")
    number = data.get("level")
    missed = data.get("missed") is True

    if not (
        isinstance(concept_id, str)
        and type(number) is int
        and isinstance(raw_answer, str)
        and len(raw_answer) <= WORD_RAIN_MAX_ANSWER_LENGTH
    ):
        return jsonify(
            ok=False, error="Invalid answer or level"
        ), 400

    answer = word_rain_normalize(raw_answer)

    if not missed and not answer:
        return jsonify(
            ok=False, error="Translation is required"
        ), 400

    catalog = dose_catalog()
    levels = dose_levels(catalog)

    if not 1 <= number <= len(levels):
        return jsonify(
            ok=False, error="Invalid level"
        ), 400

    level = levels[number - 1]

    if concept_id not in {
        item["id"] for item in level["words"]
    }:
        return jsonify(
            ok=False,
            error="Word does not belong to this level",
        ), 400

    word = catalog[concept_id]

    correct = (
        not missed
        and answer in word_rain_translations(word["english"])
    )

    with progress_lock:
        progress = get_progress()
        store = word_rain_store(progress)

        word_rain_migrate_progress(store, catalog)

        dashboard = word_rain_dashboard(store, catalog)

        if not dashboard[number - 1]["unlocked"]:
            return jsonify(
                ok=False, error="Level is locked"
            ), 403

        stats = word_rain_stats(store, concept_id)

        if correct:
            stats["correct"] += 1
            stats["wrong_streak"] = 0

            if not stats["mastered"]:
                stats["recall_streak"] += 1

                if stats["recall_streak"] >= WORD_RAIN_MASTERY:
                    stats["recall_streak"] = WORD_RAIN_MASTERY
                    stats["mastered"] = True
        else:
            stats["wrong"] += 1
            stats["wrong_streak"] += 1

            if not stats["mastered"]:
                stats["recall_streak"] = 0

        dashboard = word_rain_dashboard(store, catalog)
        level_card = dashboard[number - 1]

        store["highest_unlocked_level"] = max(
            (
                card["number"]
                for card in dashboard
                if card["unlocked"]
            ),
            default=1,
        )

        save_progress(progress)
        saved_stats = dict(stats)

    return jsonify(
        ok=True,
        correct=correct,
        missed=missed,
        word_id=concept_id,
        answer=word["english"],
        stats=saved_stats,
        mastered=word_rain_is_mastered(
            {"words": {concept_id: saved_stats}},
            concept_id,
        ),
        level_complete=level_card["complete"],
        highest_unlocked_level=store["highest_unlocked_level"],
    )


@app.route("/games/word-rain/reset", methods=["POST"])
def word_rain_reset():
    with progress_lock:
        progress = get_progress()

        progress.setdefault("games", {})["word_rain"] = {
            "words": {},
            "highest_unlocked_level": 1,
            "best_score": 0,
        }

        save_progress(progress)

    return jsonify(
        ok=True,
        level=1,
        message="Word Rain progress reset",
    )




@app.route("/despacio")
def despacio_home():
    return render_template("despacio_home.html")

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
