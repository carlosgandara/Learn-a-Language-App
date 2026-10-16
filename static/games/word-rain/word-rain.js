
(() => {
  "use strict";

  // ============================================================
  // CONFIGURATION
  // ============================================================

  let config = {};

  const configElement = document.getElementById("wr-config");

  if (configElement) {
    try {
      config = JSON.parse(configElement.textContent);
    } catch (error) {
      console.error("Word Rain: Invalid configuration.", error);
    }
  } else {
    config = window.WORD_RAIN || {};
  }

  const vocabulary = Array.isArray(config.words)
    ? config.words
    : [];

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

  // Vocabulary popup elements
  const modal = $("wr-vocab-modal");
const wordsButton = $("wr-words-button");

  const closeWordsButton =
    $("wr-vocab-close") ||
    $("wr-close-vocab");

  if (!arena || !input || !startButton || !restartButton) {
    console.error("Word Rain: Required game elements are missing.");
    return;
  }

  // Flask already provides the 10 words for this level.
  const levelWords = vocabulary;

  // ============================================================
  // WORD PROGRESS
  // ============================================================

  const stats = {};

  for (const word of levelWords) {
    const saved = progress[word.id] || {};

    stats[word.id] = {
      correct: Number(word.correct ?? saved.correct) || 0,
      wrong: Number(word.wrong ?? saved.wrong) || 0,
      recall_streak: Number(
        word.recall_streak ?? saved.recall_streak
      ) || 0,
      mastered: Boolean(
        word.mastered ??
        saved.mastered ??
        ((Number(saved.correct) || 0) >= MASTERY)
      )
    };
  }

  let active = [];
  let running = false;
  let paused = false;
  let ended = false;

  let lives = START_LIVES;
  let score = 0;
  let streak = 0;

  let lastFrame = 0;
  let spawnElapsed = 0;
  let nextId = 1;
  let requestPending = false;

  let replayMode = false;
  let replayStreaks = {};

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
    return Boolean(stats[word.id]?.mastered);
  }

  function allMastered() {
    return levelWords.length > 0 && levelWords.every(isMastered);
  }

  function remainingWords() {
    if (replayMode) {
      return levelWords.filter(
        word => (replayStreaks[word.id] || 0) < MASTERY
      );
    }

    return levelWords.filter(word => !isMastered(word));
  }

  function masteredCount() {
    if (replayMode) {
      return levelWords.filter(
        word => (replayStreaks[word.id] || 0) >= MASTERY
      ).length;
    }

    return levelWords.filter(isMastered).length;
  }

  // ============================================================
  // UI
  // ============================================================

  function updateUI() {
    if (scoreLabel) scoreLabel.textContent = score;

    if (livesLabel) {
      livesLabel.textContent = "❤️".repeat(Math.max(0, lives));
    }

    if (masteredLabel) {
      masteredLabel.textContent =
        `${masteredCount()} / ${levelWords.length}`;
    }

    if (progressFill) {
      const percent = levelWords.length
        ? (masteredCount() / levelWords.length) * 100
        : 0;

      progressFill.style.width = `${percent}%`;
    }
  }

  function message(text, type = "") {
    if (!feedback) return;

    feedback.textContent = text;
    feedback.dataset.type = type;
  }

  // ============================================================
  // VOCABULARY POPUP
  // ============================================================

  function findVocabularyContainer() {
    if (!modal) return null;

    return (
      modal.querySelector("[data-wordrain-vocab-list]") ||
      modal.querySelector("#wr-vocab-list") ||
      modal.querySelector(".wr-vocab-list") ||
      modal.querySelector("#wr-vocab-words")
    );
  }

  function renderVocabulary() {
    if (!modal) return;

    let container = findVocabularyContainer();

    if (!container) {
      container = document.createElement("div");
      container.id = "wr-vocab-list";

      const content =
        modal.querySelector(".wr-modal-content") ||
        modal.querySelector(".wr-vocab-content") ||
        modal.querySelector("[role='dialog']") ||
        modal;

      content.appendChild(container);
    }

    container.replaceChildren();

    const heading = document.createElement("h3");
    heading.textContent = `Level ${level} — Vocabulary`;

    container.appendChild(heading);

    if (!levelWords.length) {
      const empty = document.createElement("p");
      empty.textContent = "No vocabulary available.";
      container.appendChild(empty);
      return;
    }

    const list = document.createElement("div");
    list.style.display = "grid";
    list.style.gap = "10px";
    list.style.marginTop = "12px";

    for (const word of levelWords) {
      const row = document.createElement("div");

      row.style.display = "flex";
      row.style.alignItems = "center";
      row.style.justifyContent = "space-between";
      row.style.flexWrap = "wrap";
      row.style.gap = "12px";
      row.style.padding = "12px";
      row.style.border = "1px solid #ddd";
      row.style.borderRadius = "10px";

      const translation = document.createElement("div");

      const tagalog = document.createElement("strong");
      tagalog.textContent = word.tagalog || "";

      const english = document.createElement("div");
      english.textContent = Array.isArray(word.english)
        ? word.english.join(", ")
        : String(word.english || "");

      english.style.fontSize = "0.9rem";
      english.style.opacity = "0.8";
      english.style.marginTop = "4px";

      translation.appendChild(tagalog);
      translation.appendChild(english);

      const status = document.createElement("span");

      if (replayMode) {
        const count = replayStreaks[word.id] || 0;

        status.textContent = count >= MASTERY
          ? "✓ Complete"
          : `${count}/${MASTERY}`;
      } else if (isMastered(word)) {
        status.textContent = "✓ Mastered";
      } else {
        const count = stats[word.id]?.recall_streak || 0;
        status.textContent = `${count}/${MASTERY}`;
      }

      status.style.fontSize = "0.85rem";
      status.style.fontWeight = "600";

      row.appendChild(translation);
      row.appendChild(status);

      list.appendChild(row);
    }

    container.appendChild(list);
  }

  function openVocabulary() {
    if (!modal) {
      console.error("Word Rain: Vocabulary modal not found.");
      return;
    }

    renderVocabulary();

    modal.hidden = false;
    modal.style.display = "";

    paused = true;
    input.blur();
  }

  function closeVocabulary() {
    if (!modal) return;

    modal.hidden = true;
    modal.style.display = "";

    paused = false;
    lastFrame = performance.now();

    if (running) input.focus();
  }

  if (wordsButton) {
    wordsButton.addEventListener("click", event => {
      event.preventDefault();
      openVocabulary();
    });
  }

  if (closeWordsButton) {
    closeWordsButton.addEventListener("click", event => {
      event.preventDefault();
      closeVocabulary();
    });
  }

  if (modal) {
    modal.addEventListener("click", event => {
      if (event.target === modal) {
        closeVocabulary();
      }
    });
  }

  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && modal && !modal.hidden) {
      closeVocabulary();
    }
  });

  // Compatibility with existing HTML popup event handlers.
  document.addEventListener("wordrain:pause", () => {
    paused = true;
    input.blur();
  });

  document.addEventListener("wordrain:resume", () => {
    paused = false;
    lastFrame = performance.now();

    if (running) input.focus();
  });

  // ============================================================
  // FALLING WORDS
  // ============================================================

  function removeWord(item) {
    item.element.remove();

    active = active.filter(word => word.id !== item.id);
  }

  function clearWords() {
    for (const item of active) {
      item.element.remove();
    }

    active = [];
  }

  function spawnWord() {
    const available = remainingWords();

    if (!available.length || active.length >= 6) return;

    const unused = available.filter(
      word => !active.some(item => item.word.id === word.id)
    );

    if (!unused.length) return;

    const word = unused[Math.floor(Math.random() * unused.length)];

    const element = document.createElement("div");
    element.className = "wr-falling-word";
    element.textContent = word.tagalog;

    arena.appendChild(element);

    const maxX = Math.max(
      0,
      arena.clientWidth - element.offsetWidth - 16
    );

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

  // ============================================================
  // SERVER PROGRESS
  // ============================================================

  async function saveAnswer(word, answer, missed = false) {
    const response = await fetch("/games/word-rain/answer", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        level,
        word_id: word.id,
        answer,
        missed,
        replay: replayMode
      })
    });

    const result = await response.json();

    if (!response.ok || !result.ok) {
      throw new Error(
        result.error || "Unable to save Word Rain progress."
      );
    }

    return result;
  }

  // ============================================================
  // GAME END
  // ============================================================

  function finish(win) {
    running = false;
    ended = true;

    input.disabled = true;
    clearWords();

    startButton.hidden = true;
    restartButton.hidden = false;

    if (win) {
      message(
        replayMode
          ? `🎉 Level ${level} replay complete!`
          : `🎉 Level ${level} complete! All words mastered.`,
        "correct"
      );

      restartButton.textContent = replayMode
        ? "Replay Again"
        : "Next Level";
    } else {
      message(
        "Game over. Your word progress has been saved.",
        "wrong"
      );

      restartButton.textContent = "Try Again";
    }
  }

  // ============================================================
  // MISSED WORDS
  // ============================================================

  async function handleMiss(item) {
    if (requestPending || !running) return;

    requestPending = true;
    paused = true;

    removeWord(item);

    try {
      if (replayMode) {
        replayStreaks[item.word.id] = 0;
      } else {
        const result = await saveAnswer(item.word, "", true);

        if (result.stats) {
          stats[item.word.id] = {
            ...stats[item.word.id],
            ...result.stats
          };
        }
      }

      lives--;
      streak = 0;

      updateUI();

      message(
        `Missed: ${item.word.tagalog} = ${item.word.english}`,
        "wrong"
      );

      if (lives <= 0) {
        finish(false);
      }
    } catch (error) {
      message(error.message, "wrong");
    } finally {
      requestPending = false;
      paused = Boolean(modal && !modal.hidden);
      lastFrame = performance.now();

      if (running && !paused) input.focus();
    }
  }

  // ============================================================
  // ANSWERS
  // ============================================================

  async function submitAnswer() {
    if (!running || paused || requestPending) return;

    const answer = normalize(input.value);
    if (!answer) return;

    const matches = active
      .filter(item => translations(item.word).includes(answer))
      .sort((a, b) => b.y - a.y);

    const selected = matches[0];

    if (!selected) {
      streak = 0;
      message(
        "No falling word matches that translation.",
        "wrong"
      );
      input.select();
      return;
    }

    requestPending = true;
    paused = true;

    try {
      let result;

      if (replayMode) {
        replayStreaks[selected.word.id] =
          (replayStreaks[selected.word.id] || 0) + 1;

        result = { correct: true };
      } else {
        result = await saveAnswer(selected.word, answer);
      }

      if (result.correct) {
        const fast =
          performance.now() - selected.born <= FAST_BONUS_MS;

        streak++;

        const multiplier = streak >= 5 ? 2 : 1;

        score += (10 + (fast ? 5 : 0)) * multiplier;

        if (!replayMode && result.stats) {
          stats[selected.word.id] = {
            ...stats[selected.word.id],
            ...result.stats
          };

          if (result.mastered) {
            stats[selected.word.id].mastered = true;
          }
        }

        removeWord(selected);

        const wordCompleted = replayMode
          ? replayStreaks[selected.word.id] >= MASTERY
          : isMastered(selected.word);

        if (wordCompleted) {
          for (const item of [...active]) {
            if (item.word.id === selected.word.id) {
              removeWord(item);
            }
          }
        }

        message(
          `✓ ${selected.word.tagalog} = ${selected.word.english}`,
          "correct"
        );

        input.value = "";
        updateUI();

        if (remainingWords().length === 0) {
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
      lastFrame = performance.now();

      if (running && !paused) input.focus();
    }
  }

  // ============================================================
  // ANIMATION
  // ============================================================

  function frame(now) {
    requestAnimationFrame(frame);

    if (!running || paused) {
      lastFrame = now;
      return;
    }

    const dt = Math.min(
      (now - (lastFrame || now)) / 1000,
      0.05
    );

    lastFrame = now;
    spawnElapsed += dt * 1000;

    if (spawnElapsed >= SPAWN_INTERVAL) {
      spawnElapsed = 0;
      spawnWord();
    }

    const ground = arena.clientHeight;

    for (const item of [...active]) {
      item.y += item.speed * dt;

      item.element.style.transform =
        `translateY(${item.y}px)`;

      if (item.y + item.element.offsetHeight >= ground) {
        handleMiss(item);
        break;
      }
    }
  }

  // ============================================================
  // START / RESTART
  // ============================================================

  function startGame() {
    if (!levelWords.length) {
      message("No vocabulary found for this level.", "wrong");
      return;
    }

    replayMode = allMastered();

    if (replayMode) {
      replayStreaks = {};

      for (const word of levelWords) {
        replayStreaks[word.id] = 0;
      }
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

    message(
      replayMode
        ? "Replay mode: translate every word 3 times."
        : "Type the English meaning of a falling word."
    );

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
    if (ended && !replayMode && allMastered()) {
      window.location.href =
        `/games/word-rain?level=${level + 1}`;
    } else {
      startGame();
    }
  });

  // ============================================================
  // INITIALIZE
  // ============================================================

  console.log("Word Rain initialized:", {
    level,
    vocabularyCount: levelWords.length,
    mastered: masteredCount(),
    remaining: remainingWords().length,
    vocabularyButtonFound: Boolean(wordsButton),
    vocabularyModalFound: Boolean(modal)
  });

  updateUI();
  requestAnimationFrame(frame);
})();
