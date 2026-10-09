
(() => {
  "use strict";

  const config = window.WORD_RAIN || {};
  const vocabulary = Array.isArray(config.words) ? config.words : [];
  const progress = config.progress || {};
  const level = Number(config.level) || 1;

  const MASTERY = 3;
  const START_LIVES = 3;
  const SPAWN_INTERVAL = 1900;
  const BASE_SPEED = 34;
  const FAST_BONUS_MS = 2000;

  const $ = id => document.getElementById(id);

  const arena = $("wr-arena");
  const input = $("wr-input");
  const startButton = $("wr-start");
  const restartButton = $("wr-restart");
  const scoreLabel = $("wr-score");
  const livesLabel = $("wr-lives");
  const masteredLabel = $("wr-mastered");
  const progressFill = $("wr-progress-fill");
  const feedback = $("wr-feedback");
  const modal = $("wr-vocab-modal");

  const required = 10 + (level - 1) * 5;
  const previous = level - 1;
  const startIndex = previous * (20 + (previous - 1) * 5) / 2;
  const levelWords = vocabulary.slice(startIndex, startIndex + required);

  const stats = {};

  for (const word of levelWords) {
    const saved = progress[word.id] || {};
    stats[word.id] = {
      correct: Number(saved.correct) || 0,
      wrong: Number(saved.wrong) || 0
    };
  }

  let active = [];
  let running = false;
  let paused = Boolean(modal && !modal.hidden);
  let ended = false;
  let lives = START_LIVES;
  let score = 0;
  let streak = 0;
  let lastFrame = 0;
  let spawnElapsed = 0;
  let nextId = 1;
  let requestPending = false;

  const normalize = value =>
    String(value || "")
      .normalize("NFKC")
      .trim()
      .toLowerCase()
      .replace(/[.!?]+$/g, "")
      .replace(/\s+/g, " ");

  function translations(word) {
    const values = Array.isArray(word.english)
      ? word.english
      : String(word.english || "").split(/[/;,]/);

    return values.map(normalize).filter(Boolean);
  }

  function isMastered(word) {
    return (stats[word.id]?.correct || 0) >= MASTERY;
  }

  function remainingWords() {
    return levelWords.filter(word => !isMastered(word));
  }

  function masteredCount() {
    return levelWords.filter(isMastered).length;
  }

  function updateUI() {
    scoreLabel.textContent = score;
    livesLabel.textContent = "❤️".repeat(Math.max(0, lives));
    masteredLabel.textContent =
      `${masteredCount()} / ${levelWords.length}`;

    if (progressFill) {
      progressFill.style.width =
        `${levelWords.length ? masteredCount() / levelWords.length * 100 : 0}%`;
    }
  }

  function message(text, type = "") {
    feedback.textContent = text;
    feedback.dataset.type = type;
  }

  function removeWord(item) {
    item.element.remove();
    active = active.filter(w => w.id !== item.id);
  }

  function clearWords() {
    for (const item of active) item.element.remove();
    active = [];
  }

  function spawnWord() {
    const available = remainingWords();

    if (!available.length || active.length >= 6) return;

    // Avoid duplicates currently falling when possible.
    const unused = available.filter(word =>
      !active.some(item => item.word.id === word.id)
    );

    const pool = unused.length ? unused : available;
    const word = pool[Math.floor(Math.random() * pool.length)];

    const element = document.createElement("div");
    element.className = "wr-falling-word";
    element.textContent = word.tagalog;

    arena.appendChild(element);

    const maxX = Math.max(0, arena.clientWidth - element.offsetWidth - 16);
    const x = 8 + Math.random() * maxX;

    element.style.left = `${x}px`;

    active.push({
      id: nextId++,
      word,
      element,
      y: -element.offsetHeight,
      born: performance.now(),
      speed: BASE_SPEED + Math.min(level - 1, 10) * 5
    });
  }

  function finish(win) {
    running = false;
    ended = true;
    input.disabled = true;
    clearWords();

    startButton.hidden = true;
    restartButton.hidden = false;

    if (win) {
      message(`🎉 Level ${level} complete! All words mastered.`, "correct");
      restartButton.textContent = "Next Level";
    } else {
      message("Game over. Your word progress has been saved.", "wrong");
      restartButton.textContent = "Try Again";
    }
  }

  async function saveAnswer(word, answer) {
    const response = await fetch("/games/word-rain/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        level,
        word_id: word.id,
        answer
      })
    });

    const result = await response.json();

    if (!response.ok || !result.ok) {
      throw new Error(result.error || "Unable to save answer");
    }

    return result;
  }


  async function saveMissedWord(word) {
  const response = await fetch("/games/word-rain/answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      level,
      word_id: word.id,
      missed: true
    })
  });

  if (!response.ok) {
    throw new Error("Unable to save missed word");
  }

  return response.json();
}
  async function submitAnswer() {
    if (!running || paused || requestPending) return;

    const answer = normalize(input.value);
    if (!answer) return;

    // Match any falling word, prioritizing the one nearest the ground.
    const matches = active
      .filter(item => translations(item.word).includes(answer))
      .sort((a, b) => b.y - a.y);

    const selected = matches[0];

    if (!selected) {
      streak = 0;
      message("No falling word matches that translation.", "wrong");
      input.select();
      return;
    }

    requestPending = true;
    paused = true;

    try {
      const result = await saveAnswer(selected.word, answer);

      if (result.correct) {
        const fast = performance.now() - selected.born <= FAST_BONUS_MS;

        streak++;
        const multiplier = streak >= 5 ? 2 : 1;
        score += (10 + (fast ? 5 : 0)) * multiplier;

        stats[selected.word.id] = {
          ...stats[selected.word.id],
          ...result.stats
        };

        removeWord(selected);

        // Remove duplicates of a newly mastered word.
        if (isMastered(selected.word)) {
          for (const item of [...active]) {
            if (item.word.id === selected.word.id) removeWord(item);
          }
        }

        message(
          `✓ ${selected.word.tagalog} = ${selected.word.english}`,
          "correct"
        );

        input.value = "";
        updateUI();

        if (result.level_complete || remainingWords().length === 0) {
          finish(true);
        }
      } else {
        streak = 0;
        message(
          `Correct meaning: ${result.answer}`,
          "wrong"
        );
        input.select();
      }
    } catch (error) {
      message(error.message, "wrong");
    } finally {
      requestPending = false;
      paused = Boolean(modal && !modal.hidden);
      if (running && !paused) input.focus();
    }
  }

  function frame(now) {
    requestAnimationFrame(frame);

    if (!running || paused) {
      lastFrame = now;
      return;
    }

    const dt = Math.min((now - (lastFrame || now)) / 1000, 0.05);
    lastFrame = now;

    spawnElapsed += dt * 1000;

    if (spawnElapsed >= SPAWN_INTERVAL) {
      spawnElapsed = 0;
      spawnWord();
    }

    const ground = arena.clientHeight;

    for (const item of [...active]) {
      item.y += item.speed * dt;
      item.element.style.transform = `translateY(${item.y}px)`;

      if (item.y + item.element.offsetHeight >= ground) {
        removeWord(item);
        lives--;
        streak = 0;
        updateUI();
        message(`Missed: ${item.word.tagalog} = ${item.word.english}`, "wrong");

        if (lives <= 0) {
          finish(false);
          break;
        }
      }
    }
  }

  function startGame() {
    if (!levelWords.length) {
      message("No vocabulary found for this level.", "wrong");
      return;
    }

    if (levelWords.length < required) {
      message(
        `Level ${level} requires ${required} words; only ${levelWords.length} are available.`,
        "wrong"
      );
      return;
    }

    if (!remainingWords().length) {
      finish(true);
      return;
    }

    clearWords();
    running = true;
    ended = false;
    lives = START_LIVES;
    score = 0;
    streak = 0;
    spawnElapsed = SPAWN_INTERVAL;
    lastFrame = performance.now();

    input.value = "";
    input.disabled = false;
    startButton.hidden = true;
    restartButton.hidden = true;

    message("Type the English meaning of a falling word.");
    updateUI();

    if (!paused) input.focus();
  }

  input.addEventListener("keydown", event => {
    if (event.key === "Enter") {
      event.preventDefault();
      submitAnswer();
    }
  });

  startButton.addEventListener("click", startGame);

  restartButton.addEventListener("click", () => {
    if (ended && remainingWords().length === 0) {
      window.location.reload();
    } else {
      startGame();
    }
  });

  // Vocabulary popup integration.
  document.addEventListener("wordrain:pause", () => {
    paused = true;
    input.blur();
  });

  document.addEventListener("wordrain:resume", () => {
    paused = false;
    if (running) input.focus();
  });

  updateUI();
  requestAnimationFrame(frame);
})();
