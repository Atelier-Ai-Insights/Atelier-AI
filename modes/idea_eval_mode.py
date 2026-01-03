import streamlit as st
# Importamos la función de tooltips y componentes visuales
from utils import get_relevant_info, render_process_status, process_text_with_tooltips
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from prompts import get_idea_eval_prompt
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
import constants as c

def idea_evaluator_mode(db, selected_files):
    st.subheader("⚖️ Evaluador de Ideas (Shark Tank AI)")
    st.caption("Somete tu idea o hipótesis al juicio crítico de los datos de mercado.")

    # 1. INPUT DEL USUARIO
    idea_input = st.text_area(
        "Describe la idea, producto o estrategia que deseas evaluar:", 
        height=150,
        placeholder="Ej: Lanzar una bebida energizante natural enfocada en gamers universitarios..."
    )

    # 2. BOTÓN DE ACCIÓN
    if st.button("Evaluar Viabilidad", type="primary"):
        if not selected_files:
            st.warning("⚠️ Por favor selecciona al menos un documento en el menú lateral.")
            return
        
        if not idea_input:
            st.warning("⚠️ Debes escribir una idea para evaluar.")
            return

        # Limpiar estado anterior para nueva evaluación
        if "eval_result" in st.session_state.mode_state:
            del st.session_state.mode_state["eval_result"]

        # 3. PROCESAMIENTO
        with render_process_status("Analizando viabilidad contra el mercado...", expanded=True) as status:
            
            # A. Búsqueda de Evidencia
            status.write("🔍 Cruzando idea con hallazgos del repositorio...")
            relevant_info = get_relevant_info(db, idea_input, selected_files)
            
            if not relevant_info:
                status.update(label="No se encontró suficiente evidencia relacionada.", state="error")
                return

            # B. Evaluación con IA
            status.write("🧠 Consultando al Director de Estrategia...")
            prompt = get_idea_eval_prompt(idea_input, relevant_info)
            response = call_gemini_api(prompt)
            
            if response:
                st.session_state.mode_state["eval_result"] = response
                status.update(label="¡Evaluación Completada!", state="complete", expanded=False)
                
                # C. Logging
                try:
                    log_query_event(f"Evaluación: {idea_input[:50]}...", mode=c.MODE_IDEA_EVAL)
                except Exception as e:
                    print(f"Error logging: {e}")
            else:
                status.update(label="Error al generar respuesta.", state="error")

    # 4. VISUALIZACIÓN DE RESULTADOS
    if "eval_result" in st.session_state.mode_state:
        result_text = st.session_state.mode_state["eval_result"]
        
        st.divider()
        st.markdown("### 📊 Veredicto Estratégico")
        
        # --- AQUÍ APLICAMOS LA MAGIA DE LOS TOOLTIPS ---
        # Convertimos el texto con citas [1] en HTML interactivo
        enriched_html = process_text_with_tooltips(result_text)
        st.markdown(enriched_html, unsafe_allow_html=True)
        
        # 5. EXPORTACIÓN A PDF
        st.write("")
        st.write("")
        pdf_bytes = generate_pdf_html(result_text, title="Evaluación de Viabilidad", banner_path=banner_file)
        
        if pdf_bytes:
            col1, col2 = st.columns([1, 4])
            with col1:
                st.download_button(
                    label="📥 Descargar PDF",
                    data=pdf_bytes,
                    file_name="Evaluacion_Idea.pdf",
                    mime="application/pdf",
                    type="secondary"
                )
