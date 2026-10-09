// ============================================================
// Sobra Tagalog — Sentence Practice
// sentence-practice.js
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  // ----------------------------------------------------------
  // DOM
  // ----------------------------------------------------------
  const image = document.getElementById("sentence-image");

  const tagalogText = document.getElementById("tagalog-text");
  const englishText = document.getElementById("english-text");

  const learnSection = document.getElementById("learn-section");
  const recallSection = document.getElementById("recall-section");

  const nextButton = document.getElementById("next-button");
  const checkButton = document.getElementById("check-button");

  const answerInput = document.getElementById("answer-input");

  const feedback = document.getElementById("feedback");
  const correctAnswer = document.getElementById("correct-answer");

  const masteredCount = document.getElementById("mastered-count");
  const totalCount = document.getElementById("total-count");
  const progressBar = document.getElementById("mastery-progress-bar");

  const sentenceNumber = document.getElementById("sentence-number");

  // ----------------------------------------------------------
  // State
  // ----------------------------------------------------------
  let currentSentence = null;
  let phase = "learn";
  let answerSubmitted = false;

  // ----------------------------------------------------------
  // Normalize answers
  //
  // Allows:
  // "Ang sirko ay may mga nakakatawang tao."
  // and
  // "ang sirko ay may mga nakakatawang tao"
  //
  // to match.
  // ----------------------------------------------------------
  function normalizeText(text) {
    return text
      .trim()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[.,!?;:'"“”‘’]/g, "")
      .replace(/\s+/g, " ");
  }

  // ----------------------------------------------------------
  // Escape text before inserting into HTML
  // ----------------------------------------------------------
  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // ----------------------------------------------------------
  // Update mastery display
  // ----------------------------------------------------------
  function updateMastery(mastered, total) {
    if (masteredCount) {
      masteredCount.textContent = mastered;
    }

    if (totalCount) {
      totalCount.textContent = total;
    }

    if (progressBar) {
      const percent =
        total > 0
          ? Math.min(100, Math.round((mastered / total) * 100))
          : 0;

      progressBar.style.width = `${percent}%`;
      progressBar.setAttribute("aria-valuenow", percent);
    }
  }

  // ----------------------------------------------------------
  // Display new sentence
  // ----------------------------------------------------------
  function showSentence(sentence) {
    currentSentence = sentence;
    phase = "learn";
    answerSubmitted = false;

    if (image) {
      image.src = sentence.image;
      image.alt = "";
    }

    if (tagalogText) {
      tagalogText.textContent = sentence.tagalog;
    }

    if (englishText) {
      englishText.textContent = sentence.english;
    }

    if (sentenceNumber && sentence.number) {
      sentenceNumber.textContent = sentence.number;
    }

    if (answerInput) {
      answerInput.value = "";
      answerInput.disabled = false;
      answerInput.classList.remove("correct", "wrong");
    }

    if (feedback) {
      feedback.textContent = "";
      feedback.className = "feedback";
    }

    if (correctAnswer) {
      correctAnswer.textContent = "";
      correctAnswer.classList.add("hidden");
    }

    if (learnSection) {
      learnSection.classList.remove("hidden");
    }

    if (recallSection) {
      recallSection.classList.add("hidden");
    }

    if (nextButton) {
      nextButton.textContent = "Next";
    }

    if (checkButton) {
      checkButton.disabled = false;
      checkButton.textContent = "Check";
    }
  }

  // ----------------------------------------------------------
  // Switch from LEARN → RECALL
  // ----------------------------------------------------------
  function startRecall() {
    if (!currentSentence) return;

    phase = "recall";
    answerSubmitted = false;

    if (learnSection) {
      learnSection.classList.add("hidden");
    }

    if (recallSection) {
      recallSection.classList.remove("hidden");
    }

    if (answerInput) {
      answerInput.value = "";
      answerInput.disabled = false;
      answerInput.classList.remove("correct", "wrong");

      setTimeout(() => {
        answerInput.focus();
      }, 100);
    }

    if (feedback) {
      feedback.textContent = "";
      feedback.className = "feedback";
    }

    if (correctAnswer) {
      correctAnswer.textContent = "";
      correctAnswer.classList.add("hidden");
    }

    if (checkButton) {
      checkButton.textContent = "Check";
      checkButton.disabled = false;
    }
  }

  // ----------------------------------------------------------
  // Submit answer to Flask
  // ----------------------------------------------------------
  async function submitAnswer() {
    if (!currentSentence) return;
    if (answerSubmitted) return;

    const typedAnswer = answerInput.value.trim();

    if (!typedAnswer) {
      feedback.textContent = "Type the Tagalog sentence.";
      feedback.className = "feedback warning";
      answerInput.focus();
      return;
    }

    answerSubmitted = true;
    checkButton.disabled = true;

    // Front-end comparison gives immediate feedback.
    const isCorrect =
      normalizeText(typedAnswer) ===
      normalizeText(currentSentence.tagalog);

    try {
      const response = await fetch("/sentence-answer", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },

        body: JSON.stringify({
          sentence_id: currentSentence.id,
          answer: typedAnswer
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();

      // Prefer server result if Flask returns "correct".
      const finalCorrect =
        typeof data.correct === "boolean"
          ? data.correct
          : isCorrect;

      showResult(finalCorrect, data);

    } catch (error) {
      console.error("Sentence answer error:", error);

      // Do NOT silently lose the attempt.
      // Show the result locally but warn that it was not saved.
      showResult(isCorrect, {});

      feedback.insertAdjacentHTML(
        "beforeend",
        `<div class="save-warning">
          Progress could not be saved.
        </div>`
      );
    }
  }

  // ----------------------------------------------------------
  // Correct / Wrong result
  // ----------------------------------------------------------
  function showResult(isCorrect, data) {
    if (isCorrect) {
      answerInput.classList.add("correct");
      answerInput.classList.remove("wrong");

      feedback.textContent = "✓ Correct";
      feedback.className = "feedback success";

      if (correctAnswer) {
        correctAnswer.classList.add("hidden");
      }

    } else {
      answerInput.classList.add("wrong");
      answerInput.classList.remove("correct");

      feedback.textContent = "✕ Try to remember this sentence";
      feedback.className = "feedback error";

      if (correctAnswer) {
        correctAnswer.innerHTML =
          `<span class="answer-label">Correct:</span> ` +
          escapeHtml(currentSentence.tagalog);

        correctAnswer.classList.remove("hidden");
      }
    }

    if (
      typeof data.mastered === "number" &&
      typeof data.total === "number"
    ) {
      updateMastery(data.mastered, data.total);
    }

    answerInput.disabled = true;

    checkButton.disabled = false;
    checkButton.textContent = "Next";
  }

  // ----------------------------------------------------------
  // Get next sentence
  // ----------------------------------------------------------
  async function loadNextSentence() {
    setLoading(true);

    try {
      const response = await fetch("/sentence-next");

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();

      if (data.complete) {
        showCompleteScreen(data);
        return;
      }

      if (!data.sentence) {
        throw new Error("No sentence returned.");
      }

      if (
        typeof data.mastered === "number" &&
        typeof data.total === "number"
      ) {
        updateMastery(data.mastered, data.total);
      }

      showSentence(data.sentence);

    } catch (error) {
      console.error("Unable to load sentence:", error);

      if (feedback) {
        feedback.textContent = "Unable to load the next sentence.";
        feedback.className = "feedback error";
      }

    } finally {
      setLoading(false);
    }
  }

  // ----------------------------------------------------------
  // Completed all available sentences
  // ----------------------------------------------------------
  function showCompleteScreen(data) {
    currentSentence = null;

    if (learnSection) {
      learnSection.classList.add("hidden");
    }

    if (recallSection) {
      recallSection.classList.add("hidden");
    }

    const completeScreen =
      document.getElementById("complete-screen");

    if (completeScreen) {
      completeScreen.classList.remove("hidden");
    }

    if (
      typeof data.mastered === "number" &&
      typeof data.total === "number"
    ) {
      updateMastery(data.mastered, data.total);
    }
  }

  // ----------------------------------------------------------
  // Loading state
  // ----------------------------------------------------------
  function setLoading(loading) {
    document.body.classList.toggle("loading", loading);

    if (nextButton) {
      nextButton.disabled = loading;
    }

    if (checkButton) {
      checkButton.disabled = loading;
    }
  }

  // ----------------------------------------------------------
  // Buttons
  // ----------------------------------------------------------
  if (nextButton) {
    nextButton.addEventListener("click", () => {
      if (phase === "learn") {
        startRecall();
      }
    });
  }

  if (checkButton) {
    checkButton.addEventListener("click", () => {
      if (!answerSubmitted) {
        submitAnswer();
      } else {
        loadNextSentence();
      }
    });
  }

  // ----------------------------------------------------------
  // Enter key
  // ----------------------------------------------------------
  if (answerInput) {
    answerInput.addEventListener("keydown", event => {
      if (event.key !== "Enter") return;

      event.preventDefault();

      if (!answerSubmitted) {
        submitAnswer();
      } else {
        loadNextSentence();
      }
    });
  }

  // ----------------------------------------------------------
  // Reset
  // ----------------------------------------------------------
  const resetButton =
    document.getElementById("reset-sentence-progress");

  if (resetButton) {
    resetButton.addEventListener("click", async () => {
      const confirmed = window.confirm(
        "Reset all sentence progress?\n\n" +
        "Your vocabulary and study time will not be deleted."
      );

      if (!confirmed) return;

      resetButton.disabled = true;

      try {
        const response = await fetch("/sentence-reset", {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          }
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        updateMastery(0, 100);

        window.location.reload();

      } catch (error) {
        console.error("Reset error:", error);

        alert("Could not reset sentence progress.");

        resetButton.disabled = false;
      }
    });
  }

  // ----------------------------------------------------------
  // Initial sentence
  //
  // Your Flask HTML can provide:
  //
  // window.SENTENCE_DATA = {...}
  //
  // If not provided, JS requests /sentence-next.
  // ----------------------------------------------------------
  if (window.SENTENCE_DATA) {
    const data = window.SENTENCE_DATA;

    if (
      typeof data.mastered === "number" &&
      typeof data.total === "number"
    ) {
      updateMastery(data.mastered, data.total);
    }

    if (data.sentence) {
      showSentence(data.sentence);
    } else {
      loadNextSentence();
    }

  } else {
    loadNextSentence();
  }
});