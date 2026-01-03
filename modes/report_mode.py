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
    
    user_question = st.text_input("¿Qué objetivo de investigación deseas abordar?", placeholder="Ej: Analizar la percepción de precios...")
    
    if not selected_files: st.warning("Selecciona documentos."); return

    if st.button("Generar Informe", type="primary", use_container_width=True):
        if not user_question: return
        for k in ["report_step1", "report_final"]: st.session_state.mode_state.pop(k, None)
        
        with render_process_status("Investigando...", expanded=True) as status:
            relevant_info = get_relevant_info(db, user_question, selected_files)
            if not relevant_info: status.update(label="Sin datos", state="error"); return

            findings = call_gemini_api(get_report_prompt1(user_question, relevant_info))
            st.session_state.mode_state["report_step1"] = findings
            
            prompt2 = get_report_prompt2(user_question, findings, relevant_info)
            stream = call_gemini_stream(prompt2)
            
            full_resp = ""
            ph = st.empty()
            for chunk in stream: full_resp += chunk; ph.markdown(full_resp + "▌")
            
            st.session_state.mode_state["report_final"] = full_resp
            ph.empty()
            status.update(label="¡Listo!", state="complete", expanded=False)
            try: log_query_event(f"Reporte: {user_question}", mode=c.MODE_REPORT)
            except: pass

    if "report_final" in st.session_state.mode_state:
        final_text = st.session_state.mode_state["report_final"]
        
        # --- CORRECCIÓN VISUAL (El texto verde) ---
        # Eliminamos las comillas invertidas (`) que la IA usa para enfatizar,
        # ya que estas convierten el texto en código y rompen el HTML de las citas.
        clean_text = final_text.replace("```", "").replace("`", "")
        
        # 1. MOSTRAR REPORTE
        html_content = process_text_with_tooltips(clean_text)
        st.markdown(html_content, unsafe_allow_html=True)
        
        # 2. PIN MINIMALISTA
        col_space, col_pin = st.columns([15, 1])
        with col_pin:
            if st.button("📌", help="Guardar en Bitácora"):
                # Guardamos el texto limpio para que se vea bien también en la bitácora
                if save_project_insight(clean_text, source_mode="report"):
                    st.toast("✅ Guardado")
                    time.sleep(1) 
                    st.rerun()    

        st.divider()
        
        # 3. BOTONES PDF / NUEVO
        pdf_bytes = generate_pdf_html(clean_text, title="Informe", banner_path=banner_file)
        c1, c2 = st.columns(2)
        with c1:
            if pdf_bytes: st.download_button("PDF", data=pdf_bytes, file_name="reporte.pdf", mime="application/pdf", use_container_width=True)
        with c2:
            if st.button("Nuevo", type="primary", use_container_width=True):
                st.session_state.mode_state.pop("report_step1", None)
                st.session_state.mode_state.pop("report_final", None)
                st.rerun()
