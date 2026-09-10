export async function onRequestPost(context) {
  if (!context.env.TV_STATE) {
    return new Response('TV_STATE binding is not configured', { status: 503 });
  }
  const body = await context.request.text();
  if (body.length > 200000) return new Response('Payload too large', { status: 413 });
  try {
    JSON.parse(body);
  } catch (_) {
    return new Response('Invalid JSON', { status: 400 });
  }
  const id = context.env.TV_STATE.idFromName('don-miguel');
  return context.env.TV_STATE.get(id).fetch(new Request('https://state/publish', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body,
  }));
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: corsHeaders() });
}

function corsHeaders() {
  return {
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'POST, OPTIONS',
    'access-control-allow-headers': 'content-type',
  };
}
