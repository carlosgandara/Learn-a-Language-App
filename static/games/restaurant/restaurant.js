"use strict";


/* =========================================================
   RESTAURANT LEVELS

   Each shift:
   - 5 customers
   - 3 angry customers = failed shift
   - Finish all 5 = next shift
========================================================= */

const RESTAURANT_LEVELS = [

    {
        title: "Level 1 — Basic Orders",

        phrases: [
            {
                tagalog: "Gusto ko ng tubig.",
                english: "I want water.",
                pattern: "Gusto ko ng t _ b _ g.",
                missing: "ui"
            },
            {
                tagalog: "Gusto ko ng kape.",
                english: "I want coffee.",
                pattern: "Gusto ko ng k _ p _.",
                missing: "ae"
            },
            {
                tagalog: "Gusto ko ng kanin.",
                english: "I want rice.",
                pattern: "Gusto ko ng k _ n _ n.",
                missing: "ai"
            },
            {
                tagalog: "Gusto ko ng prutas.",
                english: "I want fruit.",
                pattern: "Gusto ko ng p r _ t _ s.",
                missing: "ua"
            },
            {
                tagalog: "Gusto ko ng isda.",
                english: "I want fish.",
                pattern: "Gusto ko ng _ s d _.",
                missing: "ia"
            }
        ]
    },


    {
        title: "Level 2 — Quantities",

        phrases: [
            {
                tagalog: "Gusto ko ng isang kape.",
                english: "I want one coffee.",
                pattern: "Gusto ko ng _ s _ n g kape.",
                missing: "ia"
            },
            {
                tagalog: "Gusto ko ng dalawang tubig.",
                english: "I want two waters.",
                pattern: "Gusto ko ng d _ l _ w _ n g tubig.",
                missing: "aaa"
            },
            {
                tagalog: "Gusto ko ng tatlong isda.",
                english: "I want three fish.",
                pattern: "Gusto ko ng t _ t l _ n g isda.",
                missing: "ao"
            },
            {
                tagalog: "Gusto ko ng apat na kape.",
                english: "I want four coffees.",
                pattern: "Gusto ko ng _ p _ t na kape.",
                missing: "aa"
            },
            {
                tagalog: "Gusto ko ng limang prutas.",
                english: "I want five fruits.",
                pattern: "Gusto ko ng l _ m _ n g prutas.",
                missing: "ia"
            }
        ]
    },


    {
        title: "Level 3 — Hot & Cold",

        phrases: [
            {
                tagalog: "Mainit ang kanin.",
                english: "The rice is hot.",
                pattern: "M _ i n _ t ang kanin.",
                missing: "ai"
            },
            {
                tagalog: "Malamig ang tubig.",
                english: "The water is cold.",
                pattern: "M _ l _ m _ g ang tubig.",
                missing: "aai"
            },
            {
                tagalog: "Sobrang mainit ang kanin.",
                english: "The rice is too hot.",
                pattern: "S _ b r _ n g mainit ang k _ n _ n.",
                missing: "oaai"
            },
            {
                tagalog: "Mainit ang kape.",
                english: "The coffee is hot.",
                pattern: "M _ i n _ t ang kape.",
                missing: "ai"
            },
            {
                tagalog: "Malamig ang kape.",
                english: "The coffee is cold.",
                pattern: "M _ l _ m _ g ang kape.",
                missing: "aai"
            }
        ]
    },


    {
        title: "Level 4 — Questions",

        phrases: [
            {
                tagalog: "May tubig ba?",
                english: "Is there water?",
                pattern: "May t _ b _ g ba?",
                missing: "ui"
            },
            {
                tagalog: "May kape ba?",
                english: "Is there coffee?",
                pattern: "May k _ p _ ba?",
                missing: "ae"
            },
            {
                tagalog: "May kanin ba?",
                english: "Is there rice?",
                pattern: "May k _ n _ n ba?",
                missing: "ai"
            },
            {
                tagalog: "May isda ba?",
                english: "Is there fish?",
                pattern: "May _ s d _ ba?",
                missing: "ia"
            },
            {
                tagalog: "May prutas ba?",
                english: "Is there fruit?",
                pattern: "May p r _ t _ s ba?",
                missing: "ua"
            }
        ]
    },


    {
        title: "Level 5 — Prices",

        phrases: [
            {
                tagalog: "Magkano ito?",
                english: "How much is this?",
                pattern: "M _ g k _ n _ ito?",
                missing: "aao"
            },
            {
                tagalog: "Magkano ang kape?",
                english: "How much is the coffee?",
                pattern: "M _ g k _ n _ ang kape?",
                missing: "aao"
            },
            {
                tagalog: "Magkano ang tubig?",
                english: "How much is the water?",
                pattern: "M _ g k _ n _ ang tubig?",
                missing: "aao"
            },
            {
                tagalog: "Magkano ang kanin?",
                english: "How much is the rice?",
                pattern: "M _ g k _ n _ ang kanin?",
                missing: "aao"
            },
            {
                tagalog: "Magkano ang isda?",
                english: "How much is the fish?",
                pattern: "M _ g k _ n _ ang isda?",
                missing: "aao"
            }
        ]
    }

];


const MAX_ANGRY = 3;
const MOVE_AMOUNT = 18;
const INTERACTION_DISTANCE = 115;


/* ELEMENTS */

const restaurant =
    document.getElementById("restaurant");

const player =
    document.getElementById("player");

const tables =
    Array.from(document.querySelectorAll(".table"));

const dictionaryStation =
    document.getElementById("dictionary-station");


const levelTitle =
    document.getElementById("level-title");

const servedCountElement =
    document.getElementById("served-count");

const angryCountElement =
    document.getElementById("angry-count");

const finalServedCount =
    document.getElementById("final-served-count");


const customerDialog =
    document.getElementById("customer-dialog");

const dictionaryDialog =
    document.getElementById("dictionary-dialog");

const answerDialog =
    document.getElementById("answer-dialog");

const gameOverDialog =
    document.getElementById("game-over-dialog");

const shiftCompleteDialog =
    document.getElementById("shift-complete-dialog");

const restaurantCompleteDialog =
    document.getElementById("restaurant-complete-dialog");


const customerTableName =
    document.getElementById("customer-table-name");

const customerRequest =
    document.getElementById("customer-request");

const dictionaryTagalog =
    document.getElementById("dictionary-tagalog");

const dictionaryEnglish =
    document.getElementById("dictionary-english");

const answerTableName =
    document.getElementById("answer-table-name");

const englishPrompt =
    document.getElementById("english-prompt");

const sentencePattern =
    document.getElementById("sentence-pattern");

const answerInput =
    document.getElementById("answer-input");

const answerFeedback =
    document.getElementById("answer-feedback");


/* BUTTONS */

const closeCustomerDialog =
    document.getElementById("close-customer-dialog");

const closeDictionary =
    document.getElementById("close-dictionary");

const submitAnswer =
    document.getElementById("submit-answer");

const restartGame =
    document.getElementById("restart-game");

const nextLevelButton =
    document.getElementById("next-level");

const restartRestaurant =
    document.getElementById("restart-restaurant");


/* STATE */

let currentLevelIndex = 0;
let currentTableIndex = 0;

let servedCount = 0;
let angryCount = 0;

let playerX = 450;
let playerY = 500;

let gameFinished = false;

let tableStates = [];


/* START LEVEL */

function startLevel(levelIndex) {

    currentLevelIndex = levelIndex;

    currentTableIndex = 0;

    servedCount = 0;
    angryCount = 0;

    gameFinished = false;


    const level =
        RESTAURANT_LEVELS[currentLevelIndex];


    levelTitle.textContent =
        level.title;


    tableStates = tables.map((table, index) => ({

        table: table,

        index: index,

        status: "waiting",

        requestSeen: false,

        phrase: level.phrases[index]

    }));


    tableStates.forEach(state => {

        state.table.classList.remove(
            "active",
            "served",
            "angry"
        );

        const customer =
            state.table.querySelector(".customer");

        customer.textContent = "🙂";

    });


    hideAllModals();

    updateScore();

    resetPlayer();

    activateTable(0);
}


/* PLAYER */

function resetPlayer() {

    playerX =
        restaurant.clientWidth / 2 -
        player.offsetWidth / 2;

    playerY =
        restaurant.clientHeight -
        player.offsetHeight -
        20;

    updatePlayerPosition();
}


function updatePlayerPosition() {

    player.style.left =
        `${Math.round(playerX)}px`;

    player.style.top =
        `${Math.round(playerY)}px`;
}


function movePlayer(dx, dy) {

    if (gameFinished) {
        return;
    }


    const maxX =
        restaurant.clientWidth -
        player.offsetWidth;

    const maxY =
        restaurant.clientHeight -
        player.offsetHeight;


    playerX += dx;
    playerY += dy;


    playerX =
        Math.max(
            0,
            Math.min(playerX, maxX)
        );

    playerY =
        Math.max(
            0,
            Math.min(playerY, maxY)
        );


    updatePlayerPosition();
}


/* TABLE */

function activateTable(index) {

    if (index >= tableStates.length) {

        finishShift();

        return;
    }


    currentTableIndex = index;


    const state =
        tableStates[index];


    state.status = "active";

    state.table.classList.add("active");
}


/* KEYBOARD */

document.addEventListener("keydown", event => {

    if (!answerDialog.classList.contains("hidden")) {

        if (event.key === "Enter") {

            event.preventDefault();

            checkAnswer();
        }

        return;
    }


    if (isModalOpen()) {
        return;
    }


    switch (event.key) {

        case "ArrowUp":

            event.preventDefault();

            movePlayer(
                0,
                -MOVE_AMOUNT
            );

            break;


        case "ArrowDown":

            event.preventDefault();

            movePlayer(
                0,
                MOVE_AMOUNT
            );

            break;


        case "ArrowLeft":

            event.preventDefault();

            movePlayer(
                -MOVE_AMOUNT,
                0
            );

            break;


        case "ArrowRight":

            event.preventDefault();

            movePlayer(
                MOVE_AMOUNT,
                0
            );

            break;


        case "Enter":

            event.preventDefault();

            interact();

            break;
    }

});


/* DISTANCE */

function getCenter(element) {

    const restaurantRect =
        restaurant.getBoundingClientRect();

    const rect =
        element.getBoundingClientRect();


    return {

        x:
            rect.left -
            restaurantRect.left +
            rect.width / 2,

        y:
            rect.top -
            restaurantRect.top +
            rect.height / 2
    };
}


function getPlayerCenter() {

    return {

        x:
            playerX +
            player.offsetWidth / 2,

        y:
            playerY +
            player.offsetHeight / 2
    };
}


function getDistance(a, b) {

    const dx = a.x - b.x;
    const dy = a.y - b.y;

    return Math.sqrt(
        dx * dx +
        dy * dy
    );
}


/* INTERACTION */

function interact() {

    const playerCenter =
        getPlayerCenter();


    /* DICTIONARY */

    const dictionaryDistance =
        getDistance(
            playerCenter,
            getCenter(dictionaryStation)
        );


    if (
        dictionaryDistance <=
        INTERACTION_DISTANCE
    ) {

        openDictionary();

        return;
    }


    /* ACTIVE TABLE */

    const state =
        tableStates[currentTableIndex];


    if (!state) {
        return;
    }


    const tableDistance =
        getDistance(
            playerCenter,
            getCenter(state.table)
        );


    if (
        tableDistance <=
        INTERACTION_DISTANCE
    ) {

        interactWithTable(state);
    }
}


/* CUSTOMER */

function interactWithTable(state) {

    if (state.status !== "active") {
        return;
    }


    if (!state.requestSeen) {

        state.requestSeen = true;


        customerTableName.textContent =
            `Table ${state.index + 1}`;

        customerRequest.textContent =
            state.phrase.tagalog;


        showModal(customerDialog);

        return;
    }


    showAnswer(state);
}


/* DICTIONARY */

function openDictionary() {

    const state =
        tableStates[currentTableIndex];


    if (
        !state ||
        !state.requestSeen ||
        state.status !== "active"
    ) {
        return;
    }


    dictionaryTagalog.textContent =
        state.phrase.tagalog;

    dictionaryEnglish.textContent =
        state.phrase.english;


    showModal(dictionaryDialog);
}


/* ANSWER */

function showAnswer(state) {

    answerTableName.textContent =
        `Table ${state.index + 1}`;

    englishPrompt.textContent =
        state.phrase.english;

    sentencePattern.textContent =
        state.phrase.pattern;


    answerInput.value = "";

    answerFeedback.textContent = "";

    answerFeedback.className =
        "answer-feedback";


    showModal(answerDialog);


    setTimeout(() => {

        answerInput.focus();

    }, 50);
}


function normalize(value) {

    return value
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "");
}


function checkAnswer() {

    const state =
        tableStates[currentTableIndex];


    if (!state) {
        return;
    }


    const answer =
        normalize(answerInput.value);

    const correct =
        normalize(state.phrase.missing);


    if (!answer) {

        answerFeedback.textContent =
            "Type the missing letters.";

        return;
    }


    if (answer === correct) {

        correctAnswer(state);

    } else {

        wrongAnswer(state);
    }
}


/* CORRECT */

function correctAnswer(state) {

    state.status = "served";

    state.table.classList.remove("active");
    state.table.classList.add("served");


    state.table.querySelector(
        ".customer"
    ).textContent = "😊";


    servedCount++;

    updateScore();


    answerFeedback.textContent =
        `${state.phrase.tagalog} ✓`;

    answerFeedback.className =
        "answer-feedback correct";


    setTimeout(() => {

        hideModal(answerDialog);

        nextTable();

    }, 850);
}


/* WRONG */

function wrongAnswer(state) {

    state.status = "angry";

    state.table.classList.remove("active");
    state.table.classList.add("angry");


    state.table.querySelector(
        ".customer"
    ).textContent = "😠";


    angryCount++;

    updateScore();


    answerFeedback.textContent =
        `${state.phrase.tagalog} ✗`;

    answerFeedback.className =
        "answer-feedback wrong";


    setTimeout(() => {

        hideModal(answerDialog);


        if (angryCount >= MAX_ANGRY) {

            failShift();

        } else {

            nextTable();
        }

    }, 1000);
}


/* NEXT CUSTOMER */

function nextTable() {

    currentTableIndex++;


    if (
        currentTableIndex >=
        tableStates.length
    ) {

        finishShift();

        return;
    }


    activateTable(
        currentTableIndex
    );
}


/* SCORE */

function updateScore() {

    servedCountElement.textContent =
        servedCount;

    angryCountElement.textContent =
        angryCount;
}


/* FAIL */

function failShift() {

    gameFinished = true;

    showModal(gameOverDialog);
}


/* COMPLETE SHIFT */

function finishShift() {

    gameFinished = true;

    finalServedCount.textContent =
        servedCount;

    showModal(
        shiftCompleteDialog
    );
}


/* NEXT LEVEL */

function goToNextLevel() {

    hideModal(
        shiftCompleteDialog
    );


    const next =
        currentLevelIndex + 1;


    if (
        next >=
        RESTAURANT_LEVELS.length
    ) {

        showModal(
            restaurantCompleteDialog
        );

        return;
    }


    startLevel(next);
}


/* MODALS */

function showModal(element) {

    element.classList.remove("hidden");
}


function hideModal(element) {

    element.classList.add("hidden");
}


function hideAllModals() {

    [
        customerDialog,
        dictionaryDialog,
        answerDialog,
        gameOverDialog,
        shiftCompleteDialog,
        restaurantCompleteDialog

    ].forEach(hideModal);
}


function isModalOpen() {

    return [

        customerDialog,
        dictionaryDialog,
        gameOverDialog,
        shiftCompleteDialog,
        restaurantCompleteDialog

    ].some(
        modal =>
            !modal.classList.contains("hidden")
    );
}


/* BUTTONS */

closeCustomerDialog.addEventListener(
    "click",
    () => hideModal(customerDialog)
);


closeDictionary.addEventListener(
    "click",
    () => hideModal(dictionaryDialog)
);


submitAnswer.addEventListener(
    "click",
    checkAnswer
);


restartGame.addEventListener(
    "click",
    () => startLevel(currentLevelIndex)
);


nextLevelButton.addEventListener(
    "click",
    goToNextLevel
);


restartRestaurant.addEventListener(
    "click",
    () => startLevel(0)
);


/* START */

startLevel(0);