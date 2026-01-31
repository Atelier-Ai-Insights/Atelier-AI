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
            status.write("Recopilando evidencia del repositorio...")
            relevant_info = get_relevant_info(db, user_question, selected_files)
            
            if not relevant_info:
                status.update(label="No se encontraron datos suficientes.", state="error")
                st.error("Intenta con otros documentos o una pregunta más amplia.")
                return

            # PASO 2: Extracción de Hechos (Fase Analítica)
            status.write("Analizando datos duros y hechos clave (Fase 1/2)...")
            # Usamos el Prompt 1 que extrae solo hechos, sin redacción final
            findings = call_gemini_api(get_report_prompt1(user_question, relevant_info))
            st.session_state.mode_state["report_step1"] = findings
            
            # PASO 3: Redacción Estratégica (Fase Creativa)
            status.write("Redactando informe (Fase 2/2)...")
            # Usamos el Prompt 2 que toma los hechos y escribe como consultor
            prompt2 = get_report_prompt2(user_question, findings, relevant_info)
            stream = call_gemini_stream(prompt2)
            
            # PASO 4: Streaming en tiempo real
            full_resp = ""
            ph = st.empty()
            
            if stream:
                for chunk in stream:
                    full_resp += chunk
                    # Mostramos el texto crudo mientras se genera para velocidad
                    ph.markdown(full_resp + "▌")
                
                st.session_state.mode_state["report_final"] = full_resp
                ph.empty() # Limpiamos el placeholder temporal
                
                # Finalización exitosa
                status.update(label="¡Informe completado exitosamente!", state="complete", expanded=False)
                
                # Log
                try: log_query_event(f"Reporte: {user_question}", mode=c.MODE_REPORT)
                except: pass
            else:
                status.update(label="Error de conexión con IA", state="error")

    # --- RESULTADO FINAL ---
    if "report_final" in st.session_state.mode_state:
        final_text = st.session_state.mode_state["report_final"]
        
        # Limpieza de formato para evitar conflictos con tooltips
        clean_text = final_text.replace("```markdown", "").replace("```", "")
        
        # 1. MOSTRAR REPORTE CON TOOLTIPS
        html_content = process_text_with_tooltips(clean_text)
        st.markdown(html_content, unsafe_allow_html=True)
        
        # 2. BOTÓN PIN (Discreto a la derecha)
        col_space, col_pin = st.columns([15, 1])
        with col_pin:
            if st.button("📌", help="Guardar en Bitácora"):
                if save_project_insight(clean_text, source_mode="report"):
                    st.toast("✅ Guardado en bitácora")
                    time.sleep(1) 

        st.divider()
        
        # 3. BOTONES DE DESCARGA
        c1, c2 = st.columns(2)
        
        with c1:
            # Generamos el PDF usando el texto limpio
            pdf_bytes = generate_pdf_html(clean_text, title="Informe de Investigación", banner_path=banner_file)
            if pdf_bytes:
                st.download_button(
                    label="Descargar PDF",
                    data=pdf_bytes,
                    file_name="reporte_atelier.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
        
        with c2:
            if st.button("Nuevo Informe", type="secondary", use_container_width=True):
                st.session_state.mode_state.pop("report_step1", None)
                st.session_state.mode_state.pop("report_final", None)
                st.rerun()
