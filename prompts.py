import streamlit as st
from datetime import datetime
import json

# ==============================================================================
# INSTRUCCIONES GLOBALES (BLINDAJE DE EXHAUSTIVIDAD Y TRAZABILIDAD)
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
    """Fase 2: Redacción de informe ejecutivo de alta densidad (C-Level)."""
    return (
        f"**Rol:** Socio Senior de Consultoría Estratégica (Atelier).\n"
        f"**Objetivo:** Redactar un Intelligence Report de alto impacto que agote TODA la evidencia disponible. Evita la brevedad; se busca un análisis robusto.\n"
        f"**Pregunta de Negocio:** {question}\n"
        f"**Insumos Brutos:**\n1. Hallazgos preliminares: {result1}\n2. Data Room Completo: {relevant_info}\n\n"
        f"**Instrucciones de Rigor:**\n"
        f"- **Prohibido resumir en exceso:** Explica la importancia estratégica de cada hallazgo y conéctalo con otros datos del Data Room para dar profundidad.\n"
        f"- **Cruce de Fuentes Obligatorio:** La respuesta debe reflejar un análisis comparativo entre múltiples archivos.\n\n"
        f"**Estructura del Entregable:**\n"
        f"1. **Resumen Ejecutivo:** (3-5 líneas).\n"
        f"2. **Análisis por Pilares:** Hallazgos detallados y extendidos con alta densidad de citas [1, 2].\n"
        f"3. **Insights y Tensiones:** Conexión de puntos y lecturas profundas.\n"
        f"4. **Recomendaciones Estratégicas:** Pasos accionables basados en la evidencia.\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
    )

def get_grounded_chat_prompt(conversation_history, relevant_info, long_term_memory=""):
    """Chat RAG estricto configurado para respuestas largas y detalladas."""
    bloque_memoria = f"**🧠 MEMORIA DEL PROYECTO (Contexto previo):**\n{long_term_memory}\n---" if long_term_memory else ""
    return (
        f"**Rol:** Analista de Insights Senior en Atelier AI.\n"
        f"**Misión:** Proporcionar respuestas PROFUNDAS, extensas y verificables.\n\n"
        f"{bloque_memoria}\n"
        f"**📄 Información Documentada (Fuente de Verdad):**\n{relevant_info}\n\n"
        f"**💬 Historial de Conversación:**\n{conversation_history}\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
        "**Respuesta Analítica Extendida:**"
    )

# ==============================================================================
# PROMPTS DE ANÁLISIS DE TEXTOS Y TRANSCRIPCIONES
# ==============================================================================

def get_transcript_prompt(transcript_text, additional_instructions=""):
    return (
        f"**Rol:** Especialista en Análisis Cualitativo.\n"
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

# ==============================================================================
# PROMPTS RESTAURADOS (MULTIMEDIA Y TENDENCIAS)
# ==============================================================================

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

def get_etnochat_prompt(conversation_history, text_context):
    return (
        f"**Rol:** Etnógrafo Digital.\n"
        f"**Tarea:** Responde sintetizando fuentes variadas (Chat, Transcripciones, Multimedia).\n"
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
# ANÁLISIS DE TENDENCIAS
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
# PROMPTS RESTAURADOS (PERSONAS SINTÉTICAS)
# ==============================================================================

def get_persona_generation_prompt(segment_name, relevant_info):
    """Crea la ficha psicológica del perfil sintético realista."""
    return f"""
    **Rol:** Psicólogo del Consumidor.
    **Tarea:** Basándote en los datos: "{segment_name}", crea un Perfil Sintético realista
