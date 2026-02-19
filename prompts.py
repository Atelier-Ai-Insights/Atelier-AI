import streamlit as st
from datetime import datetime
import json

# ==============================================================================
# INSTRUCCIONES GLOBALES (BLINDAJE DE EXHAUSTIVIDAD Y TRAZABILIDAD)
# ==============================================================================

# Este bloque es el corazón del sistema RAG. Prohíbe la brevedad y asegura 
# que la metadata técnica se genere correctamente para el frontend.
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

# ... (Resto de funciones: Evaluación, One-Pager, Análisis Numérico)
