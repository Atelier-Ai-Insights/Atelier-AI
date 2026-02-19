import streamlit as st
import time
import constants as c

# --- COMPONENTES UNIFICADOS ---
from components.chat_interface import render_chat_history, handle_chat_interaction
from components.export_utils import render_final_actions

# 1. Servicios IA
from services.gemini_api import call_gemini_stream
gemini_available = True

# 2. Utilidades
from utils import get_relevant_info

# 3. Base de Datos y Prompts [Sincronizados]
from services.storage import log_query_event
from prompts import get_concept_gen_prompt 

def concept_generation_mode(db, selected_files):
    """
    Generador de Conceptos: Estructura ideas de innovación manteniendo 
    el estándar de invisibilidad y trazabilidad sistemática.
    """
    st.subheader("Generador de Conceptos")
    st.caption("Estructura ideas de innovación en conceptos de marketing sólidos (Insight + Beneficio + RTB).")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    # 1. INICIALIZAR HISTORIAL
    if "concept_history" not in st.session_state.mode_state:
        st.session_state.mode_state["concept_history"] = []

    # 2. RENDERIZAR HISTORIAL
    render_chat_history(st.session_state.mode_state["concept_history"], source_mode="concept")

    # 3. INTERACCIÓN DEL USUARIO
    if concept_input := st.chat_input("Describe la idea base para el concepto..."):

        def concept_generator():
            status_box = st.empty()
            with status_box.status("Diseñando concepto ganador...", expanded=True) as status:
                # Paso 1: RAG
                status.write("Buscando evidencia de soporte en el repositorio...")
                relevant_info = get_relevant_info(db, concept_input, selected_files)
                
                # Paso 2: Estructuración
                status.write("Estructurando Insight, Beneficio y RTB...")
                # Contexto para coherencia
                hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["concept_history"][-3:]])
                prompt = get_concept_gen_prompt(concept_input, relevant_info)
                
                # Paso 3: Generación Stream
                status.write("Redactando propuesta estratégica...")
                stream = call_gemini_stream(prompt)
                
                if stream:
                    status.update(label="¡Concepto Generado!", state="complete", expanded=False)
                    time.sleep(0.7)
                    status_box.empty()
                    return stream
                else:
                    status.update(label="Error al generar", state="error")
                    return iter(["Error al generar el concepto."])

        # Delegamos al componente visual para guardado íntegro
        handle_chat_interaction(
            prompt=concept_input,
            response_generator_func=concept_generator,
            history_key="concept_history",
            source_mode="concept",
            # CORRECCIÓN: Llamada posicional para evitar TypeError
            on_generation_success=lambda resp: log_query_event(f"Concepto: {concept_input[:30]}", c.MODE_CONCEPT)
        )

    # 4. ACCIONES FINALES
    if st.session_state.mode_state["concept_history"]:
        full_content = ""
        for m in st.session_state.mode_state["concept_history"]:
            role_label = "Idea Base" if m["role"] == "user" else "Atelier AI"
            full_content += f"### {role_label}\n{m['content']}\n\n"

        def reset_concept_workflow():
            st.session_state.mode_state["concept_history"] = []
            st.rerun()

        render_final_actions(
            content=full_content,
            title="Generacion_Conceptos_Atelier",
            mode_key="concept_actions",
            on_reset_func=reset_concept_workflow
        )
