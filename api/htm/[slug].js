export const config = {
  runtime: 'edge',
};

const store = globalThis.__catbox_store || new Map();
globalThis.__catbox_store = store;

export default async function handler(req, context) {
  const { slug } = context.params;

  if (req.method === 'POST') {
    try {
      const { url } = await req.json();
      store.set(slug, {
        url,
        created: Date.now()
      });
      return new Response(JSON.stringify({ success: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    } catch (err) {
      return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400 });
    }
  }

  if (req.method === 'GET') {
    const entry = store.get(slug);
    if (!entry) {
      return new Response(`<h1 style="text-align:center;padding:2rem;">🔒 Expired or Invalid Link</h1>`, {
        headers: { 'Content-Type': 'text/html' }
      });
    }

    const oneHour = 60 * 60 * 1000;
    if (Date.now() - entry.created > oneHour) {
      store.delete(slug);
      return new Response(`<h1 style="text-align:center;padding:2rem;">⏰ Link expired (1 hour)</h1>`, {
        headers: { 'Content-Type': 'text/html' }
      });
    }

    const html = `
      <!DOCTYPE html>
      <html><head><title>Preview</title><style>
        html, body { margin:0; padding:0; height:100%; }
        iframe { width:100%; height:100%; border:none; }
      </style></head>
      <body>
        <iframe src="${entry.url}" sandbox="allow-scripts allow-same-origin allow-forms"></iframe>
      </body></html>
    `;
    return new Response(html, { headers: { 'Content-Type': 'text/html' } });
  }

  return new Response('Method Not Allowed', { status: 405 });
}
