-- Enable pgvector once per database
CREATE EXTENSION IF NOT EXISTS vector;

-- OpenAI text-embedding-3-small returns 1536 dimensions.
-- Ensure your column matches model dimensions.
ALTER TABLE posts
  ALTER COLUMN embedding TYPE vector(1536);

-- RPC function for cosine similarity search (used by Supabase API key flow)
CREATE OR REPLACE FUNCTION match_posts(
  query_embedding vector(1536),
  match_count int DEFAULT 5
)
RETURNS TABLE (
  id int,
  title text,
  body text,
  similarity float
)
LANGUAGE sql
AS $$
  SELECT
    p.id,
    p.title,
    p.body,
    1 - (p.embedding <=> query_embedding) AS similarity
  FROM posts p
  WHERE p.embedding IS NOT NULL
  ORDER BY p.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- Optional index (recommended after table has enough rows)
-- CREATE INDEX IF NOT EXISTS posts_embedding_cosine_idx
--   ON posts USING ivfflat (embedding vector_cosine_ops)
--   WITH (lists = 100);
