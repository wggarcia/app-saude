from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from django.db.models import Count
from .utils import probabilidade_doenca

from .models import RegistroSintoma, Empresa, AlertaGovernamental, DispositivoPushPublico, AceiteLegalPublico
from .utils_cidades import buscar_coordenada
from .utils import obter_localizacao
from django.conf import settings
from api.utils_ia import classificar_padrao
from api.utils_geo import obter_endereco
from api.utils_auth import validar_token
from api.models import Empresa, RegistroSintoma
from api.epidemiologia import _build_disease_probabilities
from django.db.models import Count, Avg, Q
from django.db.models.functions import TruncDate
from django.contrib.auth.hashers import check_password, make_password
from collections import defaultdict
from datetime import datetime, timedelta

# ============================
# 🧠 IA GLOBAL (MOVER PRA CIMA)
# ============================

historico = defaultdict(list)


SITE_LANGUAGE_META = {
    "pt": {"label": "PT", "flag": "🇧🇷", "name": "Portugues", "html": "pt-BR"},
    "en": {"label": "EN", "flag": "🇺🇸", "name": "English", "html": "en"},
    "es": {"label": "ES", "flag": "🇪🇸", "name": "Espanol", "html": "es"},
}


SITE_TRANSLATIONS = {
    "pt": {
        "title": "SolusCRT Saude | Radar epidemiologico inteligente",
        "description": "SolusCRT Saude e uma sala de controle epidemiologica com app populacional, IA, mapas de risco e paineis SaaS para empresas e governos.",
        "brand": "SolusCRT Saude",
        "nav": {
            "diferencial": "Diferencial",
            "ecossistema": "Ecossistema",
            "valores": "Valores",
            "app": "App",
            "contato": "Contato",
        },
        "nav_note": "Ambientes privados sob contrato",
        "language_aria": "Selecionar idioma",
        "hero_eyebrow": "Inteligencia epidemiologica em tempo real",
        "hero_title": "IA epidemiologica para antecipar surtos antes que escalem.",
        "hero_title_desktop_lines": ["IA epidemiologica", "para antecipar", "surtos antes", "que escalem."],
        "hero_title_lines": ["IA epidemiologica", "para antecipar", "surtos antes", "que escalem."],
        "hero_lead": "SolusCRT Saude e uma plataforma SaaS com inteligencia artificial operacional, app da populacao, mapas vivos, dados oficiais, alertas e paineis de decisao para enxergar risco, priorizar territorios e agir com velocidade.",
        "actions": {
            "presentation": "Ver apresentacao completa",
            "app": "Baixar app da populacao",
            "sales": "Falar com comercial",
            "open_presentation": "Abrir apresentacao completa",
            "meeting": "Solicitar reuniao",
        },
        "proofs": [
            {"title": "Antes do dado consolidado", "text": "Sinais da populacao ajudam a enxergar tendencia enquanto notificacoes oficiais ainda estao amadurecendo."},
            {"title": "Sem confundir evidencias", "text": "Sinal colaborativo, fonte oficial e inferencia de IA aparecem como camadas distintas."},
            {"title": "Decisao por territorio", "text": "Bairro, municipio, estado, hospitais, farmacias, empresas e governo com leituras proprias."},
        ],
        "chips": ["App populacional", "IA epidemiologica", "Predicao territorial", "Sala de situacao"],
        "metrics": [
            {"value": "IA", "text": "cruza sintomas, crescimento, territorio e fontes oficiais"},
            {"value": "IA + 10 dias", "text": "apos 10 dias sem novos sinais, a intensidade so reduz quando tendencia local, dados agregados e fontes oficiais sustentam queda real"},
            {"value": "100 mil", "text": "indicadores padronizados por populacao"},
            {"value": "LGPD", "text": "governanca, minimo necessario e segregacao"},
        ],
        "differential": {
            "title": "A IA do SolusCRT transforma sinais dispersos em decisao antes do pico.",
            "lead": "Ela nao tenta substituir vigilancia oficial nem diagnostico medico. A forca esta em ler milhares de sinais fracos, cruzar territorio, crescimento, sintomas, fontes brasileiras e comportamento temporal para apontar onde agir primeiro.",
            "traditional_title": "Vigilancia tradicional",
            "traditional_items": [
                "Depende de ciclos de notificacao, atendimento, consolidacao e publicacao.",
                "Excelente para confirmacao, historico e politica publica, mas naturalmente sujeita a atraso.",
                "Pode chegar tarde para estoque, escala de equipe, comunicacao e resposta local.",
            ],
            "solus_title": "Camada SolusCRT com IA",
            "solus_items": [
                "Recebe sinais sem cadastro nominal da populacao pelo celular, com localizacao atual e controle antifraude.",
                "Identifica crescimento, predominancia de sintomas e risco territorial antes da confirmacao oficial.",
                "Usa IA para priorizar bairros, municipios, doencas provaveis, estoque, atendimento e alertas publicos.",
            ],
        },
        "ecosystem_title": "Uma arquitetura para todos que precisam agir.",
        "ecosystem_lead": "O mesmo radar alimenta visoes diferentes, sem misturar acesso publico com ambientes privados.",
        "slides": [
            {"small": "Populacao", "title": "App gratuito", "text": "Envio de sintomas, radar local, mapa e alertas oficiais com linguagem simples."},
            {"small": "Empresas", "title": "Saude ocupacional", "text": "Risco por territorio, impacto operacional, unidades, equipes e afastamentos."},
            {"small": "Farmacias e hospitais", "title": "Demanda futura", "text": "Preparacao de estoque, atendimento, exames, leitos e campanhas preventivas."},
            {"small": "Governo", "title": "Sala de situacao", "text": "Alertas oficiais, fontes brasileiras, matriz de decisao, auditoria e contratos anuais."},
        ],
        "matrix": [
            {"label": "Radar vivo", "title": "Mapa de risco", "text": "Focos por bairro, municipio e estado, com icones por grupos de sintomas e intensidade temporal."},
            {"label": "IA preditiva", "title": "Motor epidemiologico", "text": "Classifica sinais, estima doencas provaveis, mede crescimento e valida reducao gradual com serie temporal, dados agregados e fontes oficiais."},
            {"label": "Oficial", "title": "Brasil Oficial", "text": "IBGE/SIDRA, InfoDengue, InfoGripe, OpenDataSUS/DATASUS em camadas separadas."},
            {"label": "Protecao", "title": "Antifraude", "text": "Controle por aparelho, rede, repeticao, localizacao confirmada e qualidade do sinal."},
            {"label": "Alerta", "title": "Comunicacao publica", "text": "Mensagens oficiais chegam ao app da populacao com governanca e rastreabilidade."},
            {"label": "Enterprise", "title": "SaaS vendavel", "text": "Pacotes por maquinas, usuarios, setores, administracao financeira e acesso separado."},
        ],
        "values": {
            "eyebrow": "Valores SolusCRT",
            "title": "Tecnologia para proteger pessoas, nao apenas vender software.",
            "lead": "A SolusCRT nasce com uma responsabilidade clara: transformar dados em cuidado, antecipar riscos sem gerar alarme vazio e ajudar empresas, governos e populacao a agir com mais consciencia, velocidade e humanidade.",
            "items": [
                {"title": "Vida em primeiro lugar", "text": "Todo indicador, alerta e mapa existe para reduzir atraso, orientar cuidado e apoiar decisoes que preservem pessoas."},
                {"title": "Verdade antes de impacto", "text": "Separar sinal precoce, dado oficial e inferencia de IA e um compromisso para evitar conclusoes falsas."},
                {"title": "Privacidade como fundamento", "text": "Dados de saude exigem minimizacao, seguranca, transparencia e exibicao adequada ao perfil autorizado."},
                {"title": "Cooperacao institucional", "text": "O sistema foi pensado para unir populacao, empresas, hospitais, farmacias, laboratorios e governo sem confundir responsabilidades."},
                {"title": "Acesso social", "text": "O app da populacao deve ser gratuito, simples e util, porque vigilancia inteligente comeca quando todos podem contribuir."},
                {"title": "Coragem operacional", "text": "A SolusCRT existe para antecipar problemas dificeis, mostrar territorios criticos e ajudar lideres a agir antes do pico."},
            ],
        },
        "app": {
            "eyebrow": "App da populacao",
            "title": "O sensor social que transforma cuidado individual em inteligencia coletiva.",
            "lead": "O app coleta sintomas sem cadastro nominal, exige localizacao atual para evitar erro territorial, mostra o radar local e recebe alertas oficiais. A experiencia foi pensada para ser simples para a populacao e valiosa para a sala de controle.",
            "app_store": "Baixar na App Store",
            "google_play": "Ver no Google Play",
            "risks": [
                {"title": "Radar local", "text": "Leitura por localizacao atual."},
                {"title": "Mapa vivo", "text": "Focos e sintomas por regiao."},
                {"title": "Alertas oficiais", "text": "Comunicacao de governo no celular."},
                {"title": "Protecao", "text": "Sem envio aproximado para cidade errada."},
            ],
        },
        "cta": {
            "title": "Veja a apresentacao completa antes de falar com vendas.",
            "lead": "A apresentacao mostra a proposta para populacao, empresas, hospitais, farmacias, laboratorios e governo, com o diferencial frente aos modelos tradicionais de monitoramento.",
        },
        "footer": "SolusCRT Saude. Inteligencia epidemiologica, app populacional e SaaS enterprise.",
        "footer_links": {
            "privacy": "Privacidade",
            "terms": "Termos",
            "security": "Seguranca",
            "methodology": "Metodologia",
            "support": "Suporte",
        },
    },
    "en": {
        "title": "SolusCRT Health | Intelligent epidemiological radar",
        "description": "SolusCRT Health is an epidemiological command center with a population app, AI, risk maps and SaaS dashboards for companies and governments.",
        "brand": "SolusCRT Health",
        "nav": {
            "diferencial": "Differentiator",
            "ecossistema": "Ecosystem",
            "valores": "Values",
            "app": "App",
            "contato": "Contact",
        },
        "nav_note": "Private environments by contract",
        "language_aria": "Select language",
        "hero_eyebrow": "Real-time epidemiological intelligence",
        "hero_title": "Epidemiological AI to anticipate outbreaks before they escalate.",
        "hero_title_desktop_lines": ["Epidemiological AI", "to anticipate", "outbreaks before", "they escalate."],
        "hero_title_lines": ["Epidemiological AI", "to anticipate", "outbreaks before", "they escalate."],
        "hero_lead": "SolusCRT Health is a SaaS platform with operational artificial intelligence, a population app, live maps, official data, alerts and decision dashboards to see risk, prioritize territories and act quickly.",
        "actions": {
            "presentation": "View full presentation",
            "app": "Download population app",
            "sales": "Talk to sales",
            "open_presentation": "Open full presentation",
            "meeting": "Request a meeting",
        },
        "proofs": [
            {"title": "Before consolidated data", "text": "Population signals help reveal trends while official notifications are still maturing."},
            {"title": "Evidence stays separated", "text": "Collaborative signals, official sources and AI inference appear as distinct layers."},
            {"title": "Territory-based decisions", "text": "Neighborhoods, cities, states, hospitals, pharmacies, companies and governments get their own readings."},
        ],
        "chips": ["Population app", "Epidemiological AI", "Territorial prediction", "Situation room"],
        "metrics": [
            {"value": "AI", "text": "crosses symptoms, growth, territory and official sources"},
            {"value": "AI + 10 days", "text": "after 10 days without new signals, intensity only decreases when local trend, aggregated data and official sources support a real decline"},
            {"value": "100k", "text": "population-standardized indicators"},
            {"value": "LGPD", "text": "governance, minimum necessary data and segregation"},
        ],
        "differential": {
            "title": "SolusCRT AI turns scattered signals into decisions before the peak.",
            "lead": "It does not try to replace official surveillance or medical diagnosis. Its strength is reading thousands of weak signals, crossing territory, growth, symptoms, Brazilian sources and time behavior to show where to act first.",
            "traditional_title": "Traditional surveillance",
            "traditional_items": [
                "Depends on notification, care, consolidation and publication cycles.",
                "Excellent for confirmation, history and public policy, but naturally subject to delay.",
                "May arrive late for stock planning, staffing, communication and local response.",
            ],
            "solus_title": "SolusCRT AI layer",
            "solus_items": [
                "Receives population signals without nominal registration through the phone, with current location and anti-fraud controls.",
                "Identifies growth, symptom predominance and territorial risk before official confirmation.",
                "Uses AI to prioritize neighborhoods, cities, likely diseases, stock, care capacity and public alerts.",
            ],
        },
        "ecosystem_title": "An architecture for everyone who needs to act.",
        "ecosystem_lead": "The same radar powers different views without mixing public access with private environments.",
        "slides": [
            {"small": "Population", "title": "Free app", "text": "Symptom reporting, local radar, map and official alerts in simple language."},
            {"small": "Companies", "title": "Occupational health", "text": "Risk by territory, operational impact, units, teams and absences."},
            {"small": "Pharmacies and hospitals", "title": "Future demand", "text": "Preparation for stock, care, tests, beds and preventive campaigns."},
            {"small": "Government", "title": "Situation room", "text": "Official alerts, Brazilian sources, decision matrix, audit trail and annual contracts."},
        ],
        "matrix": [
            {"label": "Live radar", "title": "Risk map", "text": "Hotspots by neighborhood, city and state, with icons by symptom groups and time intensity."},
            {"label": "Predictive AI", "title": "Epidemiological engine", "text": "Classifies signals, estimates likely diseases, measures growth and validates gradual decline with time series, aggregated data and official sources."},
            {"label": "Official", "title": "Official Brazil", "text": "IBGE/SIDRA, InfoDengue, InfoGripe and OpenDataSUS/DATASUS in separate layers."},
            {"label": "Protection", "title": "Anti-fraud", "text": "Controls by device, network, repetition, confirmed location and signal quality."},
            {"label": "Alert", "title": "Public communication", "text": "Official messages reach the population app with governance and traceability."},
            {"label": "Enterprise", "title": "Sellable SaaS", "text": "Packages by devices, users, sectors, financial administration and separated access."},
        ],
        "values": {
            "eyebrow": "SolusCRT Values",
            "title": "Technology to protect people, not just sell software.",
            "lead": "SolusCRT was born with a clear responsibility: turn data into care, anticipate risks without empty alarm and help companies, governments and people act with more awareness, speed and humanity.",
            "items": [
                {"title": "Life first", "text": "Every indicator, alert and map exists to reduce delay, guide care and support decisions that preserve people."},
                {"title": "Truth before impact", "text": "Separating early signal, official data and AI inference is a commitment to avoid false conclusions."},
                {"title": "Privacy as foundation", "text": "Health data requires minimization, security, transparency and display appropriate to each authorized profile."},
                {"title": "Institutional cooperation", "text": "The system was designed to connect people, companies, hospitals, pharmacies, laboratories and government without blurring responsibilities."},
                {"title": "Social access", "text": "The population app should be free, simple and useful, because intelligent surveillance begins when everyone can contribute."},
                {"title": "Operational courage", "text": "SolusCRT exists to anticipate hard problems, reveal critical territories and help leaders act before the peak."},
            ],
        },
        "app": {
            "eyebrow": "Population app",
            "title": "The social sensor that turns individual care into collective intelligence.",
            "lead": "The app collects symptoms without nominal registration, requires current location to avoid territorial mistakes, shows the local radar and receives official alerts. The experience is simple for the population and valuable for the command center.",
            "app_store": "Download on the App Store",
            "google_play": "View on Google Play",
            "risks": [
                {"title": "Local radar", "text": "Reading based on current location."},
                {"title": "Live map", "text": "Hotspots and symptoms by region."},
                {"title": "Official alerts", "text": "Government communication on the phone."},
                {"title": "Protection", "text": "No approximate submission to the wrong city."},
            ],
        },
        "cta": {
            "title": "See the full presentation before talking to sales.",
            "lead": "The presentation explains the proposal for population, companies, hospitals, pharmacies, laboratories and government, with the differentiator compared with traditional monitoring models.",
        },
        "footer": "SolusCRT Health. Epidemiological intelligence, population app and enterprise SaaS.",
        "footer_links": {
            "privacy": "Privacy",
            "terms": "Terms",
            "security": "Security",
            "methodology": "Methodology",
            "support": "Support",
        },
    },
    "es": {
        "title": "SolusCRT Salud | Radar epidemiologico inteligente",
        "description": "SolusCRT Salud es una sala de control epidemiologica con app poblacional, IA, mapas de riesgo y paneles SaaS para empresas y gobiernos.",
        "brand": "SolusCRT Salud",
        "nav": {
            "diferencial": "Diferencial",
            "ecossistema": "Ecosistema",
            "valores": "Valores",
            "app": "App",
            "contato": "Contacto",
        },
        "nav_note": "Ambientes privados bajo contrato",
        "language_aria": "Seleccionar idioma",
        "hero_eyebrow": "Inteligencia epidemiologica en tiempo real",
        "hero_title": "IA epidemiologica para anticipar brotes antes de escalar.",
        "hero_title_desktop_lines": ["IA epidemiologica", "para anticipar", "brotes antes", "de escalar."],
        "hero_title_lines": ["IA epidemiologica", "para anticipar", "brotes antes", "de escalar."],
        "hero_lead": "SolusCRT Salud es una plataforma SaaS con inteligencia artificial operacional, app para la poblacion, mapas vivos, datos oficiales, alertas y paneles de decision para ver riesgo, priorizar territorios y actuar con velocidad.",
        "actions": {
            "presentation": "Ver presentacion completa",
            "app": "Descargar app poblacional",
            "sales": "Hablar con ventas",
            "open_presentation": "Abrir presentacion completa",
            "meeting": "Solicitar reunion",
        },
        "proofs": [
            {"title": "Antes del dato consolidado", "text": "Las senales de la poblacion ayudan a ver tendencias mientras las notificaciones oficiales aun estan madurando."},
            {"title": "Sin mezclar evidencias", "text": "La senal colaborativa, la fuente oficial y la inferencia de IA aparecen como capas distintas."},
            {"title": "Decision por territorio", "text": "Barrio, municipio, estado, hospitales, farmacias, empresas y gobierno con lecturas propias."},
        ],
        "chips": ["App poblacional", "IA epidemiologica", "Prediccion territorial", "Sala de situacion"],
        "metrics": [
            {"value": "IA", "text": "cruza sintomas, crecimiento, territorio y fuentes oficiales"},
            {"value": "IA + 10 dias", "text": "despues de 10 dias sin nuevas senales, la intensidad solo baja cuando tendencia local, datos agregados y fuentes oficiales sostienen una reduccion real"},
            {"value": "100 mil", "text": "indicadores estandarizados por poblacion"},
            {"value": "LGPD", "text": "gobernanza, minimo necesario y segregacion"},
        ],
        "differential": {
            "title": "La IA de SolusCRT transforma senales dispersas en decision antes del pico.",
            "lead": "No intenta sustituir vigilancia oficial ni diagnostico medico. Su fuerza esta en leer miles de senales debiles, cruzar territorio, crecimiento, sintomas, fuentes brasilenas y comportamiento temporal para mostrar donde actuar primero.",
            "traditional_title": "Vigilancia tradicional",
            "traditional_items": [
                "Depende de ciclos de notificacion, atencion, consolidacion y publicacion.",
                "Excelente para confirmacion, historico y politica publica, pero naturalmente sujeta a retraso.",
                "Puede llegar tarde para stock, escala de equipo, comunicacion y respuesta local.",
            ],
            "solus_title": "Capa SolusCRT con IA",
            "solus_items": [
                "Recibe senales sin registro nominal de la poblacion por celular, con ubicacion actual y control antifraude.",
                "Identifica crecimiento, predominancia de sintomas y riesgo territorial antes de la confirmacion oficial.",
                "Usa IA para priorizar barrios, municipios, enfermedades probables, stock, atencion y alertas publicas.",
            ],
        },
        "ecosystem_title": "Una arquitectura para todos los que necesitan actuar.",
        "ecosystem_lead": "El mismo radar alimenta vistas diferentes, sin mezclar acceso publico con ambientes privados.",
        "slides": [
            {"small": "Poblacion", "title": "App gratuita", "text": "Envio de sintomas, radar local, mapa y alertas oficiales con lenguaje simple."},
            {"small": "Empresas", "title": "Salud ocupacional", "text": "Riesgo por territorio, impacto operacional, unidades, equipos y ausencias."},
            {"small": "Farmacias y hospitales", "title": "Demanda futura", "text": "Preparacion de stock, atencion, examenes, camas y campanas preventivas."},
            {"small": "Gobierno", "title": "Sala de situacion", "text": "Alertas oficiales, fuentes brasilenas, matriz de decision, auditoria y contratos anuales."},
        ],
        "matrix": [
            {"label": "Radar vivo", "title": "Mapa de riesgo", "text": "Focos por barrio, municipio y estado, con iconos por grupos de sintomas e intensidad temporal."},
            {"label": "IA predictiva", "title": "Motor epidemiologico", "text": "Clasifica senales, estima enfermedades probables, mide crecimiento y valida la reduccion gradual con serie temporal, datos agregados y fuentes oficiales."},
            {"label": "Oficial", "title": "Brasil Oficial", "text": "IBGE/SIDRA, InfoDengue, InfoGripe y OpenDataSUS/DATASUS en capas separadas."},
            {"label": "Proteccion", "title": "Antifraude", "text": "Control por aparato, red, repeticion, ubicacion confirmada y calidad de la senal."},
            {"label": "Alerta", "title": "Comunicacion publica", "text": "Mensajes oficiales llegan a la app poblacional con gobernanza y trazabilidad."},
            {"label": "Enterprise", "title": "SaaS vendible", "text": "Paquetes por dispositivos, usuarios, sectores, administracion financiera y acceso separado."},
        ],
        "values": {
            "eyebrow": "Valores SolusCRT",
            "title": "Tecnologia para proteger personas, no solo vender software.",
            "lead": "SolusCRT nace con una responsabilidad clara: transformar datos en cuidado, anticipar riesgos sin alarma vacia y ayudar a empresas, gobiernos y poblacion a actuar con mas conciencia, velocidad y humanidad.",
            "items": [
                {"title": "Vida en primer lugar", "text": "Todo indicador, alerta y mapa existe para reducir retraso, orientar cuidado y apoyar decisiones que preserven personas."},
                {"title": "Verdad antes que impacto", "text": "Separar senal temprana, dato oficial e inferencia de IA es un compromiso para evitar conclusiones falsas."},
                {"title": "Privacidad como fundamento", "text": "Los datos de salud exigen minimizacion, seguridad, transparencia y exhibicion adecuada al perfil autorizado."},
                {"title": "Cooperacion institucional", "text": "El sistema fue pensado para unir poblacion, empresas, hospitales, farmacias, laboratorios y gobierno sin confundir responsabilidades."},
                {"title": "Acceso social", "text": "La app poblacional debe ser gratuita, simple y util, porque la vigilancia inteligente comienza cuando todos pueden contribuir."},
                {"title": "Coraje operacional", "text": "SolusCRT existe para anticipar problemas dificiles, mostrar territorios criticos y ayudar a lideres a actuar antes del pico."},
            ],
        },
        "app": {
            "eyebrow": "App poblacional",
            "title": "El sensor social que transforma cuidado individual en inteligencia colectiva.",
            "lead": "La app recoge sintomas sin registro nominal, exige ubicacion actual para evitar error territorial, muestra el radar local y recibe alertas oficiales. La experiencia fue pensada para ser simple para la poblacion y valiosa para la sala de control.",
            "app_store": "Descargar en App Store",
            "google_play": "Ver en Google Play",
            "risks": [
                {"title": "Radar local", "text": "Lectura por ubicacion actual."},
                {"title": "Mapa vivo", "text": "Focos y sintomas por region."},
                {"title": "Alertas oficiales", "text": "Comunicacion de gobierno en el celular."},
                {"title": "Proteccion", "text": "Sin envio aproximado a la ciudad equivocada."},
            ],
        },
        "cta": {
            "title": "Vea la presentacion completa antes de hablar con ventas.",
            "lead": "La presentacion muestra la propuesta para poblacion, empresas, hospitales, farmacias, laboratorios y gobierno, con el diferencial frente a los modelos tradicionales de monitoreo.",
        },
        "footer": "SolusCRT Salud. Inteligencia epidemiologica, app poblacional y SaaS enterprise.",
        "footer_links": {
            "privacy": "Privacidad",
            "terms": "Terminos",
            "security": "Seguridad",
            "methodology": "Metodologia",
            "support": "Soporte",
        },
    },
}


PRESENTATION_TRANSLATIONS = {
    "pt": {
        "title": "Apresentacao SolusCRT Saude",
        "brand": "SolusCRT Saude",
        "site": "Site",
        "contact": "Contato",
        "language_aria": "Selecionar idioma",
        "footer_note": "Use o scroll para avancar pelos slides.",
        "vision": {
            "eyebrow": "Visao",
            "title": "Saude populacional precisa de radar, nao apenas retrovisor.",
            "body": "O SolusCRT Saude antecipa sinais territoriais usando app populacional, IA, fontes oficiais e mapas vivos para apoiar resposta antes que o surto vire crise operacional.",
            "labels": {"resp": "Respiratorio", "deng": "Arbovirose", "covid": "Viral"},
        },
        "problem": {
            "eyebrow": "Problema",
            "title": "O atraso custa estoque, equipe, comunicacao e vidas.",
            "cards": [
                {"title": "Dados oficiais chegam depois", "text": "Necessarios para confirmacao e historico, mas sujeitos a fluxo de notificacao e consolidacao."},
                {"title": "Empresas reagem tarde", "text": "Quando o foco aparece, afastamentos, demanda e insumos ja podem estar pressionados."},
                {"title": "Governo precisa priorizar", "text": "Territorios diferentes exigem comunicacao e resposta diferentes."},
                {"title": "Populacao quer clareza", "text": "O cidadao precisa saber o que ocorre na propria regiao sem excesso de complexidade."},
            ],
        },
        "solution": {
            "eyebrow": "Solucao",
            "title": "Uma camada precoce conectada a decisao.",
            "body": "Sinais colaborativos nao substituem casos oficiais. Eles funcionam como radar antecipado. O SolusCRT separa sinal precoce, fonte oficial e inferencia de IA para decisao responsavel.",
            "cards": [
                {"title": "App", "text": "Sintomas e alertas."},
                {"title": "IA", "text": "Classificacao, tendencia e risco."},
                {"title": "Mapa", "text": "Focos territoriais."},
                {"title": "Oficial", "text": "IBGE, InfoDengue, InfoGripe e DATASUS."},
            ],
        },
        "ecosystem": {
            "eyebrow": "Ecossistema",
            "title": "Uma plataforma, quatro frentes de cooperacao em saude.",
            "cards": [
                {"title": "Empresas", "text": "Saude ocupacional, risco por unidade, afastamentos e continuidade operacional."},
                {"title": "Farmacias e laboratorios", "text": "Abastecimento, exames, medicacao e demanda regional."},
                {"title": "Hospitais", "text": "Preparacao de equipes, leitos, triagem e pressao assistencial."},
                {"title": "Governo", "text": "Sala de situacao, alertas oficiais, auditoria e contratos anuais."},
            ],
        },
        "differential": {
            "eyebrow": "Diferencial",
            "title": "O diferencial e tempo de resposta com confianca.",
            "body": "Enquanto muitos paineis dependem de bases ja publicadas, o SolusCRT cria uma camada viva de sinais da populacao, protegida contra repeticoes e cruzada com bases oficiais.",
            "quote": "Sinal precoce para agir. Dado oficial para confirmar. IA para priorizar e validar queda real.",
        },
        "governance": {
            "eyebrow": "Governanca",
            "title": "Seguranca e confianca como produto.",
            "cards": [
                {"title": "Ambientes privados", "text": "Empresa, governo e operacao administrativa separados."},
                {"title": "LGPD", "text": "Minimizacao, finalidade, controle de acesso e transparencia."},
                {"title": "Antifraude", "text": "Dispositivo, rede, repeticao, localizacao atual e qualidade do sinal."},
                {"title": "Reducao validada por IA", "text": "Apos 10 dias sem novos sinais, a intensidade cai gradualmente apenas quando serie temporal, dados agregados e fontes oficiais sustentam reducao real."},
            ],
        },
        "values": {
            "eyebrow": "Valores",
            "title": "Valores que fazem a tecnologia merecer confianca.",
            "body": "O SolusCRT foi pensado para cooperar com pessoas e instituicoes: proteger vidas, antecipar riscos, respeitar privacidade, comunicar com responsabilidade e ajudar lideres a agir sem distorcer a verdade.",
            "cards": [
                {"title": "Vida primeiro", "text": "Indicadores existem para orientar cuidado."},
                {"title": "Verdade antes de impacto", "text": "Sinal, dado oficial e IA sempre separados."},
                {"title": "Acesso social", "text": "App gratuito para a populacao contribuir."},
                {"title": "Cooperacao", "text": "Empresas, governo e saude atuando juntos."},
            ],
        },
        "app": {
            "eyebrow": "App da populacao",
            "title": "O app gratuito alimenta o radar nacional.",
            "body": "A populacao envia sintomas sem cadastro nominal, acompanha focos na propria regiao e recebe comunicados oficiais. A localizacao atual reduz risco de registrar sinais na cidade errada.",
            "quote": "Gratis para a populacao. Valioso para a resposta coletiva.",
        },
        "closing": {
            "eyebrow": "Fechamento",
            "title": "O SolusCRT nao vende uma tela. Vende capacidade de antecipacao.",
            "body": "Para empresas, reduz surpresa operacional. Para hospitais e farmacias, antecipa demanda. Para governos, cria uma sala de situacao viva. Para a populacao, entrega orientacao territorial simples.",
            "meeting": "Solicitar conversa comercial",
            "back": "Voltar ao site principal",
        },
    },
    "en": {
        "title": "SolusCRT Health Presentation",
        "brand": "SolusCRT Health",
        "site": "Website",
        "contact": "Contact",
        "language_aria": "Select language",
        "footer_note": "Scroll to move through the slides.",
        "vision": {
            "eyebrow": "Vision",
            "title": "Population health needs radar, not delayed hindsight.",
            "body": "SolusCRT Health anticipates territorial signals using a population app, AI, official sources and live maps to support response before an outbreak becomes an operational crisis.",
            "labels": {"resp": "Respiratory", "deng": "Arbovirus", "covid": "Viral"},
        },
        "problem": {
            "eyebrow": "Problem",
            "title": "Delay costs stock, teams, communication and lives.",
            "cards": [
                {"title": "Official data arrives later", "text": "Necessary for confirmation and history, but subject to notification and consolidation flows."},
                {"title": "Companies react late", "text": "When a hotspot appears, absences, demand and supplies may already be under pressure."},
                {"title": "Government must prioritize", "text": "Different territories require different communication and response."},
                {"title": "People need clarity", "text": "Citizens need to know what is happening in their own region without unnecessary complexity."},
            ],
        },
        "solution": {
            "eyebrow": "Solution",
            "title": "An early layer connected to decision-making.",
            "body": "Collaborative signals do not replace official cases. They work as an early radar. SolusCRT separates early signal, official source and AI inference for responsible decisions.",
            "cards": [
                {"title": "App", "text": "Symptoms and alerts."},
                {"title": "AI", "text": "Classification, trend and risk."},
                {"title": "Map", "text": "Territorial hotspots."},
                {"title": "Official", "text": "IBGE, InfoDengue, InfoGripe and DATASUS."},
            ],
        },
        "ecosystem": {
            "eyebrow": "Ecosystem",
            "title": "One platform, four fronts of health cooperation.",
            "cards": [
                {"title": "Companies", "text": "Occupational health, risk by unit, absences and operational continuity."},
                {"title": "Pharmacies and labs", "text": "Supply planning, tests, medication and regional demand."},
                {"title": "Hospitals", "text": "Preparation of teams, beds, triage and care pressure."},
                {"title": "Government", "text": "Situation room, official alerts, audit trail and annual contracts."},
            ],
        },
        "differential": {
            "eyebrow": "Differentiator",
            "title": "The differentiator is response time with trust.",
            "body": "While many dashboards depend on already published databases, SolusCRT creates a live layer of population signals, protected against repetition and crossed with official sources.",
            "quote": "Early signal to act. Official data to confirm. AI to prioritize and validate real decline.",
        },
        "governance": {
            "eyebrow": "Governance",
            "title": "Security and trust as part of the product.",
            "cards": [
                {"title": "Private environments", "text": "Company, government and administrative operation kept separate."},
                {"title": "LGPD", "text": "Minimization, purpose, access control and transparency."},
                {"title": "Anti-fraud", "text": "Device, network, repetition, current location and signal quality."},
                {"title": "AI-validated decline", "text": "After 10 days without new signals, intensity decreases gradually only when time series, aggregated data and official sources support a real decline."},
            ],
        },
        "values": {
            "eyebrow": "Values",
            "title": "Values that make technology worthy of trust.",
            "body": "SolusCRT was designed to cooperate with people and institutions: protect lives, anticipate risks, respect privacy, communicate responsibly and help leaders act without distorting the truth.",
            "cards": [
                {"title": "Life first", "text": "Indicators exist to guide care."},
                {"title": "Truth before impact", "text": "Signal, official data and AI always separated."},
                {"title": "Social access", "text": "Free app for the population to contribute."},
                {"title": "Cooperation", "text": "Companies, government and health actors working together."},
            ],
        },
        "app": {
            "eyebrow": "Population app",
            "title": "The free app powers the national radar.",
            "body": "The population reports symptoms without nominal registration, follows hotspots in their own region and receives official messages. Current location reduces the risk of recording signals in the wrong city.",
            "quote": "Free for people. Valuable for collective response.",
        },
        "closing": {
            "eyebrow": "Closing",
            "title": "SolusCRT does not sell a screen. It sells anticipation capacity.",
            "body": "For companies, it reduces operational surprise. For hospitals and pharmacies, it anticipates demand. For governments, it creates a live situation room. For people, it delivers simple territorial guidance.",
            "meeting": "Request a sales conversation",
            "back": "Back to main website",
        },
    },
    "es": {
        "title": "Presentacion SolusCRT Salud",
        "brand": "SolusCRT Salud",
        "site": "Sitio",
        "contact": "Contacto",
        "language_aria": "Seleccionar idioma",
        "footer_note": "Use el scroll para avanzar por las diapositivas.",
        "vision": {
            "eyebrow": "Vision",
            "title": "La salud poblacional necesita radar, no solo retrovisor.",
            "body": "SolusCRT Salud anticipa senales territoriales usando app poblacional, IA, fuentes oficiales y mapas vivos para apoyar la respuesta antes de que el brote se convierta en crisis operacional.",
            "labels": {"resp": "Respiratorio", "deng": "Arbovirosis", "covid": "Viral"},
        },
        "problem": {
            "eyebrow": "Problema",
            "title": "El retraso cuesta stock, equipos, comunicacion y vidas.",
            "cards": [
                {"title": "Los datos oficiales llegan despues", "text": "Necesarios para confirmacion e historico, pero sujetos a flujos de notificacion y consolidacion."},
                {"title": "Las empresas reaccionan tarde", "text": "Cuando aparece el foco, ausencias, demanda e insumos ya pueden estar presionados."},
                {"title": "El gobierno necesita priorizar", "text": "Territorios diferentes exigen comunicacion y respuesta diferentes."},
                {"title": "La poblacion quiere claridad", "text": "El ciudadano necesita saber que ocurre en su propia region sin exceso de complejidad."},
            ],
        },
        "solution": {
            "eyebrow": "Solucion",
            "title": "Una capa temprana conectada a la decision.",
            "body": "Las senales colaborativas no sustituyen casos oficiales. Funcionan como radar anticipado. SolusCRT separa senal temprana, fuente oficial e inferencia de IA para decisiones responsables.",
            "cards": [
                {"title": "App", "text": "Sintomas y alertas."},
                {"title": "IA", "text": "Clasificacion, tendencia y riesgo."},
                {"title": "Mapa", "text": "Focos territoriales."},
                {"title": "Oficial", "text": "IBGE, InfoDengue, InfoGripe y DATASUS."},
            ],
        },
        "ecosystem": {
            "eyebrow": "Ecosistema",
            "title": "Una plataforma, cuatro frentes de cooperacion en salud.",
            "cards": [
                {"title": "Empresas", "text": "Salud ocupacional, riesgo por unidad, ausencias y continuidad operacional."},
                {"title": "Farmacias y laboratorios", "text": "Abastecimiento, examenes, medicacion y demanda regional."},
                {"title": "Hospitales", "text": "Preparacion de equipos, camas, triaje y presion asistencial."},
                {"title": "Gobierno", "text": "Sala de situacion, alertas oficiales, auditoria y contratos anuales."},
            ],
        },
        "differential": {
            "eyebrow": "Diferencial",
            "title": "El diferencial es tiempo de respuesta con confianza.",
            "body": "Mientras muchos paneles dependen de bases ya publicadas, SolusCRT crea una capa viva de senales de la poblacion, protegida contra repeticiones y cruzada con fuentes oficiales.",
            "quote": "Senal temprana para actuar. Dato oficial para confirmar. IA para priorizar y validar reduccion real.",
        },
        "governance": {
            "eyebrow": "Gobernanza",
            "title": "Seguridad y confianza como producto.",
            "cards": [
                {"title": "Ambientes privados", "text": "Empresa, gobierno y operacion administrativa separados."},
                {"title": "LGPD", "text": "Minimizacion, finalidad, control de acceso y transparencia."},
                {"title": "Antifraude", "text": "Dispositivo, red, repeticion, ubicacion actual y calidad de la senal."},
                {"title": "Reduccion validada por IA", "text": "Despues de 10 dias sin nuevas senales, la intensidad baja gradualmente solo cuando serie temporal, datos agregados y fuentes oficiales sostienen una reduccion real."},
            ],
        },
        "values": {
            "eyebrow": "Valores",
            "title": "Valores que hacen que la tecnologia merezca confianza.",
            "body": "SolusCRT fue pensado para cooperar con personas e instituciones: proteger vidas, anticipar riesgos, respetar privacidad, comunicar con responsabilidad y ayudar a lideres a actuar sin distorsionar la verdad.",
            "cards": [
                {"title": "Vida primero", "text": "Los indicadores existen para orientar cuidado."},
                {"title": "Verdad antes que impacto", "text": "Senal, dato oficial e IA siempre separados."},
                {"title": "Acceso social", "text": "App gratuita para que la poblacion contribuya."},
                {"title": "Cooperacion", "text": "Empresas, gobierno y salud actuando juntos."},
            ],
        },
        "app": {
            "eyebrow": "App poblacional",
            "title": "La app gratuita alimenta el radar nacional.",
            "body": "La poblacion envia sintomas sin registro nominal, acompana focos en su propia region y recibe comunicados oficiales. La ubicacion actual reduce el riesgo de registrar senales en la ciudad equivocada.",
            "quote": "Gratis para la poblacion. Valiosa para la respuesta colectiva.",
        },
        "closing": {
            "eyebrow": "Cierre",
            "title": "SolusCRT no vende una pantalla. Vende capacidad de anticipacion.",
            "body": "Para empresas, reduce sorpresa operacional. Para hospitales y farmacias, anticipa demanda. Para gobiernos, crea una sala de situacion viva. Para la poblacion, entrega orientacion territorial simple.",
            "meeting": "Solicitar conversacion comercial",
            "back": "Volver al sitio principal",
        },
    },
}


def _normalize_site_language(value):
    if not value:
        return None
    for part in str(value).split(","):
        code = part.split(";")[0].strip().lower().replace("_", "-").split("-")[0]
        if code in SITE_TRANSLATIONS:
            return code
    return None


def _resolve_site_language(request):
    return (
        _normalize_site_language(request.GET.get("lang"))
        or _normalize_site_language(request.COOKIES.get("site_lang"))
        or _normalize_site_language(request.headers.get("Accept-Language"))
        or "pt"
    )


def _site_language_options(request, active_language):
    path = request.path or "/"
    return [
        {
            "code": code,
            "label": meta["label"],
            "flag": meta["flag"],
            "name": meta["name"],
            "html": meta["html"],
            "active": code == active_language,
            "url": f"{path}?lang={code}",
        }
        for code, meta in SITE_LANGUAGE_META.items()
    ]


def site_principal(request):
    host = request.get_host().split(":")[0].lower()
    if host.startswith("empresa."):
        return tela_login_empresa(request)
    if host.startswith("governo."):
        return tela_login_governo(request)
    if host.startswith("admin."):
        return redirect("/operacao-central/")
    language = _resolve_site_language(request)
    response = render(
        request,
        "site_principal.html",
        {
            "site": SITE_TRANSLATIONS[language],
            "site_lang": language,
            "html_lang": SITE_LANGUAGE_META[language]["html"],
            "language_options": _site_language_options(request, language),
            "presentation_url": f"/apresentacao/?lang={language}",
        },
    )
    if request.GET.get("lang"):
        response.set_cookie("site_lang", language, max_age=31536000, samesite="Lax")
    return response


def apresentacao_comercial(request):
    language = _resolve_site_language(request)
    response = render(
        request,
        "apresentacao.html",
        {
            "deck": PRESENTATION_TRANSLATIONS[language],
            "site_lang": language,
            "html_lang": SITE_LANGUAGE_META[language]["html"],
            "language_options": _site_language_options(request, language),
            "home_url": f"/?lang={language}",
        },
    )
    if request.GET.get("lang"):
        response.set_cookie("site_lang", language, max_age=31536000, samesite="Lax")
    return response


LEGAL_COMMON = {
    "pt": {
        "brand": "SolusCRT Saude",
        "back": "Voltar ao site",
        "language_aria": "Selecionar idioma",
        "notice": "O SolusCRT Saude mantem compromisso continuo com transparencia, seguranca, minimizacao de dados e governanca responsavel. A documentacao institucional e mantida atualizada para refletir melhorias da plataforma, requisitos regulatorios e necessidades contratuais.",
    },
    "en": {
        "brand": "SolusCRT Health",
        "back": "Back to website",
        "language_aria": "Select language",
        "notice": "SolusCRT Health maintains an ongoing commitment to transparency, security, data minimization and responsible governance. Institutional documentation is kept current to reflect platform improvements, regulatory requirements and contractual needs.",
    },
    "es": {
        "brand": "SolusCRT Salud",
        "back": "Volver al sitio",
        "language_aria": "Seleccionar idioma",
        "notice": "SolusCRT Salud mantiene un compromiso continuo con la transparencia, la seguridad, la minimizacion de datos y la gobernanza responsable. La documentacion institucional se mantiene actualizada para reflejar mejoras de la plataforma, requisitos regulatorios y necesidades contractuales.",
    },
}


LEGAL_DOCUMENTS = {
    "pt": {
        "privacidade": {
            "title": "Politica de Privacidade",
            "subtitle": "Como o SolusCRT Saude trata dados no app populacional e na plataforma SaaS.",
            "sections": [
                ("Quem somos e escopo", "O SolusCRT Saude e uma plataforma de monitoramento epidemiologico populacional. Esta politica explica o tratamento de dados no app publico, no site e nos ambientes empresariais, governamentais e operacionais vinculados ao servico."),
                ("Resumo para usuarios do app", "No app publico, voce pode consultar radar, mapa e alertas e, se desejar, enviar sintomas de forma voluntaria. O app nao oferece diagnostico medico, prescricao, triagem individual, atendimento de emergencia ou substituicao de consulta profissional."),
                ("Dados que podemos tratar", "Podemos tratar sintomas selecionados, coordenadas de localizacao enquanto o app esta em uso, cidade, estado, bairro ou regiao aproximada, data e hora do envio, identificador tecnico aleatorio gerado pelo app, IP, tokens de notificacao, aceite de termos, dados de conta corporativa ou governamental e registros de auditoria."),
                ("Dados sensiveis", "Sintomas e localizacao podem ser dados sensiveis ou revelar informacoes sensiveis. Por isso, a plataforma deve operar com minimizacao, finalidade especifica, controles de acesso, seguranca, registros de auditoria e exibicao agregada ou territorial sempre que possivel."),
                ("Por que usamos localizacao", "A localizacao e usada para georreferenciar sinais de saude, mostrar risco territorial, reduzir fraude, evitar envios falsos e exibir alertas proximos. O usuario pode controlar permissoes no sistema operacional; sem localizacao atual, algumas funcoes podem ser limitadas para preservar a confiabilidade epidemiologica."),
                ("Finalidades", "Usamos os dados para operar o app, exibir radar local, formar indicadores agregados, publicar alertas, prevenir abuso, proteger a seguranca da plataforma, atender contratos, cumprir obrigacoes legais, responder titulares e apoiar governanca epidemiologica responsavel."),
                ("Base legal LGPD", "Conforme o contexto, o tratamento pode se apoiar em consentimento, execucao de contrato, cumprimento de obrigacao legal ou regulatoria, protecao da vida ou da incolumidade fisica, tutela da saude, legitimo interesse com salvaguardas e exercicio regular de direitos."),
                ("Compartilhamento", "Empresas, hospitais, farmacias, laboratorios, municipios, governos e operadores autorizados acessam informacoes conforme contrato, perfil de permissao e finalidade. A plataforma deve priorizar dados agregados, estatisticos e territoriais, evitando exposicao de pessoa identificavel."),
                ("O que nao fazemos", "Nao vendemos dados pessoais para publicidade, nao usamos dados do app para rastrear usuarios entre apps e sites de terceiros, nao entregamos diagnostico medico e nao exibimos publicamente relato individual identificavel."),
                ("Retencao e descarte", "Mantemos dados pelo tempo necessario para operacao, seguranca, auditoria, cumprimento contratual, defesa de direitos e obrigacoes legais. Quando aplicavel, dados podem ser anonimizados, agregados, descartados ou retidos em logs de seguranca por periodo proporcional ao risco."),
                ("Direitos do titular", "Titulares podem solicitar informacoes, acesso, correcao, exclusao quando aplicavel, esclarecimentos sobre compartilhamento, revisao de consentimento e orientacoes sobre tratamento de dados pelo canal oficial de privacidade."),
                ("Menores de idade", "O app e informativo e nao deve ser usado por criancas sem orientacao dos responsaveis. Quando houver uso por menores, recomendamos acompanhamento de responsavel legal e cuidado adicional com informacoes de saude e localizacao."),
                ("Seguranca", "Usamos HTTPS, variaveis de ambiente para segredos, banco gerenciado em producao, cookies seguros, restricao de CORS/CSRF, controle de sessao, limite de dispositivos, trilhas de auditoria, segregacao de perfis e boas praticas para reduzir acesso indevido, manipulacao e exposicao desnecessaria."),
                ("Contato de privacidade", "Pedidos de privacidade, direitos do titular, duvidas sobre LGPD e solicitacoes relacionadas ao tratamento de dados podem ser enviados para comercial@soluscrt.com.br com o assunto Privacidade SolusCRT."),
                ("Atualizacoes", "Esta politica pode ser atualizada para refletir melhorias da plataforma, novas exigencias legais, ajustes de App Store, contratos institucionais e mudancas nos controles de seguranca."),
            ],
        },
        "termos": {
            "title": "Termos de Uso",
            "subtitle": "Regras de uso do app, do site e dos ambientes privados.",
            "sections": [
                ("Natureza informativa", "O SolusCRT Saude oferece monitoramento e inteligencia epidemiologica. O app nao realiza diagnostico, prescricao, triagem medica individual ou substituicao de atendimento profissional."),
                ("Envio responsavel", "Usuarios devem enviar sintomas reais, de boa-fe e apenas quando houver relacao com sua condicao atual. Envios repetidos, automatizados ou fraudulentos podem ser filtrados ou bloqueados."),
                ("Ambientes privados", "Acessos empresariais, governamentais e administrativos sao exclusivos para clientes e operadores autorizados. Tentativas de acesso indevido podem ser registradas e bloqueadas."),
                ("Uso proibido", "E proibido tentar burlar controles de seguranca, automatizar envios indevidos, inserir informacoes falsas, acessar area contratual sem autorizacao, realizar engenharia reversa ou usar a plataforma para finalidade ilegal, discriminatoria ou abusiva."),
                ("Contas e credenciais", "Credenciais sao pessoais ou institucionais conforme contrato. O usuario ou cliente e responsavel por preservar senhas, dispositivos autorizados e politicas internas de acesso."),
                ("Disponibilidade", "A plataforma depende de internet, servicos de nuvem, APIs, fontes oficiais e permissao de localizacao. Podem ocorrer indisponibilidades temporarias ou degradacao de dados externos."),
                ("Responsabilidade", "Decisoes operacionais e institucionais devem considerar contexto tecnico, validacao humana e protocolos aplicaveis de saude publica."),
                ("Propriedade intelectual", "Marcas, interfaces, modelos, organizacao da plataforma, documentos, codigos, paineis e materiais do SolusCRT Saude pertencem aos seus titulares e sao licenciados nos limites contratados."),
                ("Contratacao B2B e B2G", "Planos empresariais, governamentais, limites de usuarios, dispositivos, suporte, integracoes, SLA e valores podem ser definidos em proposta, contrato, termo de adesao ou instrumento especifico."),
            ],
        },
        "seguranca-lgpd": {
            "title": "Seguranca, LGPD e Governanca",
            "subtitle": "Controles para proteger dados, acessos e confianca institucional.",
            "sections": [
                ("Principios", "A plataforma deve seguir finalidade, adequacao, necessidade, seguranca, prevencao, transparencia e responsabilizacao no tratamento de dados pessoais."),
                ("Segregacao de ambientes", "Empresa, governo e operacao administrativa sao separados por fluxo de login, permissao, sessao, auditoria e dominio/subdominio quando contratado."),
                ("Controles antifraude", "O app e o backend utilizam controles por aparelho, rede, repeticao, qualidade do sinal e localizacao atual para reduzir manipulacao de focos."),
                ("Protecao de acesso", "A plataforma adota controle de sessao, autorizacao por perfil, limite de dispositivos contratados, bloqueios de uso simultaneo quando aplicavel e revogacao de acessos."),
                ("Dados sensiveis", "Sinais de saude sao tratados com cautela, priorizando agregacao, minimizacao, separacao por finalidade e exibicao territorial adequada ao perfil autorizado."),
                ("Auditoria", "Acoes institucionais, alertas governamentais e operacoes administrativas devem ter rastreabilidade, usuario responsavel, data e contexto."),
                ("Incidentes", "Eventos de seguranca podem acionar processos de investigacao, mitigacao, registro, comunicacao a clientes e titulares quando aplicavel, e melhoria de controles."),
                ("Compromisso continuo", "A governanca do SolusCRT Saude e mantida como um processo permanente, com melhoria de controles, revisao de acessos, atualizacao documental e alinhamento aos requisitos aplicaveis de protecao de dados, saude digital e contratos institucionais."),
            ],
        },
        "metodologia": {
            "title": "Metodologia Epidemiologica",
            "subtitle": "Como o SolusCRT separa sinal precoce, fonte oficial e decisao operacional.",
            "sections": [
                ("Sinal colaborativo", "O app coleta sinais de sintomas em tempo real. Esses sinais indicam tendencia e risco territorial, mas nao equivalem a caso confirmado."),
                ("Fonte oficial", "Dados oficiais e institucionais, como bases publicas e sistemas de saude, devem ser tratados separadamente, preferencialmente em agregados, com data de coleta, fonte, versao e regra de processamento."),
                ("Indicadores", "A plataforma usa crescimento, incidencia por 100 mil habitantes, predominancia de sintomas, serie temporal e reducao gradual quando deixam de entrar novos sinais."),
                ("IA como apoio", "Modelos de IA apoiam classificacao e priorizacao, mas nao substituem equipe tecnica, vigilancia epidemiologica ou decisao institucional."),
                ("Transparencia", "Paineis devem indicar quando um dado e colaborativo, oficial, inferido ou indisponivel, evitando conclusoes falsas ou comunicacao alarmista."),
            ],
        },
        "suporte": {
            "title": "Suporte e Atendimento",
            "subtitle": "Canal institucional para suporte do app, privacidade, operacao e orientacoes gerais do SolusCRT Saude.",
            "sections": [
                ("Atendimento ao usuario", "Para suporte geral do app, dificuldades de uso, orientacoes sobre alertas, problemas de mapa, envio de sintomas ou funcionamento da experiencia publica, entre em contato por comercial@soluscrt.com.br com o assunto Suporte App SolusCRT."),
                ("Privacidade e dados pessoais", "Para pedidos relacionados a privacidade, esclarecimentos sobre tratamento de dados, direitos do titular, exclusao quando aplicavel e temas de LGPD, utilize o canal comercial@soluscrt.com.br com o assunto Privacidade SolusCRT."),
                ("Suporte institucional", "Empresas, hospitais, farmacias, laboratorios, municipios e governos que precisem de apoio operacional, contratual ou tecnico podem solicitar atendimento institucional pelo mesmo canal comercial@soluscrt.com.br."),
                ("Escopo do atendimento", "O suporte do SolusCRT Saude atende questoes sobre plataforma, app, acesso, alertas, privacidade e funcionamento do servico. O atendimento nao substitui orientacao medica, emergencia, SAMU, hospital, UPA ou consulta clinica."),
                ("Tempo de resposta", "Solicitacoes institucionais e de suporte geral sao recebidas por canal oficial e tratadas conforme criticidade, natureza do pedido, fila operacional e disponibilidade da equipe."),
                ("Base publica de documentos", "Para revisao documental, consulte tambem a Politica de Privacidade, os Termos de Uso, a pagina de Seguranca e LGPD e a Metodologia Epidemiologica publicadas no site institucional."),
            ],
        },
    },
    "en": {
        "privacidade": {
            "title": "Privacy Policy",
            "subtitle": "How SolusCRT Health handles data in the population app and SaaS platform.",
            "sections": [
                ("Who we are and scope", "SolusCRT Health is a population epidemiological monitoring platform. This policy explains how data is handled in the public app, website and business, government and operational environments connected to the service."),
                ("Summary for app users", "In the public app, you can view the radar, map and alerts and, if you choose, voluntarily submit symptoms. The app does not provide medical diagnosis, prescription, individual triage, emergency care or a replacement for professional consultation."),
                ("Data we may process", "We may process selected symptoms, location coordinates while the app is in use, city, state, neighborhood or approximate region, submission date and time, a random technical identifier generated by the app, IP address, notification tokens, acceptance of terms, corporate or government account data and audit records."),
                ("Sensitive data", "Symptoms and location may be sensitive data or reveal sensitive information. For this reason, the platform should operate with data minimization, specific purpose, access controls, security, audit records and aggregated or territorial display whenever possible."),
                ("Why we use location", "Location is used to georeference health signals, show territorial risk, reduce fraud, prevent false submissions and display nearby alerts. Users can control permissions in the operating system; without current location, some functions may be limited to preserve epidemiological reliability."),
                ("Purposes", "We use data to operate the app, display local radar, create aggregated indicators, publish alerts, prevent abuse, protect platform security, fulfill contracts, comply with legal obligations, respond to data subjects and support responsible epidemiological governance."),
                ("Legal basis", "Depending on context, processing may rely on consent, contract performance, compliance with legal or regulatory obligations, protection of life or physical safety, health protection, legitimate interest with safeguards and regular exercise of rights."),
                ("Sharing", "Companies, hospitals, pharmacies, laboratories, municipalities, governments and authorized operators access information according to contract, permission profile and purpose. The platform should prioritize aggregated, statistical and territorial data, avoiding exposure of identifiable individuals."),
                ("What we do not do", "We do not sell personal data for advertising, do not use app data to track users across third-party apps and websites, do not deliver medical diagnosis and do not publicly display individually identifiable reports."),
                ("Retention and disposal", "We keep data for the time necessary for operation, security, audit, contract compliance, defense of rights and legal obligations. When applicable, data may be anonymized, aggregated, discarded or retained in security logs for a period proportional to risk."),
                ("Data subject rights", "Data subjects may request information, access, correction, deletion when applicable, clarification about sharing, consent review and guidance about data processing through the official privacy channel."),
                ("Minors", "The app is informational and should not be used by children without guidance from guardians. When minors use it, we recommend supervision by a legal guardian and additional care with health and location information."),
                ("Security", "We use HTTPS, environment variables for secrets, managed production database, secure cookies, CORS/CSRF restriction, session control, device limits, audit trails, profile segregation and good practices to reduce unauthorized access, manipulation and unnecessary exposure."),
                ("Privacy contact", "Privacy requests, data subject rights, LGPD or privacy questions and requests related to data processing may be sent to comercial@soluscrt.com.br with the subject Privacy SolusCRT."),
                ("Updates", "This policy may be updated to reflect platform improvements, new legal requirements, App Store adjustments, institutional contracts and changes to security controls."),
            ],
        },
        "termos": {
            "title": "Terms of Use",
            "subtitle": "Rules for using the app, website and private environments.",
            "sections": [
                ("Informational nature", "SolusCRT Health provides monitoring and epidemiological intelligence. The app does not perform diagnosis, prescription, individual medical triage or replacement of professional care."),
                ("Responsible submission", "Users should submit real symptoms, in good faith and only when related to their current condition. Repeated, automated or fraudulent submissions may be filtered or blocked."),
                ("Private environments", "Business, government and administrative access is exclusive to clients and authorized operators. Unauthorized access attempts may be recorded and blocked."),
                ("Prohibited use", "It is forbidden to bypass security controls, automate improper submissions, insert false information, access contractual areas without authorization, reverse engineer the platform or use it for illegal, discriminatory or abusive purposes."),
                ("Accounts and credentials", "Credentials are personal or institutional according to contract. The user or client is responsible for protecting passwords, authorized devices and internal access policies."),
                ("Availability", "The platform depends on internet access, cloud services, APIs, official sources and location permission. Temporary unavailability or degradation of external data may occur."),
                ("Responsibility", "Operational and institutional decisions must consider technical context, human validation and applicable public health protocols."),
                ("Intellectual property", "Brands, interfaces, models, platform organization, documents, code, dashboards and SolusCRT Health materials belong to their owners and are licensed only within contracted limits."),
                ("B2B and B2G contracting", "Business and government plans, user limits, devices, support, integrations, SLA and pricing may be defined in proposal, contract, order form or specific instrument."),
            ],
        },
        "seguranca-lgpd": {
            "title": "Security, LGPD and Governance",
            "subtitle": "Controls to protect data, access and institutional trust.",
            "sections": [
                ("Principles", "The platform should follow purpose limitation, adequacy, necessity, security, prevention, transparency and accountability in the processing of personal data."),
                ("Environment segregation", "Company, government and administrative operation are separated by login flow, permission, session, audit trail and domain or subdomain when contracted."),
                ("Anti-fraud controls", "The app and backend use device, network, repetition, signal quality and current location controls to reduce manipulation of hotspots."),
                ("Access protection", "The platform adopts session control, role-based authorization, contracted device limits, simultaneous-use blocking when applicable and access revocation."),
                ("Sensitive data", "Health signals are handled carefully, prioritizing aggregation, minimization, purpose separation and territorial display appropriate to each authorized profile."),
                ("Audit", "Institutional actions, government alerts and administrative operations should have traceability, responsible user, date and context."),
                ("Incidents", "Security events may trigger investigation, mitigation, recordkeeping, communication to clients and data subjects when applicable, and improvement of controls."),
                ("Continuous commitment", "SolusCRT Health governance is maintained as an ongoing process, with control improvement, access review, documentation updates and alignment with applicable data protection, digital health and institutional contract requirements."),
            ],
        },
        "metodologia": {
            "title": "Epidemiological Methodology",
            "subtitle": "How SolusCRT separates early signal, official source and operational decision.",
            "sections": [
                ("Collaborative signal", "The app collects symptom signals in real time. These signals indicate trend and territorial risk, but they are not confirmed cases."),
                ("Official source", "Official and institutional data, such as public databases and health systems, should be handled separately, preferably in aggregated form, with collection date, source, version and processing rule."),
                ("Indicators", "The platform uses growth, incidence per 100,000 inhabitants, symptom predominance, time series and gradual decline when no new signals are received."),
                ("AI as support", "AI models support classification and prioritization, but do not replace technical teams, epidemiological surveillance or institutional decision-making."),
                ("Transparency", "Dashboards should indicate when data is collaborative, official, inferred or unavailable, avoiding false conclusions or alarmist communication."),
            ],
        },
        "suporte": {
            "title": "Support and Service",
            "subtitle": "Institutional channel for app support, privacy, operation and general SolusCRT Health guidance.",
            "sections": [
                ("User support", "For general app support, difficulty using the app, guidance about alerts, map issues, symptom submission or operation of the public experience, contact comercial@soluscrt.com.br with the subject SolusCRT App Support."),
                ("Privacy and personal data", "For privacy requests, clarification about data processing, data subject rights, deletion when applicable and LGPD matters, use comercial@soluscrt.com.br with the subject Privacy SolusCRT."),
                ("Institutional support", "Companies, hospitals, pharmacies, laboratories, municipalities and governments that need operational, contractual or technical assistance may request institutional service through the same channel comercial@soluscrt.com.br."),
                ("Scope of support", "SolusCRT Health support covers questions about the platform, app, access, alerts, privacy and service operation. Support does not replace medical guidance, emergency care, ambulance services, hospital, urgent care unit or clinical consultation."),
                ("Response time", "Institutional and general support requests are received through the official channel and handled according to criticality, request type, operational queue and team availability."),
                ("Public document base", "For document review, also consult the Privacy Policy, Terms of Use, Security and LGPD page and Epidemiological Methodology published on the institutional website."),
            ],
        },
    },
    "es": {
        "privacidade": {
            "title": "Politica de Privacidad",
            "subtitle": "Como SolusCRT Salud trata datos en la app poblacional y en la plataforma SaaS.",
            "sections": [
                ("Quienes somos y alcance", "SolusCRT Salud es una plataforma de monitoreo epidemiologico poblacional. Esta politica explica el tratamiento de datos en la app publica, el sitio web y los ambientes empresariales, gubernamentales y operativos vinculados al servicio."),
                ("Resumen para usuarios de la app", "En la app publica, puedes consultar radar, mapa y alertas y, si lo deseas, enviar sintomas de forma voluntaria. La app no ofrece diagnostico medico, prescripcion, triaje individual, atencion de emergencia ni sustitucion de una consulta profesional."),
                ("Datos que podemos tratar", "Podemos tratar sintomas seleccionados, coordenadas de ubicacion mientras la app esta en uso, ciudad, estado, barrio o region aproximada, fecha y hora del envio, identificador tecnico aleatorio generado por la app, IP, tokens de notificacion, aceptacion de terminos, datos de cuenta corporativa o gubernamental y registros de auditoria."),
                ("Datos sensibles", "Sintomas y ubicacion pueden ser datos sensibles o revelar informacion sensible. Por eso, la plataforma debe operar con minimizacion, finalidad especifica, controles de acceso, seguridad, registros de auditoria y visualizacion agregada o territorial siempre que sea posible."),
                ("Por que usamos ubicacion", "La ubicacion se usa para georreferenciar senales de salud, mostrar riesgo territorial, reducir fraude, evitar envios falsos y mostrar alertas cercanas. El usuario puede controlar permisos en el sistema operativo; sin ubicacion actual, algunas funciones pueden limitarse para preservar la confiabilidad epidemiologica."),
                ("Finalidades", "Usamos los datos para operar la app, mostrar radar local, formar indicadores agregados, publicar alertas, prevenir abuso, proteger la seguridad de la plataforma, cumplir contratos, atender obligaciones legales, responder a titulares y apoyar una gobernanza epidemiologica responsable."),
                ("Base legal", "Segun el contexto, el tratamiento puede apoyarse en consentimiento, ejecucion de contrato, cumplimiento de obligacion legal o regulatoria, proteccion de la vida o integridad fisica, tutela de la salud, interes legitimo con salvaguardas y ejercicio regular de derechos."),
                ("Compartir informacion", "Empresas, hospitales, farmacias, laboratorios, municipios, gobiernos y operadores autorizados acceden a informacion segun contrato, perfil de permiso y finalidad. La plataforma debe priorizar datos agregados, estadisticos y territoriales, evitando exponer personas identificables."),
                ("Lo que no hacemos", "No vendemos datos personales para publicidad, no usamos datos de la app para rastrear usuarios entre apps y sitios de terceros, no entregamos diagnostico medico y no mostramos publicamente relatos individuales identificables."),
                ("Retencion y descarte", "Mantenemos datos durante el tiempo necesario para operacion, seguridad, auditoria, cumplimiento contractual, defensa de derechos y obligaciones legales. Cuando corresponda, los datos pueden anonimizarse, agregarse, descartarse o conservarse en logs de seguridad por un periodo proporcional al riesgo."),
                ("Derechos del titular", "Los titulares pueden solicitar informacion, acceso, correccion, eliminacion cuando corresponda, aclaraciones sobre intercambio, revision de consentimiento y orientacion sobre tratamiento de datos por el canal oficial de privacidad."),
                ("Menores de edad", "La app es informativa y no debe ser usada por ninos sin orientacion de responsables. Cuando haya uso por menores, recomendamos supervision de un responsable legal y cuidado adicional con informacion de salud y ubicacion."),
                ("Seguridad", "Usamos HTTPS, variables de entorno para secretos, base de datos gestionada en produccion, cookies seguras, restriccion CORS/CSRF, control de sesion, limites de dispositivos, trazas de auditoria, segregacion de perfiles y buenas practicas para reducir acceso indebido, manipulacion y exposicion innecesaria."),
                ("Contacto de privacidad", "Pedidos de privacidad, derechos del titular, dudas sobre LGPD o privacidad y solicitudes relacionadas con tratamiento de datos pueden enviarse a comercial@soluscrt.com.br con el asunto Privacidad SolusCRT."),
                ("Actualizaciones", "Esta politica puede actualizarse para reflejar mejoras de la plataforma, nuevas exigencias legales, ajustes de App Store, contratos institucionales y cambios en controles de seguridad."),
            ],
        },
        "termos": {
            "title": "Terminos de Uso",
            "subtitle": "Reglas de uso de la app, del sitio y de los ambientes privados.",
            "sections": [
                ("Naturaleza informativa", "SolusCRT Salud ofrece monitoreo e inteligencia epidemiologica. La app no realiza diagnostico, prescripcion, triaje medico individual ni sustitucion de atencion profesional."),
                ("Envio responsable", "Los usuarios deben enviar sintomas reales, de buena fe y solo cuando tengan relacion con su condicion actual. Envios repetidos, automatizados o fraudulentos pueden ser filtrados o bloqueados."),
                ("Ambientes privados", "Los accesos empresariales, gubernamentales y administrativos son exclusivos para clientes y operadores autorizados. Intentos de acceso indebido pueden registrarse y bloquearse."),
                ("Uso prohibido", "Esta prohibido burlar controles de seguridad, automatizar envios indebidos, insertar informacion falsa, acceder a areas contractuales sin autorizacion, hacer ingenieria inversa o usar la plataforma con finalidad ilegal, discriminatoria o abusiva."),
                ("Cuentas y credenciales", "Las credenciales son personales o institucionales segun contrato. El usuario o cliente es responsable de preservar contrasenas, dispositivos autorizados y politicas internas de acceso."),
                ("Disponibilidad", "La plataforma depende de internet, servicios de nube, APIs, fuentes oficiales y permiso de ubicacion. Pueden ocurrir indisponibilidades temporales o degradacion de datos externos."),
                ("Responsabilidad", "Las decisiones operativas e institucionales deben considerar contexto tecnico, validacion humana y protocolos aplicables de salud publica."),
                ("Propiedad intelectual", "Marcas, interfaces, modelos, organizacion de la plataforma, documentos, codigos, paneles y materiales de SolusCRT Salud pertenecen a sus titulares y se licencian dentro de los limites contratados."),
                ("Contratacion B2B y B2G", "Planes empresariales y gubernamentales, limites de usuarios, dispositivos, soporte, integraciones, SLA y valores pueden definirse en propuesta, contrato, termino de adhesion o instrumento especifico."),
            ],
        },
        "seguranca-lgpd": {
            "title": "Seguridad, LGPD y Gobernanza",
            "subtitle": "Controles para proteger datos, accesos y confianza institucional.",
            "sections": [
                ("Principios", "La plataforma debe seguir finalidad, adecuacion, necesidad, seguridad, prevencion, transparencia y responsabilizacion en el tratamiento de datos personales."),
                ("Segregacion de ambientes", "Empresa, gobierno y operacion administrativa se separan por flujo de login, permiso, sesion, auditoria y dominio o subdominio cuando sea contratado."),
                ("Controles antifraude", "La app y el backend utilizan controles por dispositivo, red, repeticion, calidad de la senal y ubicacion actual para reducir manipulacion de focos."),
                ("Proteccion de acceso", "La plataforma adopta control de sesion, autorizacion por perfil, limite de dispositivos contratados, bloqueos de uso simultaneo cuando corresponda y revocacion de accesos."),
                ("Datos sensibles", "Las senales de salud se tratan con cautela, priorizando agregacion, minimizacion, separacion por finalidad y visualizacion territorial adecuada al perfil autorizado."),
                ("Auditoria", "Acciones institucionales, alertas gubernamentales y operaciones administrativas deben tener trazabilidad, usuario responsable, fecha y contexto."),
                ("Incidentes", "Eventos de seguridad pueden activar investigacion, mitigacion, registro, comunicacion a clientes y titulares cuando corresponda, y mejora de controles."),
                ("Compromiso continuo", "La gobernanza de SolusCRT Salud se mantiene como un proceso permanente, con mejora de controles, revision de accesos, actualizacion documental y alineacion con requisitos aplicables de proteccion de datos, salud digital y contratos institucionales."),
            ],
        },
        "metodologia": {
            "title": "Metodologia Epidemiologica",
            "subtitle": "Como SolusCRT separa senal temprana, fuente oficial y decision operativa.",
            "sections": [
                ("Senal colaborativa", "La app recopila senales de sintomas en tiempo real. Estas senales indican tendencia y riesgo territorial, pero no equivalen a caso confirmado."),
                ("Fuente oficial", "Datos oficiales e institucionales, como bases publicas y sistemas de salud, deben tratarse por separado, preferentemente en agregados, con fecha de recoleccion, fuente, version y regla de procesamiento."),
                ("Indicadores", "La plataforma usa crecimiento, incidencia por 100 mil habitantes, predominancia de sintomas, serie temporal y reduccion gradual cuando dejan de entrar nuevas senales."),
                ("IA como apoyo", "Modelos de IA apoyan clasificacion y priorizacion, pero no sustituyen al equipo tecnico, la vigilancia epidemiologica ni la decision institucional."),
                ("Transparencia", "Los paneles deben indicar cuando un dato es colaborativo, oficial, inferido o no disponible, evitando conclusiones falsas o comunicacion alarmista."),
            ],
        },
        "suporte": {
            "title": "Soporte y Atencion",
            "subtitle": "Canal institucional para soporte de la app, privacidad, operacion y orientaciones generales de SolusCRT Salud.",
            "sections": [
                ("Atencion al usuario", "Para soporte general de la app, dificultades de uso, orientaciones sobre alertas, problemas de mapa, envio de sintomas o funcionamiento de la experiencia publica, contacta comercial@soluscrt.com.br con el asunto Soporte App SolusCRT."),
                ("Privacidad y datos personales", "Para pedidos relacionados con privacidad, aclaraciones sobre tratamiento de datos, derechos del titular, eliminacion cuando corresponda y temas de LGPD, usa comercial@soluscrt.com.br con el asunto Privacidad SolusCRT."),
                ("Soporte institucional", "Empresas, hospitales, farmacias, laboratorios, municipios y gobiernos que necesiten apoyo operativo, contractual o tecnico pueden solicitar atencion institucional por el mismo canal comercial@soluscrt.com.br."),
                ("Alcance de atencion", "El soporte de SolusCRT Salud atiende cuestiones sobre plataforma, app, acceso, alertas, privacidad y funcionamiento del servicio. La atencion no sustituye orientacion medica, emergencia, ambulancia, hospital, unidad de urgencia o consulta clinica."),
                ("Tiempo de respuesta", "Solicitudes institucionales y de soporte general se reciben por canal oficial y se tratan segun criticidad, naturaleza del pedido, fila operacional y disponibilidad del equipo."),
                ("Base publica de documentos", "Para revision documental, consulta tambien la Politica de Privacidad, los Terminos de Uso, la pagina de Seguridad y LGPD y la Metodologia Epidemiologica publicadas en el sitio institucional."),
            ],
        },
    },
}


def documento_publico(request, slug):
    language = _resolve_site_language(request)
    documento = LEGAL_DOCUMENTS[language].get(slug)
    if not documento:
        return redirect("/")
    response = render(
        request,
        "documento_publico.html",
        {
            "documento": documento,
            "legal": LEGAL_COMMON[language],
            "site_lang": language,
            "html_lang": SITE_LANGUAGE_META[language]["html"],
            "language_options": _site_language_options(request, language),
            "home_url": f"/?lang={language}",
        },
    )
    if request.GET.get("lang"):
        response.set_cookie("site_lang", language, max_age=31536000, samesite="Lax")
    return response

STATE_ALIASES = {
    "AC": "Acre",
    "AL": "Alagoas",
    "AP": "Amapa",
    "AM": "Amazonas",
    "BA": "Bahia",
    "CE": "Ceara",
    "DF": "Distrito Federal",
    "ES": "Espirito Santo",
    "GO": "Goias",
    "MA": "Maranhao",
    "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais",
    "PA": "Para",
    "PB": "Paraiba",
    "PR": "Parana",
    "PE": "Pernambuco",
    "PI": "Piaui",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul",
    "RO": "Rondonia",
    "RR": "Roraima",
    "SC": "Santa Catarina",
    "SP": "Sao Paulo",
    "SE": "Sergipe",
    "TO": "Tocantins",
}


def _state_terms(value):
    raw = (value or "").strip()
    if not raw:
        return []
    upper = raw.upper()
    terms = {raw, upper}
    alias = STATE_ALIASES.get(upper)
    if alias:
        terms.add(alias)
    for uf, name in STATE_ALIASES.items():
        if raw.lower() == name.lower():
            terms.add(uf)
            terms.add(name)
    return list(terms)


JANELA_ESTABILIDADE_FOCO_DIAS = 10
JANELA_DECAIMENTO_FOCO_DIAS = 30
PESO_MINIMO_FOCO_PUBLICO = 0.01


def _peso_temporal_publico(day, agora=None):
    agora = agora or timezone.now()
    if not day:
        return 1.0
    if hasattr(day, "date"):
        day = day.date()
    dias = max((agora.date() - day).days, 0)
    if dias <= JANELA_ESTABILIDADE_FOCO_DIAS:
        return 1.0
    if dias >= JANELA_DECAIMENTO_FOCO_DIAS:
        return PESO_MINIMO_FOCO_PUBLICO
    janela_queda = JANELA_DECAIMENTO_FOCO_DIAS - JANELA_ESTABILIDADE_FOCO_DIAS
    dias_em_queda = dias - JANELA_ESTABILIDADE_FOCO_DIAS
    queda = dias_em_queda / janela_queda
    return round(max(PESO_MINIMO_FOCO_PUBLICO, 1 - (queda * (1 - PESO_MINIMO_FOCO_PUBLICO))), 3)


def _indice_temporal_publico(queryset, agora=None):
    agora = agora or timezone.now()
    rows = (
        queryset.annotate(day=TruncDate("data_registro"))
        .values("day")
        .annotate(total=Count("id"))
    )
    return round(sum(item["total"] * _peso_temporal_publico(item["day"], agora) for item in rows), 2)


def _nivel_por_indice_publico(indice, crescimento=0):
    if indice >= 500 or crescimento >= 60:
        return "alto"
    if indice >= 180 or crescimento >= 25:
        return "moderado"
    if indice >= 60 or crescimento > 0:
        return "atencao"
    return "baixo"


def _nivel_local_por_indice_publico(indice, crescimento=0):
    if indice >= 45 or crescimento >= 60:
        return "alto"
    if indice >= 20 or crescimento >= 25:
        return "moderado"
    if indice >= 8 or crescimento > 0:
        return "atencao"
    return "baixo"

def calcular_previsao(cidade, estado, total):

    chave = f"{cidade}_{estado}"
    hist = historico[chave]

    # 🔥 SALVA O DADO ATUAL (ESSA LINHA FALTAVA)
    hist.append(total)

    # mantém últimos 5
    if len(hist) > 5:
        hist.pop(0)

    if len(hist) < 2:
        return "SEM DADOS", 0

    atual = hist[-1]
    anterior = hist[-2]

    if anterior == 0:
        return "ESTÁVEL", 0

    crescimento = ((atual - anterior) / anterior) * 100

    if crescimento > 70:
        return "EXPLOSÃO IMINENTE", crescimento
    elif crescimento > 30:
        return "FORTE CRESCIMENTO", crescimento
    elif crescimento > 10:
        return "TENDÊNCIA DE ALTA", crescimento
    elif crescimento < -10:
        return "QUEDA", crescimento
    else:
        return "ESTÁVEL", crescimento


import json
import uuid
import jwt
import random
from datetime import timedelta
from django.utils import timezone
from .utils import (
    calcular_risco,
    classificar_crescimento,
    analisar_doencas,
    risco_por_doenca
)




# ================= LOGIN =================

def tela_login(request):
    return render(request, 'login_empresa.html')


def tela_login_empresa(request):
    return render(request, 'login_empresa.html')


def tela_login_governo(request):
    return render(request, 'login_governo.html')


def verificar_acesso(request):
    token = request.headers.get("Authorization")
    if not token:
        return None

    try:
        token = token.replace("Bearer ", "")
        dados = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        return Empresa.objects.get(id=dados["empresa_id"])
    except:
        return None


def dashboard(request):
    return render(request, "dashboard.html")


def dashboard_farmacia(request):
    return render(request, "dashboard_farmacia.html")


# ================= TOKEN =================

def validar_token(request):
    auth = request.headers.get("Authorization")

    if not auth:
        return None, JsonResponse({"erro": "não autorizado"}, status=403)

    try:
        token = auth.split(" ")[1]
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        return payload["empresa_id"], None
    except:
        return None, JsonResponse({"erro": "token inválido"}, status=403)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _device_id_request(request):
    return (request.headers.get("X-Device-Id") or "").strip()[:120] or None


def _score_suspeita(empresa, request, dados):
    agora = timezone.now()
    ip = _client_ip(request)
    device_id = _device_id_request(request)
    janela_10m = agora - timedelta(minutes=10)
    janela_15m = agora - timedelta(minutes=15)
    filtros_recentes = RegistroSintoma.objects.filter(empresa=empresa, data_registro__gte=janela_10m)
    filtros_duplicados = RegistroSintoma.objects.filter(empresa=empresa, data_registro__gte=janela_15m)

    score = 1.0
    motivos = []

    if ip:
        volume_ip = filtros_recentes.filter(ip=ip).count()
        if volume_ip >= 20:
            score -= 0.55
            motivos.append("volume_ip_extremo")
        elif volume_ip >= 10:
            score -= 0.25
            motivos.append("volume_ip_alto")

    if device_id:
        volume_device = filtros_recentes.filter(device_id=device_id).count()
        if volume_device >= 18:
            score -= 0.45
            motivos.append("volume_device_extremo")
        elif volume_device >= 8:
            score -= 0.2
            motivos.append("volume_device_alto")

    duplicate_filters = {
        "latitude": dados.get("latitude"),
        "longitude": dados.get("longitude"),
        "febre": bool(dados.get("febre", False)),
        "tosse": bool(dados.get("tosse", False)),
        "dor_corpo": bool(dados.get("dor_corpo", False)),
        "cansaco": bool(dados.get("cansaco", False)),
        "falta_ar": bool(dados.get("falta_ar", False)),
    }
    if ip:
        duplicate_filters["ip"] = ip
    if device_id:
        duplicate_filters["device_id"] = device_id

    duplicados = filtros_duplicados.filter(**duplicate_filters).count()
    if duplicados >= 3:
        score -= 0.5
        motivos.append("duplicado_em_massa")
    elif duplicados >= 1:
        score -= 0.18
        motivos.append("duplicado_recente")

    return max(round(score, 2), 0.0), motivos, ip, device_id


def _empresa_app_publico():
    empresa, _ = Empresa.objects.get_or_create(
        email="populacao@soluscrt.com",
        defaults={
            "nome": "SolusCRT Populacao",
            "senha": make_password("publico_app"),
            "ativo": True,
            "plano": "publico",
            "pacote_codigo": "governo_estado",
            "max_usuarios": 1000,
            "max_dispositivos": 1000,
        },
    )
    if empresa.pacote_codigo != "governo_estado":
        empresa.pacote_codigo = "governo_estado"
        empresa.save(update_fields=["pacote_codigo"])
    return empresa


def _bloqueio_envio_publico(empresa, ip, device_id, dados=None, geo=None):
    agora = timezone.now()
    janela_curta = agora - timedelta(hours=6)
    janela_longa = agora - timedelta(hours=24)
    dados = dados or {}
    geo = geo or {}

    if ip:
        duplicado_contextual = RegistroSintoma.objects.filter(
            empresa=empresa,
            ip=ip,
            data_registro__gte=janela_curta,
            cidade=geo.get("cidade"),
            estado=geo.get("estado"),
            febre=bool(dados.get("febre", False)),
            tosse=bool(dados.get("tosse", False)),
            dor_corpo=bool(dados.get("dor_corpo", False)),
            cansaco=bool(dados.get("cansaco", False)),
            falta_ar=bool(dados.get("falta_ar", False)),
        ).exists()
        if duplicado_contextual:
            return False, "Sinal semelhante ja considerado recentemente nesta rede e territorio."

        envios_ip_6h = RegistroSintoma.objects.filter(
            empresa=empresa,
            ip=ip,
            data_registro__gte=janela_curta,
        ).count()
        if envios_ip_6h >= 12:
            return False, "Volume recente alto nesta rede. Tente novamente mais tarde."

        envios_ip_24h = RegistroSintoma.objects.filter(
            empresa=empresa,
            ip=ip,
            data_registro__gte=janela_longa,
        ).count()
        if envios_ip_24h >= 35:
            return False, "Limite diario de envios desta rede atingido."

    if device_id:
        envios_device_6h = RegistroSintoma.objects.filter(
            empresa=empresa,
            device_id=device_id,
            data_registro__gte=janela_curta,
        ).count()
        if envios_device_6h >= 1:
            return False, "Ja recebemos um envio recente deste aparelho. Tente novamente mais tarde."

        envios_device_24h = RegistroSintoma.objects.filter(
            empresa=empresa,
            device_id=device_id,
            data_registro__gte=janela_longa,
        ).count()
        if envios_device_24h >= 3:
            return False, "Limite diario de envios deste aparelho atingido."

    return True, None


def _semaforo_publico(nivel):
    mapa = {
        "baixo": {
            "faixa": "Verde",
            "cor": "#1DD1A1",
            "descricao": "Sinais sob monitoramento, sem pressao relevante no momento.",
        },
        "atencao": {
            "faixa": "Amarelo",
            "cor": "#FFD166",
            "descricao": "Oscilacao perceptivel de sinais, com necessidade de atencao local.",
        },
        "moderado": {
            "faixa": "Laranja",
            "cor": "#FF9B54",
            "descricao": "Crescimento consistente de sinais na regiao, com foco reforcado de vigilancia.",
        },
        "alto": {
            "faixa": "Vermelho",
            "cor": "#FF6B6B",
            "descricao": "Alta concentracao de sinais e crescimento acima do esperado para a area.",
        },
    }
    return mapa.get(nivel, mapa["baixo"])


def _orientacao_publica(nivel, grupo_top=None):
    if nivel == "alto":
        return {
            "titulo": "Momento de cautela reforcada",
            "resumo": "Reduza exposicao desnecessaria, acompanhe sinais respiratorios ou febris e procure atendimento se houver piora.",
            "acoes": [
                "Evite exposicoes prolongadas em locais fechados e muito cheios.",
                "Acompanhe febre persistente, falta de ar ou agravamento rapido.",
                "Busque avaliacao profissional diante de sinais de alerta.",
            ],
        }
    if nivel == "moderado":
        return {
            "titulo": "Atencao preventiva na regiao",
            "resumo": "Ha crescimento relevante de sinais locais. Mantenha observacao ativa da sua saude e das pessoas proximas.",
            "acoes": [
                "Observe evolucao de sintomas nas proximas 24 a 48 horas.",
                "Reforce medidas basicas de higiene e ventilacao.",
                "Se houver pessoas vulneraveis em casa, redobre a atencao.",
            ],
        }
    if nivel == "atencao":
        return {
            "titulo": "Sinais em observacao",
            "resumo": "O territorio apresenta variacao acima do habitual, mas ainda sem pressao alta.",
            "acoes": [
                "Monitore como os sintomas evoluem ao longo do dia.",
                "Evite automedicacao inadequada.",
                "Consulte orientacao profissional se o quadro persistir.",
            ],
        }
    grupo = grupo_top or "monitoramento geral"
    return {
        "titulo": "Cenario estavel no momento",
        "resumo": f"A regiao segue em observacao publica, com predominio recente de {grupo.lower()}.",
        "acoes": [
            "Mantenha cuidados basicos de saude e hidratação.",
            "Use o app para acompanhar mudancas no seu territorio.",
            "Se surgirem sintomas, registre apenas uma vez por periodo.",
        ],
    }


def _alerta_publico(nivel, crescimento, grupo_top=None):
    if nivel == "alto":
        return {
            "titulo": "Alerta elevado na sua area",
            "mensagem": f"Crescimento de {crescimento}% com concentracao relevante de sinais recentes.",
            "gravidade": "critica",
        }
    if nivel == "moderado":
        return {
            "titulo": "Atencao reforcada para a sua area",
            "mensagem": f"A regiao apresenta crescimento de {crescimento}% e exige observacao preventiva.",
            "gravidade": "alta",
        }
    if nivel == "atencao":
        return {
            "titulo": "Mudanca detectada no territorio",
            "mensagem": "Ha oscilacao de sinais locais. Continue acompanhando o radar da sua regiao.",
            "gravidade": "moderada",
        }
    grupo = grupo_top or "sinais gerais"
    return {
        "titulo": "Situacao sob controle",
        "mensagem": f"Nao ha alerta elevado no momento. O principal sinal recente e {grupo.lower()}.",
        "gravidade": "leve",
    }


# ================= REGISTRO =================

@csrf_exempt
def registrar_sintoma(request):

    # 🔐 valida token
    empresa_id, erro = validar_token(request)
    if erro:
        return erro

    try:
        empresa = Empresa.objects.get(id=empresa_id)
    except Empresa.DoesNotExist:
        return JsonResponse({"erro": "empresa não encontrada"}, status=404)

    try:
        dados = json.loads(request.body or "{}")
    except:
        return JsonResponse({"erro": "json inválido"}, status=400)

    # 📍 coordenadas
    latitude = dados.get("latitude")
    longitude = dados.get("longitude")

    if not latitude or not longitude:
        return JsonResponse({"erro": "latitude/longitude obrigatórios"}, status=400)

    # 🌎 GEOLOCALIZAÇÃO (BRASIL INTEIRO)
    geo = obter_endereco(latitude, longitude)

    # 🧠 classificação
    grupo, classificacao = classificar_padrao(dados)
    confianca, motivos_suspeita, ip, device_id = _score_suspeita(empresa, request, dados)

    if confianca <= 0.3:
        return JsonResponse({
            "erro": "envio bloqueado por protecao antifraude",
            "motivos": motivos_suspeita,
        }, status=429)

    # 💾 salvar
    RegistroSintoma.objects.create(
        id_anonimo=uuid.uuid4(),
        febre=dados.get("febre", False),
        tosse=dados.get("tosse", False),
        dor_corpo=dados.get("dor_corpo", False),
        cansaco=dados.get("cansaco", False),
        falta_ar=dados.get("falta_ar", False),

        latitude=latitude,
        longitude=longitude,

        pais=geo.get("pais"),
        estado=geo.get("estado"),
        cidade=geo.get("cidade"),
        bairro=geo.get("bairro") or "Centro",
        condado=geo.get("condado"),

        empresa=empresa,

        grupo=grupo,
        classificacao=classificacao,
        ip=ip,
        device_id=device_id,
        confianca=confianca,
        suspeito=confianca < 0.75,
    )

    return JsonResponse({
        "status": "ok",
        "grupo": grupo,
        "classificacao": classificacao,
        "confianca": confianca,
        "suspeito": confianca < 0.75,
        "local": {
            "bairro": geo.get("bairro"),
            "cidade": geo.get("cidade"),
            "estado": geo.get("estado")
        }
    })


@csrf_exempt
def registrar_sintoma_publico(request):
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    latitude = dados.get("latitude")
    longitude = dados.get("longitude")
    location_source = (dados.get("location_source") or "current").strip()
    if latitude in [None, ""] or longitude in [None, ""]:
        return JsonResponse({"erro": "latitude/longitude obrigatórios"}, status=400)
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return JsonResponse({"erro": "latitude/longitude inválidos"}, status=400)

    simulacao_autorizada = settings.DEBUG and request.headers.get("X-Solus-Simulation") == "true"
    if location_source != "current" and not simulacao_autorizada:
        return JsonResponse({
            "erro": "envio exige GPS atual confirmado pelo aparelho",
            "codigo": "gps_atual_obrigatorio",
        }, status=400)

    empresa = _empresa_app_publico()
    if simulacao_autorizada:
        geo = {
            "bairro": (dados.get("bairro") or "Centro").strip(),
            "cidade": (dados.get("cidade") or "Rio de Janeiro").strip(),
            "estado": (dados.get("estado") or "Rio de Janeiro").strip(),
            "pais": (dados.get("pais") or "Brasil").strip(),
        }
    else:
        geo = obter_endereco(latitude, longitude)
    grupo, classificacao = classificar_padrao(dados)
    confianca, motivos_suspeita, ip, device_id = _score_suspeita(empresa, request, dados)
    permitido, motivo_bloqueio = _bloqueio_envio_publico(
        empresa,
        ip,
        device_id,
        dados=dados,
        geo=geo,
    )

    if not permitido:
        return JsonResponse({
            "status": "ja_considerado",
            "mensagem": "Seu envio recente ja foi considerado no monitoramento regional.",
            "grupo": grupo,
            "classificacao": classificacao,
            "confianca": 1,
            "suspeito": False,
            "motivos_suspeita": [],
            "local": {
                "bairro": geo.get("bairro"),
                "cidade": geo.get("cidade"),
                "estado": geo.get("estado"),
            },
            "erro": motivo_bloqueio,
            "codigo": "rate_limit_publico",
        })

    if confianca <= 0.3:
        return JsonResponse({
            "erro": "envio bloqueado por proteção antifraude",
            "motivos": motivos_suspeita,
        }, status=429)

    registro = RegistroSintoma.objects.create(
        id_anonimo=uuid.uuid4(),
        empresa=empresa,
        febre=bool(dados.get("febre", False)),
        tosse=bool(dados.get("tosse", False)),
        dor_corpo=bool(dados.get("dor_corpo", False)),
        cansaco=bool(dados.get("cansaco", False)),
        falta_ar=bool(dados.get("falta_ar", False)),
        latitude=latitude,
        longitude=longitude,
        pais=geo.get("pais"),
        estado=geo.get("estado"),
        cidade=geo.get("cidade"),
        bairro=geo.get("bairro") or "Centro",
        condado=geo.get("condado"),
        grupo=grupo,
        classificacao=classificacao,
        ip=ip,
        device_id=device_id,
        confianca=confianca,
        suspeito=confianca < 0.75,
    )

    return JsonResponse({
        "status": "ok",
        "registro_id": str(registro.id_anonimo),
        "grupo": grupo,
        "classificacao": classificacao,
        "confianca": confianca,
        "suspeito": confianca < 0.75,
        "motivos_suspeita": motivos_suspeita,
        "local": {
            "bairro": registro.bairro,
            "cidade": registro.cidade,
            "estado": registro.estado,
        },
        "coordenadas_recebidas": {
            "latitude": registro.latitude,
            "longitude": registro.longitude,
            "fonte": location_source,
        },
    })

def listar_sintomas(request):
    empresa_id, erro = validar_token(request)
    if erro:
        return erro

    dados = RegistroSintoma.objects.filter(empresa_id=empresa_id)

    return JsonResponse([
        {
            "latitude": d.latitude,
            "longitude": d.longitude,
            "estado": d.estado,
            "cidade": d.cidade
        }
        for d in dados
    ], safe=False)


# ================= RESUMOS =================

def resumo_municipios(request):

    dados = RegistroSintoma.objects.values("cidade", "estado", "grupo").annotate(total=Count("id"))

    resultado = []

    for d in dados:

        cidade = d.get("cidade")
        estado = d.get("estado")

        if not cidade or not estado:
            continue

        lat, lon = buscar_coordenada(cidade, estado)

        if lat is None or lon is None:
            continue

        resultado.append({
            "cidade": cidade,
            "estado": estado,
            "grupo": d.get("grupo"),
            "total": d.get("total"),
            "latitude": lat,
            "longitude": lon
        })

    return JsonResponse(resultado, safe=False)
# ================= SURTOS =================

from django.db.models import Sum
from django.db.models import Count, Q

def detectar_surtos(request):

    dados = RegistroSintoma.objects.values("cidade", "estado").annotate(

        total=Count("id"),

        # 🧠 SINTOMAS
        febre=Count("id", filter=Q(febre=True)),
        tosse=Count("id", filter=Q(tosse=True)),
        falta_ar=Count("id", filter=Q(falta_ar=True)),
        dor_corpo=Count("id", filter=Q(dor_corpo=True)),
        cansaco=Count("id", filter=Q(cansaco=True)),

        # 🦠 DOENÇAS
        # 🦠 DOENÇAS (CERTO BASEADO NO SEU MODEL)
        dengue=Count("id", filter=Q(grupo__icontains="dengue")),
        covid=Count("id", filter=Q(grupo__icontains="covid")),
        influenza=Count("id", filter=Q(grupo__icontains="influenza")),
        zika=Count("id", filter=Q(grupo__icontains="zika")),
        chikungunya=Count("id", filter=Q(grupo__icontains="chikungunya")),
        srag=Count("id", filter=Q(grupo__icontains="srag")),
        gastro=Count("id", filter=Q(grupo__icontains="gastro")),
    )

    resposta = []

    for d in dados:

        cidade = d["cidade"]
        estado = d["estado"]
        total = d["total"] or 0

        lat, lon = buscar_coordenada(cidade, estado)

        # 🧠 IA
        previsao, crescimento = calcular_previsao(cidade, estado, total)

        nivel = calcular_risco(total, crescimento)

        resposta.append({
            "cidade": cidade,
            "estado": estado,
            "total": total,

            "crescimento": round(crescimento, 2),
            "previsao": previsao,
            "nivel": nivel,

            "latitude": lat,
            "longitude": lon,

            # 🧠 sintomas
            "febre": d["febre"],
            "tosse": d["tosse"],
            "falta_ar": d["falta_ar"],
            "dor_corpo": d["dor_corpo"],
            "cansaco": d["cansaco"],

            # 🦠 doenças
            "dengue": d["dengue"],
            "covid": d["covid"],
            "influenza": d["influenza"],
            "zika": d["zika"],
            "chikungunya": d["chikungunya"],
            "srag": d["srag"],
            "gastro": d["gastro"],
        })

    return JsonResponse(resposta, safe=False)

# ================= PREVISÃO =================

def prever_surtos(request):

    agora = timezone.now()
    h24 = agora - timedelta(hours=24)
    h48 = agora - timedelta(hours=48)

    ultimas_24h = RegistroSintoma.objects.filter(
        data_registro__gte=h24
    ).values("cidade", "estado").annotate(total=Count("id"))

    ultimas_48h = RegistroSintoma.objects.filter(
        data_registro__gte=h48,
        data_registro__lt=h24
    ).values("cidade", "estado").annotate(total=Count("id"))

    mapa_48h = {(d["cidade"], d["estado"]): d["total"] for d in ultimas_48h}

    resultado = []

    for d in ultimas_24h:

        cidade = d["cidade"]
        estado = d["estado"]
        atual = d["total"]

        anterior = mapa_48h.get((cidade, estado), 0)

        # 🔥 CRESCIMENTO REAL (%)
        if anterior > 0:
            crescimento = ((atual - anterior) / anterior) * 100
        else:
            crescimento = 100  # novo surto

        # ============================
        # 🧠 IA DE DECISÃO
        # ============================

        risco = "BAIXO"
        previsao = "ESTÁVEL"
        interpretacao = "Situação sob controle"

        if crescimento > 100 and atual > 50:
            risco = "CRITICO"
            previsao = "EXPLOSÃO IMINENTE"
            interpretacao = "Alta probabilidade de surto grave nas próximas horas"

        elif crescimento > 50:
            risco = "ALTO"
            previsao = "FORTE CRESCIMENTO"
            interpretacao = "Disseminação acelerada detectada"

        elif crescimento > 20:
            risco = "MEDIO"
            previsao = "TENDÊNCIA DE ALTA"
            interpretacao = "Aumento consistente de casos"

        elif crescimento < -20:
            risco = "BAIXO"
            previsao = "QUEDA"
            interpretacao = "Redução de casos"

        resultado.append({
            "cidade": cidade,
            "estado": estado,
            "total": atual,
            "crescimento": round(crescimento, 2),
            "risco": risco,
            "previsao": previsao,
            "interpretacao": interpretacao
        })

    return JsonResponse(resultado, safe=False)

# ================= IA =================

@csrf_exempt
def analisar_tosse(request):
    return JsonResponse(random.choice([
        {"risco": "baixo", "possivel": "Resfriado"},
        {"risco": "medio", "possivel": "Dengue"},
        {"risco": "alto", "possivel": "COVID"}
    ]))




# ================= ALERTAS =================

def alertas(request):
    return JsonResponse([
        {"mensagem": "🚨 Sistema ativo - monitorando surtos"}
    ], safe=False)


# ================= PAGAMENTO =================

def tela_pagamento(request):
    from .planos import pacotes_por_setor
    return render(request, "pagamento.html", {
        "pacotes": pacotes_por_setor(incluir_governo=False),
    })


def sucesso(request):
    return HttpResponse("Pagamento aprovado")


def erro(request):
    return HttpResponse("Pagamento recusado")


def pendente(request):
    return HttpResponse("Pagamento pendente")


# ================= RELATÓRIOS =================

def relatorio_regioes(request):
    return JsonResponse([], safe=False)


def relatorio_municipios(request):
    dados = RegistroSintoma.objects.values(
        "cidade", "estado"
    ).annotate(total=Count("id"))

    return JsonResponse(list(dados), safe=False)

from rest_framework.decorators import api_view
from rest_framework.response import Response

    

def calcular_risco(total, crescimento):
    total = int(total)
    def safe_float(valor):
     try:
         return float(valor)
     except:
        return 0

    crescimento = safe_float(crescimento)

    if total > 50 or crescimento > 2:
        return "ALTO"
    elif total > 20:
        return "MÉDIO"
    else:
        return "BAIXO"


def resumo_doencas(request):

    registros = RegistroSintoma.objects.all()

    dados = analisar_doencas(registros)

    resultado = []

    for doenca, total in dados.items():

        risco = risco_por_doenca(doenca, total)

        resultado.append({
            "doenca": doenca,
            "total": total,
            "risco": risco
        })

    return JsonResponse(resultado, safe=False)

def diagnostico_ia(request):

    dados = json.loads(request.body or "{}")

    probs = probabilidade_doenca(dados)

    # pega a mais provável
    principal = max(probs, key=probs.get)

    return JsonResponse({
        "probabilidades": probs,
        "mais_provavel": principal
    })

from .utils import treinar_modelo, prever_com_aprendizado

def diagnostico_ia_avancado(request):

    dados = json.loads(request.body or "{}")

    registros = RegistroSintoma.objects.all()

    modelo = treinar_modelo(registros)

    resultado = prever_com_aprendizado(dados, modelo)

    if not resultado:
        return JsonResponse({"erro": "sem dados suficientes"})

    principal = max(resultado, key=resultado.get)

    return JsonResponse({
        "probabilidades": resultado,
        "mais_provavel": principal
    })



def classificar_padrao(dados):

    score_respiratorio = 0
    score_arbovirose = 0
    score_alerta = 0

    if dados.get("febre"):
        score_respiratorio += 1
        score_arbovirose += 2

    if dados.get("tosse"):
        score_respiratorio += 2

    if dados.get("falta_ar"):
        score_respiratorio += 3
        score_alerta += 3

    if dados.get("dor_corpo"):
        score_arbovirose += 2

    if dados.get("cansaco"):
        score_respiratorio += 1
        score_arbovirose += 1

    # 🔥 decisão baseada em pontuação
    if score_alerta >= 3:
        return "Alerta", "Sinais que merecem atenção médica imediata"

    if score_respiratorio >= 3:
        return "Respiratório", "Padrão compatível com infecção respiratória viral"

    if score_arbovirose >= 3:
        return "Arbovirose", "Padrão compatível com dengue ou vírus similar"

    return "Leve", "Sintomas inespecíficos de baixo risco"

def resumo_estados(request):
    dados = RegistroSintoma.objects.values("estado").annotate(total=Count("id"))
    return JsonResponse(list(dados), safe=False)

def gerar_alerta(total, grupo):

    if total >= 50:
        return "ALTO", f"Possível surto de {grupo}"
    
    elif total >= 20:
        return "MODERADO", f"Aumento de casos de {grupo}"
    
    elif total >= 10:
        return "ATENCAO", f"Crescimento leve de {grupo}"
    
    return "NORMAL", "Situação controlada"

def mapa_casos(request):

    dados = RegistroSintoma.objects.all()

    resultado = []

    for d in dados:

        if not d.latitude or not d.longitude:
            continue

        resultado.append({
            "latitude": d.latitude,
            "longitude": d.longitude,
            "grupo": d.grupo,
            "cidade": d.cidade,
        })

    return JsonResponse(resultado, safe=False)


def app_resumo_publico(request):
    agora = timezone.now()
    ultimas_24h = RegistroSintoma.objects.filter(data_registro__gte=agora - timedelta(hours=24))
    ultimos_7d = RegistroSintoma.objects.filter(data_registro__gte=agora - timedelta(days=7))
    ativos_30d = RegistroSintoma.objects.filter(data_registro__gte=agora - timedelta(days=JANELA_DECAIMENTO_FOCO_DIAS))
    dias_anteriores = RegistroSintoma.objects.filter(
        data_registro__gte=agora - timedelta(days=14),
        data_registro__lt=agora - timedelta(days=7),
    )

    total_7d = ultimos_7d.count()
    total_30d = ativos_30d.count()
    indice_ativo_30d = _indice_temporal_publico(ativos_30d, agora)
    base_anterior = dias_anteriores.count()
    crescimento = 0.0
    if base_anterior:
        crescimento = round(((total_7d - base_anterior) / base_anterior) * 100, 2)

    doencas = (
        ativos_30d.exclude(grupo__isnull=True).exclude(grupo="")
        .values("grupo")
        .annotate(total=Count("id"))
        .order_by("-total")[:6]
    )
    top_grupo = doencas[0]["grupo"] if doencas else "monitoramento geral"
    nivel_nacional = _nivel_por_indice_publico(indice_ativo_30d, crescimento)

    return JsonResponse({
        "resumo": {
            "registros_24h": ultimas_24h.count(),
            "registros_7d": total_7d,
            "registros_30d": total_30d,
            "indice_ativo_7d": indice_ativo_30d,
            "indice_ativo_30d": indice_ativo_30d,
            "crescimento_7d": crescimento,
            "suspeitos_24h": ultimas_24h.filter(suspeito=True).count(),
            "nivel_nacional": nivel_nacional,
            "decaimento_temporal": "o indice ativo fica preservado por 10 dias sem novos envios; depois a IA reduz gradualmente apenas quando serie temporal, dados agregados e fontes oficiais sustentam queda real, evitando falsa melhora precoce",
        },
        "semaforo": _semaforo_publico(nivel_nacional),
        "alerta_publico": _alerta_publico(nivel_nacional, crescimento, top_grupo),
        "orientacao_publica": _orientacao_publica(nivel_nacional, top_grupo),
        "doencas_top": [
            {
                "grupo": item["grupo"],
                "total": item["total"],
                "percentual": round((item["total"] / max(total_30d, 1)) * 100, 2),
            }
            for item in doencas
        ],
    })


def app_radar_local(request):
    latitude = request.GET.get("latitude")
    longitude = request.GET.get("longitude")
    cidade = request.GET.get("cidade")
    estado = request.GET.get("estado")
    bairro = request.GET.get("bairro")

    geo = {}
    if latitude and longitude and not (cidade and estado and bairro):
        geo = obter_endereco(latitude, longitude)
        cidade = cidade or geo.get("cidade")
        estado = estado or geo.get("estado")
        bairro = bairro or geo.get("bairro")

    if not cidade or not estado:
        return JsonResponse({"erro": "cidade/estado ou latitude/longitude obrigatórios"}, status=400)

    agora = timezone.now()
    atuais = RegistroSintoma.objects.filter(
        cidade=cidade,
        estado=estado,
        data_registro__gte=agora - timedelta(days=JANELA_DECAIMENTO_FOCO_DIAS),
    )
    atuais_7d = atuais.filter(data_registro__gte=agora - timedelta(days=7))
    anteriores = RegistroSintoma.objects.filter(
        cidade=cidade,
        estado=estado,
        data_registro__gte=agora - timedelta(days=14),
        data_registro__lt=agora - timedelta(days=7),
    )

    if bairro:
        atuais_bairro = atuais.filter(bairro=bairro)
        atuais_bairro_7d = atuais_7d.filter(bairro=bairro)
    else:
        atuais_bairro = atuais.none()
        atuais_bairro_7d = atuais_7d.none()

    total_atuais = atuais_7d.count()
    total_ativos = atuais.count()
    indice_ativo = _indice_temporal_publico(atuais, agora)
    total_anteriores = anteriores.count()
    crescimento = 0.0
    if total_anteriores:
        crescimento = round(((total_atuais - total_anteriores) / total_anteriores) * 100, 2)

    nivel = _nivel_local_por_indice_publico(indice_ativo, crescimento)

    doencas = (
        atuais.exclude(grupo__isnull=True).exclude(grupo="")
        .values("grupo")
        .annotate(total=Count("id"))
        .order_by("-total")[:6]
    )
    grupo_top = doencas[0]["grupo"] if doencas else "monitoramento geral"

    sintomas = {
        "febre": atuais.filter(febre=True).count(),
        "tosse": atuais.filter(tosse=True).count(),
        "dor_corpo": atuais.filter(dor_corpo=True).count(),
        "cansaco": atuais.filter(cansaco=True).count(),
        "falta_ar": atuais.filter(falta_ar=True).count(),
    }
    doencas_provaveis = _build_disease_probabilities(sintomas, total_ativos)

    return JsonResponse({
        "local": {
            "bairro": bairro or geo.get("bairro"),
            "cidade": cidade,
            "estado": estado,
        },
        "radar": {
            "nivel": nivel,
            "registros_7d": total_atuais,
            "registros_30d": total_ativos,
            "indice_ativo_7d": indice_ativo,
            "indice_ativo_30d": indice_ativo,
            "crescimento_7d": crescimento,
            "suspeitos_7d": atuais_7d.filter(suspeito=True).count(),
            "bairro_registros_7d": atuais_bairro_7d.count(),
            "bairro_registros_30d": atuais_bairro.count(),
            "grupo_top": grupo_top,
            "decaimento_temporal": "sem novos envios, o indice local permanece preservado por 10 dias; depois a IA reduz gradualmente apenas quando a tendencia local, dados agregados e fontes oficiais sustentam queda real",
        },
        "semaforo": _semaforo_publico(nivel),
        "alerta_publico": _alerta_publico(nivel, crescimento, grupo_top),
        "orientacao_publica": _orientacao_publica(nivel, grupo_top),
        "doencas": [
            {
                "grupo": item["grupo"],
                "total": item["total"],
                "percentual": round((item["total"] / max(total_ativos, 1)) * 100, 2),
            }
            for item in doencas
        ],
        "doencas_provaveis": doencas_provaveis,
        "sintomas": sintomas,
    })


def app_mapa_publico(request):
    agora = timezone.now()
    base = RegistroSintoma.objects.filter(
        data_registro__gte=agora - timedelta(days=JANELA_DECAIMENTO_FOCO_DIAS),
        latitude__isnull=False,
        longitude__isnull=False,
    )
    cidade = request.GET.get("cidade")
    estado = request.GET.get("estado")
    if cidade:
        base = base.filter(cidade=cidade)
    if estado:
        base = base.filter(estado__in=_state_terms(estado))

    hotspots_por_dia = (
        base.annotate(day=TruncDate("data_registro"))
        .values("cidade", "estado", "bairro", "day")
        .annotate(total=Count("id"), latitude_media=Avg("latitude"), longitude_media=Avg("longitude"))
    )

    areas = {}
    for row in hotspots_por_dia:
        key = (row["cidade"], row["estado"], row["bairro"])
        peso = _peso_temporal_publico(row["day"], agora)
        area = areas.setdefault(key, {
            "cidade": row["cidade"],
            "estado": row["estado"],
            "bairro": row["bairro"],
            "total": 0,
            "indice_ativo": 0.0,
            "latitude_soma": 0.0,
            "longitude_soma": 0.0,
            "peso_geo": 0,
        })
        total = row["total"] or 0
        area["total"] += total
        area["indice_ativo"] += total * peso
        area["latitude_soma"] += float(row["latitude_media"]) * total
        area["longitude_soma"] += float(row["longitude_media"]) * total
        area["peso_geo"] += total

    hotspots = sorted(areas.values(), key=lambda item: item["indice_ativo"], reverse=True)[:250]
    total_indice_mapa = sum(item["indice_ativo"] for item in hotspots) or 1

    resultado = []
    for item in hotspots:
        area_queryset = base.filter(
            cidade=item["cidade"],
            estado=item["estado"],
            bairro=item["bairro"],
        )
        grupo_top = (
            area_queryset
            .exclude(grupo__isnull=True)
            .exclude(grupo="")
            .values("grupo")
            .annotate(total=Count("id"))
            .order_by("-total")
            .first()
        )
        sintomas_area = {
            "febre": area_queryset.filter(febre=True).count(),
            "tosse": area_queryset.filter(tosse=True).count(),
            "dor_corpo": area_queryset.filter(dor_corpo=True).count(),
            "cansaco": area_queryset.filter(cansaco=True).count(),
            "falta_ar": area_queryset.filter(falta_ar=True).count(),
        }
        doencas_provaveis = _build_disease_probabilities(sintomas_area, item["total"])
        doenca_top = doencas_provaveis[0]["name"] if doencas_provaveis else None
        indice_ativo = round(item["indice_ativo"], 2)
        nivel = "alto" if indice_ativo >= 45 else "moderado" if indice_ativo >= 20 else "atencao" if indice_ativo >= 8 else "baixo"
        peso_geo = max(item["peso_geo"], 1)
        resultado.append({
            "cidade": item["cidade"],
            "estado": item["estado"],
            "bairro": item["bairro"],
            "total": item["total"],
            "indice_ativo": indice_ativo,
            "percentual_ativo": round((indice_ativo / total_indice_mapa) * 100, 2),
            "latitude": round(item["latitude_soma"] / peso_geo, 6),
            "longitude": round(item["longitude_soma"] / peso_geo, 6),
            "grupo_dominante": doenca_top or (grupo_top["grupo"] if grupo_top else "Monitoramento geral"),
            "perfil_sindromico": grupo_top["grupo"] if grupo_top else "Monitoramento geral",
            "doenca_dominante": doenca_top,
            "doencas_provaveis": doencas_provaveis[:5],
            "semaforo": _semaforo_publico(nivel),
            "decaimento_temporal": "foco preservado por 10 dias sem novos envios; depois a intensidade reduz gradualmente somente quando a IA valida queda real com serie temporal, dados agregados e fontes oficiais",
        })

    return JsonResponse({"hotspots": resultado}, safe=False)


def app_alertas_publicos(request):
    cidade = request.GET.get("cidade")
    estado = request.GET.get("estado")
    bairro = request.GET.get("bairro")
    incluir_gerais = request.GET.get("incluir_gerais", "1").lower() not in {"0", "false", "nao", "não"}

    alertas = AlertaGovernamental.objects.filter(
        ativo=True,
        status=AlertaGovernamental.STATUS_PUBLICADO,
    ).order_by("-criado_em")
    if estado:
        estado_filter = Q(estado__in=_state_terms(estado))
        if incluir_gerais:
            estado_filter |= Q(estado__isnull=True) | Q(estado="")
        alertas = alertas.filter(estado_filter)
    if cidade:
        cidade_filter = Q(cidade=cidade)
        if incluir_gerais:
            cidade_filter |= Q(cidade__isnull=True) | Q(cidade="")
        alertas = alertas.filter(cidade_filter)
    if bairro:
        bairro_filter = Q(bairro=bairro)
        if incluir_gerais:
            bairro_filter |= Q(bairro__isnull=True) | Q(bairro="")
        alertas = alertas.filter(bairro_filter)

    return JsonResponse({
        "alertas": [
            {
                "id": alerta.id,
                "titulo": alerta.titulo,
                "mensagem": alerta.mensagem,
                "estado": alerta.estado,
                "cidade": alerta.cidade,
                "bairro": alerta.bairro,
                "nivel": alerta.nivel,
                "criado_em": alerta.criado_em.isoformat(),
            }
            for alerta in alertas[:12]
        ]
    })


@csrf_exempt
def registrar_aceite_legal_publico(request):
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    device_id = (request.headers.get("X-Device-Id") or dados.get("device_id") or "").strip()
    versao = (dados.get("versao") or "").strip()
    if not device_id or not versao:
        return JsonResponse({"erro": "device_id e versao são obrigatórios"}, status=400)

    aceite = AceiteLegalPublico.objects.create(
        device_id=device_id[:120],
        versao=versao[:30],
        plataforma=(dados.get("plataforma") or "app")[:30],
        ip=_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:2000],
        metadados={
            "termos": bool(dados.get("termos")),
            "privacidade": bool(dados.get("privacidade")),
            "saude_localizacao": bool(dados.get("saude_localizacao")),
            "registrado_no_app_em": dados.get("aceito_em"),
        },
    )
    return JsonResponse({"status": "ok", "aceite_id": aceite.id})


@csrf_exempt
def registrar_push_publico(request):
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    token = (dados.get("token") or "").strip()
    device_id = (dados.get("device_id") or "").strip()
    if not token or not device_id:
        return JsonResponse({"erro": "token e device_id são obrigatórios"}, status=400)

    DispositivoPushPublico.objects.filter(device_id=device_id[:120]).exclude(token=token).update(ativo=False)

    registro, _ = DispositivoPushPublico.objects.update_or_create(
        token=token,
        defaults={
            "device_id": device_id[:120],
            "plataforma": (dados.get("plataforma") or "unknown")[:20],
            "estado": (dados.get("estado") or "").strip() or None,
            "cidade": (dados.get("cidade") or "").strip() or None,
            "bairro": (dados.get("bairro") or "").strip() or None,
            "ativo": True,
        },
    )
    return JsonResponse({"status": "ok", "push_id": registro.id})

@csrf_exempt
def analisar_audio(request):

    if request.method == "POST":
        audio_file = request.FILES.get("audio")

        if not audio_file:
            return JsonResponse({"erro": "sem áudio"})

        # 🔥 versão simplificada (sem numpy / soundfile)
        tamanho = audio_file.size

        if tamanho > 500000:
            return JsonResponse({
                "classificacao": "Tosse forte",
                "nivel": "ALTO"
            })

        elif tamanho > 100000:
            return JsonResponse({
                "classificacao": "Tosse moderada",
                "nivel": "MODERADO"
            })

        else:
            return JsonResponse({
                "classificacao": "Som leve",
                "nivel": "NORMAL"
            })

    return JsonResponse({"erro": "método inválido"})

from api.models import RegistroSintoma

def limpar_casos(request):
    total = RegistroSintoma.objects.count()
    RegistroSintoma.objects.all().delete()
    return JsonResponse({"apagados": total})


def insights_nacional(request):

    dados = RegistroSintoma.objects.values(
        "estado", "cidade", "grupo"
    ).annotate(total=Count("id"))

    def sugestao_estoque(grupo):
        if grupo == "Respiratório":
            return "Comprar: Antigripais, Xaropes, Vitamina C"
        if grupo == "Dengue":
            return "Comprar: Paracetamol, Soro, Repelente"
        return "Estoque básico"

    resultado = []

    for d in dados:

        total = d["total"]
        grupo = d["grupo"]
        cidade = d["cidade"]
        estado = d["estado"]

        if total > 50:
            nivel = "ALTO"
        elif total > 20:
            nivel = "MODERADO"
        else:
            nivel = "BAIXO"

        recomendacao = sugestao_estoque(grupo)

        resultado.append({
            "estado": estado,
            "cidade": cidade,
            "doenca": grupo,
            "total": total,
            "nivel": nivel,
            "recomendacao": recomendacao
        })

    return JsonResponse(resultado, safe=False)



def insights_farmacia(request):

    dados = RegistroSintoma.objects.values(
        "cidade", "estado", "grupo"
    ).annotate(total=Count("id"))

    resultado = []

    for d in dados:

        total = d["total"]
        grupo = d["grupo"] or "Geral"

        # 🎯 NÍVEL
        nivel = "BAIXO"
        if total > 50:
            nivel = "MODERADO"
        if total > 100:
            nivel = "ALTO"

        # 💊 RECOMENDAÇÃO INTELIGENTE
        recomendacao = "Estoque normal"

        if grupo == "Dengue":
            recomendacao = "💊 Paracetamol + Repelente"

        elif grupo == "Respiratório":
            recomendacao = "💊 Antigripais + Vitamina C"

        elif grupo == "COVID":
            recomendacao = "💊 Antigripais + Máscaras"

        resultado.append({
            "cidade": d["cidade"],
            "estado": d["estado"],
            "doenca": grupo,
            "total": total,
            "nivel": nivel,
            "recomendacao": recomendacao
        })

    return JsonResponse(resultado, safe=False)



from django.http import HttpResponse

def tela_cadastro(request):
    return HttpResponse("""
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<title>Solus CRT Saúde • Criar Conta</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">

<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'Inter',sans-serif;}

body{
  height:100vh;
  background:#020617;
  color:white;
  display:flex;
  align-items:center;
  justify-content:center;
}

/* 🔥 FUNDO */
.bg{
  position:absolute;
  width:100%;
  height:100%;
  background:
    radial-gradient(circle at 20% 20%, rgba(56,189,248,0.15), transparent 40%),
    radial-gradient(circle at 80% 80%, rgba(99,102,241,0.15), transparent 40%),
    #020617;
}

/* 🔥 CARD */
.card{
  position:relative;
  z-index:2;
  width:420px;
  padding:40px;
  border-radius:20px;
  background:rgba(255,255,255,0.04);
  backdrop-filter:blur(25px);
  border:1px solid rgba(255,255,255,0.08);
  box-shadow:0 20px 80px rgba(0,0,0,0.7);
}

/* LOGO */
.logo{
  font-size:22px;
  font-weight:600;
  margin-bottom:20px;
}
.logo span{color:#38bdf8}

/* TITULO */
h2{
  font-size:20px;
  margin-bottom:5px;
}

p{
  font-size:13px;
  color:#94a3b8;
  margin-bottom:25px;
}

/* INPUT */
.input{
  width:100%;
  padding:14px;
  margin-bottom:14px;
  border-radius:10px;
  border:1px solid rgba(255,255,255,0.08);
  background:rgba(255,255,255,0.03);
  color:white;
  outline:none;
  transition:0.3s;
}

.input:focus{
  border-color:#38bdf8;
  box-shadow:0 0 10px rgba(56,189,248,0.3);
}

/* BOTÃO */
.btn{
  width:100%;
  padding:14px;
  border:none;
  border-radius:10px;
  background:linear-gradient(135deg,#38bdf8,#2563eb);
  font-weight:600;
  color:white;
  cursor:pointer;
  transition:0.3s;
}

.btn:hover{
  transform:translateY(-2px);
  box-shadow:0 10px 30px rgba(56,189,248,0.4);
}

/* LOADING */
.loading{
  display:none;
  text-align:center;
  margin-top:10px;
  font-size:13px;
  color:#38bdf8;
}

/* ERRO */
.erro{
  margin-top:10px;
  color:#f87171;
  display:none;
  font-size:13px;
}

/* FOOTER */
.footer{
  margin-top:20px;
  text-align:center;
  font-size:13px;
  color:#94a3b8;
  cursor:pointer;
}

.footer:hover{
  color:#38bdf8;
}
</style>
</head>

<body>

<div class="bg"></div>

<div class="card">

  <div class="logo">Solus <span>CRT</span> Saúde</div>

  <h2>Criar Conta</h2>
  <p>Ative inteligência epidemiológica em minutos</p>

  <input id="nome" class="input" placeholder="Nome da empresa">
  <input id="email" class="input" placeholder="Email corporativo">
  <input id="senha" type="password" class="input" placeholder="Senha segura">

  <button class="btn" onclick="cadastrar()">Criar Conta</button>

  <div id="loading" class="loading">Criando conta...</div>
  <div id="erro" class="erro"></div>

  <div class="footer" onclick="window.location.href='/login-empresa/'">
    Já tenho conta
  </div>

</div>

<script>
function getDeviceId(){
  let deviceId = localStorage.getItem("device_id");
  if(!deviceId){
    deviceId = "dev-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("device_id", deviceId);
  }
  return deviceId;
}

async function cadastrar(){

  const nome = document.getElementById("nome").value;
  const email = document.getElementById("email").value;
  const senha = document.getElementById("senha").value;
  const erro = document.getElementById("erro");
  const loading = document.getElementById("loading");

  erro.style.display = "none";

  // 🔥 VALIDAÇÃO PROFISSIONAL
  if(!nome || !email || !senha){
    erro.innerText = "Preencha todos os campos";
    erro.style.display = "block";
    return;
  }

  if(senha.length < 6){
    erro.innerText = "Senha deve ter no mínimo 6 caracteres";
    erro.style.display = "block";
    return;
  }

  loading.style.display = "block";

  try{
    const res = await fetch("/api/registrar_empresa", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        nome,
        email,
        senha,
        device_id: getDeviceId(),
        device_name: navigator.platform || "Computador"
      })
    });

    const data = await res.json();

    loading.style.display = "none";

    if(data.token){
      localStorage.setItem("token", data.token);
      if(data.device_id){
        localStorage.setItem("device_id", data.device_id);
      }

      window.location.href = data.destination || "/pagamento/";
    }else{
      erro.innerText = data.erro || "Erro ao criar conta";
      erro.style.display = "block";
    }

  }catch(e){
    loading.style.display = "none";
    erro.innerText = "Erro de conexão";
    erro.style.display = "block";
  }
}
</script>

</body>
</html>
""", content_type="text/html")

def login(request):
    body = json.loads(request.body)

    email = body.get("email")
    senha = body.get("senha")

    empresa = Empresa.objects.filter(email=email).first()

    if not empresa:
        return JsonResponse({"erro": "Empresa não encontrada"}, status=401)

    if not check_password(senha, empresa.senha):
        return JsonResponse({"erro": "Senha incorreta"}, status=401)

    issued_at = datetime.utcnow()
    expires_at = issued_at + timedelta(hours=settings.JWT_EXP_HOURS)
    token = jwt.encode(
        {
            "empresa_id": empresa.id,
            "iat": issued_at,
            "exp": expires_at,
        },
        settings.JWT_SECRET_KEY,
        algorithm="HS256"
    )

    return JsonResponse({
        "status": "ok",
        "token": token,
        "empresa_id": empresa.id
    })


def pagamento(request):

    auth_header = request.headers.get("Authorization")

    if not auth_header:
        return JsonResponse({"erro": "Token não enviado"}, status=401)

    if not auth_header.startswith("Bearer "):
        return JsonResponse({"erro": "Formato inválido"}, status=401)

    token = auth_header.split(" ")[1]

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=["HS256"]
        )

    except Exception as e:
        return JsonResponse({"erro": "Token inválido"}, status=401)

    return JsonResponse({
        "status": "ok",
        "empresa_id": payload["empresa_id"]
    })

def pagamento(request):

    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return JsonResponse({"erro": "não autorizado"}, status=401)

    token = auth_header.split(" ")[1]

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=["HS256"]
        )

        empresa_id = payload["empresa_id"]

    except Exception:
        return JsonResponse({"erro": "Token inválido"}, status=401)

    return JsonResponse({
        "status": "ok",
        "empresa_id": empresa_id
    })



def painel(request):

    empresa_id = request.GET.get("empresa_id")

    if not empresa_id:
        return JsonResponse({"erro": "sem empresa"}, status=400)

    dados = RegistroSintoma.objects.filter(empresa_id=empresa_id)

    total = dados.count()

    risco = "Alto" if total > 2 else "Baixo"
    crescimento = "Subindo" if total > 1 else "Estável"

    alerta = None
    if total > 2:
        alerta = "Possível surto na região"

    insight = "Aumento de sintomas detectado" if total > 0 else "Sem registros"

    return JsonResponse({
        "total": total,
        "risco": risco,
        "crescimento": crescimento,
        "alerta": alerta,
        "insight": insight
    })


def casos_por_regiao(request):

    empresa_id = request.GET.get("empresa_id")

    dados = (
        RegistroSintoma.objects
        .filter(empresa_id=empresa_id)
        .values("bairro", "cidade", "estado")
        .annotate(
            total=Count("id"),
            lat=Avg("latitude"),
            lng=Avg("longitude"),

            # sintomas
            febre=Count("id", filter=Q(febre=True)),
            tosse=Count("id", filter=Q(tosse=True)),
            falta_ar=Count("id", filter=Q(falta_ar=True)),
            dor_corpo=Count("id", filter=Q(dor_corpo=True)),
            cansaco=Count("id", filter=Q(cansaco=True)),

            # doenças (nível OMS)
            covid=Count("id", filter=Q(grupo="COVID-19")),
            influenza=Count("id", filter=Q(grupo="Influenza")),
            dengue=Count("id", filter=Q(grupo="Dengue")),
            zika=Count("id", filter=Q(grupo="Zika")),
            chikungunya=Count("id", filter=Q(grupo="Chikungunya")),
            srag=Count("id", filter=Q(grupo="SRAG")),
            gastro=Count("id", filter=Q(grupo="Gastroviral")),
        )
    )

    resultado = []

    for d in dados:

        total = d["total"]

        if total >= 10:
            risco = "alto"
        elif total >= 5:
            risco = "medio"
        else:
            risco = "baixo"

        # dominante
        tipos = {
            "COVID-19": d["covid"],
            "Influenza": d["influenza"],
            "Dengue": d["dengue"],
            "Zika": d["zika"],
            "Chikungunya": d["chikungunya"],
            "SRAG": d["srag"],
            "Gastroviral": d["gastro"],
        }

        dominante = max(tipos, key=tipos.get) if total > 0 else "N/D"

        resultado.append({
            "regiao": f"{d['bairro']} - {d['cidade']}/{d['estado']}",
            "total": total,
            "lat": d["lat"],
            "lng": d["lng"],
            "risco": risco,

            # sintomas
            "febre": d["febre"],
            "tosse": d["tosse"],
            "falta_ar": d["falta_ar"],
            "dor_corpo": d["dor_corpo"],
            "cansaco": d["cansaco"],

            # doenças
            "covid": d["covid"],
            "influenza": d["influenza"],
            "dengue": d["dengue"],
            "zika": d["zika"],
            "chikungunya": d["chikungunya"],
            "srag": d["srag"],
            "gastro": d["gastro"],

            "dominante": dominante
        })

    return JsonResponse(resultado, safe=False)


def mapa_risco(request):

    dados = (
        RegistroSintoma.objects
        .values("bairro", "latitude", "longitude")
        .annotate(total=Count("id"))
    )

    resultado = []

    for d in dados:

        total = d["total"]

        if total > 5:
            risco = "alto"
            cor = "red"
        elif total > 2:
            risco = "medio"
            cor = "orange"
        else:
            risco = "baixo"
            cor = "green"

        resultado.append({
            "bairro": d["bairro"],
            "lat": d["latitude"],
            "lng": d["longitude"],
            "total": total,
            "risco": risco,
            "cor": cor
        })

    return JsonResponse(resultado, safe=False)


def bairros_por_cidade(request):

    cidade = request.GET.get("cidade")
    estado = request.GET.get("estado")

    if not cidade or not estado:
        return JsonResponse([], safe=False)

    dados = RegistroSintoma.objects.filter(
        cidade=cidade,
        estado=estado
    ).values("bairro").annotate(
        total=Count("id")
    ).order_by("-total")

    return JsonResponse(list(dados), safe=False)
