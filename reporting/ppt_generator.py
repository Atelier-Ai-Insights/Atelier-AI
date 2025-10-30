import json
import streamlit as st
from io import BytesIO
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_AUTO_SIZE
from pptx.dml.color import RGBColor
import os
import traceback # Importar traceback para errores

# --- Plantillas de Diapositivas ---

def _crear_slide_oportunidades(prs, data):
    """Crea la diapositiva de Definición de Oportunidades."""
    blank_slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_slide_layout)

    # Título
    txBox_title = slide.shapes.add_textbox(Inches(1.5), Inches(0.5), Inches(13), Inches(1))
    p_title = txBox_title.text_frame.paragraphs[0]
    p_title.text = data.get("titulo_diapositiva", "Resumen Estratégico")
    p_title.font.bold = True; p_title.font.size = Pt(44); p_title.alignment = PP_ALIGN.CENTER
    txBox_title.text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT

    # Insight Clave
    txBox_insight = slide.shapes.add_textbox(Inches(1.5), Inches(1.8), Inches(13), Inches(1))
    tf_insight = txBox_insight.text_frame; tf_insight.word_wrap = True
    p_insight = tf_insight.add_paragraph()
    p_insight.text = f"Insight Clave: {data.get('insight_clave', 'N/A')}"
    p_insight.font.italic = True; p_insight.font.size = Pt(18); p_insight.font.color.rgb = RGBColor(0x33, 0x33, 0x33); p_insight.alignment = PP_ALIGN.LEFT

    # Contenido Principal
    txBox_content = slide.shapes.add_textbox(Inches(1.5), Inches(2.8), Inches(13), Inches(5.5))
    tf_content = txBox_content.text_frame; tf_content.word_wrap = True

    # Hallazgos
    p_h_title = tf_content.paragraphs[0]; p_h_title.text = "Hallazgos Principales"
    p_h_title.font.bold = True; p_h_title.font.size = Pt(28); p_h_title.space_after = Pt(6)
    for hallazgo in data.get("hallazgos_principales", ["N/A"]):
        p = tf_content.add_paragraph(); p.text = hallazgo; p.font.size = Pt(16); p.level = 1; p.space_after = Pt(6)

    tf_content.add_paragraph().space_after = Pt(14) # Espacio

    # Oportunidades
    p_o_title = tf_content.add_paragraph(); p_o_title.text = "Oportunidades"
    p_o_title.font.bold = True; p_o_title.font.size = Pt(28); p_o_title.space_after = Pt(6)
    for op in data.get("oportunidades", ["N/A"]):
        p = tf_content.add_paragraph(); p.text = op; p.font.size = Pt(16); p.level = 1; p.space_after = Pt(6)

    tf_content.add_paragraph().space_after = Pt(14) # Espacio

    # Recomendación
    p_r_title = tf_content.add_paragraph(); p_r_title.text = "Recomendación Estratégica"
    p_r_title.font.bold = True; p_r_title.font.size = Pt(28); p_r_title.space_after = Pt(6)
    p_r = tf_content.add_paragraph(); p_r.text = data.get("recomendacion_estrategica", "N/A"); p_r.font.size = Pt(16); p_r.level = 1; p_r.space_after = Pt(6)

    return prs

def _crear_slide_dofa(prs, data):
    """Crea la diapositiva de Análisis DOFA."""
    blank_slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_slide_layout)

    # Título
    txBox_title = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(14), Inches(1))
    p_title = txBox_title.text_frame.paragraphs[0]
    p_title.text = data.get("titulo_diapositiva", "Análisis DOFA")
    p_title.font.bold = True; p_title.font.size = Pt(40); p_title.alignment = PP_ALIGN.CENTER
    txBox_title.text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT

    # --- Contenido en dos columnas ---
    col1_left = Inches(1); col_width = Inches(6.5); col_top = Inches(1.8); col_height = Inches(6.5)
    col2_left = Inches(1) + col_width + Inches(1)

    # Columna Izquierda (Fortalezas y Debilidades)
    txBox_col1 = slide.shapes.add_textbox(col1_left, col_top, col_width, col_height)
    tf_col1 = txBox_col1.text_frame; tf_col1.word_wrap = True

    p_f_title = tf_col1.paragraphs[0]; p_f_title.text = "Fortalezas (+ Interno)"
    p_f_title.font.bold = True; p_f_title.font.size = Pt(24); p_f_title.space_after = Pt(6)
    for item in data.get("fortalezas", ["N/A"]):
        p = tf_col1.add_paragraph(); p.text = item; p.font.size = Pt(14); p.level = 1; p.space_after = Pt(4)
    tf_col1.add_paragraph().space_after = Pt(12) # Espacio

    p_d_title = tf_col1.add_paragraph(); p_d_title.text = "Debilidades (- Interno)"
    p_d_title.font.bold = True; p_d_title.font.size = Pt(24); p_d_title.space_after = Pt(6)
    for item in data.get("debilidades", ["N/A"]):
        p = tf_col1.add_paragraph(); p.text = item; p.font.size = Pt(14); p.level = 1; p.space_after = Pt(4)

    # Columna Derecha (Oportunidades y Amenazas)
    txBox_col2 = slide.shapes.add_textbox(col2_left, col_top, col_width, col_height)
    tf_col2 = txBox_col2.text_frame; tf_col2.word_wrap = True

    p_o_title = tf_col2.paragraphs[0]; p_o_title.text = "Oportunidades (+ Externo)"
    p_o_title.font.bold = True; p_o_title.font.size = Pt(24); p_o_title.space_after = Pt(6)
    for item in data.get("oportunidades", ["N/A"]):
        p = tf_col2.add_paragraph(); p.text = item; p.font.size = Pt(14); p.level = 1; p.space_after = Pt(4)
    tf_col2.add_paragraph().space_after = Pt(12) # Espacio

    p_a_title = tf_col2.add_paragraph(); p_a_title.text = "Amenazas (- Externo)"
    p_a_title.font.bold = True; p_a_title.font.size = Pt(24); p_a_title.space_after = Pt(6)
    for item in data.get("amenazas", ["N/A"]):
        p = tf_col2.add_paragraph(); p.text = item; p.font.size = Pt(14); p.level = 1; p.space_after = Pt(4)

    return prs

def _crear_slide_empatia(prs, data):
     st.warning("Plantilla 'Mapa de Empatía' aún no implementada en el generador PPT.")
     blank_slide_layout = prs.slide_layouts[6]
     slide = prs.slides.add_slide(blank_slide_layout)
     txBox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(14), Inches(6))
     tf = txBox.text_frame
     tf.paragraphs[0].text = data.get('titulo_diapositiva', 'Mapa de Empatía')
     tf.paragraphs[0].font.bold = True; tf.paragraphs[0].font.size = Pt(36)
     p = tf.add_paragraph(); p.text = "(Implementación pendiente)"
     p = tf.add_paragraph(); p.text = json.dumps(data, indent=2) # Mostrar el JSON
     return prs

def _crear_slide_propuesta_valor(prs, data):
     st.warning("Plantilla 'Propuesta de Valor' aún no implementada en el generador PPT.")
     blank_slide_layout = prs.slide_layouts[6]
     slide = prs.slides.add_slide(blank_slide_layout)
     txBox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(14), Inches(6))
     tf = txBox.text_frame
     tf.paragraphs[0].text = data.get('titulo_diapositiva', 'Propuesta de Valor')
     tf.paragraphs[0].font.bold = True; tf.paragraphs[0].font.size = Pt(36)
     p = tf.add_paragraph(); p.text = "(Implementación pendiente)"
     p = tf.add_paragraph(); p.text = json.dumps(data, indent=2) # Mostrar el JSON
     return prs

# --- Función Principal ---

def crear_ppt_desde_json(data: dict):
    """
    Función principal que recibe un JSON y genera el archivo .pptx
    basado en el 'template_type' dentro del JSON.
    """
    try:
        template_path = "Plantilla_PPT_ATL.pptx"
        if not os.path.isfile(template_path):
            st.error(f"Error fatal: No se encontró el archivo de plantilla '{template_path}'.")
            return None

        prs = Presentation(template_path)
        prs.slide_width = Inches(16)
        prs.slide_height = Inches(9)

        template_type = data.get("template_type")

        if template_type == "oportunidades":
            prs = _crear_slide_oportunidades(prs, data)
        elif template_type == "dofa":
            prs = _crear_slide_dofa(prs, data)
        elif template_type == "empatia":
            prs = _crear_slide_empatia(prs, data)
        elif template_type == "propuesta_valor":
            prs = _crear_slide_propuesta_valor(prs, data)
        else:
            st.error(f"Error: Tipo de plantilla desconocido '{template_type}' en el JSON.")
            blank_slide_layout = prs.slide_layouts[6]
            slide = prs.slides.add_slide(blank_slide_layout)
            txBox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(14), Inches(6))
            tf = txBox.text_frame; tf.paragraphs[0].text = f"Error: Plantilla '{template_type}' no reconocida"
            p = tf.add_paragraph(); p.text = json.dumps(data, indent=2)

        f = BytesIO()
        prs.save(f)
        f.seek(0)
        return f.getvalue()

    except Exception as e:
        st.error(f"Error crítico al generar el archivo .pptx: {e}")
        st.error("Detalles del error:")
        st.code(traceback.format_exc())
        return None
    
    