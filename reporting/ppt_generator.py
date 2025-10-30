import json
import streamlit as st
from io import BytesIO
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_AUTO_SIZE
from pptx.dml.color import RGBColor
import os
import traceback

# --- Funciones de Ayuda para Dibujar (CON ARREGLOS) ---

def _crear_cuadrante_ppt(slide, left, top, width, height, title, items, title_size=Pt(22), item_size=Pt(12)): # Reducido a Pt(12)
    """Añade un cuadro de texto con título y viñetas a una diapositiva."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    
    # --- ¡ARREGLO DE DISEÑO! ---
    # Activa el auto-ajuste para que el texto no se desborde
    tf.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT 
    
    # Título del cuadrante
    p_title = tf.paragraphs[0]
    p_title.text = title
    p_title.font.bold = True
    p_title.font.size = title_size
    p_title.space_after = Pt(6)
    
    # Contenido (viñetas)
    if not items:
        items = ["N/A"]
        
    for item in items:
        p_item = tf.add_paragraph()
        p_item.text = item
        p_item.font.size = item_size
        p_item.level = 1
        p_item.space_after = Pt(4)

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
    tf_content.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT # Añadido por si acaso

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
    p_title.text = data.get("Análisis DOFA", ["N/A"])
    p_title.font.bold = True; p_title.font.size = Pt(40); p_title.alignment = PP_ALIGN.CENTER
    txBox_title.text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT

    # --- Contenido en dos columnas ---
    col1_left = Inches(1); col_width = Inches(6.5); col_top = Inches(1.8); col_height = Inches(6.8) # Un poco más de alto
    col2_left = Inches(1) + col_width + Inches(1)

    # Columna Izquierda (Fortalezas y Debilidades)
    _crear_cuadrante_ppt(slide, col1_left, col_top, col_width, col_height / 2.1, "Fortalezas (+ Interno)", data.get("fortalezas"), title_size=Pt(20), item_size=Pt(12))
    _crear_cuadrante_ppt(slide, col1_left, col_top + (col_height / 2) + Inches(0.1), col_width, col_height / 2.1, "Debilidades (- Interno)", data.get("debilidades"), title_size=Pt(20), item_size=Pt(12))

    # Columna Derecha (Oportunidades y Amenazas)
    _crear_cuadrante_ppt(slide, col2_left, col_top, col_width, col_height / 2.1, "Oportunidades (+ Externo)", data.get("oportunidades"), title_size=Pt(20), item_size=Pt(12))
    _crear_cuadrante_ppt(slide, col2_left, col_top + (col_height / 2) + Inches(0.1), col_width, col_height / 2.1, "Amenazas (- Externo)", data.get("amenazas"), title_size=Pt(20), item_size=Pt(12))

    return prs

def _crear_slide_empatia(prs, data):
    """Crea la diapositiva de Mapa de Empatía. (DISEÑO ARREGLADO)"""
    blank_slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_slide_layout)

    # Título
    txBox_title = slide.shapes.add_textbox(Inches(1), Inches(0.2), Inches(14), Inches(0.8))
    p_title = txBox_title.text_frame.paragraphs[0]
    p_title.text = data.get("Mapa de Empatía", ["N/A"])
    p_title.font.bold = True; p_title.font.size = Pt(36); p_title.alignment = PP_ALIGN.CENTER
    txBox_title.text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT
    
    # --- ARREGLO DE DISEÑO (Nuevas Coordenadas) ---
    top_y = Inches(1.0); box_w = Inches(7); box_h = Inches(2.8) # Cajas más bajas
    left_x = Inches(0.5); right_x = Inches(8.5)
    
    _crear_cuadrante_ppt(slide, left_x, top_y, box_w, box_h, "Piensa y Siente", data.get("piensa_siente"), title_size=Pt(20), item_size=Pt(12))
    _crear_cuadrante_ppt(slide, right_x, top_y, box_w, box_h, "Ve", data.get("ve"), title_size=Pt(20), item_size=Pt(12))

    # --- Cuadrantes Medios ---
    mid_y = top_y + box_h + Inches(0.2) # Espacio reducido
    _crear_cuadrante_ppt(slide, left_x, mid_y, box_w, box_h, "Dice y Hace", data.get("dice_hace"), title_size=Pt(20), item_size=Pt(12))
    _crear_cuadrante_ppt(slide, right_x, mid_y, box_w, box_h, "Oye", data.get("oye"), title_size=Pt(20), item_size=Pt(12))

    # --- Secciones Inferiores (Pains/Gains) ---
    bottom_y = mid_y + box_h + Inches(0.2) # Espacio reducido
    bottom_h = Inches(1.8) # Un poco más de alto
    _crear_cuadrante_ppt(slide, left_x, bottom_y, box_w, bottom_h, "Esfuerzos (Pains)", data.get("esfuerzos"), title_size=Pt(18), item_size=Pt(12))
    _crear_cuadrante_ppt(slide, right_x, bottom_y, box_w, bottom_h, "Resultados (Gains)", data.get("resultados"), title_size=Pt(18), item_size=Pt(12))

    return prs

def _crear_slide_propuesta_valor(prs, data):
    """Crea las DOS diapositivas de Propuesta de Valor. (DISEÑO ARREGLADO)"""
    blank_slide_layout = prs.slide_layouts[6]
    
    # --- Diapositiva 1: Perfil del Cliente ---
    slide1 = prs.slides.add_slide(blank_slide_layout)
    
    # Título
    txBox_title1 = slide1.shapes.add_textbox(Inches(1), Inches(0.5), Inches(14), Inches(1))
    p_title1 = txBox_title1.text_frame.paragraphs[0]
    p_title1.text = data.get("Propuesta de Valor", ["N/A"]) + ": Perfil del Cliente"
    p_title1.font.bold = True; p_title1.font.size = Pt(40); p_title1.alignment = PP_ALIGN.CENTER
    txBox_title1.text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT

    # Columnas
    col_w = Inches(5); col_h = Inches(6.5); col_y = Inches(1.8)
    _crear_cuadrante_ppt(slide1, Inches(0.5), col_y, col_w, col_h, "Trabajos del Cliente", data.get("trabajos_cliente"), title_size=Pt(20), item_size=Pt(12))
    _crear_cuadrante_ppt(slide1, Inches(5.5), col_y, col_w, col_h, "Alegrías (Gains)", data.get("alegrias"), title_size=Pt(20), item_size=Pt(12))
    _crear_cuadrante_ppt(slide1, Inches(10.5), col_y, col_w, col_h, "Frustraciones (Pains)", data.get("frustraciones"), title_size=Pt(20), item_size=Pt(12))

    # --- Diapositiva 2: Mapa de Valor ---
    slide2 = prs.slides.add_slide(blank_slide_layout)

    # Título
    txBox_title2 = slide2.shapes.add_textbox(Inches(1), Inches(0.5), Inches(14), Inches(1))
    p_title2 = txBox_title2.text_frame.paragraphs[0]
    p_title2.text = data.get("Propuesta de Valor", ["N/A"]) + ": Mapa de Valor"
    p_title2.font.bold = True; p_title2.font.size = Pt(40); p_title2.alignment = PP_ALIGN.CENTER
    txBox_title2.text_frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT

    # Columnas
    # Convertimos producto_servicio a lista para que el helper lo dibuje como viñeta
    producto_lista = [data.get("producto_servicio", "N/A")]
    
    _crear_cuadrante_ppt(slide2, Inches(0.5), col_y, col_w, col_h, "Producto/Servicio", producto_lista, title_size=Pt(20), item_size=Pt(12))
    _crear_cuadrante_ppt(slide2, Inches(5.5), col_y, col_w, col_h, "Creadores de Alegría", data.get("creadores_alegria"), title_size=Pt(20), item_size=Pt(12))
    _crear_cuadrante_ppt(slide2, Inches(10.5), col_y, col_w, col_h, "Aliviadores de Frustración", data.get("aliviadores_frustracion"), title_size=Pt(20), item_size=Pt(12))

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