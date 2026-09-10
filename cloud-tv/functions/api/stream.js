export async function onRequestGet(context) {
  if (!context.env.TV_STATE) {
    return new Response('TV_STATE binding is not configured', { status: 503 });
  }
  if (context.request.headers.get('Upgrade')?.toLowerCase() !== 'websocket') {
    return new Response('Expected WebSocket', { status: 426 });
  }
  const id = context.env.TV_STATE.idFromName('don-miguel');
  return context.env.TV_STATE.get(id).fetch(new Request('https://state/stream', context.request));
}
