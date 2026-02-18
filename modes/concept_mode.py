import streamlit as st
import time
import constants as c

# --- COMPONENTES UNIFICADOS ---
from components.chat_interface import render_chat_history, handle_chat_interaction
from components.export_utils import render_final_actions

# 1. Servicios IA
try:
    from services.gemini_api import call_gemini_stream
    gemini_available = True
except ImportError:
    gemini_available = False
    def call_gemini_stream(prompt): return None

# 2. Utilidades
try:
    from utils import get_relevant_info
except ImportError:
    def get_relevant_info(db, q, f): return ""

# 3. Base de Datos y Prompts
try:
    from services.supabase_db import log_query_event
    from prompts import get_concept_gen_prompt 
except ImportError:
    def log_query_event(q, m): pass
    def get_concept_gen_prompt(h, r): return ""

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

    # 2. RENDERIZAR HISTORIAL (Limpio visualmente)
    # Oculta metadatos técnicos mientras mantiene las referencias vivas.
    render_chat_history(st.session_state.mode_state["concept_history"], source_mode="concept")

    # 3. INTERACCIÓN DEL USUARIO
    if concept_input := st.chat_input("Describe la idea base para el concepto..."):

        def concept_generator():
            status_box = st.empty()
            with status_box.status("Diseñando concepto ganador...", expanded=True) as status:
                if not gemini_available:
                    status.update(label="IA no disponible", state="error")
                    return iter(["Error: IA no disponible."])

                # Paso 1: RAG
                status.write("Buscando evidencia de soporte en el repositorio...")
                relevant_info = get_relevant_info(db, concept_input, selected_files)
                
                # Paso 2: Estructuración
                status.write("Estructurando Insight, Beneficio y RTB...")
                # Contexto de los últimos 3 mensajes para coherencia
                hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["concept_history"][-3:]])
                prompt = get_concept_gen_prompt(hist_str, relevant_info)
                
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
            on_generation_success=lambda resp: log_query_event(f"Concepto: {concept_input[:30]}", mode=c.MODE_CONCEPT)
        )

    # 4. ACCIONES FINALES (Barra Maestra Unificada)
    if st.session_state.mode_state["concept_history"]:
        # Construimos el contenido acumulado preservando metadatos para el modal
        full_content = ""
        for m in st.session_state.mode_state["concept_history"]:
            role_label = "Idea Base" if m["role"] == "user" else "Atelier AI"
            full_content += f"### {role_label}\n{m['content']}\n\n"

        def reset_concept_workflow():
            st.session_state.mode_state["concept_history"] = []
            st.rerun()

        # Renderiza Feedback, Referencias (con filtrado único) y Exportaciones
        render_final_actions(
            content=full_content,
            title="Generacion_Conceptos_Atelier",
            mode_key="concept_actions",
            on_reset_func=reset_concept_workflow
        )
