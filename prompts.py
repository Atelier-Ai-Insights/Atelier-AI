import streamlit as st

# --- BLOQUE DE INSTRUCCIONES DE CITAS ---
INSTRUCCIONES_DE_CITAS = """
**REGLAS DE CITAS (ESTRICTO):**
1. **Base:** Solo usa la 'Información documentada'. No alucines información externa.
2. **Formato:** Asigna un ID numérico único [x] a cada documento la primera vez que lo uses. Reutiliza el ID para futuras referencias al mismo documento.
3. **Sintaxis:** Frase del hallazgo [1]. Otra frase contrastada [2].
4. **Sección Fuentes:** Al final, añade:
   ---
   ## Fuentes
   * [1] Documento: (Nombre exacto del archivo)
5. **Vacío:** Si la respuesta no está en los documentos, di: "Información no disponible en los documentos."
"""

# --- Prompts Anteriores (Reporte, Chat, Ideación, Conceptos, Eval, Video, Transcripciones, Autocode, EtnoChat, Excel, OnePager) ---
# (MANTÉN EL RESTO DE TUS PROMPTS IGUAL QUE ANTES, SOLO AGREGA/REEMPLAZA LA SECCIÓN DE TENDENCIAS AL FINAL)
# ...
# ... (Aquí irían get_report_prompt1, get_grounded_chat_prompt, etc. No los repito para ahorrar espacio, 
# pero asegúrate de no borrarlos).

# ==============================================================================
# NUEVA SECCIÓN: ANÁLISIS DE TENDENCIAS (LENTES + VALIDACIÓN DE MERCADO)
# ==============================================================================

# Definimos qué "datos" debe simular la IA para cada fuente
SOURCE_LENSES = {
    "DANE (Datos Demográficos/Económicos)": "Prioriza indicadores duros: IPC (Inflación), Tasa de Desempleo, PIB trimestral, Pulso Social y gasto de los hogares.",
    "Banco de la República (Macroeconomía)": "Enfócate en tasas de interés de intervención, TRM (Dólar), balanza comercial y política monetaria.",
    "Fenalco (Comercio y Retail)": "Usa la 'Bitácora Económica': comportamiento en punto de venta, fechas comerciales (Día de la Madre, etc.) y clima de negocios.",
    "Camacol (Vivienda y Construcción)": "Analiza Coordenada Urbana: ventas de vivienda VIS/No VIS, iniciaciones y licenciamiento.",
    "Euromonitor (Tendencias Globales)": "Conecta con Megatendencias (ej. Bienestar, Sostenibilidad), tamaño de mercado y benchmarks internacionales.",
    "Google Trends (Intención Digital)": "Estima el interés de búsqueda online, estacionalidad de las consultas y palabras clave emergentes.",
    "McKinsey/Deloitte (Consultoría Estratégica)": "Aplica marcos de 'Futuro del Consumidor', transformación digital y predicciones a 2030.",
    "Superintendencia (SIC) (Regulación)": "Considera el marco legal, protección al consumidor, habeas data y libre competencia."
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

{INSTRUCCIONES_DE_CITAS}
"""

# ... (Asegúrate de que el resto de funciones como get_transcript_prompt sigan en el archivo)
