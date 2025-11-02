import streamlit as st
from utils import get_relevant_info
from services.gemini_api import call_gemini_api
# --- ¡IMPORTACIÓN ACTUALIZADA! ---
from services.supabase_db import log_query_event, log_query_feedback
from prompts import get_concept_gen_prompt

# =====================================================
# MODO: GENERACIÓN DE CONCEPTOS
# =====================================================

def concept_generation_mode(db, selected_files):
    st.subheader("Generación de Conceptos")
    st.markdown("Genera concepto de producto/servicio a partir de idea y hallazgos.")

    # --- CAMBIO 1: El Callback AHORA ACEPTA el query_id ---
    def concept_feedback_callback(feedback, query_id):
        if query_id:
            # Usar .get() para seguridad y score=0 para 'thumbs_down'
            score = 1 if feedback.get('score') == 'thumbs_up' else 0
            log_query_feedback(query_id, score)
            st.toast("¡Gracias por tu feedback!")
            # Oculta los botones después de votar
            st.session_state.voted_on_last_concept = True
        else:
            st.toast("Error: No se encontró el ID de la consulta.")
    # --- FIN DEL CALLBACK ---
    
    if "generated_concept" in st.session_state:
        st.markdown("---")
        st.markdown("### Concepto Generado")
        st.markdown(st.session_state.generated_concept)

        # --- ¡SECCIÓN DE FEEDBACK CORREGIDA! ---
        query_id = st.session_state.get("last_concept_query_id")
        if query_id and not st.session_state.get("voted_on_last_concept", False):
            # CAMBIO 2: Usar st.feedback (nombre oficial)
            st.feedback(
                key=f"feedback_{query_id}", # CAMBIO 3: Key única
                on_submit=concept_feedback_callback,
                args=(query_id,) # CAMBIO 4: Pasar el query_id como argumento
            )
        # --- FIN DE LA SECCIÓN DE FEEDBACK ---

        if st.button("Generar nuevo concepto", use_container_width=True): 
            st.session_state.pop("generated_concept")
            # Limpiamos las variables de feedback
            st.session_state.pop("last_concept_query_id", None)
            st.session_state.pop("voted_on_last_concept", None)
            st.rerun() # Este rerun es correcto para limpiar
    else:
        product_idea = st.text_area("Describe tu idea:", height=150, placeholder="Ej: Snack saludable...")
        
        if st.button("Generar Concepto", use_container_width=True):
            if not product_idea.strip(): 
                st.warning("Describe tu idea.")
                return
                
            with st.spinner("Generando concepto..."):
                context_info = get_relevant_info(db, product_idea, selected_files)
                
                prompt = get_concept_gen_prompt(product_idea, context_info)
                
                response = call_gemini_api(prompt)
                
                if response: 
                    st.session_state.generated_concept = response
                    
                    query_id = log_query_event(product_idea, mode="Generación de conceptos")
                    st.session_state["last_concept_query_id"] = query_id
                    st.session_state["voted_on_last_concept"] = False 
                    
                    st.rerun() # Este rerun es correcto para mostrar el resultado
                else: 
                    st.error("No se pudo generar concepto.")