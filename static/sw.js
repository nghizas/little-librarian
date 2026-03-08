const CACHE_NAME = 'little-librarian-v1';
const PRECACHE = ['/', '/static/style.css'];

self.addEventListener('install', (e) => {
    e.waitUntil(caches.open(CACHE_NAME).then((c) => c.addAll(PRECACHE)));
    self.skipWaiting();
});

self.addEventListener('activate', (e) => {
    e.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (e) => {
    // Network-first for all requests (simple app, always online)
    if (e.request.method !== 'GET') return;
    e.respondWith(
        fetch(e.request)
            .then((response) => {
                // Cache successful responses for static assets
                if (e.request.url.includes('/static/')) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((c) => c.put(e.request, clone));
                }
                return response;
            })
            .catch(() => caches.match(e.request))
    );
});
