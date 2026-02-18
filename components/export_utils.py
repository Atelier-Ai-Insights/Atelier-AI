import streamlit as st
import re
import time
from reporting.pdf_generator import generate_pdf_html
from reporting.docx_generator import generate_docx
from services.supabase_db import log_message_feedback
from services.memory_service import save_project_insight
from config import banner_file

# --- VENTANA EMERGENTE (MODAL SIMPLIFICADO) ---
@st.dialog("Documentación de Respaldo")
def show_sources_dialog(content):
    """Muestra la lista de archivos consultados para generar el análisis."""
    # Extraemos el nombre del archivo basándonos en el patrón técnico: [1] NombreArchivo.pdf |||
    pattern = r'\[\d+\]\s*([^\[\]\|\n]+?)\s*\|\|\|'
    matches = re.findall(pattern, content)
    
    if not matches:
        st.info("Este análisis se basó en el contexto general de los documentos seleccionados.")
        return

    # Eliminamos duplicados y limpiamos nombres para una visualización estética
    fuentes_unicas = set()
    for fname in matches:
        # 1. Quitamos la extensión del archivo
        clean_name = re.sub(r'\.(pdf|docx|xlsx|txt)$', '', fname, flags=re.IGNORECASE)
        # 2. Quitamos prefijos de fecha (ej: 24-08-30_) y marcas de sistema (In-ATL_)
        clean_name = re.sub(r'^\d{2,4}[-_]\d{1,2}[-_]\d{1,2}[-_]', '', clean_name).replace("In-ATL_", "")
        fuentes_unicas.add(clean_name.strip())

    st.markdown("Los siguientes documentos fueron utilizados como evidencia para este análisis:")
    
    # Listado visual ordenado alfabéticamente
    for fuente in sorted(list(fuentes_unicas)):
        st.markdown(f"📄 **{fuente}**")

def render_final_actions(content, title, mode_key, on_reset_func):
    """Barra maestra con Feedback, Pin, Ver Referencias y Descargas."""
    if not content:
        return

    st.divider()
    clean_text = content.replace("```markdown", "").replace("```", "").strip()
    word_template = "Plantilla_Word_ATL.docx"
    
    # --- BLOQUE 1: FEEDBACK Y PIN (Interacción rápida) ---
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

    st.write("") # Espaciador vertical

    # --- BLOQUE 2: ACCIONES PRINCIPALES (4 COLUMNAS) ---
    col_ref, col_pdf, col_word, col_reset = st.columns(4)

    with col_ref:
        # Detectar si hay referencias en el contenido para habilitar el botón
        tiene_citas = "|||" in content or re.search(r'\[\d+\]', content)
        if st.button("Ver Referencias", use_container_width=True, key=f"ref_{mode_key}", disabled=not tiene_citas):
            show_sources_dialog(content)

    with col_pdf:
        pdf_bytes = generate_pdf_html(clean_text, title=title, banner_path=banner_file)
        if pdf_bytes:
            st.download_button("Descargar PDF", pdf_bytes, f"{title}.pdf", "application/pdf", use_container_width=True, key=f"pdf_{mode_key}")

    with col_word:
        docx_bytes = generate_docx(clean_text, title=title, template_path=word_template)
        if docx_bytes:
            st.download_button("Descargar Word", docx_bytes, f"{title}.docx", use_container_width=True, key=f"word_{mode_key}")

    with col_reset:
        label = "Nueva Búsqueda" if "chat" in mode_key else "Reiniciar"
        if st.button(label, use_container_width=True, type="secondary", key=f"res_{mode_key}"):
            on_reset_func()
            st.rerun()
