import "dotenv/config";
import OpenAI from "openai";
import { createClient } from "@supabase/supabase-js";

const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const EMBEDDING_MODEL = process.env.EMBEDDING_MODEL || "text-embedding-3-small";

if (!OPENAI_API_KEY) {
  console.error("Missing OPENAI_API_KEY env var.");
  process.exit(1);
}

if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
  console.error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY env var.");
  process.exit(1);
}

const openai = new OpenAI({ apiKey: OPENAI_API_KEY });
const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
  auth: { persistSession: false }
});

async function generateEmbedding(text) {
  const response = await openai.embeddings.create({
    model: EMBEDDING_MODEL,
    input: text
  });
  return response.data[0].embedding;
}

async function insertPostWithEmbedding(title, body) {
  const text = `${title}\n${body}`;
  const embedding = await generateEmbedding(text);

  const { data, error } = await supabase
    .from("posts")
    .insert({ title, body, embedding })
    .select("id, title")
    .single();

  if (error) throw error;
  return { post: data, embeddingLength: embedding.length };
}

async function cosineSearchPosts(searchText, limit = 5) {
  const embedding = await generateEmbedding(searchText);

  const { data, error } = await supabase.rpc("match_posts", {
    query_embedding: embedding,
    match_count: limit
  });

  if (error) throw error;
  return { queryEmbeddingLength: embedding.length, matches: data || [] };
}

async function main() {
  const action = process.argv[2] || "demo";

  if (action === "insert") {
    const title = process.argv[3] || "Cringe dance trend";
    const body = process.argv[4] || "Overacted expressions and awkward choreography in a bedroom setup.";
    const inserted = await insertPostWithEmbedding(title, body);
    console.log(JSON.stringify({ ok: true, action, ...inserted }, null, 2));
    return;
  }

  if (action === "search") {
    const searchText = process.argv[3] || "awkward dance cringe content";
    const limit = Number(process.argv[4] || 5);
    const searched = await cosineSearchPosts(searchText, limit);
    console.log(JSON.stringify({ ok: true, action, ...searched }, null, 2));
    return;
  }

  const inserted = await insertPostWithEmbedding(
    "Lehenga transition reel",
    "Fast fashion transition with dramatic expressions and mirror shots."
  );
  const searched = await cosineSearchPosts("fashion transition reel cringe", 5);

  console.log(
    JSON.stringify(
      {
        ok: true,
        action: "demo",
        inserted,
        searched
      },
      null,
      2
    )
  );
}

main().catch((err) => {
  console.error("pgvector experiment failed:", err?.message || err);
  if (err?.code) console.error("code:", err.code);
  if (err?.details) console.error("details:", err.details);
  if (err?.hint) console.error("hint:", err.hint);
  process.exit(1);
});
