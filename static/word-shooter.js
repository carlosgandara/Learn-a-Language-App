// ============================================================
// WORD SHOOTER
// Shared Daily Dose vocabulary, independent game mastery
// ============================================================

// ELEMENTS

const gameArea = document.getElementById("gameArea");
const targetsContainer = document.getElementById("targets");
const player = document.getElementById("player");
const englishPrompt = document.getElementById("englishPrompt");
const scoreElement = document.getElementById("score");
const livesElement = document.getElementById("lives");
const roundElement = document.getElementById("round");
const message = document.getElementById("message");
const gameOverScreen = document.getElementById("gameOver");
const gameOverTitle = document.getElementById("gameOverTitle");
const finalScore = document.getElementById("finalScore");
const restartButton = document.getElementById("restartButton");
const masteredCount = document.getElementById("masteredCount");
const nextLevelButton = document.getElementById("nextLevelButton");

// DATA

const WORDS = JSON.parse(
  document.getElementById("wordShooterData").textContent
);

const CONFIG = JSON.parse(
  document.getElementById("wordShooterConfig").textContent
);

// GAME STATE

let score = 0;
let lives = 3;
let round = 1;
let currentWord = null;
let playerX = 50;
let bullets = [];
let gameRunning = true;
let canShoot = true;
let roundLocked = false;
let levelComplete = false;
let lastWordId = null;

const keys = {
  left: false,
  right: false
};

// HELPERS

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

// MISSPELLING GENERATION

function replaceVowel(word) {
  const vowels = ["a", "e", "i", "o", "u"];
  const indexes = [];

  for (let i = 0; i < word.length; i++) {
    if (vowels.includes(word[i].toLowerCase())) {
      indexes.push(i);
    }
  }

  if (!indexes.length) return null;

  const index = randomItem(indexes);
  const original = word[index].toLowerCase();
  const alternatives = vowels.filter(v => v !== original);

  return (
    word.slice(0, index) +
    randomItem(alternatives) +
    word.slice(index + 1)
  );
}

function removeLetter(word) {
  if (word.length < 4) return null;

  const index = Math.floor(Math.random() * word.length);

  return word.slice(0, index) + word.slice(index + 1);
}

function duplicateLetter(word) {
  if (word.length < 3) return null;

  const index = Math.floor(Math.random() * word.length);

  return (
    word.slice(0, index) +
    word[index] +
    word.slice(index)
  );
}

function swapLetters(word) {
  if (word.length < 4) return null;

  const indexes = [];

  for (let i = 0; i < word.length - 1; i++) {
    if (word[i] !== word[i + 1]) {
      indexes.push(i);
    }
  }

  if (!indexes.length) return null;

  const index = randomItem(indexes);
  const chars = word.split("");

  [chars[index], chars[index + 1]] =
    [chars[index + 1], chars[index]];

  return chars.join("");
}

function generateDistractors(answer, count = 4) {
  const results = new Set();

  const generators = [
    replaceVowel,
    removeLetter,
    duplicateLetter,
    swapLetters
  ];

  let attempts = 0;

  while (results.size < count && attempts < 100) {
    attempts++;

    const result = randomItem(generators)(answer);

    if (!result) continue;

    if (result.toLowerCase() === answer.toLowerCase()) {
      continue;
    }

    results.add(result);
  }

  return [...results];
}

// LEVEL PROGRESS

function updateMasteredCount() {
  const count = WORDS.filter(word => word.mastered).length;

  if (masteredCount) {
    masteredCount.textContent = count;
  }

  return count;
}

function chooseWord() {
  const available = WORDS.filter(word => !word.mastered);

  if (!available.length) return null;

  const alternatives = available.filter(
    word => word.id !== lastWordId
  );

  const pool = alternatives.length ? alternatives : available;

  const weighted = [];

  pool.forEach(word => {
    const weight = Math.max(1, Number(word.wrong || 0));

    for (let i = 0; i < weight; i++) {
      weighted.push(word);
    }
  });

  return randomItem(weighted);
}

// SAVE ANSWER

async function saveWordResult(word, selectedAnswer) {
  const response = await fetch(CONFIG.answerUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      word_id: word.id,
      answer: selectedAnswer,
      level: CONFIG.level
    })
  });

  if (!response.ok) {
    throw new Error(`Could not save answer: HTTP ${response.status}`);
  }

  const data = await response.json();

  if (!data.ok) {
    throw new Error(data.error || "Answer rejected");
  }

  Object.assign(word, data.stats);

  updateMasteredCount();

  return data;
}

// ROUND

function startRound() {
  if (!gameRunning) return;

  roundLocked = false;
  targetsContainer.innerHTML = "";

  currentWord = chooseWord();

  if (!currentWord) {
    if (WORDS.length && WORDS.every(word => word.mastered)) {
      finishLevel();
    } else {
      englishPrompt.textContent = "NO PRACTICE WORDS FOUND";
      gameRunning = false;
    }
    return;
  }

  lastWordId = currentWord.id;

  englishPrompt.textContent =
    String(currentWord.english).toUpperCase();

  createTargets();
}

// TARGETS

function createTargets() {
  const answer = String(currentWord.answer);

  const distractors = generateDistractors(answer, 4);

  const choices = shuffle([
    answer,
    ...distractors
  ]);

  const positions = [
    { x: 5, y: 10 },
    { x: 40, y: 5 },
    { x: 72, y: 18 },
    { x: 18, y: 50 },
    { x: 62, y: 55 }
  ];

  choices.forEach((word, index) => {
    const target = document.createElement("div");

    target.className = "target";
    target.textContent = word;
    target.dataset.word = word;

    target.style.left = positions[index].x + "%";
    target.style.top = positions[index].y + "%";

    target.dataset.direction =
      Math.random() > 0.5 ? "1" : "-1";

    target.dataset.speed = (
      0.12 +
      Math.random() * 0.12 +
      Math.min(round, 20) * 0.008
    ).toString();

    targetsContainer.appendChild(target);
  });
}

// PLAYER

function updatePlayer() {
  const speed = 0.8;

  if (keys.left) playerX -= speed;
  if (keys.right) playerX += speed;

  playerX = Math.max(5, Math.min(95, playerX));

  player.style.left = playerX + "%";
}

// MOVING TARGETS

function moveTargets() {
  const targets = targetsContainer.querySelectorAll(".target");
  const containerWidth = targetsContainer.clientWidth;

  if (containerWidth <= 0) return;

  targets.forEach(target => {
    if (target.dataset.pixelLeft === undefined) {
      const percentLeft = parseFloat(target.style.left);
      const initialLeft = (percentLeft / 100) * containerWidth;

      target.dataset.pixelLeft = initialLeft.toString();
      target.style.left = Math.round(initialLeft) + "px";
    }

    let left = Number(target.dataset.pixelLeft);
    let direction = Number(target.dataset.direction);
    const speed = Number(target.dataset.speed);

    const pixelSpeed = (speed / 100) * containerWidth;

    left += pixelSpeed * direction;

    const targetWidth = target.offsetWidth;
    const minLeft = 1;
    const maxLeft = Math.max(1, containerWidth - targetWidth - 1);

    if (left <= minLeft) {
      left = minLeft;
      direction = 1;
    }

    if (left >= maxLeft) {
      left = maxLeft;
      direction = -1;
    }

    target.style.left = Math.round(left) + "px";
    target.dataset.pixelLeft = left.toString();
    target.dataset.direction = direction.toString();
  });
}

// SHOOTING

function shoot() {
  if (!gameRunning || !canShoot || roundLocked) return;

  canShoot = false;

  setTimeout(() => {
    canShoot = true;
  }, 180);

  const gameRect = gameArea.getBoundingClientRect();
  const playerRect = player.getBoundingClientRect();

  const bullet = document.createElement("div");
  bullet.className = "bullet";

  const x =
    playerRect.left -
    gameRect.left +
    playerRect.width / 2 -
    2.5;

  const y =
    playerRect.top -
    gameRect.top -
    12;

  bullet.style.left = x + "px";
  bullet.style.top = y + "px";

  gameArea.appendChild(bullet);

  bullets.push({
    element: bullet,
    x,
    y
  });
}

// BULLET COLLISIONS

function updateBullets() {
  for (let i = bullets.length - 1; i >= 0; i--) {
    const bullet = bullets[i];

    bullet.y -= 9;
    bullet.element.style.top = bullet.y + "px";

    const bulletRect = bullet.element.getBoundingClientRect();
    const targets = targetsContainer.querySelectorAll(".target");

    let hit = false;

    for (const target of targets) {
      const targetRect = target.getBoundingClientRect();

      if (
        bulletRect.left < targetRect.right &&
        bulletRect.right > targetRect.left &&
        bulletRect.top < targetRect.bottom &&
        bulletRect.bottom > targetRect.top
      ) {
        hit = true;
        handleHit(target);
        break;
      }
    }

    if (hit || bullet.y < 70) {
      bullet.element.remove();
      bullets.splice(i, 1);
    }
  }
}

// HIT HANDLING

async function handleHit(target) {
  if (!gameRunning || roundLocked) return;

  roundLocked = true;

  const selectedWord = target.dataset.word;
  const answer = String(currentWord.answer);

  const isCorrect =
    selectedWord.toLowerCase() === answer.toLowerCase();

  const wordBeingAnswered = currentWord;

  createExplosion(target);

  let result;

  try {
    result = await saveWordResult(
      wordBeingAnswered,
      selectedWord
    );
  } catch (error) {
    console.error("Could not save Word Shooter result:", error);

    showMessage("SAVE FAILED — TRY AGAIN", false);

    // Do not advance until progress is successfully saved.
    roundLocked = false;
    return;
  }

  if (isCorrect) {
    score += 5;

    target.classList.add("correct-hit");
    showMessage("+5 CORRECT", true);
  } else {
    score = Math.max(0, score - 2);
    lives--;

    target.classList.add("wrong-hit");
    showMessage("-2 WRONG", false);
  }

  scoreElement.textContent = score;
  livesElement.textContent = lives;

  if (result.level_complete) {
    setTimeout(finishLevel, 500);
    return;
  }

  if (lives <= 0) {
    setTimeout(endGame, 500);
    return;
  }

  setTimeout(() => {
    round++;
    roundElement.textContent = round;
    startRound();
  }, 500);
}

// EXPLOSION

function createExplosion(target) {
  const gameRect = gameArea.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();

  const explosion = document.createElement("div");
  explosion.className = "explosion";
  explosion.textContent = "💥";

  explosion.style.left = (
    targetRect.left -
    gameRect.left +
    targetRect.width / 2
  ) + "px";

  explosion.style.top = (
    targetRect.top -
    gameRect.top +
    targetRect.height / 2
  ) + "px";

  gameArea.appendChild(explosion);

  setTimeout(() => {
    explosion.remove();
  }, 450);
}

// MESSAGE

function showMessage(text, correct) {
  message.textContent = text;

  message.className = correct
    ? "message correct show"
    : "message wrong show";

  setTimeout(() => {
    message.className = "message";
  }, 700);
}

// GAME OVER

function endGame() {
  gameRunning = false;

  finalScore.textContent = score;
  gameOverTitle.textContent = "GAME OVER";

  nextLevelButton.style.display = "none";

  gameOverScreen.classList.remove("hidden");
}

// LEVEL COMPLETED

function finishLevel() {
  if (levelComplete) return;

  levelComplete = true;
  gameRunning = false;

  finalScore.textContent = score;
  gameOverTitle.textContent = "LEVEL COMPLETE!";

  restartButton.textContent = "PLAY AGAIN";

  const hasNextLevel = WORDS.length === CONFIG.total;

  if (hasNextLevel) {
    nextLevelButton.href =
      CONFIG.levelsUrl + "?level=" + (CONFIG.level + 1);

    // The server will validate whether the next level exists
    // and is unlocked.
    nextLevelButton.style.display = "inline-block";
    nextLevelButton.classList.remove("hidden");
  }

  gameOverScreen.classList.remove("hidden");
}

// RESTART

function restartGame() {
  score = 0;
  lives = 3;
  round = 1;
  playerX = 50;
  roundLocked = false;
  levelComplete = false;
  lastWordId = null;

  bullets.forEach(bullet => bullet.element.remove());
  bullets = [];

  scoreElement.textContent = score;
  livesElement.textContent = lives;
  roundElement.textContent = round;

  player.style.left = playerX + "%";

  gameRunning = true;

  gameOverScreen.classList.add("hidden");

  startRound();
}

// MAIN LOOP

function gameLoop() {
  if (gameRunning) {
    updatePlayer();
    moveTargets();
    updateBullets();
  }

  requestAnimationFrame(gameLoop);
}

// KEYBOARD

document.addEventListener("keydown", event => {
  if (event.code === "ArrowLeft") {
    event.preventDefault();
    keys.left = true;
  }

  if (event.code === "ArrowRight") {
    event.preventDefault();
    keys.right = true;
  }

  if (event.code === "Space") {
    event.preventDefault();
    shoot();
  }
});

document.addEventListener("keyup", event => {
  if (event.code === "ArrowLeft") {
    keys.left = false;
  }

  if (event.code === "ArrowRight") {
    keys.right = false;
  }
});

// START

restartButton.addEventListener("click", restartGame);

updateMasteredCount();

if (WORDS.length > 0) {
  startRound();
  gameLoop();
} else {
  englishPrompt.textContent = "NO PRACTICE WORDS FOUND";
  gameRunning = false;
}