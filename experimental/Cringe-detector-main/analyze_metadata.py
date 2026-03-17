import argparse
import json
import os
import math
from statistics import mean
from typing import Any

import cv2
import numpy as np
import tiktoken
from openai import OpenAI
from ultralytics import YOLO


def sample_video_frames(video_path: str, sample_count: int = 6):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        raise RuntimeError("Could not read frame count from video.")

    step = max(total_frames // sample_count, 1)
    sampled = []

    for i in range(sample_count):
        frame_idx = min(i * step, total_frames - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if ok and frame is not None:
            sampled.append(frame)

    cap.release()

    if not sampled:
        raise RuntimeError("No frames sampled from video.")

    return sampled


def detect_objects_with_yolo(frames, model_name: str = "yolov8n.pt"):
    model = YOLO(model_name)

    object_counter: dict[str, int] = {}
    confidence_scores = []

    for frame in frames:
        results = model.predict(source=frame, conf=0.25, verbose=False)
        for result in results:
            names = result.names
            boxes = result.boxes
            if boxes is None:
                continue

            for cls_idx, conf in zip(boxes.cls.tolist(), boxes.conf.tolist()):
                label = names[int(cls_idx)]
                object_counter[label] = object_counter.get(label, 0) + 1
                confidence_scores.append(float(conf))

    objects_detected = sorted(object_counter.keys(), key=lambda k: object_counter[k], reverse=True)
    return objects_detected[:10], object_counter, confidence_scores


def estimate_visual_quality(frames):
    sharpness_values = []
    for frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
        sharpness_values.append(sharpness)

    avg = mean(sharpness_values) if sharpness_values else 0.0
    return int(max(0, min(100, (avg / 500.0) * 100)))


def build_metadata_from_video(video_path: str, caption: str, hashtags, likes: int, comments: int, views: int, verbose: bool = True):
    if verbose:
        print("Video -> Frame extraction -> Vision detection -> Metadata summary")
    frames = sample_video_frames(video_path, sample_count=6)
    objects_detected, object_counts, confidences = detect_objects_with_yolo(frames)
    visual_quality = estimate_visual_quality(frames)

    return {
        "caption": caption,
        "hashtags": hashtags,
        "objects_detected": objects_detected,
        "object_counts": object_counts,
        "scene": "uncertain",
        "visual_quality": visual_quality,
        "nsfw_score": 0.01,
        "likes": likes,
        "comments": comments,
        "views": views,
        "yolo_avg_confidence": round(mean(confidences), 3) if confidences else 0.0,
        "sampled_frames": len(frames),
    }


def get_encoder(model_name: str):
    try:
        return tiktoken.encoding_for_model(model_name)
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


def token_count(text: str, model_name: str) -> int:
    enc = get_encoder(model_name)
    return len(enc.encode(text))


def compact_json(data: dict[str, Any]) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=True)


def embed_text(client: OpenAI, text: str, embedding_model: str) -> list[float]:
    resp = client.embeddings.create(model=embedding_model, input=text)
    return resp.data[0].embedding


def normalize_vector(vec: list[float]) -> np.ndarray:
    arr = np.array(vec, dtype="float32").reshape(1, -1)
    import faiss

    faiss.normalize_L2(arr)
    return arr


def load_or_create_faiss_index(index_path: str, dim: int):
    import faiss

    if os.path.exists(index_path):
        index = faiss.read_index(index_path)
        if index.d != dim:
            return faiss.IndexFlatIP(dim)
        return index
    return faiss.IndexFlatIP(dim)


def load_doc_store(doc_path: str):
    if not os.path.exists(doc_path):
        return []
    with open(doc_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_doc_store(doc_path: str, rows):
    with open(doc_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=True)


def build_retrieval_examples(index, rows, query_vec: np.ndarray, top_k: int):
    if index.ntotal == 0 or len(rows) == 0:
        return []

    k = min(top_k, index.ntotal)
    scores, ids = index.search(query_vec, k)

    out = []
    for score, idx in zip(scores[0], ids[0]):
        if idx < 0 or idx >= len(rows):
            continue
        row = rows[idx]
        out.append(
            {
                "similarity": round(float(score), 4),
                "metadata_summary": row.get("metadata_summary", ""),
                "analysis_summary": row.get("analysis_summary", ""),
            }
        )
    return out


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
      return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return -1.0
    return dot / (na * nb)


def build_retrieval_examples_no_faiss(rows, query_embedding: list[float], top_k: int):
    scored = []
    for row in rows:
        emb = row.get("embedding", [])
        sim = cosine_similarity(query_embedding, emb) if emb else -1.0
        if sim > -0.5:
            scored.append((sim, row))
    scored.sort(key=lambda x: x[0], reverse=True)

    out = []
    for score, row in scored[:top_k]:
        out.append(
            {
                "similarity": round(float(score), 4),
                "metadata_summary": row.get("metadata_summary", ""),
                "analysis_summary": row.get("analysis_summary", ""),
            }
        )
    return out


def build_rag_prompt(metadata: dict[str, Any], retrieval_examples):
    schema = {
        "summary": "",
        "primary_niche": "",
        "archetype": "",
        "tone": "",
        "confidence": 0,
        "safety": {
            "adult": False,
            "adult_confidence": 0,
            "adult_reason": "",
            "brand_safety": 0,
        },
        "creator_details": {
            "visual_style": [],
            "editing_style": [],
            "production_level": "",
        },
        "cringe_finder": {
            "cringe_score": 0,
            "is_cringe": False,
            "cringe_signals": [],
            "score_reason": "",
            "fixes": [],
        },
        "next_actions": [],
    }

    prompt = (
        "You are an AI system that analyzes creator reels for influencer marketplaces. "
        "Use the current metadata and similar examples if provided. Return ONLY valid JSON.\n\n"
        f"Metadata:\n{compact_json(metadata)}\n\n"
    )

    if retrieval_examples:
        prompt += (
            "Similar examples (context only; do NOT copy scores from these):\n"
            + json.dumps(retrieval_examples, separators=(",", ":"), ensure_ascii=True)
            + "\n\n"
        )

    prompt += (
        "Output schema:\n"
        + json.dumps(schema, separators=(",", ":"), ensure_ascii=True)
        + (
            "\nRules:"
            " scores 0-100 ints; max 3 items per list; be concise;"
            " evaluate cringe strictly."
            " Cringe rubric:"
            " 0-20 polished and natural;"
            " 21-40 minor awkwardness;"
            " 41-60 noticeable awkwardness OR weak concept;"
            " 61-80 strong cringe (forced, confusing, low coherence);"
            " 81-100 extreme cringe (chaotic or very awkward)."
            " Floor rules:"
            " if concept appears confusing/nonsensical -> cringe_score >= 65;"
            " if repeated awkward posing/expression -> cringe_score >= 55;"
            " if both -> cringe_score >= 75."
            " Set is_cringe=true when cringe_score >= 45."
        )
    )
    return prompt


def parse_response_json(text: str):
    cleaned = text.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except Exception:
        return None


def usage_to_jsonable(usage):
    if usage is None:
        return None

    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def run_pipeline(
    metadata: dict[str, Any],
    llm_model: str,
    embedding_model: str,
    faiss_index_path: str,
    doc_store_path: str,
    top_k: int,
    no_faiss: bool,
    verbose: bool,
):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "YOUR_API_KEY"))

    metadata_text = compact_json(metadata)
    query_embedding = embed_text(client, metadata_text, embedding_model)
    rows = load_doc_store(doc_store_path)
    query_vec = normalize_vector(query_embedding)

    if verbose:
        print("tiktoken check -> FAISS similarity search -> RAG prompt -> LLM classification")

    if no_faiss:
        retrieval_examples = build_retrieval_examples_no_faiss(rows, query_embedding, top_k=top_k)
    else:
        index = load_or_create_faiss_index(faiss_index_path, query_vec.shape[1])
        retrieval_examples = build_retrieval_examples(index, rows, query_vec, top_k=top_k)
    prompt = build_rag_prompt(metadata, retrieval_examples)
    prompt_tokens = token_count(prompt, llm_model)

    response = client.responses.create(
        model=llm_model,
        input=prompt,
        max_output_tokens=320,
    )

    output_text = response.output_text
    parsed = parse_response_json(output_text)

    analysis_summary = ""
    if parsed:
        analysis_summary = compact_json(
            {
                "primary_niche": parsed.get("primary_niche", ""),
                "archetype": parsed.get("archetype", ""),
                "tone": parsed.get("tone", ""),
                "cringe_score": parsed.get("cringe_finder", {}).get("cringe_score", ""),
                "brand_safety": parsed.get("safety", {}).get("brand_safety", ""),
            }
        )

    rows.append(
        {
            "metadata_summary": metadata_text,
            "analysis_summary": analysis_summary,
            "embedding": query_embedding,
        }
    )
    if not no_faiss:
        import faiss

        index.add(query_vec)
        faiss.write_index(index, faiss_index_path)
    save_doc_store(doc_store_path, rows)

    return output_text, usage_to_jsonable(response.usage), prompt_tokens, retrieval_examples


def main():
    parser = argparse.ArgumentParser(description="Video->YOLO->metadata->tiktoken->FAISS->RAG->LLM")
    parser.add_argument("--video", required=True, help="Path to reel video")
    parser.add_argument("--caption", default="Reel upload", help="Caption text")
    parser.add_argument("--hashtags", default="", help="Comma-separated hashtags")
    parser.add_argument("--likes", type=int, default=0)
    parser.add_argument("--comments", type=int, default=0)
    parser.add_argument("--views", type=int, default=0)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--llm-model", default="gpt-4o-mini")
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    parser.add_argument("--faiss-index", default=".reel_index.faiss")
    parser.add_argument("--doc-store", default=".reel_docs.json")
    parser.add_argument("--no-faiss", action="store_true", help="Use pure Python similarity search fallback")
    parser.add_argument("--emit-json", action="store_true", help="Print single JSON payload for API integration")
    args = parser.parse_args()

    hashtags = [h.strip() for h in args.hashtags.split(",") if h.strip()]

    metadata = build_metadata_from_video(
        video_path=args.video,
        caption=args.caption,
        hashtags=hashtags,
        likes=args.likes,
        comments=args.comments,
        views=args.views,
        verbose=not args.emit_json,
    )

    result, usage, prompt_tokens, retrieval = run_pipeline(
        metadata=metadata,
        llm_model=args.llm_model,
        embedding_model=args.embedding_model,
        faiss_index_path=args.faiss_index,
        doc_store_path=args.doc_store,
        top_k=args.top_k,
        no_faiss=args.no_faiss,
        verbose=not args.emit_json,
    )

    parsed = parse_response_json(result)
    payload = {
        "metadata": metadata,
        "retrieval": retrieval,
        "analysis": parsed if parsed else result,
        "token_usage": {
            "prompt_tokens_estimate": prompt_tokens,
            "api_usage": usage,
        },
    }

    if args.emit_json:
        print(json.dumps(payload, ensure_ascii=True))
        return

    print("\nDETECTED METADATA\n")
    print(json.dumps(metadata, indent=2))
    print("\nRETRIEVED CONTEXT\n")
    print(json.dumps(retrieval, indent=2))
    print("\nANALYSIS RESULT\n")
    if parsed:
        print(json.dumps(parsed, indent=2))
    else:
        print(result)
    print("\nTOKEN USAGE\n")
    print(payload["token_usage"])


if __name__ == "__main__":
    main()
