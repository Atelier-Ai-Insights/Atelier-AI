# --- BLOQUE DE INSTRUCCIONES DE CITAS REUTILIZABLE (CORREGIDO) ---

INSTRUCCIONES_DE_CITAS = """
**Instrucciones de Respuesta OBLIGATORIAS:**
1. **Fidelidad Absoluta:** Basa tu respuesta *estrictamente* en la 'Información documentada'. No inventes nada.
2. **Respuesta Directa:** Responde a la última pregunta/tarea de forma clara y concisa.

3. **Agrupación de Citas (¡MUY IMPORTANTE!):**
   - **Asigna un número único a CADA documento** la primera vez que lo cites.
   - **REUTILIZA ESE MISMO NÚMERO** cada vez que vuelvas a citar información de ese *mismo* documento.
   - *Ejemplo de texto:* El producto A es popular [1]. El producto B es nuevo [2]. La popularidad de A se debe a su sabor [1].

4. **Crear Sección de Fuentes:** Al final de tu respuesta (después de un `---`), añade una sección llamada `## Fuentes`.

5. **Formato de Fuentes:** En la sección 'Fuentes', lista CADA número de cita **UNA SOLA VEZ**, con su `Documento:` correspondiente.
   * [1] Documento: Informe Gelatina - Ecuador
   * [2] Documento: Estudio Bocatto Salvaje 2023

6. **Sin Información:** Si la respuesta no se encuentra en la 'Información documentada', responde *únicamente* con: "La información solicitada no se encuentra disponible en los documentos seleccionados."
"""

# --- Prompts para "Generar un reporte de reportes" (modes/report_mode.py) ---

def get_report_prompt1(question, relevant_info):
    """Primer prompt para extraer hallazgos clave. (ACTUALIZADO)"""
    return (
        f"Pregunta del Cliente: ***{question}***\n\n"
        f"Contexto (Información documentada):\n```\n{relevant_info}\n```\n\n"
        "**Tarea:** Extrae los hallazgos más relevantes del contexto para responder la pregunta.\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n\n"
        "**Respuesta (Solo Hallazgos y Fuentes):**\n"
        "## Hallazgos Clave:\n"
        "* [Hallazgo 1... [1]]\n"
        "* [Hallazgo 2... [2]]\n"
        "---\n"
        "## Fuentes\n"
        "* [1] Documento: ...\n"
        "* [2] Documento: ...\n"
    )

def get_report_prompt2(question, result1, relevant_info):
    """Segundo prompt para redactar el informe final. (ACTUALIZADO)"""
    return (
        f"Pregunta: ***{question}***\n\n"
        "**Tarea:** Actúa como un Analista experto. Redacta un informe completo y estructurado usando el Resumen de Hallazgos y el Contexto Adicional. Menciona que los estudios son de Atelier.\n\n"
        "**Estructura del Informe (breve y preciso):**\n"
        "- Introducción: Contexto y pregunta.\n"
        "- Hallazgos Principales: Hechos relevantes respondiendo a la pregunta. DEBES citar las fuentes [1].\n"
        "- Insights: Aprendizajes profundos.\n"
        "- Conclusiones: Síntesis clara.\n"
        "- Recomendaciones (3-4): Accionables.\n\n"
        f"**Información documentada (Resumen y Contexto):**\n"
        f"Resumen de Hallazgos:\n{result1}\n\n"
        f"Contexto Adicional:\n{relevant_info}\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
        "\n**Redacta el informe completo:**"
    )

# --- Prompt para "Chat de Consulta Directa" (modes/chat_mode.py) ---

def get_grounded_chat_prompt(conversation_history, relevant_info):
    """Prompt de chat con citas. (ACTUALIZADO)"""
    return (
        f"**Tarea:** Eres un asistente de investigación experto. Responde la **última pregunta** del Usuario usando **únicamente** la 'Información documentada' y el 'Historial'.\n\n"
        f"**Historial (reciente):**\n{conversation_history}\n\n"
        f"**Información documentada (Tus únicas fuentes):**\n"
        "```\n"
        f"{relevant_info}\n"
        "```\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n\n"
        "**Respuesta:**"
    )

# --- Prompt para "Conversaciones creativas" (modes/ideation_mode.py) ---

def get_ideation_prompt(conv_history, relevant):
    """Prompt de ideación con citas. (ACTUALIZADO)"""
    return (
        f"**Tarea:** Experto Mkt/Innovación creativo. Conversación inspiradora con usuario sobre ideas/soluciones basadas **solo** en 'Información documentada' e 'Historial'.\n\n"
        f"**Historial:**\n{conv_history}\n\n"
        f"**Información documentada (Tus únicas fuentes):**\n{relevant}\n\n"
        "**Instrucciones Adicionales:**\n"
        "1. Rol: Experto creativo.\n"
        "2. Objetivo: Ayudar a explorar soluciones creativas conectando datos.\n"
        "3. Estilo: Claro, sintético, inspirador.\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n\n"
        "**Respuesta creativa:**"
    )

# --- Prompt para "Generación de conceptos" (modes/concept_mode.py) ---

def get_concept_gen_prompt(product_idea, context_info):
    """Prompt de generación de conceptos con citas. (ACTUALIZADO)"""
    return (
        f"**Tarea:** Estratega Mkt/Innovación. Desarrolla concepto estructurado a partir de 'Idea' y 'Contexto'.\n\n"
        f"**Idea:**\n\"{product_idea}\"\n\n"
        f"**Información documentada (Contexto/Hallazgos):**\n\"{context_info}\"\n\n"
        "**Instrucciones:**\n"
        "Genera Markdown con estructura exacta. Basa tus respuestas en el contexto y **CITA TUS FUENTES** [1].\n\n"
        "---\n\n"
        "### 1. Necesidad Consumidor\n* Identifica tensiones/deseos clave del contexto. Conecta con oportunidad. (Citar fuentes)\n\n"
        "### 2. Descripción Producto/Servicio\n* Basado en Idea y enriquecido por Contexto. (Citar fuentes)\n\n"
        "### 3. Beneficios Clave (3-4)\n* Responde a necesidad (Pto 1). Sustentado en Contexto. (Citar fuentes)\n\n"
        "### 4. Conceptos para Evaluar (2 Opc.)\n"
        "* **Opción A:**\n"
        "    * **Insight:** (Dolor + Deseo. Basado en contexto). (Citar fuentes)\n"
        "    * **What:** (Características/Beneficios).\n"
        "    * **RTB:** (¿Por qué creíble? Basado en contexto). (Citar fuentes)\n"
        "    * **Claim:** (Esencia memorable).\n\n"
        "* **Opción B:** (Alternativa)\n"
        "    * **Insight:** ...\n"
        "    * **What:** ...\n"
        "    * **RTB:** ...\n"
        "    * **Claim:** ...\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
    )

# --- Prompt para "Evaluar una idea" (modes/idea_eval_mode.py) ---

def get_idea_eval_prompt(idea_input, context_info):
    """Este prompt NO se modifica, ya que pide 'No citas explícitas'."""
    return (
        f"**Tarea:** Estratega Mkt/Innovación. Evalúa potencial de 'Idea' **solo** con 'Contexto' (hallazgos Atelier).\n\n"
        f"**Idea:**\n\"{idea_input}\"\n\n"
        f"**Contexto (Hallazgos):**\n\"{context_info}\"\n\n"
        "**Instrucciones:**\nEvalúa en Markdown estructurado. Basa **cada punto** en 'Contexto'. No conocimiento externo. No citas explícitas.\n\n"
        "---\n\n"
        "### 1. Valoración General Potencial\n* Resume: Alto, Moderado con Desafíos, Bajo según Hallazgos.\n\n"
        "### 2. Sustento Detallado (Basado en Contexto)\n"
        "* **Positivos:** Conecta idea con necesidades/tensiones clave del contexto. Hallazgos específicos que respaldan.\n"
        "* **Desafíos/Contradicciones:** Hallazgos que obstaculizan/contradicen.\n\n"
        "### 3. Sugerencias Evaluación Consumidor (Basado en Contexto)\n"
        "* 3-4 **hipótesis cruciales** (de hallazgos o vacíos). Para c/u:\n"
        "    * **Hipótesis:** (Ej: \"Consumidores valoran X sobre Y...\").\n"
        "    * **Pregunta Clave:** (Ej: \"¿Qué tan importante es X para Ud? ¿Por qué?\").\n"
        "    * **Aporte Pregunta:** (Ej: \"Validar si beneficio X resuena...\")."
    )

# --- Prompt para "Evaluación Visual" (modes/image_eval_mode.py) ---

def get_image_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context):
    """Prompt de evaluación de imagen con citas. (ACTUALIZADO)"""
    return [
        "Actúa como director creativo/estratega mkt experto. Analiza la imagen en contexto de target/objetivos, usando hallazgos como referencia.",
        f"\n\n**Target:**\n{target_audience}",
        f"\n\n**Objetivos:**\n{comm_objectives}",
        f"\n\n**Información documentada (Contexto/Hallazgos):**\n```\n{relevant_text_context[:10000]}\n```",
        "\n\n**Evaluación Detallada (Markdown):**",
        "\n### 1. Notoriedad/Impacto Visual",
        "* ¿Capta la atención? ¿Atractiva/disruptiva para target?",
        "* Elementos visuales clave y su aporte (apóyate en contexto si hay insights visuales y cítalos [1]).",
        "\n### 2. Mensaje Clave/Claridad",
        "* Mensajes principal/secundarios vs objetivos?",
        "* ¿Claro para target? ¿Ambigüedad?",
        "* ¿Mensaje vs insights del contexto? (Citar [1])",
        "\n### 3. Branding/Identidad",
        "* ¿Marca integrada efectivamente? ¿Reconocible?",
        "* ¿Refuerza personalidad/valores marca (según contexto)? (Citar [l1])",
        "\n### 4. Call to Action",
        "* ¿Sugiere acción o genera emoción/pensamiento (curiosidad, deseo, etc.)?",
        "* ¿Contexto sugiere que motivará al target? (Citar [1])",
        "\n\n**Conclusión General:**",
        "* Valoración efectividad, fortalezas, mejoras (conectando con insights si aplica [1]).",
        "\n\n---\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
    ]

# --- Prompt para "Evaluación de Video" (modes/video_eval_mode.py) ---

def get_video_eval_prompt_parts(target_audience, comm_objectives, relevant_text_context):
    """Prompt de evaluación de video con citas. (ACTUALIZADO)"""
    return [
        "Actúa como director creativo/estratega mkt experto audiovisual. Analiza el video (visual/audio) en contexto de target/objetivos, usando hallazgos como referencia.",
        f"\n\n**Target:**\n{target_audience}",
        f"\n\n**Objetivos:**\n{comm_objectives}",
        f"\n\n**Información documentada (Contexto/Hallazgos):**\n```\n{relevant_text_context[:8000]}\n```",
        "\n\n**Evaluación Detallada (Markdown):**",
        "\n### 1. Notoriedad/Impacto (Visual/Auditivo)",
        "* ¿Capta la atención? ¿Memorable? ¿Destaca?",
        "* Elementos clave (narrativa, ritmo, música, etc.) y su aporte (vs contexto y citar [1]).",
        "* ¿Insights contexto sobre preferencias audiovisuales? (Citar [1])",
        "\n### 2. Mensaje Clave/Claridad",
        "* Mensajes principal/secundarios vs objetivos?",
        "* ¿Claro/relevante para target? ¿Audio+Video OK?",
        "* ¿Mensaje vs insights contexto? (Citar [1])",
        "\n### 3. Branding/Identidad",
        "* ¿Marca integrada natural/efectiva? ¿Cuándo/cómo?",
        "* ¿Refuerza personalidad/valores marca? (Citar [1])",
        "\n### 4. Call to Action",
        "* ¿Sugiere acción o genera emoción/pensamiento?",
        "* ¿Contexto sugiere que motivará? (Citar [1])",
        "\n\n**Conclusión General:**",
        "* Valoración efectividad, fortalezas, mejoras (conectando con insights si aplica [1]).",
        "\n\n---\n"
        f"{INSTRUCCIONES_DE_CITAS}\n"
    ]

# --- Prompt para "Análisis de Notas y Transcripciones" (modes/transcript_mode.py) ---

def get_transcript_prompt(combined_context, user_prompt):
    """Prompt de transcripciones con citas. (ACTUALIZADO)"""
    return [
        "Actúa como un asistente experto en análisis cualitativo. Tu tarea es responder la pregunta del usuario basándote únicamente en el texto de las transcripciones proporcionadas.",
        f"\n\n**Información documentada (Transcripciones):**\n```\n{combined_context}\n```",
        f"\n\n**Pregunta del Usuario:**\n{user_prompt}",
        "\n\n**Instrucciones OBLIGATORIAS:**",
        "1. **Fidelidad Absoluta:** Basa tu respuesta *estrictamente* en la información contenida en las transcripciones.",
        "2. **Citas en Línea:** DEBES citar tus fuentes. Después de cada oración, añade un marcador de cita en texto plano, por ejemplo: [1], [2], etc.",
        "3. **Crear Sección de Fuentes:** Al final de tu respuesta (después de un `---`), añade una sección llamada `## Fuentes`.",
        "4. **Formato de Fuentes:** En la sección 'Fuentes', lista CADA cita en una **línea separada con su propia viñeta (`*`)**. La cita debe incluir el `Archivo:` del que tomaste la información (el nombre del archivo se provee en el contexto). Por ejemplo:\n"
        "   * [1] Archivo: Entrevista_Usuario_1.docx\n"
        "   * [2] Archivo: Focus_Group_A.docx\n"
        "5. **Sin Información:** Si la respuesta no se encuentra en el texto, indica claramente: 'La información solicitada no se encuentra en las transcripciones proporcionadas.'",
        "\n\n**Respuesta:**"
    ]

# --- Prompt para "Análisis de Datos (Excel)" ---

def get_survey_articulation_prompt(survey_context, repository_context, conversation_history):
    """
    Crea un prompt que articula datos de encuestas (cuanti) con
    datos del repositorio (cuali) para un chat.
    """
    return (
        f"**Tarea:** Eres un asistente experto en investigación de mercados. Tu tarea es responder la **última pregunta** del Usuario.\n\n"
        f"**¡IMPORTANTE!** Debes articular tu respuesta usando AMBAS fuentes de información:\n"
        f"1. **Contexto de Análisis de Datos (Cuantitativo):** Datos clave de un archivo Excel recién cargado. Úsalo como el 'QUÉ'.\n"
        f"2. **Información documentada (Cualitativo):** Hallazgos del repositorio histórico (estudios). Úsalo como el 'PORQUÉ'.\n\n"
        f"--- CONTEXTO DE ANÁLISIS DE DATOS (CUANTITATIVO) ---\n"
        f"```\n{survey_context}\n```\n\n"
        f"--- HISTORIAL DEL CHAT (RECIENTE) ---\n"
        f"{conversation_history}\n\n"
        f"--- INFORMACIÓN DOCUMENTADA (CUALITATIVO / REPOSITORIO) ---\n"
        f"```\n{repository_context}\n```\n\n"
        f"**Instrucciones de Articulación:**\n"
        f"- Responde al usuario conectando los datos de la encuesta (ej. 'El 70% prefiere X...') con los hallazgos del repositorio (ej. '...esto se alinea con el estudio Y que dice que X se percibe como... [1]').\n"
        f"- Si la pregunta solo se puede responder con una fuente, usa esa, pero prioriza la articulación.\n"
        f"- Cita tus fuentes del repositorio cualitativo como siempre.\n\n"
        f"{INSTRUCCIONES_DE_CITAS}\n\n"
        f"**Respuesta Articulada:**"
    )

# --- Prompts para "Generador de One-Pager PPT" (modes/onepager_mode.py) ---

# (Estos prompts generan JSON, no Markdown para el usuario, por lo que no deben tener citas)

# 1. El diccionario de plantillas
PROMPTS_ONEPAGER = {
    "Definición de Oportunidades": """
        Genera ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta:
        {{
          "template_type": "oportunidades",
          "titulo_diapositiva": "Un título principal corto y potente (máx. 6 palabras) sobre '{tema_central}'",
          "insight_clave": "El insight o 'verdad oculta' más importante que encontraste (1 frase concisa).",
          "hallazgos_principales": ["... (3 puntos) ..."],
          "oportunidades": ["... (3 puntos) ..."],
          "recomendacion_estrategica": "Una recomendación final clara y accionable (máx. 2 líneas)."
        }}
        """,
    "Análisis DOFA (SWOT)": """
        Genera ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta:
        {{
          "template_type": "dofa",
          "titulo_diapositiva": "Análisis DOFA: {tema_central}",
          "fortalezas": ["... (2-3 puntos) ..."],
          "oportunidades": ["... (2-3 puntos) ..."],
          "debilidades": ["... (2-3 puntos) ..."],
          "amenazas": ["... (2-3 puntos) ..."]
        }}
        """,
    "Mapa de Empatía": """
        Genera ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta:
        {{
          "template_type": "empatia",
          "titulo_diapositapositiva": "Mapa de Empatía: {tema_central}",
          "piensa_siente": ["... (2-3 puntos) ..."],
          "ve": ["... (2-3 puntos) ..."],
          "dice_hace": ["... (2-3 puntos) ..."],
          "oye": ["... (2-3 puntos) ..."],
          "esfuerzos": ["... (2 puntos) ..."],
          "resultados": ["... (2 puntos) ..."]
        }}
        """,
    "Propuesta de Valor (Value Proposition)": """
        Genera ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta:
        {{
          "template_type": "propuesta_valor",
          "titulo_diapositiva": "Propuesta de Valor: {tema_central}",
          "producto_servicio": "Descripción breve del producto/servicio central.",
          "creadores_alegria": ["... (2-3 puntos) ..."],
          "aliviadores_frustracion": ["... (2-3 puntos) ..."],
          "trabajos_cliente": ["... (2-3 puntos) ..."],
          "alegrias": ["... (2-3 puntos) ..."],
          "frustraciones": ["... (2-3 puntos) ..."]
        }}
        """,
    "Mapa del Viaje (Journey Map)": """
        Genera ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta:
        {{
          "template_type": "journey_map",
          "titulo_diapositiva": "Customer Journey Map: {tema_central}",
          "etapa_1": {{"nombre_etapa": "Ej: Descubrimiento", "acciones": ["..."], "emociones": ["..."], "puntos_dolor": ["..."], "oportunidades": ["..."]}},
          "etapa_2": {{"nombre_etapa": "Ej: Consideración", "acciones": ["..."], "emociones": ["..."], "puntos_dolor": ["..."], "oportunidades": ["..."]}},
          "etapa_3": {{"nombre_etapa": "Ej: Compra/Uso", "acciones": ["..."], "emociones": ["..."], "puntos_dolor": ["..."], "oportunidades": ["..."]}},
          "etapa_4": {{"nombre_etapa": "Ej: Post-Uso", "acciones": ["..."], "emociones": ["..."], "puntos_dolor": ["..."], "oportunidades": ["..."]}}
        }}
        """,
    "Matriz de Posicionamiento (2x2)": """
        Genera ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta:
        {{
          "template_type": "matriz_2x2",
          "titulo_diapositiva": "Matriz de Posicionamiento: {tema_central}",
          "eje_x_positivo": "Ej: Moderno",
          "eje_x_negativo": "Ej: Tradicional",
          "eje_y_positivo": "Ej: Calidad Percibida Alta",
          "eje_y_negativo": "Ej: Calidad Percibida Baja",
          "items_cuadrante_sup_izq": ["..."],
          "items_cuadrante_sup_der": ["..."],
          "items_cuadrante_inf_izq": ["..."],
          "items_cuadrante_inf_der": ["..."],
          "conclusion_clave": "El principal insight visual de la matriz."
        }}
        """,
    "Perfil de Buyer Persona": """
        Genera ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta:
        {{
          "template_type": "buyer_persona",
          "titulo_diapositiva": "Perfil de Buyer Persona: {tema_central}",
          "perfil_nombre": "Un nombre ficticio y arquetipo (ej. 'Ana, la Profesional Ocupada')",
          "perfil_demografia": "Un breve resumen demográfico/psicográfico (ej. 'Mujer, 30-40, urbana, valora la conveniencia...')",
          "necesidades_jtbd": ["... (2-3 'Jobs to be Done' o necesidades clave del contexto) ..."],
          "puntos_dolor_frustraciones": ["... (2-3 frustraciones o 'pain points' principales del contexto) ..."],
          "deseos_motivaciones": ["... (2-3 deseos, ganancias o 'drivers' de decisión del contexto) ..."],
          "citas_clave": ["... (1-2 citas literales IMPACTANTES del contexto que resumen su sentir) ..."]
        }}
        """,
}

# 2. El formateador del prompt final
def get_onepager_final_prompt(relevant_info, selected_template_name, tema_central):
    """Devuelve el prompt final formateado para el modo One-Pager."""
    
    prompt_template = PROMPTS_ONEPAGER.get(selected_template_name, "{}") 
    
    return f"""
    Actúa como un Analista Estratégico experto. Has analizado los siguientes hallazgos de investigación sobre '{tema_central}':

    --- CONTEXTO ---
    {relevant_info}
    --- FIN CONTEXTO ---

    Tu tarea es sintetizar esta información para completar la plantilla '{selected_template_name}'.
    {prompt_template.format(tema_central=tema_central)}
    """

def get_autocode_prompt(context, main_topic):
    """
    Crea un prompt para que la IA lea múltiples transcripciones e identifique
    temas clave (códigos) con citas de respaldo.
    """
    return f"""
**Tarea:** Eres un investigador cualitativo experto. Tu trabajo es analizar las transcripciones de entrevistas/focus groups proporcionadas sobre el tema '{main_topic}'.
Debes identificar los **temas emergentes (códigos)** más importantes y respaldar cada tema con **citas textuales** de las transcripciones.

--- TRANSCRIPCIONES (INFORMACIÓN DOCUMENTADA) ---
```{context}```

**Formato de Salida OBLIGATORIO (Markdown):**
Debes seguir esta estructura de Markdown exactamente:

## Resumen de Temas Clave
Un párrafo corto (2-3 frases) que resuma los principales hallazgos.

## Temas Emergentes y Citas

### 1. [Nombre del Tema 1]
> *"[Cita textual 1 que ilustre este tema]"* - (Fuente: [Nombre del Archivo de la cita])

> *"[Cita textual 2 que ilustre este tema]"* - (Fuente: [Nombre del Archivo de la cita])

### 2. [Nombre del Tema 2]
> *"[Cita textual 1 que ilustre este tema]"* - (Fuente: [Nombre del Archivo de la cita])

### 3. [Nombre del Tema 3]
> *"[Cita textual 1 que ilustre este tema]"* - (Fuente: [Nombre del Archivo de la cita])

(...continuar con más temas si son relevantes...)

**Instrucciones Adicionales:**
- **Identifica Temas:** Los temas deben ser *insights* (ej. "Preferencia por la practicidad") no solo palabras (ej. "Empaque").
- **Citas Textuales:** Las citas DEBEN ser copiadas palabra por palabra de las transcripciones.
- **Fuente de la Cita:** DEBES indicar de qué archivo (ej. `(Fuente: Entrevista_Usuario_1.docx)`) proviene cada cita.
"""

def get_excel_autocode_prompt(main_topic, responses_sample):
    """
    Crea un prompt para que la IA lea una MUESTRA de respuestas de una
    pregunta abierta de Excel y genere categorías (nodos) con 
    palabras clave de búsqueda.
    """
    
    # Convertimos la lista de respuestas de Python a un string formateado
    sample_text = "\n".join([f"- {r}" for r in responses_sample])
    
    return f"""
**Tarea:** Eres un investigador cualitativo experto en codificación. Tu trabajo es analizar la siguiente MUESTRA de respuestas de una encuesta sobre el tema '{main_topic}'.

Tu objetivo es definir un **esquema de codificación (nodos)** para categorizar estas respuestas.

--- MUESTRA DE RESPUESTAS ---
```{sample_text}```

**Instrucciones de Salida (JSON OBLIGATORIO):**
Analiza la muestra y genera ÚNICAMENTE un objeto JSON válido.
El JSON debe ser una lista de objetos, donde cada objeto representa una categoría (nodo) que encuentres.

**Formato JSON Exacto:**
`[
  {{
    "categoria": "Nombre de la Categoría 1",
    "keywords": ["palabra clave 1", "frase clave 1", "sinónimo 1"]
  }},
  {{
    "categoria": "Nombre de la Categoría 2",
    "keywords": ["palabra 2", "frase 2"]
  }},
  {{
    "categoria": "Otro Tema Emergente",
    "keywords": ["palabra 3", "palabra 4", "frase clave 3"]
  }}
]`

**Reglas Importantes:**
1.  **Categorías Claras:** Las "categorias" deben ser nombres cortos y descriptivos (ej. "Precio Alto", "Sabor Agradable", "Problemas con Empaque").
2.  **Keywords de Búsqueda:** Los "keywords" deben ser las palabras o frases literales que la gente usa en la muestra y que definen esa categoría. Incluye variaciones (ej. "caro", "costoso", "precio alto").
3.  **No Inventes:** Basa tus categorías y keywords *estrictamente* en la muestra de respuestas.
4.  **JSON Válido:** Tu salida debe ser *solamente* el JSON, sin texto introductorio.
"""

# --- ¡INICIO DE LOS 3 NUEVOS PROMPTS! ---

def get_data_summary_prompt(data_snapshot_str):
    """
    Crea un prompt para que la IA genere un resumen ejecutivo de un DataFrame.
    """
    return f"""
**Tarea:** Eres un analista de investigación de mercados senior. Tu trabajo es analizar un resumen estructural de un archivo de datos (encuesta) y generar un resumen ejecutivo para tu cliente.

--- RESUMEN ESTRUCTURAL DE DATOS ---
```{data_snapshot_str}```

**Formato de Salida OBLIGATORIO (Markdown):**
Basándote *únicamente* en el resumen estructural, identifica los 3-5 hallazgos más evidentes o las hipótesis más interesantes que valdría la pena explorar.

## Resumen Ejecutivo de Datos
Un párrafo corto (2-3 frases) que describa la naturaleza de los datos.

## Hallazgos Clave e Hipótesis
* **[Hallazgo 1]:** [Explica el hallazgo o la hipótesis. Por ejemplo: "La 'Satisfacción' (media: 4.2) parece alta, pero la 'Intención de Recompra' (media: 3.1) es baja. Esto sugiere un problema de lealtad..."]
* **[Hallazgo 2]:** [Explica el hallazgo o la hipótesis. Por ejemplo: "La mayoría de los encuestados son del 'Segmento A' (60%). Sería crucial cruzar todas las métricas clave contra el 'Segmento' para ver si el 'Segmento B' opina diferente..."]
* **[Hallazgo 3]:** [...]
* **[Hallazgo 4]:** [...]
"""

def get_correlation_prompt(correlation_matrix_str):
    """
    Crea un prompt para que la IA interprete una matriz de correlación.
    """
    return f"""
**Tarea:** Eres un analista de datos experto. Interpreta la siguiente matriz de correlación en lenguaje sencillo.

--- MATRIZ DE CORRELACIÓN ---
```{correlation_matrix_str}```

**Instrucciones:**
1.  Define brevemente qué es una correlación (positiva vs. negativa).
2.  Identifica las 2 o 3 relaciones **más fuertes** (positivas o negativas) de la matriz (ignora las correlaciones de 1.00 de una variable consigo misma).
3.  Explica qué significa cada una de esas relaciones en la práctica.
4.  Si no hay correlaciones fuertes (todas < 0.3 y > -0.3), indícalo.

**Respuesta (en Markdown):**
## Interpretación de Correlaciones
...
"""

def get_stat_test_prompt(test_type, p_value, num_col, cat_col, num_groups):
    """
    Crea un prompt para que la IA interprete un resultado de T-Test o ANOVA.
    """
    
    prompt = f"""
**Tarea:** Eres un estadístico experto. Interpreta el siguiente resultado de una prueba estadística para un cliente, en lenguaje muy sencillo.

**Contexto de la Prueba:**
* **Prueba Realizada:** {test_type}
* **Objetivo:** Comparar la media de la métrica '{num_col}' entre los {num_groups} grupos de la variable '{cat_col}'.
* **Resultado (P-Value):** {p_value}

**Instrucciones:**
1.  Define el "P-Value" de forma simple (umbral 0.05).
2.  Indica si el resultado es "Estadísticamente Significativo" (p < 0.05) o "No Significativo" (p >= 0.05).
3.  Explica qué significa ese resultado en la práctica para '{num_col}' y '{cat_col}'.

**Respuesta (en Markdown):**
"""
    
    if p_value < 0.05:
        prompt += f"""
## ✅ Resultado Significativo
* **Explicación:** El P-Value de {p_value:.4f} es *menor* que 0.05.
* **Conclusión:** Esto significa que las diferencias observadas en la media de '{num_col}' entre los diferentes grupos de '{cat_col}' son **reales y estadísticamente significativas**. No se deben al azar.
* **Acción Recomendada:** [Indica una acción, ej: "Vale la pena analizar qué grupo tuvo la media más alta o más baja."]
"""
    else:
        prompt += f"""
## ℹ️ Resultado No Significativo
* **Explicación:** El P-Value de {p_value:.4f} es *mayor* que 0.05.
* **Conclusión:** Esto significa que cualquier diferencia que se observe en la media de '{num_col}' entre los grupos de '{cat_col}' es **probablemente producto del azar**.
* **Acción Recomendada:** [Indica una acción, ej: "No se puede concluir que haya una diferencia real entre los grupos para esta métrica."]
"""
    return prompt
# --- ¡FIN DE LOS 3 NUEVOS PROMPTS! ---