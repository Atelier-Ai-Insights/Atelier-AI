import streamlit as st
from utils import get_relevant_info
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event

# =====================================================
# MODO: EVALUACIÓN DE PRE-IDEAS
# =====================================================

def idea_evaluator_mode(db, selected_files):
    st.subheader("Evaluación de Pre-Ideas")
    st.markdown("Evalúa potencial de idea contra hallazgos.")
    
    if "evaluation_result" in st.session_state:
        st.markdown("---")
        st.markdown("### Evaluación")
        st.markdown(st.session_state.evaluation_result)
        if st.button("Evaluar otra idea", use_container_width=True): 
            del st.session_state["evaluation_result"]
            st.rerun()
    else:
        idea_input = st.text_area("Describe la idea a evaluar:", height=150, placeholder="Ej: Yogures con probióticos...")
        
        if st.button("Evaluar Idea", use_container_width=True):
            if not idea_input.strip(): 
                st.warning("Describe una idea.")
                return
                
            with st.spinner("Evaluando potencial..."):
                context_info = get_relevant_info(db, idea_input, selected_files)
                prompt = (
                    f"**Tarea:** Estratega Mkt/Innovación. Evalúa potencial de 'Idea' **solo** con 'Contexto' (hallazgos Atelier).\n\n"
                    f"**Idea:**\n\"{idea_input}\"\n\n"
                    f"**Contexto (Hallazgos):**\n\"{context_info}\"\n\n"
                    f"**Instrucciones:**\nEvalúa en Markdown estructurado. Basa **cada punto** en 'Contexto'. No conocimiento externo. No citas explícitas.\n\n"
                    "---\n\n"
                    "### 1. Valoración General Potencial\n* Resume: Alto, Moderado con Desafíos, Bajo según Hallazgos.\n\n"
                    "### 2. Sustento Detallado (Basado en Contexto)\n"
                    "* **Positivos:** Conecta idea con necesidades/tensiones clave del contexto. Hallazgos específicos que respaldan.\n"
                    "* **Desafíos/Contradicciones:** Hallazgos que obstaculizan/contradicen.\n\n"
                    "### 3. Sugerencias Evaluación Consumidor (Basado en Contexto)\n"
                    "* 3-4 **hipótesis cruciales** (de hallazgos o vacíos). Para c/u:\n"
                    "    * **Hipótesis:** (Ej: \"Consumidores valoran X sobre Y...\").\n"
                    "    * **Pregunta Clave:** (Ej: \"¿Qué tan importante es X para Ud? ¿Por qué?\").\n"
                    "    * **Aporte Pregunta:** (Ej: \"Validar si beneficio X resuena...\")."
                )
                
                response = call_gemini_api(prompt)
                
                if response: 
                    st.session_state.evaluation_result = response
                    log_query_event(idea_input, mode="Evaluación de Idea")
                    st.rerun()
                else: 
                    st.error("No se pudo generar evaluación.")
