/**
 * Endereço do backend Flask (o mesmo projeto Nomdo, na raiz deste repo, rodando
 * localmente na sua máquina).
 *
 * O Flask já está configurado em wsgi.py pra escutar em host="0.0.0.0",
 * porta 5000 — ou seja, ele já aceita conexões de outros dispositivos na
 * mesma rede, sem precisar de ngrok/túnel.
 *
 * Pra descobrir o IP da sua máquina na rede local:
 *   Windows -> abra o cmd e rode `ipconfig`, procure "Endereço IPv4"
 *   (algo como 192.168.1.8).
 *
 * Depois substitua abaixo pelo seu IP real (mantendo a porta 5000) e
 * garanta que o celular está na MESMA rede Wi-Fi que o computador. Se não
 * conectar, o motivo mais comum é o Firewall do Windows bloqueando a
 * porta 5000 — permita "Python" (ou a porta 5000) no Firewall do Windows
 * Defender.
 */
export const API_BASE_URL = "http://192.168.1.8:5000";
