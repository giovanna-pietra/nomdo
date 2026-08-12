/**
 * Design tokens extraídos direto do site (app/static/css/style_dashboard.css
 * e style_login.css), pra manter as telas do app com a mesma identidade
 * visual do site responsivo — mesmas cores, mesmos raios de borda, mesma
 * fonte da marca (Poppins).
 *
 * Pra usar a fonte Poppins de verdade (e não só o fallback do sistema),
 * baixe os arquivos em https://fonts.google.com/specimen/Poppins e link
 * como fonte nativa (assets/fonts + react-native.config.js -> depois
 * `npx react-native-asset` ou, no bare workflow, coloque os .ttf em
 * android/app/src/main/assets/fonts e ios (via Xcode) e adicione ao
 * Info.plist/UIAppFonts). Até isso ser feito, cai no fallback do sistema.
 */

export const cores = {
  primaria: "#0052D4",
  primariaClara: "rgba(0,82,212,0.10)",
  acento: "#6FB1FC",
  fundo: "#f8f9fa",
  cardFundo: "#ffffff",
  borda: "#edebe9",
  textoMuted: "#605e5c",
  textoEscuro: "#323130",
  perigo: "#dc2626",
  perigoClaro: "rgba(220,38,38,0.08)",
  sucesso: "#16a34a",
  aviso: "#f59e0b",
};

export const raio = {
  sm: 8,
  md: 12,
  lg: 16,
  pill: 50,
  circulo: 999,
};

export const espaco = {
  xs: 6,
  sm: 10,
  md: 16,
  lg: 20,
  xl: 24,
};

export const fontes = {
  base: "Poppins-Regular",
  medio: "Poppins-Medium",
  semiNegrito: "Poppins-SemiBold",
  negrito: "Poppins-Bold",
};

export const sombraCard = {
  shadowColor: "#000",
  shadowOpacity: 0.05,
  shadowRadius: 8,
  shadowOffset: { width: 0, height: 4 },
  elevation: 2,
};
