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
    return f"""
    **Rol:** Director de Estrategia.
    **Evidencia:** {context_info}
    **Idea a Evaluar:** "{idea_input}"
    
    Evalúa la viabilidad, deseabilidad y factibilidad basándote estrictamente en los datos.
    \n{INSTRUCCIONES_DE_CITAS}
    """

def get_trend_synthesis_prompt(topic, context):
    return f"Sintetiza tendencias para {topic} usando: {context}. Clasifica en Mega-tendencias y Fads."

def get_etnochat_prompt(context):
    return f"Actúa como un etnográfo digital. Analiza este contenido multimodal: {context}."

def get_media_transcription_prompt(media_data):
    return f"Describe y transcribe el contenido de este archivo multimedia: {media_data}."

# ==============================================================================
# PROMPTS RESTAURADOS (PERSONAS SINTÉTICAS)
# ==============================================================================

def get_persona_generation_prompt(context):
    return f"Genera 3 perfiles de consumidores (Personas) basados en: {context[:15000]}. Salida: JSON."

def get_persona_chat_instruction(persona_name, persona_data):
    return f"Actúa como el perfil sintetizado: {persona_name}. Datos: {persona_data}. Responde detalladamente."

# ==============================================================================
# ANÁLISIS NUMÉRICO (EXCEL)
# ==============================================================================

def get_excel_autocode_prompt(main_topic, sample_data):
    return f"Codificación para {main_topic}. Data: {sample_data}"

def get_correlation_prompt(correlation_matrix_str):
    return f"Analiza esta matriz de correlación: {correlation_matrix_str}"

def get_stat_test_prompt(test_type, p_value, var_num, var_cat, n_groups):
    return f"Interpreta: {test_type}, p={p_value}, variables {var_num}/{var_cat}."

# ==============================================================================
# EVALUACIÓN DE IDEAS [RESTAURADO]
# ==============================================================================

def get_idea_eval_prompt(idea_input, context_info):
    """Genera una evaluación crítica y exhaustiva de una idea de negocio."""
    return (
        f"**Rol:** Director de Estrategia Senior.\n"
        f"**Idea a Evaluar:** {idea_input}\n"
        f"**Evidencia Documentada:** {context_info}\n\n"
        f"Realiza un análisis profundo de viabilidad y factibilidad. No resumas. "
        f"Utiliza toda la evidencia para justificar tu juicio.\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

# ==============================================================================
# REPORTES ESPECIALES (ONE-PAGER)
# ==============================================================================

# 1. Definición para el Generador One Pager [RESTAURADO]
PROMPTS_ONEPAGER = {
    "Analítico": "Crea un resumen técnico y denso basado en datos.",
    "Creativo": "Desarrolla una narrativa inspiradora basada en los hallazgos.",
    "Ejecutivo": "Enfoque en KPIs y decisiones de negocio clave."
}

def get_onepager_prompt(topic, context):
    return f"Estructura JSON para One Pager sobre {topic} usando {context}."

def get_onepager_final_prompt(relevant_info, template_name, tema_central):
    return f"Completa el template {template_name} para {tema_central} con {relevant_info}. Solo JSON crudo."

def get_followup_suggestions_prompt(previous_answer):
    return f"Sugiere 3 preguntas de profundización para: {previous_answer[:1000]}"

def get_ideation_prompt(conv_history, relevant):
    return (
        f"**Rol:** Estratega de Innovación Disruptiva.\n"
        f"**Contexto:**\n{relevant}\n"
        f"**Tarea:** Genera 5 ideas aplicando 'Pensamiento Lateral' sustentadas en datos.\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )
