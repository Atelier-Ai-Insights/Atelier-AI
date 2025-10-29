import streamlit as st
from utils import get_relevant_info, reset_report_workflow
from services.gemini_api import call_gemini_api
from services.supabase_db import get_monthly_usage, log_query_event
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

# =====================================================
# MODO: GENERAR REPORTE DE REPORTES
# =====================================================

def generate_final_report(question, db, selected_files):
    relevant_info = get_relevant_info(db, question, selected_files)
    prompt1 = ( f"Pregunta del Cliente: ***{question}***\n\nInstrucciones:\n1. Identifica marca/producto exacto.\n2. Reitera: ***{question}***.\n3. Usa contexto para hallazgos relevantes.\n4. Extractos breves, no citas completas.\n5. Metadatos y cita IEEE [1].\n6. Referencias completas asociadas a [1], usar título de proyecto.\n7. Enfócate en hallazgos positivos.\n\nContexto:\n{relevant_info}\n\nRespuesta:\n## Hallazgos Clave:\n- [Hallazgo 1 [1]]\n- [Hallazgo 2 [2]]\n## Referencias:\n- [1] [Referencia completa 1]\n- [2] [Referencia completa 2]" )
    result1 = call_gemini_api(prompt1)
    if result1 is None: return None
    
    prompt2 = ( f"Pregunta: ***{question}***\n\nInstrucciones:\n1. Responde específico a marca/producto.\n2. Menciona que estudios son de Atelier.\n3. Rol: Analista experto (Ciencias Comportamiento, Mkt Research, Mkt Estratégico). Claridad, síntesis, estructura.\n4. Estilo: Claro, directo, conciso, memorable (Heath). Evita tecnicismos.\n\nEstructura Informe (breve y preciso):\n- Introducción: Contexto, pregunta, hallazgo cualitativo atractivo.\n- Hallazgos Principales: Hechos relevantes del contexto/resultados, respondiendo a pregunta. Solo info relevante de marca/producto. Citas IEEE [1] (título estudio).\n- Insights: Aprendizajes profundos, analogías. Frases cortas con significado.\n- Conclusiones: Síntesis, dirección clara basada en insights. No repetir.\n- Recomendaciones (3-4): Concretas, creativas, accionables, alineadas con insights/conclusiones.\n- Referencias: Título estudio [1].\n\n5. IMPORTANTE: Espaciar nombres de marcas/productos (ej: 'marca X debe...').\n\nUsa este Resumen y Contexto:\nResumen:\n{result1}\n\nContexto Adicional:\n{relevant_info}\n\nRedacta informe completo:" )
    result2 = call_gemini_api(prompt2)
    if result2 is None: return None
    
    return result2

def report_mode(db, selected_files):
    st.markdown("### Generar Reporte de Reportes")
    st.markdown("Herramienta potente para síntesis. Analiza estudios seleccionados y genera informe consolidado.")
    
    if "report" in st.session_state and st.session_state["report"]:
        st.markdown("---"); st.markdown("### Informe Generado"); st.markdown(st.session_state["report"], unsafe_allow_html=True); st.markdown("---")
    
    question = st.text_area("Escribe tu consulta para el reporte…", value=st.session_state.get("last_question", ""), height=150, key="report_question")
    
    if st.button("Generar Reporte", use_container_width=True):
        report_limit = st.session_state.plan_features.get('reports_per_month', 0); current_reports = get_monthly_usage(st.session_state.user, "Generar un reporte de reportes")
        if current_reports >= report_limit and report_limit != float('inf'): st.error(f"Límite de {int(report_limit)} reportes alcanzado."); return
        if not question.strip(): st.warning("Ingresa una consulta."); return
        
        st.session_state["last_question"] = question
        with st.spinner("Generando informe..."): 
            report = generate_final_report(question, db, selected_files)
            
        if report is None: 
            st.error("No se pudo generar."); st.session_state.pop("report", None)
        else: 
            st.session_state["report"] = report; log_query_event(question, mode="Generar un reporte de reportes"); st.rerun()
            
    if "report" in st.session_state and st.session_state["report"]:
        pdf_bytes = generate_pdf_html(st.session_state["report"], title="Informe Final", banner_path=banner_file)
        col1, col2 = st.columns(2)
        with col1:
            if pdf_bytes: 
                st.download_button("Descargar PDF", data=pdf_bytes, file_name="Informe_AtelierIA.pdf", mime="application/pdf", use_container_width=True)
            else: 
                st.button("Error PDF", disabled=True, use_container_width=True)
        with col2: 
            st.button("Nueva consulta", on_click=reset_report_workflow, key="new_report_query_btn", use_container_width=True)
