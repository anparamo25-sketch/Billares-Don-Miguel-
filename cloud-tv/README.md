# Billares Don Miguel — TV en la nube

Esta versión elimina la dependencia de `billaresdonmiguel.local` para la pantalla pública.

## Arquitectura

- `public/index.html`: pantalla TV responsive, HTML/CSS/JavaScript estándar.
- `worker.js`: API y WebSocket en Cloudflare Workers.
- Durable Object con SQLite: conserva el último estado y distribuye cambios en tiempo real.
- Plan gratuito de Cloudflare: adecuado para un local con una pantalla TV. El límite actual de Workers Free es 100.000 solicitudes/día y Durable Objects Free también tienen 100.000 solicitudes/día.

## Despliegue

1. Crear una cuenta gratuita de Cloudflare.
2. Instalar Wrangler y autenticarse.
3. Desde `cloud-tv/`, ejecutar `npx wrangler deploy`.
4. Cloudflare entregará una URL `https://...workers.dev`.
5. Esa será la dirección que se abrirá en el navegador del televisor.

## Siguiente integración

La aplicación central debe publicar su estado al endpoint `/api/publish` del Worker. La página TV recibirá esos cambios por WebSocket y actualizará las cinco mesas automáticamente.

No se requiere instalar una app en el televisor.
