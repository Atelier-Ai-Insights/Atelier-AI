import streamlit as st
from datetime import datetime

# ==============================================================================
# INSTRUCCIONES GLOBALES (CRÍTICO: FORMATO DE SALIDA DE FUENTES)
# ==============================================================================

# --- BLOQUE DE INSTRUCCIONES DE CITAS (CON CONTEXTO) ---
# CAMBIO: Se ajustó para prohibir nombres de archivo en el cuerpo del texto
INSTRUCCIONES_DE_CITAS = """
**REGLAS DE CITAS Y EVIDENCIA (ESTRICTO):**
1. **Base:** Solo usa la 'Información documentada'. No alucines información externa.
2. **Formato en Texto (CRÍTICO):** Usa SOLO el número entre corchetes para referenciar.
   - ✅ CORRECTO: "El mercado creció un 5% [1]."
   - 🚫 INCORRECTO: "El mercado creció [1] Reporte.pdf". NUNCA pongas el nombre del archivo dentro del párrafo.
3. **SECCIÓN FUENTES (OBLIGATORIA AL FINAL):**
   Genera una lista al final con este formato EXACTO (usando '|||' como separador):
   
   **Fuentes:**
   [1] NombreArchivo.pdf ||| Breve frase (máx 20 palabras) con el dato específico o cita textual.
   [2] OtroArchivo.pdf ||| Explicación del hallazgo.
"""

# ==============================================================================
# PROMPTS DE REPORTES Y CHAT BÁSICO
# ==============================================================================

def get_report_prompt1(question, relevant_info):
    """Extracción de hallazgos (Directo al grano)."""
    return (
        f"**Pregunta:** {question}\n\n"
        f"**Contexto:**\n{relevant_info}\n\n"
        f"**Tarea:** Extrae hallazgos fácticos del contexto que respondan la pregunta.\n"
        f"{INSTRUCCIONES_DE_CITAS}\n\n"
        "**Salida (Markdown):**\n"
        "## Hallazgos Clave\n"
        "* [Hallazgo con cita [x]]\n"
        "...\n"
        "## Fuentes\n..."
    )

def get_report_prompt2(question, result1, relevant_info):
    """Redacción de informe (Estructura forzada)."""
    return (
        f"**Rol:** Analista experto de Atelier.\n"
        f"**Pregunta:** {question}\n"
        f"**Insumos:**\n1. Hallazgos Previos: {result1}\n2. Contexto Completo: {relevant_info}\n\n"
        f"**Tarea:** Redacta informe ejecutivo estructurado.\n"
        f"**Estructura:**\n"
        f"1. **Introducción:** Contexto breve.\n"
        f"2. **Hallazgos:** Hechos con citas [x].\n"
        f"3. **Insights:** Interpretación profunda.\n"
        f"4. **Conclusiones y Recomendaciones:** 3-4 acciones.\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
    )

def get_grounded_chat_prompt(conversation_history, relevant_info, long_term_memory=""):
    """
    Chat RAG estricto con inyección de Memoria de Largo Plazo (Bitácora).
    """
    
    bloque_memoria = ""
    if long_term_memory:
        bloque_memoria = f"""
    **🧠 MEMORIA DEL PROYECTO (Bitácora de Hallazgos Previos):**
    El usuario ha guardado estos insights clave en el pasado. Úsalos para dar contexto, pero prioriza la "Info Documentada" nueva si hay contradicción.
    {long_term_memory}
    --------------------------------------------------
    """

    return (
        f"**Rol:** Asistente de investigación.\n"
        f"**Tarea:** Responde la ÚLTIMA pregunta del historial usando SOLO la 'Información Documentada' y la 'Memoria del Proyecto'.\n\n"
        f"{bloque_memoria}"
        f"**📄 Info Documentada (Extractos actuales):**\n{relevant_info}\n\n"
        f"**💬 Historial Reciente:**\n{conversation_history}\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
        "**Respuesta:**"
    )

def get_followup_suggestions_prompt(previous_answer):
    """
    Genera 3 preguntas de seguimiento CORTAS.
    """
    return f"""
    **Contexto:** Acabas de dar esta respuesta basada en un documento:
    "{previous_answer[:3000]}"
    
    **Tarea:** Sugiere 3 preguntas MUY CORTAS para que el usuario profundice en los temas que ACABAS de mencionar.
    
    **Reglas de Oro:**
    1. **GARANTÍA DE INFORMACIÓN:** Solo sugiere profundizar en temas que TÚ MISMO mencionaste.
    2. **SIN VERBATIMS:** No pidas "citas textuales".
    3. **ULTRACORTAS:** Máximo 7-8 palabras por pregunta.
    
    **Salida:** SOLO devuelve un JSON con una lista de strings.
    """

# ==============================================================================
# PROMPTS CREATIVOS Y EVALUACIÓN
# ==============================================================================

def get_ideation_prompt(conv_history, relevant):
    """Ideación."""
    return (
        f"**Rol:** Estratega de Innovación Creativo.\n"
        f"**Objetivo:** Generar soluciones inspiradoras conectando los datos proporcionados.\n"
        f"**Contexto:**\n{relevant}\n\n"
        f"**Historial:**\n{conv_history}\n\n"
        f"**Instrucción:** Responde de forma sintética e inspiradora. Basa tus premisas en los datos.\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_concept_gen_prompt(product_idea, context_info):
    """Concepto estructurado."""
    return (
        f"**Rol:** Estratega de Producto.\n"
        f"**Tarea:** Desarrolla un concepto para la idea: \"{product_idea}\" usando este contexto: \"{context_info}\".\n\n"
        f"**Formato Salida (Markdown):**\n"
        f"### 1. Necesidad (Consumer Truth)\n(Sustentar con citas [x])\n\n"
        f"### 2. Descripción Producto\n(Enriquecer idea con contexto)\n\n"
        f"### 3. Beneficios (3-4)\n(Funcionales/Emocionales)\n\n"
        f"### 4. Conceptos (2 Rutas)\n"
        f"* **Opción A:** Insight + What + RTB (Reason to Believe con citas [x]) + Claim.\n"
        f"* **Opción B:** (Variante alternativa).\n\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_idea_eval_prompt(idea_input, context_info):
    """Evaluación crítica."""
    return f"""
**Rol:** Director de Estrategia.
**Tarea:** Evaluar viabilidad de la idea contra la evidencia de mercado.

**Evidencia:**
{context_info}

**Idea:**
"{idea_input}"

**Salida (Markdown):**
1. **Veredicto:** (Viable / Riesgoso / Descartar) en 1 frase.
2. **Alineación:** ¿Responde a necesidades reales del estudio? (Cita [x]).
3. **Barreras:** ¿Qué datos contradicen la idea? (Cita [x]).
4. **Recomendación:** Pasos a seguir.

{INSTRUCCIONES_DE_CITAS}
"""

def get_image_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context):
    return [
        "**Rol:** Director Creativo.",
        f"**Contexto:** Target: {target_audience} | Objetivos: {comm_objectives}",
        f"**Datos:** {relevant_text_context[:8000]}", 
        "**Tarea:** Analiza la imagen proporcionada.",
        "**Puntos a evaluar:**",
        "1. **Impacto:** ¿Atrae al target? (Usa citas de datos [1])",
        "2. **Claridad:** ¿Comunica el objetivo?",
        "3. **Branding:** ¿Coherente con la marca?",
        "4. **Call to Action:** ¿Motiva?",
        "**Conclusión:** Veredicto final.",
        INSTRUCCIONES_DE_CITAS
    ]

def get_video_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context):
    return [
        "**Rol:** Director Audiovisual.",
        f"**Contexto:** Target: {target_audience} | Objetivos: {comm_objectives}",
        f"**Datos:** {relevant_text_context[:8000]}",
        "**Tarea:** Analiza el video (audio/visual).",
        "**Puntos a evaluar:**",
        "1. **Impacto AV:** Ritmo, narrativa, audio. (Cita datos [1])",
        "2. **Mensaje:** ¿Se entiende?",
        "3. **Branding:** ¿Integración de marca?",
        "4. **CTA:** ¿Efectividad?",
        "**Conclusión:** Veredicto final.",
        INSTRUCCIONES_DE_CITAS
    ]

# ==============================================================================
# PROMPTS DE ANÁLISIS DE TEXTO Y MULTIMEDIA
# ==============================================================================

def get_transcript_prompt(combined_context, user_prompt):
    return (
        f"**Rol:** Investigador Cualitativo Senior experto en Análisis del Discurso.\n"
        f"**Objetivo:** Responder la pregunta identificando PATRONES y sintetizando las posturas de los participantes.\n\n"
        f"**Pregunta del Usuario:** {user_prompt}\n\n"
        f"**FUENTES DE INFORMACIÓN (Transcripciones y Notas):**\n{combined_context}\n\n"
        f"**Instrucciones de Análisis:**\n"
        f"1. **IDENTIFICACIÓN DE PATRONES:** No des respuestas aisladas. Agrupa las respuestas de los participantes en temas o patrones recurrentes.\n"
        f"2. **SÍNTESIS ESTRUCTURADA:** Tu respuesta debe sintetizar los hallazgos.\n"
        f"3. **EVIDENCIA REAL (Quotes):** Es OBLIGATORIO usar citas textuales breves entre comillas para soportar cada patrón identificado.\n"
        f"4. **MATICES:** Identifica si hay consenso o disidencias entre los participantes.\n"
        f"5. **REFERENCIAS:** Al final de las citas, indica [Fuente: NombreArchivo].\n\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_text_analysis_summary_prompt(full_context):
    return f"""
**Rol:** Investigador Cualitativo.
**Tarea:** Genera un Resumen Ejecutivo exhaustivo.

**Entrada:**
{full_context}

**Salida (Markdown):**
## Resumen Ejecutivo
(4-5 frases síntesis macro)

## Hallazgos por Tema
### 1. [Tema Relevante]
* [Hallazgo detallado. Fuente: Archivo]
* [Cita textual clave: "...". Fuente: Archivo]
"""

def get_autocode_prompt(context, main_topic):
    return f"""
**Rol:** Codificador Cualitativo.
**Tarea:** Extrae temas emergentes (códigos) sobre '{main_topic}' del siguiente resumen.

**Resumen:**
{context}

**Salida (Markdown):**
## Temas Clave
(Resumen brevísimo)

## Códigos Detectados (Máx 7)
### 1. [Nombre Código]
* [Explicación del hallazgo [x]]
* [Cita de soporte [x]]
(Repetir estructura)

{INSTRUCCIONES_DE_CITAS}
"""

def get_etnochat_prompt(conversation_history, text_context):
    return (
        "**Rol:** Etnógrafo Digital.\n"
        "**Tarea:** Responde al usuario sintetizando:\n"
        "1. Historial de Chat.\n"
        "2. Transcripciones (Contexto).\n"
        "3. Archivos Multimedia (Imágenes/Audios adjuntos).\n\n"
        f"**Historial:**\n{conversation_history}\n"
        f"**Transcripciones:**\n{text_context}\n\n"
        "**Nota:** Cita los archivos por nombre (ej. [foto1.jpg], [audio.mp3]).\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_media_transcription_prompt():
    return """
    **Rol:** Transcriptor.
    **Tarea:**
    1. Transcribe el audio palabra por palabra.
    2. Si es video, describe acciones visuales clave entre corchetes [Ej: Cliente sonríe].
    **Salida:** SOLO el texto plano. Sin introducciones.
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
    prompt_template = PROMPTS_ONEPAGER.get(selected_template_name, "{}")
    return f"""
    **Rol:** Analista Estratégico.
    **Info:** {relevant_info}
    **Tarea:** Completa el template JSON '{selected_template_name}' sobre '{tema_central}'.
    **Salida:** Solo el JSON válido, sin bloques de código markdown.
    {prompt_template.format(tema_central=tema_central)}
    """

def get_excel_autocode_prompt(main_topic, responses_sample):
    sample_text = str(responses_sample) 
    return f"""
**Rol:** Codificador de Encuestas.
**Tarea:** Define categorías (nodos) para analizar respuestas sobre '{main_topic}'.
**Muestra:** {sample_text}
**Salida:** SOLO un JSON válido.
"""

# ==============================================================================
# PROMPTS DE ANÁLISIS DE DATOS
# ==============================================================================

def get_survey_articulation_prompt(survey_context, repository_context, conversation_history):
    return (
        f"**Rol:** Investigador de Mercados.\n"
        f"**Tarea:** Responde articulando datos Excel con Repositorio.\n"
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
    base = f"""
**Rol:** Estadístico.
**Tarea:** Interpretar prueba {test_type} para '{num_col}' por grupos de '{cat_col}'.
**P-Value:** {p_value} (Umbral 0.05)
"""
    if p_value < 0.05:
        base += "\n**Conclusión:** ✅ Significativo. Hay diferencias reales entre grupos. Analizar medias."
    else:
        base += "\n**Conclusión:** ℹ️ No significativo. Las diferencias son azar."
    return base

# ==============================================================================
# SECCIÓN: ANÁLISIS DE TENDENCIAS
# ==============================================================================

SOURCE_LENSES = {
    "DANE": "Indicadores duros: IPC, Desempleo, PIB.",
    "Banco de la República": "Macroeconomía, tasas, TRM.",
    "Fenalco": "Comercio y Retail.",
    "Camacol": "Vivienda y Construcción.",
    "Euromonitor": "Megatendencias globales.",
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
