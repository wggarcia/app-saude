import 'package:flutter/material.dart';

import '../../servicos/location_service.dart';
import '../../servicos/public_api_service.dart';
import '../../servicos/regiao_base_service.dart';
import '../../tela_resultado.dart';
import '../fontes/tela_fontes.dart';

// ─── Modelo de pergunta de sintoma ────────────────────────────────────────────
class _PerguntaSintoma {
  const _PerguntaSintoma({
    required this.key,
    required this.pergunta,
    required this.dica,
    this.emoji = '',
    this.isUrgencia = false,
    this.followup, // 'febre' | 'articular'
    this.condicionaisDe = const [], // só aparece se ALGUM destes foi "Sim"
  });
  final String key;
  final String pergunta;
  final String dica;
  final String emoji;
  final bool isUrgencia;
  final String? followup;

  // Perguntas de desempate: só fazem sentido se a "porta" foi aberta. Quem não
  // tem bolhinhas nunca vê pergunta sobre bolhinhas — o formulário fica mais
  // fundo sem ficar mais longo.
  //
  // É uma lista porque um mesmo achado pode servir a duas portas: suor noturno
  // discrimina tanto na tosse (tuberculose) quanto no emagrecimento
  // (tuberculose × leishmaniose), e febre que baixou e voltou discrimina na
  // febre (dengue) e na icterícia (febre amarela). Vazia = pergunta fixa.
  final List<String> condicionaisDe;
}

// ─── Perguntas de sintomas — ordem clínica neutra, sem nome de doença ────────
// Agrupamento por tipo (geral → respiratório → gastrointestinal → urgência)
// mas SEM rótulo de doença. Elimina o viés de ancoragem.
const _perguntas = [
  _PerguntaSintoma(
    key: 'febre',
    pergunta: 'Você tem ou teve febre?',
    dica: 'Temperatura acima de 37,5°C nas últimas 24 horas',
    emoji: '🌡️',
    followup: 'febre',
  ),
  // ── Desempate: febre em ciclos → Malária ────────────────────────────────
  _PerguntaSintoma(
    key: 'febre_ciclica',
    pergunta: 'A febre vem em ciclos — calafrio forte, depois febre, depois suor?',
    dica: 'Episódios que se repetem com hora quase marcada, com melhora entre eles',
    emoji: '🔁',
    condicionaisDe: ['febre'],
  ),
  _PerguntaSintoma(
    key: 'cansaco',
    pergunta: 'Sente cansaço intenso?',
    dica: 'Fadiga que dificulta suas atividades normais',
    emoji: '😴',
  ),
  _PerguntaSintoma(
    key: 'dor_corpo',
    pergunta: 'Tem dor no corpo?',
    dica: 'Dores musculares generalizadas — mialgia',
    emoji: '💪',
  ),
  _PerguntaSintoma(
    key: 'dor_cabeca',
    pergunta: 'Tem dor de cabeça?',
    dica: 'Cefaleia — pode ser intensa ou persistente',
    emoji: '🤕',
  ),
  _PerguntaSintoma(
    key: 'calafrios',
    pergunta: 'Teve calafrios ou tremores com sensação de frio?',
    dica: 'Mesmo com febre — sensação de frio intenso com tremores',
    emoji: '🥶',
  ),
  _PerguntaSintoma(
    key: 'sudorese',
    pergunta: 'Tem suado muito?',
    dica: 'Sudorese intensa, especialmente à noite ou após calafrios',
    emoji: '💧',
  ),
  _PerguntaSintoma(
    key: 'tosse',
    pergunta: 'Tem tosse?',
    dica: 'Seca, com catarro ou persistente',
    emoji: '🫁',
  ),
  // ── Desempate: tosse → Tuberculose × Coqueluche ─────────────────────────
  _PerguntaSintoma(
    key: 'tosse_mais_3_semanas',
    pergunta: 'Está tossindo há mais de 3 semanas?',
    dica: 'Conte desde o primeiro dia de tosse, mesmo que tenha melhorado no meio',
    emoji: '📅',
    condicionaisDe: ['tosse'],
  ),
  _PerguntaSintoma(
    key: 'tosse_paroxistica',
    pergunta: 'A tosse vem em acessos seguidos, com guincho ou vômito no fim?',
    dica: 'Crises em que não consegue respirar entre uma tosse e outra',
    emoji: '😤',
    condicionaisDe: ['tosse'],
  ),
  _PerguntaSintoma(
    key: 'falta_ar',
    pergunta: 'Tem falta de ar?',
    dica: 'Dificuldade para respirar — mesmo em repouso ou ao menor esforço',
    emoji: '💨',
  ),
  // ── Desempate: falta de ar → Hantavirose × causa cardíaca ───────────────
  _PerguntaSintoma(
    key: 'dispneia_subita_pos_febre',
    pergunta: 'A falta de ar começou de repente, poucos dias depois da febre?',
    dica: 'De uma hora para outra, e não aos poucos',
    emoji: '⏱️',
    condicionaisDe: ['falta_ar'],
  ),
  _PerguntaSintoma(
    key: 'dispneia_piora_deitado',
    pergunta: 'A falta de ar piora quando você deita?',
    dica: 'Precisa de travesseiro alto ou de sentar para respirar melhor',
    emoji: '🛏️',
    condicionaisDe: ['falta_ar'],
  ),
  _PerguntaSintoma(
    key: 'dor_garganta',
    pergunta: 'Tem dor de garganta?',
    dica: 'Ao engolir ou em repouso',
    emoji: '😮',
  ),
  // ── Desempate: dor de garganta → Difteria ───────────────────────────────
  _PerguntaSintoma(
    key: 'placa_na_garganta',
    pergunta: 'Tem placa branca ou acinzentada na garganta?',
    dica: 'Uma casca grudada na garganta ou nas amígdalas, difícil de soltar',
    emoji: '🗣️',
    condicionaisDe: ['dor_garganta'],
  ),
  _PerguntaSintoma(
    key: 'pescoco_inchado',
    pergunta: 'O pescoço está inchado dos dois lados?',
    dica: 'Pescoço visivelmente mais grosso, não só um caroço',
    emoji: '🧣',
    condicionaisDe: ['dor_garganta'],
  ),
  _PerguntaSintoma(
    key: 'coriza',
    pergunta: 'Está com coriza?',
    dica: 'Nariz escorrendo ou entupido, espirros frequentes',
    emoji: '🤧',
  ),
  _PerguntaSintoma(
    key: 'perda_olfato_paladar',
    pergunta: 'Perdeu o olfato ou o paladar?',
    dica: 'Não sente cheiro ou sabor como antes',
    emoji: '👃',
  ),
  _PerguntaSintoma(
    key: 'dor_articular',
    pergunta: 'Tem dor nas articulações?',
    dica: 'Joelhos, tornozelos, pulsos, dedos',
    emoji: '🦴',
    followup: 'articular',
  ),
  // ── Desempate: dor articular → Chikungunya ──────────────────────────────
  _PerguntaSintoma(
    key: 'artralgia_simetrica',
    pergunta: 'A dor pega os dois lados ao mesmo tempo — as duas mãos, os dois pés?',
    dica: 'Mesmas juntas dos dois lados do corpo',
    emoji: '🤝',
    condicionaisDe: ['dor_articular'],
  ),
  _PerguntaSintoma(
    key: 'artralgia_mais_2_semanas',
    pergunta: 'A dor nas juntas já dura mais de 2 semanas?',
    dica: 'Mesmo que tenha melhorado e voltado',
    emoji: '📆',
    condicionaisDe: ['dor_articular'],
  ),
  _PerguntaSintoma(
    key: 'exantema',
    pergunta: 'Surgiram manchas ou vermelhidão na pele?',
    dica: 'Rash, bolinhas, manchas espalhadas — pode coçar',
    emoji: '🔴',
  ),
  // ── Desempate: manchas → Sarampo × Zika × Dengue × Febre Maculosa ───────
  _PerguntaSintoma(
    key: 'exantema_craniocaudal',
    pergunta: 'As manchas começaram no rosto e foram descendo pelo corpo?',
    dica: 'Primeiro rosto e pescoço, depois tronco, depois pernas',
    emoji: '⬇️',
    condicionaisDe: ['exantema'],
  ),
  _PerguntaSintoma(
    key: 'exantema_pruriginoso',
    pergunta: 'As manchas coçam muito?',
    dica: 'Coceira forte, a ponto de atrapalhar o sono',
    emoji: '🖐️',
    condicionaisDe: ['exantema'],
  ),
  _PerguntaSintoma(
    key: 'exantema_palmo_plantar',
    pergunta: 'Tem manchas nas palmas das mãos ou nas plantas dos pés?',
    dica: 'Olhe as duas mãos e os dois pés antes de responder',
    emoji: '✋',
    condicionaisDe: ['exantema'],
  ),
  _PerguntaSintoma(
    key: 'exantema_apos_febre',
    pergunta: 'As manchas apareceram quando a febre baixou?',
    dica: 'Primeiro a febre passou, depois surgiram as manchas',
    emoji: '🌡️',
    condicionaisDe: ['exantema'],
  ),
  _PerguntaSintoma(
    key: 'conjuntivite',
    pergunta: 'Os olhos estão vermelhos ou irritados?',
    dica: 'Hiperemia ocular — sem secreção purulenta amarelada',
    emoji: '👁️',
  ),
  _PerguntaSintoma(
    key: 'vomito_nausea',
    pergunta: 'Tem vômito ou náusea?',
    dica: 'Enjoo persistente ou episódios de vômito',
    emoji: '🤢',
  ),
  _PerguntaSintoma(
    key: 'diarreia',
    pergunta: 'Tem diarreia?',
    dica: 'Mais de 3 evacuações líquidas por dia',
    emoji: '🚽',
  ),
  // ── Desempate: diarreia → Cólera × disenteria × Febre Tifoide ───────────
  _PerguntaSintoma(
    key: 'fezes_agua_arroz',
    pergunta: 'As fezes estão muito aquosas, parecendo água de arroz?',
    dica: 'Líquidas e esbranquiçadas, quase sem resíduo',
    emoji: '🍚',
    condicionaisDe: ['diarreia'],
  ),
  _PerguntaSintoma(
    key: 'fezes_com_sangue',
    pergunta: 'As fezes têm sangue ou muco?',
    dica: 'Sangue vivo, fezes escuras como piche, ou catarro nas fezes',
    emoji: '🩸',
    condicionaisDe: ['diarreia'],
  ),
  _PerguntaSintoma(
    key: 'febre_alta_prolongada',
    pergunta: 'Está com febre alta contínua há mais de uma semana?',
    dica: 'Febre que quase não baixa, todos os dias',
    emoji: '🔥',
    condicionaisDe: ['diarreia'],
  ),
  _PerguntaSintoma(
    key: 'dor_abdominal',
    pergunta: 'Tem dor na barriga?',
    dica: 'Dor abdominal persistente ou em cólicas',
    emoji: '🫄',
  ),
  _PerguntaSintoma(
    key: 'ictericia',
    pergunta: 'A pele ou os olhos ficaram amarelados?',
    dica: 'Icterícia — coloração amarela na pele ou no branco dos olhos',
    emoji: '🟡',
  ),
  // ── Desempate: icterícia → Hepatite × Leptospirose × Febre Amarela ──────
  _PerguntaSintoma(
    key: 'urina_escura_fezes_claras',
    pergunta: 'A urina está escura e as fezes claras?',
    dica: 'Urina cor de Coca-Cola, fezes esbranquiçadas como massa de vidraceiro',
    emoji: '🧪',
    condicionaisDe: ['ictericia'],
  ),
  _PerguntaSintoma(
    key: 'dor_panturrilha',
    pergunta: 'Sente dor forte na batata da perna?',
    dica: 'Dor na panturrilha que piora ao apertar',
    emoji: '🦵',
    condicionaisDe: ['ictericia'],
  ),
  _PerguntaSintoma(
    key: 'febre_bifasica',
    pergunta: 'A febre baixou e voltou depois de um ou dois dias?',
    dica: 'Chegou a melhorar e então piorou de novo',
    emoji: '📉',
    condicionaisDe: ['febre', 'ictericia'],
  ),
  _PerguntaSintoma(
    key: 'manchas_hemorragicas',
    pergunta: 'Surgiram manchas roxas ou sangramentos?',
    dica: 'Petéquias, hematomas espontâneos ou sangramento sem corte',
    emoji: '🟣',
    isUrgencia: true,
  ),
  _PerguntaSintoma(
    key: 'rigidez_nuca',
    pergunta: 'Tem dificuldade de dobrar o pescoço?',
    dica: 'Rigidez — dificuldade de encostar o queixo no peito',
    emoji: '🚨',
    isUrgencia: true,
  ),
  // Phase 2 — doenças tropicais negligenciadas
  _PerguntaSintoma(
    key: 'hemoptise',
    pergunta: 'Tossiu sangue?',
    dica: 'Sangue ao tossir — pode ser um fio ou mais',
    emoji: '🩸',
    isUrgencia: true,
  ),
  _PerguntaSintoma(
    key: 'exantema_vesicular',
    pergunta: 'As manchas na pele têm bolhinhas com líquido?',
    dica: 'Bolinhas com líquido na pele — podem doer ou coçar',
    emoji: '💧',
  ),
  // ── Desempate: varicela × Mpox (só aparece se marcou bolhinhas) ──────────
  _PerguntaSintoma(
    key: 'vesicula_dolorosa',
    pergunta: 'As bolhinhas doem mais do que coçam?',
    dica: 'Pense no que incomoda mais: a dor ou a coceira',
    emoji: '😖',
    condicionaisDe: ['exantema_vesicular'],
  ),
  _PerguntaSintoma(
    key: 'linfonodo_aumentado',
    pergunta: 'Tem íngua — caroço no pescoço, axila ou virilha?',
    dica: 'Caroço que dói ao apertar, do tamanho de um grão de feijão ou maior',
    emoji: '🔘',
    // Duas portas: com bolhinhas separa Mpox de varicela; com febre e sem
    // bolhinhas é o bubão da peste, que o catálogo não alcançava.
    condicionaisDe: ['exantema_vesicular', 'febre'],
  ),
  _PerguntaSintoma(
    key: 'lesao_face_palmas',
    pergunta: 'Começou no rosto, ou apareceu nas palmas das mãos ou plantas dos pés?',
    dica: 'Onde surgiram as primeiras bolhinhas',
    emoji: '🤲',
    condicionaisDe: ['exantema_vesicular'],
  ),
  _PerguntaSintoma(
    key: 'vesiculas_estagios_variados',
    pergunta: 'Há bolhinhas novas e feridas já com casquinha ao mesmo tempo?',
    dica: 'Umas acabando de surgir enquanto outras já secaram',
    emoji: '🫧',
    condicionaisDe: ['exantema_vesicular'],
  ),
  _PerguntaSintoma(
    key: 'perda_peso',
    pergunta: 'Emagreceu sem dieta ou motivo aparente?',
    dica: 'Perda de peso involuntária nas últimas semanas',
    emoji: '⚖️',
  ),
  // ── Desempate: emagrecimento → Leishmaniose Visceral × Tuberculose ──────
  _PerguntaSintoma(
    key: 'barriga_inchada',
    pergunta: 'A barriga está inchada, ou sente um volume do lado esquerdo?',
    dica: 'Barriga crescendo sem ganhar peso, ou peso embaixo das costelas à esquerda',
    emoji: '🫃',
    condicionaisDe: ['perda_peso'],
  ),
  _PerguntaSintoma(
    key: 'sudorese_noturna',
    pergunta: 'Tem suor à noite que chega a molhar a roupa?',
    dica: 'Suor durante o sono, a ponto de precisar trocar de roupa ou lençol',
    emoji: '💦',
    condicionaisDe: ['tosse', 'perda_peso'],
  ),
  _PerguntaSintoma(
    key: 'ulcera_cutanea',
    pergunta: 'Tem uma ferida ou úlcera na pele que não cicatriza?',
    dica: 'Ferida com bordas elevadas, indolor — comum em áreas expostas',
    emoji: '🔵',
  ),
  // ── Desempate: úlcera → Leishmaniose Tegumentar ─────────────────────────
  _PerguntaSintoma(
    key: 'ulcera_indolor_bordas',
    pergunta: 'A ferida é indolor e tem as bordas elevadas?',
    dica: 'Não dói ao tocar, e a borda é mais alta que o fundo',
    emoji: '⭕',
    condicionaisDe: ['ulcera_cutanea'],
  ),
  _PerguntaSintoma(
    key: 'ulcera_mais_1_mes',
    pergunta: 'A ferida está aberta há mais de um mês?',
    dica: 'Sem cicatrizar, mesmo com pomada ou curativo',
    emoji: '🗓️',
    condicionaisDe: ['ulcera_cutanea'],
  ),
  _PerguntaSintoma(
    key: 'mancha_anestesia',
    pergunta: 'Tem mancha na pele sem sensibilidade ao toque?',
    dica: 'Mancha clara ou avermelhada que não sente quando tocada',
    emoji: '🟤',
  ),
];

// ─── Perguntas de anamnese epidemiológica ────────────────────────────────────
enum _TipoAnamnese { simNao, dias }

class _ItemAnamnese {
  const _ItemAnamnese({
    required this.tipo,
    required this.pergunta,
    required this.dica,
    this.emoji = '',
  });
  final _TipoAnamnese tipo;
  final String pergunta;
  final String dica;
  final String emoji;
}

const _anamneseItems = [
  _ItemAnamnese(
    tipo: _TipoAnamnese.dias,
    pergunta: 'Há quantos dias com esses sintomas?',
    dica: 'Desde o primeiro sinal — mesmo que leve',
    emoji: '📅',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'O início foi repentino?',
    dica: 'Abrupto (do nada) ou gradual (ao longo de dias)',
    emoji: '⚡',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Viajou para Amazônia, pantanal ou zona de mata?',
    dica: 'Nas últimas 4 semanas',
    emoji: '🌿',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Teve contato com água de enchente ou esgoto?',
    dica: 'Wading, limpeza pós-enchente, rua alagada',
    emoji: '🌊',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Teve contato com ratos ou animais silvestres?',
    dica: 'Fezes, urina ou toque — rural ou urbano',
    emoji: '🐭',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Esteve próximo de alguém com doença confirmada?',
    dica: 'Convívio doméstico ou contato próximo nas últimas 2 semanas',
    emoji: '👥',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Está vacinado para Febre Amarela?',
    dica: 'Vacina em dia reduz probabilidade quase a zero',
    emoji: '💉',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Tem diabetes?',
    dica: 'Diabetes tipo 1 ou tipo 2, mesmo controlada com medicamento',
    emoji: '🩸',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Tem pressão alta (hipertensão)?',
    dica: 'Mesmo que esteja tomando remédio e esteja controlada',
    emoji: '💊',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Tem doença pulmonar, asma ou DPOC?',
    dica: 'Asma, bronquite crônica, enfisema ou qualquer doença respiratória crônica',
    emoji: '🫁',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Tem imunossupressão ou faz tratamento oncológico?',
    dica: 'Quimioterapia, transplante, HIV, uso de corticoide por longa data',
    emoji: '🏥',
  ),
  // Phase 2 — vetores específicos
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Teve contato com carrapatos?',
    dica: 'Carrapato-estrela — zona rural, mato, fazenda, capim alto',
    emoji: '🕷️',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Viu ou tocou um barbeiro (percevejo preto)?',
    dica: 'Inseto preto achatado que pica à noite — Doença de Chagas',
    emoji: '🦟',
  ),
  // Mordedura de animal. Vale por si, independentemente da classificação: a
  // profilaxia antirrábica é tempo-dependente, e quem responde "sim" aqui
  // precisa procurar serviço de saúde mesmo que nada mais no quadro aponte
  // raiva. É também o único caminho pelo qual a Raiva Humana pode ser
  // alcançada — sem exposição, o catálogo nunca chegaria nela.
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Foi mordido, arranhado ou lambido por algum animal?',
    dica: 'Cão, gato, morcego, macaco ou animal silvestre — nos últimos meses',
    emoji: '🐕',
  ),
];

// ─── Tela principal ───────────────────────────────────────────────────────────
class TelaSintomas extends StatefulWidget {
  const TelaSintomas({super.key, this.onSintomasEnviados});

  final VoidCallback? onSintomasEnviados;

  @override
  State<TelaSintomas> createState() => _TelaSintomasState();
}

class _TelaSintomasState extends State<TelaSintomas> {
  // ── Fase: 0=sintomas, 1=anamnese ──
  int _fase = 0;
  int _index = 0;

  // null = aguardando followup de intensidade
  String? _followupAtivo; // 'febre' | 'articular'

  // Após o último item de anamnese → pronto para enviar
  bool _concluido = false;

  // ── Estado dos sintomas (todos inicializam false) ──
  final Map<String, bool> _sintomas = {
    for (final p in _perguntas) p.key: false,
  };
  String? _intensidadeFebre;
  String? _intensidadeArticular;

  // ── Estado da anamnese ──
  int? _diasSintomas;
  bool? _inicioAbrupto;
  bool? _viagemAreaEndemica;
  bool? _exposicaoAguaEnchente;
  bool? _contatoRoedores;
  bool? _contatoConfirmado;
  bool? _vacinadoFebreAmarela;
  bool? _temDiabetes;
  bool? _temHipertensao;
  bool? _temDoencaPulmonar;
  bool? _temImunossupressao;
  // Phase 2
  bool? _exposicaoCarrapato;
  bool? _exposicaoTriatomideo;
  bool? _mordeduraAnimal;

  // Computed: true se qualquer condição crônica foi marcada Sim
  bool? get _temComorbidade {
    final respostas = [_temDiabetes, _temHipertensao, _temDoencaPulmonar, _temImunossupressao];
    if (respostas.every((r) => r == null)) return null;
    return respostas.any((r) => r == true);
  }

  // ── Envio ──
  bool _loading = false;
  Map<String, dynamic>? _lastResult;

  // ── Cooldown: 1 envio por 24 h ──
  Duration? _cooldown;

  // ── Totais ──
  // Respostas de desempate ficam FORA de _sintomas: não são sintomas, são
  // qualificadores. E só o que foi perguntado entra aqui — o que não entrar vai
  // ausente para o backend, onde null significa "não perguntado", diferente de
  // "não". Foi o erro das comorbidades, que viravam um único booleano.
  final Map<String, bool> _desempate = {};

  bool _perguntaVisivel(_PerguntaSintoma p) =>
      p.condicionaisDe.isEmpty ||
      p.condicionaisDe.any((porta) => _sintomas[porta] ?? false);

  int get _totalSintomas => _sintomas.values.where((v) => v).length;

  // ── Progresso global ──
  int get _progressoAtual =>
      _fase == 0
          ? _perguntas.take(_index).where(_perguntaVisivel).length
          : (_perguntasVisiveis + _index);

  int get _perguntasVisiveis => _perguntas.where(_perguntaVisivel).length;

  // Total conta só o que ESTA pessoa vai ver. Mostrar "1 de 42" para quem vai
  // responder 38 desanima no meio do caminho, e o número muda sozinho quando
  // uma porta abre — que é honesto: a entrevista realmente ficou maior.
  int get _progressoTotal => _perguntasVisiveis + _anamneseItems.length;

  int _ultimaPerguntaVisivel() {
    for (var i = _perguntas.length - 1; i >= 0; i--) {
      if (_perguntaVisivel(_perguntas[i])) return i;
    }
    return 0;
  }

  // ── Limpar tudo ──
  void _limparTudo() {
    setState(() {
      for (final key in _sintomas.keys) {
        _sintomas[key] = false;
      }
      _desempate.clear();
      _intensidadeFebre = null;
      _intensidadeArticular = null;
      _diasSintomas = null;
      _inicioAbrupto = null;
      _viagemAreaEndemica = null;
      _exposicaoAguaEnchente = null;
      _contatoRoedores = null;
      _contatoConfirmado = null;
      _vacinadoFebreAmarela = null;
      _temDiabetes = null;
      _temHipertensao = null;
      _temDoencaPulmonar = null;
      _temImunossupressao = null;
      _exposicaoCarrapato = null;
      _exposicaoTriatomideo = null;
      _mordeduraAnimal = null;
      _lastResult = null;
      _fase = 0;
      _index = 0;
      _followupAtivo = null;
      _concluido = false;
    });
  }

  // ── Navegar para próxima pergunta ──
  void _avancar() {
    setState(() {
      _followupAtivo = null;
      if (_fase == 0) {
        // Pula o que a porta não abriu (ex.: perguntas de bolhinhas para quem
        // não tem bolhinhas).
        var prox = _index + 1;
        while (prox < _perguntas.length && !_perguntaVisivel(_perguntas[prox])) {
          prox++;
        }
        if (prox < _perguntas.length) {
          _index = prox;
        } else {
          _fase = 1;
          _index = 0;
        }
      } else {
        if (_index < _anamneseItems.length - 1) {
          _index++;
        } else {
          _concluido = true;
        }
      }
    });
  }

  // ── Navegar para pergunta anterior ──
  void _voltar() {
    setState(() {
      _followupAtivo = null;
      if (_concluido) {
        _concluido = false;
        _fase = 1;
        _index = _anamneseItems.length - 1;
        return;
      }
      if (_fase == 0) {
        // Volta pulando o que a porta não abriu — senão o usuário cai numa
        // pergunta que nem deveria ver e fica preso nela.
        var ant = _index - 1;
        while (ant >= 0 && !_perguntaVisivel(_perguntas[ant])) {
          ant--;
        }
        if (ant >= 0) _index = ant;
      } else if (_index > 0) {
        _index--;
      } else {
        _fase = 0;
        _index = _ultimaPerguntaVisivel();
      }
    });
  }

  // ── Responder sintoma (Sim/Não) ──
  void _responderSintoma(bool valor) async {
    final pergunta = _perguntas[_index];
    if (pergunta.condicionaisDe.isNotEmpty) {
      _desempate[pergunta.key] = valor;
    } else {
      _sintomas[pergunta.key] = valor;
    }

    // Sintoma de urgência com Sim → mostrar alerta antes de continuar
    if (valor && pergunta.isUrgencia) {
      await _mostrarAlertaUrgencia(pergunta.key);
      return;
    }

    // Febre sim → pedir intensidade
    if (valor && pergunta.followup != null) {
      setState(() => _followupAtivo = pergunta.followup);
      return;
    }

    // Caso contrário avançar direto
    setState(() {});
    await Future.delayed(const Duration(milliseconds: 120));
    _avancar();
  }

  // ── Selecionar intensidade ──
  void _selecionarIntensidade(String tipo, String valor) async {
    setState(() {
      if (tipo == 'febre') {
        _intensidadeFebre = valor;
      } else {
        _intensidadeArticular = valor;
      }
      _followupAtivo = null;
    });
    await Future.delayed(const Duration(milliseconds: 120));
    _avancar();
  }

  // ── Responder anamnese ──
  void _responderAnamnese(dynamic valor) async {
    setState(() {
      switch (_index) {
        case 0:
          _diasSintomas = valor as int?;
        case 1:
          _inicioAbrupto = valor as bool?;
        case 2:
          _viagemAreaEndemica = valor as bool?;
        case 3:
          _exposicaoAguaEnchente = valor as bool?;
        case 4:
          _contatoRoedores = valor as bool?;
        case 5:
          _contatoConfirmado = valor as bool?;
        case 6:
          _vacinadoFebreAmarela = valor as bool?;
        case 7:
          _temDiabetes = valor as bool?;
        case 8:
          _temHipertensao = valor as bool?;
        case 9:
          _temDoencaPulmonar = valor as bool?;
        case 10:
          _temImunossupressao = valor as bool?;
        case 11:
          _exposicaoCarrapato = valor as bool?;
        case 12:
          _exposicaoTriatomideo = valor as bool?;
        case 13:
          _mordeduraAnimal = valor as bool?;
      }
    });
    // Mordedura de animal é a única resposta de anamnese que exige algo da
    // pessoa AGORA. A profilaxia antirrábica depende de começar cedo, e a
    // raiva é praticamente 100% letal depois que os sintomas aparecem — não
    // dá para deixar esse aviso só para o resultado no fim do questionário.
    // Diferente do alerta de urgência dos sintomas, este não desfaz a
    // resposta: a pessoa foi mordida, isso é fato, e o registro continua.
    if (_index == 13 && valor == true) {
      await _mostrarAvisoAntirrabico();
      if (!mounted) return;
    }
    if (valor != null) {
      await Future.delayed(const Duration(milliseconds: 150));
      _avancar();
    }
  }

  Future<void> _mostrarAvisoAntirrabico() async {
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Procure atendimento'),
        content: const Text(
          'Mordedura, arranhadura ou lambedura de animal pode exigir vacina '
          'antirrábica.\n\nA profilaxia funciona quando começa cedo — procure '
          'uma unidade de saúde o quanto antes, mesmo que a ferida pareça '
          'pequena ou já tenha cicatrizado, e mesmo sem nenhum sintoma.\n\n'
          'Lave o local com água e sabão.',
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Entendi'),
          ),
        ],
      ),
    );
  }

  dynamic _valorAnamnese(int idx) {
    return switch (idx) {
      0 => _diasSintomas,
      1 => _inicioAbrupto,
      2 => _viagemAreaEndemica,
      3 => _exposicaoAguaEnchente,
      4 => _contatoRoedores,
      5 => _contatoConfirmado,
      6 => _vacinadoFebreAmarela,
      7 => _temDiabetes,
      8 => _temHipertensao,
      9 => _temDoencaPulmonar,
      10 => _temImunossupressao,
      11 => _exposicaoCarrapato,
      12 => _exposicaoTriatomideo,
      13 => _mordeduraAnimal,
      _ => null,
    };
  }

  // ── Alerta de urgência ──
  Future<void> _mostrarAlertaUrgencia(String campo) async {
    final isMeningite = campo == 'rigidez_nuca';
    final titulo = isMeningite
        ? 'Sinal de emergência detectado'
        : 'Sinal de urgência detectado';
    final mensagem = isMeningite
        ? 'Rigidez na nuca pode indicar MENINGITE.\n\nLigue 192 (SAMU) ou vá ao pronto-socorro imediatamente.\n\nDeseja continuar com o registro para o radar epidemiológico?'
        : 'Manchas roxas ou sangramento espontâneo podem indicar quadro grave.\n\nProcure atendimento médico urgente.\n\nDeseja continuar com o registro epidemiológico?';

    if (!mounted) return;
    final continuar = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(titulo),
        content: Text(mensagem),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Continuar registro'),
          ),
        ],
      ),
    );
    if (!mounted) return;

    if (continuar == true) {
      final p = _perguntas[_index];
      if (p.followup != null) {
        setState(() => _followupAtivo = p.followup);
      } else {
        _avancar();
      }
    } else {
      // Desfazer o "sim" se o usuário cancelar
      setState(() => _sintomas[campo] = false);
    }
  }

  // ── Enviar ──
  Future<void> _enviar() async {
    if (_totalSintomas == 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('Responda ao menos um sintoma como Sim.')),
      );
      return;
    }

    setState(() => _loading = true);
    try {
      final location = await _resolverLocalizacao();
      if (location == null) return;

      final result = await PublicApiService.enviarSintomas(
        sintomas: Map<String, bool>.from(_sintomas),
        desempate: Map<String, bool>.from(_desempate),
        latitude: location.latitude,
        longitude: location.longitude,
        locationSource: location.source,
        intensidadeFebre: _intensidadeFebre,
        intensidadeArticular: _intensidadeArticular,
        diasSintomas: _diasSintomas,
        inicioAbrupto: _inicioAbrupto,
        viagemAreaEndemica: _viagemAreaEndemica,
        exposicaoAguaEnchente: _exposicaoAguaEnchente,
        contatoRoedores: _contatoRoedores,
        contatoConfirmado: _contatoConfirmado,
        vacinadoFebreAmarela: _vacinadoFebreAmarela,
        temComorbidade: _temComorbidade,
        temDiabetes: _temDiabetes,
        temHipertensao: _temHipertensao,
        temDoencaPulmonar: _temDoencaPulmonar,
        temImunossupressao: _temImunossupressao,
        exposicaoCarrapato: _exposicaoCarrapato,
        exposicaoTriatomideo: _exposicaoTriatomideo,
        mordeduraAnimal: _mordeduraAnimal,
      );

      final local = result['local'] as Map<String, dynamic>? ?? {};
      await RegiaoBaseService.registrarObservacao(
        local: local,
        latitude: location.latitude,
        longitude: location.longitude,
      );
      await RegiaoBaseService.salvarModoMonitoramento('atual');

      if (!mounted) return;
      setState(() => _lastResult = result);

      final cidadao = result['cidadao'] as Map<String, dynamic>?;
      final jaConsiderado = result['status'] == 'ja_considerado';

      if (cidadao != null && !jaConsiderado) {
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => TelaResultado(cidadao: cidadao, local: local),
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(jaConsiderado
                ? 'Seus sintomas desta semana já estão no radar epidemiológico. Você pode enviar novamente em 7 dias.'
                : 'Sintomas enviados com segurança. Obrigado por contribuir.'),
            duration: const Duration(seconds: 6),
          ),
        );
      }
      // Sempre reseta a tela após o envio, independente de como ela foi
      // aberta (aba inferior ou botão do painel inicial) — sem isso, quem
      // entra pelo botão do painel fica preso na tela de revisão, porque o
      // botão "Recomeçar" fica escondido justo quando _concluido == true.
      if (mounted) _limparTudo();
      widget.onSintomasEnviados?.call();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
      );
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<LocationSnapshot?> _resolverLocalizacao() async {
    try {
      return await LocationService.getCurrentLocationForSubmission();
    } catch (e) {
      final base = await RegiaoBaseService.obterRegiaoBase();
      final fallback = await LocationService.getBestEffortLocation(
        fallbackRegion: base,
      );
      if (mounted && fallback.source != 'current') {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'GPS atual instável. Envio registrado com melhor região disponível.',
            ),
            duration: Duration(seconds: 5),
          ),
        );
      }
      return fallback;
    }
  }

  @override
  void initState() {
    super.initState();
    PublicApiService.cooldownRestante().then((d) {
      if (mounted && d != null) setState(() => _cooldown = d);
    });
  }

  String _formatarCooldown(Duration d) {
    final dias = d.inDays;
    final horas = d.inHours % 24;
    final minutos = d.inMinutes % 60;
    if (dias > 0) return '${dias}d${horas > 0 ? ' ${horas}h' : ''}';
    if (horas > 0) return '${horas}h${minutos > 0 ? ' ${minutos}min' : ''}';
    return '${minutos > 0 ? minutos : 1} min';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF04131F),
      appBar: AppBar(
        backgroundColor: const Color(0xFF04131F),
        leading: _concluido || _fase > 0 || _index > 0
            ? IconButton(
                icon: const Icon(Icons.arrow_back_ios_new, size: 20),
                onPressed: _voltar,
                tooltip: 'Voltar',
              )
            : null,
        title: _concluido
            ? const Text('Revisar e enviar')
            : Text(
                _fase == 0 ? 'Como você está se sentindo?' : 'Contexto clínico',
                style: const TextStyle(fontSize: 16),
              ),
        actions: [
          if (_totalSintomas > 0 && !_concluido)
            TextButton(
              onPressed: _limparTudo,
              style: TextButton.styleFrom(foregroundColor: Colors.white54),
              child: const Text('Recomeçar'),
            ),
          IconButton(
            tooltip: 'Fontes e referências',
            icon: const Icon(Icons.menu_book_outlined),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const TelaFontes()),
            ),
          ),
        ],
      ),
      body: _concluido ? _buildRevisao() : _buildFluxo(),
    );
  }

  // ── Fluxo de perguntas ────────────────────────────────────────────────────
  Widget _buildFluxo() {
    return Column(
      children: [
        // ── Barra de progresso ──
        _BarraProgresso(
          atual: _progressoAtual,
          total: _progressoTotal,
          fase: _fase,
        ),

        // ── Pergunta atual ──
        Expanded(
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 220),
            transitionBuilder: (child, animation) => FadeTransition(
              opacity: animation,
              child: SlideTransition(
                position: Tween<Offset>(
                  begin: const Offset(0.04, 0),
                  end: Offset.zero,
                ).animate(CurvedAnimation(
                  parent: animation,
                  curve: Curves.easeOut,
                )),
                child: child,
              ),
            ),
            child: _fase == 0
                ? _buildCardSintoma(
                    key: ValueKey('s${_index}_$_followupAtivo'),
                  )
                : _buildCardAnamnese(
                    key: ValueKey('a$_index'),
                  ),
          ),
        ),

        // ── Rodapé: pular ──
        if (!_concluido)
          Padding(
            padding: EdgeInsets.fromLTRB(
              24,
              0,
              24,
              12 + MediaQuery.of(context).padding.bottom,
            ),
            child: TextButton(
              onPressed: () {
                if (_followupAtivo != null) {
                  setState(() => _followupAtivo = null);
                }
                _avancar();
              },
              style: TextButton.styleFrom(
                foregroundColor: Colors.white,
              ),
              child: Text(
                _fase == 0 ? 'Não tenho certeza — pular' : 'Pular esta pergunta',
                style: const TextStyle(fontSize: 13),
              ),
            ),
          ),
      ],
    );
  }

  // ── Card de pergunta de sintoma ──
  Widget _buildCardSintoma({Key? key}) {
    final pergunta = _perguntas[_index];
    final cor = pergunta.isUrgencia
        ? const Color(0xFFFF6B6B)
        : const Color(0xFF39D0C3);
    final selecionado = _sintomas[pergunta.key] ?? false;

    return SingleChildScrollView(
      key: key,
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const SizedBox(height: 12),

          // Emoji
          if (pergunta.emoji.isNotEmpty)
            Text(pergunta.emoji, style: const TextStyle(fontSize: 56)),

          const SizedBox(height: 20),

          // Pergunta
          Text(
            pergunta.pergunta,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: pergunta.isUrgencia
                  ? const Color(0xFFFF6B6B)
                  : Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w800,
              height: 1.3,
            ),
          ),

          const SizedBox(height: 10),

          // Dica
          Text(
            pergunta.dica,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Color(0xFF6A9AB5),
              fontSize: 14,
              height: 1.4,
            ),
          ),

          const SizedBox(height: 32),

          // Followup de intensidade (aparece inline após responder Sim)
          if (_followupAtivo != null)
            _buildFollowupIntensidade(_followupAtivo!)
          else ...[
            // Botões SIM / NÃO
            Row(
              children: [
                Expanded(
                  child: _BotaoGrande(
                    texto: 'Sim',
                    icone: Icons.check,
                    selecionado: selecionado,
                    cor: cor,
                    onTap: () => _responderSintoma(true),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _BotaoGrande(
                    texto: 'Não',
                    icone: Icons.close,
                    selecionado: !selecionado && _index > 0,
                    cor: const Color(0xFF3D6680),
                    onTap: () => _responderSintoma(false),
                  ),
                ),
              ],
            ),
          ],

          const SizedBox(height: 8),
        ],
      ),
    );
  }

  // ── Follow-up de intensidade inline ──
  Widget _buildFollowupIntensidade(String tipo) {
    final isFebre = tipo == 'febre';
    final titulo = isFebre ? 'Qual a intensidade da febre?' : 'Qual a intensidade da dor articular?';
    final opcoes = isFebre
        ? [
            ('baixa', 'Baixa', 'Abaixo de 38,5°C'),
            ('moderada', 'Moderada', '38,5 – 39,5°C'),
            ('alta', 'Alta', 'Acima de 39,5°C'),
          ]
        : [
            ('leve', 'Leve', 'Não atrapalha atividades'),
            ('moderada', 'Moderada', 'Dificulta atividades'),
            ('intensa', 'Intensa', 'Incapacitante — não consegue andar'),
          ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          titulo,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 17,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 14),
        for (final (valor, label, detalhe) in opcoes) ...[
          _OpcaoIntensidade(
            label: label,
            detalhe: detalhe,
            onTap: () => _selecionarIntensidade(tipo, valor),
          ),
          const SizedBox(height: 8),
        ],
      ],
    );
  }

  // ── Card de pergunta de anamnese ──
  Widget _buildCardAnamnese({Key? key}) {
    final item = _anamneseItems[_index];
    final valorAtual = _valorAnamnese(_index);

    return SingleChildScrollView(
      key: key,
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const SizedBox(height: 12),

          if (item.emoji.isNotEmpty)
            Text(item.emoji, style: const TextStyle(fontSize: 52)),

          const SizedBox(height: 20),

          Text(
            item.pergunta,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w800,
              height: 1.3,
            ),
          ),

          const SizedBox(height: 10),

          Text(
            item.dica,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Color(0xFF6A9AB5),
              fontSize: 14,
              height: 1.4,
            ),
          ),

          const SizedBox(height: 32),

          // Dias de sintomas → opções de botão
          if (item.tipo == _TipoAnamnese.dias)
            _buildOpcoesDias(valorAtual as int?)
          else ...[
            Row(
              children: [
                Expanded(
                  child: _BotaoGrande(
                    texto: 'Sim',
                    icone: Icons.check,
                    selecionado: valorAtual == true,
                    cor: const Color(0xFF39D0C3),
                    onTap: () => _responderAnamnese(true),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _BotaoGrande(
                    texto: 'Não',
                    icone: Icons.close,
                    selecionado: valorAtual == false,
                    cor: const Color(0xFF3D6680),
                    onTap: () => _responderAnamnese(false),
                  ),
                ),
              ],
            ),
          ],

          const SizedBox(height: 8),
        ],
      ),
    );
  }

  // ── Seletor de dias ──
  Widget _buildOpcoesDias(int? valorAtual) {
    const opcoes = [
      (1, 'Hoje'),
      (2, '2–3 dias'),
      (4, '4–5 dias'),
      (7, '1 semana'),
      (14, 'Mais de 1 sem.'),
    ];
    return Wrap(
      spacing: 10,
      runSpacing: 10,
      alignment: WrapAlignment.center,
      children: [
        for (final (val, label) in opcoes)
          GestureDetector(
            onTap: () => _responderAnamnese(val),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 150),
              padding:
                  const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
              decoration: BoxDecoration(
                color: valorAtual == val
                    ? const Color(0xFF39D0C3).withValues(alpha: 0.2)
                    : const Color(0xFF0B2333),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: valorAtual == val
                      ? const Color(0xFF39D0C3)
                      : const Color(0xFF1A3A50),
                  width: 1.5,
                ),
              ),
              child: Text(
                label,
                style: TextStyle(
                  color: valorAtual == val
                      ? const Color(0xFF39D0C3)
                      : Colors.white70,
                  fontWeight: valorAtual == val
                      ? FontWeight.w700
                      : FontWeight.normal,
                  fontSize: 14,
                ),
              ),
            ),
          ),
      ],
    );
  }

  // ── Tela de revisão + envio ────────────────────────────────────────────────
  Widget _buildRevisao() {
    final sintomasAtivos = _perguntas
        .where((p) => _sintomas[p.key] == true)
        .map((p) => p.emoji.isNotEmpty
            ? '${p.emoji} ${p.pergunta}'
            : p.pergunta)
        .toList();

    // As respostas de desempate não são sintomas — ficam fora de _sintomas e,
    // por isso, não apareciam aqui. Quem respondeu "tenho íngua" via a tela
    // dizer "1 sintoma registrado" e nada mais, sem como conferir o que de
    // fato ia ser enviado. Em vigilância, conferir antes de enviar não é
    // detalhe: é o que torna o dado auditável por quem o forneceu.
    final detalhes = _perguntas
        .where((p) => p.condicionaisDe.isNotEmpty && _desempate.containsKey(p.key))
        .map((p) => (
              texto: p.emoji.isNotEmpty ? '${p.emoji} ${p.pergunta}' : p.pergunta,
              resposta: _desempate[p.key]! ? 'Sim' : 'Não',
            ))
        .toList();

    return ListView(
      padding: EdgeInsets.fromLTRB(
        20,
        20,
        20,
        20 + MediaQuery.of(context).padding.bottom,
      ),
      children: [
        // Cabeçalho
        Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF12324B), Color(0xFF0A1B29)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(20),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Pronto para enviar',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                '${sintomasAtivos.length} sintoma${sintomasAtivos.length != 1 ? 's' : ''} registrado${sintomasAtivos.length != 1 ? 's' : ''}'
                '${detalhes.isEmpty ? '' : ' e ${detalhes.length} resposta${detalhes.length != 1 ? 's' : ''} de detalhamento'}'
                '. Envio anônimo e voluntário.',
                style: const TextStyle(
                  color: Color(0xFF9FC5D9),
                  fontSize: 14,
                  height: 1.4,
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 16),

        // Sintomas marcados
        if (sintomasAtivos.isNotEmpty) ...[
          const Text(
            'Sintomas informados',
            style: TextStyle(
              color: Color(0xFF6A9AB5),
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFF0B2333),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final s in sintomasAtivos)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Text(
                      s,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        height: 1.4,
                      ),
                    ),
                  ),
                if (_intensidadeFebre != null)
                  Text(
                    '  Febre: intensidade $_intensidadeFebre',
                    style: const TextStyle(
                        color: Color(0xFF9FC5D9), fontSize: 13),
                  ),
                if (_intensidadeArticular != null)
                  Text(
                    '  Articular: intensidade $_intensidadeArticular',
                    style: const TextStyle(
                        color: Color(0xFF9FC5D9), fontSize: 13),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],

        // Respostas de desempate — o que a porta aberta perguntou
        if (detalhes.isNotEmpty) ...[
          const Text(
            'Respostas de detalhamento',
            style: TextStyle(
              color: Color(0xFF6A9AB5),
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFF0B2333),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final d in detalhes)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          d.texto,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 14,
                            height: 1.35,
                          ),
                        ),
                        Text(
                          '  ${d.resposta}',
                          style: TextStyle(
                            color: d.resposta == 'Sim'
                                ? const Color(0xFF4FD1C5)
                                : const Color(0xFF9FC5D9),
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],

        // Contexto respondido
        if (_diasSintomas != null ||
            _inicioAbrupto != null ||
            _viagemAreaEndemica != null ||
            _exposicaoAguaEnchente != null ||
            _contatoRoedores != null ||
            _contatoConfirmado != null ||
            _vacinadoFebreAmarela != null ||
            _temDiabetes != null ||
            _temHipertensao != null ||
            _temDoencaPulmonar != null ||
            _temImunossupressao != null) ...[
          const Text(
            'Contexto clínico',
            style: TextStyle(
              color: Color(0xFF6A9AB5),
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFF0B2333),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (_diasSintomas != null)
                  _InfoRow('Duração', '$_diasSintomas dia(s)'),
                if (_inicioAbrupto != null)
                  _InfoRow('Início',
                      _inicioAbrupto! ? 'Repentino' : 'Gradual'),
                if (_viagemAreaEndemica != null)
                  _InfoRow('Viagem endêmica',
                      _viagemAreaEndemica! ? 'Sim' : 'Não'),
                if (_exposicaoAguaEnchente != null)
                  _InfoRow('Água/enchente',
                      _exposicaoAguaEnchente! ? 'Sim' : 'Não'),
                if (_contatoRoedores != null)
                  _InfoRow(
                      'Contato roedores', _contatoRoedores! ? 'Sim' : 'Não'),
                if (_contatoConfirmado != null)
                  _InfoRow('Contato doente confirmado',
                      _contatoConfirmado! ? 'Sim' : 'Não'),
                if (_vacinadoFebreAmarela != null)
                  _InfoRow('Vacina Febre Amarela',
                      _vacinadoFebreAmarela! ? 'Sim' : 'Não'),
                if (_temDiabetes != null)
                  _InfoRow('Diabetes', _temDiabetes! ? 'Sim' : 'Não'),
                if (_temHipertensao != null)
                  _InfoRow('Hipertensão', _temHipertensao! ? 'Sim' : 'Não'),
                if (_temDoencaPulmonar != null)
                  _InfoRow('D. pulmonar/asma', _temDoencaPulmonar! ? 'Sim' : 'Não'),
                if (_temImunossupressao != null)
                  _InfoRow('Imunossupressão', _temImunossupressao! ? 'Sim' : 'Não'),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],

        // Resultado anterior
        if (_lastResult != null) ...[
          _FeedbackCard(data: _lastResult!),
          const SizedBox(height: 16),
        ],

        // Aviso legal
        const Text(
          'Este app não substitui atendimento médico. Em caso de agravamento, procure atendimento profissional imediatamente.',
          style: TextStyle(
              color: Color(0xFF88AFC5), height: 1.45, fontSize: 13),
        ),
        const SizedBox(height: 24),

        // Aviso informativo — já recebemos sintomas esta semana (não bloqueia)
        if (_cooldown != null) ...[
          const SizedBox(height: 4),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: const Color(0xFF0D2233),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: const Color(0xFF1A4A6A)),
            ),
            child: Row(
              children: [
                const Icon(Icons.check_circle_outline,
                    color: Color(0xFF39D0C3), size: 20),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Já recebemos seus sintomas.',
                    style: const TextStyle(
                        color: Color(0xFF88AFC5), fontSize: 13, height: 1.4),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
        ],

        // Botão enviar
        FilledButton.icon(
          onPressed: _loading || _totalSintomas == 0
              ? null
              : _enviar,
          icon: _loading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(
                      strokeWidth: 2, color: Colors.black),
                )
              : const Icon(Icons.cloud_upload_outlined),
          label: Text(
            _loading
                ? 'Enviando...'
                : _totalSintomas == 0
                    ? 'Nenhum sintoma selecionado'
                    : 'Enviar $_totalSintomas sintoma${_totalSintomas > 1 ? 's' : ''} agora',
          ),
          style: FilledButton.styleFrom(
            minimumSize: const Size.fromHeight(54),
            backgroundColor: _totalSintomas > 0
                ? const Color(0xFF39D0C3)
                : const Color(0xFF1A3A50),
            foregroundColor: _totalSintomas > 0
                ? Colors.black
                : Colors.white38,
          ),
        ),
      ],
    );
  }
}

// ─── Barra de progresso ───────────────────────────────────────────────────────
class _BarraProgresso extends StatelessWidget {
  const _BarraProgresso({
    required this.atual,
    required this.total,
    required this.fase,
  });
  final int atual;
  final int total;
  final int fase;

  @override
  Widget build(BuildContext context) {
    final progresso = total > 0 ? atual / total : 0.0;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 0),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                fase == 0 ? 'Sintomas' : 'Contexto clínico',
                style: const TextStyle(
                    color: Color(0xFF6A9AB5),
                    fontSize: 12,
                    fontWeight: FontWeight.w600),
              ),
              Text(
                '${atual + 1} de $total',
                style: const TextStyle(
                    color: Color(0xFF4A7A8F), fontSize: 12),
              ),
            ],
          ),
        ),
        const SizedBox(height: 6),
        LinearProgressIndicator(
          value: progresso,
          backgroundColor: const Color(0xFF0B2333),
          color: fase == 0
              ? const Color(0xFF39D0C3)
              : const Color(0xFF9B59B6),
          minHeight: 3,
        ),
        const SizedBox(height: 8),
      ],
    );
  }
}

// ─── Botão grande Sim/Não ─────────────────────────────────────────────────────
class _BotaoGrande extends StatelessWidget {
  const _BotaoGrande({
    required this.texto,
    required this.icone,
    required this.selecionado,
    required this.cor,
    required this.onTap,
  });
  final String texto;
  final IconData icone;
  final bool selecionado;
  final Color cor;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        height: 64,
        decoration: BoxDecoration(
          color: selecionado
              ? cor.withValues(alpha: 0.2)
              : const Color(0xFF0B2333),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: selecionado ? cor : const Color(0xFF1A3A50),
            width: 2,
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icone,
                color: selecionado ? cor : Colors.white38, size: 20),
            const SizedBox(width: 8),
            Text(
              texto,
              style: TextStyle(
                color: selecionado ? cor : Colors.white54,
                fontWeight:
                    selecionado ? FontWeight.w800 : FontWeight.w500,
                fontSize: 16,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Opção de intensidade ─────────────────────────────────────────────────────
class _OpcaoIntensidade extends StatelessWidget {
  const _OpcaoIntensidade({
    required this.label,
    required this.detalhe,
    required this.onTap,
  });
  final String label;
  final String detalhe;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          color: const Color(0xFF0B2333),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFF1A3A50), width: 1.5),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    label,
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                        fontSize: 15),
                  ),
                  Text(
                    detalhe,
                    style: const TextStyle(
                        color: Color(0xFF6A9AB5), fontSize: 13),
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right,
                color: Color(0xFF3D6680), size: 20),
          ],
        ),
      ),
    );
  }
}

// ─── Card de feedback do último envio ────────────────────────────────────────
class _FeedbackCard extends StatelessWidget {
  const _FeedbackCard({required this.data});
  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final local = data['local'] as Map<String, dynamic>? ?? {};
    final jaConsiderado = data['status'] == 'ja_considerado';

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Leitura do envio',
              style: TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            _InfoRow('Sinal monitorado',
                data['grupo']?.toString() ?? 'Monitoramento geral'),
            _InfoRow('Classificação',
                data['classificacao']?.toString() ?? 'Regional'),
            _InfoRow('Qualidade do sinal', _qualidade(data)),
            _InfoRow(
              'Local identificado',
              '${local['bairro'] ?? '—'} / ${local['cidade'] ?? '—'} / ${local['estado'] ?? '—'}',
            ),
            if (jaConsiderado) ...[
              const SizedBox(height: 8),
              const Text(
                'Este envio não abriu novo caso — o radar já recebeu sinal recente deste aparelho.',
                style: TextStyle(
                    color: Color(0xFFFFD166), height: 1.35, fontSize: 13),
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _qualidade(Map<String, dynamic> data) {
    final valor = (data['confianca'] as num?)?.toDouble() ?? 0;
    if (valor >= 0.85) return 'alta';
    if (valor >= 0.6) return 'moderada';
    return 'em verificação';
  }
}

// ─── InfoRow helper ───────────────────────────────────────────────────────────
class _InfoRow extends StatelessWidget {
  const _InfoRow(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: RichText(
        text: TextSpan(
          style: const TextStyle(fontSize: 13, height: 1.4),
          children: [
            TextSpan(
              text: '$label: ',
              style: const TextStyle(color: Color(0xFF6A9AB5)),
            ),
            TextSpan(
              text: value,
              style: const TextStyle(color: Color(0xFF9FC5D9)),
            ),
          ],
        ),
      ),
    );
  }
}
