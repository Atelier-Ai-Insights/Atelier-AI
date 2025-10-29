import streamlit as st
import json
from services.supabase_db import get_monthly_usage, log_query_event
from services.gemini_api import call_gemini_api
from reporting.ppt_generator import crear_ppt_one_pager
from utils import get_relevant_info # Importante para obtener el contexto

# =====================================================
# MODO: GENERADOR DE ONE-PAGER PPT
# =====================================================

def one_pager_ppt_mode(db, selected_files):
    st.subheader("One-Pager Estratégico")
    ppt_limit = st.session_state.plan_features.get('ppt_downloads_per_month', 0)
    
    if ppt_limit == float('inf'):
        limit_text = "**Tu plan actual te permite generar One-Pagers ilimitados.**"
    elif ppt_limit > 0: # Si no es infinito y es mayor que 0
        limit_text = f"**Tu plan actual te permite generar {int(ppt_limit)} One-Pagers al mes.**"
    else: # Si es 0
        limit_text = "**Tu plan actual no incluye la generación de One-Pagers.**"
        
    st.markdown(f"""
        Sintetiza los hallazgos clave en una sola diapositiva de PowerPoint sobre un tema específico.
        {limit_text}
    """)

    # Usar session_state para mantener los datos del PPT generado
    if "generated_ppt_bytes" in st.session_state:
        st.success("¡Tu diapositiva One-Pager está lista!")
        st.download_button(
            label="Descargar One-Pager (.pptx)",
            data=st.session_state.generated_ppt_bytes,
            file_name=f"one_pager_estrategico.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            use_container_width=True
        )
        if st.button("Generar nuevo One-Pager", use_container_width=True, type="secondary"):
            del st.session_state.generated_ppt_bytes
            st.rerun()
        return # Detener la ejecución si el archivo ya está generado

    # --- Formulario de generación ---
    tema_central = st.text_area(
        "¿Cuál es el tema central o la pregunta clave para este One-Pager?", 
        height=100, 
        placeholder="Ej: Oportunidades para snacks saludables en adultos jóvenes"
    )

    if st.button("Generar One-Pager", use_container_width=True):
        current_ppt_usage = get_monthly_usage(st.session_state.user, "Generador de One-Pager PPT")
        
        if current_ppt_usage >= ppt_limit and ppt_limit != float('inf'):
            st.error(f"¡Límite de generación de PPT alcanzado! Tu plan permite {int(ppt_limit)} al mes.")
            return # Detener la ejecución
        
        if not tema_central.strip():
            st.warning("Por favor, describe el tema central.")
            return

        if not selected_files:
            st.warning("No has seleccionado ningún estudio. Por favor, selecciona estudios en el filtro del sidebar.")
            return

        with st.spinner("Obteniendo contexto de los estudios..."):
            relevant_info = get_relevant_info(db, tema_central, selected_files)
        
        # --- Prompt de Gemini para JSON ---
        prompt_json = f"""
        Actúa como un Director de Estrategia. Has analizado los siguientes hallazgos de investigación:
        
        --- CONTEXTO ---
        {relevant_info}
        --- FIN CONTEXTO ---

        Tu tarea es sintetizar esta información para crear un "One-Pager" estratégico en una sola diapositiva de PowerPoint sobre el tema: "{tema_central}".

        Genera ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta:

        {{
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
        """

        data_json = None
        with st.spinner("Generando contenido con IA..."):
            response = call_gemini_api(prompt_json)
            if not response:
                st.error("Error al contactar la API de Gemini.")
                return

            try:
                # Limpiar la respuesta de Gemini (a veces añade '```json' y '```')
                clean_response = response.strip().replace("```json", "").replace("```", "")
                data_json = json.loads(clean_response)
            except json.JSONDecodeError:
                st.error("Error: La IA no devolvió un JSON válido. Reintentando...")
                st.code(response) # Muestra la respuesta errónea para depuración
                return
        
        if data_json:
            with st.spinner("Ensamblando diapositiva .pptx..."):
                ppt_bytes = crear_ppt_one_pager(data_json)
            
            if ppt_bytes:
                st.session_state.generated_ppt_bytes = ppt_bytes
                log_query_event(tema_central, mode="Generador de One-Pager PPT")
                with st.spinner("Finalizando..."):
                    st.rerun() # Recargar para mostrar el botón de descarga
            else:
                st.error("No se pudo crear el archivo PowerPoint.")
