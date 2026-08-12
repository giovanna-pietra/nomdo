/*
 * app/static/js/push.js
 * Cliente de notificações push do navegador (Web Push). Exposto como
 * `window.NomdoPush`, usado em dois lugares:
 *   1. base_dash.html — no carregamento de QUALQUER página logada, garante
 *      silenciosamente a inscrição se `notify_browser` já estiver ligado e
 *      a permissão do navegador já tiver sido concedida antes (não pede
 *      permissão de novo sem gesto do usuário).
 *   2. configuracoes.html — no clique do toggle "Notificações no
 *      Navegador", pede permissão (se preciso) e inscreve/desinscreve na
 *      hora, sem esperar o botão "Salvar Configurações".
 *
 * Precisa de `window.NOMDO_VAPID_PUBLIC_KEY` e `window.NOMDO_CSRF_TOKEN`
 * já definidos antes deste script (ver base_dash.html).
 */

(function () {
  function suportado() {
    return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  }

  // Converte a chave pública VAPID (base64url) pro formato binário que
  // `pushManager.subscribe` espera.
  function urlBase64ParaUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  async function registrarServiceWorker() {
    if (!suportado()) return null;
    try {
      return await navigator.serviceWorker.register("/sw.js");
    } catch (e) {
      console.error("Falha ao registrar o Service Worker do Nomdo:", e);
      return null;
    }
  }

  async function enviarAoServidor(url, corpo) {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": window.NOMDO_CSRF_TOKEN || "",
      },
      body: JSON.stringify(corpo || {}),
    });
    return resp.json().catch(() => ({}));
  }

  // Pede permissão (se ainda não decidida) + assina o push + manda a
  // assinatura pro servidor salvar. Só mostra o prompt de permissão do
  // navegador quando chamado a partir de um gesto do usuário (ex: clique
  // no toggle) — em outros contextos, navegadores modernos já ignoram/
  // bloqueiam o prompt automaticamente se não for assim.
  async function inscrever() {
    if (!suportado()) {
      return { success: false, message: "Este navegador não suporta notificações push." };
    }

    let permissao = Notification.permission;
    if (permissao === "default") {
      permissao = await Notification.requestPermission();
    }
    if (permissao !== "granted") {
      return { success: false, message: "Permissão de notificação negada." };
    }

    if (!window.NOMDO_VAPID_PUBLIC_KEY) {
      return { success: false, message: "Chave pública VAPID não configurada no servidor." };
    }

    const registro = await registrarServiceWorker();
    if (!registro) {
      return { success: false, message: "Não foi possível registrar o Service Worker." };
    }

    let assinatura = await registro.pushManager.getSubscription();
    if (!assinatura) {
      assinatura = await registro.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ParaUint8Array(window.NOMDO_VAPID_PUBLIC_KEY),
      });
    }

    const resultado = await enviarAoServidor("/push/subscribe", assinatura.toJSON());
    return resultado;
  }

  // Confere se este navegador já tem uma inscrição de push ATIVA de
  // verdade (Service Worker registrado + PushManager.getSubscription()
  // preenchido) — diferente de só olhar `NOMDO_NOTIFY_BROWSER`, que é só
  // a preferência salva no banco (pode estar "true" por padrão numa conta
  // nova, sem o navegador ter concluído a inscrição de fato).
  async function jaInscrito() {
    if (!suportado()) return false;
    if (Notification.permission !== "granted") return false;
    try {
      const registro = await navigator.serviceWorker.getRegistration("/sw.js");
      if (!registro) return false;
      const assinatura = await registro.pushManager.getSubscription();
      return !!assinatura;
    } catch (e) {
      return false;
    }
  }

  async function desinscrever() {
    if (!suportado()) return { success: true };

    const registro = await navigator.serviceWorker.getRegistration("/sw.js");
    if (!registro) return { success: true };

    const assinatura = await registro.pushManager.getSubscription();
    if (!assinatura) return { success: true };

    const endpoint = assinatura.endpoint;
    await assinatura.unsubscribe();
    return enviarAoServidor("/push/unsubscribe", { endpoint });
  }

  // Chamado em toda página autenticada (base_dash.html) — só re-inscreve
  // silenciosamente se o usuário JÁ tinha concedido permissão antes E o
  // toggle continua ligado, pra manter a assinatura viva (ex: depois de
  // limpar dados do navegador ou trocar de aparelho). Nunca pede
  // permissão sozinho aqui.
  async function garantirInscricaoSeJaPermitido() {
    if (!suportado()) return;
    if (Notification.permission !== "granted") return;
    if (!window.NOMDO_NOTIFY_BROWSER) return;

    try {
      const registro = await registrarServiceWorker();
      if (!registro) return;
      const existente = await registro.pushManager.getSubscription();
      if (existente) return; // já inscrito, nada a fazer

      if (!window.NOMDO_VAPID_PUBLIC_KEY) return;
      const nova = await registro.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ParaUint8Array(window.NOMDO_VAPID_PUBLIC_KEY),
      });
      await enviarAoServidor("/push/subscribe", nova.toJSON());
    } catch (e) {
      console.warn("Não foi possível renovar a inscrição de push automaticamente:", e);
    }
  }

  window.NomdoPush = {
    suportado,
    inscrever,
    desinscrever,
    jaInscrito,
    garantirInscricaoSeJaPermitido,
  };
})();
