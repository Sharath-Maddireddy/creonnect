import express from "express";
import OpenAI from "openai";
import fs from "fs";
import path from "path";
import multer from "multer";
import ffmpeg from "fluent-ffmpeg";
import ffmpegPath from "ffmpeg-static";
import ffprobeStatic from "ffprobe-static";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

if (ffmpegPath) {
  ffmpeg.setFfmpegPath(ffmpegPath);
}

const ffprobePath =
  ffprobeStatic?.path ||
  ffprobeStatic?.default?.path ||
  ffprobeStatic?.default ||
  ffprobeStatic;

if (ffprobePath) {
  ffmpeg.setFfprobePath(ffprobePath);
}

const app = express();
const port = process.env.PORT || 3000;

const uploadDir = path.join(__dirname, "uploads");
const tempDir = path.join(__dirname, "temp");

for (const dir of [uploadDir, tempDir]) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

const upload = multer({
  dest: uploadDir,
  limits: {
    fileSize: 100 * 1024 * 1024
  }
});

function parseJsonSafe(text) {
  if (typeof text !== "string") return null;

  const cleaned = text
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();

  try {
    return JSON.parse(cleaned);
  } catch {
    const start = cleaned.indexOf("{");
    const end = cleaned.lastIndexOf("}");
    if (start !== -1 && end !== -1 && end > start) {
      try {
        return JSON.parse(cleaned.slice(start, end + 1));
      } catch {
        return null;
      }
    }
    return null;
  }
}

function extractFrames(videoPath, outputDir, count = 3) {
  return new Promise((resolve, reject) => {
    ffmpeg(videoPath)
      .on("end", resolve)
      .on("error", reject)
      .screenshots({
        count,
        folder: outputDir,
        filename: "frame-%i.png"
      });
  });
}

function extractAudioSample(videoPath, audioPath, maxSeconds = 45) {
  return new Promise((resolve, reject) => {
    ffmpeg(videoPath)
      .noVideo()
      .audioCodec("pcm_s16le")
      .audioChannels(1)
      .audioFrequency(16000)
      .duration(maxSeconds)
      .format("wav")
      .on("end", resolve)
      .on("error", reject)
      .save(audioPath);
  });
}

function enforceCringeFloor(outputText) {
  try {
    const parsed = parseJsonSafe(outputText);
    if (!parsed) return outputText;
    const cringe = parsed?.cringe_finder || {};
    const signals = Array.isArray(cringe.cringe_signals) ? cringe.cringe_signals : [];
    const signalText = signals.join(" ").toLowerCase();
    let score = Number(cringe.cringe_score || 0);

    const strongSignal =
      /awkward|cringe|forced|overexaggerated|nonsens|confus|chaotic|low production|poor quality/.test(signalText);

    if (signals.length >= 3 && strongSignal) {
      score = Math.max(score, 70);
    } else if (signals.length >= 2 && strongSignal) {
      score = Math.max(score, 60);
    }

    parsed.cringe_finder = {
      ...cringe,
      cringe_score: Math.min(100, Math.max(0, Math.round(score)))
    };
    return JSON.stringify(parsed);
  } catch {
    return outputText;
  }
}

function buildVoiceFallback(reason, transcriptExcerpt = "") {
  return {
    ok: false,
    reason,
    voice_cringe: {
      label: "uncertain",
      score: 0,
      confidence: 0,
      signals: [],
      fixes: []
    },
    voice_meaning: {
      verdict: "uncertain",
      is_wrong: null,
      confidence: 0,
      reason: "",
      suggested_correction: ""
    },
    voice_transcript_excerpt: transcriptExcerpt.slice(0, 280),
    usage: null
  };
}

function normalizeVoicePayload(payload, transcript) {
  const voice = payload?.voice_cringe || {};
  const cleanScore = Number.isFinite(Number(voice.score)) ? Math.max(0, Math.min(100, Math.round(Number(voice.score)))) : 0;
  const cleanConfidence = Number.isFinite(Number(voice.confidence))
    ? Math.max(0, Math.min(100, Math.round(Number(voice.confidence))))
    : 0;
  const label = typeof voice.label === "string" ? voice.label.toLowerCase() : "uncertain";
  const cleanLabel = ["cringe", "not_cringe", "uncertain"].includes(label) ? label : "uncertain";
  const signals = Array.isArray(voice.signals)
    ? voice.signals.filter((item) => typeof item === "string").slice(0, 3)
    : [];
  const fixes = Array.isArray(voice.fixes)
    ? voice.fixes.filter((item) => typeof item === "string").slice(0, 3)
    : [];
  const meaning = payload?.voice_meaning || {};
  const meaningVerdict = typeof meaning.verdict === "string" ? meaning.verdict.toLowerCase() : "uncertain";
  const cleanMeaningVerdict = ["wrong", "not_wrong", "uncertain"].includes(meaningVerdict) ? meaningVerdict : "uncertain";
  let cleanIsWrong = null;
  if (typeof meaning.is_wrong === "boolean") {
    cleanIsWrong = meaning.is_wrong;
  } else if (cleanMeaningVerdict === "wrong") {
    cleanIsWrong = true;
  } else if (cleanMeaningVerdict === "not_wrong") {
    cleanIsWrong = false;
  }
  const cleanMeaningConfidence = Number.isFinite(Number(meaning.confidence))
    ? Math.max(0, Math.min(100, Math.round(Number(meaning.confidence))))
    : 0;
  const cleanMeaningReason = typeof meaning.reason === "string" ? meaning.reason.slice(0, 280) : "";
  const cleanMeaningCorrection = typeof meaning.suggested_correction === "string" ? meaning.suggested_correction.slice(0, 280) : "";
  const transcriptExcerpt = typeof payload?.transcript_excerpt === "string" ? payload.transcript_excerpt : transcript || "";

  return {
    voice_cringe: {
      label: cleanLabel,
      score: cleanScore,
      confidence: cleanConfidence,
      signals,
      fixes
    },
    voice_meaning: {
      verdict: cleanMeaningVerdict,
      is_wrong: cleanIsWrong,
      confidence: cleanMeaningConfidence,
      reason: cleanMeaningReason,
      suggested_correction: cleanMeaningCorrection
    },
    voice_transcript_excerpt: transcriptExcerpt.slice(0, 280)
  };
}

async function analyzeVoice(videoPath, frameDir, client) {
  const audioPath = path.join(frameDir, "voice.wav");

  try {
    await extractAudioSample(videoPath, audioPath);
  } catch {
    return buildVoiceFallback("Could not read an audio track from this video.");
  }

  let transcript = "";
  try {
    const tx = await client.audio.transcriptions.create({
      file: fs.createReadStream(audioPath),
      model: "gpt-4o-mini-transcribe"
    });
    transcript = typeof tx?.text === "string" ? tx.text.trim() : "";
  } catch {
    return buildVoiceFallback("Audio transcription failed.");
  }

  if (!transcript) {
    return buildVoiceFallback("No clear speech detected in audio.");
  }

  let voiceResponse;
  try {
    voiceResponse = await client.responses.create({
      model: "gpt-4.1-mini",
      input: [
        {
          role: "user",
          content: [
            {
              type: "input_text",
              text: `Evaluate if the spoken script feels cringe for social media.
Use transcript only; if uncertain, lower confidence.
Return ONLY valid JSON using this exact schema:
{
  "voice_cringe": {
    "label": "cringe|not_cringe|uncertain",
    "score": 0,
    "confidence": 0,
    "signals": ["string"],
    "fixes": ["string"]
  },
  "voice_meaning": {
    "verdict": "wrong|not_wrong|uncertain",
    "is_wrong": true,
    "confidence": 0,
    "reason": "string",
    "suggested_correction": "string"
  },
  "transcript_excerpt": "string"
}
Rules:
- score and confidence are integers 0-100.
- max 3 signals and 3 fixes.
- label must match the score:
  - 0-30 => not_cringe
  - 31-59 => uncertain
  - 60-100 => cringe
- Analyze meaning quality and correctness from transcript wording:
  - wrong: clear contradiction, broken meaning, or obvious incorrect claim in-context.
  - not_wrong: clear and coherent meaning with no obvious error in-context.
  - uncertain: cannot verify correctness from transcript alone.
- If external fact-check is required, use uncertain.
- excerpt max 200 chars.
- meaning reason and suggested correction should be concise (<= 140 chars each).
- Keep concise.
Transcript:
"""${transcript}"""`
            }
          ]
        }
      ]
    });
  } catch {
    return buildVoiceFallback("Voice analysis failed.", transcript);
  }

  const parsed = parseJsonSafe(voiceResponse.output_text);
  const normalized = normalizeVoicePayload(parsed || {}, transcript);

  return {
    ok: true,
    reason: "",
    ...normalized,
    usage: voiceResponse.usage
  };
}

function attachVoiceAnalysis(resultText, voiceResult) {
  const parsed = parseJsonSafe(resultText);
  if (!parsed) return resultText;

  parsed.voice_cringe = voiceResult?.voice_cringe || {
    label: "uncertain",
    score: 0,
    confidence: 0,
    signals: [],
    fixes: []
  };
  parsed.voice_meaning = voiceResult?.voice_meaning || {
    verdict: "uncertain",
    is_wrong: null,
    confidence: 0,
    reason: "",
    suggested_correction: ""
  };
  parsed.voice_transcript_excerpt = voiceResult?.voice_transcript_excerpt || "";
  if (voiceResult?.reason) {
    parsed.voice_analysis_note = voiceResult.reason;
  }

  return JSON.stringify(parsed);
}

function mergeUsage(usageA, usageB) {
  const keys = ["input_tokens", "output_tokens", "total_tokens"];
  const merged = {};

  for (const key of keys) {
    const a = Number(usageA?.[key] ?? 0);
    const b = Number(usageB?.[key] ?? 0);
    merged[key] = a + b;
  }

  return merged;
}

async function analyzeFrames(frameDir, client) {
  const images = fs
    .readdirSync(frameDir)
    .filter((name) => name.endsWith(".png"))
    .sort();

  if (images.length === 0) {
    throw new Error("No frames extracted from video.");
  }

  const content = [
    {
      type: "input_text",
      text: `Analyze these extracted video frames and return ONLY valid JSON.
Use this exact schema:
{
  "summary": {
    "primary_niche": "string",
    "creator_archetype": "string",
    "tone": "string",
    "confidence": 0
  },
  "safety": {
    "adult_content": {
      "is_adult": false,
      "confidence": 0,
      "reason": "string"
    },
    "brand_safety_score": 0
  },
  "creator_details": {
    "visual_style": ["string"],
    "editing_style": ["string"],
    "production_level": "low|medium|high"
  },
  "cringe_finder": {
    "cringe_score": 0,
    "cringe_signals": ["string"],
    "fixes_to_reduce_cringe": ["string"]
  },
  "next_actions": ["string"]
}
Rules:
- Scores are 0-100 integers.
- Max 3 items in each list.
- Keep outputs concise and evidence-based from frames only.
- If uncertain, use \"uncertain\" and lower confidence.
- Nudity policy:
  - Swimwear/bikini alone IS nudity for this classifier.
  - Set adult_content.is_adult=true when swimwear/bikini is visible.
  - Use lower brand_safety_score for swimwear/bikini content.
  - Explicit sexual exposure/acts should be scored as highest adult risk.
- Cringe rubric:
  - 0-20 polished and natural.
  - 21-40 minor awkwardness.
  - 41-60 noticeable awkwardness.
  - 61-80 strong cringe (forced/awkward/confusing).
  - 81-100 extreme cringe.
- Floor rules:
  - repeated awkward signals in 3+ cues => score must be >= 70.
  - confusing concept + awkward acting => score must be >= 75.`
    }
  ];

  for (const img of images) {
    const imagePath = path.join(frameDir, img);
    const base64 = fs.readFileSync(imagePath, { encoding: "base64" });
    content.push({
      type: "input_image",
      image_url: `data:image/png;base64,${base64}`
    });
  }

  const response = await client.responses.create({
    model: "gpt-4.1-mini",
    input: [
      {
        role: "user",
        content
      }
    ]
  });

  return {
    outputText: enforceCringeFloor(response.output_text),
    usage: response.usage
  };
}

app.use(express.static(path.join(__dirname, "public")));

app.post("/analyze", upload.single("video"), async (req, res) => {
  const apiKey = process.env.OPENAI_API_KEY;

  if (!apiKey) {
    return res.status(500).json({
      error: "OPENAI_API_KEY is not set. Add it to your environment and restart the server."
    });
  }

  if (!req.file) {
    return res.status(400).json({ error: "No video uploaded." });
  }

  const client = new OpenAI({ apiKey });
  const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const frameDir = path.join(tempDir, requestId);

  fs.mkdirSync(frameDir, { recursive: true });

  try {
    await extractFrames(req.file.path, frameDir, 3);
    const [frameResult, voiceResult] = await Promise.all([analyzeFrames(frameDir, client), analyzeVoice(req.file.path, frameDir, client)]);
    const mergedResultText = attachVoiceAnalysis(frameResult.outputText, voiceResult);
    res.json({
      ok: true,
      result: mergedResultText,
      usage: mergeUsage(frameResult.usage, voiceResult.usage),
      voice: {
        ok: voiceResult.ok,
        reason: voiceResult.reason || ""
      }
    });
  } catch (error) {
    res.status(500).json({
      error: error instanceof Error ? error.message : "Unknown error"
    });
  } finally {
    try {
      fs.rmSync(req.file.path, { force: true });
      fs.rmSync(frameDir, { recursive: true, force: true });
    } catch {
      // Ignore cleanup issues.
    }
  }
});

app.listen(port, () => {
  console.log(`Server running at http://localhost:${port}`);
});
