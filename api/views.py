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
        "title": "SolusCRT Saude | Gestao de saude ocupacional, epidemiologia e bem-estar",
        "description": "SolusCRT Saude e uma plataforma SaaS completa de gestao em saude: SST, ASO, eSocial, bem-estar da equipe, app do funcionario, radar epidemiologico com IA, farmacia, hospital e governo. Teste gratis por 15 dias.",
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
        "hero_eyebrow": "SST, bem-estar e inteligencia epidemiologica em uma plataforma",
        "hero_title": "Gestao completa de saude ocupacional com IA que antecipa surtos.",
        "hero_title_desktop_lines": ["Gestao completa de", "saude ocupacional", "com IA que", "antecipa surtos."],
        "hero_title_lines": ["Gestao completa", "de saude ocupacional", "com IA que", "antecipa surtos."],
        "hero_lead": "SolusCRT Saude e a plataforma SaaS que une SST completo, bem-estar da equipe, app do funcionario e radar epidemiologico com IA. Do ASO ao eSocial, do check-in anonimo de humor a antecipacao de surtos 7 a 10 dias antes do dado oficial. Teste gratis por 15 dias.",
        "actions": {
            "presentation": "Ver apresentacao completa",
            "app": "Baixar app da populacao",
            "sales": "Falar com comercial",
            "open_presentation": "Abrir apresentacao completa",
            "meeting": "Solicitar reuniao",
        },
        "proofs": [
            {"title": "SST completo em um painel", "text": "ASO, CAT, afastamentos, exames, treinamentos NR, EPI/EPC, PGR, postos S-2240, eSocial SST e conformidade — tudo integrado, sem planilha avulsa."},
            {"title": "Bem-estar sem expor o funcionario", "text": "Check-ins anonimos de humor, saude fisica, saude mental, estresse e satisfacao. A empresa ve agregados. O nome so aparece se o funcionario pedir ajuda voluntariamente."},
            {"title": "IA que antecipa, nao apenas notifica", "text": "O radar epidemiologico cruza sinais da populacao, fontes oficiais brasileiras e dados internos para antecipar surtos 7 a 10 dias antes do pico confirmado."},
        ],
        "chips": ["SST completo + eSocial", "Bem-estar da equipe", "App do funcionario", "15 dias gratis"],
        "metrics": [
            {"value": "SST", "text": "ASO, CAT, afastamentos, exames, treinamentos NR, EPI/EPC, PGR e eSocial em um unico painel"},
            {"value": "Bem-estar", "text": "check-ins anonimos de humor, saude fisica, mental, estresse e satisfacao no trabalho"},
            {"value": "IA + 7-10 dias", "text": "antecipacao de surtos antes do dado oficial, com validacao gradual por tendencia, agregados e fontes brasileiras"},
            {"value": "LGPD", "text": "governanca, minimizacao, segregacao de ambientes e anonimizacao do bem-estar"},
        ],
        "differential": {
            "title": "SST que protege hoje. IA que antecipa o que vem amanha.",
            "lead": "A maioria das plataformas faz SST ou faz epidemiologia. O SolusCRT une os dois: gestao ocupacional completa com o motor de inteligencia territorial que identifica risco antes que ele chegue ao consultorio ou ao INSS.",
            "traditional_title": "Gestao tradicional de SST",
            "traditional_items": [
                "ASO em papel ou sistema isolado, sem conexao com afastamentos reais e saude da equipe.",
                "eSocial SST preenchido na correria, sem visibilidade de conformidade em tempo real.",
                "Surtos percebidos quando o absenteismo ja subiu — sem chance de agir antes.",
            ],
            "solus_title": "SolusCRT SST + IA",
            "solus_items": [
                "SST completo integrado: ASO digital, CAT, afastamentos, NR, EPI/EPC, PGR e eSocial com painel de conformidade em tempo real.",
                "Bem-estar anonimo da equipe com check-ins de humor, saude e satisfacao — empresa ve tendencias, nao nomes.",
                "IA epidemiologica cruza sinais populacionais, dados oficiais e comportamento interno para alertar 7 a 10 dias antes do pico.",
            ],
        },
        "ecosystem_title": "Uma plataforma. Quatro ambientes. Um objetivo: proteger pessoas.",
        "ecosystem_lead": "SST para empresas, gestao para farmacias e hospitais, sala de situacao para governo e app gratuito para a populacao — conectados pela mesma camada de inteligencia epidemiologica.",
        "slides": [
            {"small": "Populacao", "title": "App gratuito", "text": "Envio anonimo de sintomas, radar local, mapa de risco e alertas oficiais. O sensor social que alimenta a inteligencia coletiva."},
            {"small": "SST e Empresas", "title": "Saude ocupacional completa", "text": "ASO, CAT, afastamentos, exames, treinamentos NR, EPI/EPC, PGR, eSocial SST, bem-estar anonimo da equipe e app do funcionario. Tudo em um painel."},
            {"small": "Farmacia e Hospital", "title": "Gestao e demanda futura", "text": "Controle farmaceutico, demanda regional, integracao epidemiologica. Gestao hospitalar de leitos, triagem, atendimento e pressao assistencial."},
            {"small": "Governo", "title": "Sala de situacao", "text": "Alertas oficiais, IBGE, InfoDengue, InfoGripe, DATASUS, matriz de decisao, auditoria e contratos anuais."},
        ],
        "enterprise": {
            "eyebrow": "Ambiente SST e Empresas",
            "title": "O SST mais completo do mercado, com bem-estar e app do funcionario incluidos.",
            "lead": "O ambiente empresarial do SolusCRT vai alem do cumprimento legal. Une a gestao SST completa com o bem-estar real da equipe e um app que coloca o funcionario no centro do proprio cuidado. Tudo isso conectado ao radar epidemiologico que antecipa o que vem antes do pico.",
            "items": [
                {"title": "SST completo e eSocial", "text": "ASO digital, CAT, afastamentos, exames, treinamentos NR, EPI/EPC, postos de trabalho S-2240, riscos e PGR, documentos e conformidade. Integracao eSocial SST com painel de status em tempo real."},
                {"title": "Bem-estar da Equipe", "text": "Check-ins anonimos de humor, saude fisica, saude mental, estresse e satisfacao no trabalho. A empresa enxerga tendencias agregadas — o nome do funcionario so aparece se ele voluntariamente solicitar contato de apoio."},
                {"title": "App do Funcionario", "text": "O funcionario acessa o proprio ASO digitalmente, faz solicitacoes, recebe notificacoes de exames e treinamentos e envia check-ins de bem-estar. Mais autonomia, menos papel, mais engajamento."},
            ],
            "metrics": [
                {"value": "37 NRs", "text": "consulta tecnica de conformidade para seguranca e saude no trabalho"},
                {"value": "eSocial SST", "text": "integracao com S-2220, S-2240, S-2210 e eventos SST com painel de conformidade"},
                {"value": "15 dias gratis", "text": "teste completo sem cartao de credito — todos os modulos ativos desde o primeiro acesso"},
            ],
        },
        "matrix": [
            {"label": "SST", "title": "Gestao ocupacional", "text": "ASO, CAT, afastamentos, exames, treinamentos NR, EPI/EPC, PGR, postos S-2240 e eSocial SST integrados em um painel de conformidade."},
            {"label": "Bem-estar", "title": "Saude da equipe", "text": "Check-ins anonimos de humor, saude fisica, mental, estresse e satisfacao. Empresa ve agregados. Funcionario controla se quer ajuda."},
            {"label": "IA preditiva", "title": "Motor epidemiologico", "text": "Classifica sinais populacionais, estima doencas provaveis, mede crescimento e valida reducao gradual com serie temporal, agregados e fontes oficiais."},
            {"label": "Oficial", "title": "Brasil Oficial", "text": "IBGE/SIDRA, InfoDengue, InfoGripe, OpenDataSUS/DATASUS em camadas separadas, com data de coleta e fonte identificada."},
            {"label": "App funcionario", "title": "Engajamento ativo", "text": "Funcionario acessa ASO, faz solicitacoes, recebe notificacoes e envia check-ins de bem-estar diretamente pelo celular."},
            {"label": "Enterprise", "title": "SaaS multissetor", "text": "Ambientes separados para empresa, farmacia, hospital e governo. Controle de usuarios, dispositivos e acesso por perfil."},
        ],
        "values": {
            "eyebrow": "Valores SolusCRT",
            "title": "Tecnologia para proteger pessoas, nao apenas vender software.",
            "lead": "A SolusCRT nasce com uma responsabilidade clara: transformar dados em cuidado, antecipar riscos sem gerar alarme vazio e ajudar empresas, governos e populacao a agir com mais consciencia, velocidade e humanidade.",
            "items": [
                {"title": "Vida em primeiro lugar", "text": "Todo indicador, alerta e mapa existe para reduzir atraso, orientar cuidado e apoiar decisoes que preservem pessoas."},
                {"title": "Verdade antes de impacto", "text": "Separar sinal precoce, dado oficial e inferencia de IA e um compromisso para evitar conclusoes falsas."},
                {"title": "Privacidade como fundamento", "text": "Dados de saude exigem minimizacao, seguranca, transparencia e exibicao adequada ao perfil autorizado. O bem-estar e anonimo por design."},
                {"title": "Cooperacao institucional", "text": "O sistema foi pensado para unir populacao, empresas, hospitais, farmacias, laboratorios e governo sem confundir responsabilidades."},
                {"title": "Acesso social", "text": "O app da populacao e gratuito e simples, porque vigilancia inteligente comeca quando todos podem contribuir."},
                {"title": "Coragem operacional", "text": "A SolusCRT existe para antecipar problemas dificeis, mostrar territorios criticos e ajudar lideres a agir antes do pico."},
            ],
        },
        "app": {
            "eyebrow": "Dois apps. Um para a populacao, um para o funcionario.",
            "title": "Do cidadao ao colaborador: cada um com o app que precisa.",
            "lead": "O app da populacao coleta sintomas sem cadastro nominal, exige localizacao atual, mostra o radar local e recebe alertas oficiais — alimentando a inteligencia coletiva. O app do funcionario da acesso ao ASO digital, solicitacoes, notificacoes de exames e check-ins de bem-estar — colocando o cuidado na palma da mao de quem trabalha.",
            "app_store": "Baixar na App Store",
            "google_play": "Ver no Google Play",
            "risks": [
                {"title": "Radar local", "text": "Leitura por localizacao atual para a populacao."},
                {"title": "ASO digital", "text": "Funcionario acessa o proprio atestado no celular."},
                {"title": "Alertas oficiais", "text": "Comunicacao de governo direto no app da populacao."},
                {"title": "Bem-estar", "text": "Check-in anonimo de humor e saude para o funcionario."},
            ],
        },
        "cta": {
            "title": "Teste o SolusCRT gratis por 15 dias. Sem cartao de credito.",
            "lead": "Todos os modulos ativos desde o primeiro acesso: SST completo, bem-estar da equipe, app do funcionario e radar epidemiologico com IA. Ou fale com o comercial e veja uma demonstracao completa da plataforma.",
        },
        "footer": "SolusCRT Saude. Gestao SST, bem-estar da equipe, inteligencia epidemiologica e SaaS multissetor.",
        "footer_links": {
            "privacy": "Privacidade",
            "terms": "Termos",
            "security": "Seguranca",
            "methodology": "Metodologia",
            "support": "Suporte",
        },
    },
    "en": {
        "title": "SolusCRT Health | Occupational health management, epidemiology and team wellness",
        "description": "SolusCRT Health is a complete health SaaS: occupational safety, medical certificates, eSocial, anonymous team wellness, employee app, AI epidemiological radar, pharmacy, hospital and government. Free 15-day trial.",
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
        "hero_eyebrow": "OSH, team wellness and epidemiological intelligence in one platform",
        "hero_title": "Complete occupational health management with AI that anticipates outbreaks.",
        "hero_title_desktop_lines": ["Complete occupational", "health management", "with AI that", "anticipates outbreaks."],
        "hero_title_lines": ["Complete occupational", "health management", "with AI that", "anticipates outbreaks."],
        "hero_lead": "SolusCRT Health is the SaaS platform that unites complete occupational safety, anonymous team wellness, an employee app and an AI-powered epidemiological radar. From medical certificates to eSocial, from anonymous mood check-ins to outbreak anticipation 7 to 10 days before official data. Free 15-day trial.",
        "actions": {
            "presentation": "View full presentation",
            "app": "Download population app",
            "sales": "Talk to sales",
            "open_presentation": "Open full presentation",
            "meeting": "Request a meeting",
        },
        "proofs": [
            {"title": "Complete OSH in one dashboard", "text": "Medical certificates, incident reports, leave management, exams, NR training, PPE/EPC, PGR, workstation profiles, eSocial OSH and compliance — all integrated, no separate spreadsheet."},
            {"title": "Team wellness without exposing employees", "text": "Anonymous check-ins on mood, physical health, mental health, stress and job satisfaction. The company sees aggregates. Names only appear if the employee voluntarily asks for support."},
            {"title": "AI that anticipates, not just notifies", "text": "The epidemiological radar crosses population signals, official Brazilian sources and internal data to anticipate outbreaks 7 to 10 days before the confirmed peak."},
        ],
        "chips": ["Full OSH + eSocial", "Team wellness", "Employee app", "15-day free trial"],
        "metrics": [
            {"value": "OSH", "text": "medical certificates, incident reports, leave, exams, NR training, PPE/EPC, PGR and eSocial in one dashboard"},
            {"value": "Wellness", "text": "anonymous check-ins on mood, physical health, mental health, stress and job satisfaction"},
            {"value": "AI + 7-10 days", "text": "outbreak anticipation before official data, with gradual validation by trend, aggregates and Brazilian sources"},
            {"value": "LGPD", "text": "governance, minimization, environment segregation and wellness anonymization"},
        ],
        "differential": {
            "title": "OSH that protects today. AI that anticipates what comes tomorrow.",
            "lead": "Most platforms do OSH or epidemiology. SolusCRT unites both: complete occupational health management with a territorial intelligence engine that identifies risk before it reaches HR or social security.",
            "traditional_title": "Traditional OSH management",
            "traditional_items": [
                "Medical certificates on paper or in isolated systems, disconnected from real absences and team health.",
                "eSocial OSH filled in a rush, with no real-time compliance visibility.",
                "Outbreaks noticed only after absenteeism has already risen — no chance to act early.",
            ],
            "solus_title": "SolusCRT OSH + AI",
            "solus_items": [
                "Complete integrated OSH: digital medical certificates, incident reports, leave management, NR training, PPE/EPC, PGR and eSocial with real-time compliance dashboard.",
                "Anonymous team wellness with mood, health and satisfaction check-ins — the company sees trends, not names.",
                "Epidemiological AI crosses population signals, official data and internal behavior to alert 7 to 10 days before the peak.",
            ],
        },
        "ecosystem_title": "One platform. Four environments. One goal: protect people.",
        "ecosystem_lead": "OSH for companies, management for pharmacies and hospitals, situation room for government and a free app for the population — all connected by the same epidemiological intelligence layer.",
        "slides": [
            {"small": "Population", "title": "Free app", "text": "Anonymous symptom reporting, local radar, risk map and official alerts. The social sensor that feeds collective intelligence."},
            {"small": "OSH and Companies", "title": "Complete occupational health", "text": "Medical certificates, incident reports, leave, exams, NR training, PPE/EPC, PGR, eSocial OSH, anonymous team wellness and employee app. All in one dashboard."},
            {"small": "Pharmacy and Hospital", "title": "Management and future demand", "text": "Pharmaceutical management, regional demand, epidemiological integration. Hospital management of beds, triage, care and care pressure."},
            {"small": "Government", "title": "Situation room", "text": "Official alerts, IBGE, InfoDengue, InfoGripe, DATASUS, decision matrix, audit trail and annual contracts."},
        ],
        "enterprise": {
            "eyebrow": "OSH and Company Environment",
            "title": "The most complete OSH on the market, with team wellness and employee app included.",
            "lead": "SolusCRT's company environment goes beyond legal compliance. It combines complete OSH management with real team wellness and an app that puts employees at the center of their own care. All connected to the epidemiological radar that anticipates risk before the peak.",
            "items": [
                {"title": "Complete OSH and eSocial", "text": "Digital medical certificates, incident reports, leave management, exams, NR training, PPE/EPC, workstation profiles S-2240, hazards and PGR, documents and compliance. eSocial OSH integration with real-time status dashboard."},
                {"title": "Team Wellness", "text": "Anonymous check-ins on mood, physical health, mental health, stress and job satisfaction. The company sees aggregated trends — employee names only appear if they voluntarily request support contact."},
                {"title": "Employee App", "text": "Employees access their own medical certificate digitally, make requests, receive exam and training notifications and submit wellness check-ins. More autonomy, less paper, more engagement."},
            ],
            "metrics": [
                {"value": "37 NRs", "text": "technical compliance reference for occupational health and safety"},
                {"value": "eSocial OSH", "text": "integration with S-2220, S-2240, S-2210 and OSH events with compliance dashboard"},
                {"value": "15-day free trial", "text": "full access without credit card — all modules active from day one"},
            ],
        },
        "matrix": [
            {"label": "OSH", "title": "Occupational management", "text": "Medical certificates, incident reports, leave, exams, NR training, PPE/EPC, PGR, workstation profiles and eSocial OSH in one compliance dashboard."},
            {"label": "Wellness", "title": "Team health", "text": "Anonymous check-ins on mood, physical health, mental health, stress and satisfaction. Company sees aggregates. Employees control whether they want help."},
            {"label": "Predictive AI", "title": "Epidemiological engine", "text": "Classifies population signals, estimates likely diseases, measures growth and validates gradual decline with time series, aggregates and official sources."},
            {"label": "Official", "title": "Official Brazil", "text": "IBGE/SIDRA, InfoDengue, InfoGripe and OpenDataSUS/DATASUS in separate layers, with identified collection date and source."},
            {"label": "Employee app", "title": "Active engagement", "text": "Employees access their medical certificate, make requests, receive notifications and submit wellness check-ins directly from their phone."},
            {"label": "Enterprise", "title": "Multi-sector SaaS", "text": "Separate environments for company, pharmacy, hospital and government. Control over users, devices and role-based access."},
        ],
        "values": {
            "eyebrow": "SolusCRT Values",
            "title": "Technology to protect people, not just sell software.",
            "lead": "SolusCRT was born with a clear responsibility: turn data into care, anticipate risks without empty alarm and help companies, governments and people act with more awareness, speed and humanity.",
            "items": [
                {"title": "Life first", "text": "Every indicator, alert and map exists to reduce delay, guide care and support decisions that preserve people."},
                {"title": "Truth before impact", "text": "Separating early signal, official data and AI inference is a commitment to avoid false conclusions."},
                {"title": "Privacy as foundation", "text": "Health data requires minimization, security, transparency and display appropriate to each authorized profile. Wellness is anonymous by design."},
                {"title": "Institutional cooperation", "text": "The system was designed to connect people, companies, hospitals, pharmacies, laboratories and government without blurring responsibilities."},
                {"title": "Social access", "text": "The population app is free and simple, because intelligent surveillance begins when everyone can contribute."},
                {"title": "Operational courage", "text": "SolusCRT exists to anticipate hard problems, reveal critical territories and help leaders act before the peak."},
            ],
        },
        "app": {
            "eyebrow": "Two apps. One for the population, one for employees.",
            "title": "From citizen to employee: each with the app they need.",
            "lead": "The population app collects symptoms without nominal registration, requires current location, shows the local radar and receives official alerts — feeding collective intelligence. The employee app gives access to digital medical certificates, requests, exam notifications and wellness check-ins — putting care in the hands of every worker.",
            "app_store": "Download on the App Store",
            "google_play": "View on Google Play",
            "risks": [
                {"title": "Local radar", "text": "Location-based reading for the population."},
                {"title": "Digital certificate", "text": "Employee accesses their own medical certificate on their phone."},
                {"title": "Official alerts", "text": "Government communication directly in the population app."},
                {"title": "Wellness", "text": "Anonymous mood and health check-in for employees."},
            ],
        },
        "cta": {
            "title": "Try SolusCRT free for 15 days. No credit card required.",
            "lead": "All modules active from day one: complete OSH, team wellness, employee app and AI epidemiological radar. Or talk to sales and see a full platform demo.",
        },
        "footer": "SolusCRT Health. OSH management, team wellness, epidemiological intelligence and multi-sector SaaS.",
        "footer_links": {
            "privacy": "Privacy",
            "terms": "Terms",
            "security": "Security",
            "methodology": "Methodology",
            "support": "Support",
        },
    },
    "es": {
        "title": "SolusCRT Salud | Gestion de salud ocupacional, epidemiologia y bienestar laboral",
        "description": "SolusCRT Salud es una plataforma SaaS completa: SST, certificados medicos, eSocial, bienestar anonimo del equipo, app del trabajador, radar epidemiologico con IA, farmacia, hospital y gobierno. Prueba gratuita de 15 dias.",
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
        "hero_eyebrow": "SST, bienestar laboral e inteligencia epidemiologica en una plataforma",
        "hero_title": "Gestion completa de salud ocupacional con IA que anticipa brotes.",
        "hero_title_desktop_lines": ["Gestion completa de", "salud ocupacional", "con IA que", "anticipa brotes."],
        "hero_title_lines": ["Gestion completa", "de salud ocupacional", "con IA que", "anticipa brotes."],
        "hero_lead": "SolusCRT Salud es la plataforma SaaS que une SST completo, bienestar anonimo del equipo, app del trabajador y radar epidemiologico con IA. Del certificado medico al eSocial, del check-in anonimo de humor a la anticipacion de brotes 7 a 10 dias antes del dato oficial. Prueba gratuita de 15 dias.",
        "actions": {
            "presentation": "Ver presentacion completa",
            "app": "Descargar app poblacional",
            "sales": "Hablar con ventas",
            "open_presentation": "Abrir presentacion completa",
            "meeting": "Solicitar reunion",
        },
        "proofs": [
            {"title": "SST completo en un panel", "text": "Certificados medicos, registros de accidente, ausencias, examenes, capacitaciones NR, EPI/EPC, PGR, puestos S-2240, eSocial SST y conformidad — todo integrado, sin planilla separada."},
            {"title": "Bienestar sin exponer al trabajador", "text": "Check-ins anonimos de humor, salud fisica, salud mental, estres y satisfaccion laboral. La empresa ve agregados. El nombre solo aparece si el trabajador solicita voluntariamente apoyo."},
            {"title": "IA que anticipa, no solo notifica", "text": "El radar epidemiologico cruza senales de la poblacion, fuentes oficiales brasilenas y datos internos para anticipar brotes 7 a 10 dias antes del pico confirmado."},
        ],
        "chips": ["SST completo + eSocial", "Bienestar del equipo", "App del trabajador", "15 dias gratis"],
        "metrics": [
            {"value": "SST", "text": "certificados, accidentes, ausencias, examenes, capacitaciones NR, EPI/EPC, PGR y eSocial en un unico panel"},
            {"value": "Bienestar", "text": "check-ins anonimos de humor, salud fisica, mental, estres y satisfaccion laboral"},
            {"value": "IA + 7-10 dias", "text": "anticipacion de brotes antes del dato oficial, con validacion gradual por tendencia, agregados y fuentes brasilenas"},
            {"value": "LGPD", "text": "gobernanza, minimizacion, segregacion de ambientes y anonimizacion del bienestar"},
        ],
        "differential": {
            "title": "SST que protege hoy. IA que anticipa lo que viene manana.",
            "lead": "La mayoria de las plataformas hacen SST o epidemiologia. SolusCRT une los dos: gestion ocupacional completa con el motor de inteligencia territorial que identifica riesgo antes de que llegue a RRHH o a la seguridad social.",
            "traditional_title": "Gestion tradicional de SST",
            "traditional_items": [
                "Certificados en papel o en sistemas aislados, sin conexion con ausencias reales y salud del equipo.",
                "eSocial SST completado con urgencia, sin visibilidad de conformidad en tiempo real.",
                "Brotes detectados cuando el ausentismo ya subio — sin posibilidad de actuar antes.",
            ],
            "solus_title": "SolusCRT SST + IA",
            "solus_items": [
                "SST completo integrado: certificados digitales, registros de accidente, ausencias, NR, EPI/EPC, PGR y eSocial con panel de conformidad en tiempo real.",
                "Bienestar anonimo del equipo con check-ins de humor, salud y satisfaccion — la empresa ve tendencias, no nombres.",
                "IA epidemiologica cruza senales poblacionales, datos oficiales y comportamiento interno para alertar 7 a 10 dias antes del pico.",
            ],
        },
        "ecosystem_title": "Una plataforma. Cuatro ambientes. Un objetivo: proteger personas.",
        "ecosystem_lead": "SST para empresas, gestion para farmacias y hospitales, sala de situacion para gobierno y app gratuita para la poblacion — conectados por la misma capa de inteligencia epidemiologica.",
        "slides": [
            {"small": "Poblacion", "title": "App gratuita", "text": "Envio anonimo de sintomas, radar local, mapa de riesgo y alertas oficiales. El sensor social que alimenta la inteligencia colectiva."},
            {"small": "SST y Empresas", "title": "Salud ocupacional completa", "text": "Certificados, accidentes, ausencias, examenes, capacitaciones NR, EPI/EPC, PGR, eSocial SST, bienestar anonimo del equipo y app del trabajador. Todo en un panel."},
            {"small": "Farmacia y Hospital", "title": "Gestion y demanda futura", "text": "Control farmaceutico, demanda regional, integracion epidemiologica. Gestion hospitalaria de camas, triaje, atencion y presion asistencial."},
            {"small": "Gobierno", "title": "Sala de situacion", "text": "Alertas oficiales, IBGE, InfoDengue, InfoGripe, DATASUS, matriz de decision, auditoria y contratos anuales."},
        ],
        "enterprise": {
            "eyebrow": "Ambiente SST y Empresas",
            "title": "El SST mas completo del mercado, con bienestar y app del trabajador incluidos.",
            "lead": "El ambiente empresarial de SolusCRT va mas alla del cumplimiento legal. Une la gestion SST completa con el bienestar real del equipo y una app que pone al trabajador en el centro de su propio cuidado. Todo conectado al radar epidemiologico que anticipa el riesgo antes del pico.",
            "items": [
                {"title": "SST completo y eSocial", "text": "Certificados medicos digitales, registros de accidente, ausencias, examenes, capacitaciones NR, EPI/EPC, puestos S-2240, riesgos y PGR, documentos y conformidad. Integracion eSocial SST con panel de estado en tiempo real."},
                {"title": "Bienestar del Equipo", "text": "Check-ins anonimos de humor, salud fisica, salud mental, estres y satisfaccion laboral. La empresa ve tendencias agregadas — el nombre del trabajador solo aparece si voluntariamente solicita contacto de apoyo."},
                {"title": "App del Trabajador", "text": "El trabajador accede a su certificado medico digitalmente, realiza solicitudes, recibe notificaciones de examenes y capacitaciones y envia check-ins de bienestar. Mas autonomia, menos papel, mas compromiso."},
            ],
            "metrics": [
                {"value": "37 NRs", "text": "consulta tecnica de conformidad para seguridad y salud en el trabajo"},
                {"value": "eSocial SST", "text": "integracion con S-2220, S-2240, S-2210 y eventos SST con panel de conformidad"},
                {"value": "15 dias gratis", "text": "prueba completa sin tarjeta de credito — todos los modulos activos desde el primer acceso"},
            ],
        },
        "matrix": [
            {"label": "SST", "title": "Gestion ocupacional", "text": "Certificados, accidentes, ausencias, examenes, capacitaciones NR, EPI/EPC, PGR, puestos S-2240 y eSocial SST en un panel de conformidad."},
            {"label": "Bienestar", "title": "Salud del equipo", "text": "Check-ins anonimos de humor, salud fisica, mental, estres y satisfaccion. La empresa ve agregados. El trabajador controla si quiere ayuda."},
            {"label": "IA predictiva", "title": "Motor epidemiologico", "text": "Clasifica senales poblacionales, estima enfermedades probables, mide crecimiento y valida la reduccion gradual con serie temporal, agregados y fuentes oficiales."},
            {"label": "Oficial", "title": "Brasil Oficial", "text": "IBGE/SIDRA, InfoDengue, InfoGripe y OpenDataSUS/DATASUS en capas separadas, con fecha de recoleccion y fuente identificada."},
            {"label": "App trabajador", "title": "Compromiso activo", "text": "El trabajador accede a su certificado, realiza solicitudes, recibe notificaciones y envia check-ins de bienestar directamente desde el celular."},
            {"label": "Enterprise", "title": "SaaS multisectorial", "text": "Ambientes separados para empresa, farmacia, hospital y gobierno. Control de usuarios, dispositivos y acceso por perfil."},
        ],
        "values": {
            "eyebrow": "Valores SolusCRT",
            "title": "Tecnologia para proteger personas, no solo vender software.",
            "lead": "SolusCRT nace con una responsabilidad clara: transformar datos en cuidado, anticipar riesgos sin alarma vacia y ayudar a empresas, gobiernos y poblacion a actuar con mas conciencia, velocidad y humanidad.",
            "items": [
                {"title": "Vida en primer lugar", "text": "Todo indicador, alerta y mapa existe para reducir retraso, orientar cuidado y apoyar decisiones que preserven personas."},
                {"title": "Verdad antes que impacto", "text": "Separar senal temprana, dato oficial e inferencia de IA es un compromiso para evitar conclusiones falsas."},
                {"title": "Privacidad como fundamento", "text": "Los datos de salud exigen minimizacion, seguridad, transparencia y exhibicion adecuada al perfil autorizado. El bienestar es anonimo por diseno."},
                {"title": "Cooperacion institucional", "text": "El sistema fue pensado para unir poblacion, empresas, hospitales, farmacias, laboratorios y gobierno sin confundir responsabilidades."},
                {"title": "Acceso social", "text": "La app poblacional es gratuita y simple, porque la vigilancia inteligente comienza cuando todos pueden contribuir."},
                {"title": "Coraje operacional", "text": "SolusCRT existe para anticipar problemas dificiles, mostrar territorios criticos y ayudar a lideres a actuar antes del pico."},
            ],
        },
        "app": {
            "eyebrow": "Dos apps. Una para la poblacion, una para el trabajador.",
            "title": "Del ciudadano al colaborador: cada uno con la app que necesita.",
            "lead": "La app poblacional recoge sintomas sin registro nominal, exige ubicacion actual, muestra el radar local y recibe alertas oficiales — alimentando la inteligencia colectiva. La app del trabajador da acceso al certificado medico digital, solicitudes, notificaciones de examenes y check-ins de bienestar — poniendo el cuidado en la palma de la mano de quien trabaja.",
            "app_store": "Descargar en App Store",
            "google_play": "Ver en Google Play",
            "risks": [
                {"title": "Radar local", "text": "Lectura por ubicacion actual para la poblacion."},
                {"title": "Certificado digital", "text": "El trabajador accede a su certificado en el celular."},
                {"title": "Alertas oficiales", "text": "Comunicacion de gobierno directo en la app poblacional."},
                {"title": "Bienestar", "text": "Check-in anonimo de humor y salud para el trabajador."},
            ],
        },
        "cta": {
            "title": "Prueba SolusCRT gratis por 15 dias. Sin tarjeta de credito.",
            "lead": "Todos los modulos activos desde el primer acceso: SST completo, bienestar del equipo, app del trabajador y radar epidemiologico con IA. O habla con ventas y solicita una demostracion completa de la plataforma.",
        },
        "footer": "SolusCRT Salud. Gestion SST, bienestar del equipo, inteligencia epidemiologica y SaaS multisectorial.",
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
            "title": "Gestao de saude completa: do ASO ao surto que ainda nao chegou.",
            "body": "O SolusCRT Saude une gestao SST completa, bem-estar anonimo da equipe, app do funcionario e radar epidemiologico com IA — tudo em uma plataforma. Para empresas que querem proteger quem trabalha hoje e antecipar o que vem amanha.",
            "labels": {"resp": "Respiratorio", "deng": "Arbovirose", "covid": "Viral"},
        },
        "problem": {
            "eyebrow": "Problema",
            "title": "SST em papel, bem-estar invisivel e surtos percebidos tarde demais.",
            "cards": [
                {"title": "ASO e SST ainda sao analogicos", "text": "ASO em papel, CAT preenchido no susto, EPI sem rastreabilidade, PGR desatualizado. O cumprimento legal vira correria e o eSocial SST fica em aberto."},
                {"title": "O funcionario esta desconectado", "text": "Nao acessa o proprio ASO, nao recebe lembrete de exame, nao tem canal para sinalizar que nao esta bem. O cuidado e unilateral."},
                {"title": "Bem-estar e um ponto cego", "text": "Humor, estresse, satisfacao e saude mental raramente sao monitorados. Quando o absenteismo sobe, o problema ja estava la ha semanas."},
                {"title": "Surtos chegam depois do pico", "text": "Dados oficiais sao essenciais para confirmacao, mas chegam apos ciclos de notificacao. A empresa reage quando o afastamento ja esta pressionado."},
            ],
        },
        "solution": {
            "eyebrow": "Solucao",
            "title": "SST completo + bem-estar + IA epidemiologica. Em um unico painel.",
            "body": "O SolusCRT resolve os tres pontos cegos simultaneamente: gestao SST integrada com eSocial, bem-estar anonimo da equipe com check-ins digitais e radar de IA que antecipa surtos 7 a 10 dias antes do dado oficial.",
            "cards": [
                {"title": "SST + eSocial", "text": "ASO, CAT, afastamentos, NR, EPI/EPC, PGR e conformidade."},
                {"title": "Bem-estar", "text": "Check-ins anonimos de humor, saude e satisfacao."},
                {"title": "App do funcionario", "text": "ASO digital, solicitacoes e notificacoes no celular."},
                {"title": "IA epidemiologica", "text": "Radar territorial com IBGE, InfoDengue, InfoGripe e DATASUS."},
            ],
        },
        "ecosystem": {
            "eyebrow": "Ecossistema",
            "title": "Uma plataforma. Quatro ambientes especializados.",
            "cards": [
                {"title": "SST e Empresas", "text": "SST completo, bem-estar anonimo, app do funcionario, dashboard de funcionarios, KPIs de absenteismo e integracao eSocial SST. Teste gratis por 15 dias."},
                {"title": "Farmacia", "text": "Gestao farmaceutica, controle de demanda regional e integracao epidemiologica para antecipar demanda de medicamentos e insumos."},
                {"title": "Hospital", "text": "Gestao hospitalar de leitos, atendimento, triagem, pressao assistencial e equipes — conectado ao radar epidemiologico."},
                {"title": "Governo", "text": "Sala de situacao epidemiologica, alertas oficiais, matriz de decisao, auditoria, contratos anuais e fontes brasileiras oficiais."},
            ],
        },
        "differential": {
            "eyebrow": "Diferencial",
            "title": "O unico SaaS que une SST legal, bem-estar humano e IA epidemiologica.",
            "body": "Plataformas de SST nao tem radar de surto. Sistemas de epidemiologia nao tem ASO nem eSocial. O SolusCRT e o primeiro a unir os tres — para que a empresa proteja sua forca de trabalho antes do problema chegar ao INSS, ao pronto-socorro ou ao absenteismo.",
            "quote": "SST em dia. Equipe bem monitorada. Surto antecipado. Tudo em uma plataforma com 15 dias gratis.",
        },
        "governance": {
            "eyebrow": "Governanca",
            "title": "Seguranca, LGPD e anonimato como fundamentos do produto.",
            "cards": [
                {"title": "Ambientes separados", "text": "SST, farmacia, hospital e governo em ambientes distintos, com login, permissao e auditoria proprios."},
                {"title": "LGPD para dados SST", "text": "ASO, CAT, exames e afastamentos sao dados sensiveis. Minimizacao, finalidade, controle de acesso e auditoria por operacao."},
                {"title": "Bem-estar anonimo por design", "text": "Check-ins de humor, saude e satisfacao nunca expoe o nome do funcionario para a empresa. Anonimato e o padrao — o contato e sempre voluntario."},
                {"title": "Antifraude epidemiologico", "text": "Sinais populacionais passam por controle de dispositivo, rede, repeticao e localizacao. Intensidade so cai apos 10 dias sem novos sinais e quando tendencia, agregados e fontes oficiais sustentam queda real."},
            ],
        },
        "values": {
            "eyebrow": "Valores",
            "title": "Valores que fazem a tecnologia merecer confianca.",
            "body": "O SolusCRT foi pensado para cooperar com pessoas e instituicoes: proteger vidas, antecipar riscos, respeitar privacidade, comunicar com responsabilidade e ajudar lideres a agir sem distorcer a verdade.",
            "cards": [
                {"title": "Vida primeiro", "text": "SST, bem-estar e IA existem para reduzir dano real a pessoas reais."},
                {"title": "Verdade antes de impacto", "text": "Sinal precoce, dado oficial e IA sempre separados e identificados."},
                {"title": "Privacidade e anonimato", "text": "Bem-estar anonimo por design. Dados SST com minimizacao e LGPD."},
                {"title": "Cooperacao", "text": "Empresa, funcionario, governo e populacao atuando na mesma rede de cuidado."},
            ],
        },
        "app": {
            "eyebrow": "Dois apps integrados",
            "title": "App da populacao e app do funcionario: cada um no lugar certo.",
            "body": "O app da populacao coleta sintomas sem cadastro nominal, mostra o radar local e recebe alertas oficiais — alimentando o motor epidemiologico. O app do funcionario da acesso ao ASO digital, permite solicitacoes, envia notificacoes de exames e coleta check-ins de bem-estar anonimos. Dois canais. Uma plataforma.",
            "quote": "App da populacao: gratis e anonimo. App do funcionario: cuidado ativo no bolso.",
        },
        "closing": {
            "eyebrow": "Fechamento",
            "title": "SST em dia, equipe cuidada, surto antecipado. Comece em 15 minutos.",
            "body": "O SolusCRT e a unica plataforma que entrega conformidade SST, bem-estar real da equipe e antecipacao epidemiologica em um unico ambiente. Teste gratis por 15 dias — todos os modulos ativos, sem cartao de credito. Ou agende uma conversa com o comercial e veja uma demonstracao completa.",
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
            "title": "Complete health management: from medical certificates to outbreaks that haven't arrived yet.",
            "body": "SolusCRT Health unites complete OSH management, anonymous team wellness, an employee app and an AI epidemiological radar — all in one platform. For organizations that want to protect workers today and anticipate what comes tomorrow.",
            "labels": {"resp": "Respiratory", "deng": "Arbovirus", "covid": "Viral"},
        },
        "problem": {
            "eyebrow": "Problem",
            "title": "Paper-based OSH, invisible wellness and outbreaks noticed too late.",
            "cards": [
                {"title": "OSH is still analog", "text": "Medical certificates on paper, incident reports filled in a rush, PPE without traceability, outdated safety plans. Legal compliance becomes firefighting and eSocial OSH stays pending."},
                {"title": "The employee is disconnected", "text": "No digital access to their own medical certificate, no exam reminders, no channel to flag when they are not doing well. Care is one-directional."},
                {"title": "Wellness is a blind spot", "text": "Mood, stress, satisfaction and mental health are rarely monitored. When absenteeism rises, the problem was already there weeks earlier."},
                {"title": "Outbreaks arrive after the peak", "text": "Official data is essential for confirmation, but it arrives after notification cycles. The company reacts when leave is already under pressure."},
            ],
        },
        "solution": {
            "eyebrow": "Solution",
            "title": "Complete OSH + wellness + epidemiological AI. In one single dashboard.",
            "body": "SolusCRT addresses all three blind spots simultaneously: integrated OSH management with eSocial, anonymous team wellness with digital check-ins and an AI radar that anticipates outbreaks 7 to 10 days before official data.",
            "cards": [
                {"title": "OSH + eSocial", "text": "Medical certificates, incidents, leave, NR training, PPE/EPC, PGR and compliance."},
                {"title": "Wellness", "text": "Anonymous check-ins on mood, health and satisfaction."},
                {"title": "Employee app", "text": "Digital medical certificate, requests and notifications on the phone."},
                {"title": "Epidemiological AI", "text": "Territorial radar with IBGE, InfoDengue, InfoGripe and DATASUS."},
            ],
        },
        "ecosystem": {
            "eyebrow": "Ecosystem",
            "title": "One platform. Four specialized environments.",
            "cards": [
                {"title": "OSH and Companies", "text": "Complete OSH, anonymous wellness, employee app, workforce dashboard, absenteeism KPIs and eSocial OSH integration. Free 15-day trial."},
                {"title": "Pharmacy", "text": "Pharmaceutical management, regional demand control and epidemiological integration to anticipate medication and supply demand."},
                {"title": "Hospital", "text": "Hospital management of beds, care, triage, care pressure and teams — connected to the epidemiological radar."},
                {"title": "Government", "text": "Epidemiological situation room, official alerts, decision matrix, audit trail, annual contracts and official Brazilian sources."},
            ],
        },
        "differential": {
            "eyebrow": "Differentiator",
            "title": "The only SaaS that unites legal OSH, human wellness and epidemiological AI.",
            "body": "OSH platforms do not have an outbreak radar. Epidemiology systems do not have medical certificates or eSocial. SolusCRT is the first to unite all three — so organizations can protect their workforce before the problem reaches social security, the emergency room or absenteeism charts.",
            "quote": "OSH compliant. Team monitored. Outbreak anticipated. One platform, 15-day free trial.",
        },
        "governance": {
            "eyebrow": "Governance",
            "title": "Security, LGPD and anonymity as product foundations.",
            "cards": [
                {"title": "Separated environments", "text": "OSH, pharmacy, hospital and government in distinct environments, each with its own login, permissions and audit trail."},
                {"title": "LGPD for OSH data", "text": "Medical certificates, incident reports, exams and leave records are sensitive data. Minimization, purpose, access control and per-operation audit trail."},
                {"title": "Wellness anonymous by design", "text": "Mood, health and satisfaction check-ins never expose the employee's name to the company. Anonymity is the default — contact is always voluntary."},
                {"title": "Epidemiological anti-fraud", "text": "Population signals go through device, network, repetition and location controls. Intensity only decreases after 10 days without new signals and when trend, aggregates and official sources support real decline."},
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
            "body": "The population app collects symptoms without nominal registration, shows the local radar and receives official alerts — feeding the epidemiological engine. The employee app gives access to the digital medical certificate, allows requests, sends exam notifications and collects anonymous wellness check-ins. Two channels. One platform.",
            "quote": "Population app: free and anonymous. Employee app: active care in their pocket.",
        },
        "closing": {
            "eyebrow": "Closing",
            "title": "OSH compliant, team cared for, outbreak anticipated. Get started in 15 minutes.",
            "body": "SolusCRT is the only platform that delivers OSH compliance, real team wellness and epidemiological anticipation in a single environment. Free 15-day trial — all modules active, no credit card. Or schedule a conversation with sales and see a full platform demo.",
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
            "title": "Gestion completa de salud: del certificado medico al brote que aun no llego.",
            "body": "SolusCRT Salud une gestion SST completa, bienestar anonimo del equipo, app del trabajador y radar epidemiologico con IA — todo en una plataforma. Para organizaciones que quieren proteger a quienes trabajan hoy y anticipar lo que viene manana.",
            "labels": {"resp": "Respiratorio", "deng": "Arbovirosis", "covid": "Viral"},
        },
        "problem": {
            "eyebrow": "Problema",
            "title": "SST en papel, bienestar invisible y brotes detectados tarde.",
            "cards": [
                {"title": "El SST sigue siendo analogico", "text": "Certificados en papel, registros de accidente completados con urgencia, EPI sin trazabilidad, plan de prevencion desactualizado. El cumplimiento legal se convierte en una carrera y el eSocial SST queda pendiente."},
                {"title": "El trabajador esta desconectado", "text": "Sin acceso digital a su propio certificado, sin recordatorio de examen, sin canal para senalar que no esta bien. El cuidado es unidireccional."},
                {"title": "El bienestar es un punto ciego", "text": "El humor, el estres, la satisfaccion y la salud mental rara vez se monitorean. Cuando el ausentismo sube, el problema ya estaba ahi semanas antes."},
                {"title": "Los brotes llegan despues del pico", "text": "Los datos oficiales son esenciales para la confirmacion, pero llegan despues de ciclos de notificacion. La empresa reacciona cuando las ausencias ya estan presionadas."},
            ],
        },
        "solution": {
            "eyebrow": "Solucion",
            "title": "SST completo + bienestar + IA epidemiologica. En un unico panel.",
            "body": "SolusCRT aborda los tres puntos ciegos simultaneamente: gestion SST integrada con eSocial, bienestar anonimo del equipo con check-ins digitales y radar de IA que anticipa brotes 7 a 10 dias antes del dato oficial.",
            "cards": [
                {"title": "SST + eSocial", "text": "Certificados, accidentes, ausencias, NR, EPI/EPC, PGR y conformidad."},
                {"title": "Bienestar", "text": "Check-ins anonimos de humor, salud y satisfaccion."},
                {"title": "App del trabajador", "text": "Certificado digital, solicitudes y notificaciones en el celular."},
                {"title": "IA epidemiologica", "text": "Radar territorial con IBGE, InfoDengue, InfoGripe y DATASUS."},
            ],
        },
        "ecosystem": {
            "eyebrow": "Ecosistema",
            "title": "Una plataforma. Cuatro ambientes especializados.",
            "cards": [
                {"title": "SST y Empresas", "text": "SST completo, bienestar anonimo, app del trabajador, panel de empleados, KPIs de ausentismo e integracion eSocial SST. Prueba gratuita de 15 dias."},
                {"title": "Farmacia", "text": "Gestion farmaceutica, control de demanda regional e integracion epidemiologica para anticipar demanda de medicamentos e insumos."},
                {"title": "Hospital", "text": "Gestion hospitalaria de camas, atencion, triaje, presion asistencial y equipos — conectado al radar epidemiologico."},
                {"title": "Gobierno", "text": "Sala de situacion epidemiologica, alertas oficiales, matriz de decision, auditoria, contratos anuales y fuentes brasilenas oficiales."},
            ],
        },
        "differential": {
            "eyebrow": "Diferencial",
            "title": "El unico SaaS que une SST legal, bienestar humano e IA epidemiologica.",
            "body": "Las plataformas de SST no tienen radar de brotes. Los sistemas de epidemiologia no tienen certificados medicos ni eSocial. SolusCRT es el primero en unir los tres — para que la organizacion proteja su fuerza laboral antes de que el problema llegue a la seguridad social, a urgencias o a los graficos de ausentismo.",
            "quote": "SST al dia. Equipo monitoreado. Brote anticipado. Una plataforma, 15 dias gratis.",
        },
        "governance": {
            "eyebrow": "Gobernanza",
            "title": "Seguridad, LGPD y anonimato como fundamentos del producto.",
            "cards": [
                {"title": "Ambientes separados", "text": "SST, farmacia, hospital y gobierno en ambientes distintos, cada uno con login, permisos y auditoria propios."},
                {"title": "LGPD para datos SST", "text": "Certificados, registros de accidente, examenes y ausencias son datos sensibles. Minimizacion, finalidad, control de acceso y auditoria por operacion."},
                {"title": "Bienestar anonimo por diseno", "text": "Los check-ins de humor, salud y satisfaccion nunca exponen el nombre del trabajador a la empresa. El anonimato es el estandar — el contacto es siempre voluntario."},
                {"title": "Antifraude epidemiologico", "text": "Las senales poblacionales pasan por controles de dispositivo, red, repeticion y ubicacion. La intensidad solo baja tras 10 dias sin nuevas senales y cuando tendencia, agregados y fuentes oficiales sostienen una reduccion real."},
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
            "body": "La app poblacional recoge sintomas sin registro nominal, muestra el radar local y recibe alertas oficiales — alimentando el motor epidemiologico. La app del trabajador da acceso al certificado medico digital, permite solicitudes, envia notificaciones de examenes y recoge check-ins de bienestar anonimos. Dos canales. Una plataforma.",
            "quote": "App poblacional: gratuita y anonima. App del trabajador: cuidado activo en el bolsillo.",
        },
        "closing": {
            "eyebrow": "Cierre",
            "title": "SST al dia, equipo cuidado, brote anticipado. Comienza en 15 minutos.",
            "body": "SolusCRT es la unica plataforma que entrega conformidad SST, bienestar real del equipo y anticipacion epidemiologica en un unico ambiente. Prueba gratuita de 15 dias — todos los modulos activos, sin tarjeta de credito. O agenda una conversacion con ventas y solicita una demostracion completa.",
            "meeting": "Solicitar demostracion comercial",
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
            "subtitle": "Como o SolusCRT Saude trata dados no app da populacao, no app do funcionario, no ambiente SST e na plataforma SaaS.",
            "sections": [
                ("Quem somos e escopo", "O SolusCRT Saude e uma plataforma SaaS completa de gestao em saude, com ambiente SST para empresas, gestao farmaceutica, gestao hospitalar, sala de situacao para governo e dois apps: o app da populacao (gratuito e anonimo) e o app do funcionario (vinculado a conta empresarial). Esta politica explica o tratamento de dados em todos esses contextos."),
                ("Resumo para usuarios do app da populacao", "No app publico, voce pode consultar radar, mapa e alertas e, se desejar, enviar sintomas de forma voluntaria e anonima. O app nao oferece diagnostico medico, prescricao, triagem individual, atendimento de emergencia ou substituicao de consulta profissional."),
                ("Resumo para usuarios do app do funcionario", "O app do funcionario e vinculado a conta empresarial contratante. Por meio dele, o funcionario acessa o proprio ASO digital, faz solicitacoes, recebe notificacoes de exames e treinamentos e envia check-ins de bem-estar. Check-ins de bem-estar sao anonimos por padrao — a empresa ve apenas dados agregados, nunca o nome associado ao check-in individual, salvo quando o proprio funcionario solicita contato de apoio."),
                ("Dados que podemos tratar", "Podemos tratar, conforme o contexto e o ambiente: sintomas selecionados; coordenadas de localizacao enquanto o app esta em uso; cidade, estado, bairro ou regiao aproximada; data e hora do envio; identificador tecnico aleatorio gerado pelo app; IP; tokens FCM de notificacao push; aceite de termos; dados de conta corporativa ou governamental; registros de acesso e auditoria. No ambiente SST: ASO, CAT, laudos de exames, afastamentos, treinamentos NR, EPI/EPC, postos de trabalho, riscos, PGR e registros eSocial SST — todos dados de saude sensiveis tratados com controles adicionais. No bem-estar: respostas anonimas de check-in de humor, saude fisica, saude mental, estresse e satisfacao no trabalho."),
                ("Dados sensiveis de saude — SST e bem-estar", "ASO, CAT, exames, afastamentos e qualquer dado de saude ocupacional sao dados sensiveis nos termos da LGPD. Sao tratados com minimizacao, finalidade especifica, controles de acesso por perfil, auditoria por operacao e exibicao restrita ao perfil autorizado. Dados de bem-estar sao anonimos por arquitetura: o nome do funcionario nunca e associado a uma resposta individual de check-in nos paineis da empresa, a menos que o proprio funcionario consinta explicitamente ao solicitar contato de apoio."),
                ("Por que usamos localizacao", "No app da populacao, a localizacao e usada para georreferenciar sinais de saude, mostrar risco territorial, reduzir fraude e exibir alertas proximos. No app do funcionario, a localizacao pode ser usada para confirmar presenca em posto de trabalho ou contexto de notificacao, conforme configuracao do contrato. O usuario pode controlar permissoes no sistema operacional."),
                ("Tokens de notificacao FCM", "Usamos tokens FCM para enviar notificacoes push no app do funcionario (lembretes de exame, treinamento, alertas) e no app da populacao (alertas oficiais). Tokens sao armazenados de forma segura, vinculados ao dispositivo autorizado e podem ser revogados pelo usuario ou pelo gestor conforme contrato."),
                ("Finalidades", "Usamos os dados para operar a plataforma, exibir radar local, formar indicadores agregados, publicar alertas, gerenciar SST e conformidade eSocial, enviar notificacoes ao funcionario, coletar e agregar check-ins de bem-estar, prevenir abuso, proteger a seguranca, atender contratos, cumprir obrigacoes legais e apoiar governanca responsavel."),
                ("Base legal LGPD", "Conforme o contexto, o tratamento pode se apoiar em consentimento, execucao de contrato, cumprimento de obrigacao legal ou regulatoria (inclusive SST e eSocial), protecao da vida ou da incolumidade fisica, tutela da saude, legitimo interesse com salvaguardas e exercicio regular de direitos."),
                ("Compartilhamento", "Empresas contratantes acessam dados SST de seus proprios funcionarios conforme perfil e contrato. Dados de bem-estar sao exibidos apenas de forma agregada para a empresa. Governos, hospitais, farmacias e operadores autorizados acessam informacoes conforme escopo contratual. A plataforma prioriza dados agregados e territoriais, evitando exposicao de pessoa identificavel sem base legal."),
                ("O que nao fazemos", "Nao vendemos dados pessoais para publicidade, nao usamos dados do app para rastrear usuarios entre apps e sites de terceiros, nao entregamos diagnostico medico e nao exibimos publicamente relato individual identificavel."),
                ("Retencao e descarte", "Mantemos dados pelo tempo necessario para operacao, seguranca, auditoria, cumprimento contratual, defesa de direitos e obrigacoes legais — incluindo prazos de retencao de documentos SST exigidos pela legislacao trabalhista e previdenciaria. Dados de bem-estar anonimizados podem ser mantidos para analise de tendencias agregadas."),
                ("Direitos do titular", "Titulares podem solicitar informacoes, acesso, correcao, exclusao quando aplicavel, esclarecimentos sobre compartilhamento, revisao de consentimento e orientacoes sobre tratamento de dados pelo canal oficial de privacidade."),
                ("Menores de idade", "O app da populacao e informativo e nao deve ser usado por criancas sem orientacao dos responsaveis. O app do funcionario e destinado a trabalhadores maiores de idade vinculados ao contrato empresarial."),
                ("Seguranca", "Usamos HTTPS, variaveis de ambiente para segredos, banco gerenciado em producao, cookies seguros, restricao de CORS/CSRF, controle de sessao, limite de dispositivos por contrato, trilhas de auditoria, segregacao de perfis e boas praticas para reduzir acesso indevido, manipulacao e exposicao desnecessaria."),
                ("Contato de privacidade", "Pedidos de privacidade, direitos do titular, duvidas sobre LGPD e solicitacoes relacionadas ao tratamento de dados podem ser enviados para comercial@soluscrt.com.br com o assunto Privacidade SolusCRT."),
                ("Atualizacoes", "Esta politica pode ser atualizada para refletir melhorias da plataforma, novas exigencias legais, ajustes de App Store, contratos institucionais e mudancas nos controles de seguranca."),
            ],
        },
        "termos": {
            "title": "Termos de Uso",
            "subtitle": "Regras de uso do app da populacao, do app do funcionario, do ambiente SST e dos ambientes privados da plataforma.",
            "sections": [
                ("Natureza da plataforma", "O SolusCRT Saude e uma plataforma SaaS de gestao em saude. O app da populacao oferece inteligencia epidemiologica informativa. O ambiente empresarial oferece gestao SST, bem-estar e conformidade. Nenhum dos recursos substitui diagnostico medico, prescricao, triagem clinica individual ou atendimento de emergencia."),
                ("Envio responsavel no app da populacao", "Usuarios devem enviar sintomas reais, de boa-fe e apenas quando houver relacao com sua condicao atual. Envios repetidos, automatizados ou fraudulentos podem ser filtrados ou bloqueados."),
                ("App do funcionario — uso adequado", "O app do funcionario e de uso exclusivo do trabalhador vinculado ao contrato da empresa. E proibido compartilhar credenciais, acessar dados de outros funcionarios sem autorizacao ou usar o app para fins alheios a gestao de saude ocupacional e bem-estar."),
                ("Bem-estar — submissao voluntaria", "Check-ins de bem-estar sao voluntarios. O funcionario nao e obrigado a responder e pode omitir qualquer campo. A empresa ve apenas dados agregados. O funcionario consente explicitamente ao solicitar contato de apoio."),
                ("Responsabilidade por dados SST", "A empresa contratante e responsavel pela exatidao dos dados SST inseridos na plataforma — incluindo ASO, CAT, exames, afastamentos e registros eSocial SST. O SolusCRT e o ambiente de gestao; a responsabilidade tecnica e legal pelos dados e do empregador e do profissional de saude responsavel."),
                ("Periodo de teste gratuito", "O periodo de teste gratuito tem duracao de 15 dias corridos a partir da ativacao, sem necessidade de cartao de credito. Ao final do periodo de teste, sem assinatura ativa, o acesso e suspenso automaticamente e os dados podem ser retidos por periodo adicional conforme politica de retencao. Nao ha cobranca automatica apos o trial."),
                ("Ambientes privados", "Acessos empresariais, governamentais e administrativos sao exclusivos para clientes e operadores autorizados. Tentativas de acesso indevido podem ser registradas e bloqueadas."),
                ("Uso proibido", "E proibido tentar burlar controles de seguranca, automatizar envios indevidos, inserir informacoes falsas em dados SST ou de bem-estar, acessar area contratual sem autorizacao, realizar engenharia reversa ou usar a plataforma para finalidade ilegal, discriminatoria ou abusiva."),
                ("Contas e credenciais", "Credenciais sao pessoais ou institucionais conforme contrato. O usuario ou cliente e responsavel por preservar senhas, dispositivos autorizados e politicas internas de acesso."),
                ("Disponibilidade", "A plataforma depende de internet, servicos de nuvem, APIs, fontes oficiais e permissao de localizacao. Podem ocorrer indisponibilidades temporarias ou degradacao de dados externos."),
                ("Responsabilidade decisoria", "Decisoes operacionais, clinicas e institucionais devem considerar contexto tecnico, validacao humana e protocolos aplicaveis de saude publica e saude ocupacional."),
                ("Propriedade intelectual", "Marcas, interfaces, modelos, organizacao da plataforma, documentos, codigos, paineis e materiais do SolusCRT Saude pertencem aos seus titulares e sao licenciados nos limites contratados."),
                ("Contratacao B2B e B2G", "Planos empresariais, governamentais, limites de usuarios, dispositivos, suporte, integracoes, SLA e valores podem ser definidos em proposta, contrato, termo de adesao ou instrumento especifico."),
            ],
        },
        "seguranca-lgpd": {
            "title": "Seguranca, LGPD e Governanca",
            "subtitle": "Controles para proteger dados, acessos e confianca institucional em todos os ambientes da plataforma.",
            "sections": [
                ("Principios", "A plataforma deve seguir finalidade, adequacao, necessidade, seguranca, prevencao, transparencia e responsabilizacao no tratamento de dados pessoais, com atencao especial a dados sensiveis de saude presentes no ambiente SST."),
                ("Segregacao de ambientes", "SST/Empresa, farmacia, hospital e governo sao ambientes separados por fluxo de login, permissao, sessao, auditoria e dominio/subdominio quando contratado. Dados de um ambiente nao sao acessiveis a outros sem autorizacao explicita."),
                ("Controles antifraude epidemiologicos", "O app da populacao e o backend utilizam controles por aparelho, rede, repeticao, qualidade do sinal e localizacao atual para reduzir manipulacao de focos. Intensidade epidemiologica so cai apos 10 dias sem novos sinais e quando serie temporal, agregados e fontes oficiais sustentam queda real."),
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
            "subtitle": "Como o SolusCRT separa sinal precoce, fonte oficial, SST e decisao operacional.",
            "sections": [
                ("Sinal colaborativo epidemiologico", "O app da populacao coleta sinais de sintomas em tempo real. Esses sinais indicam tendencia e risco territorial, mas nao equivalem a caso confirmado. Sao exibidos como camada de sinal precoce, separados de fontes oficiais e inferencias de IA."),
                ("Fonte oficial brasileira", "Dados oficiais — IBGE/SIDRA, InfoDengue, InfoGripe, OpenDataSUS/DATASUS — sao tratados separadamente, preferencialmente em agregados, com data de coleta, fonte, versao e regra de processamento. Nunca sao misturados com sinais colaborativos sem identificacao de camada."),
                ("Indicadores epidemiologicos", "A plataforma usa crescimento, incidencia por 100 mil habitantes, predominancia de sintomas, serie temporal e reducao gradual quando deixam de entrar novos sinais. Intensidade so cai apos 10 dias sem novos sinais e quando tendencia, agregados e fontes oficiais sustentam queda real."),
                ("IA como apoio epidemiologico", "Modelos de IA apoiam classificacao e priorizacao de sinais e territorios. Nao substituem equipe tecnica, vigilancia epidemiologica ou decisao institucional. Toda inferencia de IA e identificada como tal nos paineis."),
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
                ("Suporte institucional — farmacia, hospital e governo", "Farmacias, hospitais, municipios e governos que precisem de apoio operacional, contratual ou tecnico em seus ambientes especificos podem solicitar atendimento por comercial@soluscrt.com.br."),
                ("Escopo do atendimento", "O suporte do SolusCRT Saude atende questoes sobre plataforma, apps, acesso, alertas, SST, privacidade e funcionamento do servico. O atendimento nao substitui orientacao medica, emergencia, SAMU, hospital, UPA ou consulta clinica."),
                ("Tempo de resposta", "Solicitacoes institucionais e de suporte geral sao recebidas por canal oficial e tratadas conforme criticidade, natureza do pedido, fila operacional e disponibilidade da equipe."),
                ("Base publica de documentos", "Para revisao documental, consulte tambem a Politica de Privacidade, os Termos de Uso, a pagina de Seguranca e LGPD e a Metodologia publicadas no site institucional."),
            ],
        },
    },
    "en": {
        "privacidade": {
            "title": "Privacy Policy",
            "subtitle": "How SolusCRT Health handles data in the population app, the employee app, the OSH environment and the SaaS platform.",
            "sections": [
                ("Who we are and scope", "SolusCRT Health is a complete health management SaaS platform, with an OSH environment for companies, pharmaceutical management, hospital management, a situation room for government and two apps: the population app (free and anonymous) and the employee app (linked to the company account). This policy explains data handling across all these contexts."),
                ("Summary for population app users", "In the public app, you can view the radar, map and alerts and, if you choose, voluntarily and anonymously submit symptoms. The app does not provide medical diagnosis, prescription, individual triage, emergency care or a replacement for professional consultation."),
                ("Summary for employee app users", "The employee app is linked to the contracting company account. Through it, employees access their own digital medical certificate, make requests, receive exam and training notifications and submit wellness check-ins. Wellness check-ins are anonymous by default — the company sees only aggregated data, never a name associated with an individual check-in, unless the employee voluntarily requests support contact."),
                ("Data we may process", "We may process, depending on context and environment: selected symptoms; location coordinates while the app is in use; city, state, neighborhood or approximate region; submission date and time; a random technical identifier generated by the app; IP address; FCM push notification tokens; acceptance of terms; corporate or government account data; access and audit records. In the OSH environment: medical certificates, incident reports, exam results, leave records, NR training, PPE/EPC, workstations, hazards, PGR and eSocial OSH records — all sensitive health data handled with additional controls. In wellness: anonymous check-in responses on mood, physical health, mental health, stress and job satisfaction."),
                ("Sensitive health data — OSH and wellness", "Medical certificates, incident reports, exams, leave records and any occupational health data are sensitive data under the LGPD. They are handled with minimization, specific purpose, role-based access controls, per-operation audit trail and display restricted to the authorized profile. Wellness data is anonymous by architecture: employee names are never associated with individual check-in responses in company dashboards, unless the employee explicitly consents by requesting support contact."),
                ("Why we use location", "In the population app, location is used to georeference health signals, show territorial risk, reduce fraud and display nearby alerts. In the employee app, location may be used to confirm presence at a workstation or notification context, as configured by contract. Users can control permissions in the operating system."),
                ("FCM notification tokens", "We use FCM tokens to send push notifications in the employee app (exam reminders, training, alerts) and the population app (official alerts). Tokens are stored securely, linked to the authorized device and may be revoked by the user or manager according to contract."),
                ("Purposes", "We use data to operate the platform, display local radar, create aggregated indicators, publish alerts, manage OSH and eSocial compliance, send employee notifications, collect and aggregate wellness check-ins, prevent abuse, protect security, fulfill contracts, comply with legal obligations and support responsible governance."),
                ("Legal basis", "Depending on context, processing may rely on consent, contract performance, compliance with legal or regulatory obligations (including OSH and eSocial), protection of life or physical safety, health protection, legitimate interest with safeguards and regular exercise of rights."),
                ("Sharing", "Contracting companies access OSH data of their own employees according to profile and contract. Wellness data is displayed only in aggregated form to the company. Governments, hospitals, pharmacies and authorized operators access information according to their contractual scope. The platform prioritizes aggregated and territorial data, avoiding exposure of identifiable individuals without legal basis."),
                ("What we do not do", "We do not sell personal data for advertising, do not use app data to track users across third-party apps and websites, do not deliver medical diagnosis and do not publicly display individually identifiable reports."),
                ("Retention and disposal", "We keep data for the time necessary for operation, security, audit, contract compliance, defense of rights and legal obligations — including OSH document retention periods required by labor and social security law. Anonymized wellness data may be retained for aggregated trend analysis."),
                ("Data subject rights", "Data subjects may request information, access, correction, deletion when applicable, clarification about sharing, consent review and guidance about data processing through the official privacy channel."),
                ("Minors", "The population app is informational and should not be used by children without guidance from guardians. The employee app is intended for adult workers linked to the company contract."),
                ("Security", "We use HTTPS, environment variables for secrets, managed production database, secure cookies, CORS/CSRF restriction, session control, device limits by contract, audit trails, profile segregation and good practices to reduce unauthorized access, manipulation and unnecessary exposure."),
                ("Privacy contact", "Privacy requests, data subject rights, LGPD or privacy questions and requests related to data processing may be sent to comercial@soluscrt.com.br with the subject Privacy SolusCRT."),
                ("Updates", "This policy may be updated to reflect platform improvements, new legal requirements, App Store adjustments, institutional contracts and changes to security controls."),
            ],
        },
        "termos": {
            "title": "Terms of Use",
            "subtitle": "Rules for using the population app, the employee app, the OSH environment and the private platform environments.",
            "sections": [
                ("Nature of the platform", "SolusCRT Health is a health management SaaS platform. The population app provides informational epidemiological intelligence. The company environment offers OSH management, team wellness and compliance. None of these resources replaces medical diagnosis, prescription, individual clinical triage or emergency care."),
                ("Responsible submission in the population app", "Users should submit real symptoms, in good faith and only when related to their current condition. Repeated, automated or fraudulent submissions may be filtered or blocked."),
                ("Employee app — proper use", "The employee app is for exclusive use by workers linked to the company contract. It is prohibited to share credentials, access other employees' data without authorization or use the app for purposes unrelated to occupational health management and wellness."),
                ("Wellness — voluntary submission", "Wellness check-ins are voluntary. The employee is not required to respond and may omit any field. The company sees only aggregated data. The employee explicitly consents when requesting support contact."),
                ("Responsibility for OSH data", "The contracting company is responsible for the accuracy of OSH data entered into the platform — including medical certificates, incident reports, exams, leave records and eSocial OSH records. SolusCRT is the management environment; technical and legal responsibility for the data lies with the employer and the responsible occupational health professional."),
                ("Free trial period", "The free trial period lasts 15 calendar days from activation, with no credit card required. At the end of the trial period, without an active subscription, access is automatically suspended and data may be retained for an additional period according to the retention policy. There is no automatic charge after the trial."),
                ("Private environments", "Business, government and administrative access is exclusive to clients and authorized operators. Unauthorized access attempts may be recorded and blocked."),
                ("Prohibited use", "It is forbidden to bypass security controls, automate improper submissions, insert false information in OSH or wellness data, access contractual areas without authorization, reverse engineer the platform or use it for illegal, discriminatory or abusive purposes."),
                ("Accounts and credentials", "Credentials are personal or institutional according to contract. The user or client is responsible for protecting passwords, authorized devices and internal access policies."),
                ("Availability", "The platform depends on internet access, cloud services, APIs, official sources and location permission. Temporary unavailability or degradation of external data may occur."),
                ("Decision responsibility", "Operational, clinical and institutional decisions must consider technical context, human validation and applicable public health and occupational health protocols."),
                ("Intellectual property", "Brands, interfaces, models, platform organization, documents, code, dashboards and SolusCRT Health materials belong to their owners and are licensed only within contracted limits."),
                ("B2B and B2G contracting", "Business and government plans, user limits, devices, support, integrations, SLA and pricing may be defined in proposal, contract, order form or specific instrument."),
            ],
        },
        "seguranca-lgpd": {
            "title": "Security, LGPD and Governance",
            "subtitle": "Controls to protect data, access and institutional trust across all platform environments.",
            "sections": [
                ("Principles", "The platform should follow purpose limitation, adequacy, necessity, security, prevention, transparency and accountability in the processing of personal data, with special attention to sensitive health data present in the OSH environment."),
                ("Environment segregation", "OSH/Company, pharmacy, hospital and government are separate environments with distinct login flows, permissions, sessions, audit trails and domain/subdomain when contracted. Data from one environment is not accessible to others without explicit authorization."),
                ("Epidemiological anti-fraud controls", "The population app and backend use device, network, repetition, signal quality and current location controls to reduce hotspot manipulation. Epidemiological intensity only decreases after 10 days without new signals and when time series, aggregates and official sources support a real decline."),
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
            "subtitle": "How SolusCRT separates early signal, official source, OSH management and operational decision.",
            "sections": [
                ("Epidemiological collaborative signal", "The population app collects symptom signals in real time. These signals indicate trend and territorial risk, but they are not confirmed cases. They are displayed as an early signal layer, separated from official sources and AI inferences."),
                ("Official Brazilian source", "Official data — IBGE/SIDRA, InfoDengue, InfoGripe, OpenDataSUS/DATASUS — are handled separately, preferably in aggregated form, with collection date, source, version and processing rule. They are never mixed with collaborative signals without layer identification."),
                ("Epidemiological indicators", "The platform uses growth, incidence per 100,000 inhabitants, symptom predominance, time series and gradual decline when no new signals are received. Intensity only decreases after 10 days without new signals and when trend, aggregates and official sources support a real decline."),
                ("AI as epidemiological support", "AI models support classification and prioritization of signals and territories. They do not replace technical teams, epidemiological surveillance or institutional decision-making. Every AI inference is identified as such in dashboards."),
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
                ("Institutional support — pharmacy, hospital and government", "Pharmacies, hospitals, municipalities and governments that need operational, contractual or technical support in their specific environments may contact comercial@soluscrt.com.br."),
                ("Scope of support", "SolusCRT Health support covers questions about the platform, apps, access, alerts, OSH, privacy and service operation. Support does not replace medical guidance, emergency care, ambulance services, hospital, urgent care unit or clinical consultation."),
                ("Response time", "Institutional and general support requests are received through the official channel and handled according to criticality, request type, operational queue and team availability."),
                ("Public document base", "For document review, also consult the Privacy Policy, Terms of Use, Security and LGPD page and Methodology published on the institutional website."),
            ],
        },
    },
    "es": {
        "privacidade": {
            "title": "Politica de Privacidad",
            "subtitle": "Como SolusCRT Salud trata datos en la app poblacional, la app del trabajador, el ambiente SST y la plataforma SaaS.",
            "sections": [
                ("Quienes somos y alcance", "SolusCRT Salud es una plataforma SaaS completa de gestion en salud, con ambiente SST para empresas, gestion farmaceutica, gestion hospitalaria, sala de situacion para gobierno y dos apps: la app poblacional (gratuita y anonima) y la app del trabajador (vinculada a la cuenta empresarial). Esta politica explica el tratamiento de datos en todos estos contextos."),
                ("Resumen para usuarios de la app poblacional", "En la app publica, puedes consultar radar, mapa y alertas y, si lo deseas, enviar sintomas de forma voluntaria y anonima. La app no ofrece diagnostico medico, prescripcion, triaje individual, atencion de emergencia ni sustitucion de una consulta profesional."),
                ("Resumen para usuarios de la app del trabajador", "La app del trabajador esta vinculada a la cuenta de la empresa contratante. A traves de ella, el trabajador accede a su certificado medico digital, realiza solicitudes, recibe notificaciones de examenes y capacitaciones y envia check-ins de bienestar. Los check-ins de bienestar son anonimos por defecto — la empresa ve solo datos agregados, nunca el nombre asociado a un check-in individual, salvo cuando el propio trabajador solicita voluntariamente contacto de apoyo."),
                ("Datos que podemos tratar", "Podemos tratar, segun el contexto y el ambiente: sintomas seleccionados; coordenadas de ubicacion mientras la app esta en uso; ciudad, estado, barrio o region aproximada; fecha y hora del envio; identificador tecnico aleatorio generado por la app; IP; tokens FCM de notificacion push; aceptacion de terminos; datos de cuenta corporativa o gubernamental; registros de acceso y auditoria. En el ambiente SST: certificados medicos, registros de accidente, resultados de examenes, ausencias, capacitaciones NR, EPI/EPC, puestos de trabajo, riesgos, PGR y registros eSocial SST — todos datos de salud sensibles tratados con controles adicionales. En bienestar: respuestas anonimas de check-in de humor, salud fisica, salud mental, estres y satisfaccion laboral."),
                ("Datos sensibles de salud — SST y bienestar", "Los certificados medicos, registros de accidente, examenes, ausencias y cualquier dato de salud ocupacional son datos sensibles segun la LGPD. Se tratan con minimizacion, finalidad especifica, controles de acceso por perfil, auditoria por operacion y visualizacion restringida al perfil autorizado. Los datos de bienestar son anonimos por arquitectura: el nombre del trabajador nunca se asocia a una respuesta individual de check-in en los paneles de la empresa, salvo cuando el trabajador consiente explicitamente al solicitar contacto de apoyo."),
                ("Por que usamos ubicacion", "En la app poblacional, la ubicacion se usa para georreferenciar senales de salud, mostrar riesgo territorial, reducir fraude y mostrar alertas cercanas. En la app del trabajador, la ubicacion puede usarse para confirmar presencia en un puesto de trabajo o contexto de notificacion, segun la configuracion del contrato. El usuario puede controlar permisos en el sistema operativo."),
                ("Tokens de notificacion FCM", "Usamos tokens FCM para enviar notificaciones push en la app del trabajador (recordatorios de examen, capacitacion, alertas) y en la app poblacional (alertas oficiales). Los tokens se almacenan de forma segura, vinculados al dispositivo autorizado y pueden ser revocados por el usuario o el gestor segun contrato."),
                ("Finalidades", "Usamos los datos para operar la plataforma, mostrar radar local, formar indicadores agregados, publicar alertas, gestionar SST y conformidad eSocial, enviar notificaciones al trabajador, recoger y agregar check-ins de bienestar, prevenir abuso, proteger la seguridad, cumplir contratos, atender obligaciones legales y apoyar una gobernanza responsable."),
                ("Base legal", "Segun el contexto, el tratamiento puede apoyarse en consentimiento, ejecucion de contrato, cumplimiento de obligacion legal o regulatoria (incluido SST y eSocial), proteccion de la vida o integridad fisica, tutela de la salud, interes legitimo con salvaguardas y ejercicio regular de derechos."),
                ("Compartir informacion", "Las empresas contratantes acceden a datos SST de sus propios trabajadores segun perfil y contrato. Los datos de bienestar se muestran solo de forma agregada a la empresa. Gobiernos, hospitales, farmacias y operadores autorizados acceden a informacion segun su alcance contractual. La plataforma prioriza datos agregados y territoriales, evitando exponer personas identificables sin base legal."),
                ("Lo que no hacemos", "No vendemos datos personales para publicidad, no usamos datos de la app para rastrear usuarios entre apps y sitios de terceros, no entregamos diagnostico medico y no mostramos publicamente relatos individuales identificables."),
                ("Retencion y descarte", "Mantenemos datos durante el tiempo necesario para operacion, seguridad, auditoria, cumplimiento contractual, defensa de derechos y obligaciones legales — incluyendo plazos de retencion de documentos SST exigidos por la legislacion laboral y de seguridad social. Los datos de bienestar anonimizados pueden mantenerse para analisis de tendencias agregadas."),
                ("Derechos del titular", "Los titulares pueden solicitar informacion, acceso, correccion, eliminacion cuando corresponda, aclaraciones sobre intercambio, revision de consentimiento y orientacion sobre tratamiento de datos por el canal oficial de privacidad."),
                ("Menores de edad", "La app poblacional es informativa y no debe ser usada por ninos sin orientacion de responsables. La app del trabajador esta destinada a trabajadores mayores de edad vinculados al contrato empresarial."),
                ("Seguridad", "Usamos HTTPS, variables de entorno para secretos, base de datos gestionada en produccion, cookies seguras, restriccion CORS/CSRF, control de sesion, limite de dispositivos por contrato, trazas de auditoria, segregacion de perfiles y buenas practicas para reducir acceso indebido, manipulacion y exposicion innecesaria."),
                ("Contacto de privacidad", "Pedidos de privacidad, derechos del titular, dudas sobre LGPD o privacidad y solicitudes relacionadas con tratamiento de datos pueden enviarse a comercial@soluscrt.com.br con el asunto Privacidad SolusCRT."),
                ("Actualizaciones", "Esta politica puede actualizarse para reflejar mejoras de la plataforma, nuevas exigencias legales, ajustes de App Store, contratos institucionales y cambios en controles de seguridad."),
            ],
        },
        "termos": {
            "title": "Terminos de Uso",
            "subtitle": "Reglas de uso de la app poblacional, la app del trabajador, el ambiente SST y los ambientes privados de la plataforma.",
            "sections": [
                ("Naturaleza de la plataforma", "SolusCRT Salud es una plataforma SaaS de gestion en salud. La app poblacional ofrece inteligencia epidemiologica informativa. El ambiente empresarial ofrece gestion SST, bienestar del equipo y conformidad. Ningun recurso sustituye diagnostico medico, prescripcion, triaje clinico individual ni atencion de emergencia."),
                ("Envio responsable en la app poblacional", "Los usuarios deben enviar sintomas reales, de buena fe y solo cuando tengan relacion con su condicion actual. Envios repetidos, automatizados o fraudulentos pueden ser filtrados o bloqueados."),
                ("App del trabajador — uso adecuado", "La app del trabajador es de uso exclusivo del trabajador vinculado al contrato de la empresa. Esta prohibido compartir credenciales, acceder a datos de otros trabajadores sin autorizacion o usar la app para fines ajenos a la gestion de salud ocupacional y bienestar."),
                ("Bienestar — envio voluntario", "Los check-ins de bienestar son voluntarios. El trabajador no esta obligado a responder y puede omitir cualquier campo. La empresa ve solo datos agregados. El trabajador consiente explicitamente al solicitar contacto de apoyo."),
                ("Responsabilidad por datos SST", "La empresa contratante es responsable de la exactitud de los datos SST ingresados en la plataforma — incluyendo certificados medicos, registros de accidente, examenes, ausencias y registros eSocial SST. SolusCRT es el ambiente de gestion; la responsabilidad tecnica y legal por los datos corresponde al empleador y al profesional de salud ocupacional responsable."),
                ("Periodo de prueba gratuito", "El periodo de prueba gratuito tiene una duracion de 15 dias corridos desde la activacion, sin necesidad de tarjeta de credito. Al terminar el periodo de prueba, sin suscripcion activa, el acceso se suspende automaticamente y los datos pueden retenerse por un periodo adicional segun la politica de retencion. No hay cobro automatico despues de la prueba."),
                ("Ambientes privados", "Los accesos empresariales, gubernamentales y administrativos son exclusivos para clientes y operadores autorizados. Intentos de acceso indebido pueden registrarse y bloquearse."),
                ("Uso prohibido", "Esta prohibido burlar controles de seguridad, automatizar envios indebidos, insertar informacion falsa en datos SST o de bienestar, acceder a areas contractuales sin autorizacion, hacer ingenieria inversa o usar la plataforma con finalidad ilegal, discriminatoria o abusiva."),
                ("Cuentas y credenciales", "Las credenciales son personales o institucionales segun contrato. El usuario o cliente es responsable de preservar contrasenas, dispositivos autorizados y politicas internas de acceso."),
                ("Disponibilidad", "La plataforma depende de internet, servicios de nube, APIs, fuentes oficiales y permiso de ubicacion. Pueden ocurrir indisponibilidades temporales o degradacion de datos externos."),
                ("Responsabilidad de decision", "Las decisiones operativas, clinicas e institucionales deben considerar contexto tecnico, validacion humana y protocolos aplicables de salud publica y salud ocupacional."),
                ("Propiedad intelectual", "Marcas, interfaces, modelos, organizacion de la plataforma, documentos, codigos, paneles y materiales de SolusCRT Salud pertenecen a sus titulares y se licencian dentro de los limites contratados."),
                ("Contratacion B2B y B2G", "Planes empresariales y gubernamentales, limites de usuarios, dispositivos, soporte, integraciones, SLA y valores pueden definirse en propuesta, contrato, termino de adhesion o instrumento especifico."),
            ],
        },
        "seguranca-lgpd": {
            "title": "Seguridad, LGPD y Gobernanza",
            "subtitle": "Controles para proteger datos, accesos y confianza institucional en todos los ambientes de la plataforma.",
            "sections": [
                ("Principios", "La plataforma debe seguir finalidad, adecuacion, necesidad, seguridad, prevencion, transparencia y responsabilizacion en el tratamiento de datos personales, con especial atencion a los datos sensibles de salud presentes en el ambiente SST."),
                ("Segregacion de ambientes", "SST/Empresa, farmacia, hospital y gobierno son ambientes separados con flujos de login, permisos, sesiones, auditoria y dominio/subdominio distintos cuando sea contratado. Los datos de un ambiente no son accesibles a otros sin autorizacion explicita."),
                ("Controles antifraude epidemiologicos", "La app poblacional y el backend utilizan controles por dispositivo, red, repeticion, calidad de la senal y ubicacion actual para reducir manipulacion de focos. La intensidad epidemiologica solo baja tras 10 dias sin nuevas senales y cuando serie temporal, agregados y fuentes oficiales sostienen una reduccion real."),
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
            "subtitle": "Como SolusCRT separa senal temprana, fuente oficial, gestion SST y decision operativa.",
            "sections": [
                ("Senal colaborativa epidemiologica", "La app poblacional recopila senales de sintomas en tiempo real. Estas senales indican tendencia y riesgo territorial, pero no equivalen a caso confirmado. Se muestran como capa de senal temprana, separadas de fuentes oficiales e inferencias de IA."),
                ("Fuente oficial brasilena", "Datos oficiales — IBGE/SIDRA, InfoDengue, InfoGripe, OpenDataSUS/DATASUS — se tratan por separado, preferentemente en agregados, con fecha de recoleccion, fuente, version y regla de procesamiento. Nunca se mezclan con senales colaborativas sin identificacion de capa."),
                ("Indicadores epidemiologicos", "La plataforma usa crecimiento, incidencia por 100 mil habitantes, predominancia de sintomas, serie temporal y reduccion gradual cuando dejan de entrar nuevas senales. La intensidad solo baja tras 10 dias sin nuevas senales y cuando tendencia, agregados y fuentes oficiales sostienen una reduccion real."),
                ("IA como apoyo epidemiologico", "Modelos de IA apoyan clasificacion y priorizacion de senales y territorios. No sustituyen al equipo tecnico, la vigilancia epidemiologica ni la decision institucional. Toda inferencia de IA se identifica como tal en los paneles."),
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
                ("Soporte institucional — farmacia, hospital y gobierno", "Farmacias, hospitales, municipios y gobiernos que necesiten apoyo operativo, contractual o tecnico en sus ambientes especificos pueden contactar comercial@soluscrt.com.br."),
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
            "total": indice_ativo,
            "total_registros_30d": item["total"],
            "raw_total": item["total"],
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
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    total = RegistroSintoma.objects.filter(empresa=empresa).count()
    RegistroSintoma.objects.filter(empresa=empresa).delete()
    return JsonResponse({"apagados": total})


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
