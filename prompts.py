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
# PROMPTS DE ANÁLISIS DE TEXTOS (TRANSCRIPCIONES)
# ==============================================================================

def get_transcript_prompt(transcript_text, additional_instructions=""):
    """Análisis profundo de transcripciones de entrevistas o focus groups."""
    return (
        f"**Rol:** Especialista en Análisis Cualitativo y Semiótica.\n"
        f"**Tarea:** Realiza un análisis exhaustivo de la siguiente transcripción:\n"
        f"--- INICIO TRANSCRIPCIÓN ---\n{transcript_text}\n--- FIN TRANSCRIPCIÓN ---\n\n"
        f"**Instrucciones específicas:** {additional_instructions}\n"
        f"Busca tensiones, verbatims poderosos, insights subyacentes y patrones de comportamiento.\n"
        f"**Regla:** No resumas. Desarrolla cada hallazgo con profundidad analítica.\n"
    )

def get_text_analysis_summary_prompt(analysis_results):
    """Genera una síntesis estratégica de múltiples análisis cualitativos."""
    return (
        f"**Rol:** Director de Estrategia.\n"
        f"**Insumos:** {analysis_results}\n"
        f"**Tarea:** Cruza los hallazgos de todos los textos analizados para identificar temas recurrentes y discrepancias críticas.\n"
        f"**Salida:** Informe ejecutivo de alta densidad con recomendaciones accionables."
    )

# ==============================================================================
# PROMPTS DE ANÁLISIS NUMÉRICO (RESTAURADOS)
# ==============================================================================

def get_excel_autocode_prompt(main_topic, sample_data):
    """Genera categorías para codificación automática de Excel."""
    return f"""
    Actúa como un experto en codificación cualitativa de mercado.
    **Tema Principal:** {main_topic}
    **Muestra de Respuestas:** {sample_data}
    
    **Tarea:** Crea un libro de códigos (codebook) con máximo 8 categorías mutuamente excluyentes.
    Para cada categoría define:
    1. Nombre corto y claro.
    2. Palabras clave o conceptos asociados (Regex patterns).
    
    Respuesta EXCLUSIVAMENTE en formato JSON:
    {{ "categorias": [ {{ "nombre": "...", "keywords": "palabra1|palabra2" }} ] }}
    """

def get_correlation_prompt(correlation_matrix_str):
    """Interpretación de matrices de correlación."""
    return f"""
    Analiza la siguiente matriz de correlación:
    {correlation_matrix_str}
    
    **Tarea:** Identifica las relaciones más fuertes y explica su implicación estratégica. 
    No te limites a los números; interpreta el comportamiento del consumidor.
    Sé exhaustivo en tu explicación y desarrolla cada punto.
    """

def get_stat_test_prompt(test_type, p_value, var_num, var_cat, n_groups):
    """Interpretación de significancia estadística."""
    return f"""
    Interpreta los resultados:
    - **Prueba:** {test_type}
    - **Variable:** {var_num} por {var_cat}
    - **P-Value:** {p_value:.4f}
    
    **Tarea:** Explica si existen diferencias significativas. Si p < 0.05, describe qué grupo destaca y por qué es un insight accionable. 
    Evita respuestas cortas; desarrolla la importancia de este hallazgo.
    """

# ==============================================================================
# PROMPTS CREATIVOS Y EVALUACIÓN
# ==============================================================================

def get_ideation_prompt(conv_history, relevant):
    return (
        f"**Rol:** Estratega de Innovación Disruptiva.\n"
        f"**Contexto:**\n{relevant}\n"
        f"**Tarea:** Genera 5 ideas aplicando 'Pensamiento Lateral' sustentadas en datos.\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_concept_gen_prompt(product_idea, context_info):
    return (
        f"**Rol:** Estratega de Producto Senior.\n"
        f"**Tarea:** Desarrolla un concepto GANADOR y detallado para: \"{product_idea}\".\n"
        f"**Mercado:** {context_info}\n\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_idea_eval_prompt(idea_input, context_info):
    return (
        f"**Rol:** Director de Estrategia.\n"
        f"**Idea:** {idea_input}\n"
        f"**Evidencia:** {context_info}\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

# ==============================================================================
# OTROS
# ==============================================================================

def get_data_analysis_prompt(user_query, relevant_info):
    return (
        f"**Tarea:** Análisis numérico detallado de: {user_query}\n"
        f"**Datos:** {relevant_info}\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_followup_suggestions_prompt(previous_answer):
    return f"""
    **Contexto:** Respuesta previa: "{previous_answer[:1500]}"
    **Tarea:** Sugiere 3 preguntas de profundización (JSON list).
    """
