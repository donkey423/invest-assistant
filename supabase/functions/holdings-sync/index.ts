// holdings-sync：讓 GitHub Actions 不用任何密鑰就能讀持股、寫回計算結果。
// 驗證方式：GitHub Actions 發的 OIDC 身分證明（由 GitHub 簽章的 JWT）。
// 這裡驗證簽章，並確認它來自 donkey423/invest-assistant main 分支上的 holdings.yml，通過才讀寫。
import { createRemoteJWKSet, jwtVerify } from "npm:jose@5.9.6";
import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const REPO = "donkey423/invest-assistant";
const WORKFLOW = `${REPO}/.github/workflows/holdings.yml@refs/heads/main`;
const AUDIENCE = "invest-assistant-holdings";
const JWKS = createRemoteJWKSet(new URL("https://token.actions.githubusercontent.com/.well-known/jwks"));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

async function verify(req: Request): Promise<string | null> {
  const token = (req.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
  if (!token) return "missing token";
  try {
    const { payload } = await jwtVerify(token, JWKS, {
      issuer: "https://token.actions.githubusercontent.com",
      audience: AUDIENCE,
    });
    if (payload.repository !== REPO) return "wrong repository";
    if (payload.workflow_ref !== WORKFLOW && payload.job_workflow_ref !== WORKFLOW) return "wrong workflow";
    return null;
  } catch (e) {
    return `invalid token: ${(e as Error).message}`;
  }
}

Deno.serve(async (req) => {
  const err = await verify(req);
  if (err) return json({ error: err }, 401);

  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
    auth: { persistSession: false },
  });

  if (req.method === "GET") {
    const [h, t, r] = await Promise.all([
      db.from("holdings").select("*").order("id"),
      db.from("transactions").select("*").order("date"),
      db.from("holdings_reports").select("user_id,report"),
    ]);
    const e = h.error || t.error || r.error;
    if (e) return json({ error: e.message }, 500);
    return json({ holdings: h.data, transactions: t.data, reports: r.data });
  }

  if (req.method === "POST") {
    const body = await req.json();
    const rows = (Array.isArray(body) ? body : [body]).map((x) => ({
      user_id: x.user_id, report: x.report, generated_at: x.generated_at ?? new Date().toISOString(),
    }));
    if (!rows.every((x) => typeof x.user_id === "string" && x.report && typeof x.report === "object")) {
      return json({ error: "bad payload" }, 400);
    }
    const { error } = await db.from("holdings_reports").upsert(rows, { onConflict: "user_id" });
    if (error) return json({ error: error.message }, 500);
    return json({ saved: rows.length });
  }

  return json({ error: "method not allowed" }, 405);
});
