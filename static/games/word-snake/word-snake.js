
/* ============================================================
   WORD SNAKE
   Saved mastery, sequential levels, replay, responsive board
   ============================================================ */

(() => {
  "use strict";

  const $ = id => document.getElementById(id);

  const board = $("gameBoard");
  if (!board) return;

  const lettersLayer = $("letters");
  const snakeLayer = $("snake");
  const prompt = $("englishPrompt");
  const progress = $("wordProgress");
  const scoreLabel = $("score");
  const livesLabel = $("lives");
  const roundLabel = $("round");
  const masteredLabel = $("masteredCount");
  const masteryFill = $("masteryFill");
  const message = $("message");

  const gameOver = $("gameOver");
  const gameOverTitle = $("gameOverTitle");
  const finalScore = $("finalScore");
  const restartButton = $("restartButton");

  const wordsButton = $("wordsButton");
  const wordsModal = $("wordsModal");
  const wordsList = $("wordsList");
  const closeWordsButton = $("closeWordsButton");

  const pauseButton = $("pauseButton");
  const pauseModal = $("pauseModal");
  const resumeButton = $("resumeButton");

  let WORDS;
  let CONFIG;

  try {
    WORDS = JSON.parse($("wordSnakeData").textContent);
    CONFIG = JSON.parse($("wordSnakeConfig").textContent);

    if (!Array.isArray(WORDS)) {
      throw new Error("Invalid vocabulary");
    }
  } catch (error) {
    console.error("Word Snake configuration:", error);
    prompt.textContent = "COULD NOT LOAD WORDS";
    return;
  }

  const LEVEL = Number(CONFIG.level);
  const TOTAL_LEVELS = Number(CONFIG.totalLevels);
  const MASTERY = Number(CONFIG.mastery) || 3;

  const ANSWER_URL = CONFIG.answerUrl;
  const LEVELS_URL = CONFIG.levelsUrl;

  const START_LIVES = 3;
  const MOVE_INTERVAL = 300;
  const DISTRACTORS = 10;

  const stats = {};

  for (const word of WORDS) {
    stats[word.id] = {
      correct: Number(word.correct) || 0,
      wrong: Number(word.wrong) || 0,
      recall_streak: Number(word.recall_streak) || 0,
      mastered: Boolean(word.mastered)
    };
  }

  let replayMode = Boolean(CONFIG.levelComplete);
  let replayStreaks = {};

  let cellSize = 32;
  let columns = 8;
  let rows = 8;

  let score = 0;
  let lives = START_LIVES;
  let round = 1;

  let currentWord = null;
  let letterIndex = 0;

  let snake = [];
  let letters = [];

  let direction = { x: 1, y: 0 };
  let nextDirection = { x: 1, y: 0 };

  let running = false;
  let paused = false;
  let locked = false;
  let pending = false;
  let ended = false;
  let won = false;

  let moveTimer = null;
  let roundTimer = null;
  let messageTimer = null;
  let resizeTimer = null;

  // ==========================================================
  // HELPERS
  // ==========================================================

  function shuffle(array) {
    const copy = [...array];

    for (let i = copy.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [copy[i], copy[j]] = [copy[j], copy[i]];
    }

    return copy;
  }

  function randomItem(array) {
    return array[Math.floor(Math.random() * array.length)];
  }

  function allMastered() {
    return WORDS.length > 0 &&
      WORDS.every(word => stats[word.id].mastered);
  }

  function isComplete(word) {
    if (replayMode) {
      return (replayStreaks[word.id] || 0) >= MASTERY;
    }

    return stats[word.id].mastered;
  }

  function remainingWords() {
    return WORDS.filter(word => !isComplete(word));
  }

  function masteredCount() {
    return WORDS.filter(isComplete).length;
  }

  function updateUI() {
    scoreLabel.textContent = score;
    livesLabel.textContent = lives;
    roundLabel.textContent = round;

    masteredLabel.textContent =
      `${masteredCount()} / ${WORDS.length}`;

    const percent = WORDS.length
      ? (masteredCount() / WORDS.length) * 100
      : 0;

    masteryFill.style.width = `${percent}%`;
  }

  function showMessage(text, correct) {
    clearTimeout(messageTimer);

    message.textContent = text;
    message.className =
      `message ${correct ? "correct" : "wrong"} show`;

    messageTimer = setTimeout(() => {
      message.className = "message";
    }, 800);
  }

  // ==========================================================
  // GRID
  // ==========================================================

  function calculateGrid() {
    const width = Math.max(1, board.clientWidth);
    const height = Math.max(1, board.clientHeight);

    let target = 32;

    if (width < 480) target = 28;
    if (width < 350 || height < 350) target = 24;

    cellSize = Math.max(
      14,
      Math.min(target, Math.floor(height / 8))
    );

    columns = Math.max(3, Math.floor(width / cellSize));
    rows = Math.max(3, Math.floor(height / cellSize));
  }

  function position(element, x, y) {
    element.style.left =
      `${x * cellSize + cellSize / 2}px`;

    element.style.top =
      `${y * cellSize + cellSize / 2}px`;
  }

  // ==========================================================
  // WORD SELECTION
  // ==========================================================

  function chooseWord() {
    const available = remainingWords();
    if (!available.length) return null;

    const alternatives = available.filter(
      word => !currentWord || word.id !== currentWord.id
    );

    const pool = alternatives.length
      ? alternatives
      : available;

    const weighted = [];

    for (const word of pool) {
      const weight = Math.min(
        10,
        Math.max(1, Number(stats[word.id].wrong) || 0)
      );

      for (let i = 0; i < weight; i++) {
        weighted.push(word);
      }
    }

    return randomItem(weighted);
  }

  // ==========================================================
  // WORD DISPLAY
  // ==========================================================

  function answerCharacters() {
    return Array.from(String(currentWord.answer));
  }

  function isCollectible(character) {
    return /[\p{L}\p{N}]/u.test(character);
  }

  function advanceSeparators() {
    const chars = answerCharacters();

    while (
      letterIndex < chars.length &&
      !isCollectible(chars[letterIndex])
    ) {
      letterIndex++;
    }
  }

  function createWordProgress() {
    progress.replaceChildren();

    for (const character of answerCharacters()) {
      const slot = document.createElement("div");
      slot.className = "word-slot";

      if (!isCollectible(character)) {
        slot.textContent = character === " " ? "\u00a0" : character;
        slot.style.borderBottom = "none";
      }

      progress.appendChild(slot);
    }

    updateWordProgress();
  }

  function updateWordProgress() {
    const chars = answerCharacters();
    const slots = progress.querySelectorAll(".word-slot");

    slots.forEach((slot, index) => {
      if (!isCollectible(chars[index])) return;

      const filled = index < letterIndex;

      slot.textContent = filled
        ? chars[index].toUpperCase()
        : "";

      slot.classList.toggle("filled", filled);
    });
  }

  // ==========================================================
  // SNAKE
  // ==========================================================

  function createSnake() {
    const x = Math.floor(columns / 2);
    const y = Math.floor(rows / 2);

    snake = [
      { x, y },
      { x: (x - 1 + columns) % columns, y },
      { x: (x - 2 + columns) % columns, y }
    ];

    direction = { x: 1, y: 0 };
    nextDirection = { x: 1, y: 0 };
  }

  function renderSnake() {
    snakeLayer.replaceChildren();

    snake.forEach((segment, index) => {
      const element = document.createElement("div");

      element.className = index === 0
        ? "snake-segment snake-head"
        : "snake-segment";

      if (index === 0) element.textContent = "●";

      position(element, segment.x, segment.y);
      snakeLayer.appendChild(element);
    });
  }

  // ==========================================================
  // LETTERS
  // ==========================================================

  function occupiedCells() {
    return new Set(
      snake.map(segment => `${segment.x},${segment.y}`)
    );
  }

  function freeCells() {
    const occupied = occupiedCells();

    for (const letter of letters) {
      occupied.add(`${letter.x},${letter.y}`);
    }

    const free = [];

    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < columns; x++) {
        if (!occupied.has(`${x},${y}`)) {
          free.push({ x, y });
        }
      }
    }

    return free;
  }

  function addLetter(character, required = false) {
    const free = freeCells();
    if (!free.length) return false;

    const location = randomItem(free);

    letters.push({
      letter: character,
      required,
      x: location.x,
      y: location.y
    });

    return true;
  }

  function createLetters() {
    letters = [];

    const required = answerCharacters()
      .filter(isCollectible)
      .map(character => character.toLowerCase());

    const available = freeCells().length;

    if (required.length > available) {
      showMessage("Board too small for this word", false);
      return false;
    }

    for (const character of shuffle(required)) {
      addLetter(character, true);
    }

    const alphabet = "abcdefghijklmnopqrstuvwxyz";

    for (
      let i = 0;
      i < Math.min(DISTRACTORS, freeCells().length);
      i++
    ) {
      addLetter(randomItem(Array.from(alphabet)));
    }

    renderLetters();
    return true;
  }

  function renderLetters() {
    lettersLayer.replaceChildren();

    for (const item of letters) {
      const element = document.createElement("div");

      element.className = "letter";
      element.textContent = item.letter.toUpperCase();

      position(element, item.x, item.y);
      lettersLayer.appendChild(element);
    }
  }

  function removeLetter(item) {
    letters = letters.filter(letter => letter !== item);
  }

  function ensureNextLetter() {
    const chars = answerCharacters();
    const expected = chars[letterIndex]?.toLowerCase();

    if (!expected) return;

    const available = letters.some(
      item => item.letter.toLowerCase() === expected
    );

    if (!available) {
      addLetter(expected, true);
    }

    renderLetters();
  }

  // ==========================================================
  // SERVER PROGRESS
  // ==========================================================

  async function saveResult(word, correct) {
    const response = await fetch(ANSWER_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        level: LEVEL,
        word_id: word.id,
        correct,
        replay: replayMode
      })
    });

    let result;

    try {
      result = await response.json();
    } catch {
      throw new Error("Invalid server response");
    }

    if (!response.ok || !result.ok) {
      throw new Error(
        result.error || "Could not save progress"
      );
    }

    return result;
  }

  function applyResult(word, result) {
    if (replayMode) return;

    if (result.stats) {
      stats[word.id] = {
        ...stats[word.id],
        ...result.stats
      };
    }
  }

  // ==========================================================
  // GAME COMPLETION
  // ==========================================================

  function finish(success) {
    running = false;
    ended = true;
    locked = true;
    won = success;

    clearTimeout(roundTimer);

    const levelComplete = success &&
      (replayMode
        ? remainingWords().length === 0
        : allMastered());

    gameOverTitle.textContent = levelComplete
      ? (replayMode ? "REPLAY COMPLETE!" : "LEVEL COMPLETE!")
      : "GAME OVER";

    finalScore.textContent = `Score: ${score}`;

    if (!levelComplete) {
      restartButton.textContent = "Try Again";
    } else if (replayMode) {
      restartButton.textContent = "Replay Again";
    } else if (LEVEL < TOTAL_LEVELS) {
      restartButton.textContent = "Next Level";
    } else {
      restartButton.textContent = "All Levels Complete";
    }

    gameOver.classList.remove("hidden");
  }

  // ==========================================================
  // WORD COMPLETION
  // ==========================================================

  async function completeWord() {
    locked = true;
    pending = true;

    try {
      const word = currentWord;
      const result = await saveResult(word, true);

      if (replayMode) {
        replayStreaks[word.id] =
          (replayStreaks[word.id] || 0) + 1;
      } else {
        applyResult(word, result);
      }

      score += 5;
      updateUI();

      showMessage(
        `${word.answer.toUpperCase()} ✓`,
        true
      );

      if (remainingWords().length === 0) {
        finish(true);
        return;
      }

      roundTimer = setTimeout(() => {
        if (!running) return;

        if (paused) {
          // The next round waits until the player resumes.
          return;
        }

        round++;
        startRound();
      }, 1000);

    } catch (error) {
      showMessage(error.message, false);
      finish(false);
    } finally {
      pending = false;
    }
  }

  // ==========================================================
  // LETTER COLLISION
  // ==========================================================

  async function handleLetter(item) {
    if (locked || pending) return;

    const chars = answerCharacters();
    const expected = chars[letterIndex];

    if (!expected) return;

    if (
      item.letter.toLowerCase() === expected.toLowerCase()
    ) {
      removeLetter(item);

      letterIndex++;
      advanceSeparators();

      score++;
      updateWordProgress();
      updateUI();

      showMessage(`+1 ${item.letter.toUpperCase()}`, true);

      if (letterIndex >= chars.length) {
        renderLetters();
        await completeWord();
      } else {
        ensureNextLetter();
      }

      return;
    }

    locked = true;
    pending = true;

    try {
      const result = await saveResult(currentWord, false);

      if (replayMode) {
        replayStreaks[currentWord.id] = 0;
      } else {
        applyResult(currentWord, result);
      }

      lives--;

      removeLetter(item);
      ensureNextLetter();

      showMessage(
        `WRONG — FIND ${expected.toUpperCase()}`,
        false
      );

      updateUI();

      if (lives <= 0) {
        finish(false);
      }
    } catch (error) {
      showMessage(error.message, false);
      finish(false);
    } finally {
      pending = false;

      if (running) locked = false;
    }
  }

  // ==========================================================
  // ROUND
  // ==========================================================

  function startRound() {
    if (!running || paused) return;

    clearTimeout(roundTimer);
    roundTimer = null;

    locked = true;
    letterIndex = 0;

    letters = [];
    snake = [];

    lettersLayer.replaceChildren();
    snakeLayer.replaceChildren();

    currentWord = chooseWord();

    if (!currentWord) {
      finish(true);
      return;
    }

    prompt.textContent =
      String(currentWord.english).toUpperCase();

    calculateGrid();
    createSnake();
    advanceSeparators();
    createWordProgress();

    if (!createLetters()) {
      finish(false);
      return;
    }

    renderSnake();
    updateUI();

    locked = false;
  }

  // ==========================================================
  // MOVEMENT
  // ==========================================================

  function moveSnake() {
    if (
      !running ||
      paused ||
      locked ||
      pending ||
      !snake.length
    ) {
      return;
    }

    direction = { ...nextDirection };

    const head = snake[0];

    const newHead = {
      x: (head.x + direction.x + columns) % columns,
      y: (head.y + direction.y + rows) % rows
    };

    snake.unshift(newHead);

    const item = letters.find(
      letter =>
        letter.x === newHead.x &&
        letter.y === newHead.y
    );

    if (item) {
      const expected =
        answerCharacters()[letterIndex]?.toLowerCase();

      const correct =
        item.letter.toLowerCase() === expected;

      // Grow only for a correct letter.
      // Never remove the tail a second time.
      if (!correct) {
        snake.pop();
      }

      renderSnake();
      void handleLetter(item);
    } else {
      snake.pop();
      renderSnake();
    }
  }

  function changeDirection(x, y) {
    if (!running || paused || locked || pending) return;

    if (
      direction.x === -x &&
      direction.y === -y
    ) {
      return;
    }

    nextDirection = { x, y };
  }

  // ==========================================================
  // KEYBOARD
  // ==========================================================

  document.addEventListener("keydown", event => {
    if (event.code === "Escape") {
      if (!wordsModal.classList.contains("hidden")) {
        closeWords();
      } else if (!pauseModal.classList.contains("hidden")) {
        resumeGame();
      }
      return;
    }

    const directions = {
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      KeyW: [0, -1],
      KeyS: [0, 1],
      KeyA: [-1, 0],
      KeyD: [1, 0]
    };

    const selected = directions[event.code];
    if (!selected) return;

    event.preventDefault();
    changeDirection(...selected);
  });

  // ==========================================================
  // TOUCH
  // ==========================================================

  let touchX = null;
  let touchY = null;

  board.addEventListener("touchstart", event => {
    if (!event.touches.length) return;

    touchX = event.touches[0].clientX;
    touchY = event.touches[0].clientY;
  }, { passive: true });

  board.addEventListener("touchend", event => {
    if (
      touchX === null ||
      touchY === null ||
      !event.changedTouches.length
    ) {
      return;
    }

    const dx = event.changedTouches[0].clientX - touchX;
    const dy = event.changedTouches[0].clientY - touchY;

    touchX = null;
    touchY = null;

    if (Math.max(Math.abs(dx), Math.abs(dy)) < 20) {
      return;
    }

    if (Math.abs(dx) > Math.abs(dy)) {
      changeDirection(dx > 0 ? 1 : -1, 0);
    } else {
      changeDirection(0, dy > 0 ? 1 : -1);
    }
  }, { passive: true });

  board.addEventListener("touchcancel", () => {
    touchX = null;
    touchY = null;
  });

  // ==========================================================
  // VOCABULARY
  // ==========================================================

  function renderVocabulary() {
    wordsList.replaceChildren();

    for (const word of WORDS) {
      const row = document.createElement("div");
      row.className = "vocab-row";

      const translation = document.createElement("div");

      const name = document.createElement("strong");
      name.textContent = word.answer;

      const english = document.createElement("small");
      english.textContent = word.english;

      translation.appendChild(name);
      translation.appendChild(english);

      const status = document.createElement("span");
      status.className = "vocab-status";

      if (replayMode) {
        status.textContent =
          `${replayStreaks[word.id] || 0}/${MASTERY}`;
      } else if (stats[word.id].mastered) {
        status.textContent = "✓ Mastered";
      } else {
        status.textContent =
          `${stats[word.id].recall_streak}/${MASTERY}`;
      }

      row.appendChild(translation);
      row.appendChild(status);
      wordsList.appendChild(row);
    }
  }

  function openWords() {
    if (!running || ended) return;

    paused = true;
    renderVocabulary();
    wordsModal.classList.remove("hidden");
  }

  function resumePendingRound() {
    if (
      running &&
      !paused &&
      locked &&
      !pending &&
      roundTimer
    ) {
      clearTimeout(roundTimer);
      roundTimer = null;
      round++;
      startRound();
    }
  }

  function closeWords() {
    wordsModal.classList.add("hidden");
    paused = !pauseModal.classList.contains("hidden");
    resumePendingRound();
  }

  wordsButton.addEventListener("click", openWords);
  closeWordsButton.addEventListener("click", closeWords);

  // ==========================================================
  // PAUSE
  // ==========================================================

  function pauseGame() {
    if (!running || ended) return;

    paused = true;
    pauseModal.classList.remove("hidden");
  }

  function resumeGame() {
    pauseModal.classList.add("hidden");
    paused = !wordsModal.classList.contains("hidden");
    resumePendingRound();
  }

  pauseButton.addEventListener("click", pauseGame);
  resumeButton.addEventListener("click", resumeGame);

  // ==========================================================
  // START / RESTART / NEXT LEVEL
  // ==========================================================

  function startGame() {
    clearTimeout(roundTimer);
    roundTimer = null;

    if (!WORDS.length) {
      prompt.textContent = "NO PRACTICE WORDS FOUND";
      return;
    }

    replayMode = allMastered();

    replayStreaks = {};
    for (const word of WORDS) {
      replayStreaks[word.id] = 0;
    }

    score = 0;
    lives = START_LIVES;
    round = 1;

    currentWord = null;
    letterIndex = 0;

    running = true;
    paused = false;
    locked = false;
    pending = false;
    ended = false;
    won = false;

    gameOver.classList.add("hidden");
    wordsModal.classList.add("hidden");
    pauseModal.classList.add("hidden");

    updateUI();
    startRound();

    if (!moveTimer) {
      moveTimer = setInterval(moveSnake, MOVE_INTERVAL);
    }
  }

  restartButton.addEventListener("click", () => {
    // A completed level advances to the next level.
    if (ended && won && !replayMode && allMastered()) {
      if (LEVEL < TOTAL_LEVELS) {
        window.location.assign(
          `${LEVELS_URL}?level=${LEVEL + 1}`
        );
      } else {
        window.location.assign(LEVELS_URL);
      }
      return;
    }

    // Failure retries the SAME level.
    // Replay completion replays the SAME level.
    startGame();
  });

  // ==========================================================
  // RESIZE
  // ==========================================================

  let previousWidth = board.clientWidth;
  let previousHeight = board.clientHeight;

  function handleResize() {
    const width = board.clientWidth;
    const height = board.clientHeight;

    if (
      width === previousWidth &&
      height === previousHeight
    ) {
      return;
    }

    previousWidth = width;
    previousHeight = height;

    clearTimeout(resizeTimer);

    resizeTimer = setTimeout(() => {
      if (!running || pending || paused || locked) return;

      // Preserve score, lives and saved mastery.
      // Rebuild only the unfinished word.
      letterIndex = 0;
      calculateGrid();
      createSnake();
      advanceSeparators();
      createWordProgress();

      if (!createLetters()) {
        finish(false);
        return;
      }

      renderSnake();
    }, 180);
  }

  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(handleResize).observe(board);
  } else {
    window.addEventListener("resize", handleResize);
  }

  // ==========================================================
  // INITIALIZE
  // ==========================================================

  calculateGrid();
  updateUI();
  startGame();

})();
