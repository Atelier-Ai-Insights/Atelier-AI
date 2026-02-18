import streamlit as st
import time
import constants as c

# --- UTILS & SERVICES ---
from utils import get_relevant_info, process_text_with_tooltips
from services.gemini_api import call_gemini_api, call_gemini_stream
from services.supabase_db import log_query_event
from prompts import get_report_prompt1, get_report_prompt2

# --- COMPONENTES UNIFICADOS ---
from components.chat_interface import render_chat_history
from components.export_utils import render_final_actions

def report_mode(db, selected_files):
    """
    Generador de Informes: Crea informes ejecutivos siguiendo el estándar
    de invisibilidad y trazabilidad sistemática.
    """
    st.subheader("Generador de Informes de Investigación")
    st.caption("Crea informes ejecutivos de alto nivel basados en múltiples documentos.")
    
    user_question = st.text_input(
        "¿Qué objetivo de investigación deseas abordar?", 
        placeholder="Ej: Analizar la percepción de precios en la categoría de lácteos..."
    )
    
    if not selected_files:
        st.info("👈 Por favor, selecciona los documentos a analizar en el menú lateral.")
        return

    # 1. INICIALIZAR HISTORIAL (Persistencia para componentes unificados)
    if "report_history" not in st.session_state.mode_state:
        st.session_state.mode_state["report_history"] = []

    # 2. RENDERIZAR HISTORIAL (Limpio visualmente)
    # Oculta metadatos técnicos mientras mantiene las referencias vivas para el modal.
    render_chat_history(st.session_state.mode_state["report_history"], source_mode="report")

    # 3. GENERACIÓN DE INFORME
    if st.button("Generar Informe", type="primary", use_container_width=True):
        if not user_question:
            st.warning("Debes definir un objetivo."); return
            
        # Limpieza de estados previos
        st.session_state.mode_state["report_history"] = []
        
        with st.status("Iniciando protocolo de investigación...", expanded=True) as status:
            status.write("Recopilando evidencia del repositorio (RAG)...")
            relevant_info = get_relevant_info(db, user_question, selected_files)
            
            if not relevant_info:
                status.update(label="No se encontraron datos suficientes.", state="error")
                st.error("Intenta con otros documentos o una pregunta más amplia.")
                return

            status.write("Analizando datos duros y hechos clave (Fase 1/2)...")
            findings = call_gemini_api(get_report_prompt1(user_question, relevant_info))
            
            status.write("Redactando informe para C-Level (Fase 2/2)...")
            prompt2 = get_report_prompt2(user_question, findings, relevant_info)
            stream = call_gemini_stream(prompt2)
            
            full_resp = ""
            ph = st.empty()
            
            if stream:
                for chunk in stream:
                    full_resp += chunk
                    ph.markdown(full_resp + "▌")
                
                # GUARDADO CRÍTICO: Persistencia para render_final_actions
                st.session_state.mode_state["report_history"] = [
                    {"role": "user", "content": f"Objetivo: {user_question}"},
                    {"role": "assistant", "content": full_resp}
                ]
                ph.empty() 
                
                status.update(label="¡Informe completado exitosamente!", state="complete", expanded=False)
                try: log_query_event(f"Reporte: {user_question}", mode=c.MODE_REPORT)
                except: pass
                st.rerun()
            else:
                status.update(label="Error de conexión con IA", state="error")

    # 4. ACCIONES FINALES (Barra Maestra Unificada)
    if st.session_state.mode_state["report_history"]:
        # Recuperamos el análisis final (el informe)
        final_report_content = st.session_state.mode_state["report_history"][-1]["content"]
        
        def reset_report_workflow():
            st.session_state.mode_state["report_history"] = []
            st.rerun()

        # Renderiza Feedback, Referencias (con filtrado único) y Exportaciones
        render_final_actions(
            content=final_report_content,
            title=f"Informe_Atelier_{user_question[:20]}",
            mode_key="report_actions",
            on_reset_func=reset_report_workflow
        )
