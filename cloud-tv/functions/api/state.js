export async function onRequestGet(context) {
  if (!context.env.TV_STATE) {
    return new Response(JSON.stringify({ ok: false, error: 'TV_STATE binding is not configured' }), {
      status: 503,
      headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
    });
  }
  const id = context.env.TV_STATE.idFromName('don-miguel');
  return context.env.TV_STATE.get(id).fetch(new Request('https://state/get'));
}
