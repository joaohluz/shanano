// app.js — mic lifecycle, fetch to /match/, render result/errors.

import { startRecording } from "./audio.js";

const recordBtn = document.getElementById("record-btn");
const durationSelect = document.getElementById("duration");
const statusLine = document.getElementById("status");
const errorArea = document.getElementById("error");
const resultCard = document.getElementById("result");

let state = "idle"; // idle | recording | matching
let recording = null;

function setState(next) {
  state = next;
  recordBtn.textContent = next === "recording" ? "Stop" : "Record";
  recordBtn.disabled = next === "matching";
  durationSelect.disabled = next !== "idle";
}

function setStatus(text) {
  statusLine.textContent = text;
}

function showError(message) {
  errorArea.textContent = message;
  errorArea.hidden = false;
}

function clearError() {
  errorArea.hidden = true;
}

function hideResult() {
  resultCard.hidden = true;
}

function renderResult(result) {
  const cover = document.getElementById("result-cover");
  const coverFallback = document.getElementById("result-cover-fallback");

  if (result.cover_art_url) {
    cover.src = result.cover_art_url;
    cover.hidden = false;
    coverFallback.hidden = true;
    cover.onload = () => {
      cover.hidden = false;
      coverFallback.hidden = true;
    };
    cover.onerror = () => {
      cover.hidden = true;
      coverFallback.hidden = false;
    };
  } else {
    cover.hidden = true;
    coverFallback.hidden = false;
  }

  document.getElementById("result-title").textContent = result.song_name;
  document.getElementById("result-artist").textContent =
    [result.artist, result.album, result.year].filter(Boolean).join(" · ");
  document.getElementById("result-genre").textContent = result.genre || "";

  const score = result.score;
  const confidence = result.confidence != null
    ? Math.round(result.confidence * 100)
    : "";
  document.getElementById("result-score").textContent =
    confidence === "" ? `score ${score}` : `score ${score} · ${confidence}% confidence`;

  const sourceLink = document.getElementById("result-source");
  if (result.source_url) {
    sourceLink.href = result.source_url;
    sourceLink.hidden = false;
  } else {
    sourceLink.hidden = true;
  }

  resultCard.hidden = false;
}

function resetAfterFailure() {
  setState("idle");
  setStatus("");
  recording = null;
}

async function matchWav(wavBlob) {
  const formData = new FormData();
  formData.append("file", wavBlob, "query.wav");

  let response;
  try {
    response = await fetch("/match/", { method: "POST", body: formData });
  } catch (error) {
    showError("Could not reach the server.");
    resetAfterFailure();
    return;
  }

  if (!response.ok) {
    if (response.status === 404) {
      showError("No match found.");
    } else if (response.status === 400) {
      showError("Could not decode that recording (or unsupported format).");
    } else {
      showError(`Server error (${response.status}).`);
    }
    resetAfterFailure();
    return;
  }

  const result = await response.json();
  renderResult(result);
  setState("idle");
  setStatus("");
  recording = null;
}

async function beginRecording() {
  const duration = parseInt(durationSelect.value, 10);
  clearError();
  hideResult();
  setState("recording");
  setStatus(`Recording… ${duration}s`);

  try {
    const { stop, done } = await startRecording({
      durationSeconds: duration,
      onTick: (remaining) => {
        setStatus(remaining > 0 ? `Recording… ${remaining}s` : "Finishing…");
      },
    });
    recording = { stop };

    const wavBlob = await done;
    recording = null;
    setState("matching");
    setStatus("Matching…");
    await matchWav(wavBlob);
  } catch (error) {
    if (error && (error.name === "NotAllowedError" || error.name === "SecurityError")) {
      showError("Microphone permission is required to record.");
    } else {
      showError("Could not decode that recording (or unsupported format).");
    }
    resetAfterFailure();
  }
}

recordBtn.addEventListener("click", () => {
  if (state === "recording" && recording) {
    recording.stop();
  } else if (state === "idle") {
    beginRecording();
  }
});
