import { auth } from "@clerk/nextjs/server";
import sql from "@/lib/db";

export const runtime = "nodejs";

async function ensureTable() {
  await sql`
    CREATE TABLE IF NOT EXISTS agent_runs (
      id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id      TEXT        NOT NULL,
      thread_id    TEXT        NOT NULL,
      product_name TEXT        NOT NULL,
      agent_type   TEXT        NOT NULL,
      reply        TEXT        NOT NULL DEFAULT '',
      methodology  TEXT        NOT NULL DEFAULT '',
      confidence   TEXT        NOT NULL DEFAULT 'estimated',
      data_sources JSONB       NOT NULL DEFAULT '[]',
      extracted_fields JSONB   NOT NULL DEFAULT '[]',
      field_count  INTEGER     NOT NULL DEFAULT 0,
      created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `;
}

// GET /api/agent-runs — list all runs for the signed-in user
export async function GET() {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  await ensureTable();

  const rows = await sql`
    SELECT id, thread_id, product_name, agent_type, reply, methodology,
           confidence, data_sources, extracted_fields, field_count, created_at
    FROM   agent_runs
    WHERE  user_id = ${userId}
    ORDER  BY created_at DESC
  `;

  return Response.json(rows);
}

// POST /api/agent-runs — record a completed agent run
export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json() as {
    thread_id?: string;
    product_name?: string;
    agent_type?: string;
    reply?: string;
    methodology?: string;
    confidence?: string;
    data_sources?: string[];
    extracted_fields?: unknown[];
  };

  const { thread_id, product_name, agent_type } = body;
  if (!thread_id || !product_name || !agent_type) {
    return Response.json(
      { error: "thread_id, product_name and agent_type are required" },
      { status: 400 },
    );
  }

  await ensureTable();

  const reply        = body.reply        ?? "";
  const methodology  = body.methodology  ?? "";
  const confidence   = body.confidence   ?? "estimated";
  const data_sources = JSON.stringify(body.data_sources ?? []);
  const extracted_fields = JSON.stringify(body.extracted_fields ?? []);
  const field_count  = Array.isArray(body.extracted_fields) ? body.extracted_fields.length : 0;

  await sql`
    INSERT INTO agent_runs
      (user_id, thread_id, product_name, agent_type,
       reply, methodology, confidence, data_sources, extracted_fields, field_count)
    VALUES
      (${userId}, ${thread_id}, ${product_name}, ${agent_type},
       ${reply}, ${methodology}, ${confidence}, ${data_sources}, ${extracted_fields}, ${field_count})
  `;

  return Response.json({ ok: true });
}
