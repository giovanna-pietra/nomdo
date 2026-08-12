/*
 * app/static/sw.js
 * Service Worker do Nomdo — só cuida de notificações push (não faz cache
 * de páginas/offline, pra não arriscar servir versão desatualizada do
 * site). Fica registrado no navegador mesmo com todas as abas fechadas,
 * que é justamente o que permite a notificação chegar nesse estado.
 */

self.addEventListener("install", (event) => {
  // Ativa o novo Service Worker assim que instalado, sem esperar as abas
  // antigas fecharem — a lógica aqui é simples e idempotente o bastante
  // pra não ter risco em trocar na hora.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let dados = {};
  try {
    dados = event.data ? event.data.json() : {};
  } catch (e) {
    dados = { title: "Nomdo", body: event.data ? event.data.text() : "" };
  }

  const titulo = dados.title || "Nomdo";
  const opcoes = {
    body: dados.body || "",
    icon: "/static/img/icone_fundo.png",
    badge: "/static/img/icone_fundo.png",
    tag: dados.tag || "nomdo-notificacao",
    // Sem isso, uma 2ª notificação com a MESMA tag (ex: clicar "Testar"
    // de novo) só substitui a anterior sem alertar — se a primeira ainda
    // estiver na Central de Notificações, a segunda não aparece/não
    // toca som, dando a falsa impressão de que parou de funcionar.
    renotify: true,
    data: { url: dados.url || "/hub-anfitriao" },
  };

  event.waitUntil(self.registration.showNotification(titulo, opcoes));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const urlAlvo = (event.notification.data && event.notification.data.url) || "/hub-anfitriao";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((janelas) => {
      // Se já tem uma aba do Nomdo aberta, foca nela em vez de abrir outra.
      for (const janela of janelas) {
        if (janela.url.includes(self.location.origin) && "focus" in janela) {
          janela.navigate(urlAlvo);
          return janela.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(urlAlvo);
      }
    })
  );
});
