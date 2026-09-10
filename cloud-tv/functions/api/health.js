export async function onRequestGet() {
  return new Response(JSON.stringify({ ok: true, service: 'Billares Don Miguel TV' }), {
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
  });
}
