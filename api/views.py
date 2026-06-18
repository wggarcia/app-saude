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
from api.classificador_doencas import classificar_para_cidadao as _classificar_cidadao
from api.utils_geo import obter_endereco
from api.utils_auth import validar_token
from api.models import Empresa, RegistroSintoma
from api.epidemiologia import (
    SYMPTOM_LABELS,
    _build_disease_probabilities,
    build_panorama_payload,
    clear_panorama_cache,
)
from api.services.public_integrity import (
    alerta_governamental_sintetico,
    q_registro_sintoma_sintetico,
)
from django.db.models import Count, Avg, Q
from django.db.models.functions import TruncDate
from django.contrib.auth.hashers import check_password, make_password
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta

# ============================
# 🧠 IA GLOBAL (MOVER PRA CIMA)
# ============================

historico = defaultdict(list)


SITE_LANGUAGE_META = {
    "pt": {"label": "PT", "flag": "🇧🇷", "name": "Português", "html": "pt-BR"},
    "en": {"label": "EN", "flag": "🇺🇸", "name": "English", "html": "en"},
    "es": {"label": "ES", "flag": "🇪🇸", "name": "Español", "html": "es"},
}


SITE_TRANSLATIONS = {
    "pt": {
        "title": "SolusCRT Saude | monitoramento epidemiologico com IA em ambientes isolados",
        "description": "Monitoramento epidemiologico com IA para antecipar risco, apoiar decisao e gerar assinatura em cinco ambientes isolados, protegidos e vendidos separadamente.",
        "brand": "SolusCRT Saúde",
        "nav": {
            "diferencial": "Por que assinam",
            "ecossistema": "Ambientes",
            "valores": "Confianca",
            "app": "Apps",
            "contato": "Contato",
        },
        "nav_note": "Radar epidemiologico e IA no topo. Cinco ambientes privados, isolados e protegidos.",
        "language_aria": "Selecionar idioma",
        "hero_eyebrow": "Monitoramento epidemiologico em tempo real. IA para antecipar o pico.",
        "hero_title": "Monitoramento epidemiologico com IA que antecipa decisao.",
        "hero_title_desktop_lines": ["Monitoramento", "epidemiologico", "com IA que", "antecipa decisao."],
        "hero_title_lines": ["Monitoramento", "epidemiologico", "com IA que", "antecipa decisao."],
        "hero_lead": "O SolusCRT cruza sinais da populacao, fontes oficiais e IA para mostrar onde o risco cresce primeiro e onde agir antes do pico. Governo, Farmacia, Hospital, SST e Plano de Saude nao compartilham a mesma base: cada um recebe seu proprio ambiente isolado, protegido e vendido ao seu proprio cliente.",
        "actions": {
            "presentation": "Ver apresentacao comercial",
            "app": "Conhecer os apps",
            "sales": "Falar com comercial",
            "open_presentation": "Abrir apresentacao comercial",
            "meeting": "Agendar conversa comercial",
            "login": "Entrar",
            "signup": "Criar conta gratis",
        },
        "proofs": [
            {"title": "Sinais da populacao", "text": "Captura colaborativa sem registro nominal para enxergar tendencia antes da confirmacao oficial."},
            {"title": "Fontes oficiais", "text": "IBGE, InfoDengue, InfoGripe e DATASUS com lastro para leitura territorial."},
            {"title": "IA preditiva", "text": "Classifica sinais, cruza variaveis e destaca risco antes do pico ganhar forca."},
            {"title": "Mapa territorial", "text": "Mostra onde agir primeiro com leitura executiva e contexto local."},
            {"title": "5 ambientes", "text": "Governo, Farmacia, Hospital, SST e Plano de Saude entram como ambientes isolados e independentes."},
        ],
        "chips": ["Monitoramento", "IA", "Territorio", "Governo", "Farmacia", "Hospital"],
        "metrics": [
            {"value": "Sinais + fontes + IA", "text": "O motor cruza entrada colaborativa, fonte oficial e inferencia para antecipar risco"},
            {"value": "5 ambientes", "text": "Governo, Farmacia, Hospital, SST e Plano de Saude viram ambientes isolados, independentes e protegidos"},
            {"value": "2 apps distintos", "text": "App da populacao para territorio e app do funcionario para SST"},
            {"value": "LGPD por arquitetura", "text": "Segregacao, auditoria e controle de acesso tratados como parte central da confianca"},
        ],
        "differential": {
            "title": "A IA da SolusCRT transforma sinais dispersos em decisao antes do pico.",
            "lead": "A forca do produto esta em ler milhares de sinais fracos, cruzar territorio, sintomas, fontes brasileiras e comportamento temporal para mostrar onde agir primeiro. Os cinco segmentos entram depois como ambientes isolados onde essa inteligencia vira receita, sem mistura de dados ou acesso compartilhado.",
            "traditional_title": "Vigilancia tradicional",
            "traditional_items": [
                "Depende de notificacao, consolidacao e publicacao, o que costuma atrasar a leitura do risco.",
                "Entrega historico e confirmacao, mas chega tarde para compras, escala, comunicacao e resposta local.",
                "Sem IA e sem cruzamento territorial, o comprador nao enxerga a janela de acao com a mesma clareza.",
            ],
            "solus_title": "Capa SolusCRT com IA",
            "solus_items": [
                "Recebe sinais sem cadastro nominal pela populacao, com localizacao atual e controle antifraude.",
                "Identifica crescimento, predominancia de sintomas e risco territorial antes da confirmacao oficial.",
                "Entrega a decisao para o ambiente certo: governo, farmacia, hospital, SST ou plano de saude.",
            ],
        },
        "ecosystem_title": "Cinco ambientes isolados para a mesma inteligencia epidemiologica.",
        "ecosystem_lead": "O visitante entende primeiro o motor: monitoramento epidemiologico com IA. Depois, reconhece o proprio ambiente isolado, o proprio contrato e a propria privacidade: Governo, Farmacia, Hospital, SST e Plano de Saude.",
        "slides": [
            {"small": "Governo", "title": "Ambiente isolado com IA", "text": "Leitura territorial para comunicar, priorizar e agir antes do pico com governanca institucional e acesso restrito."},
            {"small": "Farmacia", "title": "Ambiente isolado de demanda", "text": "Radar territorial para compra, estoque e ruptura antes de a falta de produto bater no caixa."},
            {"small": "Hospital", "title": "Ambiente isolado de pressao", "text": "Capacidade, triagem e equipes organizadas a partir da tendencia epidemiologica."},
            {"small": "SST", "title": "Ambiente isolado ocupacional", "text": "ASO, CAT, eSocial e bem-estar com leitura preventiva e contexto proprio."},
            {"small": "Plano de Saude", "title": "Ambiente isolado de operadora", "text": "Beneficiarios, autorizacoes, sinistros e reembolsos com radar territorial integrado."},
        ],
        "platform": {
            "title_html": "Uma IA epidemiologica.<br>Cinco ambientes isolados prontos para assinar.",
            "lead": "Cada ambiente isolado recebe uma IA feita para o proprio contexto, o proprio risco e o proprio momento de agir. Depois disso, cada ambiente entra por assinatura, trial, proposta comercial ou contrato institucional, sem compartilhamento de base entre clientes.",
            "cards": [
                {
                    "title": "SST & Clinicas Ocupacionais",
                    "badge": "Assinatura recorrente",
                    "text": "Aplique a IA epidemiologica para dar contexto ao SST em um ambiente isolado, reduzir atrito e vender conformidade com valor claro.",
                    "price": "R$ 799",
                    "caption": "/mes · assinatura recorrente com trial",
                    "cta": "Comecar com teste",
                },
                {
                    "title": "Farmacia & Rede Farmaceutica",
                    "badge": "Operacao por loja ou rede",
                    "text": "Um ambiente isolado para antecipar demanda, proteger margem e fazer a farmacia se preparar antes da ruptura com radar epidemiologico.",
                    "price": "R$ 859",
                    "caption": "/mes · por loja ou operacao",
                    "cta": "Solicitar demonstracao",
                },
                {
                    "title": "Hospital & Rede Assistencial",
                    "badge": "Estrutura ou rede",
                    "text": "Um ambiente isolado para proteger capacidade assistencial, organizar fluxo e preparar equipe antes da pressao com leitura territorial.",
                    "price": "R$ 7.250",
                    "caption": "/mes · por estrutura ou rede",
                    "cta": "Solicitar proposta",
                },
                {
                    "title": "Governo & Vigilancia Publica",
                    "badge": "Contrato institucional",
                    "text": "Escolha a SolusCRT Saude para integrar vigilancia territorial, IA, e-SUS/RNDS, faturamento SUS, auditoria e governanca LGPD em um ambiente publico isolado e confiavel.",
                    "price": "Sob proposta",
                    "caption": "licitacao e proposta tecnica institucional",
                    "cta": "Falar com especialista",
                },
                {
                    "title": "Operadora de Plano de Saude",
                    "badge": "Operadora especializada",
                    "text": "Gestao completa para operadoras em ambiente isolado: beneficiarios, contratos, guias de autorizacao, sinistros, reembolsos e dashboard epidemiologico com mapa de calor territorial.",
                    "price": "R$ 36.250",
                    "caption": "/mes · anual R$ 435.000 · por operadora",
                    "cta": "Solicitar proposta",
                },
            ],
        },
        "enterprise": {
            "eyebrow": "Ambientes isolados e assinatura",
            "title": "Cinco segmentos, um motor de monitoramento epidemiologico com IA.",
            "lead": "A plataforma nao existe para empurrar o mesmo argumento para todo mundo. Ela foi organizada para que cada cliente reconheca o seu proprio caso de uso, o seu tipo de compra e a sua melhor porta de entrada, sempre a partir do monitoramento epidemiologico e da IA. Cada segmento opera em ambiente isolado, com privacidade e dados segregados.",
            "items": [
                {"title": "Governo", "text": "Sala de situacao, alertas, auditoria e leitura territorial em ambiente isolado para uniao, estados e municipios."},
                {"title": "Farmacia", "text": "Previsibilidade de demanda, compras, lotes e ruptura em ambiente isolado para loja, rede ou distribuidor."},
                {"title": "Hospital", "text": "Leitos, triagem, equipes e capacidade assistencial em ambiente isolado antes da pressao chegar ao pronto atendimento."},
                {"title": "SST", "text": "ASO, CAT, eSocial, exames, PGR, bem-estar anonimo e app do trabalhador em ambiente isolado e recorrente."},
                {"title": "Plano de Saude", "text": "Beneficiarios, contratos, guias, sinistros, reembolsos e radar territorial em ambiente isolado para operacao especializada."},
            ],
            "metrics": [
                {"value": "IA + territorio", "text": "o motor cruza sinais, fontes oficiais e comportamento temporal"},
                {"value": "5 ambientes", "text": "cada decisor entra no proprio caso de uso em ambiente isolado e protegido"},
                {"value": "15 dias gratis", "text": "Entrada rapida para experimentar valor real antes da assinatura"},
            ],
        },
        "matrix": [
            {"label": "Governo", "title": "Autoridade territorial", "text": "Paineis para gestores federais, estaduais e municipais com radar territorial, fontes oficiais, comunicacao e auditoria institucional."},
            {"label": "Farmacia", "title": "Previsibilidade de demanda", "text": "Antecipacao de demanda, giro, ruptura e insumos com gestao farmaceutica conectada ao risco regional."},
            {"label": "Hospital", "title": "Preparo assistencial", "text": "Preparacao de leitos, triagem, equipes e pressao assistencial com visibilidade de surtos antes do pico chegar ao pronto-socorro."},
            {"label": "SST", "title": "Operacao ocupacional", "text": "ASO, CAT, afastamentos, NR, EPI/EPC, PGR, eSocial SST, app do funcionario e bem-estar anonimo em ambiente proprio, sem dado epidemiologico."},
            {"label": "Plano de Saude", "title": "Gestao especializada de operadora", "text": "Beneficiarios, contratos, guias, sinistros, reembolsos e leitura territorial no mesmo ambiente para operadoras."},
            {"label": "Privacidade", "title": "Confianca por segregacao", "text": "Cada ambiente tem login, permissao, dados e auditoria proprios. Governo, farmacia, hospital, SST e plano de saude nao compartilham base operacional entre si."},
        ],
        "values": {
            "eyebrow": "Confiança SolusCRT",
            "title": "Confiança para assinar, implantar e renovar.",
            "lead": "A SolusCRT nasceu de uma pergunta que incomodava: por que a informação de saúde sempre chega tarde? Tarde para o gestor agir, tarde para o hospital se preparar, tarde para o trabalhador ser amparado. Cada decisão de produto, privacidade e governança começa daqui — do compromisso de que tecnologia de saúde existe para chegar a tempo e proteger vidas reais.",
            "items": [
                {"title": "Vida em primeiro lugar", "text": "Todo indicador, alerta e mapa existe para reduzir atraso, orientar cuidado e apoiar decisões que preservem pessoas."},
                {"title": "Verdade antes de impacto", "text": "Separar sinal precoce, dado oficial e inferência de IA é um compromisso para evitar conclusões falsas."},
                {"title": "Privacidade como fundamento", "text": "Dados de saúde exigem minimização, segurança, transparência e exibição adequada ao perfil autorizado. Cada ambiente tem sua própria segregação."},
                {"title": "Cooperação institucional", "text": "O sistema foi pensado para unir população, empresas, hospitais, farmácias e governo sem confundir responsabilidades nem misturar dados."},
                {"title": "Acesso social", "text": "O app da população deve ser gratuito, simples e útil, porque vigilância inteligente começa quando todos podem contribuir."},
                {"title": "Coragem operacional", "text": "A SolusCRT existe para antecipar problemas difíceis, mostrar territórios críticos e ajudar líderes a agir antes do pico."},
            ],
        },
        "app": {
            "eyebrow": "Dois apps, dois contextos",
            "title": "App da populacao para territorio. App do funcionario para SST.",
            "lead": "O app gratuito coleta sintomas sem cadastro nominal, mostra radar local e recebe alertas oficiais para alimentar a inteligencia territorial. O outro pertence ao ambiente SST isolado: libera ASO digital, notificacoes, solicitacoes e check-ins de bem-estar anonimos.",
            "app_store": "Baixar na App Store",
            "google_play": "Ver no Google Play",
            "note": "O app do funcionario e ativado por contrato dentro do ambiente SST. O app listado nas lojas e o app da populacao.",
            "risks": [
                {"title": "App da populacao", "text": "Sintomas anonimos, radar local e alertas oficiais."},
                {"title": "App do funcionario", "text": "ASO, notificacoes e bem-estar no fluxo SST."},
                {"title": "Leitura territorial", "text": "Focos e sintomas por regiao com localizacao atual."},
                {"title": "Privacidade por contexto", "text": "Dois apps, duas promessas e duas governancas distintas."},
            ],
        },
        "cta": {
            "title": "Quando o monitoramento mostra o risco primeiro, a compra avanca mais rapido.",
            "lead": "Se o seu cliente quer IA epidemiologica para governo, farmacia, hospital, SST ou operadora, o SolusCRT ja chega com narrativa, produto e governanca coerentes. Os cinco ambientes entram como formas de monetizar essa inteligencia, sempre de forma isolada e protegida.",
        },
        "footer": "SolusCRT Saude. Monitoramento epidemiologico com IA em ambientes privados, isolados e protegidos.",
        "footer_links": {
            "privacy": "Privacidade",
            "terms": "Termos",
            "security": "Segurança",
            "methodology": "Metodologia",
            "support": "Suporte",
        },
    },
    "en": {
        "title": "SolusCRT Health | 5 environments for Government, Pharmacy, Hospital, OSH and Health Plan",
        "description": "Five private environments for Government, Pharmacy, Hospital, OSH and Health Plan, with distinct apps, territorial AI and a commercial structure ready for subscription, proposal or institutional contract.",
        "brand": "SolusCRT Health",
        "nav": {
            "diferencial": "Why it sells",
            "ecossistema": "Environments",
            "valores": "Trust",
            "app": "Apps",
            "contato": "Contact",
        },
        "nav_note": "Five private environments. One brand ready for contracts and recurring revenue.",
        "language_aria": "Select language",
        "hero_eyebrow": "Five private environments. One sales architecture for every health decision-maker.",
        "hero_title": "Five private environments for every health decision-maker.",
        "hero_title_desktop_lines": ["Five private", "environments for", "every health", "decision-maker."],
        "hero_title_lines": ["Five private", "environments for", "every health", "decision-maker."],
        "hero_lead": "SolusCRT Health does not force every buyer into the same generic dashboard. It presents five independent commercial environments: Government, Pharmacy, Hospital, OSH and Health Plan. Each one has its own language, workflow, privacy and offer. The first impression feels mature, credible and ready to sign.",
        "actions": {
            "presentation": "View commercial presentation",
            "app": "Explore the apps",
            "sales": "Talk to sales",
            "open_presentation": "Open commercial presentation",
            "meeting": "Book a sales conversation",
            "login": "Sign in",
            "signup": "Create free account",
        },
        "proofs": [
            {"title": "Government", "text": "Situation room, alerts and territorial authority for institutional B2G contracts."},
            {"title": "Pharmacy", "text": "Demand anticipation, safer purchasing and fewer shortages for retail or networks."},
            {"title": "Hospital", "text": "Beds, triage, teams and care capacity prepared before the peak."},
            {"title": "OSH", "text": "Recurring subscription with employee app, wellness and compliance in its own workflow."},
            {"title": "Health Plan", "text": "Operator management with beneficiaries, claims, reimbursements and territorial radar in one place."},
        ],
        "chips": ["Government", "Pharmacy", "Hospital", "OSH", "Health Plan", "Population app"],
        "metrics": [
            {"value": "5 environments", "text": "Each segment enters a commercial experience that feels built for its own routine"},
            {"value": "2 distinct apps", "text": "Population app for territorial intelligence and employee app for the OSH environment"},
            {"value": "AI + time series", "text": "More time to communicate, buy, scale teams or protect capacity before the peak"},
            {"value": "LGPD by architecture", "text": "Segregation, audit trail and access control treated as a core trust layer"},
        ],
        "differential": {
            "title": "SolusCRT AI turns scattered signals into decisions before the peak.",
            "lead": "It does not try to replace official surveillance or medical diagnosis. Its strength is reading thousands of weak signals, crossing territory, growth, symptoms, Brazilian sources and time behavior to show where to act first — and delivering that view to the right environment: government, pharmacy, hospital or company.",
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
                "Delivers the view to the right environment: situation room for government, demand for pharmacy, capacity for hospital.",
            ],
        },
        "ecosystem_title": "Five environments commercialized like real products.",
        "ecosystem_lead": "The buyer should not have to translate the platform. They should recognize their sector, workflow, privacy boundaries and buying model on the first screen. Government, Pharmacy, Hospital, OSH and Health Plan all appear with their own language and offer.",
        "slides": [
            {"small": "Government", "title": "Epidemiological situation room", "text": "Dedicated environment for federal, state and municipal managers with official alerts, IBGE, InfoDengue, InfoGripe, DATASUS, audit trail and decision matrix."},
            {"small": "Pharmacy", "title": "Pharmaceutical management with radar", "text": "Inventory control, FEFO, lots, suppliers and future demand for medicines and supplies with territorial risk visibility."},
            {"small": "Hospital", "title": "Hospital management with anticipation", "text": "Beds, triage, admissions, teams and care pressure organized before the epidemiological peak hits the front door."},
            {"small": "OSH", "title": "Independent occupational management", "text": "Medical certificates, incident reports, leave, exams, NR, PPE/EPC, PGR, eSocial OSH, employee app and anonymous wellness in an environment without epidemiological data."},
            {"small": "Health Plan", "title": "Complete health operator management", "text": "Beneficiaries, contracts, authorization guides, claims, reimbursements and epidemiological heatmap dashboard for health insurance operators."},
        ],
        "enterprise": {
            "eyebrow": "OSH Environment — Companies and Occupational Clinics",
            "title": "Complete OSH management, team wellness and employee app in one dashboard.",
            "lead": "SolusCRT's OSH environment is focused on pure organizational management: companies of any size and occupational health clinics that need legal compliance, employee engagement and real visibility of team wellness — without epidemiology, without external data, with full privacy.",
            "items": [
                {"title": "Complete OSH and eSocial", "text": "Digital medical certificates, incident reports, leave management, exams, NR training, PPE/EPC, S-2240 workstation profiles, hazards and PGR, documents and compliance. eSocial OSH integration with real-time status dashboard."},
                {"title": "Anonymous Team Wellness", "text": "Anonymous check-ins on mood, physical health, mental health, stress and job satisfaction. The company sees aggregated trends. Employee names only appear if they voluntarily request support contact."},
                {"title": "Employee App", "text": "Employees access their own medical certificate digitally, make requests, receive exam and training notifications and submit wellness check-ins. More autonomy, less paper, more real engagement."},
            ],
            "metrics": [
                {"value": "37 NRs", "text": "technical compliance reference for occupational health and safety"},
                {"value": "eSocial OSH", "text": "integration with S-2220, S-2240, S-2210 and OSH events with compliance dashboard"},
                {"value": "15-day free trial", "text": "full access without credit card for the OSH and Companies environment"},
            ],
        },
        "matrix": [
            {"label": "Government", "title": "Situation room", "text": "Dashboards for federal, state and municipal managers with territorial radar, official sources, communication and institutional audit trail."},
            {"label": "Pharmacy", "title": "Demand radar", "text": "Anticipating demand, turnover, shortage and supplies with pharmaceutical management tied to regional risk."},
            {"label": "Hospital", "title": "Care management", "text": "Preparing beds, triage, teams and care pressure with outbreak visibility before the peak reaches the emergency department."},
            {"label": "OSH", "title": "Occupational management", "text": "Medical certificates, incident reports, leave, NR training, PPE/EPC, PGR, eSocial OSH, employee app and anonymous team wellness in its own environment, without epidemiological data."},
            {"label": "Health Plan", "title": "Operator management", "text": "Beneficiaries, contracts, authorization guides, claims, reimbursements and territorial intelligence in one dedicated environment."},
            {"label": "Privacy", "title": "Segment segregation", "text": "Each environment has its own login, permissions, data and audit trail. Government, pharmacy, hospital, OSH and health plan do not share the same operational base."},
        ],
        "values": {
            "eyebrow": "SolusCRT Values",
            "title": "Technology to protect people, not just sell software.",
            "lead": "SolusCRT was born with a clear responsibility: turn data into care, anticipate risks without empty alarm and help companies, governments, pharmacies and hospitals act with more awareness, speed and humanity.",
            "items": [
                {"title": "Life first", "text": "Every indicator, alert and map exists to reduce delay, guide care and support decisions that preserve people."},
                {"title": "Truth before impact", "text": "Separating early signal, official data and AI inference is a commitment to avoid false conclusions."},
                {"title": "Privacy as foundation", "text": "Health data requires minimization, security, transparency and display appropriate to each authorized profile. Each environment has its own segregation."},
                {"title": "Institutional cooperation", "text": "The system was designed to connect people, companies, hospitals, pharmacies and government without blurring responsibilities or mixing data."},
                {"title": "Social access", "text": "The population app should be free, simple and useful, because intelligent surveillance begins when everyone can contribute."},
                {"title": "Operational courage", "text": "SolusCRT exists to anticipate hard problems, reveal critical territories and help leaders act before the peak."},
            ],
        },
        "app": {
            "eyebrow": "Two apps, two contexts",
            "title": "Population app for territory. Employee app for OSH.",
            "lead": "One free app collects symptoms without nominal registration, shows local radar and receives official alerts for government, pharmacy, hospital and health plan territorial intelligence. The other belongs to the OSH environment: digital medical certificates, notifications, requests and anonymous wellness check-ins.",
            "app_store": "Download on the App Store",
            "google_play": "View on Google Play",
            "note": "The employee app is activated by contract inside the OSH environment. The app listed in stores is the population app.",
            "risks": [
                {"title": "Population app", "text": "Anonymous symptoms, local radar and official alerts."},
                {"title": "Employee app", "text": "Medical certificate, notifications and wellness inside OSH."},
                {"title": "Territorial reading", "text": "Hotspots and symptoms by region with current location."},
                {"title": "Privacy by context", "text": "Two apps, two promises and two separate governance layers."},
            ],
        },
        "cta": {
            "title": "When each environment speaks the right language, the buying decision moves faster.",
            "lead": "If your buyer is government, pharmacy, hospital, OSH or a health plan operator, SolusCRT already arrives with coherent narrative, product and governance. The commercial deck shows how each front supports the right subscription or contract model.",
        },
        "platform": {
            "title_html": "One platform.<br>Five entry points that make sense.",
            "lead": "Each buyer lands in an environment that respects their language, workflow and decision rhythm. The result is a more mature conversation from the very first contact.",
            "cards": [
                {
                    "title": "OSH & Occupational Clinics",
                    "badge": "Recurring subscription",
                    "text": "A subscription that organizes routines, values employees and reduces operational friction without mixing OSH with epidemiology.",
                    "price": "R$ 799",
                    "caption": "/month · recurring plan with trial",
                    "cta": "Start free trial",
                },
                {
                    "title": "Pharmacy & Retail Networks",
                    "badge": "Store or network operation",
                    "text": "An environment built to anticipate demand, protect margins and help pharmacy operations prepare before shortages hit.",
                    "price": "R$ 859",
                    "caption": "/month · per store or operation",
                    "cta": "Request demo",
                },
                {
                    "title": "Hospital & Care Networks",
                    "badge": "Facility or network",
                    "text": "A platform to protect care capacity, organize flow and prepare teams before pressure reaches the frontline.",
                    "price": "R$ 7,250",
                    "caption": "/month · per facility or network",
                    "cta": "Request proposal",
                },
                {
                    "title": "Government & Public Surveillance",
                    "badge": "Institutional contract",
                    "text": "Choose SolusCRT Health to unify territorial surveillance, e-SUS/RNDS, SUS billing, audit trails and LGPD governance in one trusted public-health platform.",
                    "price": "Custom proposal",
                    "caption": "public procurement and technical proposal",
                    "cta": "Talk to a specialist",
                },
                {
                    "title": "Health Insurance Operator",
                    "badge": "Specialized operator environment",
                    "text": "Complete management for health plan operators: beneficiaries, contracts, authorization guides, claims, reimbursements and epidemiological heatmap. 100 users and 100 authorized devices.",
                    "price": "R$ 36,250",
                    "caption": "/month · annual R$ 435,000 · per operator",
                    "cta": "Request proposal",
                },
            ],
        },
        "footer": "SolusCRT Health. Five private environments for Government, Pharmacy, Hospital, OSH, Health Plan and two apps with distinct roles.",
        "footer_links": {
            "privacy": "Privacy",
            "terms": "Terms",
            "security": "Security",
            "methodology": "Methodology",
            "support": "Support",
        },
    },
    "es": {
        "title": "SolusCRT Salud | 5 ambientes para Gobierno, Farmacia, Hospital, SST y Plan de Salud",
        "description": "Cinco ambientes privados para Gobierno, Farmacia, Hospital, SST y Plan de Salud, con apps distintos, IA territorial y una estructura comercial lista para suscripcion, propuesta o contrato institucional.",
        "brand": "SolusCRT Salud",
        "nav": {
            "diferencial": "Por que vende",
            "ecossistema": "Ambientes",
            "valores": "Confianza",
            "app": "Apps",
            "contato": "Contacto",
        },
        "nav_note": "Cinco ambientes privados. Una marca lista para contratos y recurrencia.",
        "language_aria": "Seleccionar idioma",
        "hero_eyebrow": "Cinco ambientes privados. Una arquitectura comercial para cada decisor en salud.",
        "hero_title": "Cinco ambientes privados para cada decisor en salud.",
        "hero_title_desktop_lines": ["Cinco ambientes", "privados para", "cada decisor", "en salud."],
        "hero_title_lines": ["Cinco ambientes", "privados para", "cada decisor", "en salud."],
        "hero_lead": "SolusCRT Salud no obliga a todos a entrar en el mismo panel generico. Presenta cinco ambientes comerciales independientes: Gobierno, Farmacia, Hospital, SST y Plan de Salud. Cada uno tiene su propio lenguaje, flujo, privacidad y oferta. La primera impresion se siente madura, creible y lista para firma.",
        "actions": {
            "presentation": "Ver presentacion comercial",
            "app": "Conocer las apps",
            "sales": "Hablar con ventas",
            "open_presentation": "Abrir presentacion comercial",
            "meeting": "Agendar conversacion comercial",
            "login": "Ingresar",
            "signup": "Crear cuenta gratis",
        },
        "proofs": [
            {"title": "Gobierno", "text": "Sala de situacion, alertas y autoridad territorial para contratos institucionales B2G."},
            {"title": "Farmacia", "text": "Anticipacion de demanda, compra mas segura y menos quiebres para tiendas o redes."},
            {"title": "Hospital", "text": "Camas, triaje, equipos y capacidad asistencial preparados antes del pico."},
            {"title": "SST", "text": "Suscripcion recurrente con app del trabajador, bienestar y conformidad en su propio flujo."},
            {"title": "Plan de Salud", "text": "Gestion de operadora con beneficiarios, siniestros, reembolsos y radar territorial en un solo lugar."},
        ],
        "chips": ["Gobierno", "Farmacia", "Hospital", "SST", "Plan de Salud", "App poblacional"],
        "metrics": [
            {"value": "5 ambientes", "text": "Cada segmento entra en una experiencia comercial que parece hecha para su propia rutina"},
            {"value": "2 apps distintos", "text": "App poblacional para inteligencia territorial y app del trabajador para el ambiente SST"},
            {"value": "IA + serie temporal", "text": "Mas tiempo para comunicar, comprar, escalar equipos o proteger capacidad antes del pico"},
            {"value": "LGPD por arquitectura", "text": "Segregacion, auditoria y control de acceso tratados como capa central de confianza"},
        ],
        "differential": {
            "title": "La IA de SolusCRT transforma senales dispersas en decision antes del pico.",
            "lead": "No intenta sustituir vigilancia oficial ni diagnostico medico. Su fuerza esta en leer miles de senales debiles, cruzar territorio, crecimiento, sintomas, fuentes brasilenas y comportamiento temporal para mostrar donde actuar primero — y entregar esa vision al ambiente correcto: gobierno, farmacia, hospital o empresa.",
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
                "Entrega la vision al ambiente correcto: sala de situacion para gobierno, demanda para farmacia, capacidad para hospital.",
            ],
        },
        "ecosystem_title": "Cinco ambientes comercializados como productos reales.",
        "ecosystem_lead": "El comprador no deberia traducir la plataforma. Deberia reconocer su sector, su flujo, sus fronteras de privacidad y su modelo de compra desde la primera pantalla. Gobierno, Farmacia, Hospital, SST y Plan de Salud aparecen con lenguaje y oferta propios.",
        "slides": [
            {"small": "Gobierno", "title": "Sala de situacion epidemiologica", "text": "Ambiente dedicado para gestores federales, estaduales y municipales con alertas oficiales, IBGE, InfoDengue, InfoGripe, DATASUS, auditoria y matriz de decision."},
            {"small": "Farmacia", "title": "Gestion farmaceutica con radar", "text": "Control de inventario, FEFO, lotes, proveedores y demanda futura de medicamentos e insumos con lectura territorial de riesgo."},
            {"small": "Hospital", "title": "Gestion hospitalaria con anticipacion", "text": "Camas, triaje, internaciones, equipos y presion asistencial organizados antes de que el pico epidemiologico presione la puerta de entrada."},
            {"small": "SST", "title": "Gestion ocupacional independiente", "text": "Certificados medicos, accidentes, ausencias, examenes, NR, EPI/EPC, PGR, eSocial SST, app del trabajador y bienestar anonimo en un ambiente sin datos epidemiologicos."},
            {"small": "Plan de Salud", "title": "Gestion completa de operadora", "text": "Beneficiarios, contratos, guias de autorizacion, siniestros, reembolsos y dashboard epidemiologico con mapa de calor territorial para operadoras de plan de salud."},
        ],
        "enterprise": {
            "eyebrow": "Ambiente SST — Empresas y Clinicas Ocupacionales",
            "title": "Gestion SST completa, bienestar del equipo y app del trabajador en un panel.",
            "lead": "El ambiente SST de SolusCRT esta orientado a la gestion organizacional pura: empresas de cualquier tamano y clinicas de salud ocupacional que necesitan conformidad legal, compromiso del trabajador y visibilidad real del bienestar del equipo — sin epidemiologia, sin datos externos, con total privacidad.",
            "items": [
                {"title": "SST completo y eSocial", "text": "Certificados medicos digitales, registros de accidente, ausencias, examenes, capacitaciones NR, EPI/EPC, puestos S-2240, riesgos y PGR, documentos y conformidad. Integracion eSocial SST con panel de estado en tiempo real."},
                {"title": "Bienestar Anonimo del Equipo", "text": "Check-ins anonimos de humor, salud fisica, salud mental, estres y satisfaccion laboral. La empresa ve tendencias agregadas. El nombre del trabajador solo aparece si voluntariamente solicita contacto de apoyo."},
                {"title": "App del Trabajador", "text": "El trabajador accede a su certificado medico digitalmente, realiza solicitudes, recibe notificaciones de examenes y capacitaciones y envia check-ins de bienestar. Mas autonomia, menos papel, mas compromiso real."},
            ],
            "metrics": [
                {"value": "37 NRs", "text": "consulta tecnica de conformidad para seguridad y salud en el trabajo"},
                {"value": "eSocial SST", "text": "integracion con S-2220, S-2240, S-2210 y eventos SST con panel de conformidad"},
                {"value": "15 dias gratis", "text": "prueba completa sin tarjeta de credito para el ambiente SST y Empresas"},
            ],
        },
        "matrix": [
            {"label": "Gobierno", "title": "Sala de situacion", "text": "Paneles para gestores federales, estaduales y municipales con radar territorial, fuentes oficiales, comunicacion y auditoria institucional."},
            {"label": "Farmacia", "title": "Radar de demanda", "text": "Anticipacion de demanda, rotacion, quiebre y suministros con gestion farmaceutica conectada al riesgo regional."},
            {"label": "Hospital", "title": "Gestion asistencial", "text": "Preparacion de camas, triaje, equipos y presion asistencial con visibilidad de brotes antes de que el pico llegue a urgencias."},
            {"label": "SST", "title": "Gestion ocupacional", "text": "Certificados, accidentes, ausencias, NR, EPI/EPC, PGR, eSocial SST, app del trabajador y bienestar anonimo del equipo en ambiente propio, sin dato epidemiologico."},
            {"label": "Plan de Salud", "title": "Gestion de operadora", "text": "Beneficiarios, contratos, guias de autorizacion, siniestros, reembolsos e inteligencia territorial en un ambiente dedicado."},
            {"label": "Privacidad", "title": "Segregacion por segmento", "text": "Cada ambiente tiene login, permisos, datos y auditoria propios. Gobierno, farmacia, hospital, SST y plan de salud no comparten la misma base operativa."},
        ],
        "values": {
            "eyebrow": "Valores SolusCRT",
            "title": "Tecnologia para proteger personas, no solo vender software.",
            "lead": "SolusCRT nace con una responsabilidad clara: transformar datos en cuidado, anticipar riesgos sin alarma vacia y ayudar a empresas, gobiernos, farmacias y hospitales a actuar con mas conciencia, velocidad y humanidad.",
            "items": [
                {"title": "Vida en primer lugar", "text": "Todo indicador, alerta y mapa existe para reducir retraso, orientar cuidado y apoyar decisiones que preserven personas."},
                {"title": "Verdad antes que impacto", "text": "Separar senal temprana, dato oficial e inferencia de IA es un compromiso para evitar conclusiones falsas."},
                {"title": "Privacidad como fundamento", "text": "Los datos de salud exigen minimizacion, seguridad, transparencia y exhibicion adecuada al perfil autorizado. Cada ambiente tiene su propia segregacion."},
                {"title": "Cooperacion institucional", "text": "El sistema fue pensado para unir poblacion, empresas, hospitales, farmacias y gobierno sin confundir responsabilidades ni mezclar datos."},
                {"title": "Acceso social", "text": "La app poblacional debe ser gratuita, simple y util, porque la vigilancia inteligente comienza cuando todos pueden contribuir."},
                {"title": "Coraje operacional", "text": "SolusCRT existe para anticipar problemas dificiles, mostrar territorios criticos y ayudar a lideres a actuar antes del pico."},
            ],
        },
        "app": {
            "eyebrow": "Dos apps, dos contextos",
            "title": "App poblacional para territorio. App del trabajador para SST.",
            "lead": "Una app gratuita recoge sintomas sin registro nominal, muestra radar local y recibe alertas oficiales para alimentar la inteligencia territorial de gobierno, farmacia, hospital y plan de salud. La otra pertenece al ambiente SST: certificados medicos digitales, notificaciones, solicitudes y check-ins anonimos de bienestar.",
            "app_store": "Descargar en App Store",
            "google_play": "Ver en Google Play",
            "note": "La app del trabajador se activa por contrato dentro del ambiente SST. La app publicada en las tiendas es la app poblacional.",
            "risks": [
                {"title": "App poblacional", "text": "Sintomas anonimos, radar local y alertas oficiales."},
                {"title": "App del trabajador", "text": "Certificado medico, notificaciones y bienestar dentro del SST."},
                {"title": "Lectura territorial", "text": "Focos y sintomas por region con ubicacion actual."},
                {"title": "Privacidad por contexto", "text": "Dos apps, dos promesas y dos capas separadas de gobernanza."},
            ],
        },
        "cta": {
            "title": "Cuando cada ambiente habla el idioma correcto, la decision de compra avanza mas rapido.",
            "lead": "Si su comprador es gobierno, farmacia, hospital, SST o una operadora, SolusCRT ya llega con narrativa, producto y gobernanza coherentes. La presentacion comercial muestra como cada frente sostiene el modelo correcto de suscripcion o contrato.",
        },
        "platform": {
            "title_html": "Una plataforma.<br>Cinco puertas de entrada con sentido.",
            "lead": "Cada cliente llega a un ambiente que respeta su lenguaje, su operacion y su ritmo de decision. El resultado es una conversacion mas madura desde el primer contacto.",
            "cards": [
                {
                    "title": "SST y Clinicas Ocupacionales",
                    "badge": "Suscripcion recurrente",
                    "text": "Una suscripcion que organiza rutinas, valora al trabajador y reduce friccion operativa sin mezclar SST con epidemiologia.",
                    "price": "R$ 799",
                    "caption": "/mes · suscripcion recurrente con prueba",
                    "cta": "Comenzar prueba",
                },
                {
                    "title": "Farmacia y Redes Farmaceuticas",
                    "badge": "Operacion por tienda o red",
                    "text": "Un ambiente pensado para anticipar demanda, proteger margen y preparar la operacion antes del quiebre.",
                    "price": "R$ 859",
                    "caption": "/mes · por tienda u operacion",
                    "cta": "Solicitar demo",
                },
                {
                    "title": "Hospital y Red Asistencial",
                    "badge": "Estructura o red",
                    "text": "Una plataforma para proteger capacidad asistencial, ordenar flujo y preparar equipos antes de la presion.",
                    "price": "R$ 7.250",
                    "caption": "/mes · por estructura o red",
                    "cta": "Solicitar propuesta",
                },
                {
                    "title": "Gobierno y Vigilancia Publica",
                    "badge": "Contrato institucional",
                    "text": "Elija SolusCRT Salud para unificar vigilancia territorial, e-SUS/RNDS, facturacion SUS, auditoria y gobernanza LGPD en una plataforma publica confiable.",
                    "price": "Bajo propuesta",
                    "caption": "licitacion y propuesta tecnica institucional",
                    "cta": "Hablar con especialista",
                },
                {
                    "title": "Operadora de Plan de Salud",
                    "badge": "Ambiente especializado",
                    "text": "Gestion completa para operadoras: beneficiarios, contratos, guias de autorizacion, siniestros, reembolsos y dashboard epidemiologico con mapa de calor. 100 usuarios y 100 maquinas autorizadas.",
                    "price": "R$ 36.250",
                    "caption": "/mes · anual R$ 435.000 · por operadora",
                    "cta": "Solicitar propuesta",
                },
            ],
        },
        "footer": "SolusCRT Salud. Cinco ambientes privados para Gobierno, Farmacia, Hospital, SST, Plan de Salud y dos apps con funciones distintas.",
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
        "brand": "SolusCRT Saúde",
        "site": "Site",
        "contact": "Contato",
        "language_aria": "Selecionar idioma",
        "footer_note": "Use o scroll para avançar pelos slides.",
        "vision": {
            "eyebrow": "Visão",
            "title": "Monitoramento epidemiologico com IA que antecipa o pico.",
            "body": "O SolusCRT cruza sinais da populacao, fontes oficiais e inferencia de IA para mostrar onde o risco cresce primeiro e onde agir antes da curva subir. Governo, Farmacia, Hospital, SST e Plano de Saude entram depois como os cinco mercados que compram essa inteligencia e a transformam em assinatura ou contrato.",
            "labels": {"resp": "Sinais", "deng": "IA", "covid": "Risco"},
        },
        "problem": {
            "eyebrow": "Problema",
            "title": "Quando o monitoramento chega tarde, cada segmento perde tempo, margem, capacidade ou confianca.",
            "cards": [
                {"title": "Governo governa no retrovisor", "text": "Secretarias e gestores dependem de fontes dispersas, planilhas e leitura tardia para decidir alerta, comunicacao e resposta territorial."},
                {"title": "Farmacia compra depois da ruptura", "text": "Sem radar epidemiologico territorial, a demanda por medicamentos e insumos aparece primeiro no caixa ou na falta de estoque."},
                {"title": "Hospital sente o pico dentro da porta", "text": "Sem antecipacao assistencial, leitos, triagem, escala e suprimentos reagem apenas quando a pressao ja chegou ao pronto atendimento."},
                {"title": "SST precisa gestao propria", "text": "ASO, CAT, eSocial SST, exames, PGR, app do funcionario e bem-estar anonimo exigem fluxo ocupacional proprio, sem depender nem se misturar ao radar epidemiologico."},
            ],
        },
        "solution": {
            "eyebrow": "Solução",
            "title": "A IA transforma sinais dispersos em decisao antes do pico.",
            "body": "O SolusCRT separa contratos, acessos, indicadores e experiencia por segmento. Governo, farmacia e hospital usam inteligencia epidemiologica territorial com a linguagem do seu setor. SST opera como ambiente independente de gestao ocupacional, com assinatura propria, trial de 15 dias e app do funcionario.",
            "cards": [
                {"title": "Governo", "text": "Sala de situacao, alertas, auditoria, matriz de decisao e leitura territorial para uniao, estados e municipios."},
                {"title": "Farmacia", "text": "Estoque, FEFO, lotes, compras e previsao de demanda ligados ao risco epidemiologico regional."},
                {"title": "Hospital", "text": "Leitos, triagem, internacoes, equipes e pressao assistencial com antecipacao do pico."},
                {"title": "SST", "text": "ASO, CAT, exames, NRs, eSocial, bem-estar anonimo e app do funcionario sem dado epidemiologico no ambiente."},
            ],
        },
        "ecosystem": {
            "eyebrow": "Ecossistema",
            "title": "Uma plataforma. Cinco mercados para IA especializada por segmento.",
            "cards": [
                {"title": "Governo", "text": "Uma sala de situacao epidemiologica feita para autoridade publica, leitura territorial e resposta institucional."},
                {"title": "Farmacia", "text": "Gestao farmaceutica, FEFO, lotes, ruptura, compras e inteligencia territorial para antecipar demanda."},
                {"title": "Hospital", "text": "Gestao de leitos, atendimento, triagem, internacao, pressao assistencial e equipes conectadas ao radar epidemiologico."},
                {"title": "SST e Empresas", "text": "SST completo, bem-estar anonimo, app do funcionario e integracao eSocial SST em uma experiencia pronta para assinatura."},
                {"title": "Plano de Saude", "text": "Gestao completa para operadoras: beneficiarios, contratos, guias, sinistros, reembolsos e mapa de calor territorial."},
            ],
        },
        "differential": {
            "eyebrow": "Diferencial",
            "title": "A IA da SolusCRT transforma sinais dispersos em decisao antes do pico.",
            "body": "O SolusCRT cruza milhares de sinais fracos, territorio, sintomas, fontes brasileiras e comportamento temporal para mostrar onde agir primeiro. Governo, Farmacia, Hospital, SST e Plano de Saude entram depois como mercados que monetizam essa inteligencia.",
            "quote": "Sinais viram risco. Risco vira decisao. Decisao vira contrato.",
        },
        "governance": {
            "eyebrow": "Governança",
            "title": "Privacidade, segurança e segregação por segmento fazem parte do produto.",
            "cards": [
                {"title": "Ambientes isolados", "text": "Governo, farmácia, hospital, SST e plano de saúde possuem acessos, sessões, trilhas e escopos próprios. O que nasce em um ambiente não aparece em outro."},
                {"title": "Epidemiologia territorial", "text": "O app da população gera sinais anônimos e territoriais para governo, farmácia e hospital, com antifraude, localização atual e separação entre sinal, fonte oficial e inferência."},
                {"title": "SST e bem-estar protegidos", "text": "ASO, CAT, exames, afastamentos e eSocial são dados sensíveis. Check-ins de bem-estar são anônimos por arquitetura e o nome só aparece mediante iniciativa do funcionário."},
                {"title": "Apps e auditoria", "text": "App da população e app do funcionário cumprem papéis distintos, com tokens, dispositivos autorizados, notificações e revogação por contrato."},
            ],
        },
        "values": {
            "eyebrow": "Valores",
            "title": "Valores que fazem a tecnologia merecer confiança",
            "body": "O SolusCRT foi pensado para cooperar com pessoas e instituições: proteger vidas, antecipar riscos, respeitar privacidade, comunicar com responsabilidade e ajudar líderes a agir sem distorcer a verdade.",
            "cards": [
                {"title": "Vida primeiro", "text": "SST, bem-estar e IA existem para reduzir dano real a pessoas reais."},
                {"title": "Verdade antes de impacto", "text": "Sinal precoce, dado oficial e IA sempre separados e identificados."},
                {"title": "Privacidade e anonimato", "text": "Bem-estar anônimo por design. Dados SST com minimização e LGPD."},
                {"title": "Cooperação", "text": "Empresa, funcionário, governo e população atuando na mesma rede de cuidado."},
            ],
        },
        "app": {
            "eyebrow": "Dois apps integrados",
            "title": "App da populacao e app do funcionario: cada um no lugar certo.",
            "body": "O app da populacao envia sintomas anonimos, recebe alertas e alimenta governo, farmacia e hospital com inteligencia territorial. O app do funcionario pertence ao ambiente SST: libera ASO digital, notificacoes, solicitacoes e check-ins de bem-estar anonimos. Dois apps. Dois contextos. Uma governanca clara.",
            "quote": "App da populacao para epidemiologia territorial. App do funcionario para SST organizacional.",
        },
        "closing": {
            "eyebrow": "Fechamento",
            "title": "Uma apresentacao que faz cada decisor se reconhecer no produto.",
            "body": "Na demonstracao, cada segmento encontra a sua propria resposta: governo enxerga governanca e leitura territorial; farmacia percebe previsibilidade e margem; hospital percebe preparo antes da pressao; SST percebe organizacao, cuidado com a equipe e adesao mais facil. O resultado e uma conversa madura, segura e pronta para evoluir em assinatura ou contrato.",
            "meeting": "Solicitar demonstracao comercial",
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
            "title": "One health platform with five private environments.",
            "body": "SolusCRT Health was designed as a sector ecosystem: Government with an epidemiological situation room for federal, state and municipal use; Pharmacy with management and demand radar; Hospital with care management and pressure anticipation; OSH with occupational compliance, an employee app and anonymous wellness; and Health Plan operators with complete beneficiary, claims and reimbursement management. The population app feeds epidemiological intelligence for government, pharmacy and hospital without mixing data with OSH or health plan.",
            "labels": {"resp": "Respiratory", "deng": "Arbovirus", "covid": "Viral"},
        },
        "problem": {
            "eyebrow": "Problem",
            "title": "Every segment loses time, money or capacity when everything is forced into one generic system.",
            "cards": [
                {"title": "Government governs in the rear-view mirror", "text": "Secretariats and public managers depend on scattered sources, spreadsheets and delayed reading to decide alerts, communication and territorial response."},
                {"title": "Pharmacy buys after the shortage", "text": "Without territorial epidemiological radar, medicine and supply demand appears first at the counter or in stock rupture."},
                {"title": "Hospital feels the peak at the door", "text": "Without care anticipation, beds, triage, staffing and supplies only react when pressure has already arrived at the frontline."},
                {"title": "OSH needs its own workflow", "text": "Medical certificates, incident reports, eSocial OSH, exams, PGR, employee app and anonymous wellness require their own occupational flow, without depending on or mixing with the epidemiological radar."},
            ],
        },
        "solution": {
            "eyebrow": "Solution",
            "title": "An architecture that delivers the right operation with the right privacy.",
            "body": "SolusCRT separates contracts, logins, indicators and operations by segment. Government, pharmacy and hospital use territorial epidemiological intelligence in the language of their own sector. OSH runs as an independent occupational management environment, with its own subscription, 15-day trial and employee app.",
            "cards": [
                {"title": "Government", "text": "Situation room, alerts, audit trail, decision matrix and territorial reading for federal, state and municipal managers."},
                {"title": "Pharmacy", "text": "Inventory, FEFO, lots, purchasing and demand forecasting tied to regional epidemiological risk."},
                {"title": "Hospital", "text": "Beds, triage, admissions, teams and care pressure with peak anticipation."},
                {"title": "OSH", "text": "Medical certificates, incident reports, exams, NRs, eSocial, anonymous wellness and employee app without epidemiological data inside the environment."},
            ],
        },
        "ecosystem": {
            "eyebrow": "Ecosystem",
            "title": "One platform. Five specialized environments.",
            "cards": [
                {"title": "Government", "text": "Epidemiological situation room, official alerts, decision matrix, audit trail, annual contracts and official Brazilian sources for federal, state and municipal use."},
                {"title": "Pharmacy", "text": "Pharmaceutical management, FEFO, lots, shortage, purchasing and epidemiological integration to anticipate demand by store or network."},
                {"title": "Hospital", "text": "Bed management, care, triage, admissions, care pressure and teams connected to the epidemiological radar."},
                {"title": "OSH and Companies", "text": "Complete OSH, anonymous wellness, employee app, workforce dashboard, absenteeism KPIs and eSocial OSH integration. Free 15-day trial."},
                {"title": "Health Plan Operator", "text": "Complete management for health operators: beneficiaries, contracts, authorization guides, claims, reimbursements and epidemiological heatmap dashboard. 100 users and 100 authorized devices."},
            ],
        },
        "differential": {
            "eyebrow": "Differentiator",
            "title": "This is not one product forced on everyone. It is an ecosystem built for five coordinated paths.",
            "body": "SolusCRT respects the logic of each segment: institutional contract and governance for government; expansion by store or network for pharmacy; care capacity for hospital; recurring subscription, fast implementation and proof of value for OSH and occupational clinics; specialized beneficiary, claims and reimbursement management for health plan operators.",
            "quote": "Government buys territorial intelligence. Pharmacy buys future demand. Hospital buys care readiness. OSH buys compliance, app and engagement. Health Plan buys operator management with epidemiology.",
        },
        "governance": {
            "eyebrow": "Governance",
            "title": "Privacy, security and segregation by segment are part of the product.",
            "cards": [
                {"title": "Isolated environments", "text": "Government, pharmacy, hospital, OSH and health plan have their own access, sessions, trails and scopes. What is born in one environment does not appear in another."},
                {"title": "Territorial epidemiology", "text": "The population app generates anonymous territorial signals for government, pharmacy and hospital, with anti-fraud, current location and separation between signal, official source and inference."},
                {"title": "Protected OSH and wellness", "text": "Medical certificates, incident reports, exams, leave and eSocial are sensitive data. Wellness check-ins are anonymous by architecture and the name only appears when the employee initiates support."},
                {"title": "Apps and audit trail", "text": "The population app and the employee app serve distinct roles, with tokens, authorized devices, notifications and contract-based revocation."},
            ],
        },
        "values": {
            "eyebrow": "Values",
            "title": "Values that make technology worthy of trust.",
            "body": "SolusCRT was designed to cooperate with people and institutions: protect lives, anticipate risks, respect privacy, communicate responsibly and help leaders act without distorting the truth.",
            "cards": [
                {"title": "Life first", "text": "OSH, wellness and AI exist to reduce real harm to real people."},
                {"title": "Truth before impact", "text": "Early signal, official data and AI always separated and identified."},
                {"title": "Privacy and anonymity", "text": "Wellness anonymous by design. OSH data with minimization and LGPD compliance."},
                {"title": "Cooperation", "text": "Company, employee, government and population acting in the same care network."},
            ],
        },
        "app": {
            "eyebrow": "Two integrated apps",
            "title": "Population app and employee app: each in the right place.",
            "body": "The population app submits anonymous symptoms, receives alerts and feeds government, pharmacy and hospital with territorial intelligence. The employee app belongs to the OSH environment: it unlocks digital medical certificates, notifications, requests and anonymous wellness check-ins. Two apps. Two contexts. One clear governance model.",
            "quote": "Population app for territorial epidemiology. Employee app for organizational OSH.",
        },
        "closing": {
            "eyebrow": "Closing",
            "title": "A strong market story. A clear product for subscription and contract.",
            "body": "In the demo, each buyer sees their own value: government with institutional contract and situation room; pharmacy and hospital with expansion by unit or network; OSH with recurring subscription, 15-day trial and fast implementation. SolusCRT grows without mixing operations, privacy or institutional purpose.",
            "meeting": "Request a sales demo",
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
            "title": "Una plataforma de salud con cinco ambientes privados.",
            "body": "SolusCRT Salud fue disenado como un ecosistema sectorial: Gobierno con sala de situacion epidemiologica para nivel federal, estadual y municipal; Farmacia con gestion y radar de demanda; Hospital con gestion asistencial y anticipacion de presion; SST con conformidad ocupacional, app del trabajador y bienestar anonimo; y Plan de Salud con gestion completa de beneficiarios, siniestros, reembolsos y dashboard epidemiologico. La app poblacional alimenta la inteligencia de los tres primeros sin mezclar datos con SST ni plan de salud.",
            "labels": {"resp": "Respiratorio", "deng": "Arbovirosis", "covid": "Viral"},
        },
        "problem": {
            "eyebrow": "Problema",
            "title": "Cada segmento pierde tiempo, dinero o capacidad cuando todo se fuerza dentro de un sistema generico.",
            "cards": [
                {"title": "Gobierno gobierna por el retrovisor", "text": "Secretarias y gestores dependen de fuentes dispersas, planillas y lectura tardia para decidir alertas, comunicacion y respuesta territorial."},
                {"title": "Farmacia compra despues del quiebre", "text": "Sin radar epidemiologico territorial, la demanda de medicamentos e insumos aparece primero en el mostrador o en la falta de stock."},
                {"title": "Hospital siente el pico en la puerta", "text": "Sin anticipacion asistencial, camas, triaje, escalas e insumos reaccionan solo cuando la presion ya llego a la puerta de entrada."},
                {"title": "SST necesita flujo propio", "text": "Certificados, accidentes, eSocial SST, examenes, PGR, app del trabajador y bienestar anonimo requieren su propio flujo ocupacional, sin depender ni mezclarse con el radar epidemiologico."},
            ],
        },
        "solution": {
            "eyebrow": "Solucion",
            "title": "Una arquitectura que entrega la operacion correcta con la privacidad correcta.",
            "body": "SolusCRT separa contratos, logins, indicadores y operacion por segmento. Gobierno, farmacia y hospital usan inteligencia epidemiologica territorial en el lenguaje de su propio sector. SST funciona como ambiente independiente de gestion ocupacional, con suscripcion propia, prueba de 15 dias y app del trabajador.",
            "cards": [
                {"title": "Gobierno", "text": "Sala de situacion, alertas, auditoria, matriz de decision y lectura territorial para union, estados y municipios."},
                {"title": "Farmacia", "text": "Inventario, FEFO, lotes, compras y prevision de demanda ligadas al riesgo epidemiologico regional."},
                {"title": "Hospital", "text": "Camas, triaje, internaciones, equipos y presion asistencial con anticipacion del pico."},
                {"title": "SST", "text": "Certificados, accidentes, examenes, NRs, eSocial, bienestar anonimo y app del trabajador sin dato epidemiologico dentro del ambiente."},
            ],
        },
        "ecosystem": {
            "eyebrow": "Ecosistema",
            "title": "Una plataforma. Cinco ambientes especializados.",
            "cards": [
                {"title": "Gobierno", "text": "Sala de situacion epidemiologica, alertas oficiales, matriz de decision, auditoria, contratos anuales y fuentes brasilenas oficiales para esfera federal, estadual y municipal."},
                {"title": "Farmacia", "text": "Gestion farmaceutica, FEFO, lotes, quiebre, compras e integracion epidemiologica para anticipar demanda por tienda o red."},
                {"title": "Hospital", "text": "Gestion de camas, atencion, triaje, internacion, presion asistencial y equipos conectados al radar epidemiologico."},
                {"title": "SST y Empresas", "text": "SST completo, bienestar anonimo, app del trabajador, panel de empleados, KPIs de ausentismo e integracion eSocial SST. Prueba gratuita de 15 dias."},
                {"title": "Plan de Salud", "text": "Gestion completa para operadoras: beneficiarios, contratos, guias de autorizacion, siniestros, reembolsos y dashboard epidemiologico con mapa de calor territorial. 100 usuarios y 100 maquinas autorizadas."},
            ],
        },
        "differential": {
            "eyebrow": "Diferencial",
            "title": "No es un unico producto empujado para todos. Es un ecosistema listo para cinco frentes que colaboran entre si.",
            "body": "SolusCRT respeta la logica de cada segmento: contrato institucional y gobernanza para gobierno; expansion por tienda o red para farmacia; capacidad asistencial para hospital; suscripcion recurrente, implantacion rapida y prueba de valor para SST y clinicas ocupacionales; gestion especializada de beneficiarios, siniestros y reembolsos para operadoras de plan de salud.",
            "quote": "Gobierno compra inteligencia territorial. Farmacia compra demanda futura. Hospital compra preparacion asistencial. SST compra conformidad, app y compromiso. Plan de Salud compra gestion de operadora con epidemiologia.",
        },
        "governance": {
            "eyebrow": "Gobernanza",
            "title": "Privacidad, seguridad y segregacion por segmento forman parte del producto.",
            "cards": [
                {"title": "Ambientes aislados", "text": "Gobierno, farmacia, hospital, SST y plan de salud tienen sus propios accesos, sesiones, trazas y alcances. Lo que nace en un ambiente no aparece en otro."},
                {"title": "Epidemiologia territorial", "text": "La app poblacional genera senales anonimas y territoriales para gobierno, farmacia y hospital, con antifraude, ubicacion actual y separacion entre senal, fuente oficial e inferencia."},
                {"title": "SST y bienestar protegidos", "text": "Certificados, accidentes, examenes, ausencias y eSocial son datos sensibles. Los check-ins de bienestar son anonimos por arquitectura y el nombre solo aparece cuando el trabajador inicia el contacto."},
                {"title": "Apps y auditoria", "text": "La app poblacional y la app del trabajador cumplen roles distintos, con tokens, dispositivos autorizados, notificaciones y revocacion por contrato."},
            ],
        },
        "values": {
            "eyebrow": "Valores",
            "title": "Valores que hacen que la tecnologia merezca confianza.",
            "body": "SolusCRT fue pensado para cooperar con personas e instituciones: proteger vidas, anticipar riesgos, respetar privacidad, comunicar con responsabilidad y ayudar a lideres a actuar sin distorsionar la verdad.",
            "cards": [
                {"title": "Vida primero", "text": "SST, bienestar e IA existen para reducir dano real a personas reales."},
                {"title": "Verdad antes que impacto", "text": "Senal temprana, dato oficial e IA siempre separados e identificados."},
                {"title": "Privacidad y anonimato", "text": "Bienestar anonimo por diseno. Datos SST con minimizacion y cumplimiento LGPD."},
                {"title": "Cooperacion", "text": "Empresa, trabajador, gobierno y poblacion actuando en la misma red de cuidado."},
            ],
        },
        "app": {
            "eyebrow": "Dos apps integradas",
            "title": "App poblacional y app del trabajador: cada una en el lugar correcto.",
            "body": "La app poblacional envia sintomas anonimos, recibe alertas y alimenta a gobierno, farmacia y hospital con inteligencia territorial. La app del trabajador pertenece al ambiente SST: libera certificado medico digital, notificaciones, solicitudes y check-ins de bienestar anonimos. Dos apps. Dos contextos. Una gobernanza clara.",
            "quote": "App poblacional para epidemiologia territorial. App del trabajador para SST organizacional.",
        },
        "closing": {
            "eyebrow": "Cierre",
            "title": "Un relato fuerte para mercado. Un producto claro para suscripcion y contrato.",
            "body": "En la demostracion, cada comprador ve su propio valor: gobierno con contrato institucional y sala de situacion; farmacia y hospital con expansion por unidad o red; SST con suscripcion recurrente, prueba de 15 dias e implantacion rapida. SolusCRT crece sin mezclar operacion, privacidad ni proposito institucional.",
            "meeting": "Solicitar demostracion comercial",
            "back": "Volver al sitio principal",
        },
    },
}


def _commercial_site_copy(language, site):
    if language != "pt":
        return site
    site = deepcopy(site)
    site["title"] = "SolusCRT Saúde | healthtech de inteligência em saúde com IA para Governo, Farmácia, Hospital, SST e Plano de Saúde"
    site["description"] = "Healthtech brasileira de inteligência em saúde com IA. Cinco ambientes privados por segmento — Governo, Farmácia, Hospital, SST e Plano de Saúde — com dois apps e governança LGPD."
    site["nav"]["diferencial"] = "Por que comprar"
    site["nav"]["ecossistema"] = "Segmentos"
    site["nav"]["valores"] = "Confiança"
    site["nav"]["app"] = "Apps"
    site["nav"]["contato"] = "Contato"
    site["nav_note"] = "Uma healthtech. Cinco segmentos. Um caminho claro para compra."
    site["hero_eyebrow"] = "Healthtech brasileira · pronta para demonstração comercial."
    site["hero_title"] = "Cinco ambientes privados para cada decisor em saúde."
    site["hero_title_desktop_lines"] = [
        "Cinco ambientes",
        "privados para",
        "cada decisor",
        "em saúde.",
    ]
    site["hero_title_lines"] = [
        "Cinco ambientes",
        "privados para",
        "cada decisor",
        "em saúde.",
    ]
    site["hero_lead"] = (
        "A SolusCRT é uma healthtech brasileira de inteligência em saúde com IA. Em vez de um painel único e técnico, a home mostra cinco ambientes que o cliente reconhece de imediato: "
        "Governo, Farmácia, Hospital, SST e Plano de Saúde. Cada setor entra com linguagem própria, proposta clara "
        "e caminho de compra objetivo."
    )
    site["actions"]["presentation"] = "Ver apresentação comercial"
    site["actions"]["app"] = "Conhecer os apps"
    site["actions"]["sales"] = "Agendar demonstração"
    site["actions"]["open_presentation"] = "Abrir apresentação"
    site["actions"]["meeting"] = "Falar com comercial"
    site["actions"]["login"] = "Acesso cliente"
    site["actions"]["signup"] = "Solicitar demo"
    site["proofs"] = [
        {
            "title": "Governo",
            "text": "Sala de situação, alertas e governança territorial para contratos B2G com leitura executiva.",
        },
        {
            "title": "Farmácia",
            "text": "Previsibilidade de demanda, compra mais segura e menos ruptura para loja ou rede.",
        },
        {
            "title": "Hospital",
            "text": "Leitos, triagem, equipes e capacidade assistencial preparados antes do pico.",
        },
        {
            "title": "SST",
            "text": "Assinatura recorrente com app do trabalhador, bem-estar e conformidade em um fluxo próprio.",
        },
        {
            "title": "Plano de Saúde",
            "text": "Operadora com beneficiários, guias, sinistros, reembolsos e radar territorial no mesmo ambiente.",
        },
    ]
    site["chips"] = [
        "Governo",
        "Farmácia",
        "Hospital",
        "SST",
        "Plano de Saúde",
        "Demo comercial",
    ]
    site["metrics"] = [
        {
            "value": "5 segmentos",
            "text": "Cada decisor entra numa experiência pensada para sua rotina e seu contrato",
        },
        {
            "value": "2 apps separados",
            "text": "App da população para território e app do trabalhador para SST",
        },
        {
            "value": "LGPD por arquitetura",
            "text": "Segregação, auditoria e controle de acesso tratados como parte central da confiança",
        },
        {
            "value": "Contato comercial",
            "text": "A conversa sai da vitrine e vai direto para o enquadramento certo do cliente",
        },
    ]
    site["differential"]["title"] = (
        "Quando a IA fala a linguagem do segmento certo, a conversa encurta e a compra avança."
    )
    site["differential"]["lead"] = (
        "A proposta certa reduz explicação, diminui objeção e acelera demo, negociação e assinatura. O SolusCRT "
        "organiza a conversa por segmento para que cada cliente veja uma IA desenhada para o próprio contexto, sem "
        "precisar traduzir a plataforma."
    )
    site["differential"]["traditional_title"] = "Oferta genérica"
    site["differential"]["traditional_items"] = [
        "O mesmo discurso tenta servir governo, farmácia, hospital, SST e operadora ao mesmo tempo.",
        "O comprador precisa traduzir sozinho onde está o valor para sua rotina e seu contrato.",
        "Quando a proposta parece improvisada, a venda perde força antes da demo ficar memorável.",
    ]
    site["differential"]["solus_title"] = "Arquitetura comercial SolusCRT"
    site["differential"]["solus_items"] = [
        "Cada segmento abre um ambiente com linguagem, rotina e IA próprias.",
        "A prova de valor aparece no ponto certo: Governo, Farmácia, Hospital, SST e Plano de Saúde.",
        "O SST fica separado, com assinatura própria, app do trabalhador e experiência ocupacional sem mistura de contexto.",
    ]
    site["ecosystem_title"] = "Cinco ambientes isolados, comercializados separadamente."
    site["ecosystem_lead"] = (
        "O visitante reconhece o seu setor, o seu risco e o seu modelo de compra sem misturar clientes, bases ou "
        "permissões. Cada ambiente nasce para um contrato próprio."
    )
    site["slides"] = [
        {
            "small": "Governo",
            "title": "Autoridade territorial com governança",
            "text": "Sala de situação para comunicar melhor, agir antes e sustentar resposta pública com clareza.",
        },
        {
            "small": "Farmácia",
            "title": "Previsibilidade de demanda",
            "text": "Gestão para reduzir ruptura, planejar compras e crescer com mais previsibilidade.",
        },
        {
            "small": "Hospital",
            "title": "Capacidade assistencial preparada",
            "text": "Leitos, triagem, equipes e fluxo organizados antes da pressão ganhar velocidade.",
        },
        {
            "small": "SST",
            "title": "Conformidade com adesão",
            "text": "SST completo, app do trabalhador e bem-estar em uma jornada mais fluida e comercialmente clara.",
        },
        {
            "small": "Plano de Saúde",
            "title": "Operação especializada",
            "text": "Beneficiários, contratos, guias, sinistros, reembolsos e radar territorial em um ambiente próprio.",
        },
    ]
    site["platform"]["title_html"] = "Quer proposta?<br>Fale com comercial."
    site["platform"]["lead"] = (
        "Cada cliente entra pelo caminho certo. Se o segmento faz sentido, a gente aprofunda por contato comercial, "
        "sem tabela pública e sem expor valores antes da hora."
    )
    site["platform"]["cards"] = [
        {
            "title": "SST & Clínicas Ocupacionais",
            "badge": "Assinatura recorrente",
            "text": "Uma conversa de negócio que organiza a rotina, valoriza o colaborador e reduz atrito operacional.",
            "cta": "Falar com comercial",
        },
        {
            "title": "Farmácia & Rede Farmacêutica",
            "badge": "Operação por loja ou rede",
            "text": "Um ambiente para antecipar demanda, proteger margem e preparar a farmácia antes da ruptura.",
            "cta": "Falar com comercial",
        },
        {
            "title": "Hospital & Rede Assistencial",
            "badge": "Estrutura ou rede",
            "text": "Uma plataforma para proteger capacidade assistencial, ordenar fluxo e preparar equipes antes da pressão.",
            "cta": "Falar com comercial",
        },
        {
            "title": "Governo & Vigilância Pública",
            "badge": "Contrato institucional",
            "text": "Unifique vigilância territorial, e-SUS/RNDS, faturamento SUS, auditoria e governança LGPD em uma operação pública única.",
            "cta": "Falar com comercial",
        },
        {
            "title": "Operadora de Plano de Saúde",
            "badge": "Operadora especializada",
            "text": "Gestão completa para operadoras: beneficiários, contratos, guias, sinistros, reembolsos e leitura territorial.",
            "cta": "Falar com comercial",
        },
    ]
    site["enterprise"]["eyebrow"] = "Mercado e assinatura"
    site["enterprise"]["title"] = "Cinco segmentos, cinco motivos claros para assinar."
    site["enterprise"]["lead"] = (
        "A plataforma não existe para empurrar o mesmo argumento para todo mundo. Ela foi organizada para que cada "
        "cliente reconheça o seu próprio caso de uso, o seu tipo de compra e a sua melhor porta de entrada."
    )
    site["enterprise"]["items"] = [
        {
            "title": "Governo",
            "text": "Sala de situação, alertas, auditoria e leitura territorial para união, estados e municípios com contrato institucional.",
        },
        {
            "title": "Farmácia",
            "text": "Previsibilidade de demanda, compras, lotes e ruptura para loja, rede ou distribuidor com leitura regional.",
        },
        {
            "title": "Hospital",
            "text": "Leitos, triagem, equipes e capacidade assistencial preparados antes da pressão chegar ao pronto atendimento.",
        },
        {
            "title": "SST",
            "text": "ASO, CAT, eSocial, exames, PGR, bem-estar anônimo e app do trabalhador em um ambiente próprio e recorrente.",
        },
        {
            "title": "Plano de Saúde",
            "text": "Beneficiários, contratos, guias, sinistros, reembolsos e radar territorial em uma operação especializada.",
        },
    ]
    site["enterprise"]["metrics"] = [
        {"value": "5 segmentos", "text": "cada decisor encontra um ambiente com linguagem, risco, compra e IA próprios"},
        {"value": "2 apps separados", "text": "app da população para território e app do trabalhador para SST"},
        {"value": "Contato comercial", "text": "sem tabela pública e com proposta ajustada ao segmento"},
    ]
    site["matrix"] = [
        {
            "label": "Governo",
            "title": "Autoridade territorial",
            "text": "Painéis para gestores federais, estaduais e municipais com radar territorial, fontes oficiais, comunicação e auditoria institucional.",
        },
        {
            "label": "Farmácia",
            "title": "Previsibilidade de demanda",
            "text": "Antecipação de demanda, giro, ruptura e insumos com gestão conectada ao risco regional.",
        },
        {
            "label": "Hospital",
            "title": "Preparo assistencial",
            "text": "Leitos, triagem, equipes e pressão assistencial com visibilidade antes do pico chegar ao pronto atendimento.",
        },
        {
            "label": "SST",
            "title": "Operação ocupacional",
            "text": "ASO, CAT, afastamentos, NR, EPI/EPC, PGR, eSocial SST, app do trabalhador e bem-estar em ambiente próprio.",
        },
        {
            "label": "Plano de Saúde",
            "title": "Gestão especializada de operadora",
            "text": "Beneficiários, contratos, guias, sinistros, reembolsos e leitura territorial no mesmo ambiente.",
        },
        {
            "label": "Privacidade",
            "title": "Confiança por segregação",
            "text": "Cada ambiente tem login, permissão, dados e auditoria próprios. Governo, farmácia, hospital, SST e plano de saúde não compartilham base operacional.",
        },
    ]
    site["values"]["title"] = "Valores que fazem a tecnologia merecer confiança"
    site["values"]["lead"] = (
        "A SolusCRT nasceu de uma pergunta que incomodava: por que a informação de saúde sempre chega tarde? "
        "Tarde para o gestor agir, tarde para o hospital se preparar, tarde para o trabalhador ser amparado. "
        "Cada decisão de produto, privacidade e governança começa daqui — do compromisso de que tecnologia "
        "de saúde existe para chegar a tempo e proteger vidas reais."
    )
    site["app"]["title"] = "Dois apps, duas jornadas, uma venda mais clara."
    site["app"]["lead"] = (
        "A app da população gera inteligência territorial. A app do trabalhador pertence ao ambiente SST. Separar as "
        "jornadas deixa a proposta mais simples para o cliente e mais clara para a compra."
    )
    site["app"]["note"] = "O app do trabalhador é ativado por contrato dentro do ambiente SST. O app listado nas lojas é o app da população."
    site["app"]["risks"] = [
        {"title": "App da população", "text": "Sintomas anônimos, radar local e alertas oficiais."},
        {"title": "App do trabalhador", "text": "ASO, notificações e bem-estar no fluxo SST."},
        {"title": "Leitura territorial", "text": "Focos e sintomas por região com localização atual."},
        {"title": "Privacidade por contexto", "text": "Dois apps, duas promessas e duas governanças distintas."},
    ]
    site["cta"]["title"] = "Quando cada segmento se reconhece no produto, a decisão avança mais rápido."
    site["cta"]["lead"] = (
        "Se o seu cliente é Governo, Farmácia, Hospital, SST ou Plano de Saúde, o SolusCRT já chega com narrativa "
        "comercial, oferta e governança coerentes."
    )
    site["footer"] = "SolusCRT Saúde · healthtech de inteligência em saúde com IA. Cinco ambientes privados para Governo, Farmácia, Hospital, SST e Plano de Saúde."
    return site


def _commercial_presentation_copy(language, deck):
    if language != "pt":
        return deck
    deck = deepcopy(deck)
    deck["title"] = "Apresentação comercial SolusCRT Saúde"
    deck["vision"]["title"] = "Healthtech de monitoramento epidemiológico com IA em cinco ambientes privados e isolados."
    deck["vision"]["body"] = (
        "A SolusCRT Saúde é uma healthtech brasileira de inteligência em saúde com IA. Organiza a conversa por segmento, mas nunca mistura clientes: Governo, Farmácia, Hospital, "
        "SST e Plano de Saúde entram em jornadas distintas, com ambiente, acesso e privacidade próprios. A IA é "
        "desenhada para cada ambiente, com contexto, leitura e recomendação próprios para cada contrato."
    )
    deck["vision"]["labels"] = {"resp": "Sinais", "deng": "IA", "covid": "Risco"}
    deck["problem"]["title"] = "Quando tudo parece um único pacote, o comprador não enxerga seu próprio contexto."
    deck["problem"]["cards"] = [
        {
            "title": "Governo demora para decidir",
            "text": "Secretarias e gestores dependem de fontes dispersas, planilhas e leitura tardia para definir alerta, comunicação e resposta territorial.",
        },
        {
            "title": "Farmácia perde margem",
            "text": "Sem previsibilidade, a demanda por medicamentos e insumos aparece tarde demais e a ruptura vira custo.",
        },
        {
            "title": "Hospital reage em cima do pico",
            "text": "Sem antecipação assistencial, leitos, triagem, escala e suprimentos correm atrás da pressão.",
        },
        {
            "title": "SST precisa de fluxo próprio",
            "text": "ASO, CAT, eSocial SST, exames, PGR, app do trabalhador e bem-estar exigem um ambiente independente, sem mistura com outros clientes.",
        },
    ]
    deck["solution"]["title"] = "Cada segmento entra no ambiente certo, com isolamento, privacidade e proposta própria."
    deck["solution"]["body"] = (
        "SolusCRT separa contratos, acesso e narrativa por segmento. Governo, Farmácia e Hospital usam inteligência "
        "territorial com linguagem de negócio dentro do seu próprio espaço; SST opera como ambiente independente de "
        "gestão ocupacional, com assinatura própria, trial e app do trabalhador, sem compartilhamento de base entre clientes."
    )
    deck["solution"]["cards"] = [
        {"title": "Governo", "text": "Sala de situação, alertas, auditoria e leitura territorial para união, estados e municípios."},
        {"title": "Farmácia", "text": "Estoque, lotes, compras e previsão de demanda ligados ao risco regional."},
        {"title": "Hospital", "text": "Leitos, triagem, internações, equipes e pressão assistencial com antecipação do pico."},
        {"title": "SST", "text": "ASO, CAT, exames, NRs, eSocial, bem-estar anônimo e app do trabalhador em um ambiente próprio."},
    ]
    deck["ecosystem"]["eyebrow"] = "Ambientes isolados"
    deck["ecosystem"]["title"] = "Cinco ambientes isolados para cinco compradoras diferentes."
    deck["ecosystem"]["cards"] = [
        {"title": "Governo", "text": "Sala de situação, alertas oficiais, matriz de decisão, auditoria e contrato institucional em ambiente próprio."},
        {"title": "Farmácia", "text": "Gestão farmacêutica, FEFO, lotes, ruptura, compras e previsão de demanda em ambiente próprio."},
        {"title": "Hospital", "text": "Gestão de leitos, atendimento, triagem, internação e preparação assistencial em ambiente próprio."},
        {"title": "SST e Empresas", "text": "SST completo, bem-estar anônimo, app do trabalhador e prova de valor em ambiente próprio."},
        {"title": "Plano de Saúde", "text": "Beneficiários, contratos, guias, sinistros, reembolsos e leitura territorial em ambiente próprio."},
    ]
    deck["differential"]["eyebrow"] = "Diferencial"
    deck["differential"]["title"] = "Não é uma IA genérica. É inteligência epidemiológica desenhada por segmento."
    deck["differential"]["body"] = (
        "SolusCRT respeita a forma como cada segmento decide: Governo compra clareza e governança; Farmácia compra "
        "previsibilidade; Hospital compra capacidade; SST compra adesão e recorrência; Plano de Saúde compra operação "
        "especializada. Cada um entra no seu próprio ambiente com uma IA ajustada ao contexto, com dados segregados e "
        "experiência protegida."
    )
    deck["differential"]["quote"] = "Um motor. Cinco ambientes. Nenhum cliente misturado."
    deck["governance"]["title"] = "Privacidade e segregação fazem parte de cada ambiente."
    deck["values"]["title"] = "Valores que fazem a tecnologia merecer confiança"
    deck["values"]["body"] = (
        "SolusCRT foi pensado para cooperar com pessoas e instituições: proteger vidas, antecipar riscos, respeitar "
        "privacidade, comunicar com responsabilidade e ajudar líderes a agir sem distorcer a verdade ou misturar "
        "clientes."
    )
    deck["app"]["title"] = "Dois apps, duas promessas, uma arquitetura clara."
    deck["app"]["body"] = (
        "A app da população alimenta a inteligência territorial. A app do trabalhador fica no ambiente SST. Separar as "
        "jornadas torna a venda mais clara, preserva a privacidade e evita qualquer mistura entre ambientes."
    )
    deck["app"]["quote"] = "App da população para território. App do trabalhador para SST."
    deck["closing"]["eyebrow"] = "Fechamento"
    deck["closing"]["title"] = "Uma apresentação que faz cada decisor ver seu próprio ambiente."
    deck["closing"]["body"] = (
        "Na demonstração, cada decisor enxerga o seu valor dentro do seu próprio ambiente: governo com leitura territorial, "
        "farmácia com previsibilidade, hospital com capacidade e SST com conformidade e adesão, sempre com isolamento e "
        "privacidade."
    )
    deck["closing"]["meeting"] = "Solicitar demonstração comercial"
    deck["closing"]["back"] = "Voltar ao site principal"
    return deck


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
    site = _commercial_site_copy(language, SITE_TRANSLATIONS[language])
    response = render(
        request,
        "site_principal.html",
        {
            "site": site,
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
    deck = _commercial_presentation_copy(language, PRESENTATION_TRANSLATIONS[language])
    response = render(
        request,
        "apresentacao.html",
        {
            "deck": deck,
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
        "brand": "SolusCRT Saúde",
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
            "subtitle": "Como o SolusCRT Saude trata dados no app da populacao, no app do funcionario e nos ambientes de Governo, Farmacia, Hospital, SST e Plano de Saude.",
            "sections": [
                ("Quem somos e escopo", "O SolusCRT Saude e uma plataforma SaaS completa de gestao em saude, com ambiente SST para empresas, gestao farmaceutica, gestao hospitalar, sala de situacao para governo, ambiente dedicado para operadoras de plano de saude e dois apps: o app da populacao (gratuito e anonimo) e o app do funcionario (vinculado a conta empresarial). Esta politica explica o tratamento de dados em todos esses contextos."),
                ("Resumo para usuarios do app da populacao", "No app publico, voce pode consultar radar, mapa e alertas e, se desejar, enviar sintomas de forma voluntaria e anonima. O app nao oferece diagnostico medico, prescricao, triagem individual, atendimento de emergencia ou substituicao de consulta profissional."),
                ("Resumo para usuarios do app do funcionario", "O app do funcionario e vinculado a conta empresarial contratante. Por meio dele, o funcionario acessa o proprio ASO digital, faz solicitacoes, recebe notificacoes de exames e treinamentos e envia check-ins de bem-estar. Check-ins de bem-estar sao anonimos por padrao — a empresa ve apenas dados agregados, nunca o nome associado ao check-in individual, salvo quando o proprio funcionario solicita contato de apoio."),
                ("Cinco ambientes, cinco contextos de tratamento", "Governo trata indicadores territoriais, alertas, auditoria e operacao institucional. Farmacia trata catalogo, estoque, lotes, fornecedores, demanda e rastreabilidade. Hospital trata triagem, leitos, internacoes, prescricoes e operacao assistencial. SST trata ASO, CAT, exames, afastamentos, eSocial, treinamentos e bem-estar anonimo. Plano de Saude trata cadastros de beneficiarios, contratos, guias de autorizacao, sinistros, reembolsos e dados epidemiologicos territoriais. O app da populacao alimenta apenas a inteligencia epidemiologica territorial; o app do funcionario pertence ao ambiente SST."),
                ("Dados que podemos tratar", "Podemos tratar, conforme o contexto e o ambiente: sintomas selecionados; coordenadas de localizacao enquanto o app esta em uso; cidade, estado, bairro ou regiao aproximada; data e hora do envio; identificador tecnico aleatorio gerado pelo app; IP; tokens FCM de notificacao push; aceite de termos; dados de conta corporativa ou governamental; registros de acesso e auditoria. No ambiente de Governo: alertas, parametros territoriais, indicadores agregados, historico de comunicacao e trilhas institucionais. Na Farmacia: cadastros de itens, lotes, validades, inventario, compras, fornecedores, pacientes quando aplicavel e rastreabilidade operacional. No Hospital: cadastros assistenciais, triagem, leitos, internacoes, prescricoes e operacao clinica interna. No ambiente SST: ASO, CAT, laudos de exames, afastamentos, treinamentos NR, EPI/EPC, postos de trabalho, riscos, PGR e registros eSocial SST — todos dados de saude sensiveis tratados com controles adicionais. No bem-estar: respostas anonimas de check-in de humor, saude fisica, saude mental, estresse e satisfacao no trabalho."),
                ("Dados sensiveis de saude — SST e bem-estar", "ASO, CAT, exames, afastamentos e qualquer dado de saude ocupacional sao dados sensiveis nos termos da LGPD. Sao tratados com minimizacao, finalidade especifica, controles de acesso por perfil, auditoria por operacao e exibicao restrita ao perfil autorizado. Dados de bem-estar sao anonimos por arquitetura: o nome do funcionario nunca e associado a uma resposta individual de check-in nos paineis da empresa, a menos que o proprio funcionario consinta explicitamente ao solicitar contato de apoio."),
                ("Por que usamos localizacao", "No app da populacao, a localizacao e usada para georreferenciar sinais de saude, mostrar risco territorial, reduzir fraude e exibir alertas proximos. No app do funcionario, a localizacao pode ser usada para confirmar presenca em posto de trabalho ou contexto de notificacao, conforme configuracao do contrato. O usuario pode controlar permissoes no sistema operacional."),
                ("Tokens de notificacao FCM", "Usamos tokens FCM para enviar notificacoes push no app do funcionario (lembretes de exame, treinamento, alertas) e no app da populacao (alertas oficiais). Tokens sao armazenados de forma segura, vinculados ao dispositivo autorizado e podem ser revogados pelo usuario ou pelo gestor conforme contrato."),
                ("Finalidades", "Usamos os dados para operar a plataforma, exibir radar local, formar indicadores agregados, publicar alertas, apoiar decisao territorial em governo, orientar demanda em farmacia, antecipar pressao assistencial em hospital, gerenciar SST e conformidade eSocial, enviar notificacoes ao funcionario, coletar e agregar check-ins de bem-estar, prevenir abuso, proteger a seguranca, atender contratos, cumprir obrigacoes legais e apoiar governanca responsavel."),
                ("Base legal LGPD", "Conforme o contexto, o tratamento pode se apoiar em consentimento, execucao de contrato, cumprimento de obrigacao legal ou regulatoria (inclusive SST e eSocial), protecao da vida ou da incolumidade fisica, tutela da saude, legitimo interesse com salvaguardas e exercicio regular de direitos."),
                ("Compartilhamento", "Empresas contratantes acessam dados SST de seus proprios funcionarios conforme perfil e contrato. Dados de bem-estar sao exibidos apenas de forma agregada para a empresa. Governos, hospitais, farmacias e operadores autorizados acessam informacoes conforme escopo contratual do seu proprio ambiente. A plataforma prioriza dados agregados e territoriais quando o caso exige leitura territorial e nao mistura a base operacional de um segmento com a de outro sem base legal, contratual e tecnica explicita."),
                ("O que nao fazemos", "Nao vendemos dados pessoais para publicidade, nao usamos dados do app para rastrear usuarios entre apps e sites de terceiros, nao entregamos diagnostico medico e nao exibimos publicamente relato individual identificavel."),
                ("Retencao e descarte", "Mantemos dados pelo tempo necessario para operacao, seguranca, auditoria, cumprimento contratual, defesa de direitos e obrigacoes legais — incluindo prazos de retencao de documentos SST exigidos pela legislacao trabalhista e previdenciaria. Dados de bem-estar anonimizados podem ser mantidos para analise de tendencias agregadas."),
                ("Direitos do titular", "Titulares podem solicitar informacoes, acesso, correcao, exclusao quando aplicavel, esclarecimentos sobre compartilhamento, revisao de consentimento e orientacoes sobre tratamento de dados pelo canal oficial de privacidade."),
                ("Menores de idade", "O app da populacao e informativo e nao deve ser usado por criancas sem orientacao dos responsaveis. O app do funcionario e destinado a trabalhadores maiores de idade vinculados ao contrato empresarial."),
                ("Seguranca", "Usamos HTTPS, variaveis de ambiente para segredos, banco gerenciado em producao, cookies seguros, restricao de CORS/CSRF, controle de sessao, limite de dispositivos por contrato, trilhas de auditoria, segregacao por ambiente e perfil e boas praticas para reduzir acesso indevido, manipulacao e exposicao desnecessaria. Governo, farmacia, hospital, SST e plano de saude possuem controles de acesso e contexto operacional proprios."),
                ("Contato de privacidade / DPO", "Pedidos de privacidade, direitos do titular (acesso, correcao, exclusao, portabilidade), duvidas sobre LGPD e solicitacoes relacionadas ao tratamento de dados devem ser enviados para privacidade@soluscrt.com.br. Prazo de resposta: ate 15 dias uteis. Para incidentes urgentes de seguranca, utilize o mesmo endereco com o assunto [INCIDENTE]."),
                ("Atualizacoes", "Esta politica pode ser atualizada para refletir melhorias da plataforma, novas exigencias legais, ajustes de App Store, contratos institucionais e mudancas nos controles de seguranca."),
            ],
        },
        "termos": {
            "title": "Termos de Uso",
            "subtitle": "Regras de uso do app da populacao, do app do funcionario e dos ambientes privados de Governo, Farmacia, Hospital, SST e Plano de Saude.",
            "sections": [
                ("Natureza da plataforma", "O SolusCRT Saude e uma plataforma SaaS de gestao em saude com cinco ambientes privados e independentes: Governo, Farmacia, Hospital, SST e Plano de Saude. O app da populacao oferece inteligencia epidemiologica informativa. O app do funcionario atende o ambiente SST. Nenhum dos recursos substitui diagnostico medico, prescricao, triagem clinica individual ou atendimento de emergencia."),
                ("Envio responsavel no app da populacao", "Usuarios devem enviar sintomas reais, de boa-fe e apenas quando houver relacao com sua condicao atual. Envios repetidos, automatizados ou fraudulentos podem ser filtrados ou bloqueados."),
                ("App do funcionario — uso adequado", "O app do funcionario e de uso exclusivo do trabalhador vinculado ao contrato da empresa. E proibido compartilhar credenciais, acessar dados de outros funcionarios sem autorizacao ou usar o app para fins alheios a gestao de saude ocupacional e bem-estar."),
                ("Bem-estar — submissao voluntaria", "Check-ins de bem-estar sao voluntarios. O funcionario nao e obrigado a responder e pode omitir qualquer campo. A empresa ve apenas dados agregados. O funcionario consente explicitamente ao solicitar contato de apoio."),
                ("Responsabilidade por dados do contratante", "Cada cliente contratante e responsavel pela exatidao, licitude e atualizacao dos dados inseridos no seu proprio ambiente. No SST, isso inclui ASO, CAT, exames, afastamentos e registros eSocial SST. Em Farmacia e Hospital, inclui cadastros, estoque, operacao assistencial e registros internos. Em Governo, inclui configuracoes, alertas e fluxos institucionais publicados por seus operadores autorizados."),
                ("Periodo de teste gratuito e assinaturas", "O periodo de teste gratuito tem duracao de 15 dias corridos a partir da ativacao, sem necessidade de cartao de credito, para os ambientes privados em que essa oferta estiver ativa. Ao final do periodo de teste, sem assinatura ativa, o acesso e suspenso automaticamente e os dados podem ser retidos por periodo adicional conforme politica de retencao. Nao ha cobranca automatica apos o trial."),
                ("Ambientes privados", "Acessos de SST, farmacia, hospital, governo, plano de saude e administracao sao exclusivos para clientes e operadores autorizados. Tentativas de acesso indevido podem ser registradas e bloqueadas."),
                ("Uso proibido", "E proibido tentar burlar controles de seguranca, automatizar envios indevidos, inserir informacoes falsas em dados SST ou de bem-estar, acessar area contratual sem autorizacao, realizar engenharia reversa ou usar a plataforma para finalidade ilegal, discriminatoria ou abusiva."),
                ("Contas e credenciais", "Credenciais sao pessoais ou institucionais conforme contrato. O usuario ou cliente e responsavel por preservar senhas, dispositivos autorizados e politicas internas de acesso."),
                ("Disponibilidade", "A plataforma depende de internet, servicos de nuvem, APIs, fontes oficiais e permissao de localizacao. Podem ocorrer indisponibilidades temporarias ou degradacao de dados externos."),
                ("Responsabilidade decisoria", "Decisoes operacionais, clinicas e institucionais devem considerar contexto tecnico, validacao humana e protocolos aplicaveis de saude publica e saude ocupacional."),
                ("Propriedade intelectual", "Marcas, interfaces, modelos, organizacao da plataforma, documentos, codigos, paineis e materiais do SolusCRT Saude pertencem aos seus titulares e sao licenciados nos limites contratados."),
                ("Contratacao B2B e B2G", "Assinaturas privadas, trial, implantacao, expansao por unidade ou rede, limites de usuarios, dispositivos, suporte, integracoes, SLA e valores podem ser definidos em proposta, contrato, termo de adesao ou instrumento especifico. Contratos governamentais e institucionais podem seguir regras proprias de B2G."),
            ],
        },
        "seguranca-lgpd": {
            "title": "Seguranca, LGPD e Governanca",
            "subtitle": "Controles para proteger dados, acessos e confianca institucional em todos os ambientes da plataforma.",
            "sections": [
                ("Principios", "A plataforma deve seguir finalidade, adequacao, necessidade, seguranca, prevencao, transparencia e responsabilizacao no tratamento de dados pessoais, com atencao especial a dados sensiveis de saude presentes nos ambientes SST e Plano de Saude."),
                ("Segregacao de ambientes", "SST/Empresa, farmacia, hospital, governo e plano de saude sao ambientes separados por fluxo de login, permissao, sessao, auditoria e dominio/subdominio quando contratado. Dados de um ambiente nao sao acessiveis a outros sem autorizacao explicita."),
                ("Controles antifraude epidemiologicos", "O app da populacao e o backend utilizam controles por aparelho, rede, repeticao, qualidade do sinal e localizacao atual para reduzir manipulacao de focos. Intensidade epidemiologica so cai apos 10 dias sem novos sinais e quando serie temporal, agregados e fontes oficiais sustentam queda real."),
                ("Dados de governo, farmacia, hospital e plano de saude", "Os ambientes epidemiologicos e operacionais tratam escopos diferentes: governo recebe leitura territorial e governanca; farmacia recebe dados de estoque, lotes e demanda; hospital recebe dados assistenciais e capacidade; plano de saude recebe cadastros de beneficiarios, guias de autorizacao, sinistros, reembolsos e inteligencia epidemiologica territorial propria. Cada ambiente tem trilhas, perfis e autorizacoes proprias."),
                ("Protecao de acesso", "A plataforma adota controle de sessao, autorizacao por perfil, limite de dispositivos contratados, bloqueios de uso simultaneo quando aplicavel e revogacao de acessos."),
                ("Dados SST — dados sensiveis de saude", "ASO, CAT, exames, laudos e afastamentos sao dados sensiveis tratados com minimizacao, acesso restrito por perfil profissional autorizado, auditoria por operacao e exibicao adequada ao contexto contratual."),
                ("Bem-estar — anonimato por arquitetura", "Check-ins de bem-estar nunca associam o nome do funcionario a uma resposta individual nos paineis da empresa. O anonimato e o padrao da arquitetura. O contato so e possivel quando o funcionario age voluntariamente para solicita-lo."),
                ("Tokens de notificacao e dispositivos", "Tokens FCM e dispositivos autorizados sao gerenciados por contrato. Revogacao de acesso do funcionario implica revogacao de token e desativacao do dispositivo na plataforma."),
                ("Auditoria", "Acoes institucionais, alertas governamentais, operacoes SST e operacoes administrativas devem ter rastreabilidade, usuario responsavel, data e contexto."),
                ("Incidentes", "Eventos de seguranca podem acionar processos de investigacao, mitigacao, registro, comunicacao a clientes e titulares quando aplicavel, e melhoria de controles."),
                ("Compromisso continuo", "A governanca do SolusCRT Saude e mantida como um processo permanente, com melhoria de controles, revisao de acessos, atualizacao documental e alinhamento aos requisitos aplicaveis de protecao de dados, saude digital, SST e contratos institucionais."),
            ],
        },
        "metodologia": {
            "title": "Metodologia",
            "subtitle": "Como o SolusCRT separa sinal precoce, fonte oficial, operacao setorial e decisao responsavel.",
            "sections": [
                ("Sinal colaborativo epidemiologico", "O app da populacao coleta sinais de sintomas em tempo real. Esses sinais indicam tendencia e risco territorial, mas nao equivalem a caso confirmado. Sao exibidos como camada de sinal precoce, separados de fontes oficiais e inferencias de IA."),
                ("Fonte oficial brasileira", "Dados oficiais — IBGE/SIDRA, InfoDengue, InfoGripe, OpenDataSUS/DATASUS — sao tratados separadamente, preferencialmente em agregados, com data de coleta, fonte, versao e regra de processamento. Nunca sao misturados com sinais colaborativos sem identificacao de camada."),
                ("Indicadores epidemiologicos", "A plataforma usa crescimento, incidencia por 100 mil habitantes, predominancia de sintomas, serie temporal e reducao gradual quando deixam de entrar novos sinais. Intensidade so cai apos 10 dias sem novos sinais e quando tendencia, agregados e fontes oficiais sustentam queda real."),
                ("IA como apoio epidemiologico", "Modelos de IA apoiam classificacao e priorizacao de sinais e territorios. Nao substituem equipe tecnica, vigilancia epidemiologica ou decisao institucional. Toda inferencia de IA e identificada como tal nos paineis."),
                ("Metodologia Governo - leitura territorial e governanca", "No ambiente de Governo, o radar e apresentado com foco em territorio, tendencia, intensidade, comunicacao institucional e auditoria. A decisao continua humana e vinculada aos protocolos e competencias do ente publico responsavel."),
                ("Metodologia Farmacia - demanda, giro e ruptura", "No ambiente de Farmacia, os sinais epidemiologicos sao convertidos em apoio a demanda futura, giro de itens, planejamento de compra, risco de ruptura e leitura regional de medicamentos e insumos."),
                ("Metodologia Hospital - pressao assistencial e preparo", "No ambiente Hospitalar, a plataforma cruza tendencia territorial com capacidade assistencial para apoiar leitos, triagem, internacao, equipes e resposta operacional antes do pico atingir a porta de entrada."),
                ("Metodologia SST — conformidade e ASO", "No ambiente empresarial, a plataforma rastreia vencimentos de ASO, periodicidade de exames por funcao e risco, conformidade com NRs aplicaveis e status dos eventos eSocial SST. Alertas de nao-conformidade sao gerados automaticamente com base nas regras tecnicas cadastradas, sem substituir o julgamento do profissional de saude ocupacional responsavel."),
                ("Metodologia de bem-estar — agregacao e anonimato", "Check-ins de bem-estar sao agregados por periodo, setor e indicador antes de serem exibidos para a empresa. O anonimato e preservado enquanto o numero de respondentes em um grupo for inferior ao limiar minimo configurado — grupos muito pequenos nao geram exibicao individual para proteger o funcionario. Alertas de tendencia negativa sao gerados apenas em nivel agregado."),
                ("Transparencia", "Paineis devem indicar quando um dado e colaborativo, oficial, inferido por IA, proveniente de SST ou indisponivel, evitando conclusoes falsas ou comunicacao alarmista."),
            ],
        },
        "suporte": {
            "title": "Suporte e Atendimento",
            "subtitle": "Canal institucional para suporte do app da populacao, app do funcionario, ambiente SST, privacidade e orientacoes gerais do SolusCRT Saude.",
            "sections": [
                ("Atendimento ao usuario do app da populacao", "Para suporte geral do app da populacao, dificuldades de uso, orientacoes sobre alertas, problemas de mapa ou envio de sintomas, entre em contato por comercial@soluscrt.com.br com o assunto Suporte App SolusCRT."),
                ("Atendimento ao funcionario — app do funcionario", "Para duvidas sobre acesso ao ASO digital, notificacoes, check-in de bem-estar ou funcionamento do app do funcionario, o trabalhador deve contatar o RH ou gestor SST da empresa contratante. Para problemas tecnicos nao resolvidos internamente, a empresa pode acionar o suporte institucional pelo canal abaixo."),
                ("Suporte SST e gestao empresarial", "Empresas com duvidas sobre configuracao SST, integracao eSocial, cadastro de funcionarios, NRs, EPI/EPC, PGR, postos de trabalho ou painel de conformidade podem solicitar suporte tecnico por comercial@soluscrt.com.br com o assunto Suporte SST SolusCRT."),
                ("Privacidade e dados pessoais", "Para pedidos relacionados a privacidade, esclarecimentos sobre tratamento de dados SST ou bem-estar, direitos do titular, exclusao quando aplicavel e temas de LGPD, utilize o canal comercial@soluscrt.com.br com o assunto Privacidade SolusCRT."),
                ("Suporte institucional — farmacia, hospital, governo e plano de saude", "Farmacias, hospitais, municipios, governos e operadoras de plano de saude que precisem de apoio operacional, contratual ou tecnico em seus ambientes especificos podem solicitar atendimento por comercial@soluscrt.com.br."),
                ("Escopo do atendimento", "O suporte do SolusCRT Saude atende questoes sobre plataforma, apps, acesso, alertas, SST, privacidade e funcionamento do servico. O atendimento nao substitui orientacao medica, emergencia, SAMU, hospital, UPA ou consulta clinica."),
                ("Tempo de resposta", "Solicitacoes institucionais e de suporte geral sao recebidas por canal oficial e tratadas conforme criticidade, natureza do pedido, fila operacional e disponibilidade da equipe."),
                ("Base publica de documentos", "Para revisao documental, consulte tambem a Politica de Privacidade, os Termos de Uso, a pagina de Seguranca e LGPD e a Metodologia publicadas no site institucional."),
            ],
        },
    },
    "en": {
        "privacidade": {
            "title": "Privacy Policy",
            "subtitle": "How SolusCRT Health handles data in the population app, the employee app and the Government, Pharmacy, Hospital, OSH and Health Plan environments.",
            "sections": [
                ("Who we are and scope", "SolusCRT Health is a complete health management SaaS platform, with an OSH environment for companies, pharmaceutical management, hospital management, a situation room for government, a dedicated environment for health plan operators and two apps: the population app (free and anonymous) and the employee app (linked to the company account). This policy explains data handling across all these contexts."),
                ("Summary for population app users", "In the public app, you can view the radar, map and alerts and, if you choose, voluntarily and anonymously submit symptoms. The app does not provide medical diagnosis, prescription, individual triage, emergency care or a replacement for professional consultation."),
                ("Summary for employee app users", "The employee app is linked to the contracting company account. Through it, employees access their own digital medical certificate, make requests, receive exam and training notifications and submit wellness check-ins. Wellness check-ins are anonymous by default — the company sees only aggregated data, never a name associated with an individual check-in, unless the employee voluntarily requests support contact."),
                ("Five environments, five processing contexts", "Government handles territorial indicators, alerts, audit trail and institutional operations. Pharmacy handles catalog, inventory, lots, suppliers, demand and traceability. Hospital handles triage, beds, admissions, prescriptions and care operations. OSH handles medical certificates, incident reports, exams, leave, eSocial, training and anonymous wellness. Health Plan handles beneficiary records, contracts, authorization guides, claims, reimbursements and territorial epidemiological data. The population app feeds only territorial epidemiological intelligence; the employee app belongs to the OSH environment."),
                ("Data we may process", "We may process, depending on context and environment: selected symptoms; location coordinates while the app is in use; city, state, neighborhood or approximate region; submission date and time; a random technical identifier generated by the app; IP address; FCM push notification tokens; acceptance of terms; corporate or government account data; access and audit records. In the Government environment: alerts, territorial parameters, aggregated indicators, communication history and institutional trails. In Pharmacy: item records, lots, expiration dates, inventory, purchasing, suppliers, patients when applicable and operational traceability. In Hospital: care records, triage, beds, admissions, prescriptions and internal clinical operations. In the OSH environment: medical certificates, incident reports, exam results, leave records, NR training, PPE/EPC, workstations, hazards, PGR and eSocial OSH records — all sensitive health data handled with additional controls. In wellness: anonymous check-in responses on mood, physical health, mental health, stress and job satisfaction."),
                ("Sensitive health data — OSH and wellness", "Medical certificates, incident reports, exams, leave records and any occupational health data are sensitive data under the LGPD. They are handled with minimization, specific purpose, role-based access controls, per-operation audit trail and display restricted to the authorized profile. Wellness data is anonymous by architecture: employee names are never associated with individual check-in responses in company dashboards, unless the employee explicitly consents by requesting support contact."),
                ("Why we use location", "In the population app, location is used to georeference health signals, show territorial risk, reduce fraud and display nearby alerts. In the employee app, location may be used to confirm presence at a workstation or notification context, as configured by contract. Users can control permissions in the operating system."),
                ("FCM notification tokens", "We use FCM tokens to send push notifications in the employee app (exam reminders, training, alerts) and the population app (official alerts). Tokens are stored securely, linked to the authorized device and may be revoked by the user or manager according to contract."),
                ("Purposes", "We use data to operate the platform, display local radar, create aggregated indicators, publish alerts, support territorial decisions in government, guide demand in pharmacy, anticipate care pressure in hospital, manage OSH and eSocial compliance, send employee notifications, collect and aggregate wellness check-ins, prevent abuse, protect security, fulfill contracts, comply with legal obligations and support responsible governance."),
                ("Legal basis", "Depending on context, processing may rely on consent, contract performance, compliance with legal or regulatory obligations (including OSH and eSocial), protection of life or physical safety, health protection, legitimate interest with safeguards and regular exercise of rights."),
                ("Sharing", "Contracting companies access OSH data of their own employees according to profile and contract. Wellness data is displayed only in aggregated form to the company. Governments, hospitals, pharmacies and authorized operators access information according to the contractual scope of their own environment. The platform prioritizes aggregated and territorial data where surveillance requires it and does not mix the operational base of one segment with another without explicit legal, contractual and technical grounds."),
                ("What we do not do", "We do not sell personal data for advertising, do not use app data to track users across third-party apps and websites, do not deliver medical diagnosis and do not publicly display individually identifiable reports."),
                ("Retention and disposal", "We keep data for the time necessary for operation, security, audit, contract compliance, defense of rights and legal obligations — including OSH document retention periods required by labor and social security law. Anonymized wellness data may be retained for aggregated trend analysis."),
                ("Data subject rights", "Data subjects may request information, access, correction, deletion when applicable, clarification about sharing, consent review and guidance about data processing through the official privacy channel."),
                ("Minors", "The population app is informational and should not be used by children without guidance from guardians. The employee app is intended for adult workers linked to the company contract."),
                ("Security", "We use HTTPS, environment variables for secrets, managed production database, secure cookies, CORS/CSRF restriction, session control, device limits by contract, audit trails, segregation by environment and profile and good practices to reduce unauthorized access, manipulation and unnecessary exposure. Government, pharmacy, hospital, OSH and health plan have their own access controls and operational context."),
                ("Privacy contact", "Privacy requests, data subject rights, LGPD or privacy questions and requests related to data processing may be sent to comercial@soluscrt.com.br with the subject Privacy SolusCRT."),
                ("Updates", "This policy may be updated to reflect platform improvements, new legal requirements, App Store adjustments, institutional contracts and changes to security controls."),
            ],
        },
        "termos": {
            "title": "Terms of Use",
            "subtitle": "Rules for using the population app, the employee app and the private Government, Pharmacy, Hospital, OSH and Health Plan environments.",
            "sections": [
                ("Nature of the platform", "SolusCRT Health is a health management SaaS platform with five private and independent environments: Government, Pharmacy, Hospital, OSH and Health Plan. The population app provides informational epidemiological intelligence. The employee app serves the OSH environment. None of these resources replaces medical diagnosis, prescription, individual clinical triage or emergency care."),
                ("Responsible submission in the population app", "Users should submit real symptoms, in good faith and only when related to their current condition. Repeated, automated or fraudulent submissions may be filtered or blocked."),
                ("Employee app — proper use", "The employee app is for exclusive use by workers linked to the company contract. It is prohibited to share credentials, access other employees' data without authorization or use the app for purposes unrelated to occupational health management and wellness."),
                ("Wellness — voluntary submission", "Wellness check-ins are voluntary. The employee is not required to respond and may omit any field. The company sees only aggregated data. The employee explicitly consents when requesting support contact."),
                ("Responsibility for customer data", "Each contracting customer is responsible for the accuracy, lawfulness and currency of the data entered into its own environment. In OSH, this includes medical certificates, incident reports, exams, leave and eSocial OSH records. In Pharmacy and Hospital, it includes records, inventory, care operations and internal data. In Government, it includes settings, alerts and institutional flows published by authorized operators."),
                ("Free trial period and subscriptions", "The free trial period lasts 15 calendar days from activation, with no credit card required, for private environments where this offer is active. At the end of the trial period, without an active subscription, access is automatically suspended and data may be retained for an additional period according to the retention policy. There is no automatic charge after the trial."),
                ("Private environments", "OSH, pharmacy, hospital, government, health plan and administrative access is exclusive to clients and authorized operators. Unauthorized access attempts may be recorded and blocked."),
                ("Prohibited use", "It is forbidden to bypass security controls, automate improper submissions, insert false information in OSH or wellness data, access contractual areas without authorization, reverse engineer the platform or use it for illegal, discriminatory or abusive purposes."),
                ("Accounts and credentials", "Credentials are personal or institutional according to contract. The user or client is responsible for protecting passwords, authorized devices and internal access policies."),
                ("Availability", "The platform depends on internet access, cloud services, APIs, official sources and location permission. Temporary unavailability or degradation of external data may occur."),
                ("Decision responsibility", "Operational, clinical and institutional decisions must consider technical context, human validation and applicable public health and occupational health protocols."),
                ("Intellectual property", "Brands, interfaces, models, platform organization, documents, code, dashboards and SolusCRT Health materials belong to their owners and are licensed only within contracted limits."),
                ("B2B and B2G contracting", "Private subscriptions, trials, implementation, expansion by unit or network, user limits, devices, support, integrations, SLA and pricing may be defined in proposal, contract, order form or specific instrument. Government and institutional contracts may follow their own B2G rules."),
            ],
        },
        "seguranca-lgpd": {
            "title": "Security, LGPD and Governance",
            "subtitle": "Controls to protect data, access and institutional trust across all platform environments.",
            "sections": [
                ("Principles", "The platform should follow purpose limitation, adequacy, necessity, security, prevention, transparency and accountability in the processing of personal data, with special attention to sensitive health data present in the OSH and Health Plan environments."),
                ("Environment segregation", "OSH/Company, pharmacy, hospital, government and health plan are separate environments with distinct login flows, permissions, sessions, audit trails and domain/subdomain when contracted. Data from one environment is not accessible to others without explicit authorization."),
                ("Epidemiological anti-fraud controls", "The population app and backend use device, network, repetition, signal quality and current location controls to reduce hotspot manipulation. Epidemiological intensity only decreases after 10 days without new signals and when time series, aggregates and official sources support a real decline."),
                ("Government, pharmacy, hospital and health plan data", "The epidemiological and operational environments treat different scopes: government receives territorial reading and governance; pharmacy receives stock, lots and demand data; hospital receives care and capacity data; health plan receives beneficiary records, authorization guides, claims, reimbursements and territorial epidemiological data. Each environment has its own trails, profiles and authorizations."),
                ("Access protection", "The platform adopts session control, role-based authorization, contracted device limits, simultaneous-use blocking when applicable and access revocation."),
                ("OSH data — sensitive health data", "Medical certificates, incident reports, exams, results and leave records are sensitive data handled with minimization, access restricted to authorized professional profiles, per-operation audit trail and display appropriate to the contractual context."),
                ("Wellness — anonymity by architecture", "Wellness check-ins never associate an employee's name with an individual response in company dashboards. Anonymity is the architectural default. Contact is only possible when the employee voluntarily acts to request it."),
                ("Notification tokens and devices", "FCM tokens and authorized devices are managed by contract. Revoking an employee's access implies token revocation and device deactivation on the platform."),
                ("Audit", "Institutional actions, government alerts, OSH operations and administrative operations should have traceability, responsible user, date and context."),
                ("Incidents", "Security events may trigger investigation, mitigation, recordkeeping, communication to clients and data subjects when applicable, and improvement of controls."),
                ("Continuous commitment", "SolusCRT Health governance is maintained as an ongoing process, with control improvement, access review, documentation updates and alignment with applicable data protection, digital health, OSH and institutional contract requirements."),
            ],
        },
        "metodologia": {
            "title": "Methodology",
            "subtitle": "How SolusCRT separates early signal, official source, sector operation and responsible decision-making.",
            "sections": [
                ("Epidemiological collaborative signal", "The population app collects symptom signals in real time. These signals indicate trend and territorial risk, but they are not confirmed cases. They are displayed as an early signal layer, separated from official sources and AI inferences."),
                ("Official Brazilian source", "Official data — IBGE/SIDRA, InfoDengue, InfoGripe, OpenDataSUS/DATASUS — are handled separately, preferably in aggregated form, with collection date, source, version and processing rule. They are never mixed with collaborative signals without layer identification."),
                ("Epidemiological indicators", "The platform uses growth, incidence per 100,000 inhabitants, symptom predominance, time series and gradual decline when no new signals are received. Intensity only decreases after 10 days without new signals and when trend, aggregates and official sources support a real decline."),
                ("AI as epidemiological support", "AI models support classification and prioritization of signals and territories. They do not replace technical teams, epidemiological surveillance or institutional decision-making. Every AI inference is identified as such in dashboards."),
                ("Government methodology - territorial reading and governance", "In the Government environment, the radar is presented with a focus on territory, trend, intensity, institutional communication and audit trail. The decision remains human and linked to the protocols and powers of the responsible public authority."),
                ("Pharmacy methodology - demand, turnover and shortage", "In the Pharmacy environment, epidemiological signals are converted into support for future demand, item turnover, purchasing planning, shortage risk and regional reading of medicines and supplies."),
                ("Hospital methodology - care pressure and readiness", "In the Hospital environment, the platform crosses territorial trend with care capacity to support beds, triage, admissions, teams and operational response before the peak reaches the front door."),
                ("OSH methodology — compliance and medical certificates", "In the company environment, the platform tracks medical certificate expiration, exam frequency by role and risk, compliance with applicable NRs and eSocial OSH event status. Non-compliance alerts are generated automatically based on configured technical rules, without replacing the judgment of the responsible occupational health professional."),
                ("Wellness methodology — aggregation and anonymity", "Wellness check-ins are aggregated by period, sector and indicator before being displayed to the company. Anonymity is preserved when the number of respondents in a group falls below the configured minimum threshold — very small groups do not generate individual display to protect the employee. Negative trend alerts are generated only at the aggregate level."),
                ("Transparency", "Dashboards should indicate when data is collaborative, official, AI-inferred, from OSH or unavailable, avoiding false conclusions or alarmist communication."),
            ],
        },
        "suporte": {
            "title": "Support and Service",
            "subtitle": "Institutional channel for population app support, employee app support, OSH environment, privacy and general SolusCRT Health guidance.",
            "sections": [
                ("Population app user support", "For general population app support, difficulty using the app, guidance about alerts, map issues or symptom submission, contact comercial@soluscrt.com.br with the subject SolusCRT App Support."),
                ("Employee app support", "For questions about accessing the digital medical certificate, notifications, wellness check-ins or employee app operation, workers should contact their company's HR or OSH manager. For unresolved technical issues, the company may contact institutional support through the channel below."),
                ("OSH and company management support", "Companies with questions about OSH configuration, eSocial integration, employee records, NR compliance, PPE/EPC, PGR, workstations or compliance dashboards may request technical support at comercial@soluscrt.com.br with the subject SolusCRT OSH Support."),
                ("Privacy and personal data", "For privacy requests, clarification about OSH or wellness data processing, data subject rights, deletion when applicable and LGPD matters, use comercial@soluscrt.com.br with the subject Privacy SolusCRT."),
                ("Institutional support — pharmacy, hospital, government and health plan", "Pharmacies, hospitals, municipalities, governments and health plan operators that need operational, contractual or technical support in their specific environments may contact comercial@soluscrt.com.br."),
                ("Scope of support", "SolusCRT Health support covers questions about the platform, apps, access, alerts, OSH, privacy and service operation. Support does not replace medical guidance, emergency care, ambulance services, hospital, urgent care unit or clinical consultation."),
                ("Response time", "Institutional and general support requests are received through the official channel and handled according to criticality, request type, operational queue and team availability."),
                ("Public document base", "For document review, also consult the Privacy Policy, Terms of Use, Security and LGPD page and Methodology published on the institutional website."),
            ],
        },
    },
    "es": {
        "privacidade": {
            "title": "Politica de Privacidad",
            "subtitle": "Como SolusCRT Salud trata datos en la app poblacional, la app del trabajador y en los ambientes de Gobierno, Farmacia, Hospital, SST y Plan de Salud.",
            "sections": [
                ("Quienes somos y alcance", "SolusCRT Salud es una plataforma SaaS completa de gestion en salud, con ambiente SST para empresas, gestion farmaceutica, gestion hospitalaria, sala de situacion para gobierno, ambiente dedicado para operadoras de plan de salud y dos apps: la app poblacional (gratuita y anonima) y la app del trabajador (vinculada a la cuenta empresarial). Esta politica explica el tratamiento de datos en todos estos contextos."),
                ("Resumen para usuarios de la app poblacional", "En la app publica, puedes consultar radar, mapa y alertas y, si lo deseas, enviar sintomas de forma voluntaria y anonima. La app no ofrece diagnostico medico, prescripcion, triaje individual, atencion de emergencia ni sustitucion de una consulta profesional."),
                ("Resumen para usuarios de la app del trabajador", "La app del trabajador esta vinculada a la cuenta de la empresa contratante. A traves de ella, el trabajador accede a su certificado medico digital, realiza solicitudes, recibe notificaciones de examenes y capacitaciones y envia check-ins de bienestar. Los check-ins de bienestar son anonimos por defecto — la empresa ve solo datos agregados, nunca el nombre asociado a un check-in individual, salvo cuando el propio trabajador solicita voluntariamente contacto de apoyo."),
                ("Cinco ambientes, cinco contextos de tratamiento", "Gobierno trata indicadores territoriales, alertas, auditoria y operacion institucional. Farmacia trata catalogo, inventario, lotes, proveedores, demanda y trazabilidad. Hospital trata triaje, camas, internaciones, prescripciones y operacion asistencial. SST trata certificados medicos, accidentes, examenes, ausencias, eSocial, capacitaciones y bienestar anonimo. Plan de Salud trata beneficiarios, contratos, guias de autorizacion, siniestros, reembolsos y datos epidemiologicos territoriales. La app poblacional alimenta solo la inteligencia epidemiologica territorial; la app del trabajador pertenece al ambiente SST."),
                ("Datos que podemos tratar", "Podemos tratar, segun el contexto y el ambiente: sintomas seleccionados; coordenadas de ubicacion mientras la app esta en uso; ciudad, estado, barrio o region aproximada; fecha y hora del envio; identificador tecnico aleatorio generado por la app; IP; tokens FCM de notificacion push; aceptacion de terminos; datos de cuenta corporativa o gubernamental; registros de acceso y auditoria. En el ambiente de Gobierno: alertas, parametros territoriales, indicadores agregados, historial de comunicacion y trazas institucionales. En Farmacia: registros de items, lotes, vencimientos, inventario, compras, proveedores, pacientes cuando corresponda y trazabilidad operativa. En Hospital: registros asistenciales, triaje, camas, internaciones, prescripciones y operacion clinica interna. En el ambiente SST: certificados medicos, registros de accidente, resultados de examenes, ausencias, capacitaciones NR, EPI/EPC, puestos de trabajo, riesgos, PGR y registros eSocial SST — todos datos de salud sensibles tratados con controles adicionales. En bienestar: respuestas anonimas de check-in de humor, salud fisica, salud mental, estres y satisfaccion laboral."),
                ("Datos sensibles de salud — SST y bienestar", "Los certificados medicos, registros de accidente, examenes, ausencias y cualquier dato de salud ocupacional son datos sensibles segun la LGPD. Se tratan con minimizacion, finalidad especifica, controles de acceso por perfil, auditoria por operacion y visualizacion restringida al perfil autorizado. Los datos de bienestar son anonimos por arquitectura: el nombre del trabajador nunca se asocia a una respuesta individual de check-in en los paneles de la empresa, salvo cuando el trabajador consiente explicitamente al solicitar contacto de apoyo."),
                ("Por que usamos ubicacion", "En la app poblacional, la ubicacion se usa para georreferenciar senales de salud, mostrar riesgo territorial, reducir fraude y mostrar alertas cercanas. En la app del trabajador, la ubicacion puede usarse para confirmar presencia en un puesto de trabajo o contexto de notificacion, segun la configuracion del contrato. El usuario puede controlar permisos en el sistema operativo."),
                ("Tokens de notificacion FCM", "Usamos tokens FCM para enviar notificaciones push en la app del trabajador (recordatorios de examen, capacitacion, alertas) y en la app poblacional (alertas oficiales). Los tokens se almacenan de forma segura, vinculados al dispositivo autorizado y pueden ser revocados por el usuario o el gestor segun contrato."),
                ("Finalidades", "Usamos los datos para operar la plataforma, mostrar radar local, formar indicadores agregados, publicar alertas, apoyar decision territorial en gobierno, orientar demanda en farmacia, anticipar presion asistencial en hospital, gestionar SST y conformidad eSocial, enviar notificaciones al trabajador, recoger y agregar check-ins de bienestar, prevenir abuso, proteger la seguridad, cumplir contratos, atender obligaciones legales y apoyar una gobernanza responsable."),
                ("Base legal", "Segun el contexto, el tratamiento puede apoyarse en consentimiento, ejecucion de contrato, cumplimiento de obligacion legal o regulatoria (incluido SST y eSocial), proteccion de la vida o integridad fisica, tutela de la salud, interes legitimo con salvaguardas y ejercicio regular de derechos."),
                ("Compartir informacion", "Las empresas contratantes acceden a datos SST de sus propios trabajadores segun perfil y contrato. Los datos de bienestar se muestran solo de forma agregada a la empresa. Gobiernos, hospitales, farmacias y operadores autorizados acceden a informacion segun el alcance contractual de su propio ambiente. La plataforma prioriza datos agregados y territoriales cuando la vigilancia lo exige y no mezcla la base operativa de un segmento con otra sin base legal, contractual y tecnica explicita."),
                ("Lo que no hacemos", "No vendemos datos personales para publicidad, no usamos datos de la app para rastrear usuarios entre apps y sitios de terceros, no entregamos diagnostico medico y no mostramos publicamente relatos individuales identificables."),
                ("Retencion y descarte", "Mantenemos datos durante el tiempo necesario para operacion, seguridad, auditoria, cumplimiento contractual, defensa de derechos y obligaciones legales — incluyendo plazos de retencion de documentos SST exigidos por la legislacion laboral y de seguridad social. Los datos de bienestar anonimizados pueden mantenerse para analisis de tendencias agregadas."),
                ("Derechos del titular", "Los titulares pueden solicitar informacion, acceso, correccion, eliminacion cuando corresponda, aclaraciones sobre intercambio, revision de consentimiento y orientacion sobre tratamiento de datos por el canal oficial de privacidad."),
                ("Menores de edad", "La app poblacional es informativa y no debe ser usada por ninos sin orientacion de responsables. La app del trabajador esta destinada a trabajadores mayores de edad vinculados al contrato empresarial."),
                ("Seguridad", "Usamos HTTPS, variables de entorno para secretos, base de datos gestionada en produccion, cookies seguras, restriccion CORS/CSRF, control de sesion, limite de dispositivos por contrato, trazas de auditoria, segregacion por ambiente y perfil y buenas practicas para reducir acceso indebido, manipulacion y exposicion innecesaria. Gobierno, farmacia, hospital, SST y plan de salud tienen controles de acceso y contexto operativo propios."),
                ("Contacto de privacidad", "Pedidos de privacidad, derechos del titular, dudas sobre LGPD o privacidad y solicitudes relacionadas con tratamiento de datos pueden enviarse a comercial@soluscrt.com.br con el asunto Privacidad SolusCRT."),
                ("Actualizaciones", "Esta politica puede actualizarse para reflejar mejoras de la plataforma, nuevas exigencias legales, ajustes de App Store, contratos institucionales y cambios en controles de seguridad."),
            ],
        },
        "termos": {
            "title": "Terminos de Uso",
            "subtitle": "Reglas de uso de la app poblacional, la app del trabajador y de los ambientes privados de Gobierno, Farmacia, Hospital, SST y Plan de Salud.",
            "sections": [
                ("Naturaleza de la plataforma", "SolusCRT Salud es una plataforma SaaS de gestion en salud con cinco ambientes privados e independientes: Gobierno, Farmacia, Hospital, SST y Plan de Salud. La app poblacional ofrece inteligencia epidemiologica informativa. La app del trabajador sirve al ambiente SST. Ningun recurso sustituye diagnostico medico, prescripcion, triaje clinico individual ni atencion de emergencia."),
                ("Envio responsable en la app poblacional", "Los usuarios deben enviar sintomas reales, de buena fe y solo cuando tengan relacion con su condicion actual. Envios repetidos, automatizados o fraudulentos pueden ser filtrados o bloqueados."),
                ("App del trabajador — uso adecuado", "La app del trabajador es de uso exclusivo del trabajador vinculado al contrato de la empresa. Esta prohibido compartir credenciales, acceder a datos de otros trabajadores sin autorizacion o usar la app para fines ajenos a la gestion de salud ocupacional y bienestar."),
                ("Bienestar — envio voluntario", "Los check-ins de bienestar son voluntarios. El trabajador no esta obligado a responder y puede omitir cualquier campo. La empresa ve solo datos agregados. El trabajador consiente explicitamente al solicitar contacto de apoyo."),
                ("Responsabilidad por datos del contratante", "Cada cliente contratante es responsable de la exactitud, licitud y actualizacion de los datos ingresados en su propio ambiente. En SST, esto incluye certificados medicos, accidentes, examenes, ausencias y registros eSocial SST. En Farmacia y Hospital, incluye registros, inventario, operacion asistencial y datos internos. En Gobierno, incluye configuraciones, alertas y flujos institucionales publicados por operadores autorizados."),
                ("Periodo de prueba gratuito y suscripciones", "El periodo de prueba gratuito tiene una duracion de 15 dias corridos desde la activacion, sin necesidad de tarjeta de credito, para los ambientes privados donde esta oferta este activa. Al terminar el periodo de prueba, sin suscripcion activa, el acceso se suspende automaticamente y los datos pueden retenerse por un periodo adicional segun la politica de retencion. No hay cobro automatico despues de la prueba."),
                ("Ambientes privados", "Los accesos de SST, farmacia, hospital, gobierno, plan de salud y administracion son exclusivos para clientes y operadores autorizados. Intentos de acceso indebido pueden registrarse y bloquearse."),
                ("Uso prohibido", "Esta prohibido burlar controles de seguridad, automatizar envios indebidos, insertar informacion falsa en datos SST o de bienestar, acceder a areas contractuales sin autorizacion, hacer ingenieria inversa o usar la plataforma con finalidad ilegal, discriminatoria o abusiva."),
                ("Cuentas y credenciales", "Las credenciales son personales o institucionales segun contrato. El usuario o cliente es responsable de preservar contrasenas, dispositivos autorizados y politicas internas de acceso."),
                ("Disponibilidad", "La plataforma depende de internet, servicios de nube, APIs, fuentes oficiales y permiso de ubicacion. Pueden ocurrir indisponibilidades temporales o degradacion de datos externos."),
                ("Responsabilidad de decision", "Las decisiones operativas, clinicas e institucionales deben considerar contexto tecnico, validacion humana y protocolos aplicables de salud publica y salud ocupacional."),
                ("Propiedad intelectual", "Marcas, interfaces, modelos, organizacion de la plataforma, documentos, codigos, paneles y materiales de SolusCRT Salud pertenecen a sus titulares y se licencian dentro de los limites contratados."),
                ("Contratacion B2B y B2G", "Suscripciones privadas, prueba, implantacion, expansion por unidad o red, limites de usuarios, dispositivos, soporte, integraciones, SLA y valores pueden definirse en propuesta, contrato, termino de adhesion o instrumento especifico. Los contratos gubernamentales e institucionales pueden seguir sus propias reglas B2G."),
            ],
        },
        "seguranca-lgpd": {
            "title": "Seguridad, LGPD y Gobernanza",
            "subtitle": "Controles para proteger datos, accesos y confianza institucional en todos los ambientes de la plataforma.",
            "sections": [
                ("Principios", "La plataforma debe seguir finalidad, adecuacion, necesidad, seguridad, prevencion, transparencia y responsabilizacion en el tratamiento de datos personales, con especial atencion a los datos sensibles de salud presentes en el ambiente SST."),
                ("Segregacion de ambientes", "SST/Empresa, farmacia, hospital y gobierno son ambientes separados con flujos de login, permisos, sesiones, auditoria y dominio/subdominio distintos cuando sea contratado. Los datos de un ambiente no son accesibles a otros sin autorizacion explicita."),
                ("Controles antifraude epidemiologicos", "La app poblacional y el backend utilizan controles por dispositivo, red, repeticion, calidad de la senal y ubicacion actual para reducir manipulacion de focos. La intensidad epidemiologica solo baja tras 10 dias sin nuevas senales y cuando serie temporal, agregados y fuentes oficiales sostienen una reduccion real."),
                ("Datos de gobierno, farmacia y hospital", "Los ambientes epidemiologicos y operativos tratan alcances distintos: gobierno recibe lectura territorial y gobernanza; farmacia recibe datos de stock, lotes y demanda; hospital recibe datos asistenciales y de capacidad. Cada ambiente tiene sus propias trazas, perfiles y autorizaciones."),
                ("Proteccion de acceso", "La plataforma adopta control de sesion, autorizacion por perfil, limite de dispositivos contratados, bloqueos de uso simultaneo cuando corresponda y revocacion de accesos."),
                ("Datos SST — datos sensibles de salud", "Certificados medicos, registros de accidente, examenes, resultados y ausencias son datos sensibles tratados con minimizacion, acceso restringido a perfiles profesionales autorizados, auditoria por operacion y visualizacion adecuada al contexto contractual."),
                ("Bienestar — anonimato por arquitectura", "Los check-ins de bienestar nunca asocian el nombre del trabajador a una respuesta individual en los paneles de la empresa. El anonimato es el estandar de la arquitectura. El contacto solo es posible cuando el trabajador actua voluntariamente para solicitarlo."),
                ("Tokens de notificacion y dispositivos", "Los tokens FCM y dispositivos autorizados se gestionan por contrato. La revocacion del acceso del trabajador implica revocacion del token y desactivacion del dispositivo en la plataforma."),
                ("Auditoria", "Acciones institucionales, alertas gubernamentales, operaciones SST y operaciones administrativas deben tener trazabilidad, usuario responsable, fecha y contexto."),
                ("Incidentes", "Eventos de seguridad pueden activar investigacion, mitigacion, registro, comunicacion a clientes y titulares cuando corresponda, y mejora de controles."),
                ("Compromiso continuo", "La gobernanza de SolusCRT Salud se mantiene como un proceso permanente, con mejora de controles, revision de accesos, actualizacion documental y alineacion con requisitos aplicables de proteccion de datos, salud digital, SST y contratos institucionales."),
            ],
        },
        "metodologia": {
            "title": "Metodologia",
            "subtitle": "Como SolusCRT separa senal temprana, fuente oficial, operacion sectorial y decision responsable.",
            "sections": [
                ("Senal colaborativa epidemiologica", "La app poblacional recopila senales de sintomas en tiempo real. Estas senales indican tendencia y riesgo territorial, pero no equivalen a caso confirmado. Se muestran como capa de senal temprana, separadas de fuentes oficiales e inferencias de IA."),
                ("Fuente oficial brasilena", "Datos oficiales — IBGE/SIDRA, InfoDengue, InfoGripe, OpenDataSUS/DATASUS — se tratan por separado, preferentemente en agregados, con fecha de recoleccion, fuente, version y regla de procesamiento. Nunca se mezclan con senales colaborativas sin identificacion de capa."),
                ("Indicadores epidemiologicos", "La plataforma usa crecimiento, incidencia por 100 mil habitantes, predominancia de sintomas, serie temporal y reduccion gradual cuando dejan de entrar nuevas senales. La intensidad solo baja tras 10 dias sin nuevas senales y cuando tendencia, agregados y fuentes oficiales sostienen una reduccion real."),
                ("IA como apoyo epidemiologico", "Modelos de IA apoyan clasificacion y priorizacion de senales y territorios. No sustituyen al equipo tecnico, la vigilancia epidemiologica ni la decision institucional. Toda inferencia de IA se identifica como tal en los paneles."),
                ("Metodologia Gobierno - lectura territorial y gobernanza", "En el ambiente de Gobierno, el radar se presenta con foco en territorio, tendencia, intensidad, comunicacion institucional y auditoria. La decision sigue siendo humana y vinculada a los protocolos y competencias del ente publico responsable."),
                ("Metodologia Farmacia - demanda, rotacion y quiebre", "En el ambiente de Farmacia, las senales epidemiologicas se convierten en apoyo a la demanda futura, rotacion de items, planificacion de compra, riesgo de quiebre y lectura regional de medicamentos e insumos."),
                ("Metodologia Hospital - presion asistencial y preparacion", "En el ambiente Hospitalario, la plataforma cruza tendencia territorial con capacidad asistencial para apoyar camas, triaje, internaciones, equipos y respuesta operativa antes de que el pico llegue a la puerta de entrada."),
                ("Metodologia SST — conformidad y certificados", "En el ambiente empresarial, la plataforma rastrea vencimientos de certificados medicos, periodicidad de examenes por funcion y riesgo, conformidad con NRs aplicables y estado de los eventos eSocial SST. Las alertas de no conformidad se generan automaticamente segun las reglas tecnicas configuradas, sin sustituir el juicio del profesional de salud ocupacional responsable."),
                ("Metodologia de bienestar — agregacion y anonimato", "Los check-ins de bienestar se agregan por periodo, sector e indicador antes de mostrarse a la empresa. El anonimato se preserva cuando el numero de respondientes en un grupo es inferior al umbral minimo configurado — grupos muy pequenos no generan visualizacion individual para proteger al trabajador. Las alertas de tendencia negativa se generan solo a nivel agregado."),
                ("Transparencia", "Los paneles deben indicar cuando un dato es colaborativo, oficial, inferido por IA, proveniente de SST o no disponible, evitando conclusiones falsas o comunicacion alarmista."),
            ],
        },
        "suporte": {
            "title": "Soporte y Atencion",
            "subtitle": "Canal institucional para soporte de la app poblacional, app del trabajador, ambiente SST, privacidad y orientaciones generales de SolusCRT Salud.",
            "sections": [
                ("Atencion al usuario de la app poblacional", "Para soporte general de la app poblacional, dificultades de uso, orientaciones sobre alertas, problemas de mapa o envio de sintomas, contacta comercial@soluscrt.com.br con el asunto Soporte App SolusCRT."),
                ("Soporte al trabajador — app del trabajador", "Para dudas sobre acceso al certificado medico digital, notificaciones, check-in de bienestar o funcionamiento de la app del trabajador, el trabajador debe contactar al departamento de RRHH o al gestor SST de la empresa contratante. Para problemas tecnicos no resueltos internamente, la empresa puede activar el soporte institucional por el canal indicado abajo."),
                ("Soporte SST y gestion empresarial", "Empresas con dudas sobre configuracion SST, integracion eSocial, registro de trabajadores, NRs, EPI/EPC, PGR, puestos de trabajo o panel de conformidad pueden solicitar soporte tecnico a comercial@soluscrt.com.br con el asunto Soporte SST SolusCRT."),
                ("Privacidad y datos personales", "Para pedidos relacionados con privacidad, aclaraciones sobre tratamiento de datos SST o bienestar, derechos del titular, eliminacion cuando corresponda y temas de LGPD, usa comercial@soluscrt.com.br con el asunto Privacidad SolusCRT."),
                ("Soporte institucional — farmacia, hospital, gobierno y plan de salud", "Farmacias, hospitales, municipios, gobiernos y operadoras de plan de salud que necesiten apoyo operativo, contractual o tecnico en sus ambientes especificos pueden contactar comercial@soluscrt.com.br."),
                ("Alcance de atencion", "El soporte de SolusCRT Salud atiende cuestiones sobre plataforma, apps, acceso, alertas, SST, privacidad y funcionamiento del servicio. La atencion no sustituye orientacion medica, emergencia, ambulancia, hospital, unidad de urgencia o consulta clinica."),
                ("Tiempo de respuesta", "Solicitudes institucionales y de soporte general se reciben por canal oficial y se tratan segun criticidad, naturaleza del pedido, fila operacional y disponibilidad del equipo."),
                ("Base publica de documentos", "Para revision documental, consulta tambien la Politica de Privacidad, los Terminos de Uso, la pagina de Seguridad y LGPD y la Metodologia publicadas en el sitio institucional."),
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
    "AP": "Amapá",
    "AM": "Amazonas",
    "BA": "Bahia",
    "CE": "Ceará",
    "DF": "Distrito Federal",
    "ES": "Espírito Santo",
    "GO": "Goiás",
    "MA": "Maranhão",
    "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais",
    "PA": "Pará",
    "PB": "Paraíba",
    "PR": "Paraná",
    "PE": "Pernambuco",
    "PI": "Piauí",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul",
    "RO": "Rondônia",
    "RR": "Roraima",
    "SC": "Santa Catarina",
    "SP": "São Paulo",
    "SE": "Sergipe",
    "TO": "Tocantins",
}


def _uf_sigla(estado):
    """Converte um nome de estado em sigla UF. Aceita já-sigla ou nome completo."""
    import unicodedata
    raw = (estado or "").strip()
    if not raw:
        return ""
    if len(raw) == 2 and raw.upper() in STATE_ALIASES:
        return raw.upper()

    def _norm(s):
        return "".join(
            ch for ch in unicodedata.normalize("NFD", (s or "").lower())
            if unicodedata.category(ch) != "Mn"
        ).strip()

    alvo = _norm(raw)
    for uf, nome in STATE_ALIASES.items():
        if _norm(nome) == alvo:
            return uf
    return raw[:2].upper()


def _state_terms(value):
    import unicodedata

    def _normalize_term(term):
        base = (term or "").strip()
        if not base:
            return ""
        return "".join(
            ch for ch in unicodedata.normalize("NFD", base.lower())
            if unicodedata.category(ch) != "Mn"
        )

    raw = (value or "").strip()
    if not raw:
        return []
    upper = raw.upper()
    normalized_raw = _normalize_term(raw)
    terms = {raw, upper}
    alias = STATE_ALIASES.get(upper)
    if alias:
        terms.add(alias)
        terms.add(_normalize_term(alias).title())
    for uf, name in STATE_ALIASES.items():
        if normalized_raw == _normalize_term(name):
            terms.add(uf)
            terms.add(name)
            terms.add(_normalize_term(name).title())
    return list(terms)


JANELA_ESTABILIDADE_FOCO_DIAS = 10
JANELA_DECAIMENTO_FOCO_DIAS = 30
PESO_MINIMO_FOCO_PUBLICO = 0.1

_UF_PARA_NOME = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo",
    "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina",
    "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}


def _normalizar_estado(estado: str | None) -> str | None:
    if not estado:
        return estado
    uf = estado.strip().upper()
    if len(uf) == 2 and uf in _UF_PARA_NOME:
        return _UF_PARA_NOME[uf]
    return estado


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
    janela_7d = agora - timedelta(days=7)
    janela_1h = agora - timedelta(hours=1)
    dados = dados or {}

    # Regra principal: 1 envio por aparelho em 7 dias, sem excecao por sintoma.
    # Qualquer variacao de sintoma do mesmo device é bloqueada igualmente —
    # isso impede que um atacante envie N vezes trocando um campo bool.
    if device_id:
        ja_enviou = RegistroSintoma.objects.filter(
            empresa=empresa,
            device_id=device_id,
            data_registro__gte=janela_7d,
        ).exists()
        if ja_enviou:
            return False, "Voce ja contribuiu com um relato nos ultimos 7 dias. Um envio por semana e suficiente para o monitoramento."

    if ip:
        # IP so bloqueia em volumes altissimos (redes NAT/CGNAT compartilham IP).
        envios_ip_1h = RegistroSintoma.objects.filter(
            empresa=empresa,
            ip=ip,
            data_registro__gte=janela_1h,
        ).count()
        if envios_ip_1h >= 60:
            return False, "Volume recente alto nesta rede. Tente novamente mais tarde."

        envios_ip_7d = RegistroSintoma.objects.filter(
            empresa=empresa,
            ip=ip,
            data_registro__gte=janela_7d,
        ).count()
        if envios_ip_7d >= 180:
            return False, "Limite semanal de envios desta rede atingido."

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
            "titulo": "Momento de cautela reforçada",
            "resumo": "Reduza exposição desnecessária, acompanhe sinais respiratórios ou febris e procure atendimento se houver piora.",
            "acoes": [
                "Evite exposições prolongadas em locais fechados e muito cheios.",
                "Acompanhe febre persistente, falta de ar ou agravamento rápido.",
                "Busque avaliação profissional diante de sinais de alerta.",
            ],
        }
    if nivel == "moderado":
        return {
            "titulo": "Atenção preventiva na região",
            "resumo": "Há crescimento relevante de sinais locais. Mantenha observação ativa da sua saúde e das pessoas próximas.",
            "acoes": [
                "Observe evolução de sintomas nas próximas 24 a 48 horas.",
                "Reforce medidas básicas de higiene e ventilação.",
                "Se houver pessoas vulneráveis em casa, redobre a atenção.",
            ],
        }
    if nivel == "atencao":
        return {
            "titulo": "Sinais em observação",
            "resumo": "O território apresenta variação acima do habitual, mas ainda sem pressão alta.",
            "acoes": [
                "Monitore como os sintomas evoluem ao longo do dia.",
                "Evite automedicação inadequada.",
                "Consulte orientação profissional se o quadro persistir.",
            ],
        }
    grupo = grupo_top or "monitoramento geral"
    return {
        "titulo": "Cenário estável no momento",
        "resumo": f"A região segue em observação pública, com predomínio recente de {grupo.lower()}.",
        "acoes": [
            "Mantenha cuidados básicos de saúde e hidratação.",
            "Use o app para acompanhar mudanças no seu território.",
            "Se surgirem sintomas, registre apenas uma vez por período.",
        ],
    }


def _alerta_publico(nivel, crescimento, grupo_top=None):
    if nivel == "alto":
        return {
            "titulo": "Alerta elevado na sua área",
            "mensagem": f"Crescimento de {crescimento}% com concentração relevante de sinais recentes.",
            "gravidade": "critica",
        }
    if nivel == "moderado":
        return {
            "titulo": "Atenção reforçada para a sua área",
            "mensagem": f"A região apresenta crescimento de {crescimento}% e exige observação preventiva.",
            "gravidade": "alta",
        }
    if nivel == "atencao":
        return {
            "titulo": "Mudança detectada no território",
            "mensagem": "Há oscilação de sinais locais. Continue acompanhando o radar da sua região.",
            "gravidade": "moderada",
        }
    grupo = grupo_top or "sinais gerais"
    return {
        "titulo": "Situação sob controle",
        "mensagem": f"Não há alerta elevado no momento. O principal sinal recente é {grupo.lower()}.",
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

    # 🧠 classificação bayesiana — passa estado para prior geográfico
    dados_classificacao = {**dados, "estado": geo.get("estado", ""), "cidade": geo.get("cidade", "")}
    grupo, classificacao = classificar_padrao(dados_classificacao, setor="governo")
    resultado_cidadao = _classificar_cidadao(dados_classificacao, estado=geo.get("estado", ""))
    confianca, motivos_suspeita, ip, device_id = _score_suspeita(empresa, request, dados)

    if confianca <= 0.3:
        return JsonResponse({
            "erro": "envio bloqueado por protecao antifraude",
            "motivos": motivos_suspeita,
        }, status=429)

    # 💾 salvar
    RegistroSintoma.objects.create(
        id_anonimo=uuid.uuid4(),
        # Sintomas base
        febre=bool(dados.get("febre", False)),
        tosse=bool(dados.get("tosse", False)),
        dor_corpo=bool(dados.get("dor_corpo", False)),
        cansaco=bool(dados.get("cansaco", False)),
        falta_ar=bool(dados.get("falta_ar", False)),
        # Sintomas expandidos (IA 2.0)
        dor_cabeca=bool(dados.get("dor_cabeca", False)),
        dor_articular=bool(dados.get("dor_articular", False)),
        exantema=bool(dados.get("exantema", False)),
        conjuntivite=bool(dados.get("conjuntivite", False)),
        vomito_nausea=bool(dados.get("vomito_nausea", False)),
        diarreia=bool(dados.get("diarreia", False)),
        dor_abdominal=bool(dados.get("dor_abdominal", False)),
        rigidez_nuca=bool(dados.get("rigidez_nuca", False)),
        ictericia=bool(dados.get("ictericia", False)),
        manchas_hemorragicas=bool(dados.get("manchas_hemorragicas", False)),
        perda_olfato_paladar=bool(dados.get("perda_olfato_paladar", False)),
        dor_garganta=bool(dados.get("dor_garganta", False)),
        coriza=bool(dados.get("coriza", False)),
        calafrios=bool(dados.get("calafrios", False)),
        sudorese=bool(dados.get("sudorese", False)),
        intensidade_febre=dados.get("intensidade_febre", ""),
        intensidade_articular=dados.get("intensidade_articular", ""),
        # Anamnese epidemiológica
        dias_sintomas=dados.get("dias_sintomas"),
        inicio_abrupto=dados.get("inicio_abrupto"),
        viagem_area_endemica=dados.get("viagem_area_endemica"),
        exposicao_agua_enchente=dados.get("exposicao_agua_enchente"),
        contato_roedores=dados.get("contato_roedores"),
        contato_caso_confirmado=dados.get("contato_caso_confirmado"),
        vacinado_febre_amarela=dados.get("vacinado_febre_amarela"),
        tem_comorbidade=dados.get("tem_comorbidade"),
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
        fonte_referencia="simulacao_publica" if simulacao_autorizada else "",
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
        },
        "cidadao": resultado_cidadao,
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

    empresa = _empresa_app_publico()
    # ── RLS: define o tenant boundary para o endpoint público ──────────────
    # A política de isolamento (migration 0085) exige que app.empresa_id esteja
    # definido antes de qualquer INSERT em api_registrosintoma.  No fluxo
    # autenticado isso é feito pelo middleware; aqui precisamos fazer
    # manualmente, pois /api/public/ é rota livre (sem sessão de usuário).
    from api.middleware import _rls_set_empresa as _set_rls
    _set_rls(empresa.id)
    if simulacao_autorizada:
        geo = {
            "bairro": (dados.get("bairro") or "Centro").strip(),
            "cidade": (dados.get("cidade") or "Rio de Janeiro").strip(),
            "estado": (dados.get("estado") or "Rio de Janeiro").strip(),
            "pais": (dados.get("pais") or "Brasil").strip(),
        }
    else:
        geo = obter_endereco(latitude, longitude)
    dados_classificacao = {**dados, "estado": geo.get("estado", ""), "cidade": geo.get("cidade", "")}
    grupo, classificacao = classificar_padrao(dados_classificacao, setor="governo")
    resultado_cidadao = _classificar_cidadao(dados_classificacao, estado=geo.get("estado", ""))
    confianca, motivos_suspeita, ip, device_id = _score_suspeita(empresa, request, dados)
    if location_source != "current":
        # Mantem o fluxo resiliente para versões antigas do app e cenários de
        # GPS degradado, sem dar o mesmo peso epidemiológico de um GPS atual.
        confianca = min(confianca, 0.6)
        motivos_suspeita.append("localizacao_nao_confirmada")
    permitido, motivo_bloqueio = _bloqueio_envio_publico(
        empresa,
        ip,
        device_id,
        dados=dados,
        geo=geo,
    )

    if not permitido:
        # Injeta aviso no resultado cidadao para a tela mostrar que
        # o relato anterior ja esta sendo monitorado (nao contabiliza de novo).
        resultado_cidadao_ja = dict(resultado_cidadao)
        resultado_cidadao_ja["ja_monitorado"] = True
        resultado_cidadao_ja["conduta"] = (
            "Seus sintomas já estão sendo acompanhados no mapa epidemiológico regional. "
            "Não é necessário enviar novamente — um relato por período é suficiente para o monitoramento. "
            + resultado_cidadao.get("conduta", "")
        )
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
            "cidadao": resultado_cidadao_ja,
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
        # Sintomas base
        febre=bool(dados.get("febre", False)),
        tosse=bool(dados.get("tosse", False)),
        dor_corpo=bool(dados.get("dor_corpo", False)),
        cansaco=bool(dados.get("cansaco", False)),
        falta_ar=bool(dados.get("falta_ar", False)),
        # Sintomas expandidos (IA 2.0)
        dor_cabeca=bool(dados.get("dor_cabeca", False)),
        dor_articular=bool(dados.get("dor_articular", False)),
        exantema=bool(dados.get("exantema", False)),
        conjuntivite=bool(dados.get("conjuntivite", False)),
        vomito_nausea=bool(dados.get("vomito_nausea", False)),
        diarreia=bool(dados.get("diarreia", False)),
        dor_abdominal=bool(dados.get("dor_abdominal", False)),
        rigidez_nuca=bool(dados.get("rigidez_nuca", False)),
        ictericia=bool(dados.get("ictericia", False)),
        manchas_hemorragicas=bool(dados.get("manchas_hemorragicas", False)),
        perda_olfato_paladar=bool(dados.get("perda_olfato_paladar", False)),
        dor_garganta=bool(dados.get("dor_garganta", False)),
        coriza=bool(dados.get("coriza", False)),
        calafrios=bool(dados.get("calafrios", False)),
        sudorese=bool(dados.get("sudorese", False)),
        intensidade_febre=dados.get("intensidade_febre", ""),
        intensidade_articular=dados.get("intensidade_articular", ""),
        # Anamnese epidemiológica
        dias_sintomas=dados.get("dias_sintomas"),
        inicio_abrupto=dados.get("inicio_abrupto"),
        viagem_area_endemica=dados.get("viagem_area_endemica"),
        exposicao_agua_enchente=dados.get("exposicao_agua_enchente"),
        contato_roedores=dados.get("contato_roedores"),
        contato_caso_confirmado=dados.get("contato_caso_confirmado"),
        vacinado_febre_amarela=dados.get("vacinado_febre_amarela"),
        tem_comorbidade=dados.get("tem_comorbidade"),
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
    clear_panorama_cache()

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
        "cidadao": resultado_cidadao,
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
    # Dados epidemiológicos são sempre da empresa pública (app da população).
    # Governo, Hospital, Farmácia e Plano de Saúde leem os mesmos dados.
    empresa = _empresa_app_publico()
    from api.middleware import _rls_set_empresa as _set_rls
    _set_rls(empresa.id)

    dados = RegistroSintoma.objects.filter(empresa=empresa).values("cidade", "estado", "grupo").annotate(total=Count("id"))

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
    # Dados epidemiológicos são sempre da empresa pública (app da população).
    # Governo, Hospital, Farmácia e Plano de Saúde leem os mesmos dados.
    empresa = _empresa_app_publico()
    from api.middleware import _rls_set_empresa as _set_rls
    _set_rls(empresa.id)

    dados = RegistroSintoma.objects.filter(empresa=empresa).values("cidade", "estado").annotate(

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
    # Dados epidemiológicos são sempre da empresa pública (app da população).
    # Governo, Hospital, Farmácia e Plano de Saúde leem os mesmos dados.
    empresa = _empresa_app_publico()
    from api.middleware import _rls_set_empresa as _set_rls
    _set_rls(empresa.id)

    agora = timezone.now()
    h24 = agora - timedelta(hours=24)
    h48 = agora - timedelta(hours=48)

    ultimas_24h = RegistroSintoma.objects.filter(
        empresa=empresa, data_registro__gte=h24
    ).values("cidade", "estado").annotate(total=Count("id"))

    ultimas_48h = RegistroSintoma.objects.filter(
        empresa=empresa, data_registro__gte=h48, data_registro__lt=h24
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
    # Dados epidemiológicos são sempre da empresa pública (app da população).
    # Governo, Hospital, Farmácia e Plano de Saúde leem os mesmos dados.
    empresa = _empresa_app_publico()
    from api.middleware import _rls_set_empresa as _set_rls
    _set_rls(empresa.id)

    dados = RegistroSintoma.objects.filter(empresa=empresa).values(
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
    # Dados epidemiológicos são sempre da empresa pública (app da população).
    # Governo, Hospital, Farmácia e Plano de Saúde leem os mesmos dados.
    empresa = _empresa_app_publico()
    from api.middleware import _rls_set_empresa as _set_rls
    _set_rls(empresa.id)

    registros = RegistroSintoma.objects.filter(empresa=empresa)

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
    if not getattr(request, "empresa", None):
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    # Dados epidemiológicos são sempre da empresa pública (app da população).
    # Governo, Hospital, Farmácia e Plano de Saúde leem os mesmos dados.
    empresa = _empresa_app_publico()
    from api.middleware import _rls_set_empresa as _set_rls
    _set_rls(empresa.id)

    dados = json.loads(request.body or "{}")

    registros = RegistroSintoma.objects.filter(empresa=empresa)

    modelo = treinar_modelo(registros)

    resultado = prever_com_aprendizado(dados, modelo)

    if not resultado:
        return JsonResponse({"erro": "sem dados suficientes"})

    principal = max(resultado, key=resultado.get)

    return JsonResponse({
        "probabilidades": resultado,
        "mais_provavel": principal
    })



def classificar_padrao(dados, setor: str = "governo"):
    """
    Motor IA 2.0 — diagnóstico diferencial probabilístico completo.
    Retorna (grupo, classificacao) para compatibilidade com os endpoints legados.
    Para resultado completo usar api.utils_ia.classificar_padrao diretamente.
    """
    from api.classificador_doencas import classificar, DOENCAS_BRASIL
    # Passa estado para que o prior geográfico seja consistente com o classificador cidadão.
    estado = dados.get("estado") or dados.get("uf") or ""
    resultado = classificar(dados, setor=setor, estado=estado)
    doenca = resultado["primario"]
    grupo = resultado["grupo"]
    confianca = resultado["confianca"]

    # Flags de urgência absoluta
    urgencias = resultado.get("urgencia_absoluta", [])
    if urgencias:
        titulo_urgencia = urgencias[0]["titulo"]
        classificacao = f"URGÊNCIA: {titulo_urgencia} — {doenca} ({confianca}% confiança)"
    elif doenca == "Inconclusivo":
        classificacao = "Sintomas insuficientes para classificação"
    else:
        diferencial = resultado.get("diagnostico_diferencial", "")
        if diferencial:
            classificacao = f"{doenca} ({confianca}% confiança) — {diferencial}"
        else:
            classificacao = f"{doenca} ({confianca}% confiança)"

    return grupo, classificacao[:300]

def resumo_estados(request):
    # Dados epidemiológicos são sempre da empresa pública (app da população).
    # Governo, Hospital, Farmácia e Plano de Saúde leem os mesmos dados.
    empresa = _empresa_app_publico()
    from api.middleware import _rls_set_empresa as _set_rls
    _set_rls(empresa.id)
    dados = RegistroSintoma.objects.filter(empresa=empresa).values("estado").annotate(total=Count("id"))
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
    # Dados epidemiológicos são sempre da empresa pública (app da população).
    # Governo, Hospital, Farmácia e Plano de Saúde leem os mesmos dados.
    empresa = _empresa_app_publico()
    from api.middleware import _rls_set_empresa as _set_rls
    _set_rls(empresa.id)

    dados = RegistroSintoma.objects.filter(empresa=empresa)

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


def app_vigilancia_resumo(request):
    """
    Resumo epidemiológico nacional (mesma fonte do console admin):
    casos 30d/24h, focos, estados, crescimento 7d, top doenças e top estados.
    Endpoint público compartilhado por todos os ambientes (Governo, Farmácia,
    Hospital, Plano de Saúde e console), garantindo números IDÊNTICOS.
    """
    from api.services.dashboard_core import _resumo_vigilancia_publica
    response = JsonResponse(_resumo_vigilancia_publica(timezone.now()))
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


def app_resumo_publico(request):
    # ── RLS: garante visibilidade dos registros públicos ─────────────────────
    from api.middleware import _rls_set_empresa as _set_rls
    _emp_pub = _empresa_app_publico()
    _set_rls(_emp_pub.id)
    agora = timezone.now()
    from api.epidemiologia import _scope_public_population_queryset as _scope_public

    base_publica = _scope_public(
        RegistroSintoma.objects.exclude(q_registro_sintoma_sintetico())
    )
    ultimas_24h = base_publica.filter(data_registro__gte=agora - timedelta(hours=24))
    ultimos_7d = base_publica.filter(data_registro__gte=agora - timedelta(days=7))
    ativos_30d = base_publica.filter(data_registro__gte=agora - timedelta(days=JANELA_DECAIMENTO_FOCO_DIAS))
    dias_anteriores = base_publica.filter(
        data_registro__gte=agora - timedelta(days=14),
        data_registro__lt=agora - timedelta(days=7),
    )

    total_24h = ultimas_24h.count()
    total_7d = ultimos_7d.count()
    total_30d = ativos_30d.count()
    indice_ativo_30d = _indice_temporal_publico(ativos_30d, agora)
    base_anterior = dias_anteriores.count()

    ativos_por_estado = defaultdict(float)
    totais_por_estado = defaultdict(int)
    ativos_por_estado_rows = (
        ativos_30d.exclude(estado__isnull=True).exclude(estado="")
        .annotate(day=TruncDate("data_registro"))
        .values("estado", "day")
        .annotate(total=Count("id"))
    )
    for item in ativos_por_estado_rows:
        estado = item["estado"]
        peso = _peso_temporal_publico(item["day"], agora)
        totais_por_estado[estado] += int(item["total"] or 0)
        ativos_por_estado[estado] += int(item["total"] or 0) * peso

    # ── Crescimento robusto ────────────────────────────────────────────────
    # 1ª escolha: 7 dias atuais vs 7 dias anteriores (janela clássica).
    # Fallback: quando não há histórico de 7-14 dias mas há atividade recente,
    # usa o momentum das últimas 24h contra a média diária dos 7 dias — assim
    # um surto novo (todos os casos recentes) não fica travado em 0,0%.
    if base_anterior:
        crescimento = round(((total_7d - base_anterior) / base_anterior) * 100, 2)
    else:
        media_diaria_7d = (total_7d / 7.0) if total_7d else 0.0
        if media_diaria_7d > 0 and total_24h > 0:
            crescimento = round(((total_24h - media_diaria_7d) / media_diaria_7d) * 100, 2)
            crescimento = max(0.0, min(crescimento, 999.0))
        else:
            crescimento = 0.0

    doencas = (
        ativos_30d.exclude(grupo__isnull=True).exclude(grupo="")
        .values("grupo")
        .annotate(total=Count("id"))
        .order_by("-total")[:6]
    )
    top_grupo = doencas[0]["grupo"] if doencas else "monitoramento geral"
    nivel_nacional = _nivel_por_indice_publico(indice_ativo_30d, crescimento)

    # ── Casos por estado (visualização fácil no app) ───────────────────────
    por_estado_rows = (
        ativos_30d.exclude(estado__isnull=True).exclude(estado="")
        .values("estado")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    casos_por_estado = []
    for row in por_estado_rows:
        uf = _uf_sigla(row["estado"])
        casos_por_estado.append({
            "estado": row["estado"],
            "uf": uf,
            "total": row["total"],
            "percentual": round((row["total"] / max(total_30d, 1)) * 100, 1),
        })

    casos_por_estado_ativos = []
    for estado, total_ativo in sorted(ativos_por_estado.items(), key=lambda item: item[1], reverse=True):
        uf = _uf_sigla(estado)
        total_bruto = totais_por_estado.get(estado, 0)
        casos_por_estado_ativos.append({
            "estado": estado,
            "uf": uf,
            "total": round(total_ativo, 2),
            "total_bruto": total_bruto,
            "percentual": round((total_ativo / max(indice_ativo_30d, 1)) * 100, 1),
        })

    response = JsonResponse({
        "resumo": {
            "registros_24h": total_24h,
            "registros_7d": total_7d,
            "registros_30d": total_30d,
            "total_ativo_30d": round(indice_ativo_30d, 2),
            "indice_ativo_7d": indice_ativo_30d,
            "indice_ativo_30d": indice_ativo_30d,
            "crescimento_7d": crescimento,
            "suspeitos_24h": ultimas_24h.filter(suspeito=True).count(),
            "nivel_nacional": nivel_nacional,
            "total_estados": len(casos_por_estado),
            "decaimento_temporal": "o indice ativo fica preservado por 10 dias sem novos envios; depois a IA reduz gradualmente apenas quando serie temporal, dados agregados e fontes oficiais sustentam queda real, evitando falsa melhora precoce",
        },
        "semaforo": _semaforo_publico(nivel_nacional),
        "alerta_publico": _alerta_publico(nivel_nacional, crescimento, top_grupo),
        "orientacao_publica": _orientacao_publica(nivel_nacional, top_grupo),
        "casos_por_estado": casos_por_estado,
        "casos_por_estado_ativos": casos_por_estado_ativos,
        "doencas_top": [
            {
                "grupo": item["grupo"],
                "total": item["total"],
                "percentual": round((item["total"] / max(total_30d, 1)) * 100, 2),
            }
            for item in doencas
        ],
    })
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


def app_radar_local(request):
    # ── RLS: garante visibilidade dos registros públicos ─────────────────────
    from api.middleware import _rls_set_empresa as _set_rls
    from api.epidemiologia import _scope_public_population_queryset as _scope_public
    _emp_pub = _empresa_app_publico()
    _set_rls(_emp_pub.id)
    latitude = request.GET.get("latitude")
    longitude = request.GET.get("longitude")
    cidade = request.GET.get("cidade")
    estado = _normalizar_estado(request.GET.get("estado"))
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
    base_publica = _scope_public(
        RegistroSintoma.objects.exclude(q_registro_sintoma_sintetico())
    )
    atuais = base_publica.filter(
        cidade=cidade,
        estado=estado,
        data_registro__gte=agora - timedelta(days=JANELA_DECAIMENTO_FOCO_DIAS),
    )
    atuais_7d = atuais.filter(data_registro__gte=agora - timedelta(days=7))
    anteriores = base_publica.filter(
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
    risk_level = "ALTO" if nivel == "alto" else "MODERADO" if nivel in {"moderado", "atencao"} else "BAIXO"

    doencas = (
        atuais.exclude(grupo__isnull=True).exclude(grupo="")
        .values("grupo")
        .annotate(total=Count("id"))
        .order_by("-total")[:6]
    )
    grupo_top = doencas[0]["grupo"] if doencas else "monitoramento geral"

    sintomas = {
        key: atuais.filter(**{key: True}).count()
        for key in SYMPTOM_LABELS
    }
    sintoma_dominante_key = max(sintomas, key=sintomas.get) if sintomas else None
    sintoma_dominante = (
        SYMPTOM_LABELS.get(sintoma_dominante_key)
        if sintoma_dominante_key and sintomas.get(sintoma_dominante_key, 0) > 0
        else "Sem dados"
    )
    doencas_provaveis = _build_disease_probabilities(sintomas, total_ativos)
    doenca_dominante = doencas_provaveis[0]["name"] if doencas_provaveis else None

    response = JsonResponse({
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
            "indice_ativo": indice_ativo,
            "casos_ativos": indice_ativo,
            "active_cases": indice_ativo,
            "total_cases": indice_ativo,
            "raw_total_cases": total_ativos,
            "total_registros_30d": total_ativos,
            "crescimento_7d": crescimento,
            "crescimento_percent": crescimento,
            "suspeitos_7d": atuais_7d.filter(suspeito=True).count(),
            "bairro_registros_7d": atuais_bairro_7d.count(),
            "bairro_registros_30d": atuais_bairro.count(),
            "grupo_top": grupo_top,
            "nivel_risco": risk_level,
            "sintoma_dominante": sintoma_dominante,
            "dominant_symptom": sintoma_dominante,
            "doenca_dominante": doenca_dominante,
            "dominant_disease": doenca_dominante,
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
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


def _risk_level_para_nivel_publico(risk_level):
    """Converte o risk_level do panorama (CRITICO/ALTO/MODERADO/BAIXO) para o
    nível do semáforo público (alto/moderado/atencao/baixo)."""
    rl = (risk_level or "").strip().upper()
    if rl in ("CRITICO", "CRÍTICO", "ALTO"):
        return "alto"
    if rl == "MODERADO":
        return "moderado"
    if rl in ("ATENCAO", "ATENÇÃO"):
        return "atencao"
    return "baixo"


def app_mapa_publico(request):
    """
    Mapa de focos do app da população.

    Reaproveita o panorama cacheado para manter o app alinhado aos painéis de
    segmento e evitar o custo de recalcular agregações pesadas a cada abertura.
    """
    from api.middleware import _rls_set_empresa as _set_rls
    _emp_pub = _empresa_app_publico()
    _set_rls(_emp_pub.id)

    cidade = request.GET.get("cidade")
    estado = _normalizar_estado(request.GET.get("estado"))
    bairro = request.GET.get("bairro")
    def _norm(value):
        return " ".join(str(value or "").strip().split()).casefold()

    def _matches_filters(item):
        if estado and item.get("estado") not in _state_terms(estado):
            return False
        if cidade and _norm(item.get("cidade")) != _norm(cidade):
            return False
        bairro_item = item.get("bairro") or item.get("nome")
        if bairro and _norm(bairro_item) != _norm(bairro):
            return False
        return True

    payload = build_panorama_payload()
    hotspots_base = payload.get("layers", {}).get("bairros", [])
    hotspots = []
    for item in hotspots_base:
        if not _matches_filters(item):
            continue

        latitude = item.get("latitude")
        longitude = item.get("longitude")
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            continue
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue

        hotspots.append({
            "cidade": item.get("cidade"),
            "estado": item.get("estado"),
            "bairro": item.get("nome") or item.get("bairro"),
            "total": float(item.get("total_cases") or item.get("active_cases") or 0),
            "total_cases": float(item.get("total_cases") or item.get("active_cases") or 0),
            "active_cases": float(item.get("active_cases") or item.get("total_cases") or 0),
            "casos_ativos": float(item.get("active_cases") or item.get("total_cases") or 0),
            "total_registros_30d": int(item.get("raw_total_cases") or item.get("total_registros_30d") or 0),
            "registros_30d": int(item.get("raw_total_cases") or item.get("total_registros_30d") or 0),
            "raw_total_cases": int(item.get("raw_total_cases") or item.get("total_registros_30d") or 0),
            "raw_total": int(item.get("raw_total_cases") or item.get("total_registros_30d") or 0),
            "indice_ativo": float(item.get("active_cases") or item.get("total_cases") or 0),
            "recent_24h": int(item.get("recent_24h") or 0),
            "previous_24h": int(item.get("previous_24h") or 0),
            "growth_percent": float(item.get("growth_percent") or 0),
            "crescimento_percent": float(item.get("growth_percent") or 0),
            "latitude": latitude,
            "longitude": longitude,
            "grupo_dominante": item.get("dominant_disease")
                or item.get("focus_message")
                or "Monitoramento geral",
            "perfil_sindromico": item.get("dominant_disease")
                or "Monitoramento geral",
            "doenca_dominante": item.get("dominant_disease"),
            "dominant_disease": item.get("dominant_disease"),
            "dominant_symptom": item.get("dominant_symptom") or "Sem dados",
            "sintoma_dominante": item.get("dominant_symptom") or "Sem dados",
            "sintomas": {
                symptom.get("key"): int(symptom.get("count", 0) or 0)
                for symptom in (item.get("symptoms") or [])
                if isinstance(symptom, dict) and symptom.get("key")
            },
            "doencas_provaveis": [dict(d) for d in (item.get("probable_diseases") or [])][:5],
            "probable_diseases": [dict(d) for d in (item.get("probable_diseases") or [])][:5],
            "risk_level": item.get("risk_level") or "BAIXO",
            "nivel_risco": item.get("risk_level") or "BAIXO",
            "semaforo": _semaforo_publico(
                _risk_level_para_nivel_publico(item.get("risk_level"))
            ),
            "decaimento_temporal": item.get("focus_message")
                or "foco preservado por 10 dias sem novos envios; depois a intensidade reduz gradualmente somente quando a IA valida queda real com serie temporal, dados agregados e fontes oficiais",
        })

    hotspots.sort(
        key=lambda item: (
            float(item.get("indice_ativo") or 0),
            float(item.get("raw_total_cases") or 0),
        ),
        reverse=True,
    )
    total_indice_mapa = sum(float(item.get("indice_ativo") or 0) for item in hotspots) or 1

    for item in hotspots:
        item["percentual_ativo"] = round(
            (float(item.get("indice_ativo") or 0) / total_indice_mapa) * 100,
            2,
        )

    response = JsonResponse({"hotspots": hotspots}, safe=False)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


def _filtrar_alertas_publicos(queryset, estado=None, cidade=None, bairro=None, incluir_gerais=True):
    if estado:
        estado_filter = Q(estado__in=_state_terms(estado))
        if incluir_gerais:
            estado_filter |= Q(estado__isnull=True) | Q(estado="")
        queryset = queryset.filter(estado_filter)
    if cidade:
        cidade_filter = Q(cidade=cidade)
        if incluir_gerais:
            cidade_filter |= Q(cidade__isnull=True) | Q(cidade="")
        queryset = queryset.filter(cidade_filter)
    if bairro:
        bairro_filter = Q(bairro=bairro)
        if incluir_gerais:
            bairro_filter |= Q(bairro__isnull=True) | Q(bairro="")
        queryset = queryset.filter(bairro_filter)
    return queryset


def _payload_alerta_publico(alerta):
    return {
        "id": alerta.id,
        "titulo": alerta.titulo,
        "mensagem": alerta.mensagem,
        "estado": alerta.estado,
        "cidade": alerta.cidade,
        "bairro": alerta.bairro,
        "nivel": alerta.nivel,
        "protocolo": alerta.protocolo,
        "criado_em": alerta.criado_em.isoformat(),
    }


def _dedupe_alertas_publicos(alertas):
    unicos = {}
    for alerta in sorted(alertas, key=lambda item: item.criado_em, reverse=True):
        chave = (
            alerta.protocolo
            or f"{alerta.titulo}|{alerta.mensagem}|{alerta.estado}|{alerta.cidade}|{alerta.bairro}"
        )
        atual = unicos.get(chave)
        if atual is None or alerta.criado_em >= atual.criado_em:
            unicos[chave] = alerta
    return sorted(unicos.values(), key=lambda item: item.criado_em, reverse=True)


def app_alertas_publicos(request):
    # ── RLS: garante visibilidade dos alertas do setor público ──────────────
    from api.middleware import _rls_set_empresa as _set_rls
    _emp_pub = _empresa_app_publico()
    cidade = request.GET.get("cidade")
    estado = _normalizar_estado(request.GET.get("estado"))
    bairro = request.GET.get("bairro")
    incluir_gerais = request.GET.get("incluir_gerais", "1").lower() not in {"0", "false", "nao", "não"}

    alertas_coletados = []
    empresas_publicaveis = list(
        Empresa.objects.filter(
            Q(id=_emp_pub.id) | Q(tipo_conta=Empresa.TIPO_GOVERNO)
        ).values_list("id", flat=True)
    )
    if _emp_pub.id not in empresas_publicaveis:
        empresas_publicaveis.insert(0, _emp_pub.id)

    for empresa_id in empresas_publicaveis:
        _set_rls(empresa_id)
        queryset = AlertaGovernamental.objects.filter(
            empresa_id=empresa_id,
            ativo=True,
            status=AlertaGovernamental.STATUS_PUBLICADO,
        ).order_by("-criado_em")
        queryset = _filtrar_alertas_publicos(
            queryset,
            estado=estado,
            cidade=cidade,
            bairro=bairro,
            incluir_gerais=incluir_gerais,
        )
        alertas_coletados.extend(
            [alerta for alerta in queryset[:24] if not alerta_governamental_sintetico(alerta)][:12]
        )

    _set_rls(_emp_pub.id)
    alertas = _dedupe_alertas_publicos(alertas_coletados)[:12]

    return JsonResponse({
        "alertas": [
            _payload_alerta_publico(alerta)
            for alerta in alertas
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

def analisar_audio(request):
    return JsonResponse(
        {"erro": "Análise de áudio não disponível nesta versão."},
        status=501,
    )

from api.models import RegistroSintoma

def limpar_casos(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    total = RegistroSintoma.objects.filter(empresa=empresa).count()
    RegistroSintoma.objects.filter(empresa=empresa).delete()
    clear_panorama_cache()
    return JsonResponse({"apagados": total})


@csrf_exempt
def simular_focos_epidemicos(request):
    """
    Cria dados de simulação epidemiológica reais no banco de produção.
    Fases: 1=50 casos/10 focos, 2=~700/46 focos, 3=~5000/46 focos
    Uso: GET/POST /api/simular-focos?fase=1&limpar=1
    Protegido: requer sessão empresa autenticada.
    """
    import random as _rnd
    from datetime import timedelta as _td
    from django.utils import timezone as _tz
    from api.epidemiologia import clear_panorama_cache as _clr

    # Requer sessão autenticada (empresa logada)
    empresa_req = getattr(request, "empresa", None)
    if not empresa_req:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    try:
        body = json.loads(request.body or "{}")
    except Exception:
        body = {}

    # Aceita parâmetros via GET query string ou body JSON
    fase = int(request.GET.get("fase") or body.get("fase") or 1)
    limpar = bool(request.GET.get("limpar") or body.get("limpar", False))

    emp = _empresa_app_publico()
    # Seta RLS para a empresa pública
    try:
        from api.middleware import _rls_set_empresa
        _rls_set_empresa(emp.id)
    except Exception:
        pass
    if limpar:
        RegistroSintoma.objects.filter(empresa=emp).delete()

    now = _tz.now()

    SINTOMAS = {
        "Dengue":         {"febre":True,"dor_corpo":True,"dor_cabeca":True,"cansaco":True,"vomito_nausea":True},
        "Chikungunya":    {"febre":True,"dor_articular":True,"exantema":True,"dor_corpo":True,"cansaco":True},
        "Zika":           {"exantema":True,"conjuntivite":True,"febre":True,"dor_articular":True},
        "COVID-19":       {"febre":True,"tosse":True,"falta_ar":True,"perda_olfato_paladar":True,"cansaco":True},
        "Gripe":          {"febre":True,"tosse":True,"dor_corpo":True,"dor_cabeca":True,"cansaco":True},
        "Malária":        {"febre":True,"calafrios":True,"cansaco":True,"dor_corpo":True},
        "Resfriado Viral":{"coriza":True,"dor_garganta":True,"tosse":True},
    }

    # Todos os focos do Brasil — RJ com múltiplos municípios e bairros
    TODOS_FOCOS = [
        # ── RIO DE JANEIRO ──────────────────────────────────────────────
        {"b":"Copacabana",       "c":"Rio de Janeiro","e":"Rio de Janeiro","lat":-22.9711,"lng":-43.1835,"d":"Dengue"},
        {"b":"Icaraí",           "c":"Niterói",       "e":"Rio de Janeiro","lat":-22.8993,"lng":-43.1163,"d":"Dengue"},
        {"b":"Tijuca",           "c":"Rio de Janeiro","e":"Rio de Janeiro","lat":-22.9218,"lng":-43.2358,"d":"Gripe"},
        {"b":"Botafogo",         "c":"Rio de Janeiro","e":"Rio de Janeiro","lat":-22.9519,"lng":-43.1869,"d":"Dengue"},
        {"b":"Madureira",        "c":"Rio de Janeiro","e":"Rio de Janeiro","lat":-22.8762,"lng":-43.3340,"d":"Dengue"},
        {"b":"Barra da Tijuca",  "c":"Rio de Janeiro","e":"Rio de Janeiro","lat":-22.9999,"lng":-43.3645,"d":"Gripe"},
        {"b":"Leblon",           "c":"Rio de Janeiro","e":"Rio de Janeiro","lat":-22.9842,"lng":-43.2247,"d":"COVID-19"},
        {"b":"Méier",            "c":"Rio de Janeiro","e":"Rio de Janeiro","lat":-22.8981,"lng":-43.2797,"d":"Dengue"},
        {"b":"Centro",           "c":"Nova Iguaçu",   "e":"Rio de Janeiro","lat":-22.7596,"lng":-43.4505,"d":"Dengue"},
        {"b":"Centro",           "c":"Duque de Caxias","e":"Rio de Janeiro","lat":-22.7853,"lng":-43.3115,"d":"Dengue"},
        {"b":"Centro",           "c":"São Gonçalo",   "e":"Rio de Janeiro","lat":-22.8267,"lng":-43.0539,"d":"Gripe"},
        {"b":"Centro",           "c":"Campos dos Goytacazes","e":"Rio de Janeiro","lat":-21.7542,"lng":-41.3244,"d":"Dengue"},
        {"b":"Centro",           "c":"Petrópolis",    "e":"Rio de Janeiro","lat":-22.5043,"lng":-43.1820,"d":"Resfriado Viral"},
        {"b":"Centro",           "c":"Volta Redonda", "e":"Rio de Janeiro","lat":-22.5233,"lng":-44.1044,"d":"Resfriado Viral"},
        {"b":"Centro",           "c":"Angra dos Reis","e":"Rio de Janeiro","lat":-22.9682,"lng":-44.3178,"d":"Chikungunya"},
        # ── SÃO PAULO ───────────────────────────────────────────────────
        {"b":"Pinheiros",        "c":"São Paulo",     "e":"São Paulo",     "lat":-23.5629,"lng":-46.6898,"d":"Gripe"},
        {"b":"Santana",          "c":"São Paulo",     "e":"São Paulo",     "lat":-23.4948,"lng":-46.6387,"d":"Gripe"},
        {"b":"Centro",           "c":"Campinas",      "e":"São Paulo",     "lat":-22.9058,"lng":-47.0609,"d":"COVID-19"},
        {"b":"Centro",           "c":"Ribeirão Preto","e":"São Paulo",     "lat":-21.1775,"lng":-47.8103,"d":"Dengue"},
        {"b":"Centro",           "c":"São José dos Campos","e":"São Paulo","lat":-23.1896,"lng":-45.8841,"d":"COVID-19"},
        # ── MINAS GERAIS ────────────────────────────────────────────────
        {"b":"Savassi",          "c":"Belo Horizonte","e":"Minas Gerais",  "lat":-19.9385,"lng":-43.9385,"d":"Dengue"},
        {"b":"Centro",           "c":"Uberlândia",    "e":"Minas Gerais",  "lat":-18.9186,"lng":-48.2772,"d":"Gripe"},
        # ── NORDESTE ────────────────────────────────────────────────────
        {"b":"Boa Viagem",       "c":"Recife",        "e":"Pernambuco",    "lat":-8.1167,"lng":-34.8993,"d":"Dengue"},
        {"b":"Aldeota",          "c":"Fortaleza",     "e":"Ceará",         "lat":-3.7327,"lng":-38.5024,"d":"Chikungunya"},
        {"b":"Pelourinho",       "c":"Salvador",      "e":"Bahia",         "lat":-12.9718,"lng":-38.5102,"d":"Dengue"},
        {"b":"Centro",           "c":"Maceió",        "e":"Alagoas",       "lat":-9.6658,"lng":-35.7350,"d":"Dengue"},
        {"b":"Centro",           "c":"João Pessoa",   "e":"Paraíba",       "lat":-7.1150,"lng":-34.8633,"d":"Zika"},
        {"b":"Centro",           "c":"Natal",         "e":"Rio Grande do Norte","lat":-5.7945,"lng":-35.2110,"d":"Dengue"},
        {"b":"Centro",           "c":"São Luís",      "e":"Maranhão",      "lat":-2.5283,"lng":-44.3068,"d":"Dengue"},
        {"b":"Centro",           "c":"Teresina",      "e":"Piauí",         "lat":-5.0892,"lng":-42.8019,"d":"Dengue"},
        # ── NORTE ───────────────────────────────────────────────────────
        {"b":"Centro",           "c":"Manaus",        "e":"Amazonas",      "lat":-3.1190,"lng":-60.0217,"d":"Malária"},
        {"b":"Centro",           "c":"Belém",         "e":"Pará",          "lat":-1.4558,"lng":-48.4902,"d":"Dengue"},
        {"b":"Centro",           "c":"Porto Velho",   "e":"Rondônia",      "lat":-8.7612,"lng":-63.9004,"d":"Malária"},
        # ── CENTRO-OESTE ────────────────────────────────────────────────
        {"b":"Asa Sul",          "c":"Brasília",      "e":"Distrito Federal","lat":-15.7949,"lng":-47.8825,"d":"Gripe"},
        {"b":"Centro",           "c":"Goiânia",       "e":"Goiás",         "lat":-16.6869,"lng":-49.2648,"d":"Dengue"},
        {"b":"Centro",           "c":"Campo Grande",  "e":"Mato Grosso do Sul","lat":-20.4428,"lng":-54.6460,"d":"Dengue"},
        # ── SUL ─────────────────────────────────────────────────────────
        {"b":"Centro",           "c":"Curitiba",      "e":"Paraná",        "lat":-25.4284,"lng":-49.2733,"d":"Gripe"},
        {"b":"Floresta",         "c":"Porto Alegre",  "e":"Rio Grande do Sul","lat":-30.0346,"lng":-51.2177,"d":"Gripe"},
        {"b":"Centro",           "c":"Florianópolis", "e":"Santa Catarina","lat":-27.5954,"lng":-48.5480,"d":"COVID-19"},
    ]

    # Quantidade por foco dependendo da fase
    CASOS_FASE = {1: 5, 2: 50, 3: 130}
    qtd_por_foco = CASOS_FASE.get(fase, 5)
    # Fase 1: apenas 10 primeiros focos
    focos_usar = TODOS_FOCOS if fase >= 2 else TODOS_FOCOS[:10]

    registros = []
    for f in focos_usar:
        sint = SINTOMAS.get(f["d"], {})
        for _ in range(qtd_por_foco):
            registros.append(RegistroSintoma(
                empresa=emp,
                latitude=f["lat"] + _rnd.uniform(-0.01, 0.01),
                longitude=f["lng"] + _rnd.uniform(-0.01, 0.01),
                cidade=f["c"], bairro=f["b"], estado=f["e"], pais="Brasil",
                grupo=f["d"],
                febre=sint.get("febre", False),
                tosse=sint.get("tosse", False),
                dor_corpo=sint.get("dor_corpo", False),
                cansaco=sint.get("cansaco", False),
                falta_ar=sint.get("falta_ar", False),
                dor_cabeca=sint.get("dor_cabeca", False),
                dor_articular=sint.get("dor_articular", False),
                exantema=sint.get("exantema", False),
                vomito_nausea=sint.get("vomito_nausea", False),
                calafrios=sint.get("calafrios", False),
                conjuntivite=sint.get("conjuntivite", False),
                perda_olfato_paladar=sint.get("perda_olfato_paladar", False),
                coriza=sint.get("coriza", False),
                dor_garganta=sint.get("dor_garganta", False),
                confianca=1.0,
                origem_dado="cidadao",
                data_registro=now - _td(hours=_rnd.uniform(0, 6)),
            ))

    RegistroSintoma.objects.bulk_create(registros)

    # Re-geocodifica usando o fallback local melhorado (sem depender de Nominatim)
    from api.utils_geo import _fallback_local as _geo
    for r in RegistroSintoma.objects.filter(empresa=emp, latitude__isnull=False, longitude__isnull=False):
        g = _geo(r.latitude, r.longitude)
        if r.bairro != g["bairro"] or r.cidade != g["cidade"] or r.estado != g["estado"]:
            r.bairro = g["bairro"]; r.cidade = g["cidade"]; r.estado = g["estado"]
            r.save(update_fields=["bairro", "cidade", "estado"])

    _clr()

    total = RegistroSintoma.objects.filter(empresa=emp).count()
    focos_count = RegistroSintoma.objects.filter(empresa=emp).values("cidade","bairro","estado").distinct().count()
    return JsonResponse({
        "ok": True,
        "fase": fase,
        "total_casos": total,
        "total_focos": focos_count,
        "criados": len(registros),
    })


@csrf_exempt
def regeocodificar_focos(request):
    """
    Reprocessa cidade/bairro/estado de TODOS os registros do app público,
    aplicando o geocodificador de referência (100+ pontos do Brasil).
    Não-destrutivo: apenas atualiza os rótulos territoriais.

    Corrige o problema dos registros antigos rotulados genericamente como
    "Centro, Rio de Janeiro" cujo lat/lng real é Copacabana/Tijuca/Niterói etc.,
    fazendo o foco agregado deixar de cair na Baía de Guanabara.

    Aceita GET ou POST. Requer sessão autenticada (bypass de plano no middleware).
    """
    empresa_req = getattr(request, "empresa", None)
    if not empresa_req:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    from api.utils_geo import _fallback_local as _geo
    from api.epidemiologia import (
        clear_panorama_cache as _clr,
        _scope_public_population_queryset as _scope,
    )

    # Usa EXATAMENTE o mesmo caminho de leitura do /api/epidemiologia
    # (define RLS para a empresa pública e filtra por ela) — caminho comprovado.
    qs = _scope(
        RegistroSintoma.objects.filter(
            latitude__isnull=False, longitude__isnull=False
        )
    )

    atualizados = 0
    amostra = []
    for r in qs.iterator():
        g = _geo(r.latitude, r.longitude)
        if (r.bairro != g["bairro"] or r.cidade != g["cidade"]
                or r.estado != g["estado"]):
            if len(amostra) < 12:
                amostra.append(
                    f"{r.bairro or '?'}/{r.cidade or '?'} -> "
                    f"{g['bairro']}/{g['cidade']}"
                )
            r.bairro = g["bairro"]
            r.cidade = g["cidade"]
            r.estado = g["estado"]
            r.pais = g.get("pais", "Brasil")
            r.save(update_fields=["bairro", "cidade", "estado", "pais"])
            atualizados += 1

    _clr()
    total = qs.count()
    focos = qs.values("cidade", "bairro", "estado").distinct().count()
    return JsonResponse({
        "ok": True,
        "total": total,
        "focos": focos,
        "atualizados": atualizados,
        "amostra": amostra,
    })


def insights_nacional(request):

    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    dados = RegistroSintoma.objects.filter(empresa=empresa).values(
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

    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    dados = RegistroSintoma.objects.filter(empresa=empresa).values(
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




def tela_cadastro(request):
    from django.shortcuts import render
    return render(request, 'cadastro.html')

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

    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    dados = RegistroSintoma.objects.filter(empresa=empresa)

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

    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    dados = (
        RegistroSintoma.objects
        .filter(empresa=empresa)
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
