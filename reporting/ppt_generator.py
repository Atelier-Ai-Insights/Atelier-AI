from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_AUTO_SIZE 
import io

def crear_ppt_desde_json(data_json, image_stream=None):
    """
    Genera un PowerPoint con formas NATIVAS y EDITABLES.
    Corregido para detectar DOFA/SWOT/FODA robustamente.
    """
    
    # 1. Cargar Plantilla
    try:
        prs = Presentation("Plantilla_PPT_ATL.pptx")
    except:
        prs = Presentation()

    slide_layout = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[-1]
    slide = prs.slides.add_slide(slide_layout)

    # 2. Configurar Título
    if slide.shapes.title:
        slide.shapes.title.text = data_json.get('titulo_diapositiva', 'Resumen Estratégico')
    else:
        title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.2), Inches(9), Inches(1))
        tf = title_box.text_frame
        tf.text = data_json.get('titulo_diapositiva', 'Resumen Estratégico')
        tf.paragraphs[0].font.size = Pt(24)
        tf.paragraphs[0].font.bold = True
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER

    # 3. Detectar Tipo y Dibujar (LÓGICA MEJORADA)
    template_type = data_json.get('template_type', '').lower()
    
    # Normalizamos el string para búsqueda
    if "matriz" in template_type or "2x2" in template_type:
        _dibujar_matriz_nativa(slide, data_json)
    # AQUI AGREGAMOS "dofa" PARA QUE LO RECONOZCA
    elif "foda" in template_type or "swot" in template_type or "dofa" in template_type:
        _dibujar_foda_nativo(slide, data_json)
    elif "embudo" in template_type or "funnel" in template_type:
        _dibujar_embudo_nativo(slide, data_json)
    else:
        _dibujar_lista_generica(slide, data_json)

    # 4. Agregar Conclusión
    if 'conclusion_clave' in data_json:
        bg = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.5), Inches(6.6), Inches(9), Inches(0.8))
        bg.fill.solid()
        bg.fill.fore_color.rgb = RGBColor(245, 245, 245)
        bg.line.color.rgb = RGBColor(220, 220, 220)
        
        tf = bg.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE 
        
        tf.text = "💡 " + data_json['conclusion_clave']
        p = tf.paragraphs[0]
        p.font.color.rgb = RGBColor(50, 50, 50)
        p.alignment = PP_ALIGN.LEFT

    # 5. Guardar
    output = io.BytesIO()
    prs.save(output)
    output.seek(0)
    return output

# ==============================================================================
# FUNCIONES DE DIBUJO
# ==============================================================================

def _get_case_insensitive(data, key):
    """Helper para encontrar claves (ej: 'Fortalezas') aunque estén en mayúsculas."""
    key = key.lower()
    for k, v in data.items():
        if k.lower() == key:
            return v
    return []

def _dibujar_foda_nativo(slide, data):
    """Dibuja matriz DOFA/FODA en 4 cuadrantes con colores."""
    center_x, center_y = 5.0, 3.5
    width, height = 4.0, 2.2
    margin = 0.1

    # Usamos el helper _get_case_insensitive para ser robustos
    fortalezas = _get_case_insensitive(data, 'fortalezas')
    debilidades = _get_case_insensitive(data, 'debilidades')
    oportunidades = _get_case_insensitive(data, 'oportunidades')
    amenazas = _get_case_insensitive(data, 'amenazas')

    configs = [
        (center_x - width - margin, center_y - height - margin, (200, 230, 201), 'FORTALEZAS', fortalezas),    # Verde
        (center_x + margin,         center_y - height - margin, (255, 205, 210), 'DEBILIDADES', debilidades),   # Rojo
        (center_x - width - margin, center_y + margin,          (187, 222, 251), 'OPORTUNIDADES', oportunidades), # Azul
        (center_x + margin,         center_y + margin,          (255, 224, 178), 'AMENAZAS', amenazas)      # Naranja
    ]

    for left, top, color, title, items in configs:
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(*color)
        shape.line.color.rgb = RGBColor(180, 180, 180)
        
        tf = shape.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

        p = tf.paragraphs[0]
        p.text = title
        p.font.bold = True
        p.font.color.rgb = RGBColor(50, 50, 50)
        
        for item in items:
            p = tf.add_paragraph()
            p.text = f"• {item}"
            p.level = 0
            p.font.color.rgb = RGBColor(50, 50, 50)

def _dibujar_matriz_nativa(slide, data):
    center_x, center_y = 5.0, 3.5
    width, height = 4.0, 2.2
    margin = 0.05

    quads = [
        (center_x - width - margin, center_y - height - margin, (227, 242, 253), 'items_cuadrante_sup_izq'),
        (center_x + margin,         center_y - height - margin, (232, 245, 233), 'items_cuadrante_sup_der'),
        (center_x - width - margin, center_y + margin,          (255, 243, 224), 'items_cuadrante_inf_izq'),
        (center_x + margin,         center_y + margin,          (243, 229, 245), 'items_cuadrante_inf_der')
    ]

    for left, top, color, key in quads:
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(*color)
        shape.line.color.rgb = RGBColor(210, 210, 210)
        
        tf = shape.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        
        items = data.get(key, [])
        _llenar_text_frame_flexible(tf, items)

    _crear_etiqueta(slide, center_x, center_y - height - 0.3, data.get('eje_y_positivo', 'Alto'), bold=True)
    _crear_etiqueta(slide, center_x, center_y + height + 0.3, data.get('eje_y_negativo', 'Bajo'), bold=True)
    _crear_etiqueta(slide, center_x - width - 0.3, center_y, data.get('eje_x_negativo', 'Bajo'), bold=True, vertical=True)
    _crear_etiqueta(slide, center_x + width + 0.3, center_y, data.get('eje_x_positivo', 'Alto'), bold=True, vertical=True)


def _dibujar_embudo_nativo(slide, data):
    pasos = data.get('pasos', []) or data.get('etapas', [])
    if not pasos: return
    
    num = len(pasos)
    start_y = 1.5
    total_h = 4.8
    step_h = total_h / num
    max_w = 8.5
    min_w = 3.0
    center_x = 5.0

    for i, paso in enumerate(pasos):
        top_w = max_w - (i * (max_w - min_w) / num)
        
        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, 
            Inches(center_x - top_w/2), Inches(start_y + (i * step_h) + (i*0.05)), 
            Inches(top_w), Inches(step_h)
        )
        
        shape.fill.solid()
        blue_val = max(100, 220 - (i * 30))
        shape.fill.fore_color.rgb = RGBColor(30, 130, blue_val)
        shape.line.fill.background() 

        tf = shape.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

        tf.text = paso
        tf.paragraphs[0].font.color.rgb = RGBColor(255, 255, 255)
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        tf.paragraphs[0].font.bold = True

def _dibujar_lista_generica(slide, data):
    left = Inches(1)
    top = Inches(1.5)
    width = Inches(8)
    height = Inches(4.8)
    
    textbox = slide.shapes.add_textbox(left, top, width, height)
    tf = textbox.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    
    excluded_keys = ['titulo_diapositiva', 'template_type', 'conclusion_clave']
    
    first = True
    for k, v in data.items():
        if k in excluded_keys: continue
        
        if not first: tf.add_paragraph() 
        
        p = tf.add_paragraph() if not first else tf.paragraphs[0]
        p.text = k.replace('_', ' ').upper()
        p.font.bold = True
        p.font.color.rgb = RGBColor(0, 51, 102)
        first = False
        
        if isinstance(v, list):
            for item in v:
                p = tf.add_paragraph()
                p.text = f"• {item}"
                p.level = 1
        else:
            p = tf.add_paragraph()
            p.text = str(v)
            p.level = 1

def _llenar_text_frame_flexible(text_frame, lista_items):
    if not lista_items: return
    p = text_frame.paragraphs[0]
    p.text = f"• {lista_items[0]}"
    p.font.color.rgb = RGBColor(40, 40, 40)
    for item in lista_items[1:]:
        p = text_frame.add_paragraph()
        p.text = f"• {item}"
        p.font.color.rgb = RGBColor(40, 40, 40)

def _crear_etiqueta(slide, x, y, texto, bold=False, vertical=False):
    w, h = (Inches(2), Inches(0.5)) if not vertical else (Inches(0.5), Inches(2))
    x_pos = Inches(x) - w/2
    y_pos = Inches(y) - h/2
    
    tb = slide.shapes.add_textbox(x_pos, y_pos, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    
    p = tf.paragraphs[0]
    p.text = texto
    p.alignment = PP_ALIGN.CENTER
    p.font.bold = bold
    p.font.color.rgb = RGBColor(80, 80, 80)
    if vertical:
         tb.rotation = -90
