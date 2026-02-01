import streamlit as st
import time
from services.gemini_api import call_gemini_api, call_gemini_stream
from utils import get_relevant_info, render_process_status, process_text_with_tooltips
from prompts import get_report_prompt1, get_report_prompt2
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from services.supabase_db import log_query_event, log_message_feedback # <--- NUEVO IMPORT
from services.memory_service import save_project_insight
import constants as c

def report_mode(db, selected_files):
    st.subheader("Generador de Informes de Investigación")
    st.caption("Crea informes ejecutivos de alto nivel basados en múltiples documentos.")
    
    # Input de objetivo
    user_question = st.text_input("¿Qué objetivo de investigación deseas abordar?", placeholder="Ej: Analizar la percepción de precios en la categoría de lácteos...")
    
    if not selected_files:
        st.info("👈 Por favor, selecciona los documentos a analizar en el menú lateral.")
        return

    # Botón de Acción
    if st.button("Generar Informe", type="primary", use_container_width=True):
        if not user_question:
            st.warning("Debes definir un objetivo."); return
            
        # Limpiar estados previos
        for k in ["report_step1", "report_final"]: st.session_state.mode_state.pop(k, None)
        
        # --- INICIO PROCESO VISUAL ---
        with st.status("Iniciando protocolo de investigación...", expanded=True) as status:
            
            # PASO 1: Búsqueda RAG
            status.write("Recopilando evidencia del repositorio (RAG)...")
            relevant_info = get_relevant_info(db, user_question, selected_files)
            
            if not relevant_info:
                status.update(label="No se encontraron datos suficientes.", state="error")
                st.error("Intenta con otros documentos o una pregunta más amplia.")
                return

            # PASO 2: Extracción de Hechos
            status.write("Analizando datos duros y hechos clave (Fase 1/2)...")
            findings = call_gemini_api(get_report_prompt1(user_question, relevant_info))
            st.session_state.mode_state["report_step1"] = findings
            
            # PASO 3: Redacción Estratégica
            status.write("Redactando informe para C-Level (Fase 2/2)...")
            prompt2 = get_report_prompt2(user_question, findings, relevant_info)
            stream = call_gemini_stream(prompt2)
            
            # PASO 4: Streaming
            full_resp = ""
            ph = st.empty()
            
            if stream:
                for chunk in stream:
                    full_resp += chunk
                    ph.markdown(full_resp + "▌")
                
                st.session_state.mode_state["report_final"] = full_resp
                ph.empty() 
                
                status.update(label="¡Informe completado exitosamente!", state="complete", expanded=False)
                
                try: log_query_event(f"Reporte: {user_question}", mode=c.MODE_REPORT)
                except: pass
            else:
                status.update(label="Error de conexión con IA", state="error")

    # --- RESULTADO FINAL ---
    if "report_final" in st.session_state.mode_state:
        final_text = st.session_state.mode_state["report_final"]
        
        # Limpieza y Renderizado
        clean_text = final_text.replace("```markdown", "").replace("```", "")
        html_content = process_text_with_tooltips(clean_text)
        st.markdown(html_content, unsafe_allow_html=True)
        
        # --- BARRA DE ACCIONES INTEGRADA (Igual al Chat) ---
        st.write("") # Espaciador
        col_up, col_down, col_spacer, col_pin = st.columns([1, 1, 10, 1])
        
        # Claves únicas para evitar conflictos si se generan varios reportes
        key_suffix = str(len(final_text)) 

        with col_up:
            if st.button("👍", key=f"rep_up_{key_suffix}", help="Informe útil"):
                if log_message_feedback(final_text, "report_mode", "up"):
                    st.toast("Feedback registrado 👍")

        with col_down:
            if st.button("👎", key=f"rep_down_{key_suffix}", help="Informe inexacta"):
                if log_message_feedback(final_text, "report_mode", "down"):
                    st.toast("Revisaremos la calidad 🤔")

        with col_pin:
            if st.button("📌", key=f"rep_pin_{key_suffix}", help="Guardar en Bitácora"):
                if save_project_insight(final_text, source_mode="report"):
                    st.toast("✅ Guardado en bitácora")
                    time.sleep(1) 

        st.divider()
        
        # 3. BOTONES DE DESCARGA
        c1, c2 = st.columns(2)
        
        with c1:
            pdf_bytes = generate_pdf_html(clean_text, title="Informe de Investigación", banner_path=banner_file)
            if pdf_bytes:
                st.download_button("Descargar PDF", data=pdf_bytes, file_name="reporte_atelier.pdf", mime="application/pdf", use_container_width=True)
        
        with c2:
            if st.button("Nuevo Informe", type="secondary", use_container_width=True):
                st.session_state.mode_state.pop("report_step1", None)
                st.session_state.mode_state.pop("report_final", None)
                st.rerun()
