// /static/game/word-snake/word-snake.js


// --------------------------------------------------
// ELEMENTS
// --------------------------------------------------

const gameBoard =
  document.getElementById(
    "gameBoard"
  );

const lettersContainer =
  document.getElementById(
    "letters"
  );

const snakeContainer =
  document.getElementById(
    "snake"
  );

const englishPrompt =
  document.getElementById(
    "englishPrompt"
  );

const wordProgress =
  document.getElementById(
    "wordProgress"
  );

const scoreElement =
  document.getElementById(
    "score"
  );

const livesElement =
  document.getElementById(
    "lives"
  );

const roundElement =
  document.getElementById(
    "round"
  );

const message =
  document.getElementById(
    "message"
  );

const gameOverScreen =
  document.getElementById(
    "gameOver"
  );

const gameOverTitle =
  document.getElementById(
    "gameOverTitle"
  );

const finalScore =
  document.getElementById(
    "finalScore"
  );

const restartButton =
  document.getElementById(
    "restartButton"
  );


// --------------------------------------------------
// LOAD WORDS FROM FLASK
// --------------------------------------------------

const wordDataElement =
  document.getElementById(
    "wordSnakeData"
  );

let WORDS = [];

if (wordDataElement) {
  try {
    const parsedWords =
      JSON.parse(
        wordDataElement.textContent
      );

    if (
      Array.isArray(
        parsedWords
      )
    ) {
      WORDS = parsedWords;
    }

  } catch (error) {
    console.error(
      "Could not load Word Snake vocabulary:",
      error
    );
  }
}


// --------------------------------------------------
// GAME SETTINGS
// --------------------------------------------------

const CELL_SIZE = 32;

const MOVE_INTERVAL = 300;

const DISTRACTOR_COUNT = 10;


// --------------------------------------------------
// GAME STATE
// --------------------------------------------------

let score = 0;

let lives = 3;

let round = 1;

let currentWord = null;

let currentLetterIndex = 0;

let direction = {
  x: 1,
  y: 0
};

let nextDirection = {
  x: 1,
  y: 0
};

let snake = [];

let letters = [];

let gameRunning = true;

let roundLocked = false;

let moveTimer = null;


// --------------------------------------------------
// HELPERS
// --------------------------------------------------

function randomItem(array) {
  return array[
    Math.floor(
      Math.random() *
      array.length
    )
  ];
}


function randomLetter() {
  const alphabet =
    "abcdefghijklmnopqrstuvwxyz";

  return alphabet[
    Math.floor(
      Math.random() *
      alphabet.length
    )
  ];
}


function shuffle(array) {
  const copy = [...array];

  for (
    let i =
      copy.length - 1;

    i > 0;

    i--
  ) {
    const j =
      Math.floor(
        Math.random() *
        (i + 1)
      );

    [
      copy[i],
      copy[j]
    ] = [
      copy[j],
      copy[i]
    ];
  }

  return copy;
}


// --------------------------------------------------
// WORD SELECTION
// --------------------------------------------------

function chooseWord() {
  if (
    WORDS.length === 0
  ) {
    return null;
  }

  if (
    WORDS.length === 1
  ) {
    return WORDS[0];
  }

  /*
    Weak words appear more often.

    A word with more recorded mistakes
    receives a larger selection weight.
  */

  const weightedWords = [];

  WORDS.forEach(
    word => {
      const wrong =
        Number(
          word.wrong || 0
        );

      const weight =
        Math.max(
          1,
          wrong
        );

      for (
        let i = 0;
        i < weight;
        i++
      ) {
        weightedWords.push(
          word
        );
      }
    }
  );

  let nextWord;

  do {
    nextWord =
      randomItem(
        weightedWords
      );

  } while (
    currentWord &&
    WORDS.length > 1 &&
    nextWord.answer ===
      currentWord.answer
  );

  return nextWord;
}


// --------------------------------------------------
// BOARD SIZE
// --------------------------------------------------

function getBoardGrid() {
  const width =
    gameBoard.clientWidth;

  const height =
    gameBoard.clientHeight;

  return {
    columns:
      Math.max(
        8,
        Math.floor(
          width /
          CELL_SIZE
        )
      ),

    rows:
      Math.max(
        8,
        Math.floor(
          height /
          CELL_SIZE
        )
      )
  };
}


// --------------------------------------------------
// START ROUND
// --------------------------------------------------

function startRound() {
  if (
    !gameRunning
  ) {
    return;
  }

  roundLocked = false;

  currentLetterIndex = 0;

  letters = [];

  lettersContainer.innerHTML =
    "";

  snakeContainer.innerHTML =
    "";

  currentWord =
    chooseWord();

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

  createWordProgress();

  createSnake();

  createLetters();

  renderSnake();
}


// --------------------------------------------------
// WORD PROGRESS
// --------------------------------------------------

function createWordProgress() {
  wordProgress.innerHTML =
    "";

  const answer =
    String(
      currentWord.answer
    );

  for (
    let i = 0;
    i < answer.length;
    i++
  ) {
    const slot =
      document.createElement(
        "div"
      );

    slot.className =
      "word-slot";

    slot.dataset.index =
      i;

    slot.textContent =
      "";

    wordProgress.appendChild(
      slot
    );
  }
}


function updateWordProgress() {
  const answer =
    String(
      currentWord.answer
    );

  const slots =
    wordProgress
      .querySelectorAll(
        ".word-slot"
      );

  slots.forEach(
    (slot, index) => {

      if (
        index <
        currentLetterIndex
      ) {
        slot.textContent =
          answer[index]
            .toUpperCase();

        slot.classList.add(
          "filled"
        );

      } else {
        slot.textContent =
          "";

        slot.classList.remove(
          "filled"
        );
      }
    }
  );
}


// --------------------------------------------------
// SNAKE
// --------------------------------------------------

function createSnake() {
  const grid =
    getBoardGrid();

  const startX =
    Math.floor(
      grid.columns / 2
    );

  const startY =
    Math.floor(
      grid.rows / 2
    );

  snake = [
    {
      x: startX,
      y: startY
    },
    {
      x: startX - 1,
      y: startY
    },
    {
      x: startX - 2,
      y: startY
    }
  ];

  direction = {
    x: 1,
    y: 0
  };

  nextDirection = {
    x: 1,
    y: 0
  };
}


// --------------------------------------------------
// LETTER CREATION
// --------------------------------------------------

function createLetters() {
  const answer =
    String(
      currentWord.answer
    ).toLowerCase();

  /*
    Put every required letter for the word
    onto the board.

    Example:

    pupunta

    p u p u n t a

    Duplicate letters remain separate objects.
  */

  const requiredLetters =
    answer
      .split("")
      .map(
        letter => ({
          letter: letter,
          required: true
        })
      );


  /*
    Add random distractor letters.
  */

  const distractors = [];

  for (
    let i = 0;
    i < DISTRACTOR_COUNT;
    i++
  ) {
    distractors.push({
      letter:
        randomLetter(),

      required:
        false
    });
  }


  const allLetters =
    shuffle([
      ...requiredLetters,
      ...distractors
    ]);


  allLetters.forEach(
    item => {
      const position =
        findFreePosition();

      if (!position) {
        return;
      }

      letters.push({
        letter:
          item.letter,

        x:
          position.x,

        y:
          position.y,

        element:
          null
      });
    }
  );


  renderLetters();
}


// --------------------------------------------------
// FREE POSITION
// --------------------------------------------------

function findFreePosition() {
  const grid =
    getBoardGrid();

  for (
    let attempt = 0;
    attempt < 200;
    attempt++
  ) {
    const x =
      Math.floor(
        Math.random() *
        grid.columns
      );

    const y =
      Math.floor(
        Math.random() *
        grid.rows
      );

    const onSnake =
      snake.some(
        segment =>
          segment.x === x &&
          segment.y === y
      );

    const onLetter =
      letters.some(
        item =>
          item.x === x &&
          item.y === y
      );

    if (
      !onSnake &&
      !onLetter
    ) {
      return {
        x: x,
        y: y
      };
    }
  }

  return null;
}


// --------------------------------------------------
// RENDER LETTERS
// --------------------------------------------------

function renderLetters() {
  lettersContainer.innerHTML =
    "";

  letters.forEach(
    item => {
      const element =
        document.createElement(
          "div"
        );

      element.className =
        "letter";

      element.textContent =
        item.letter
          .toUpperCase();

      element.style.left =
        (
          item.x *
          CELL_SIZE +
          CELL_SIZE / 2
        ) +
        "px";

      element.style.top =
        (
          item.y *
          CELL_SIZE +
          CELL_SIZE / 2
        ) +
        "px";

      item.element =
        element;

      lettersContainer
        .appendChild(
          element
        );
    }
  );
}


// --------------------------------------------------
// RENDER SNAKE
// --------------------------------------------------

function renderSnake() {
  snakeContainer.innerHTML =
    "";

  snake.forEach(
    (segment, index) => {
      const element =
        document.createElement(
          "div"
        );

      element.className =
        "snake-segment";

      if (
        index === 0
      ) {
        element.classList.add(
          "snake-head"
        );

        element.textContent =
          "●";
      }

      element.style.left =
        (
          segment.x *
          CELL_SIZE +
          CELL_SIZE / 2
        ) +
        "px";

      element.style.top =
        (
          segment.y *
          CELL_SIZE +
          CELL_SIZE / 2
        ) +
        "px";

      snakeContainer
        .appendChild(
          element
        );
    }
  );
}


// --------------------------------------------------
// MOVE SNAKE
// --------------------------------------------------

function moveSnake() {
  if (
    !gameRunning ||
    roundLocked
  ) {
    return;
  }

  direction = {
    ...nextDirection
  };

  const grid =
    getBoardGrid();

  const head =
    snake[0];

  let newX =
    head.x +
    direction.x;

  let newY =
    head.y +
    direction.y;


  /*
    Wrap around the board.

    Leaving one side enters from
    the opposite side.
  */

  if (
    newX < 0
  ) {
    newX =
      grid.columns - 1;
  }

  if (
    newX >=
    grid.columns
  ) {
    newX = 0;
  }

  if (
    newY < 0
  ) {
    newY =
      grid.rows - 1;
  }

  if (
    newY >=
    grid.rows
  ) {
    newY = 0;
  }


  const newHead = {
    x: newX,
    y: newY
  };


  snake.unshift(
    newHead
  );


  const eatenLetter =
    letters.find(
      item =>
        item.x ===
          newHead.x &&
        item.y ===
          newHead.y
    );


  if (
    eatenLetter
  ) {
    handleLetter(
      eatenLetter
    );

  } else {
    snake.pop();
  }


  renderSnake();
}


// --------------------------------------------------
// HANDLE LETTER
// --------------------------------------------------

function handleLetter(
  item
) {
  if (
    roundLocked
  ) {
    return;
  }

  const answer =
    String(
      currentWord.answer
    ).toLowerCase();

  const expectedLetter =
    answer[
      currentLetterIndex
    ];


  if (
    item.letter
      .toLowerCase() ===
    expectedLetter
      .toLowerCase()
  ) {
    /*
      Correct letter.

      Snake grows because we do NOT
      remove the tail during this move.
    */

    score += 1;

    scoreElement.textContent =
      score;

    currentLetterIndex++;

    showMessage(
      `+1 ${item.letter.toUpperCase()}`,
      true
    );

    removeLetter(
      item
    );

    updateWordProgress();


    /*
      Entire word completed.
    */

    if (
      currentLetterIndex >=
      answer.length
    ) {
      completeWord();
    }

  } else {
    /*
      Wrong letter.

      Lose a life and remove the
      wrong letter from the board.

      The expected letter does NOT change.
    */

    lives--;

    livesElement.textContent =
      lives;

    showMessage(
      `WRONG — FIND ${expectedLetter.toUpperCase()}`,
      false
    );

    removeLetter(
      item
    );


    /*
      Because eating normally grows the snake,
      remove the tail for a wrong letter.
    */

    snake.pop();


    if (
      lives <= 0
    ) {
      endGame();
    }
  }
}


// --------------------------------------------------
// REMOVE LETTER
// --------------------------------------------------

function removeLetter(
  item
) {
  if (
    item.element
  ) {
    item.element.remove();
  }

  letters =
    letters.filter(
      letter =>
        letter !== item
    );
}


// --------------------------------------------------
// COMPLETE WORD
// --------------------------------------------------

function completeWord() {
  roundLocked = true;

  /*
    Bonus for completing the whole word.
  */

  score += 5;

  scoreElement.textContent =
    score;

  showMessage(
    `${String(
      currentWord.answer
    ).toUpperCase()} ✓`,
    true
  );


  /*
    Move to the next word.
  */

  setTimeout(
    () => {
      round++;

      roundElement.textContent =
        round;

      startRound();
    },
    1000
  );
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

  setTimeout(
    () => {
      message.className =
        "message";
    },
    700
  );
}


// --------------------------------------------------
// GAME OVER
// --------------------------------------------------

function endGame() {
  gameRunning = false;

  roundLocked = true;

  finalScore.textContent =
    score;

  gameOverTitle.textContent =
    "GAME OVER";

  gameOverScreen
    .classList
    .remove(
      "hidden"
    );
}


// --------------------------------------------------
// RESTART
// --------------------------------------------------

function restartGame() {
  score = 0;

  lives = 3;

  round = 1;

  currentWord = null;

  currentLetterIndex = 0;

  scoreElement.textContent =
    score;

  livesElement.textContent =
    lives;

  roundElement.textContent =
    round;

  gameRunning = true;

  roundLocked = false;

  gameOverScreen
    .classList
    .add(
      "hidden"
    );

  startRound();
}


// --------------------------------------------------
// KEYBOARD
// --------------------------------------------------

document.addEventListener(
  "keydown",
  event => {

    if (
      event.code ===
      "ArrowUp"
    ) {
      event.preventDefault();

      if (
        direction.y !== 1
      ) {
        nextDirection = {
          x: 0,
          y: -1
        };
      }
    }


    if (
      event.code ===
      "ArrowDown"
    ) {
      event.preventDefault();

      if (
        direction.y !== -1
      ) {
        nextDirection = {
          x: 0,
          y: 1
        };
      }
    }


    if (
      event.code ===
      "ArrowLeft"
    ) {
      event.preventDefault();

      if (
        direction.x !== 1
      ) {
        nextDirection = {
          x: -1,
          y: 0
        };
      }
    }


    if (
      event.code ===
      "ArrowRight"
    ) {
      event.preventDefault();

      if (
        direction.x !== -1
      ) {
        nextDirection = {
          x: 1,
          y: 0
        };
      }
    }
  }
);


// --------------------------------------------------
// START / RESTART
// --------------------------------------------------

restartButton.addEventListener(
  "click",
  restartGame
);


if (
  WORDS.length > 0
) {
  startRound();

  moveTimer =
    setInterval(
      moveSnake,
      MOVE_INTERVAL
    );

} else {
  englishPrompt.textContent =
    "NO PRACTICE WORDS FOUND";

  gameRunning = false;
}