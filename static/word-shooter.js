// /static/word-shooter.js


// --------------------------------------------------
// ELEMENTS
// --------------------------------------------------

const gameArea = document.getElementById("gameArea");

const targetsContainer = document.getElementById("targets");

const player = document.getElementById("player");

const englishPrompt = document.getElementById("englishPrompt");

const scoreElement = document.getElementById("score");

const livesElement = document.getElementById("lives");

const roundElement = document.getElementById("round");

const message = document.getElementById("message");

const gameOverScreen = document.getElementById("gameOver");

const finalScore = document.getElementById("finalScore");

const restartButton = document.getElementById("restartButton");


// --------------------------------------------------
// LOAD WORDS FROM FLASK
// --------------------------------------------------

const wordDataElement = document.getElementById("wordShooterData");

let WORDS = [];

if (wordDataElement) {
  try {
    const parsedWords = JSON.parse(wordDataElement.textContent);

    if (Array.isArray(parsedWords)) {
      WORDS = parsedWords;
    }
  } catch (error) {
    console.error(
      "Could not load Word Shooter vocabulary:",
      error
    );
  }
}


// --------------------------------------------------
// GAME STATE
// --------------------------------------------------

let score = 0;

let lives = 3;

let round = 1;

let currentWord = null;

let playerX = 50;

let bullets = [];

let gameRunning = true;

let canShoot = true;

/*
  Once a target is hit, this becomes true.

  That prevents multiple bullets from recording
  multiple correct/wrong answers for one round.
*/
let roundLocked = false;


const keys = {
  left: false,
  right: false
};


// --------------------------------------------------
// GENERAL HELPERS
// --------------------------------------------------

function shuffle(array) {
  const copy = [...array];

  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(
      Math.random() * (i + 1)
    );

    [copy[i], copy[j]] = [
      copy[j],
      copy[i]
    ];
  }

  return copy;
}


function randomItem(array) {
  return array[
    Math.floor(Math.random() * array.length)
  ];
}


// --------------------------------------------------
// AUTOMATIC MISSPELLING GENERATION
// --------------------------------------------------

function replaceVowel(word) {
  const vowels = [
    "a",
    "e",
    "i",
    "o",
    "u"
  ];

  const indexes = [];

  for (let i = 0; i < word.length; i++) {
    if (
      vowels.includes(
        word[i].toLowerCase()
      )
    ) {
      indexes.push(i);
    }
  }

  if (indexes.length === 0) {
    return null;
  }

  const index =
    randomItem(indexes);

  const original =
    word[index].toLowerCase();

  const alternatives =
    vowels.filter(
      vowel => vowel !== original
    );

  const replacement =
    randomItem(alternatives);

  return (
    word.slice(0, index) +
    replacement +
    word.slice(index + 1)
  );
}


function removeLetter(word) {
  if (word.length < 4) {
    return null;
  }

  const index =
    Math.floor(
      Math.random() * word.length
    );

  return (
    word.slice(0, index) +
    word.slice(index + 1)
  );
}


function duplicateLetter(word) {
  if (word.length < 3) {
    return null;
  }

  const index =
    Math.floor(
      Math.random() * word.length
    );

  return (
    word.slice(0, index) +
    word[index] +
    word.slice(index)
  );
}


function swapLetters(word) {
  if (word.length < 4) {
    return null;
  }

  const possibleIndexes = [];

  for (
    let i = 0;
    i < word.length - 1;
    i++
  ) {
    if (
      word[i] !==
      word[i + 1]
    ) {
      possibleIndexes.push(i);
    }
  }

  if (
    possibleIndexes.length === 0
  ) {
    return null;
  }

  const index =
    randomItem(possibleIndexes);

  const chars =
    word.split("");

  [
    chars[index],
    chars[index + 1]
  ] = [
    chars[index + 1],
    chars[index]
  ];

  return chars.join("");
}


function generateDistractors(
  answer,
  count = 4
) {
  const results = new Set();

  const generators = [
    replaceVowel,
    removeLetter,
    duplicateLetter,
    swapLetters
  ];

  let attempts = 0;

  while (
    results.size < count &&
    attempts < 100
  ) {
    attempts++;

    const generator =
      randomItem(generators);

    const result =
      generator(answer);

    if (!result) {
      continue;
    }

    if (
      result.toLowerCase() ===
      answer.toLowerCase()
    ) {
      continue;
    }

    results.add(result);
  }

  return Array.from(results);
}


// --------------------------------------------------
// WORD SELECTION
// --------------------------------------------------

function chooseWord() {
  if (WORDS.length === 0) {
    return null;
  }

  if (WORDS.length === 1) {
    return WORDS[0];
  }

  /*
    Words with more wrong answers get
    a higher chance of appearing.

    Minimum weight is 1.
  */
  const weightedWords = [];

  WORDS.forEach(word => {
    const wrong =
      Number(word.wrong || 0);

    const weight =
      Math.max(1, wrong);

    for (
      let i = 0;
      i < weight;
      i++
    ) {
      weightedWords.push(word);
    }
  });

  let nextWord;

  do {
    nextWord =
      randomItem(weightedWords);

  } while (
    currentWord &&
    nextWord.answer ===
      currentWord.answer
  );

  return nextWord;
}


// --------------------------------------------------
// SAVE RESULT TO PROGRESS.JSON
// --------------------------------------------------

async function saveWordResult(
  word,
  correct
) {
  try {
    const response =
      await fetch(
        "/word-shooter-answer",
        {
          method: "POST",

          headers: {
            "Content-Type":
              "application/json"
          },

          body: JSON.stringify({
            word: word,
            correct: correct
          })
        }
      );

    if (!response.ok) {
      throw new Error(
        `HTTP ${response.status}`
      );
    }

    const data =
      await response.json();

    /*
      Keep the browser's copy of the word stats
      synchronized with progress.json.
    */
    const localWord =
      WORDS.find(
        item =>
          item.answer === word
      );

    if (localWord) {
      localWord.correct =
        data.correct;

      localWord.wrong =
        data.wrong;

      localWord.wrong_streak =
        data.wrong_streak;
    }

  } catch (error) {
    console.error(
      "Could not save Word Shooter result:",
      error
    );
  }
}


// --------------------------------------------------
// ROUND
// --------------------------------------------------

function startRound() {
  if (!gameRunning) {
    return;
  }

  /*
    New word = allow one new answer.
  */
  roundLocked = false;

  targetsContainer.innerHTML = "";

  currentWord = chooseWord();

  if (!currentWord) {
    englishPrompt.textContent =
      "NO PRACTICE WORDS FOUND";

    gameRunning = false;

    return;
  }

  englishPrompt.textContent =
    String(
      currentWord.english
    ).toUpperCase();

  createTargets();
}


// --------------------------------------------------
// TARGETS
// --------------------------------------------------

function createTargets() {
  const answer =
    String(currentWord.answer);

  const distractors =
    generateDistractors(
      answer,
      4
    );

  const choices =
    shuffle([
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

  choices.forEach(
    (word, index) => {

      const target =
        document.createElement(
          "div"
        );

      target.className =
        "target";

      target.textContent =
        word;

      target.dataset.word =
        word;

      target.style.left =
        positions[index].x +
        "%";

      target.style.top =
        positions[index].y +
        "%";

      target.dataset.direction =
        Math.random() > 0.5
          ? "1"
          : "-1";

      target.dataset.speed =
        (
          0.12 +
          Math.random() * 0.12 +
          Math.min(
            round,
            20
          ) * 0.008
        ).toString();

      targetsContainer.appendChild(
        target
      );
    }
  );
}


// --------------------------------------------------
// PLAYER
// --------------------------------------------------

function updatePlayer() {
  const speed = 0.8;

  if (keys.left) {
    playerX -= speed;
  }

  if (keys.right) {
    playerX += speed;
  }

  playerX =
    Math.max(
      5,
      Math.min(
        95,
        playerX
      )
    );

  player.style.left =
    playerX + "%";
}


// --------------------------------------------------
// MOVING WORD TARGETS
// --------------------------------------------------

function moveTargets() {
  const targets =
    document.querySelectorAll(
      ".target"
    );

  const containerWidth =
    targetsContainer.clientWidth;

  if (
    containerWidth <= 0
  ) {
    return;
  }

  targets.forEach(
    target => {

      /*
        Convert the initial percentage position
        to pixels the first time this target moves.
      */
      if (
        target.dataset.pixelLeft === undefined
      ) {
        const percentLeft =
          parseFloat(
            target.style.left
          );

        const initialLeft =
          (
            percentLeft / 100
          ) * containerWidth;

        target.dataset.pixelLeft =
          initialLeft.toString();

        target.style.left =
          Math.round(initialLeft) + "px";
      }


      let left =
        Number(
          target.dataset.pixelLeft
        );

      let direction =
        Number(
          target.dataset.direction
        );

      const speed =
        Number(
          target.dataset.speed
        );


      /*
        Original speed was percentage-based.

        Convert it to approximately the same
        visual speed in pixels.
      */
      const pixelSpeed =
        (
          speed / 100
        ) * containerWidth;


      left +=
        pixelSpeed * direction;


      const targetWidth =
        target.offsetWidth;

      const minLeft = 1;

      const maxLeft =
        containerWidth -
        targetWidth -
        1;


      if (
        left <= minLeft
      ) {
        left = minLeft;
        direction = 1;
      }


      if (
        left >= maxLeft
      ) {
        left = maxLeft;
        direction = -1;
      }


      /*
        IMPORTANT:
        Render on whole pixels.

        This helps prevent moving text from
        being rendered on fractional pixels.
      */
      target.style.left =
        Math.round(left) + "px";


      /*
        Keep the precise position internally
        so movement remains smooth.
      */
      target.dataset.pixelLeft =
        left.toString();


      target.dataset.direction =
        direction.toString();
    }
  );
}


// --------------------------------------------------
// SHOOTING
// --------------------------------------------------

function shoot() {
  if (
    !gameRunning ||
    !canShoot ||
    roundLocked
  ) {
    return;
  }

  canShoot = false;

  setTimeout(() => {
    canShoot = true;
  }, 180);

  const gameRect =
    gameArea.getBoundingClientRect();

  const playerRect =
    player.getBoundingClientRect();

  const bullet =
    document.createElement(
      "div"
    );

  bullet.className =
    "bullet";

  const x =
    playerRect.left -
    gameRect.left +
    playerRect.width / 2 -
    2.5;

  const y =
    playerRect.top -
    gameRect.top -
    12;

  bullet.style.left =
    x + "px";

  bullet.style.top =
    y + "px";

  gameArea.appendChild(
    bullet
  );

  bullets.push({
    element: bullet,
    x: x,
    y: y
  });
}


// --------------------------------------------------
// BULLETS
// --------------------------------------------------

function updateBullets() {
  for (
    let i =
      bullets.length - 1;

    i >= 0;

    i--
  ) {
    const bullet =
      bullets[i];

    bullet.y -= 9;

    bullet.element.style.top =
      bullet.y + "px";

    const bulletRect =
      bullet.element
        .getBoundingClientRect();

    const targets =
      document.querySelectorAll(
        ".target"
      );

    let hit = false;

    for (
      const target
      of targets
    ) {
      const targetRect =
        target
          .getBoundingClientRect();

      if (
        bulletRect.left <
          targetRect.right &&

        bulletRect.right >
          targetRect.left &&

        bulletRect.top <
          targetRect.bottom &&

        bulletRect.bottom >
          targetRect.top
      ) {
        hit = true;

        handleHit(
          target
        );

        break;
      }
    }

    if (
      hit ||
      bullet.y < 70
    ) {
      bullet.element.remove();

      bullets.splice(
        i,
        1
      );
    }
  }
}


// --------------------------------------------------
// TARGET HIT
// --------------------------------------------------

function handleHit(target) {
  if (
    !gameRunning ||
    roundLocked
  ) {
    return;
  }

  /*
    IMPORTANT:

    First target hit ends the round.

    This guarantees that one displayed word
    creates exactly one update in progress.json.
  */
  roundLocked = true;

  const selectedWord =
    target.dataset.word;

  const answer =
    String(
      currentWord.answer
    );

  const isCorrect =
    selectedWord
      .toLowerCase() ===
    answer
      .toLowerCase();

  createExplosion(
    target
  );

  /*
    Save the result.

    CORRECT:
      correct + 1
      wrong_streak = 0

    WRONG:
      wrong + 1
      wrong_streak + 1
  */
  saveWordResult(
    answer,
    isCorrect
  );

  if (isCorrect) {
    score += 5;

    target.classList.add(
      "correct-hit"
    );

    showMessage(
      "+5 CORRECT",
      true
    );

    scoreElement.textContent =
      score;

  } else {
    score =
      Math.max(
        0,
        score - 2
      );

    lives--;

    target.classList.add(
      "wrong-hit"
    );

    showMessage(
      "-2 WRONG",
      false
    );

    scoreElement.textContent =
      score;

    livesElement.textContent =
      lives;
  }

  /*
    If no lives remain, finish the game.
  */
  if (lives <= 0) {
    setTimeout(
      endGame,
      500
    );

    return;
  }

  /*
    Otherwise move to the next word.
  */
  setTimeout(
    () => {
      round++;

      roundElement.textContent =
        round;

      startRound();
    },
    500
  );
}


// --------------------------------------------------
// EXPLOSION
// --------------------------------------------------

function createExplosion(
  target
) {
  const gameRect =
    gameArea
      .getBoundingClientRect();

  const targetRect =
    target
      .getBoundingClientRect();

  const explosion =
    document.createElement(
      "div"
    );

  explosion.className =
    "explosion";

  explosion.textContent =
    "💥";

  explosion.style.left =
    (
      targetRect.left -
      gameRect.left +
      targetRect.width / 2
    ) + "px";

  explosion.style.top =
    (
      targetRect.top -
      gameRect.top +
      targetRect.height / 2
    ) + "px";

  gameArea.appendChild(
    explosion
  );

  setTimeout(() => {
    explosion.remove();
  }, 450);
}


// --------------------------------------------------
// MESSAGE
// --------------------------------------------------

function showMessage(
  text,
  correct
) {
  message.textContent =
    text;

  message.className =
    correct
      ? "message correct show"
      : "message wrong show";

  setTimeout(() => {
    message.className =
      "message";
  }, 700);
}


// --------------------------------------------------
// GAME OVER
// --------------------------------------------------

function endGame() {
  gameRunning = false;

  finalScore.textContent =
    score;

  gameOverScreen
    .classList
    .remove("hidden");
}


// --------------------------------------------------
// RESTART
// --------------------------------------------------

function restartGame() {
  score = 0;

  lives = 3;

  round = 1;

  playerX = 50;

  roundLocked = false;

  bullets.forEach(
    bullet => {
      bullet.element.remove();
    }
  );

  bullets = [];

  scoreElement.textContent =
    score;

  livesElement.textContent =
    lives;

  roundElement.textContent =
    round;

  player.style.left =
    playerX + "%";

  gameRunning = true;

  gameOverScreen
    .classList
    .add("hidden");

  startRound();
}


// --------------------------------------------------
// MAIN GAME LOOP
// --------------------------------------------------

function gameLoop() {
  if (gameRunning) {
    updatePlayer();

    moveTargets();

    updateBullets();
  }

  requestAnimationFrame(
    gameLoop
  );
}


// --------------------------------------------------
// KEYBOARD
// --------------------------------------------------

document.addEventListener(
  "keydown",
  event => {

    if (
      event.code ===
      "ArrowLeft"
    ) {
      event.preventDefault();

      keys.left = true;
    }

    if (
      event.code ===
      "ArrowRight"
    ) {
      event.preventDefault();

      keys.right = true;
    }

    if (
      event.code ===
      "Space"
    ) {
      event.preventDefault();

      shoot();
    }
  }
);


document.addEventListener(
  "keyup",
  event => {

    if (
      event.code ===
      "ArrowLeft"
    ) {
      keys.left = false;
    }

    if (
      event.code ===
      "ArrowRight"
    ) {
      keys.right = false;
    }
  }
);


// --------------------------------------------------
// START
// --------------------------------------------------

restartButton.addEventListener(
  "click",
  restartGame
);


if (WORDS.length > 0) {
  startRound();

  gameLoop();

} else {
  englishPrompt.textContent =
    "NO PRACTICE WORDS FOUND";

  gameRunning = false;
}