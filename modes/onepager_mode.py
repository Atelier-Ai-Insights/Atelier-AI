import streamlit as st
import json
from services.supabase_db import get_monthly_usage, log_query_event
import google.generativeai as genai
from config import safety_settings
from services.gemini_api import configure_api_dynamically
from reporting.ppt_generator import crear_ppt_desde_json
from utils import get_relevant_info, extract_text_from_pdfs

# =====================================================
# MODO: GENERADOR DE ONE-PAGER PPT (MEJORADO)
# =====================================================

# --- Diccionario de Plantillas y sus Prompts ---
PROMPTS_ONEPAGER = {
    "Definición de Oportunidades": """
        Genera ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta:
        {{
          "template_type": "oportunidades",
          "titulo_diapositiva": "Un título principal corto y potente (máx. 6 palabras) sobre '{tema_central}'",
          "insight_clave": "El insight o 'verdad oculta' más importante que encontraste (1 frase concisa).",
          "hallazgos_principales": [
            "Hallazgo #1: Un punto clave sintetizado.",
            "Hallazgo #2: Otro punto clave sintetizado.",
            "Hallazgo #3: Un tercer punto clave sintetizado."
          ],
          "oportunidades": [
            "Oportunidad #1: Una acción o área de innovación basada en los hallazgos.",
            "Oportunidad #2: Otra acción o área de innovación.",
            "Oportunidad #3: Otra acción o área de innovación."
          ],
          "recomendacion_estrategica": "Una recomendación final clara y accionable (máx. 2 líneas)."
        }}
        """,
    "Análisis DOFA (SWOT)": """
        Genera ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta:
        {{
          "template_type": "dofa",
          "titulo_diapositiva": "Análisis DOFA: {tema_central}",
          "fortalezas": [
            "Fortaleza #1: Aspecto interno positivo clave extraído del contexto.",
            "Fortaleza #2: Otro aspecto interno positivo."
          ],
          "oportunidades": [
            "Oportunidad #1: Factor externo positivo clave extraído del contexto.",
            "Oportunidad #2: Otro factor externo positivo."
          ],
          "debilidades": [
            "Debilidad #1: Aspecto interno negativo clave extraído del contexto.",
            "Debilidad #2: Otro aspecto interno negativo."
          ],
          "amenazas": [
            "Amenaza #1: Factor externo negativo clave extraído del contexto.",
            "Amenaza #2: Otro factor externo negativo."
          ]
        }}
        """,
    "Mapa de Empatía": """
        Genera ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta:
        {{
          "template_type": "empatia",
          "titulo_diapositiva": "Mapa de Empatía: {tema_central}",
          "piensa_siente": [
            "Pensamiento/Sentimiento #1: Creencia, preocupación o aspiración clave.",
            "Pensamiento/Sentimiento #2: Otra emoción o idea relevante."
          ],
          "ve": [
            "Observación #1: Algo que el usuario ve en su entorno.",
            "Observación #2: Otra influencia visual."
          ],
          "dice_hace": [
            "Acción/Dicho #1: Comportamiento o frase típica.",
            "Acción/Dicho #2: Otra actitud observable."
          ],
          "oye": [
            "Influencia Auditiva #1: Algo que escucha de amigos, medios, etc.",
            "Influencia Auditiva #2: Otra fuente de información."
          ],
          "esfuerzos": [
            "Dolor/Esfuerzo #1: Frustración, obstáculo o miedo.",
            "Dolor/Esfuerzo #2: Otro desafío."
          ],
          "resultados": [
            "Ganancia/Resultado #1: Deseo, necesidad o medida de éxito.",
            "Ganancia/Resultado #2: Otra aspiración."
           ]
        }}
        """,
    "Propuesta de Valor (Value Proposition)": """
        Genera ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta:
        {{
          "template_type": "propuesta_valor",
          "titulo_diapositiva": "Propuesta de Valor: {tema_central}",
          "producto_servicio": "Descripción breve del producto/servicio central.",
          "creadores_alegria": [
             "Creador de Alegría #1: Cómo el producto/servicio produce ganancias.",
             "Creador de Alegría #2: Otra forma en que ayuda a obtener resultados."
          ],
          "aliviadores_frustracion": [
             "Aliviador #1: Cómo el producto/servicio alivia dolores.",
             "Aliviador #2: Otra forma en que soluciona problemas."
          ],
          "trabajos_cliente": [
              "Trabajo #1: Tarea funcional, social o emocional que el cliente intenta hacer.",
              "Trabajo #2: Otra tarea o problema a resolver."
          ],
          "alegrias": [
              "Alegría #1: Resultado o beneficio deseado por el cliente.",
              "Alegría #2: Otra aspiración."
          ],
          "frustraciones": [
              "Frustración #1: Obstáculo, riesgo o emoción negativa del cliente.",
              "Frustración #2: Otro dolor."
          ]
        }}
        """
}


def one_pager_ppt_mode(db_filtered, selected_files):
    st.subheader("Generador de Diapositivas Estratégicas")
    ppt_limit = st.session_state.plan_features.get('ppt_downloads_per_month', 0)

    if ppt_limit == float('inf'):
        limit_text = "**Tu plan actual te permite generar One-Pagers ilimitados.**"
    elif ppt_limit > 0:
        limit_text = f"**Tu plan actual te permite generar {int(ppt_limit)} One-Pagers al mes.**"
    else:
        limit_text = "**Tu plan actual no incluye la generación de One-Pagers.**"

    st.markdown(f"""
        Sintetiza los hallazgos clave en una diapositiva de PowerPoint usando la plantilla seleccionada.
        {limit_text}
    """)

    if "generated_ppt_bytes" in st.session_state:
        st.success(f"¡Tu diapositiva '{st.session_state.get('generated_ppt_template_name', 'Estratégica')}' está lista!")
        st.download_button(
            label=f"Descargar Diapositiva (.pptx)",
            data=st.session_state.generated_ppt_bytes,
            file_name=f"diapositiva_{st.session_state.get('generated_ppt_template_name', 'estrategica').lower().replace(' ','_')}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            use_container_width=True
        )
        if st.button("Generar nueva Diapositiva", use_container_width=True, type="secondary"):
            del st.session_state.generated_ppt_bytes
            st.session_state.pop('generated_ppt_template_name', None)
            st.rerun()
        return

    st.divider()
    st.markdown("#### 1. Selecciona la Plantilla")
    template_options = list(PROMPTS_ONEPAGER.keys())
    selected_template_name = st.selectbox("Elige el tipo de diapositiva:", template_options)

    st.markdown("#### 2. Selecciona la Fuente de Datos")
    col1, col2 = st.columns(2)
    with col1: use_repo = st.toggle("Usar Repositorio de Estudios", value=True)
    with col2: use_uploads = st.toggle("Usar Archivos PDF Cargados", value=False)

    uploaded_files = None
    if use_uploads:
        uploaded_files = st.file_uploader("Carga tus archivos PDF aquí:", type=["pdf"], accept_multiple_files=True, key="onepager_pdf_uploader")
        if uploaded_files: st.caption(f"Cargados {len(uploaded_files)} archivo(s).")

    st.markdown(f"#### 3. Define el Tema Central para '{selected_template_name}'")
    tema_central = st.text_area("¿Cuál es el enfoque principal?", height=100, placeholder=f"Ej: {selected_template_name} para snacks saludables...")
    st.divider()

    if st.button(f"Generar Diapositiva '{selected_template_name}'", use_container_width=True, type="primary"):
        current_ppt_usage = get_monthly_usage(st.session_state.user, "Generador de One-Pager PPT")
        if current_ppt_usage >= ppt_limit and ppt_limit != float('inf'): st.error(f"¡Límite alcanzado!"); return
        if not tema_central.strip(): st.warning("Por favor, describe el tema central."); return
        if not use_repo and not use_uploads: st.error("Debes seleccionar al menos una fuente de datos."); return
        if use_uploads and not uploaded_files: st.error("Seleccionaste 'Usar Archivos Cargados', pero no has subido PDFs."); return

        relevant_info = ""
        with st.spinner("Procesando fuentes de datos..."):
            if use_repo:
                repo_text = get_relevant_info(db_filtered, tema_central, selected_files)
                if repo_text: relevant_info += f"--- CONTEXTO REPOSITORIO ---\n{repo_text}\n\n"
            if use_uploads and uploaded_files:
                try:
                    pdf_text = extract_text_from_pdfs(uploaded_files)
                    if pdf_text: relevant_info += f"--- CONTEXTO PDFS CARGADOS ---\n{pdf_text}\n\n"
                except Exception as e:
                    st.error(f"Error al procesar PDFs: {e}"); pdf_text = None
        if not relevant_info.strip(): st.error("No se pudo extraer ningún contexto."); return

        prompt_template = PROMPTS_ONEPAGER.get(selected_template_name)
        if not prompt_template:
            st.error("Error interno: Plantilla de prompt no encontrada."); return

        final_prompt_json = f"""
        Actúa como un Analista Estratégico experto. Has analizado los siguientes hallazgos de investigación sobre '{tema_central}':

        --- CONTEXTO ---
        {relevant_info}
        --- FIN CONTEXTO ---

        Tu tarea es sintetizar esta información para completar la plantilla '{selected_template_name}'.
        {prompt_template.format(tema_central=tema_central)}
        """

        data_json = None
        with st.spinner(f"Generando contenido para '{selected_template_name}'..."):
            response_text = None
            try:
                configure_api_dynamically()
                json_generation_config = {"temperature": 0.5, "top_p": 0.8, "top_k": 32, "max_output_tokens": 8192, "response_mime_type": "application/json"}
                json_model = genai.GenerativeModel(model_name="gemini-2.5-flash", generation_config=json_generation_config, safety_settings=safety_settings)
                response = json_model.generate_content(final_prompt_json)
                response_text = response.text
                data_json = json.loads(response_text)
            except json.JSONDecodeError: st.error("Error: La IA no devolvió un JSON válido."); st.code(response_text); return
            except Exception as e: st.error(f"Error API Gemini: {e}"); st.code(str(response_text)); return

        if data_json:
            with st.spinner("Ensamblando diapositiva .pptx..."):
                ppt_bytes = crear_ppt_desde_json(data_json)
            if ppt_bytes:
                st.session_state.generated_ppt_bytes = ppt_bytes
                st.session_state.generated_ppt_template_name = selected_template_name
                log_query_event(f"{selected_template_name}: {tema_central}", mode="Generador de One-Pager PPT")
                st.rerun()
            else:
                pass # El error ya se muestra desde crear_ppt_desde_json
            
            