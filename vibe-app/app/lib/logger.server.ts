// Minimal structured-logger for the Vibe Remix app.
//
// We don't have Sentry / Datadog / a metrics client wired into vibe-app
// today. Every Remix function (action, loader, API route) is a Vercel
// Serverless Function, which means stdout writes are captured by Vercel
// Logs verbatim and become greppable / filter-able in the Vercel
// dashboard and any log drain. So a one-line JSON-to-stdout helper is
// enough to give us per-request observability for the Vibe surface.
//
// Why JSON not text: Vercel Log Drains forward each stdout line as a
// distinct record. If the consumer is Datadog / Logtail / a custom
// drain, structured JSON is parsed into searchable fields out of the
// box. Plain text becomes a single `.message` blob that has to be
// regex-mined for every query.
//
// Shape (loosely matches the engine's _JsonFormatter in
// platform_core/logging_config.py so a future unified drain doesn't
// need two parsers):
//   {"ts": "...Z", "level": "info|warn|error", "event": "<name>", ...fields}
//
// `event` is the load-bearing field — pick a snake_case name that's
// stable enough to be the query key (`event="vibe_init_outcome"`).
// Everything else is per-event context.

type Level = "info" | "warn" | "error";

function emit(level: Level, event: string, fields: Record<string, unknown>): void {
  // Spread fields first, then assign canonical keys last so a caller
  // who accidentally passes `event` / `level` / `ts` in `fields` can't
  // shadow the queryable shape.
  const record: Record<string, unknown> = {
    ...fields,
    ts: new Date().toISOString(),
    level,
    event,
  };
  try {
    // info/warn → stdout; error → stderr. Vercel aggregates both, but
    // some drains key alerts off stderr presence so this matches the
    // ecosystem convention.
    const line = JSON.stringify(record);
    if (level === "error") {
      // eslint-disable-next-line no-console
      console.error(line);
    } else {
      // eslint-disable-next-line no-console
      console.log(line);
    }
  } catch {
    // JSON.stringify can throw on circular references — fall back to
    // a degraded line so we still see SOMETHING in the log.
    // eslint-disable-next-line no-console
    console.log(JSON.stringify({ ts: new Date().toISOString(), level, event, _stringify_failed: true }));
  }
}

export function logInfo(event: string, fields: Record<string, unknown> = {}): void {
  emit("info", event, fields);
}

export function logWarn(event: string, fields: Record<string, unknown> = {}): void {
  emit("warn", event, fields);
}

export function logError(event: string, fields: Record<string, unknown> = {}): void {
  emit("error", event, fields);
}
