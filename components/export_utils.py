import streamlit as st
import re
import time
from reporting.pdf_generator import generate_pdf_html
from reporting.docx_generator import generate_docx
from services.supabase_db import log_message_feedback
from services.memory_service import save_project_insight
from config import banner_file

# --- VENTANA EMERGENTE (VERSIÓN ROBUSTA) ---
@st.dialog("Documentación de Respaldo")
def show_sources_dialog(content):
    """Extrae y muestra las fuentes detectadas con su numeración."""
    
    # 1. Intentamos capturar el formato técnico: [1] Nombre.pdf |||
    matches = re.findall(r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|', content)
    
    # 2. Respaldo: Buscamos archivos mencionados con su número [1] Nombre.pdf
    if not matches:
        matches = re.findall(r'\[(\d+)\]\s*([a-zA-Z0-9_-]+\.(?:pdf|docx|xlsx))', content, flags=re.IGNORECASE)

    if not matches:
        st.info("Este análisis se basó en el contexto general de los documentos seleccionados.")
        return

    # Diccionario para mapear {Número: NombreLimpio}
    fuentes_finales = {}
    for cid, fname in matches:
        # Limpieza de extensiones y prefijos técnicos
        name = re.sub(r'\.(pdf|docx|xlsx)$', '', fname, flags=re.IGNORECASE)
        name = re.sub(r'^\d{2,4}[-_]\d{1,2}[-_]\d{1,2}[-_]', '', name).replace("In-ATL_", "")
        fuentes_finales[cid] = name.strip()

    st.write("### Fuentes asociadas a este análisis:")
    
    # Renderizar lista numerada ordenada
    for cid in sorted(fuentes_finales.keys(), key=int):
        st.markdown(f"**[{cid}]** 📄 {fuentes_finales[cid]}")

def render_final_actions(content, title, mode_key, on_reset_func):
    """Barra maestra de acciones finales."""
    if not content:
        return

    st.divider()
    clean_text = content.replace("```markdown", "").replace("```", "").strip()
    
    # --- BLOQUE 1: FEEDBACK Y PIN ---
    st.caption("¿Qué te pareció este análisis?")
    col_f1, col_f2, col_pin, col_spacer = st.columns([1, 1, 1, 9])
    
    with col_f1:
        if st.button("👍", key=f"up_{mode_key}"):
            log_message_feedback(clean_text, mode_key, "up")
            st.toast("Feedback registrado 👍")
    
    with col_f2:
        if st.button("👎", key=f"down_{mode_key}"):
            log_message_feedback(clean_text, mode_key, "down")
            st.toast("Feedback registrado 🤔")

    with col_pin:
        if st.button("📌", key=f"pin_{mode_key}"):
            if save_project_insight(clean_text, source_mode=mode_key):
                st.toast("✅ Guardado en bitácora")
                time.sleep(0.5)
                st.rerun()

    st.write("") 

    # --- BLOQUE 2: ACCIONES PRINCIPALES ---
    col_ref, col_pdf, col_word, col_reset = st.columns(4)

    with col_ref:
        # Habilitado si detecta corchetes o rastro de archivos
        tiene_datos = "[" in content or ".pdf" in content.lower()
        if st.button("Ver Referencias", use_container_width=True, key=f"ref_{mode_key}", disabled=not tiene_datos):
            show_sources_dialog(content)

    with col_pdf:
        pdf_bytes = generate_pdf_html(clean_text, title=title, banner_path=banner_file)
        if pdf_bytes:
            st.download_button("Descargar PDF", pdf_bytes, f"{title}.pdf", use_container_width=True, key=f"p_{mode_key}")

    with col_word:
        docx_bytes = generate_docx(clean_text, title=title)
        if docx_bytes:
            st.download_button("Descargar Word", docx_bytes, f"{title}.docx", use_container_width=True, key=f"w_{mode_key}")

    with col_reset:
        label = "Nueva Búsqueda" if "chat" in mode_key else "Reiniciar"
        if st.button(label, use_container_width=True, type="secondary", key=f"res_{mode_key}"):
            on_reset_func()
            st.rerun()
