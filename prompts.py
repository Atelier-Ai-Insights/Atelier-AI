import streamlit as st

# --- BLOQUE DE INSTRUCCIONES DE CITAS ---
INSTRUCCIONES_DE_CITAS = """
**REGLAS DE CITAS (ESTRICTO):**
1. **Base:** Solo usa la 'Información documentada'. No alucines información externa sin sustentarla.
2. **Formato Interno:** Asigna un ID numérico único [x] a cada documento del repositorio/PDF la primera vez que lo uses.
3. **Sintaxis:** Frase del hallazgo [1]. Otra frase contrastada [2].
4. **Sección Fuentes:** Al final, DEBES generar una lista consolidada.
5. **Vacío:** Si la respuesta no está en los documentos, di: "Información no disponible en los documentos."
"""

# --- Prompts para "Generar un reporte de reportes" ---

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

# --- Prompt para "Chat de Consulta Directa" ---

def get_grounded_chat_prompt(conversation_history, relevant_info):
    """Chat RAG estricto."""
    return (
        f"**Rol:** Asistente de investigación.\n"
        f"**Tarea:** Responde la ÚLTIMA pregunta del historial usando SOLO la 'Información Documentada'.\n\n"
        f"**Info Documentada:**\n{relevant_info}\n\n"
        f"**Historial:**\n{conversation_history}\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
        "**Respuesta:**"
    )

# --- Prompt para "Conversaciones creativas" ---

def get_ideation_prompt(conv_history, relevant):
    """Ideación (Permite más flexibilidad en tono, estricto en datos)."""
    return (
        f"**Rol:** Estratega de Innovación Creativo.\n"
        f"**Objetivo:** Generar soluciones inspiradoras conectando los datos proporcionados.\n"
        f"**Contexto:**\n{relevant}\n\n"
        f"**Historial:**\n{conv_history}\n\n"
        f"**Instrucción:** Responde de forma sintética e inspiradora. Basa tus premisas en los datos.\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

# --- Prompt para "Generación de conceptos" ---

def get_concept_gen_prompt(product_idea, context_info):
    """Concepto estructurado (Markdown forzado)."""
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

# --- Prompt para "Evaluar una idea" ---

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

# --- Prompt para "Evaluación Visual" y "Video" ---

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

# --- Prompt para "Análisis de Notas y Transcripciones" ---

def get_transcript_prompt(combined_context, user_prompt):
    return (
        f"**Rol:** Investigador Cualitativo Senior.\n"
        f"**Contexto (Resumen Global y Fragmentos Específicos):**\n{combined_context}\n\n"
        f"**Pregunta del Usuario:** {user_prompt}\n\n"
        f"**Instrucciones CRÍTICAS de Análisis:**\n"
        f"1. **IGNORA LA LOGÍSTICA:** No menciones temas de 'encender cámaras', 'firmar consentimientos', 'presentaciones personales', 'normas de la sesión' o 'problemas de audio', a menos que el usuario pregunte explícitamente por ello.\n"
        f"2. **PROFUNDIDAD:** Céntrate en opiniones, emociones, percepciones, barreras y motivadores profundos de los participantes.\n"
        f"3. **SÍNTESIS INTELIGENTE:** Si la pregunta es amplia (ej. 'temas recurrentes'), apóyate en el 'Resumen Global'. Si es específica, usa los 'Fragmentos'.\n"
        f"4. **CITAS:** Siempre que sea posible, respalda tus afirmaciones indicando [Fuente: NombreArchivo].\n\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

def get_text_analysis_summary_prompt(full_context):
    """Resumen denso para contexto futuro."""
    return f"""
**Rol:** Investigador Cualitativo.
**Tarea:** Genera un Resumen Ejecutivo exhaustivo de las siguientes transcripciones. Será la ÚNICA fuente para análisis futuros.

**Entrada:**
{full_context}

**Salida (Markdown):**
## Resumen Ejecutivo
(4-5 frases síntesis macro)

## Hallazgos por Tema (Ignorando logística/presentaciones)
### 1. [Tema Relevante]
* [Hallazgo detallado. Fuente: Archivo]
* [Cita textual clave: "...". Fuente: Archivo]
(Repetir para todos los temas relevantes)
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

# --- Prompt para "EtnoChat" y Transcripción Multimedia ---

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

# --- Prompt para "Análisis de Datos (Excel)" ---

def get_survey_articulation_prompt(survey_context, repository_context, conversation_history):
    return (
        f"**Rol:** Investigador de Mercados (Cuanti/Cuali).\n"
        f"**Tarea:** Responde articulando datos duros (Excel) con hallazgos previos (Repositorio).\n\n"
        f"**Excel (El QUÉ):**\n{survey_context}\n\n"
        f"**Repositorio (El PORQUÉ):**\n{repository_context}\n\n"
        f"**Historial:**\n{conversation_history}\n\n"
        f"**Instrucción:** Conecta el dato numérico con la explicación cualitativa. Cita el repositorio [x].\n"
        f"{INSTRUCCIONES_DE_CITAS}"
    )

# --- Prompts para "Generador de One-Pager PPT" ---

PROMPTS_ONEPAGER = {
    "Definición de Oportunidades": """
        Genera SOLO un JSON crudo (sin markdown) con esta estructura:
        {{
          "template_type": "oportunidades",
          "titulo_diapositiva": "Título corto sobre {tema_central}",
          "insight_clave": "Frase potente de verdad oculta.",
          "hallazgos_principales": ["Hallazgo 1", "Hallazgo 2", "Hallazgo 3"],
          "oportunidades": ["Oportunidad 1", "Oportunidad 2", "Oportunidad 3"],
          "recomendacion_estrategica": "Acción final."
        }}
        """,
    "Análisis DOFA (SWOT)": """
        Genera SOLO un JSON crudo (sin markdown) con esta estructura:
        {{
          "template_type": "dofa",
          "titulo_diapositiva": "DOFA: {tema_central}",
          "fortalezas": ["F1", "F2", "F3"],
          "oportunidades": ["O1", "O2", "O3"],
          "debilidades": ["D1", "D2", "D3"],
          "amenazas": ["A1", "A2", "A3"]
        }}
        """,
    "Mapa de Empatía": """
        Genera SOLO un JSON crudo (sin markdown):
        {{
          "template_type": "empatia",
          "titulo_diapositiva": "Empatía: {tema_central}",
          "piensa_siente": ["..."], "ve": ["..."], "dice_hace": ["..."], 
          "oye": ["..."], "esfuerzos": ["..."], "resultados": ["..."]
        }}
        """,
    "Propuesta de Valor (Value Proposition)": """
         Genera SOLO un JSON crudo (sin markdown):
        {{
          "template_type": "propuesta_valor",
          "titulo_diapositiva": "Propuesta: {tema_central}",
          "producto_servicio": "Descripción.",
          "creadores_alegria": ["..."], "aliviadores_frustracion": ["..."],
          "trabajos_cliente": ["..."], "alegrias": ["..."], "frustraciones": ["..."]
        }}
        """,
    "Mapa del Viaje (Journey Map)": """
        Genera SOLO un JSON crudo (sin markdown):
        {{
          "template_type": "journey_map",
          "titulo_diapositiva": "Journey: {tema_central}",
          "etapa_1": {{"nombre_etapa": "Nombre", "acciones": ["..."], "emociones": ["..."], "puntos_dolor": ["..."], "oportunidades": ["..."]}},
          "etapa_2": {{"nombre_etapa": "Nombre", "acciones": ["..."], "emociones": ["..."], "puntos_dolor": ["..."], "oportunidades": ["..."]}},
          "etapa_3": {{"nombre_etapa": "Nombre", "acciones": ["..."], "emociones": ["..."], "puntos_dolor": ["..."], "oportunidades": ["..."]}}
        }}
        """,
    "Matriz de Posicionamiento (2x2)": """
        Genera SOLO un JSON crudo (sin markdown):
        {{
          "template_type": "matriz_2x2",
          "titulo_diapositiva": "Matriz: {tema_central}",
          "eje_x_positivo": "Label X+", "eje_x_negativo": "Label X-",
          "eje_y_positivo": "Label Y+", "eje_y_negativo": "Label Y-",
          "items_cuadrante_sup_izq": ["..."], "items_cuadrante_sup_der": ["..."],
          "items_cuadrante_inf_izq": ["..."], "items_cuadrante_inf_der": ["..."],
          "conclusion_clave": "Insight visual."
        }}
        """,
    "Perfil de Buyer Persona": """
        Genera SOLO un JSON crudo (sin markdown):
        {{
          "template_type": "buyer_persona",
          "titulo_diapositiva": "Persona: {tema_central}",
          "perfil_nombre": "Nombre/Arquetipo", "perfil_demografia": "Resumen demo",
          "necesidades_jtbd": ["..."], "puntos_dolor_frustraciones": ["..."],
          "deseos_motivaciones": ["..."], "citas_clave": ["..."]
        }}
        """
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
    # Optimizamos la lista para que ocupe menos tokens visualmente
    sample_text = str(responses_sample) 
    
    return f"""
**Rol:** Codificador de Encuestas.
**Tarea:** Define categorías (nodos) para analizar respuestas sobre '{main_topic}'.

**Muestra de respuestas:**
{sample_text}

**Salida:** SOLO un JSON válido (Array de objetos). Sin Markdown.
Estructura:
[
  {{ "categoria": "Nombre corto", "keywords": ["k1", "k2"] }},
  ...
]
**Reglas CRÍTICAS de optimización:**
1. Genera máximo **8-10 categorías** principales.
2. Para cada categoría, incluye SOLO las **15 palabras clave o frases cortas más representativas** y repetidas (No listes todas las variaciones únicas).
3. Las keywords deben ser literales (encontradas en el texto) para usarse en búsqueda exacta (Regex).
"""

# --- Prompts Análisis de Datos ---

def get_data_summary_prompt(data_snapshot_str):
    return f"""
**Rol:** Analista de Datos.
**Tarea:** Resumen ejecutivo basado en la estructura del dataset.

**Datos:**
{data_snapshot_str}

**Salida (Markdown):**
## Resumen Datos
(Breve descripción)

## Hallazgos Clave (3-5)
* **[Hallazgo]:** Interpretación de medias, frecuencias o faltantes notables.
"""

def get_correlation_prompt(correlation_matrix_str):
    return f"""
**Rol:** Analista de Datos.
**Tarea:** Interpreta esta matriz de correlación. Destaca las 3 relaciones más fuertes (pos/neg).

**Matriz:**
{correlation_matrix_str}

**Salida (Markdown):**
## Interpretación
1. Explicación breve de correlaciones fuertes encontradas y su sentido práctico.
"""

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
# SECCIÓN: ANÁLISIS DE TENDENCIAS (LENTES + VALIDACIÓN DE MERCADO)
# ==============================================================================

# Definimos qué "datos" debe simular la IA para cada fuente Y AGREGAMOS LA URL
SOURCE_LENSES = {
    "DANE (Datos Demográficos/Económicos)": "Prioriza indicadores duros: IPC (Inflación), Tasa de Desempleo, PIB trimestral, Pulso Social y gasto de los hogares. (Web: https://www.dane.gov.co)",
    "Banco de la República (Macroeconomía)": "Enfócate en tasas de interés de intervención, TRM (Dólar), balanza comercial y política monetaria. (Web: https://www.banrep.gov.co)",
    "Fenalco (Comercio y Retail)": "Usa la 'Bitácora Económica': comportamiento en punto de venta, fechas comerciales (Día de la Madre, etc.) y clima de negocios. (Web: https://www.fenalco.com.co)",
    "Camacol (Vivienda y Construcción)": "Analiza Coordenada Urbana: ventas de vivienda VIS/No VIS, iniciaciones y licenciamiento. (Web: https://camacol.co)",
    "Euromonitor (Tendencias Globales)": "Conecta con Megatendencias (ej. Bienestar, Sostenibilidad), tamaño de mercado y benchmarks internacionales. (Web: https://www.euromonitor.com)",
    "Google Trends (Intención Digital)": "Estima el interés de búsqueda online, estacionalidad de las consultas y palabras clave emergentes. (Web: https://trends.google.com)",
    "McKinsey/Deloitte (Consultoría Estratégica)": "Aplica marcos de 'Futuro del Consumidor', transformación digital y predicciones a 2030. (Web: https://www.mckinsey.com / https://www2.deloitte.com)",
    "Superintendencia (SIC) (Regulación)": "Considera el marco legal, protección al consumidor, habeas data y libre competencia. (Web: https://www.sic.gov.co)"
}

def get_trend_analysis_prompt(topic, repo_context, pdf_context, public_sources_list):
    
    # Construcción dinámica de la instrucción de fuentes públicas
    sources_instruction = ""
    if public_sources_list:
        lens_descriptions = []
        for source in public_sources_list:
            # Buscamos la instrucción específica para esa fuente
            lens = SOURCE_LENSES.get(source, "aporta contexto general de mercado")
            lens_descriptions.append(f"- **{source.split('(')[0].strip()}**: {lens}.")
        
        sources_text = "\n".join(lens_descriptions)
        
        sources_instruction = (
            f"3. **LENTES DE MERCADO (Fuentes Públicas):**\n"
            f"Actúa como un analista experto que tiene acceso al conocimiento general de estas entidades. "
            f"Para este análisis, OBLIGATORIAMENTE aplica estas perspectivas:\n"
            f"{sources_text}\n"
            f"**Nota:** Usa las tendencias macroeconómicas y sociales conocidas de estas entidades para validar o refutar los hallazgos internos."
        )

    return f"""
**Rol:** Director de Estrategia y Tendencias de Mercado.
**Misión:** Realizar una triangulación estratégica sobre: "{topic}".

**Tus 3 Insumos de Información:**
A. **ADN Interno (Repositorio):** {repo_context[:15000]}

B. **Evidencia Nueva (PDFs Cargados):** {pdf_context[:15000]}

C. **Contexto de Mercado (Fuentes Públicas Seleccionadas):**
{sources_instruction}

**Instrucción:** Debes cruzar estas tres fuentes. No las analices por separado. 

**Formato de Salida (Markdown Estricto):**

# Radar de Tendencias: {topic}

## 1. Insight Estratégico
(Una verdad reveladora y sintética que surge de cruzar lo interno con lo externo).

## 2. Validación de Mercado (Tabla de Triangulación)
*Este análisis contrasta la visión interna de la empresa (Repositorio/PDFs) con la realidad del mercado (Fuentes Públicas).*

| Tendencia Interna (Lo que dicen nuestros estudios) | Validación Externa (Datos DANE/Fenalco/Etc) | Veredicto (¿Oportunidad o Riesgo?) |
| :--- | :--- | :--- |
| (Hallazgo clave del repo [Cita]) | (Dato o tendencia macro que lo confirma o contradice) | (Conclusión breve) |
| (Hallazgo clave del repo [Cita]) | (Dato o tendencia macro que lo confirma o contradice) | (Conclusión breve) |
| (Hallazgo clave del repo [Cita]) | (Dato o tendencia macro que lo confirma o contradice) | (Conclusión breve) |

## 3. Hallazgos Principales (Deep Dive)
* **[Patrón Detectado 1]:** Explicación profunda. ¿Por qué ocurre? ¿Qué fuentes lo sustentan?
* **[Patrón Detectado 2]:** Explicación profunda.
* **[Perspectiva Externa]:** Análisis exclusivo desde las fuentes públicas seleccionadas ({', '.join(public_sources_list) if public_sources_list else 'Mercado General'}).

## 4. Territorios de Oportunidad
1. **[Oportunidad A]:** Descripción y potencial.
2. **[Oportunidad B]:** Descripción y potencial.
3. **[Oportunidad C]:** Descripción y potencial.

## 5. Recomendaciones Estratégicas
(Acciones concretas a corto y mediano plazo).

---
## Bibliografía y Fuentes Consultadas

### Fuentes Internas (Repositorio y PDFs)
* [1] Documento: (Listar los nombres de archivos del repositorio usados)
* [2] PDF Cargado: (Nombre del archivo PDF)

### Fuentes Externas (Referencias Públicas)
* Lista aquí las fuentes públicas seleccionadas para este análisis y sus enlaces de referencia:
(Ejemplo: **DANE**: https://www.dane.gov.co)
* ...
"""
