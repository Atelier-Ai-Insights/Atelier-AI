import streamlit as st
from datetime import datetime

# ==============================================================================
# INSTRUCCIONES GLOBALES (CRÍTICO: CALIDAD DE EVIDENCIA EN TOOLTIPS)
# ==============================================================================

# --- BLOQUE DE INSTRUCCIONES DE CITAS (CON CONTEXTO OBLIGATORIO) ---
INSTRUCCIONES_DE_CITAS = """
**REGLAS DE CITAS Y EVIDENCIA (ESTRICTO):**
1. **Base:** Solo usa la 'Información documentada'.
2. **Formato en Texto:** Usa SOLO números entre corchetes. Ej: "La tendencia subió [1, 2]". NUNCA pongas nombres de archivo en el párrafo.
3. **SECCIÓN FUENTES (AL FINAL):**
   Genera la lista con este formato EXACTO (usando '|||' como separador):
   
   **Fuentes:**
   [1] Archivo.pdf ||| EVIDENCIA REAL. (Ej: "El 45% de usuarios prefiere X").
   [2] Otro.pdf ||| CITA TEXTUAL. (Ej: "El cliente mencionó: 'Es muy costoso'").

   ⚠️ **REGLA DE CALIDAD:** El texto después de '|||' DEBE aportar valor.
   - 🚫 PROHIBIDO usar frases vacías como: "Fuente del documento", "Referencia bibliográfica", "Ver archivo", "Hallazgo clave".
   - ✅ OBLIGATORIO: Poner el dato, porcentaje, fecha o frase exacta que justifica la cita.
"""

# ==============================================================================
# PROMPTS DE REPORTES Y CHAT BÁSICO
# ==============================================================================

def get_report_prompt1(question, relevant_info):
    """Extracción de hallazgos."""
    return (
        f"**Pregunta:** {question}\n\n"
        f"**Contexto:**\n{relevant_info}\n\n"
        f"**Tarea:** Extrae hallazgos fácticos.\n"
        f"{INSTRUCCIONES_DE_CITAS}\n\n"
        "**Salida:**\nMarkdown estructurado."
    )

def get_report_prompt2(question, result1, relevant_info):
    """Redacción de informe."""
    return (
        f"**Rol:** Analista experto de Atelier.\n"
        f"**Pregunta:** {question}\n"
        f"**Insumos:**\n1. Hallazgos: {result1}\n2. Contexto: {relevant_info}\n\n"
        f"**Tarea:** Informe ejecutivo.\n"
        f"**Estructura:** Introducción, Hallazgos, Insights, Conclusiones.\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
    )

def get_grounded_chat_prompt(conversation_history, relevant_info, long_term_memory=""):
    """Chat RAG estricto con tooltips ricos."""
    
    bloque_memoria = ""
    if long_term_memory:
        bloque_memoria = f"""
    **🧠 MEMORIA DEL PROYECTO:**
    {long_term_memory}
    --------------------------------------------------
    """

    return (
        f"**Rol:** Asistente de investigación.\n"
        f"**Tarea:** Responde la ÚLTIMA pregunta usando 'Información Documentada' y 'Memoria'.\n\n"
        f"{bloque_memoria}"
        f"**📄 Info Documentada:**\n{relevant_info}\n\n"
        f"**💬 Historial:**\n{conversation_history}\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
        "**Respuesta:**"
    )

def get_followup_suggestions_prompt(previous_answer):
    """Sugerencias de seguimiento."""
    return f"""
    **Contexto:** Acabas de dar esta respuesta:
    "{previous_answer[:3000]}"
    
    **Tarea:** Sugiere 3 preguntas MUY CORTAS (máx 7 palabras) para profundizar.
    **Reglas:** Sin verbatims, solo temas lógicos de continuidad.
    **Salida:** JSON list[str].
    """

# ==============================================================================
# PROMPTS CREATIVOS Y EVALUACIÓN
# ==============================================================================

def get_ideation_prompt(conv_history, relevant):
    return (
        f"**Rol:** Estratega de Innovación.\n"
        f"**Contexto:**\n{relevant}\n"
        f"**Historial:**\n{conv_history}\n"
        f"Responde de forma inspiradora.\n{INSTRUCCIONES_DE_CITAS}"
    )

def get_concept_gen_prompt(product_idea, context_info):
    return (
        f"**Rol:** Estratega de Producto.\n"
        f"**Idea:** \"{product_idea}\"\n"
        f"**Contexto:** \"{context_info}\"\n"
        f"Genera concepto estructurado (Necesidad, Descripción, Beneficios, Rutas).\n{INSTRUCCIONES_DE_CITAS}"
    )

def get_idea_eval_prompt(idea_input, context_info):
    return f"""
**Rol:** Director de Estrategia.
**Evidencia:** {context_info}
**Idea:** "{idea_input}"
Evalúa viabilidad.\n{INSTRUCCIONES_DE_CITAS}
"""

def get_image_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context):
    return [
        "**Rol:** Director Creativo.",
        f"Target: {target_audience} | Objetivos: {comm_objectives}",
        f"Datos: {relevant_text_context[:8000]}", 
        "Evalúa la imagen (Impacto, Claridad, Branding, CTA).",
        INSTRUCCIONES_DE_CITAS
    ]

def get_video_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context):
    return [
        "**Rol:** Director Audiovisual.",
        f"Target: {target_audience} | Objetivos: {comm_objectives}",
        f"Datos: {relevant_text_context[:8000]}",
        "Evalúa el video (Ritmo, Mensaje, Branding, CTA).",
        INSTRUCCIONES_DE_CITAS
    ]

# ==============================================================================
# PROMPTS DE ANÁLISIS DE TEXTO Y MULTIMEDIA
# ==============================================================================

def get_transcript_prompt(combined_context, user_prompt):
    return (
        f"**Rol:** Investigador Cualitativo.\n"
        f"**Pregunta:** {user_prompt}\n"
        f"**Info:**\n{combined_context}\n"
        f"Identifica patrones y sintetiza con quotes.\n{INSTRUCCIONES_DE_CITAS}"
    )

def get_text_analysis_summary_prompt(full_context):
    return f"""
**Rol:** Investigador Cualitativo.
**Tarea:** Resumen Ejecutivo exhaustivo.
**Entrada:** {full_context}
**Salida (Markdown):** Resumen y Hallazgos por Tema.
"""

def get_autocode_prompt(context, main_topic):
    return f"""
**Rol:** Codificador Cualitativo.
**Tarea:** Extrae códigos sobre '{main_topic}'.
**Resumen:** {context}
**Salida:** Temas clave y Códigos (con citas).
{INSTRUCCIONES_DE_CITAS}
"""

def get_etnochat_prompt(conversation_history, text_context):
    return (
        "**Rol:** Etnógrafo Digital.\n"
        "**Tarea:** Responde sintetizando Chat, Transcripciones y Multimedia.\n"
        f"**Historial:**\n{conversation_history}\n"
        f"**Transcripciones:**\n{text_context}\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_media_transcription_prompt():
    return """
    **Rol:** Transcriptor.
    **Tarea:** Transcribe audio palabra por palabra. Describe acciones visuales entre corchetes.
    **Salida:** Texto plano.
    """

# ==============================================================================
# PROMPTS DE ONE-PAGER
# ==============================================================================

PROMPTS_ONEPAGER = {
    "Definición de Oportunidades": """Genera JSON: {"template_type": "oportunidades", "titulo_diapositiva": "...", "insight_clave": "...", "hallazgos_principales": [], "oportunidades": [], "recomendacion_estrategica": "..."}""",
    "Análisis DOFA (SWOT)": """Genera JSON: {"template_type": "dofa", "titulo_diapositiva": "...", "fortalezas": [], "oportunidades": [], "debilidades": [], "amenazas": []}""",
    "Mapa de Empatía": """Genera JSON: {"template_type": "empatia", "titulo_diapositiva": "...", "piensa_siente": [], "ve": [], "dice_hace": [], "oye": [], "esfuerzos": [], "resultados": []}""",
    "Propuesta de Valor (Value Proposition)": """Genera JSON: {"template_type": "propuesta_valor", "titulo_diapositiva": "...", "producto_servicio": "...", "creadores_alegria": [], "aliviadores_frustracion": [], "trabajos_cliente": [], "alegrias": [], "frustraciones": []}""",
    "Mapa del Viaje (Journey Map)": """Genera JSON: {"template_type": "journey_map", "titulo_diapositiva": "...", "etapa_1": {}, "etapa_2": {}, "etapa_3": {}}""",
    "Matriz de Posicionamiento (2x2)": """Genera JSON: {"template_type": "matriz_2x2", "titulo_diapositiva": "...", "eje_x_positivo": "...", "eje_x_negativo": "...", "eje_y_positivo": "...", "eje_y_negativo": "...", "items_cuadrante_sup_izq": [], "items_cuadrante_sup_der": [], "items_cuadrante_inf_izq": [], "items_cuadrante_inf_der": [], "conclusion_clave": "..."}""",
    "Perfil de Buyer Persona": """Genera JSON: {"template_type": "buyer_persona", "titulo_diapositiva": "...", "perfil_nombre": "...", "perfil_demografia": "...", "necesidades_jtbd": [], "puntos_dolor_frustraciones": [], "deseos_motivaciones": [], "citas_clave": []}"""
}

def get_onepager_final_prompt(relevant_info, selected_template_name, tema_central):
    t = PROMPTS_ONEPAGER.get(selected_template_name, "{}")
    return f"Completa template JSON '{selected_template_name}' sobre '{tema_central}'. Info: {relevant_info}. Salida solo JSON. {t}"

def get_excel_autocode_prompt(main_topic, responses_sample):
    return f"Define categorías (nodos) para '{main_topic}'. Respuestas: {str(responses_sample)}. Salida JSON array."

# ==============================================================================
# PROMPTS DE ANÁLISIS DE DATOS
# ==============================================================================

def get_survey_articulation_prompt(survey_context, repository_context, conversation_history):
    return (
        f"**Rol:** Investigador de Mercados.\n"
        f"**Tarea:** Articula datos Excel con Repositorio.\n"
        f"**Excel:**\n{survey_context}\n"
        f"**Repo:**\n{repository_context}\n"
        f"**Historial:**\n{conversation_history}\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_data_summary_prompt(data_snapshot_str):
    return f"Resumen ejecutivo de datos:\n{data_snapshot_str}"

def get_correlation_prompt(correlation_matrix_str):
    return f"Interpreta correlaciones:\n{correlation_matrix_str}"

def get_stat_test_prompt(test_type, p_value, num_col, cat_col, num_groups):
    return f"Interpreta prueba {test_type} para '{num_col}' por '{cat_col}'. P-value: {p_value}."

# ==============================================================================
# SECCIÓN: ANÁLISIS DE TENDENCIAS
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
**Misión:** Intelligence Brief sobre: "{topic}".
**Insumos:** {repo_context[:10000]} {pdf_context[:10000]} {sources_text}
Genera reporte Markdown.
"""

def get_trend_synthesis_prompt(keyword, trend_context, geo_context, topics_context, internal_context):
    return f"""
    **Rol:** Coolhunter.
    **Objetivo:** Radar 360 sobre "{keyword}".
    **Datos:** {trend_context} {geo_context} {topics_context} {internal_context}
    Genera Brief estratégico.
    """

# ==============================================================================
# PROMPTS DE PERFILES SINTÉTICOS
# ==============================================================================

def get_persona_generation_prompt(segment_name, relevant_info):
    return f"""
    **Rol:** Psicólogo del Consumidor.
    **Tarea:** Perfil Sintético para "{segment_name}".
    **Datos:** {relevant_info[:25000]}
    **Estilo:** Neutro.
    **Salida:** JSON.
    """

def get_persona_chat_instruction(persona_json, user_question):
    p = persona_json 
    return f"""
    **ACTING:** ERES **{p.get('nombre')}**.
    **Perfil:** {p.get('bio_breve')}
    **Pregunta:** "{user_question}"
    Responde como {p.get('nombre')} en Español Neutro.
    """
