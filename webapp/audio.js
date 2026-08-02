// audio.js — MediaRecorder capture + decode + WAV encoding (no build step).

export function encodeWav(samples, sampleRate) {
  // Standard 44-byte-header PCM WAV: mono, 16-bit, little-endian.
  const bytesPerSample = 2;
  const dataLength = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataLength);
  const view = new DataView(buffer);

  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + dataLength, true);
  writeString(view, 8, "WAVE");

  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);            // fmt chunk size
  view.setUint16(20, 1, true);             // audioFormat: PCM
  view.setUint16(22, 1, true);             // channels: mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true); // byteRate
  view.setUint16(32, bytesPerSample, true);              // blockAlign
  view.setUint16(34, 16, true);            // bitsPerSample

  writeString(view, 36, "data");
  view.setUint32(40, dataLength, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += bytesPerSample) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, clamped * 0x7fff, true);
  }

  return new Blob([buffer], { type: "audio/wav" });
}

function writeString(view, offset, str) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
}

/**
 * Record `durationSeconds` from the mic, decode to PCM, and return a WAV Blob.
 * Returns `{ stop, done }` — call `stop()` to end early (or wait out the
 * duration); `done` resolves with the WAV Blob once recording has stopped.
 * Rejects with the DOM exception when the mic is denied and with the decode
 * error when the recorded audio cannot be decoded.
 */
export async function startRecording({ durationSeconds, onTick }) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

  const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? "audio/webm;codecs=opus"
    : "";
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

  const chunks = [];
  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  };

  let finished = false;
  let resolveDone;
  let rejectDone;
  const done = new Promise((resolve, reject) => {
    resolveDone = resolve;
    rejectDone = reject;
  });

  recorder.onstop = async () => {
    stream.getTracks().forEach((track) => track.stop());
    try {
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      const arrayBuffer = await blob.arrayBuffer();
      // Decode with an OfflineAudioContext. A normal AudioContext created
      // inside onstop (after the button-click gesture has expired) starts in
      // "suspended" state under the autoplay policy, and resume() there never
      // resolves — leaving the UI stuck on "Finishing…". OfflineAudioContext
      // has no audio output and no autoplay policy, so decodeAudioData always
      // settles.
      const OfflineCtx =
        window.OfflineAudioContext || window.webkitOfflineAudioContext;
      const audioCtx = new OfflineCtx(1, 1, 22050);
      const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
      const mono = new Float32Array(audioBuffer.length);
      for (let ch = 0; ch < audioBuffer.numberOfChannels; ch++) {
        const data = audioBuffer.getChannelData(ch);
        for (let i = 0; i < mono.length; i++) mono[i] += data[i];
      }
      if (audioBuffer.numberOfChannels > 1) {
        for (let i = 0; i < mono.length; i++) mono[i] /= audioBuffer.numberOfChannels;
      }
      resolveDone(await encodeWav(mono, audioBuffer.sampleRate));
    } catch (error) {
      rejectDone(error);
    }
  };

  let elapsed = 0;
  const timer = setInterval(() => {
    elapsed += 1;
    const remaining = durationSeconds - elapsed;
    if (onTick) onTick(Math.max(remaining, 0));
    if (elapsed >= durationSeconds) stop();
  }, 1000);

  function stop() {
    if (finished) return;
    finished = true;
    clearInterval(timer);
    if (recorder.state !== "inactive") recorder.stop();
  }

  recorder.start();
  if (onTick) onTick(durationSeconds);
  return { stop, done };
}
