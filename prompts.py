import streamlit as st
from datetime import datetime
import json

# ==============================================================================
# INSTRUCCIONES GLOBALES (BLINDAJE DE EXHAUSTIVIDAD Y TRAZABILIDAD)
# ==============================================================================

INSTRUCCIONES_DE_CITAS = """
**REGLAS DE EVIDENCIA Y ANÁLISIS (SISTEMA RAG - ESTRICTO):**
1. **Análisis Exhaustivo y Extenso:** Tu objetivo es la profundidad. Prohibido dar respuestas cortas o resúmenes ejecutivos a menos que se pida explícitamente. Si la información está dispersa en varios documentos, conéctala, compárala y desarrolla cada punto con detalle técnico.
2. **Densidad de Datos:** Responde ÚNICAMENTE con la 'Información documentada'. Debes incluir porcentajes, cifras exactas, verbatims y todos los hallazgos específicos disponibles. Si un tema tiene múltiples aristas en los documentos, explora cada una de ellas.
3. **Atribución Inmediata:** Cada hallazgo debe llevar su sustento técnico al final de la frase. Formato: [1], [2]. Si una idea surge de cruzar dos fuentes, usa [1, 2].
4. **SECCIÓN DE FUENTES (Obligatoria al final):**
    Genera una lista numerada que relacione los índices usados. Usa este formato exacto:
    
    **Fuentes Verificadas:**
    [1] Nombre_del_Archivo_A.pdf
    [2] Nombre_del_Archivo_B.pdf

    ⚠️ **CRÍTICO:** Solo el nombre del archivo. El sistema ocultará esta lista visualmente en el chat, pero la usará para habilitar el modal de referencias detalladas.
"""

# ==============================================================================
# PROMPTS DE REPORTES Y CHAT BÁSICO
# ==============================================================================

def get_report_prompt1(question, relevant_info):
    """Fase 1: Extracción masiva de hallazgos fácticos."""
    return (
        f"**Pregunta de Investigación:** {question}\n\n"
        f"**Data Room (Contexto):**\n{relevant_info}\n\n"
        f"**Tarea:** Realiza un escaneo profundo y exhaustivo de la data. Extrae TODOS los hallazgos fácticos, datos numéricos y señales detectadas sin omitir detalles por brevedad.\n"
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
        f"- **Cruce de Fuentes Obligatorio:** La respuesta debe reflejar un análisis comparativo entre múltiples archivos.\n"
        f"- **Principio de la Pirámide:** Empieza con un BLUF contundente, pero desarrolla el cuerpo del informe con extensión analítica.\n\n"
        
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
        f"**Misión:** Proporcionar respuestas PROFUNDAS, extensas y verificables. Si el usuario hace una pregunta, no te limites a lo obvio; explora toda la Información Documentada para dar la versión más completa y detallada posible.\n\n"
        f"{bloque_memoria}\n"
        f"**📄 Información Documentada (Fuente de Verdad):**\n{relevant_info}\n\n"
        f"**💬 Historial de Conversación:**\n{conversation_history}\n\n"
        f"**Instrucción Adicional:** Desarrolla tus ideas. Si un tema es mencionado brevemente en un documento pero se conecta con otro, elabora esa conexión. Sé elocuente y exhaustivo.\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
        "**Respuesta Analítica Extendida:**"
    )

def get_followup_suggestions_prompt(previous_answer):
    """Sugerencias de seguimiento lógicas."""
    return f"""
    **Contexto:** Acabas de dar esta respuesta: "{previous_answer[:2000]}"
    **Tarea:** Sugiere 3 preguntas cortas (máx 7 palabras) para profundizar en los datos o explorar áreas laterales del análisis.
    **Salida:** JSON list[str].
    """

# ==============================================================================
# PROMPTS CREATIVOS Y EVALUACIÓN
# ==============================================================================

def get_ideation_prompt(conv_history, relevant):
    """Ideación fundamentada en evidencia documental."""
    return (
        f"**Rol:** Estratega de Innovación Disruptiva.\n"
        f"**Contexto de Datos:**\n{relevant}\n"
        f"**Historial:**\n{conv_history}\n"
        
        f"**Tarea:** Genera 5 ideas aplicando el método 'Pensamiento Lateral'. Cada idea debe estar profundamente sustentada en datos reales del contexto (usa citas [x]). Desarrolla el razonamiento detrás de cada idea.\n"
        f"Estructura: Idea, Provocación, Analogía e Insight de soporte extendido.\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_concept_gen_prompt(product_idea, context_info):
    """Desarrollo de concepto estratégico con RTB sólido."""
    return (
        f"**Rol:** Estratega de Producto Senior.\n"
        f"**Tarea:** Desarrolla un concepto GANADOR y detallado para la idea: \"{product_idea}\".\n"
        f"**Sustento de Mercado:** {context_info}\n\n"
        
        f"**Formato de Salida OBLIGATORIO (Markdown):**\n"
        f"1. **Consumer Truth:** (Tensión analizada a profundidad con citas [x])\n"
        f"2. **La Solución:** (Propuesta de valor enriquecida y detallada)\n"
        f"3. **Beneficios Clave:** (Lista de beneficios con explicación de por qué importan)\n"
        f"4. **Rutas Creativas (A y B):** Incluye Insight, What y RTB con amplia evidencia técnica.\n\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_idea_eval_prompt(idea_input, context_info):
    """Evaluación crítica basada en datos duros."""
    return (
        f"**Rol:** Director de Estrategia.\n"
        f"**Idea:** {idea_input}\n"
        f"**Evidencia:** {context_info}\n"
        f"Realiza un análisis exhaustivo de viabilidad, deseabilidad y factibilidad. No resumas; utiliza toda la evidencia documental disponible para justificar tu juicio.\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

# ==============================================================================
# ANÁLISIS MULTIMEDIA Y TENDENCIAS
# ==============================================================================

def get_image_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context):
    """Evaluación de impacto visual basada en contexto de mercado."""
    return [
        "**Rol:** Director Creativo y Semiótico.",
        f"Target: {target_audience} | Objetivos: {comm_objectives}",
        f"Contexto Estratégico: {relevant_text_context[:8000]}",
        "Evalúa la imagen con profundidad (Impacto, Branding, CTA). Cruza tu análisis visual con los datos de mercado del contexto.",
        INSTRUCCIONES_DE_CITAS
    ]

def get_video_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context):
    """Evaluación de narrativa audiovisual."""
    return [
        "**Rol:** Director Audiovisual y de Estrategia.",
        f"Target: {target_audience} | Objetivos: {comm_objectives}",
        f"Contexto Estratégico: {relevant_text_context[:8000]}",
        "Realiza una crítica técnica y estratégica del video (Narrativa, Ritmo, Branding) contrastando con la información documentada.",
        INSTRUCCIONES_DE_CITAS
    ]

# ==============================================================================
# PROMPTS DE ESTRUCTURAS DE DATOS (ONE-PAGER / JSON)
# ==============================================================================

def get_onepager_prompt(topic, context):
    """Estructura de One Pager ejecutiva."""
    return f"""
    Actúa como un estratega de negocios senior. Estructura un "One Pager" sobre: "{topic}".
    Insumos RAG: {context[:25000]}
    
    Respuesta: EXCLUSIVAMENTE JSON válido con llaves: titulo, subtitulo, puntos_clave (list), insight_principal.
    """

def get_onepager_final_prompt(relevant_info, selected_template_name, tema_central):
    """Generador de JSON blindado para diapositivas específicas."""
    return (
        f"**SISTEMA:** Generador de JSON Estratégico.\n"
        f"**Tarea:** Completa el template para '{tema_central}' usando: {relevant_info[:15000]}\n"
        f"**REGLA:** Devuelve SOLAMENTE el JSON crudo, sin bloques de código markdown ni texto extra."
    )

# ==============================================================================
# ANÁLISIS NUMÉRICO Y TENDENCIAS
# ==============================================================================

def get_data_analysis_prompt(user_query, relevant_info):
    """Análisis estadístico y numérico profundo."""
    return (
        f"**Tarea:** Realiza un análisis numérico detallado y exhaustivo de: {user_query}\n"
        f"**Datos Extraídos:** {relevant_info}\n"
        f"Identifica medias, tendencias, y valores atípicos. No te limites a las cifras; explica el impacto de estos datos para el negocio con profundidad.\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_trend_analysis_prompt(topic, repo_context, pdf_context, public_sources_list):
    """Intelligence Brief de tendencias de mercado."""
    current_date = datetime.now().strftime("%d de %B de %Y")
    sources = "\n".join([f"- {s}" for s in public_sources_list]) if public_sources_list else "No especificadas"
    
    return f"""
    **Fecha:** {current_date} | **Misión:** Intelligence Brief detallado sobre "{topic}".
    **Insumos:** {repo_context[:8000]} {pdf_context[:8000]}
    **Fuentes:** {sources}
    
    Clasifica en: Mega-Tendencias, Fads y Señales Débiles. Desarrolla cada categoría con evidencia y conecta los hallazgos para hallar oportunidades de innovación reales.
    """
