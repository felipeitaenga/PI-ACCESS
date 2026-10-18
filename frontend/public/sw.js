/* PI-ACCESS — notificações do autocadastro (Web Push) */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let d = {};
  try { d = event.data ? event.data.json() : {}; } catch { d = { title: "PI-ACCESS", body: event.data && event.data.text() }; }
  event.waitUntil(self.registration.showNotification(d.title || "PI-ACCESS", {
    body: d.body || "", tag: d.tag || "selfreg", renotify: true, vibrate: [200, 100, 200, 100, 300],
    icon: "/icon-192.png", badge: "/favicon-32.png", data: { url: d.url || "/" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const open = all.find((c) => c.url.includes("/solicitacao/"));
    if (open) { return open.focus(); }
    const cache = await caches.open("piaccess-selfreg");
    const saved = await cache.match("/__last_status");
    const url = saved ? await saved.text() : "/";
    return self.clients.openWindow(url);
  })());
});
