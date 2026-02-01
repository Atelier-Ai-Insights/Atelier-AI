import io
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

# --- COLORES CORPORATIVOS ---
COLOR_PRIMARY = RGBColor(0, 51, 102)    # Azul Oscuro
COLOR_ACCENT = RGBColor(255, 102, 0)    # Naranja
COLOR_GRAY = RGBColor(100, 100, 100)    # Gris Texto
COLOR_LIGHT = RGBColor(245, 245, 245)   # Gris Fondo

def create_pptx_from_structure(data):
    """
    Generador Inteligente: Detecta estructura JSON y elige diseño visual.
    """
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    
    # Slide en blanco
    try: slide_layout = prs.slide_layouts[6]
    except: slide_layout = prs.slide_layouts[0]
    
    slide = prs.slides.add_slide(slide_layout)
    
    # Dibujar Cabecera
    _draw_header(slide, data)
    
    # ENRUTADOR INTELIGENTE
    keys = " ".join(data.keys()).lower()
    t_type = data.get("template_type", "").lower()
    
    if "dofa" in t_type or "swot" in t_type or ("fortalezas" in keys and "amenazas" in keys):
        _draw_dofa_layout(slide, data)
    elif "buyer" in t_type or "persona" in t_type or ("perfil" in keys and "dolor" in keys):
        _draw_persona_layout(slide, data)
    elif "journey" in t_type or "viaje" in t_type or "etapa" in keys:
        _draw_journey_table(slide, data)
    elif "matriz" in t_type or "2x2" in t_type:
        _draw_matrix_layout(slide, data)
    else:
        _draw_smart_generic_layout(slide, data)

    # Insight al pie
    if data.get("insight_principal"):
        _draw_footer_insight(slide, data.get("insight_principal"))

    output = io.BytesIO()
    prs.save(output)
    output.seek(0)
    return output

# --- FUNCIONES DE DIBUJO ---
def _draw_header(slide, data):
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(12), Inches(1))
    p = tb.text_frame.paragraphs[0]
    p.text = str(data.get("titulo", "Sin Título")).upper()
    p.font.name = 'Arial'; p.font.size = Pt(32); p.font.bold = True; p.font.color.rgb = COLOR_PRIMARY
    
    if data.get("subtitulo"):
        tb_sub = slide.shapes.add_textbox(Inches(0.5), Inches(1.0), Inches(12), Inches(0.5))
        p_sub = tb_sub.text_frame.paragraphs[0]
        p_sub.text = str(data.get("subtitulo", "")); p_sub.font.size = Pt(14); p_sub.font.color.rgb = COLOR_GRAY

def _draw_dofa_layout(slide, data):
    margin_x, margin_y, w, h, gap = 0.5, 1.8, 6.0, 2.2, 0.2
    quadrants = [("Fortalezas", data.get("fortalezas", []), margin_x, margin_y),
                 ("Debilidades", data.get("debilidades", []), margin_x + w + gap, margin_y),
                 ("Oportunidades", data.get("oportunidades", []), margin_x, margin_y + h + gap),
                 ("Amenazas", data.get("amenazas", []), margin_x + w + gap, margin_y + h + gap)]
    
    for title, points, x, y in quadrants:
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
        shape.fill.solid(); shape.fill.fore_color.rgb = COLOR_LIGHT; shape.line.color.rgb = COLOR_PRIMARY
        
        tb = slide.shapes.add_textbox(Inches(x+0.1), Inches(y+0.1), Inches(w-0.2), Inches(0.5))
        p = tb.text_frame.paragraphs[0]; p.text = title.upper(); p.font.bold = True; p.font.color.rgb = COLOR_ACCENT; p.font.size = Pt(14)
        
        tb_body = slide.shapes.add_textbox(Inches(x+0.1), Inches(y+0.5), Inches(w-0.2), Inches(h-0.6))
        tf = tb_body.text_frame; tf.word_wrap = True
        for point in (points if isinstance(points, list) else [str(points)])[:5]:
            p = tf.add_paragraph(); p.text = f"• {point}"; p.font.size = Pt(11)

def _draw_journey_table(slide, data):
    stages = [v for k, v in data.items() if "etapa" in k.lower() and isinstance(v, dict)]
    if not stages: return _draw_smart_generic_layout(slide, data)
    
    table = slide.shapes.add_table(3, len(stages), Inches(0.5), Inches(2.0), Inches(12.3), Inches(4.0)).table
    for i, stage in enumerate(stages):
        c = table.cell(0, i); c.text = str(stage.get("nombre", f"Etapa {i+1}")).upper(); c.fill.solid(); c.fill.fore_color.rgb = COLOR_PRIMARY; c.text_frame.paragraphs[0].font.color.rgb = RGBColor(255,255,255)
        c = table.cell(1, i); c.text = f"Acción:\n{stage.get('accion', '')}"; c.text_frame.paragraphs[0].font.size = Pt(10)
        c = table.cell(2, i); c.text = f"Piensa:\n{stage.get('pensamiento', '')}"; c.text_frame.paragraphs[0].font.size = Pt(10); c.text_frame.paragraphs[0].font.italic = True

def _draw_persona_layout(slide, data):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(1.8), Inches(3.5), Inches(4.5))
    shape.fill.solid(); shape.fill.fore_color.rgb = COLOR_LIGHT
    tf = shape.text_frame; tf.margin_top = Inches(0.2); p = tf.paragraphs[0]
    p.text = str(data.get("perfil_nombre", "Usuario")).upper(); p.font.bold = True; p.font.color.rgb = COLOR_PRIMARY; p.font.size = Pt(16)
    for d in [f"Bio: {data.get('perfil_demografia', '')}", f"Edad: {data.get('edad', '')}", f"Ocupación: {data.get('ocupacion', '')}"]:
        p = tf.add_paragraph(); p.text = d; p.font.size = Pt(11); p.space_after = Pt(6)

    tb1 = slide.shapes.add_textbox(Inches(4.2), Inches(1.8), Inches(8.5), Inches(2.0))
    p1 = tb1.text_frame.paragraphs[0]; p1.text = "NECESIDADES"; p1.font.bold = True; p1.font.color.rgb = COLOR_ACCENT
    for n in (data.get("necesidades_jtbd", []) + data.get("deseos_motivaciones", []))[:4]:
        p = tb1.text_frame.add_paragraph(); p.text = f"• {n}"

    tb2 = slide.shapes.add_textbox(Inches(4.2), Inches(4.0), Inches(8.5), Inches(2.0))
    p2 = tb2.text_frame.paragraphs[0]; p2.text = "FRUSTRACIONES"; p2.font.bold = True; p2.font.color.rgb = COLOR_ACCENT
    for pn in data.get("puntos_dolor_frustraciones", [])[:4]:
        p = tb2.text_frame.add_paragraph(); p.text = f"• {pn}"

def _draw_matrix_layout(slide, data):
    _draw_smart_generic_layout(slide, data) # Placeholder para brevedad, usa genérico inteligente si no hay lógica matriz

def _draw_smart_generic_layout(slide, data):
    ignore = ["titulo", "subtitulo", "insight_principal", "template_type", "titulo_diapositiva"]
    keys = [k for k in data.keys() if k not in ignore]
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(1.8), Inches(12), Inches(4.5)); tf = tb.text_frame; tf.word_wrap = True
    for first, key in enumerate(keys):
        if not data[key]: continue
        p = tf.add_paragraph() if first else tf.paragraphs[0]; p.text = key.replace("_", " ").upper(); p.font.bold = True; p.font.color.rgb = COLOR_PRIMARY
        for item in (data[key] if isinstance(data[key], list) else [str(data[key])]):
            b = tf.add_paragraph(); b.text = f"• {item}"; b.font.size = Pt(11)

def _draw_footer_insight(slide, text):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.5), Inches(6.5), Inches(12.33), Inches(0.8))
    shape.fill.solid(); shape.fill.fore_color.rgb = RGBColor(255, 240, 230); shape.line.color.rgb = COLOR_ACCENT
    p = shape.text_frame.paragraphs[0]; p.text = f"💡 INSIGHT: {text}"; p.font.color.rgb = RGBColor(50, 50, 50); p.font.size = Pt(12); p.alignment = PP_ALIGN.CENTER
