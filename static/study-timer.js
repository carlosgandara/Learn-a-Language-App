let activeSeconds = 0;
let lastActivity = Date.now();

const IDLE_LIMIT = 60 * 1000;

function markActive() {
  lastActivity = Date.now();
}

["mousemove", "keydown", "click", "touchstart"].forEach(event => {
  document.addEventListener(event, markActive, { passive: true });
});

setInterval(() => {
  const visible = document.visibilityState === "visible";
  const recentlyActive = Date.now() - lastActivity < IDLE_LIMIT;

  if (visible && recentlyActive) {
    activeSeconds++;
  }
}, 1000);


async function saveStudyTime() {
  if (activeSeconds === 0) return;

  const seconds = activeSeconds;
  activeSeconds = 0;

  try {
    await fetch("/study-time", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ seconds })
    });
  } catch (err) {
    activeSeconds += seconds;
  }
}


setInterval(saveStudyTime, 30000);

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    saveStudyTime();
  }
});

window.addEventListener("beforeunload", () => {
  if (activeSeconds > 0) {
    navigator.sendBeacon(
      "/study-time",
      new Blob(
        [JSON.stringify({ seconds: activeSeconds })],
        { type: "application/json" }
      )
    );
  }
});