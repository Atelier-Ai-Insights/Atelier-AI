import streamlit as st
from datetime import datetime
import json

# ==============================================================================
# INSTRUCCIONES GLOBALES (BLINDAJE DE EXHAUSTIVIDAD Y TRAZABILIDAD)
# ==============================================================================

# Este bloque obliga a la IA a no resumir en exceso y a conectar múltiples fuentes.
INSTRUCCIONES_DE_CITAS = """
**REGLAS DE EVIDENCIA Y ANÁLISIS (SISTEMA RAG - ESTRICTO):**
1. **Análisis Exhaustivo:** Tu objetivo es la profundidad. No resumas en exceso. Si la información está dispersa en varios documentos, conéctala, compárala y extrae todas las implicaciones posibles.
2. **Veracidad y Datos Duros:** Responde ÚNICAMENTE con la 'Información documentada'. Incluye porcentajes, cifras, verbatims y hallazgos específicos. Si algo no está, busca datos relacionados que aporten contexto.
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
        f"**Tarea:** Realiza un escaneo profundo de la data y extrae TODOS los hallazgos fácticos, datos numéricos y señales detectadas.\n"
        f"{INSTRUCCIONES_DE_CITAS}\n\n"
        "**Salida:** Markdown estructurado por temas con alta densidad de datos."
    )

def get_report_prompt2(question, result1, relevant_info):
    """Fase 2: Redacción de informe ejecutivo de alta densidad (C-Level)."""
    return (
        f"**Rol:** Socio Senior de Consultoría Estratégica (Atelier).\n"
        f"**Objetivo:** Redactar un Intelligence Report de alto impacto que agote la evidencia disponible.\n"
        f"**Pregunta de Negocio:** {question}\n"
        f"**Insumos Brutos:**\n1. Hallazgos preliminares: {result1}\n2. Data Room Completo: {relevant_info}\n\n"
        
        f"**Instrucciones de Rigor:**\n"
        f"- **Densidad de Información:** No solo describas hallazgos; explica su importancia estratégica y relaciónalo con otros datos del Data Room.\n"
        f"- **Cruce de Fuentes:** Es vital que la respuesta refleje que has consultado múltiples archivos. Compara cifras entre fuentes.\n"
        f"- **Principio de la Pirámide:** Empieza con un BLUF (Bottom Line Up Front) contundente.\n\n"
        
        f"**Estructura del Entregable:**\n"
        f"1. **Resumen Ejecutivo:** Conclusión principal en 3-5 líneas.\n"
        f"2. **Análisis por Pilares:** Hallazgos detallados con alta densidad de citas [1, 2].\n"
        f"3. **Insights y Tensiones:** Conexión de puntos y lecturas no evidentes.\n"
        f"4. **Recomendaciones Estratégicas:** Pasos accionables basados en la evidencia.\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
    )

def get_grounded_chat_prompt(conversation_history, relevant_info, long_term_memory=""):
    """Chat RAG estricto configurado para respuestas largas y detalladas."""
    bloque_memoria = f"**🧠 MEMORIA DEL PROYECTO (Contexto previo):**\n{long_term_memory}\n---" if long_term_memory else ""

    return (
        f"**Rol:** Analista de Insights Senior en Atelier AI.\n"
        f"**Misión:** Proporcionar respuestas PROFUNDAS y verificables. Si el usuario hace una pregunta, busca en todos los documentos proporcionados para dar la respuesta más completa posible.\n\n"
        f"{bloque_memoria}\n"
        f"**📄 Información Documentada (Fuente de Verdad):**\n{relevant_info}\n\n"
        f"**💬 Historial de Conversación:**\n{conversation_history}\n\n"
        f"**Instrucción Adicional:** Si la información es escasa en un punto, busca temas relacionados en los documentos para dar contexto. Sé elocuente y analítico.\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
        "**Respuesta Analítica:**"
    )

def get_followup_suggestions_prompt(previous_answer):
    """Sugerencias de seguimiento lógicas."""
    return f"""
    **Contexto:** Acabas de dar esta respuesta: "{previous_answer[:2000]}"
    **Tarea:** Sugiere 3 preguntas cortas (máx 7 palabras) para profundizar en los datos hallados o explorar áreas adyacentes.
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
        
        f"**Tarea:** Genera 5 ideas aplicando el método 'Pensamiento Lateral'. Cada idea debe nacer de un dato real del contexto (usa citas [x]).\n"
        f"Estructura: Idea, Provocación, Analogía e Insight de soporte.\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_concept_gen_prompt(product_idea, context_info):
    """Desarrollo de concepto estratégico con RTB (Reason to Believe) sólido."""
    return (
        f"**Rol:** Estratega de Producto Senior.\n"
        f"**Tarea:** Desarrolla un concepto GANADOR para la idea: \"{product_idea}\".\n"
        f"**Sustento de Mercado:** {context_info}\n\n"
        
        f"**Formato de Salida OBLIGATORIO (Markdown):**\n"
        f"1. **Consumer Truth:** (Tensión sustentada con citas [x])\n"
        f"2. **La Solución:** (Propuesta de valor enriquecida)\n"
        f"3. **Beneficios Clave:** (3-4 beneficios funcionales y emocionales)\n"
        f"4. **Rutas Creativas (A y B):** Incluye Insight, What y RTB con evidencia técnica.\n\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_idea_eval_prompt(idea_input, context_info):
    """Evaluación crítica basada en datos duros."""
    return (
        f"**Rol:** Director de Estrategia.\n"
        f"**Idea:** {idea_input}\n"
        f"**Evidencia:** {context_info}\n"
        f"Analiza viabilidad, deseabilidad y factibilidad usando exclusivamente la evidencia documental.\n"
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
        "Analiza la imagen considerando Impacto, Branding y Call to Action bajo la luz de los datos de mercado.",
        INSTRUCCIONES_DE_CITAS
    ]

def get_video_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context):
    """Evaluación de narrativa audiovisual."""
    return [
        "**Rol:** Director Audiovisual y de Estrategia.",
        f"Target: {target_audience} | Objetivos: {comm_objectives}",
        f"Contexto Estratégico: {relevant_text_context[:8000]}",
        "Evalúa el video (Impacto, Narrativa, Ritmo, Branding) contrastando con la información documentada.",
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
        f"**Tarea:** Realiza un análisis numérico detallado de: {user_query}\n"
        f"**Datos Extraídos:** {relevant_info}\n"
        f"Identifica medias, tendencias, y valores atípicos. Explica qué significan estas cifras para el negocio.\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_trend_analysis_prompt(topic, repo_context, pdf_context, public_sources_list):
    """Intelligence Brief de tendencias de mercado."""
    current_date = datetime.now().strftime("%d de %B de %Y")
    sources = "\n".join([f"- {s}" for s in public_sources_list]) if public_sources_list else "No especificadas"
    
    return f"""
    **Fecha:** {current_date} | **Misión:** Intelligence Brief sobre "{topic}".
    **Insumos:** {repo_context[:8000]} {pdf_context[:8000]}
    **Fuentes:** {sources}
    
    Clasifica en: Mega-Tendencias, Fads y Señales Débiles. Conecta los hallazgos para hallar oportunidades.
    """
