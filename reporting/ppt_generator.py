import json
import traceback
from io import BytesIO
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_AUTO_SIZE
from pptx.dml.color import RGBColor

# ==============================
# CONFIGURACIÓN DE ESTILOS GLOBALES
# ==============================
# Definimos constantes para mantener consistencia visual en todo el reporte
TITLE_FONT_SIZE = Pt(32)
SUBTITLE_FONT_SIZE = Pt(20)
BODY_FONT_SIZE = Pt(12)
HEADER_FONT_SIZE = Pt(16)

# Colores corporativos (aproximados al estilo Atelier)
COLOR_BLACK = RGBColor(0x00, 0x00, 0x00)
COLOR_DARK_GRAY = RGBColor(0x33, 0x33, 0x33)
COLOR_BLUE_ACCENT = RGBColor(0x00, 0x33, 0x66)

# Dimensiones estándar para diapositiva 16:9
SLIDE_WIDTH = Inches(16)
SLIDE_HEIGHT = Inches(9)

# ==============================
# FUNCIONES DE UTILIDAD (CORE)
# ==============================

def _add_text_box(slide, text, left, top, width, height, font_size=BODY_FONT_SIZE, is_bold=False, alignment=PP_ALIGN.LEFT, color=COLOR_BLACK):
    """
    Función universal para crear cajas de texto con estilo consistente.
    Elimina la repetición de código para configurar fuentes y párrafos.
    """
    shape = slide.shapes.add_textbox(left, top, width, height)
    tf = shape.text_frame
    tf.word_wrap = True
    # Ajustar forma al texto si es necesario, o viceversa. 
    # SHAPE_TO_FIT_TEXT ajusta la caja al contenido.
    tf.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT
    
    p = tf.paragraphs[0]
    p.text = str(text) if text else ""
    p.font.size = font_size
    p.font.bold = is_bold
    p.font.color.rgb = color
    p.alignment = alignment
    
    return tf

def _add_bullet_points(text_frame, items, level=0, font_size=BODY_FONT_SIZE):
    """
    Agrega una lista de viñetas a un text_frame existente.
    Maneja la lógica de si el cuadro está vacío o ya tiene texto.
    """
    if not items: return
    
    # Si es el primer párrafo y está vacío, lo usamos. Si no, agregamos uno nuevo.
    start_idx = 0 if (len(text_frame.paragraphs) == 1 and not text_frame.paragraphs[0].text) else 1
    
    # Si agregamos, iteramos sobre los items
    first = True
    for item in items:
        if first and start_idx == 0:
            p = text_frame.paragraphs[0]
            first = False
        else:
            p = text_frame.add_paragraph()
        
        p.text = str(item)
        p.font.size = font_size
        p.level = level
        p.space_after = Pt(6) # Espacio entre bullets

def _create_quadrant(slide, title, items, left, top, width, height):
    """
    Crea un bloque visual estándar (Título + Lista de Items).
    Muy usado en matrices, DOFA, Mapas de Empatía.
    """
    # 1. Título del cuadrante (Header)
    _add_text_box(slide, title, left, top, width, Inches(0.5), 
                  font_size=HEADER_FONT_SIZE, is_bold=True, alignment=PP_ALIGN.CENTER, color=COLOR_DARK_GRAY)
    
    # 2. Contenido (Lista) debajo del título
    content_top = top + Inches(0.6)
    tf = _add_text_box(slide, "", left, content_top, width, height - Inches(0.6), font_size=BODY_FONT_SIZE)
    
    # Llenar lista
    if items:
        _add_bullet_points(tf, items, font_size=BODY_FONT_SIZE)
    else:
        tf.paragraphs[0].text = "N/A"

# ==============================
# CONSTRUCTORES DE DIAPOSITIVAS
# ==============================

def _slide_oportunidades(prs, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6]) # Blank layout
    
    # Título Principal
    _add_text_box(slide, data.get("titulo_diapositiva", "Oportunidades"), Inches(1), Inches(0.5), Inches(14), Inches(1), 
                  font_size=TITLE_FONT_SIZE, is_bold=True, alignment=PP_ALIGN.CENTER)
    
    # Insight Clave (Destacado)
    _add_text_box(slide, f"Insight: {data.get('insight_clave', '')}", Inches(1), Inches(1.5), Inches(14), Inches(1), 
                  font_size=Pt(18), is_bold=True, color=COLOR_BLUE_ACCENT)
    
    # Definición de Columnas
    y_start = Inches(2.8)
    col_w = Inches(4.5)
    gap = Inches(0.25)
    x1 = Inches(1)
    x2 = x1 + col_w + gap
    x3 = x2 + col_w + gap
    
    # Columna 1: Hallazgos
    _add_text_box(slide, "Hallazgos Principales", x1, y_start, col_w, Inches(0.5), font_size=SUBTITLE_FONT_SIZE, is_bold=True)
    tf_h = _add_text_box(slide, "", x1, y_start + Inches(0.7), col_w, Inches(4))
    _add_bullet_points(tf_h, data.get("hallazgos_principales", []))
    
    # Columna 2: Oportunidades
    _add_text_box(slide, "Oportunidades", x2, y_start, col_w, Inches(0.5), font_size=SUBTITLE_FONT_SIZE, is_bold=True)
    tf_o = _add_text_box(slide, "", x2, y_start + Inches(0.7), col_w, Inches(4))
    _add_bullet_points(tf_o, data.get("oportunidades", []))
    
    # Columna 3: Recomendación
    _add_text_box(slide, "Recomendación", x3, y_start, col_w, Inches(0.5), font_size=SUBTITLE_FONT_SIZE, is_bold=True)
    tf_r = _add_text_box(slide, "", x3, y_start + Inches(0.7), col_w, Inches(4))
    rec = data.get("recomendacion_estrategica", "")
    _add_bullet_points(tf_r, [rec] if isinstance(rec, str) else rec)
    
    return prs

def _slide_dofa(prs, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    
    _add_text_box(slide, data.get("titulo_diapositiva", "Análisis DOFA"), Inches(1), Inches(0.5), Inches(14), Inches(1), 
                  font_size=TITLE_FONT_SIZE, is_bold=True, alignment=PP_ALIGN.CENTER)
    
    # Matriz 2x2 centrada
    center_x = SLIDE_WIDTH / 2
    center_y = (SLIDE_HEIGHT / 2) + Inches(0.5)
    box_w = Inches(6.5)
    box_h = Inches(3.2)
    gap = Inches(0.5)
    
    # Coordenadas: [Arriba-Izq, Arriba-Der, Abajo-Izq, Abajo-Der]
    _create_quadrant(slide, "Fortalezas", data.get("fortalezas"), center_x - box_w - (gap/2), center_y - box_h - (gap/2), box_w, box_h)
    _create_quadrant(slide, "Oportunidades", data.get("oportunidades"), center_x + (gap/2), center_y - box_h - (gap/2), box_w, box_h)
    _create_quadrant(slide, "Debilidades", data.get("debilidades"), center_x - box_w - (gap/2), center_y + (gap/2), box_w, box_h)
    _create_quadrant(slide, "Amenazas", data.get("amenazas"), center_x + (gap/2), center_y + (gap/2), box_w, box_h)
    
    return prs

def _slide_empatia(prs, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_text_box(slide, data.get("titulo_diapositiva", "Mapa de Empatía"), Inches(1), Inches(0.5), Inches(14), Inches(1), 
                  font_size=TITLE_FONT_SIZE, is_bold=True, alignment=PP_ALIGN.CENTER)
    
    # Diseño: 2 arriba, 2 medio, 2 abajo
    top_y = Inches(1.5); mid_y = Inches(4.0); bot_y = Inches(6.5)
    left_x = Inches(1); right_x = Inches(8.5)
    w = Inches(6.5); h = Inches(2.2)
    
    _create_quadrant(slide, "Piensa y Siente", data.get("piensa_siente"), left_x, top_y, w, h)
    _create_quadrant(slide, "Ve", data.get("ve"), right_x, top_y, w, h)
    _create_quadrant(slide, "Dice y Hace", data.get("dice_hace", data.get("dice_ace")), left_x, mid_y, w, h)
    _create_quadrant(slide, "Oye", data.get("oye"), right_x, mid_y, w, h)
    _create_quadrant(slide, "Esfuerzos", data.get("esfuerzos"), left_x, bot_y, w, h)
    _create_quadrant(slide, "Resultados", data.get("resultados"), right_x, bot_y, w, h)
    
    return prs

def _slide_buyer_persona(prs, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_text_box(slide, data.get("titulo_diapositiva", "Buyer Persona"), Inches(1), Inches(0.5), Inches(14), Inches(1), 
                  font_size=TITLE_FONT_SIZE, is_bold=True, alignment=PP_ALIGN.CENTER)
    
    # Panel Izquierdo: Identidad
    _add_text_box(slide, data.get("perfil_nombre", "Nombre"), Inches(1), Inches(2), Inches(4), Inches(1), 
                  font_size=Pt(26), is_bold=True, color=COLOR_BLUE_ACCENT)
    _add_text_box(slide, data.get("perfil_demografia", ""), Inches(1), Inches(3), Inches(4), Inches(4), 
                  font_size=Pt(14), is_bold=False)
    
    # Panel Derecho: Matriz de detalles (2x2)
    r_x = Inches(5.5); r_w = Inches(4.8); r_h = Inches(3)
    
    _create_quadrant(slide, "Necesidades / JTBD", data.get("necesidades_jtbd"), r_x, Inches(2), r_w, r_h)
    _create_quadrant(slide, "Deseos", data.get("deseos_motivaciones"), r_x + r_w + Inches(0.2), Inches(2), r_w, r_h)
    _create_quadrant(slide, "Puntos de Dolor", data.get("puntos_dolor_frustraciones"), r_x, Inches(5.2), r_w, r_h)
    _create_quadrant(slide, "Citas Clave", data.get("citas_clave"), r_x + r_w + Inches(0.2), Inches(5.2), r_w, r_h)

    return prs

def _slide_journey_map(prs, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_text_box(slide, data.get("titulo_diapositiva", "Journey Map"), Inches(1), Inches(0.5), Inches(14), Inches(1), 
                  font_size=TITLE_FONT_SIZE, is_bold=True, alignment=PP_ALIGN.CENTER)
    
    # 4 Columnas
    col_w = Inches(3.5); gap = Inches(0.2); start_x = Inches(0.8); top_y = Inches(1.5)
    
    for i, key in enumerate(["etapa_1", "etapa_2", "etapa_3", "etapa_4"]):
        stage = data.get(key, {})
        x_pos = start_x + (i * (col_w + gap))
        
        # Título Etapa
        _add_text_box(slide, stage.get("nombre_etapa", f"Etapa {i+1}"), x_pos, top_y, col_w, Inches(0.5), 
                      font_size=HEADER_FONT_SIZE, is_bold=True, alignment=PP_ALIGN.CENTER, color=COLOR_BLUE_ACCENT)
        
        # Contenido
        content_y = top_y + Inches(0.6)
        tf = _add_text_box(slide, "", x_pos, content_y, col_w, Inches(6))
        
        # Función local para añadir secciones dentro de la columna
        def add_sec(title, items):
            p = tf.add_paragraph(); p.text = title; p.font.bold = True; p.font.size = Pt(11)
            for item in items:
                p = tf.add_paragraph(); p.text = f"• {item}"; p.font.size = Pt(10); p.level = 0
            tf.add_paragraph() # Espacio vacio
            
        add_sec("Acciones", stage.get("acciones", []))
        add_sec("Emociones", stage.get("emociones", []))
        add_sec("Puntos Dolor", stage.get("puntos_dolor", []))
        add_sec("Oportunidades", stage.get("oportunidades", []))

    return prs

# ==============================
# ENRUTADOR PRINCIPAL
# ==============================

def crear_ppt_desde_json(data: dict):
    """
    Función principal: Recibe JSON, devuelve bytes PPTX.
    """
    try:
        template_path = "Plantilla_PPT_ATL.pptx"
        if os.path.isfile(template_path):
            prs = Presentation(template_path)
        else:
            prs = Presentation() # Crea una en blanco si no hay plantilla
            
        # Ajuste forzado a 16:9
        prs.slide_width = SLIDE_WIDTH
        prs.slide_height = SLIDE_HEIGHT

        t_type = data.get("template_type", "")

        # Mapeo simple de tipo -> función
        if t_type == "oportunidades":
            prs = _slide_oportunidades(prs, data)
        elif t_type == "dofa":
            prs = _slide_dofa(prs, data)
        elif t_type == "empatia":
            prs = _slide_empatia(prs, data)
        elif t_type == "buyer_persona":
            prs = _slide_buyer_persona(prs, data)
        elif t_type == "journey_map":
            prs = _slide_journey_map(prs, data)
        # Puedes agregar más `elif` aquí para Propuesta de Valor, Matriz 2x2, etc.
        # Usando los helpers existentes es muy rápido.
        else:
            # Fallback genérico por si el tipo no coincide
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            _add_text_box(slide, f"Plantilla: {t_type}", Inches(1), Inches(1), Inches(10), Inches(1), font_size=TITLE_FONT_SIZE)
            _add_text_box(slide, json.dumps(data, indent=2)[:2000], Inches(1), Inches(2.5), Inches(14), Inches(5), font_size=Pt(10))

        f = BytesIO()
        prs.save(f)
        f.seek(0)
        return f.getvalue()

    except Exception as e:
        print(f"Error crítico generando PPT: {e}")
        traceback.print_exc()
        return None
