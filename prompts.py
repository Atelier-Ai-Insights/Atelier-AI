import streamlit as st
from datetime import datetime

# ==============================================================================
# INSTRUCCIONES GLOBALES (CRÍTICO: TOOLTIPS CON EVIDENCIA RICA)
# ==============================================================================

# --- BLOQUE DE INSTRUCCIONES DE CITAS (MEJORADO: EVIDENCIA EXPANDIDA) ---
INSTRUCCIONES_DE_CITAS = """
**REGLAS DE EVIDENCIA Y CITAS (SISTEMA RAG - ESTRICTO):**
1. **Veracidad Absoluta:** Responde ÚNICAMENTE usando la 'Información documentada'.
2. **Atribución Inmediata (FORMATO OBLIGATORIO):** Cada vez que cites un hecho, DEBES usar este formato exacto al final de la frase:
   **[Fuente: NombreDelArchivo.docx; Contexto: "Cita textual relevante o explicación detallada del dato (aprox 20 palabras)"]**
   
   *Ejemplo Correcto:* "El 45% prefiere rojo [Fuente: Encuesta_2024.pdf; Contexto: "Según la Tabla 4, el segmento joven prioriza el color rojo por encima del precio."]"
   *Incorrecto:* [Fuente: Archivo] (Falta el contexto rico)

3. **Sin Lista Final:** No generes lista de fuentes al final, usa solo las citas en línea.
"""

# ==============================================================================
# PROMPTS DE REPORTES Y CHAT BÁSICO
# ==============================================================================

def get_report_prompt1(question, relevant_info):
    """Extracción de hallazgos fácticos."""
    return (
        f"**Pregunta:** {question}\n\n"
        f"**Contexto:**\n{relevant_info}\n\n"
        f"**Tarea:** Extrae hallazgos fácticos y datos duros.\n"
        f"{INSTRUCCIONES_DE_CITAS}\n\n"
        "**Salida:**\nMarkdown estructurado."
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
        f"- **Lenguaje:** Directo, activo, sin adjetivos vacíos.\n"
        f"- **Profundidad:** Explica POR QUÉ importa (Implicaciones).\n\n"
        
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
        f"**Tarea:** Responde la ÚLTIMA pregunta sintetizando la info.\n\n"
        f"{bloque_memoria}"
        f"**📄 Info Documentada:**\n{relevant_info}\n\n"
        f"**💬 Historial:**\n{conversation_history}\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
        "**Respuesta:**"
    )

def get_followup_suggestions_prompt(previous_answer):
    return f"""
    **Contexto:** Respuesta anterior: "{previous_answer[:3000]}"
    **Tarea:** Sugiere 3 preguntas MUY CORTAS para profundizar.
    **Salida:** JSON list[str]. Ejemplo: ["Ver demográficos", "Comparar años", "Analizar riesgos"]
    """

# ==============================================================================
# PROMPTS CREATIVOS
# ==============================================================================

def get_ideation_prompt(conv_history, relevant):
    return (
        f"**Rol:** Estratega de Innovación.\n"
        f"**Contexto:**\n{relevant}\n"
        f"**Historial:**\n{conv_history}\n"
        f"Genera 5 ideas disruptivas usando Lateral Thinking.\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_concept_gen_prompt(product_idea, context_info):
    return (
        f"**Rol:** Estratega de Producto.\n"
        f"**Tarea:** Concepto para: \"{product_idea}\".\n"
        f"**Contexto:** \"{context_info}\".\n\n"
        f"**Estructura:** 1. Consumer Truth, 2. La Solución, 3. Beneficios, 4. Conceptos (Ruta A y B).\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_idea_eval_prompt(idea_input, context_info):
    return f"""
    **Rol:** Director de Estrategia.
    **Evidencia:** {context_info}
    **Idea:** "{idea_input}"
    Evalúa viabilidad, deseabilidad y factibilidad.
    \n{INSTRUCCIONES_DE_CITAS}
    """

def get_image_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context):
    return [
        "**Rol:** Director Creativo.",
        f"Target: {target_audience} | Objetivos: {comm_objectives}",
        f"Datos: {relevant_text_context[:8000]}", 
        "Evalúa imagen (Impacto, Branding).",
        INSTRUCCIONES_DE_CITAS
    ]

def get_video_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context):
    return [
        "**Rol:** Director Audiovisual.",
        f"Target: {target_audience} | Objetivos: {comm_objectives}",
        f"Datos: {relevant_text_context[:8000]}",
        "Evalúa video (Narrativa, Ritmo).",
        INSTRUCCIONES_DE_CITAS
    ]

# ==============================================================================
# PROMPTS DE ANÁLISIS DE TEXTO (Ajustados)
# ==============================================================================

def get_transcript_prompt(combined_context, user_prompt):
    return (
        f"**Rol:** Investigador Cualitativo Experto.\n"
        f"**Pregunta:** {user_prompt}\n"
        f"**Info (Transcripciones):**\n{combined_context}\n"
        f"**Instrucción:** Identifica patrones recurrentes y anomalías.\n"
        f"**Regla de Evidencia:** NO uses formatos de metadatos complejos. Integra las citas textuales naturalmente en el párrafo.\n"
        f"Ejemplo: 'Los usuarios mencionan sentirse frustrados por el precio, como se ve en el Documento A: \"es demasiado caro para lo que ofrece\".'\n"
        f"Usa comillas para la evidencia literal.\n"
    )

def get_text_analysis_summary_prompt(full_context):
    return f"""
    **Rol:** Investigador Cualitativo.
    **Tarea:** Resumen Ejecutivo exhaustivo.
    **Entrada:** {full_context}
    **Salida:** Resumen general y desglose por Temas.
    """

def get_etnochat_prompt(conversation_history, text_context):
    return (
        "**Rol:** Etnógrafo Digital.\n"
        "**Tarea:** Responde sintetizando fuentes.\n"
        f"**Historial:**\n{conversation_history}\n"
        f"**Contexto:**\n{text_context}\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_media_transcription_prompt():
    return """
    **Rol:** Transcriptor.
    **Tarea:** Transcribe audio verbatim.
    **Formato:** Texto plano con hablantes identificados.
    """

# ==============================================================================
# PROMPTS DE ONE-PAGER y OTROS
# ==============================================================================
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
        f"**SISTEMA:** Generador JSON.\n"
        f"**Tarea:** Template '{tema_central}'.\n"
        f"**Info:** {relevant_info[:15000]}\n"
        f"**TEMPLATE:** {t}\n"
        f"**REGLA:** Solo JSON válido."
    )

def get_excel_autocode_prompt(main_topic, responses_sample):
    return f"Categoriza respuestas sobre '{main_topic}'. Muestra: {str(responses_sample)}. Salida: JSON array de categorías."

def get_survey_articulation_prompt(survey_context, repository_context, conversation_history):
    return (
        f"**Rol:** Investigador Cuantitativo.\n"
        f"**Tarea:** Articula hallazgos.\n"
        f"**Datos Excel:**\n{survey_context}\n"
        f"**Contexto Repo:**\n{repository_context}\n"
        f"**Historial:**\n{conversation_history}\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_data_summary_prompt(data_snapshot_str):
    return f"Resumen ejecutivo de datos:\n{data_snapshot_str}"

def get_correlation_prompt(correlation_matrix_str):
    return f"Interpreta correlaciones:\n{correlation_matrix_str}"

def get_stat_test_prompt(test_type, p_value, num_col, cat_col, num_groups):
    return f"Interpreta prueba {test_type} para '{num_col}' por '{cat_col}'. P-value: {p_value}."

def get_trend_analysis_prompt(topic, repo_context, pdf_context, public_sources_list):
    current_date = datetime.now().strftime("%d de %B de %Y")
    sources_text = "\n".join([f"- {s}" for s in public_sources_list]) if public_sources_list else ""
    return f"""
    **Fecha:** {current_date}. Brief sobre: "{topic}".
    Clasifica: 1. Mega-Tendencias, 2. Fads, 3. Señales Débiles.
    **Insumos:** {repo_context[:10000]} {pdf_context[:10000]} {sources_text}
    """

def get_trend_synthesis_prompt(keyword, trend_context, geo_context, topics_context, internal_context):
    return f"Radar 360 sobre '{keyword}'. Datos: {trend_context} {geo_context}. Sintetiza oportunidades."

def get_persona_generation_prompt(segment_name, relevant_info):
    return f"""
    **Rol:** Psicólogo. Crea Perfil Sintético para "{segment_name}".
    **Datos:** {relevant_info[:25000]}
    **Salida JSON:** {{nombre, edad, ocupacion, bio_breve, personalidad, dolores_principales, motivadores_compra, estilo_comunicacion, creencias_limitantes, frustracion_oculta}}
    """

def get_persona_chat_instruction(persona_json, user_question):
    p = persona_json 
    return f"""
    **ACTUACIÓN:** Eres {p.get('nombre')}.
    Personalidad: {p.get('personalidad')}. Frustración: {p.get('frustracion_oculta')}.
    Pregunta: "{user_question}". Responde corto y natural.
    """
