import streamlit as st
import time
from services.gemini_api import call_gemini_api, call_gemini_stream
from utils import get_relevant_info, render_process_status, process_text_with_tooltips
from prompts import get_report_prompt1, get_report_prompt2
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from services.supabase_db import log_query_event
from services.memory_service import save_project_insight
import constants as c

def report_mode(db, selected_files):
    st.subheader("📝 Generador de Informes de Investigación")
    
    # 1. INPUT
    user_question = st.text_input("¿Qué objetivo de investigación deseas abordar?", placeholder="Ej: Analizar la percepción de precios en la categoría...")
    
    if not selected_files:
        st.warning("Selecciona documentos en el menú lateral.")
        return

    # 2. BOTÓN DE ACCIÓN
    if st.button("Generar Informe", type="primary", use_container_width=True):
        if not user_question: return
        
        # Resetear estado
        for k in ["report_step1", "report_final"]: st.session_state.mode_state.pop(k, None)
        
        with render_process_status("Iniciando investigación...", expanded=True) as status:
            
            # --- FASE 1 ---
            status.write("🔍 Fase 1: Escaneando documentos y extrayendo evidencia...")
            relevant_info = get_relevant_info(db, user_question, selected_files)
            
            if not relevant_info:
                status.update(label="No se encontró información relevante.", state="error")
                return

            prompt1 = get_report_prompt1(user_question, relevant_info)
            findings = call_gemini_api(prompt1)
            st.session_state.mode_state["report_step1"] = findings
            
            # --- FASE 2 ---
            status.write("✍️ Fase 2: Redactando informe ejecutivo...")
            prompt2 = get_report_prompt2(user_question, findings, relevant_info)
            final_report_stream = call_gemini_stream(prompt2)
            
            full_response = ""
            placeholder = st.empty()
            
            for chunk in final_report_stream:
                full_response += chunk
                placeholder.markdown(full_response + "▌")
            
            st.session_state.mode_state["report_final"] = full_response
            placeholder.empty() 
            
            status.update(label="¡Informe completado!", state="complete", expanded=False)
            
            try:
                log_query_event(f"Reporte: {user_question}", mode=c.MODE_REPORT)
            except: pass

    # 3. VISUALIZACIÓN DE RESULTADOS
    if "report_final" in st.session_state.mode_state:
        final_text = st.session_state.mode_state["report_final"]
        
        # A. Renderizado del Texto
        html_content = process_text_with_tooltips(final_text)
        st.markdown(html_content, unsafe_allow_html=True)
        
        st.divider()
        
        # B. SECCIÓN DE GUARDADO (AL FINAL)
        # Usamos un expander o una fila dedicada para guardar
        col_save_btn, col_spacer = st.columns([2, 8])
        
        with col_save_btn:
            # Botón directo para guardar
            if st.button("📌 Guardar en Bitácora", use_container_width=True, help="Guarda este hallazgo en el panel lateral"):
                if save_project_insight(final_text, source_mode="report"):
                    st.toast("✅ ¡Hallazgo guardado exitosamente!")
                    # PEQUEÑA PAUSA Y RECARGA PARA ACTUALIZAR SIDEBAR
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("No se pudo guardar. Verifica la conexión.")

        st.write("") # Espacio
        
        # C. BOTONES DE EXPORTACIÓN
        pdf_bytes = generate_pdf_html(final_text, title="Informe de Investigación", banner_path=banner_file)
        
        col1, col2 = st.columns(2)
        with col1:
            if pdf_bytes:
                st.download_button(
                    label="📥 Descargar PDF",
                    data=pdf_bytes,
                    file_name="Informe_Investigacion.pdf",
                    mime="application/pdf",
                    type="secondary",
                    use_container_width=True
                )
        with col2:
            if st.button("✨ Nuevo Reporte", type="primary", use_container_width=True):
                st.session_state.mode_state.pop("report_step1", None)
                st.session_state.mode_state.pop("report_final", None)
                st.rerun()
