
(() => {
  "use strict";

  // ==================================================
  // ELEMENTS
  // ==================================================

  const el = id => document.getElementById(id);

  const ui = {
    mastered: el("cg-mastered"),
    fill: el("cg-progress-fill"),
    round: el("cg-round"),
    score: el("cg-score"),
    instruction: el("cg-instruction"),
    swatch: el("cg-swatch"),
    english: el("cg-english"),
    word: el("cg-word"),
    countdown: el("cg-countdown"),
    area: el("cg-answer-area"),
    answer: el("cg-answer"),
    check: el("cg-check"),
    feedback: el("cg-feedback"),
    next: el("cg-next"),
    reset: el("cg-reset"),
    error: el("cg-error")
  };

  // ==================================================
  // CONFIGURATION FROM FLASK
  // ==================================================

  let game = null;

  try {
    const configElement = el("color-game-config");

    if (!configElement) {
      throw new Error("Missing color-game-config element");
    }

    game = {
      colors: JSON.parse(configElement.dataset.colors),
      progress: JSON.parse(configElement.dataset.progress),
      preview_seconds: 3,
      time_limit_seconds: 10,
      mastery_correct: 3
    };

  } catch (error) {
    console.error("Color game configuration error:", error);
  }

  // ==================================================
  // GAME STATE
  // ==================================================

  let current = null;
  let phase = "loading";
  let timer = null;
  let remaining = 0;
  let score = 0;
  let rounds = 0;
  let lastColorId = null;

  let colorProgress = {};

  // ==================================================
  // API
  // ==================================================

  async function post(url, data = {}) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(data)
    });

    const result = await response.json();

    if (!response.ok || result.ok === false) {
      throw new Error(
        result.error || `Request failed (${response.status})`
      );
    }

    return result;
  }

  // ==================================================
  // TIMER
  // ==================================================

  function clearClock() {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  // ==================================================
  // PROGRESS
  // ==================================================

  function getMasteredCount() {
    return game.colors.filter(color => {
      const stats = colorProgress[color.id] || {};

      return (
        (stats.correct || 0) >= game.mastery_correct
      );
    }).length;
  }

  function updateProgress() {
    const mastered = getMasteredCount();
    const total = game.colors.length;

    ui.mastered.textContent =
      `${mastered} / ${total} mastered`;

    ui.fill.style.width =
      `${total ? (mastered / total) * 100 : 0}%`;

    ui.score.textContent = `Score: ${score}`;
  }

  function showError(error) {
    console.error(error);

    ui.error.textContent =
      error.message || "Something went wrong.";
  }

  // ==================================================
  // SELECT NEXT COLOR
  // ==================================================

  function selectNextColor() {
    const available = game.colors.filter(color => {
      const stats = colorProgress[color.id] || {};

      return (
        (stats.correct || 0) < game.mastery_correct
      );
    });

    if (available.length === 0) {
      return null;
    }

    const lowestCorrect = Math.min(
      ...available.map(color =>
        colorProgress[color.id]?.correct || 0
      )
    );

    let candidates = available.filter(color =>
      (colorProgress[color.id]?.correct || 0) === lowestCorrect
    );

    // Avoid repeating the same color if possible.
    if (candidates.length > 1) {
      candidates = candidates.filter(
        color => color.id !== lastColorId
      );
    }

    const selected = candidates[
      Math.floor(Math.random() * candidates.length)
    ];

    lastColorId = selected.id;

    return selected;
  }

  // ==================================================
  // PREVIEW
  // ==================================================

  function beginPreview(color) {
    clearClock();

    current = color;
    phase = "preview";
    rounds++;

    ui.round.textContent =
      `Round ${rounds} · ${color.english}`;

    ui.swatch.style.background = color.hex;

    ui.swatch.setAttribute(
      "aria-label",
      color.english
    );

    ui.english.textContent = color.english;
    ui.word.textContent = color.tagalog;

    ui.instruction.textContent =
      "Memorize the Tagalog word";

    ui.area.hidden = true;
    ui.next.hidden = true;

    ui.feedback.textContent = "";
    ui.error.textContent = "";

    ui.answer.value = "";
    ui.answer.disabled = false;
    ui.check.disabled = false;

    updateProgress();

    remaining = game.preview_seconds;

    ui.countdown.textContent =
      `Memorize: ${remaining}s`;

    timer = setInterval(() => {
      remaining--;

      if (remaining <= 0) {
        clearClock();
        beginRecall();
      } else {
        ui.countdown.textContent =
          `Memorize: ${remaining}s`;
      }
    }, 1000);
  }

  // ==================================================
  // RECALL
  // ==================================================

  function beginRecall() {
    phase = "recall";

    remaining = game.time_limit_seconds;

    ui.word.textContent = "???";

    ui.instruction.textContent =
      "Type the Tagalog word";

    ui.area.hidden = false;

    ui.countdown.textContent =
      `${remaining}s left`;

    ui.answer.focus();

    timer = setInterval(() => {
      remaining--;

      ui.countdown.textContent =
        `${remaining}s left`;

      if (remaining <= 0) {
        clearClock();
        submit(true);
      }
    }, 1000);
  }

  // ==================================================
  // SUBMIT ANSWER
  // ==================================================

  async function submit(timedOut = false) {
    if (phase !== "recall") {
      return;
    }

    phase = "saving";
    clearClock();

    ui.check.disabled = true;
    ui.answer.disabled = true;
    ui.error.textContent = "";

    try {
      const data = await post(
        "/games/colors/answer",
        {
          color_id: current.id,
          answer: timedOut ? "" : ui.answer.value
        }
      );

      phase = "result";

      // Keep local progress synchronized with Flask.
      colorProgress[current.id] = data.stats;

      if (data.correct) {
        score += 10;

        ui.feedback.textContent =
          "✓ Correct! +10 points";

        ui.instruction.textContent =
          "Well done!";
      } else {
        ui.feedback.textContent = timedOut
          ? `Time up! Correct: ${data.answer}`
          : `Incorrect. Correct: ${data.answer}`;

        ui.instruction.textContent =
          "Study the correct answer";
      }

      ui.word.textContent = data.answer;
      ui.countdown.textContent = "";

      ui.area.hidden = true;
      ui.next.hidden = false;
      ui.next.textContent = "Next color →";

      updateProgress();

    } catch (error) {
      showError(error);

      phase = "recall";

      ui.check.disabled = false;
      ui.answer.disabled = false;

      ui.countdown.textContent =
        "Could not save. Try again.";
    }
  }

  // ==================================================
  // NEXT ROUND
  // ==================================================

  function next() {
    clearClock();

    phase = "loading";

    ui.next.hidden = true;
    ui.error.textContent = "";

    const color = selectNextColor();

    if (!color) {
      showComplete();
      return;
    }

    beginPreview(color);
  }

  // ==================================================
  // MISSION COMPLETE
  // ==================================================

  function showComplete() {
    clearClock();

    phase = "complete";
    current = null;

    ui.instruction.textContent =
      "✓ Mission Complete";

    ui.english.textContent = "";

    ui.word.textContent =
      "All 10 colors mastered!";

    ui.swatch.style.background =
      "linear-gradient(120deg, red, orange, yellow, green, blue, purple)";

    ui.countdown.textContent = "";

    ui.feedback.textContent =
      `Final score: ${score} points`;

    ui.area.hidden = true;
    ui.next.hidden = true;

    updateProgress();
  }

  // ==================================================
  // RESET
  // ==================================================

  async function resetProgress() {
    const confirmed = confirm(
      "Reset Color Memory Game progress? " +
      "Your levels, vocabulary, sentences and study time will be preserved."
    );

    if (!confirmed) {
      return;
    }

    clearClock();

    phase = "resetting";

    ui.reset.disabled = true;
    ui.next.hidden = true;
    ui.area.hidden = true;

    try {
      await post("/games/colors/reset");

      colorProgress = {};

      score = 0;
      rounds = 0;
      lastColorId = null;

      updateProgress();
      next();

    } catch (error) {
      showError(error);
      phase = "error";

    } finally {
      ui.reset.disabled = false;
    }
  }

  // ==================================================
  // EVENTS
  // ==================================================

  ui.check.addEventListener("click", () => {
    submit(false);
  });

  ui.answer.addEventListener("keydown", event => {
    if (event.key === "Enter") {
      event.preventDefault();
      submit(false);
    }
  });

  ui.next.addEventListener("click", next);

  ui.reset.addEventListener("click", resetProgress);

  // ==================================================
  // INITIALIZE
  // ==================================================

  function init() {
    if (
      !game ||
      !Array.isArray(game.colors) ||
      game.colors.length === 0
    ) {
      ui.instruction.textContent =
        "Game configuration missing";

      ui.english.textContent =
        "Unable to start game";

      ui.error.textContent =
        "Check Flask colors_page() and color-game-config.";

      return;
    }

    colorProgress = game.progress || {};

    updateProgress();
    next();
  }

  init();

})();
