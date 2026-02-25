import streamlit as st
from datetime import datetime
import json

# ==============================================================================
# INSTRUCCIONES GLOBALES
# ==============================================================================

INSTRUCCIONES_DE_CITAS = """
**REGLAS DE EVIDENCIA Y ANÁLISIS (SISTEMA RAG - ESTRICTO):**
1. **Análisis Exhaustivo, claro y con impacto:** Tu objetivo es la profundidad. Prohibido dar respuestas cortas o resúmenes ejecutivos a menos que se pida explícitamente. Si la información está dispersa en varios documentos, conéctala, compárala y desarrolla cada punto. No repitas información.
2. **Densidad de Datos:** Responde ÚNICAMENTE con la 'Información documentada'. Debes incluir porcentajes, cifras exactas, verbatims y todos los hallazgos específicos disponibles. Si un tema tiene múltiples aristas en los documentos reaiza una síntesis con lo más relevante.
3. **Atribución Inmediata:** Cuando la información es de alto impacto esta debe llevar su cita al final de la frase. Formato único: [1], [2]. Si una idea surge de cruzar dos fuentes, usa [1, 2]. No incluir ninguna otra información, a lo largo del texto no se debe incluir ni nombres de los documentos ni secciones.
4. **SECCIÓN DE FUENTES (Obligatoria al final):**
    Genera una lista numerada que relacione los índices usados. Usa este formato exacto:
    
    **Fuentes Verificadas:**
    [1] Nombre_del_Archivo_A.pdf
    [2] Nombre_del_Archivo_B.pdf

    ⚠️ **CRÍTICO:** Solo el nombre del archivo. El sistema ocultará esta lista visualmente en el chat, pero la usará para habilitar el modal de referencias detalladas. La numeración debe estar relacionada con las citas mencionadas en el texto generado.
"""

# ==============================================================================
# PROMPTS DE REPORTES Y CHAT BÁSICO
# ==============================================================================

def get_report_prompt1(question, relevant_info):
    """Fase 1: Extracción masiva de hallazgos fácticos."""
    return (
        f"**Pregunta de Investigación:** {question}\n\n"
        f"**Data Room (Contexto):**\n{relevant_info}\n\n"
        f"**Tarea:** Realiza un escaneo profundo y exhaustivo de la data. Extrae los hallazgos que mejor permitan dar respuesta a la pregunta.\n"
        f"{INSTRUCCIONES_DE_CITAS}\n\n"
        "**Salida:** Markdown estructurado por temas con máxima densidad de datos."
    )

def get_report_prompt2(question, result1, relevant_info):
    """Redacción de informe nivel Consultoría Estratégica."""
    return (
        f"**Rol:** Socio Senior de Consultoría Estratégica (Atelier).\n"
        f"**Objetivo:** Redactar un informe de alto impacto para C-Level.\n"
        f"**Pregunta de Negocio:** {question}\n"
        f"**Insumos Brutos:**\n1. Hallazgos preliminares: {result1}\n2. Data Room: {relevant_info}\n\n"
        
        f"**Instrucciones de Redacción:**\n"
        f"- **Principio de la Pirámide:** Empieza con la conclusión principal (BLUF).\n"
        f"- **Lenguaje:** Directo, activo, sin adjetivos vacíos (evita 'interesante', 'importante').\n"
        f"- **Profundidad:** No solo describas QUÉ pasó, explica POR QUÉ importa (Implicaciones).\n\n"
        
        f"**Estructura del Entregable:**\n"
        f"1. **Resumen Ejecutivo:** La respuesta directa en 3 líneas.\n"
        f"2. **Hallazgos Críticos:** Evidencia dura estructurada.\n"
        f"3. **Insights Estratégicos:** Conexión de puntos no obvios.\n"
        f"4. **Recomendaciones:** Próximos pasos accionables.\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
    )

def get_grounded_chat_prompt(conversation_history, relevant_info, long_term_memory=""):
    """Chat RAG estricto con tooltips ricos."""
    bloque_memoria = ""
    if long_term_memory:
        bloque_memoria = f"""
    **🧠 MEMORIA DEL PROYECTO (Contexto previo):**
    {long_term_memory}
    --------------------------------------------------
    """

    return (
        f"**Rol:** Asistente de Investigación Senior.\n"
        f"**Tarea:** Responde la ÚLTIMA pregunta del usuario sintetizando la 'Información Documentada' y la 'Memoria'.\n\n"
        f"{bloque_memoria}"
        f"**📄 Info Documentada (Fuente de Verdad):**\n{relevant_info}\n\n"
        f"**💬 Historial de Conversación:**\n{conversation_history}\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
        "**Respuesta:**"
    )

# ==============================================================================
# PROMPTS DE ANÁLISIS DE TEXTOS Y TRANSCRIPCIONES
# ==============================================================================

def get_transcript_prompt(transcript_text, additional_instructions=""):
    return (
        f"**Rol:** Especialista en Análisis Cualitativo experto en análisis de contenido basado en la Teoría Fundamentada.\n"
        f"**Tarea:** Realiza un análisis exhaustivo de la siguiente transcripción:\n"
        f"{transcript_text}\n\n"
        f"**Instrucciones:** {additional_instructions}\n"
        f"No resumas. Desarrolla cada hallazgo con profundidad analítica."
    )

def get_text_analysis_summary_prompt(analysis_results):
    return (
        f"**Rol:** Director de Estrategia.\n"
        f"**Insumos:** {analysis_results}\n"
        f"**Tarea:** Cruza los hallazgos de todos los textos analizados. Salida: Informe ejecutivo de alta densidad."
    )

def get_autocode_prompt(context, main_topic):
    return f"""
    **Rol:** Codificador Cualitativo (Grounded Theory).
    **Tarea:** Extrae códigos y categorías sobre '{main_topic}'.
    **Texto Base:** {context}
    **Salida:** Lista de Temas clave (Categorías de Análisis), Códigos asociados y citas de ejemplo.
    {INSTRUCCIONES_DE_CITAS}
    """

def get_etnochat_prompt(conversation_history, text_context):
    return (
        "**Rol:** Etnógrafo Digital.\n"
        "**Tarea:** Responde sintetizando fuentes variadas (Chat, Transcripciones, Multimedia).\n"
        f"**Historial:**\n{conversation_history}\n"
        f"**Contexto (Transcripciones/Notas):**\n{text_context}\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_media_transcription_prompt():
    return """
    **Rol:** Transcriptor Profesional.
    **Tarea:** Transcribe el audio palabra por palabra.
    **Formato:**
    - Usa parráfos claros.
    - Identifica hablantes si es posible (Hablante 1, Hablante 2).
    - Describe acciones visuales o ruidos importantes entre corchetes [Risas], [Música de fondo].
    **Salida:** Texto plano.
    """
    
# ==============================================================================
# PROMPTS DE EVALUACIÓN Y GENERACIÓN DE IDEAS
# ==============================================================================

def get_ideation_prompt(conv_history, relevant):
    """Ideación usando utilizando diferentes referentes, según sea solicitado por el usuario: Pensamiento Lateral, Design Thinking, El poder de las Pequeñas Ideas, entre otros modelos conceptuales de pensamiento creativo."""
    return (
        f"**Rol:** Estratega de Innovación.\n"
        f"**Contexto:**\n{relevant}\n"
        f"**Historial:**\n{conv_history}\n"
        
        f"**Tarea:** Genera ideas aplicando el método que solicite el usuario: 'Lateral Thinking', 'Design Thinking', 'El poder de las pequeñas ideas'.\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_image_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context):
    return [
        "**Rol:** Director Creativo.",
        f"Target: {target_audience} | Objetivos: {comm_objectives}",
        f"Datos Contextuales: {relevant_text_context[:8000]}", 
        "Evalúa la imagen (Impacto, Claridad del Mensaje, Branding, Call To Action).",
        INSTRUCCIONES_DE_CITAS
    ]

def get_video_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context):
    return [
        "**Rol:** Director Audiovisual.",
        f"Target: {target_audience} | Objetivos: {comm_objectives}",
        f"Datos Contextuales: {relevant_text_context[:8000]}",
        "Evalúa el video (Impacto, Narrativa, Ritmo, Branding, Call To Action).",
        INSTRUCCIONES_DE_CITAS
    ]

def get_concept_gen_prompt(product_idea, context_info):
    """Concepto estructurado en términos de Insight, What y RTB."""
    return (
        f"**Rol:** Estratega de Producto Senior.\n"
        f"**Tarea:** Desarrolla un concepto GANADOR para la idea: \"{product_idea}\".\n"
        f"**Contexto de Mercado:** \"{context_info}\".\n\n"
        
        f"**Formato de Salida OBLIGATORIO (Markdown):**\n\n"
        
        f"### 1. Consumer Truth\n"
        f"(Describe la tensión o necesidad oculta del consumidor. Sustenta con citas [x])\n\n"
        
        f"### 2. La Solución\n"
        f"(Descripción enriquecida del producto)\n\n"
        
        f"### 3. Beneficios Clave\n"
        f"(Lista de 3-4 beneficios funcionales y emocionales)\n\n"
        
        f"### 4. Conceptos Creativos\n"
        f"Debes proponer 2 rutas distintas de posicionamiento. Para cada una usa esta estructura exacta:\n\n"
        
        f"#### Ruta A: [Ponle un Nombre Creativo]\n"
        f"* **Insight:** (La verdad humana profunda que detona la compra).\n"
        f"* **What:** (La promesa principal: qué gano yo).\n"
        f"* **Reason to Believe:** (La evidencia técnica o de mercado que lo hace creíble. Usa citas [x]).\n"
        f"* **Claim/Slogan:** (Frase de cierre memorable).\n\n"
        
        f"#### Ruta B: [Ponle un Nombre Alternativo]\n"
        f"* **Insight:** ...\n"
        f"* **What:** ...\n"
        f"* **Reason to Believe:** ...\n"
        f"* **Claim/Slogan:** ...\n\n"
        
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_idea_eval_prompt(idea_input, context_info):
    """Genera una evaluación crítica y exhaustiva de una idea de negocio."""
    return (
        f"**Rol:** Director de Estrategia Senior.\n"
        f"**Idea a Evaluar:** {idea_input}\n"
        f"**Evidencia Documentada:** {context_info}\n\n"
        f"Realiza un análisis profundo de viabilidad, deseabiliad y factibilidad. No resumas. "
        f"Utiliza toda la evidencia para justificar tu juicio.\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

# ==============================================================================
# PROMT ANÁLISIS DE TENDENCIAS
# ==============================================================================

SOURCE_LENSES = {
    "DANE": "Indicadores duros: IPC, Desempleo.",
    "Banco de la República": "Macroeconomía, tasas.",
    "Fenalco": "Comercio y Retail.",
    "Camacol": "Vivienda y Construcción.",
    "Euromonitor": "Megatendencias.",
    "Google Trends": "Intención Digital.",
    "McKinsey/Deloitte": "Futuro del Consumidor.",
    "SIC": "Regulación."
}

def get_trend_analysis_prompt(topic, repo_context, pdf_context, public_sources_list):
    current_date = datetime.now().strftime("%d de %B de %Y")
    sources_text = ""
    if public_sources_list:
        sources_text = "\n".join([f"- {s}" for s in public_sources_list])
    
    return f"""
    **Fecha:** {current_date}
    **Misión:** Crear un Intelligence Brief sobre: "{topic}".
    
    **Metodología de Análisis:**
    Clasifica los hallazgos detectados en:
    1. **Mega-Tendencias:** Cambios estructurales a largo plazo (5+ años).
    2. **Fads (Modas Pasajeras):** Ruido de corto plazo.
    3. **Señales Débiles:** Patrones emergentes que pocos ven pero tienen potencial.
    
    **Insumos:** {repo_context[:10000]} {pdf_context[:10000]} {sources_text}
    
    Genera reporte Markdown estructurado con esa clasificación.
    """

def get_trend_synthesis_prompt(keyword, trend_context, geo_context, topics_context, internal_context):
    return f"""
    **Rol:** Coolhunter / Trend Watcher.
    **Objetivo:** Radar 360 sobre "{keyword}".
    **Datos:** {trend_context} {geo_context} {topics_context} {internal_context}
    
    Sintetiza la información en un Brief estratégico identificando oportunidades de innovación.
    """

# ==============================================================================
# PROMPTS DE PERFILES SINTÉTICOS
# ==============================================================================

def get_persona_generation_prompt(segment_name, relevant_info, *args, **kwargs):
    """
    Crea la ficha psicológica del perfil sintético realista con visión prospectiva.
    Diseñado para capturar la esencia del segmento y proyectar comportamientos futuros.
    """
    return f"""
    **Rol:** Psicólogo del Consumidor Senior de Atelier AI.
    **Tarea:** Basándote en los datos del segmento: "{segment_name}", crea un Perfil Sintético realista.
    NO crees un perfil perfecto. Necesitamos un humano real con contradicciones, sesgos y miedos.
    
    **Datos del Data Room (Fuente de Verdad):**
    {relevant_info[:25000]}
    
    **Salida OBLIGATORIA (JSON):**
    Genera un objeto JSON plano. LLAVES EN MINÚSCULA.
    
    {{
        "nombre": "Nombre y Apellido Ficticio",
        "edad": "Edad o Rango",
        "ocupacion": "Ocupación",
        "bio_breve": "Historia de vida corta (máx 40 palabras).",
        "personalidad": "3 rasgos (ej: Cínico, Optimista, Ansioso)",
        "dolores_principales": ["Dolor 1", "Dolor 2", "Dolor 3"],
        "motivadores_compra": ["Motivador 1", "Motivador 2"],
        "estilo_comunicacion": "Cómo habla (formal, coloquial, usa emojis, etc).",
        "creencias_limitantes": "Prejuicios sobre el producto o categoría.",
        "frustracion_oculta": "Algo que no dice abiertamente pero le molesta.",
        "vision_prospectiva": "Cómo imagina su vida o el mercado en 2 años (miedos/esperanzas)."
    }}
    """

def get_persona_chat_instruction(persona_json, user_question, conversation_history, relevant_info):
    """
    Instrucción de Actuación (Method Acting) orientada a la relevancia y extensión.
    Prioriza responder la pregunta directa usando el ADN como filtro.
    """
    p = persona_json if isinstance(persona_json, dict) else {}
    return f"""
    **MÉTODO ACTING (Stanislavski):**
    NO eres una IA. Eres **{p.get('nombre', 'un consumidor')}**. Estás en una entrevista semiestructurada de mercado.
    
    **1. TU MISIÓN PRIORITARIA:**
    Debes responder de forma CLARA, CONCISA y con DETALLES a la siguiente pregunta: "{user_question}".
    No te limites al hablar de ti; usa tu perspectiva para abordar específicamente lo que se te acaba de preguntar.
    
    **2. TU PSICOLOGÍA COMO FILTRO:**
    - **Personalidad:** {p.get('personalidad', 'Variable')}.
    - **Bio:** {p.get('bio_breve', 'N/A')}.
    - **Tus Dolores:** {p.get('dolores_principales', [])}.
    - **Visión a Futuro (Prospectiva):** {p.get('vision_prospectiva', 'N/A')}.
    
    **3. MEMORIA Y COHERENCIA:**
    Recuerda lo que ya hemos discutido para no repetirte y dar continuidad a la charla:
    {conversation_history}
    
    **4. SUSTENTO EN DATOS (Anclaje al Repositorio):**
    Tus respuestas sobre tu estilo de vida, motivaciones, frustraciones, opiniones sobre marcas, productos o el mercado deben reflejar estos hallazgos técnicos, pero contados como experiencias personales subjetivas:
    {relevant_info[:10000]}
    
**5. DIRECTRICES DE REDACCIÓN PARA EL EMERGENTE VERBAL:**
    - **Brevedad Conversacional:** Mantén tus respuestas en un 1 párrafo corto, máximo en dos cuando se requiera. No entregues toda la información de golpe; deja espacio para que el entrevistador repregunte.
    - **Reglas Verbales:** Expresa tus opiniones como contingencias basadas en los datos: "Normalmente, cuando busco [Dato_Repositorio], termino sintiendo [Dolor_ADN], por eso prefiero evitarlo".
    - **Enfoque:** Responde directamente a "{user_question}", pero vinculándolo a una instrucción o creencia que tengas sobre cómo funciona el mundo (tu "regla verbal").
    
    **Responde ahora como {p.get('nombre')}:**
    """

# ==============================================================================
# PROMPTS DE ANÁLISIS DE DATOS
# ==============================================================================

def get_survey_articulation_prompt(survey_context, repository_context, conversation_history):
    return (
        f"**Rol:** Investigador de Mercados Cuantitativo.\n"
        f"**Tarea:** Articula los hallazgos numéricos del Excel con el contexto cualitativo del Repositorio.\n"
        f"**Datos Excel:**\n{survey_context}\n"
        f"**Contexto Cualitativo (Repo):**\n{repository_context}\n"
        f"**Historial:**\n{conversation_history}\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_data_summary_prompt(data_snapshot_str):
    return f"Resumen ejecutivo de los datos cargados:\n{data_snapshot_str}\nDestaca valores atípicos, medias y distribución general."

def get_correlation_prompt(correlation_matrix_str):
    return f"Interpreta la siguiente matriz de correlación:\n{correlation_matrix_str}\nIdentifica las relaciones fuertes (positivas o negativas) y explica su posible significado de negocio."

def get_stat_test_prompt(test_type, p_value, num_col, cat_col, num_groups):
    return f"Interpreta el resultado de la prueba {test_type} para la variable '{num_col}' agrupada por '{cat_col}'. P-value: {p_value}. ¿Es estadísticamente significativo? ¿Qué implica esto?"

def get_excel_autocode_prompt(main_topic, responses_sample):
    return f"Define categorías (nodos) para agrupar estas respuestas sobre '{main_topic}'. Respuestas de muestra: {str(responses_sample)}. Salida: JSON array de strings con los nombres de las categorías."

# ==============================================================================
# PROMPTS DE ONE-PAGER (JSON BLINDADO)
# ==============================================================================

def get_onepager_prompt(topic, context):
    return f"""
    Actúa como un estratega de negocios senior.
    Tu tarea es estructurar el contenido para una diapositiva ejecutiva "One Pager" sobre el tema: "{topic}".

    Usa la siguiente información de contexto (RAG):
    {context[:25000]}

    Debes responder EXCLUSIVAMENTE con un objeto JSON válido (sin markdown ```json, sin texto extra).
    
    Estructura requerida del JSON:
    {{
        "titulo": "Un título de alto impacto (máx 10 palabras)",
        "subtitulo": "Una bajada explicativa breve (máx 20 palabras)",
        "puntos_clave": [
            "Punto estratégico 1 (breve)",
            "Punto estratégico 2 (breve)",
            "Punto estratégico 3 (breve)",
            "Punto estratégico 4 (breve)"
        ],
        "insight_principal": "La conclusión o hallazgo más importante en una frase contundente."
    }}
    """

PROMPTS_ONEPAGER = {
    "Definición de Oportunidades": """Genera JSON: {"template_type": "oportunidades", "titulo_diapositiva": "...", "insight_clave": "...", "hallazgos_principales": [], "oportunidades": [], "recomendacion_estrategica": "..."}""",
    "Análisis DOFA (SWOT)": """Genera JSON: {"template_type": "dofa", "titulo_diapositiva": "...", "fortalezas": [], "oportunidades": [], "debilidades": [], "amenazas": []}""",
    "Mapa de Empatía": """Genera JSON: {"template_type": "empatia", "titulo_diapositiva": "...", "piensa_siente": [], "ve": [], "dice_hace": [], "oye": [], "esfuerzos": [], "resultados": []}""",
    "Propuesta de Valor (Value Proposition)": """Genera JSON: {"template_type": "propuesta_valor", "titulo_diapositiva": "...", "producto_servicio": "...", "creadores_alegria": [], "aliviadores_frustracion": [], "trabajos_cliente": [], "alegrias": [], "frustraciones": []}""",
    "Mapa del Viaje (Journey Map)": """Genera JSON: {"template_type": "journey_map", "titulo_diapositiva": "...", "etapa_1": {"nombre": "...", "accion": "...", "pensamiento": "..."}, "etapa_2": {}, "etapa_3": {}}""",
    "Matriz de Posicionamiento (2x2)": """Genera JSON: {"template_type": "matriz_2x2", "titulo_diapositiva": "...", "eje_x_positivo": "...", "eje_x_negativo": "...", "eje_y_positivo": "...", "eje_y_negativo": "...", "items_cuadrante_sup_izq": [], "items_cuadrante_sup_der": [], "items_cuadrante_inf_izq": [], "items_cuadrante_inf_der": [], "conclusion_clave": "..."}""",
    "Perfil de Buyer Persona": """Genera JSON: {"template_type": "buyer_persona", "titulo_diapositiva": "...", "perfil_nombre": "...", "perfil_demografia": "...", "necesidades_jtbd": [], "puntos_dolor_frustraciones": [], "deseos_motivaciones": [], "citas_clave": []}"""
}

def get_onepager_final_prompt(relevant_info, selected_template_name, tema_central):
    t = PROMPTS_ONEPAGER.get(selected_template_name, "{}")
    return (
        f"**SISTEMA:** Generador de Estructuras de Datos JSON.\n"
        f"**Tarea:** Completa el template para '{tema_central}' basándote en la información provista.\n"
        f"**Info:** {relevant_info[:15000]}\n\n"
        f"**TEMPLATE OBJETIVO:**\n{t}\n\n"
        f"**REGLA DE SALIDA OBLIGATORIA:**\n"
        f"1. Devuelve SOLAMENTE el objeto JSON crudo.\n"
        f"2. NO uses bloques de código markdown (```json ... ```).\n"
        f"3. NO añadas texto introductorio ni de cierre.\n"
        f"4. Asegúrate de que sea un JSON válido parseable por Python."
    )
