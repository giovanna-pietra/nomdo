/**
 * Endereço do backend Flask.
 *
 * Agora apontando pro deploy em produção no Render — funciona de
 * qualquer rede (Wi-Fi, dados móveis), sem depender de IP local, ngrok
 * ou de deixar o computador ligado rodando o Flask.
 *
 * Se precisar voltar a testar contra o Flask rodando localmente na sua
 * máquina (útil pra depurar algo antes de subir pro Render), troque
 * temporariamente pelo IP da sua máquina na rede local, ex.:
 *   export const API_BASE_URL = "http://192.168.1.8:5000";
 * (descobre o IP com `ipconfig` no cmd, procurando "Endereço IPv4"; o
 * celular precisa estar na mesma rede Wi-Fi do computador nesse caso).
 */
export const API_BASE_URL = "https://nomdo.onrender.com";
