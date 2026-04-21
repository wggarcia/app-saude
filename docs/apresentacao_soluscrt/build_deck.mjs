import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUT = "/Users/angelica/backend/docs/apresentacao_soluscrt/soluscrt_palestra.pptx";
const W = 1280;
const H = 720;

const COLORS = {
  bg: "#06111B",
  bg2: "#0C2232",
  panel: "#0F2A3B",
  panel2: "#12384B",
  cyan: "#32E6D0",
  blue: "#74C0FC",
  yellow: "#FFD166",
  red: "#FF5574",
  white: "#EAF6FF",
  muted: "#9CC4DB",
};

const FONT = {
  title: "Poppins",
  body: "Lato",
};

const deck = Presentation.create({ slideSize: { width: W, height: H } });

function addBg(slide) {
  slide.background.fill = {
    color: COLORS.bg,
  };
  slide.shapes.add({
    geometry: "rect",
    position: { left: 0, top: 0, width: W, height: H },
    fill: {
      type: "gradient",
      stops: [
        { color: COLORS.bg, position: 0 },
        { color: COLORS.bg2, position: 65000 },
        { color: "#02070D", position: 100000 },
      ],
      angle: 25,
    },
    line: { width: 0, fill: COLORS.bg },
  });
  for (let i = 0; i < 10; i++) {
    slide.shapes.add({
      geometry: "ellipse",
      position: {
        left: 820 + i * 26,
        top: 60 + i * 18,
        width: 220 - i * 10,
        height: 220 - i * 10,
      },
      fill: `${COLORS.cyan}${Math.max(10, 32 - i * 2).toString(16).padStart(2, "0")}`,
      line: { width: 0, fill: COLORS.cyan },
    });
  }
}

function text(slide, value, x, y, w, h, opts = {}) {
  const s = slide.shapes.add({
    geometry: "rect",
    position: { left: x, top: y, width: w, height: h },
    fill: "#00000000",
    line: { width: 0, fill: "#00000000" },
  });
  s.text = value;
  s.text.typeface = opts.typeface || FONT.body;
  s.text.fontSize = opts.size || 24;
  s.text.color = opts.color || COLORS.white;
  s.text.bold = Boolean(opts.bold);
  s.text.alignment = opts.align || "left";
  s.text.verticalAlignment = opts.valign || "top";
  s.text.insets = { left: 4, right: 4, top: 4, bottom: 4 };
  return s;
}

function title(slide, value, subtitle = "") {
  text(slide, value, 70, 62, 850, 92, { typeface: FONT.title, size: 46, bold: true });
  if (subtitle) text(slide, subtitle, 74, 150, 770, 58, { size: 20, color: COLORS.muted });
}

function pill(slide, value, x, y, color = COLORS.cyan) {
  const p = slide.shapes.add({
    geometry: "roundRect",
    position: { left: x, top: y, width: 190, height: 36 },
    adjustmentList: [{ name: "adj", formula: "val 50000" }],
    fill: `${color}22`,
    line: { width: 1.2, fill: `${color}88` },
  });
  p.text = value;
  p.text.typeface = FONT.body;
  p.text.fontSize = 15;
  p.text.bold = true;
  p.text.color = color;
  p.text.alignment = "center";
  p.text.verticalAlignment = "middle";
}

function card(slide, x, y, w, h, head, body, accent = COLORS.cyan) {
  slide.shapes.add({
    geometry: "roundRect",
    position: { left: x, top: y, width: w, height: h },
    adjustmentList: [{ name: "adj", formula: "val 18000" }],
    fill: `${COLORS.panel}DD`,
    line: { width: 1, fill: `${accent}55` },
  });
  slide.shapes.add({
    geometry: "rect",
    position: { left: x, top: y, width: 7, height: h },
    fill: accent,
    line: { width: 0, fill: accent },
  });
  text(slide, head, x + 22, y + 18, w - 44, 32, { size: 21, bold: true, color: COLORS.white });
  text(slide, body, x + 22, y + 58, w - 44, h - 70, { size: 17, color: COLORS.muted });
}

function bullets(slide, items, x, y, w, gap = 54) {
  items.forEach((item, i) => {
    const cy = y + i * gap;
    slide.shapes.add({
      geometry: "ellipse",
      position: { left: x, top: cy + 8, width: 16, height: 16 },
      fill: COLORS.cyan,
      line: { width: 0, fill: COLORS.cyan },
    });
    text(slide, item, x + 30, cy, w - 30, 38, { size: 22, color: COLORS.white });
  });
}

function footer(slide, n) {
  text(slide, `SolusCRT Saude | ${n}`, 70, 665, 260, 30, { size: 13, color: "#6F91A6" });
}

function addSlide(n, headline, subtitle, content) {
  const slide = deck.slides.add();
  addBg(slide);
  title(slide, headline, subtitle);
  content(slide);
  footer(slide, n);
}

addSlide(1, "SolusCRT Saude", "Sala de controle epidemiologica com IA para antecipar riscos e orientar decisoes.", (s) => {
  pill(s, "App populacional", 78, 238);
  pill(s, "IA epidemiologica", 290, 238, COLORS.blue);
  pill(s, "Fontes oficiais", 502, 238, COLORS.yellow);
  text(s, "Transformamos sintomas da populacao e dados oficiais em decisao territorial antes que o risco vire crise.", 78, 320, 780, 120, { size: 34, bold: true, typeface: FONT.title });
  card(s, 910, 300, 260, 180, "Mensagem central", "Antecipar, coordenar e proteger.", COLORS.cyan);
});

addSlide(2, "O problema", "A resposta tradicional chega tarde quando os sinais ja estao espalhados.", (s) => {
  bullets(s, ["Surtos sao percebidos tarde", "Empresas sofrem com afastamentos", "Farmacias perdem previsibilidade", "Hospitais recebem pressao inesperada", "Governo precisa agir com evidencias"], 90, 245, 700, 58);
  card(s, 850, 250, 300, 230, "Ponto critico", "O desafio nao e apenas coletar dados. E transformar sinais dispersos em acao rapida.", COLORS.red);
});

addSlide(3, "A solucao", "Uma plataforma unica para populacao, empresas, hospitais, farmacias e governo.", (s) => {
  card(s, 80, 235, 330, 150, "App gratuito", "A populacao envia sintomas e acompanha alertas da propria regiao.", COLORS.cyan);
  card(s, 475, 235, 330, 150, "Mapa de risco", "Focos por bairro, municipio, estado e tendencia temporal.", COLORS.blue);
  card(s, 870, 235, 330, 150, "IA e fontes oficiais", "Classificacao de sinais, crescimento e cruzamento com bases brasileiras.", COLORS.yellow);
});

addSlide(4, "Como funciona", "Do sintoma individual ao painel de decisao territorial.", (s) => {
  const steps = ["Envio no app", "Antifraude", "IA classifica", "Mapa mostra foco", "Organizacao age"];
  steps.forEach((step, i) => {
    const x = 80 + i * 230;
    card(s, x, 285, 185, 140, `${i + 1}. ${step}`, i === 0 ? "Sinal colaborativo" : i === 1 ? "Rede, aparelho e confianca" : i === 2 ? "Padrao epidemiologico" : i === 3 ? "Bairro, cidade e estado" : "Alerta e resposta", i % 2 ? COLORS.blue : COLORS.cyan);
    if (i < steps.length - 1) text(s, "→", x + 190, 326, 40, 50, { size: 36, color: COLORS.yellow, bold: true });
  });
});

addSlide(5, "Mapa de risco", "O mapa nao e estetica. Ele e decisao territorial.", (s) => {
  card(s, 80, 230, 270, 210, "Territorio", "Bairro, municipio, estado e recorte regional.", COLORS.cyan);
  card(s, 390, 230, 270, 210, "Crescimento", "Percentual, tendencia e nivel de risco.", COLORS.yellow);
  card(s, 700, 230, 270, 210, "Decaimento", "10 dias estaveis e reducao gradual ate 30 dias sem novos sinais.", COLORS.blue);
  card(s, 1010, 230, 170, 210, "Foco", "Ponto, area ou camada de calor.", COLORS.red);
});

addSlide(6, "Brasil Oficial", "Sinal colaborativo antecipa. Fonte oficial valida e contextualiza.", (s) => {
  bullets(s, ["IBGE/SIDRA: populacao e denominadores", "InfoDengue/Fiocruz: arboviroses", "InfoGripe/Fiocruz: SRAG e respiratorio", "OpenDataSUS e DATASUS: bases institucionais", "SINAN, SIM, SIH e SIVEP-Gripe catalogados"], 90, 230, 840, 56);
  card(s, 925, 275, 250, 185, "Regra de ouro", "Nao misturar sinal colaborativo com caso oficial confirmado.", COLORS.yellow);
});

addSlide(7, "Valor para empresas", "Saude ocupacional e continuidade operacional.", (s) => {
  card(s, 90, 245, 320, 160, "Reduzir afastamentos", "Monitorar crescimento de sintomas antes de uma onda interna.", COLORS.cyan);
  card(s, 480, 245, 320, 160, "Filiais e regioes", "Comparar risco por unidade, cidade e territorio.", COLORS.blue);
  card(s, 870, 245, 320, 160, "Planos B2B", "A partir de R$ 799/mes conforme pacote.", COLORS.yellow);
});

addSlide(8, "Valor para farmacias", "Estoque orientado por risco epidemiologico.", (s) => {
  card(s, 100, 245, 300, 170, "Demanda por bairro", "Ver onde sintomas crescem e ajustar abastecimento.", COLORS.cyan);
  card(s, 490, 245, 300, 170, "Classes de sintomas", "Respiratorio, arboviroses, febre, dor e cansaco.", COLORS.blue);
  card(s, 880, 245, 300, 170, "Pacotes", "Farmacia Local e Rede Farmaceutica Regional.", COLORS.yellow);
});

addSlide(9, "Valor para hospitais", "Preparar pronto atendimento antes da pressao chegar.", (s) => {
  bullets(s, ["Antecipar demanda por triagem", "Monitorar SRAG e arboviroses", "Preparar leitos e equipes", "Apoiar plano de contingencia"], 100, 250, 680, 62);
  card(s, 850, 265, 300, 190, "Oferta", "Hospital Medio e Rede Hospitalar com monitoramento territorial.", COLORS.red);
});

addSlide(10, "Valor para governo", "Ambiente separado, institucional e protegido.", (s) => {
  card(s, 80, 230, 330, 165, "Contrato anual fechado", "Governo nao e mensalidade simples. Ha escopo, SLA e governanca.", COLORS.yellow);
  card(s, 475, 230, 330, 165, "Alertas oficiais", "Governo emite comunicados para o app da populacao.", COLORS.cyan);
  card(s, 870, 230, 330, 165, "Sala de controle", "Monitoramento por populacao coberta, territorio e fontes oficiais.", COLORS.blue);
});

addSlide(11, "Seguranca e LGPD", "Confianca e parte do produto.", (s) => {
  bullets(s, ["Dados agregados e finalidade epidemiologica", "Controle de dispositivos e usuarios", "Sessao unica por usuario", "Antifraude no envio populacional", "Auditoria e separacao de ambientes"], 90, 230, 850, 56);
  card(s, 930, 275, 230, 170, "Mensagem", "Monitoramos risco territorial, nao expomos pessoas.", COLORS.cyan);
});

addSlide(12, "Modelo comercial", "Preco por valor entregue, setor e cobertura.", (s) => {
  card(s, 80, 225, 250, 180, "Empresas", "A partir de R$ 799/mes.", COLORS.cyan);
  card(s, 360, 225, 250, 180, "Farmacias", "A partir de R$ 699/mes.", COLORS.blue);
  card(s, 640, 225, 250, 180, "Hospitais", "A partir de R$ 12 mil/mes.", COLORS.red);
  card(s, 920, 225, 250, 180, "Governo", "Contrato anual a partir de R$ 120 mil/ano.", COLORS.yellow);
});

addSlide(13, "Frase de impacto", "Para fechar a apresentacao.", (s) => {
  text(s, "O SolusCRT transforma sintomas da populacao e dados oficiais em decisao territorial antes que o risco vire crise.", 110, 250, 1020, 160, { size: 42, bold: true, typeface: FONT.title, align: "center" });
  pill(s, "Antecipar", 330, 470, COLORS.cyan);
  pill(s, "Coordenar", 545, 470, COLORS.blue);
  pill(s, "Proteger", 760, 470, COLORS.yellow);
});

addSlide(14, "Proximo passo", "Diagnostico, escopo e implantacao assistida.", (s) => {
  bullets(s, ["Reuniao de diagnostico", "Definicao de setor e territorio", "Escolha do pacote ou contrato anual", "Implantacao assistida", "Treinamento e acompanhamento dos primeiros indicadores"], 120, 230, 850, 58);
  card(s, 930, 300, 230, 150, "Chamada final", "Vamos antecipar o risco antes que ele vire crise.", COLORS.cyan);
});

const pptx = await PresentationFile.exportPptx(deck);
await pptx.save(OUT);
console.log(OUT);
