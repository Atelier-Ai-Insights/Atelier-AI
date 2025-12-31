from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_AUTO_SIZE
import io
import re

def crear_ppt_desde_json(data_json, image_stream=None):
    """
    Genera un PowerPoint con formas NATIVAS y EDITABLES basado en el JSON.
    Soporta: Matriz 2x2, FODA, Embudo, Journey Map, Buyer Persona, Mapa Empatía y Propuesta Valor.
    """
    
    # 1. Cargar Plantilla Base
    try:
        prs = Presentation("Plantilla_PPT_ATL.pptx")
    except:
        prs = Presentation()

    slide_layout = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[-1]
    slide = prs.slides.add_slide(slide_layout)

    # 2. Configurar Título
    titulo_texto = data_json.get('titulo_diapositiva', 'Resumen Estratégico')
    
    if slide.shapes.title:
        slide.shapes.title.text = titulo_texto
    else:
        title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.2), Inches(9), Inches(1))
        tf = title_box.text_frame
        tf.text = titulo_texto
        tf.paragraphs[0].font.size = Pt(24)
        tf.paragraphs[0].font.bold = True
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER

    # 3. Router de Plantillas (Detectar Tipo y Dibujar)
    template_type = data_json.get('template_type', '').lower()
    
    # --- Lógica de Selección ---
    if "matriz" in template_type or "2x2" in template_type:
        _dibujar_matriz_nativa(slide, data_json)
        
    elif "foda" in template_type or "swot" in template_type or "dofa" in template_type:
        _dibujar_foda_nativo(slide, data_json)
        
    elif "embudo" in template_type or "funnel" in template_type:
        _dibujar_embudo_nativo(slide, data_json)
        
    elif "journey" in template_type or "viaje" in template_type or "map" in template_type:
        _dibujar_journey_nativo(slide, data_json)
        
    # --- NUEVAS PLANTILLAS ---
    elif "persona" in template_type or "buyer" in template_type or "cliente" in template_type:
        _dibujar_buyer_persona_nativo(slide, data_json)
        
    elif "empatia" in template_type or "empathy" in template_type:
        _dibujar_mapa_empatia_nativo(slide, data_json)
        
    elif "valor" in template_type or "value" in template_type or "canvas" in template_type:
        _dibujar_propuesta_valor_nativo(slide, data_json)
        
    else:
        _dibujar_lista_generica(slide, data_json)

    # 4. Agregar Conclusión (Común a todos)
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

    # 5. Guardar y Retornar
    output = io.BytesIO()
    prs.save(output)
    output.seek(0)
    return output


# ==============================================================================
# FUNCIONES DE DIBUJO (NUEVAS Y EXISTENTES)
# ==============================================================================

def _dibujar_buyer_persona_nativo(slide, data):
    """
    Diseño de Tarjeta de Perfil:
    - Izquierda: Barra lateral (Avatar + Bio + Demográficos)
    - Derecha: Paneles principales (Metas, Frustraciones, Comportamiento)
    """
    # 1. Barra Lateral (Izquierda)
    sidebar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(1.2), Inches(2.5), Inches(5.2))
    sidebar.fill.solid()
    sidebar.fill.fore_color.rgb = RGBColor(230, 240, 250) # Azul muy pálido
    sidebar.line.fill.background()

    # Avatar (Placeholder)
    avatar = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(1.0), Inches(1.4), Inches(1.5), Inches(1.5))
    avatar.fill.solid()
    avatar.fill.fore_color.rgb = RGBColor(180, 200, 220)
    avatar.line.color.rgb = RGBColor(255, 255, 255)
    
    # Nombre del Persona
    nombre = _get_case_insensitive_val(data, 'nombre') or "Nombre del Persona"
    tb_name = slide.shapes.add_textbox(Inches(0.6), Inches(3.0), Inches(2.3), Inches(0.5))
    p = tb_name.text_frame.paragraphs[0]
    p.text = str(nombre)
    p.font.bold = True
    p.font.size = Pt(14)
    p.alignment = PP_ALIGN.CENTER
    p.font.color.rgb = RGBColor(0, 51, 102)

    # Datos Demográficos / Bio (En la barra lateral)
    bio_text = []
    demos = _get_case_insensitive(data, 'demograficos') or _get_case_insensitive(data, 'perfil')
    if demos: 
        if isinstance(demos, list): bio_text.extend(demos)
        else: bio_text.append(str(demos))
    
    role = _get_case_insensitive_val(data, 'rol') or _get_case_insensitive_val(data, 'trabajo')
    if role and role != "-": bio_text.insert(0, f"Rol: {role}")

    if bio_text:
        tb_bio = slide.shapes.add_textbox(Inches(0.6), Inches(3.5), Inches(2.3), Inches(2.8))
        tf_bio = tb_bio.text_frame
        tf_bio.word_wrap = True
        tf_bio.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        _llenar_text_frame_flexible(tf_bio, bio_text)

    # 2. Paneles Principales (Derecha)
    # Definimos 3 secciones horizontales
    sections = [
        ("METAS / OBJETIVOS", _get_case_insensitive(data, 'metas') or _get_case_insensitive(data, 'objetivos'), (232, 245, 233)), # Verde claro
        ("FRUSTRACIONES / DOLORES", _get_case_insensitive(data, 'frustraciones') or _get_case_insensitive(data, 'dolores'), (255, 235, 238)), # Rojo claro
        ("COMPORTAMIENTO / NECESIDADES", _get_case_insensitive(data, 'comportamiento') or _get_case_insensitive(data, 'necesidades'), (255, 248, 225)) # Amarillo claro
    ]
    
    start_y = 1.2
    h_panel = 1.6
    gap = 0.2
    
    for i, (title, content, color) in enumerate(sections):
        y_pos = start_y + (i * (h_panel + gap))
        
        # Caja de fondo
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(3.2), Inches(y_pos), Inches(6.3), Inches(h_panel))
        box.fill.solid()
        box.fill.fore_color.rgb = RGBColor(*color)
        box.line.color.rgb = RGBColor(200, 200, 200)
        
        # Título Sección
        tb_title = slide.shapes.add_textbox(Inches(3.3), Inches(y_pos + 0.1), Inches(6.0), Inches(0.3))
        p = tb_title.text_frame.paragraphs[0]
        p.text = title
        p.font.bold = True
        p.font.size = Pt(10)
        p.font.color.rgb = RGBColor(80, 80, 80)
        
        # Contenido
        tb_content = slide.shapes.add_textbox(Inches(3.3), Inches(y_pos + 0.4), Inches(6.0), Inches(h_panel - 0.5))
        tf = tb_content.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        _llenar_text_frame_flexible(tf, content)


def _dibujar_mapa_empatia_nativo(slide, data):
    """Diseño en X o 4 Cuadrantes para Mapa de Empatía."""
    center_x, center_y = 5.0, 3.8
    w, h = 4.0, 2.2 # Ancho/Alto de cada cuadrante
    margin = 0.05
    
    # Mapeo de cuadrantes
    # Sup Izq: DICE, Sup Der: PIENSA, Inf Izq: HACE, Inf Der: SIENTE
    quads = [
        (center_x - w - margin, center_y - h - margin, "DICE", _get_case_insensitive(data, 'dice'), (227, 242, 253)),
        (center_x + margin, center_y - h - margin, "PIENSA", _get_case_insensitive(data, 'piensa'), (243, 229, 245)),
        (center_x - w - margin, center_y + margin, "HACE", _get_case_insensitive(data, 'hace'), (232, 245, 233)),
        (center_x + margin, center_y + margin, "SIENTE", _get_case_insensitive(data, 'siente'), (255, 243, 224))
    ]
    
    for left, top, title, content, color in quads:
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(w), Inches(h))
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(*color)
        shape.line.color.rgb = RGBColor(200, 200, 200)
        
        # Título
        tb_title = slide.shapes.add_textbox(Inches(left), Inches(top + 0.1), Inches(w), Inches(0.3))
        p = tb_title.text_frame.paragraphs[0]
        p.text = f"¿QUÉ {title}?"
        p.font.bold = True
        p.alignment = PP_ALIGN.CENTER
        p.font.size = Pt(11)
        p.font.color.rgb = RGBColor(80, 80, 80)
        
        # Contenido
        tb_cont = slide.shapes.add_textbox(Inches(left + 0.2), Inches(top + 0.4), Inches(w - 0.4), Inches(h - 0.5))
        tf = tb_cont.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        _llenar_text_frame_flexible(tf, content)
        
    # Icono central (Círculo decorativo)
    center_circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(center_x - 0.5), Inches(center_y - 0.5), Inches(1), Inches(1))
    center_circle.fill.solid()
    center_circle.fill.fore_color.rgb = RGBColor(255, 255, 255)
    center_circle.line.color.rgb = RGBColor(100, 100, 100)
    p = center_circle.text_frame.paragraphs[0]
    p.text = "👤"
    p.font.size = Pt(24)
    p.alignment = PP_ALIGN.CENTER


def _dibujar_propuesta_valor_nativo(slide, data):
    """Recreación del Canvas de Propuesta de Valor (Cuadrado Producto vs Círculo Cliente)."""
    
    # --- LADO PRODUCTO (Izquierda - Cuadrado) ---
    # Título General
    tb_prod = slide.shapes.add_textbox(Inches(0.5), Inches(1.2), Inches(4.0), Inches(0.3))
    tb_prod.text_frame.text = "MAPA DE VALOR (Producto)"
    tb_prod.text_frame.paragraphs[0].font.bold = True
    
    # 1. Productos y Servicios (Izquierda Centro)
    s_prod = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(2.5), Inches(1.5), Inches(3.0))
    s_prod.fill.solid(); s_prod.fill.fore_color.rgb = RGBColor(220, 220, 220)
    _poner_titulo_contenido(slide, s_prod, "Productos", _get_case_insensitive(data, 'productos') or _get_case_insensitive(data, 'servicios'))

    # 2. Creadores de Alegrías (Arriba)
    s_gain_c = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(2.1), Inches(1.5), Inches(2.4), Inches(1.9))
    s_gain_c.fill.solid(); s_gain_c.fill.fore_color.rgb = RGBColor(200, 230, 201) # Verde suave
    _poner_titulo_contenido(slide, s_gain_c, "Creadores de Alegrías", _get_case_insensitive(data, 'creadores_alegrias'))

    # 3. Aliviadores de Dolor (Abajo)
    s_pain_r = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(2.1), Inches(3.5), Inches(2.4), Inches(2.0))
    s_pain_r.fill.solid(); s_pain_r.fill.fore_color.rgb = RGBColor(255, 205, 210) # Rojo suave
    _poner_titulo_contenido(slide, s_pain_r, "Aliviadores de Dolor", _get_case_insensitive(data, 'aliviadores') or _get_case_insensitive(data, 'aliviadores_dolor'))


    # --- LADO CLIENTE (Derecha - Círculo Implícito) ---
    # Título General
    tb_cust = slide.shapes.add_textbox(Inches(5.0), Inches(1.2), Inches(4.0), Inches(0.3))
    p = tb_cust.text_frame.paragraphs[0]
    p.text = "PERFIL DEL CLIENTE"; p.font.bold = True; p.alignment = PP_ALIGN.RIGHT

    # 4. Alegrías (Gains) - Arriba
    s_gains = slide.shapes.add_shape(MSO_SHAPE.CHORD, Inches(5.0), Inches(1.5), Inches(4.0), Inches(2.0))
    s_gains.rotation = 180 # Para que parezca un sector superior
    s_gains.adjustments[0] = 180 # Ajuste de forma para parecer sector circular
    s_gains.fill.solid(); s_gains.fill.fore_color.rgb = RGBColor(200, 230, 201)
    # Corrección de rotación de texto manual
    _poner_titulo_contenido_manual(slide, 5.5, 1.6, 3.0, 1.5, "Alegrías (Gains)", _get_case_insensitive(data, 'alegrias') or _get_case_insensitive(data, 'gains'))

    # 5. Dolores (Pains) - Abajo
    s_pains = slide.shapes.add_shape(MSO_SHAPE.CHORD, Inches(5.0), Inches(3.5), Inches(4.0), Inches(2.0))
    # s_pains no necesita rotación si es la parte de abajo por defecto o ajuste
    s_pains.fill.solid(); s_pains.fill.fore_color.rgb = RGBColor(255, 205, 210)
    _poner_titulo_contenido_manual(slide, 5.5, 3.8, 3.0, 1.5, "Dolores (Pains)", _get_case_insensitive(data, 'dolores') or _get_case_insensitive(data, 'pains') or _get_case_insensitive(data, 'frustraciones'))

    # 6. Trabajos del Cliente (Jobs) - Derecha
    s_jobs = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(8.2), Inches(2.5), Inches(1.3), Inches(2.0))
    s_jobs.fill.solid(); s_jobs.fill.fore_color.rgb = RGBColor(220, 220, 220)
    _poner_titulo_contenido(slide, s_jobs, "Trabajos (Jobs)", _get_case_insensitive(data, 'trabajos') or _get_case_insensitive(data, 'jobs') or _get_case_insensitive(data, 'acciones'))


# --- FUNCIONES DE DIBUJO EXISTENTES (MATRIZ, FODA, EMBUDO, JOURNEY) ---

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
        shape.fill.solid(); shape.fill.fore_color.rgb = RGBColor(*color); shape.line.color.rgb = RGBColor(210, 210, 210)
        tf = shape.text_frame; tf.word_wrap = True; tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        _llenar_text_frame_flexible(tf, data.get(key, []))
    _crear_etiqueta(slide, center_x, center_y - height - 0.3, data.get('eje_y_positivo', 'Alto'), bold=True)
    _crear_etiqueta(slide, center_x, center_y + height + 0.3, data.get('eje_y_negativo', 'Bajo'), bold=True)
    _crear_etiqueta(slide, center_x - width - 0.3, center_y, data.get('eje_x_negativo', 'Bajo'), bold=True, vertical=True)
    _crear_etiqueta(slide, center_x + width + 0.3, center_y, data.get('eje_x_positivo', 'Alto'), bold=True, vertical=True)

def _dibujar_foda_nativo(slide, data):
    center_x, center_y = 5.0, 3.5; width, height = 4.0, 2.2; margin = 0.1
    fortalezas = _get_case_insensitive(data, 'fortalezas')
    debilidades = _get_case_insensitive(data, 'debilidades')
    oportunidades = _get_case_insensitive(data, 'oportunidades')
    amenazas = _get_case_insensitive(data, 'amenazas')
    configs = [
        (center_x - width - margin, center_y - height - margin, (200, 230, 201), 'FORTALEZAS', fortalezas),
        (center_x + margin,         center_y - height - margin, (255, 205, 210), 'DEBILIDADES', debilidades),
        (center_x - width - margin, center_y + margin,          (187, 222, 251), 'OPORTUNIDADES', oportunidades),
        (center_x + margin,         center_y + margin,          (255, 224, 178), 'AMENAZAS', amenazas)
    ]
    for left, top, color, title, items in configs:
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
        shape.fill.solid(); shape.fill.fore_color.rgb = RGBColor(*color); shape.line.color.rgb = RGBColor(180, 180, 180)
        tf = shape.text_frame; tf.word_wrap = True; tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        p = tf.paragraphs[0]; p.text = title; p.font.bold = True; p.font.color.rgb = RGBColor(50, 50, 50)
        for item in items:
            p = tf.add_paragraph(); p.text = f"• {item}"; p.level = 0; p.font.color.rgb = RGBColor(50, 50, 50)

def _dibujar_journey_nativo(slide, data):
    keys_candidates = [k for k in data.keys() if "etapa" in k.lower() or "stage" in k.lower()]
    def natural_sort_key(s): nums = re.findall(r'\d+', s); return int(nums[0]) if nums else s
    sorted_keys = sorted(keys_candidates, key=natural_sort_key)
    etapas = []
    for k in sorted_keys:
        val = data[k]
        etapas.append(val if isinstance(val, dict) else {"nombre_etapa": k, "descripcion": str(val)})
    if not etapas:
        list_etapas = data.get('etapas', []) or data.get('pasos', [])
        if list_etapas and isinstance(list_etapas, list): etapas = list_etapas
    if not etapas: _dibujar_lista_generica(slide, data); return

    num_etapas = min(len(etapas), 6)
    etapas = etapas[:num_etapas]
    rows = 5; cols = num_etapas + 1
    left = Inches(0.5); top = Inches(1.2); width = Inches(9.0); height = Inches(5.0)
    shape = slide.shapes.add_table(rows, cols, left, top, width, height); table = shape.table
    row_headers = ["Fases", "Acciones", "Emociones", "Puntos de Dolor", "Oportunidades"]
    colors_rows = [(0, 51, 102), (245, 245, 245), (255, 255, 255), (255, 235, 238), (232, 245, 233)]
    for i, header in enumerate(row_headers):
        cell = table.cell(i, 0); cell.text = header; cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(*colors_rows[i]) if i > 0 else RGBColor(0, 51, 102)
        cell.margin_left = Inches(0.05); cell.margin_right = Inches(0.05)
        p = cell.text_frame.paragraphs[0]; p.font.bold = True; p.font.size = Pt(9)
        p.font.color.rgb = RGBColor(255, 255, 255) if i == 0 else RGBColor(0, 0, 0)
    
    keys_map = ["nombre_etapa", "acciones", "emociones", "puntos_dolor", "oportunidades"]
    for col_idx, etapa_data in enumerate(etapas):
        real_col = col_idx + 1
        for row_idx, key_part in enumerate(keys_map):
            cell = table.cell(row_idx, real_col); cell.fill.solid()
            bg_color = colors_rows[row_idx] if row_idx > 0 else (33, 150, 243)
            cell.fill.fore_color.rgb = RGBColor(*bg_color)
            cell.margin_left = Inches(0.05); cell.margin_right = Inches(0.05)
            
            if row_idx == 0:
                content = etapa_data.get("nombre_etapa", f"Etapa {col_idx+1}") if isinstance(etapa_data, dict) else f"Etapa {col_idx+1}"
            else:
                content = _get_case_insensitive_val(etapa_data, key_part)

            tf = cell.text_frame; tf.word_wrap = True
            if row_idx == 0:
                p = tf.paragraphs[0]; p.text = str(content).upper(); p.font.bold = True
                p.font.color.rgb = RGBColor(255, 255, 255); p.alignment = PP_ALIGN.CENTER; p.font.size = Pt(9)
            else:
                _llenar_text_frame_tabla(tf, content)

def _dibujar_embudo_nativo(slide, data):
    pasos = data.get('pasos', []) or data.get('etapas', [])
    if not pasos: return
    num = len(pasos); start_y = 1.5; total_h = 4.8; step_h = total_h / num; max_w = 8.5; min_w = 3.0; center_x = 5.0
    for i, paso in enumerate(pasos):
        top_w = max_w - (i * (max_w - min_w) / num)
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(center_x - top_w/2), Inches(start_y + (i * step_h) + (i*0.05)), Inches(top_w), Inches(step_h))
        shape.fill.solid(); blue_val = max(100, 220 - (i * 30)); shape.fill.fore_color.rgb = RGBColor(30, 130, blue_val)
        shape.line.fill.background()
        tf = shape.text_frame; tf.word_wrap = True; tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        tf.text = str(paso); tf.paragraphs[0].font.color.rgb = RGBColor(255, 255, 255)
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER; tf.paragraphs[0].font.bold = True

def _dibujar_lista_generica(slide, data):
    left = Inches(1); top = Inches(1.5); width = Inches(8); height = Inches(4.8)
    textbox = slide.shapes.add_textbox(left, top, width, height)
    tf = textbox.text_frame; tf.word_wrap = True; tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    excluded_keys = ['titulo_diapositiva', 'template_type', 'conclusion_clave']
    first = True
    for k, v in data.items():
        if k in excluded_keys: continue
        if not first: tf.add_paragraph()
        p = tf.add_paragraph() if not first else tf.paragraphs[0]
        p.text = k.replace('_', ' ').upper(); p.font.bold = True; p.font.color.rgb = RGBColor(0, 51, 102); first = False
        _llenar_text_frame_flexible(tf, v if isinstance(v, list) else [v])

# ==============================================================================
# HELPERS AUXILIARES
# ==============================================================================

def _get_case_insensitive(data, key):
    key = key.lower()
    for k, v in data.items():
        if k.lower() == key: return v
    return []

def _get_case_insensitive_val(data, key_part):
    if not isinstance(data, dict): return None
    if key_part in data: return data[key_part]
    for k, v in data.items():
        if key_part in k.lower(): return v
    return None

def _llenar_text_frame_flexible(text_frame, lista_items):
    if not lista_items: return
    if not isinstance(lista_items, list): lista_items = [str(lista_items)]
    valid_items = [str(x) for x in lista_items if x and str(x).lower() != "none"]
    if not valid_items: return
    p = text_frame.paragraphs[0]; p.text = f"• {valid_items[0]}"; p.font.color.rgb = RGBColor(40, 40, 40)
    for item in valid_items[1:]:
        p = text_frame.add_paragraph(); p.text = f"• {item}"; p.font.color.rgb = RGBColor(40, 40, 40)

def _llenar_text_frame_tabla(text_frame, content):
    text_frame.clear()
    if content is None or str(content).strip().lower() == "none": content = "-"
    if isinstance(content, list):
        for item in content:
            if not item: continue
            p = text_frame.add_paragraph(); p.text = f"• {item}"; p.font.size = Pt(9); p.font.color.rgb = RGBColor(0, 0, 0); p.space_after = Pt(2)
    else:
        text_str = str(content).strip()
        if not text_str: return
        p = text_frame.add_paragraph(); p.text = text_str; p.font.size = Pt(9); p.font.color.rgb = RGBColor(0, 0, 0)

def _crear_etiqueta(slide, x, y, texto, bold=False, vertical=False):
    w, h = (Inches(2), Inches(0.5)) if not vertical else (Inches(0.5), Inches(2))
    tb = slide.shapes.add_textbox(Inches(x) - w/2, Inches(y) - h/2, w, h)
    tf = tb.text_frame; tf.word_wrap = True; tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    p = tf.paragraphs[0]; p.text = str(texto); p.alignment = PP_ALIGN.CENTER; p.font.bold = bold; p.font.color.rgb = RGBColor(80, 80, 80)
    if vertical: tb.rotation = -90

def _poner_titulo_contenido(slide, shape, title, content):
    """Helper para Proposal Value Canvas (Shapes)"""
    tf = shape.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    p = tf.paragraphs[0]
    p.text = title.upper()
    p.font.bold = True
    p.font.size = Pt(10)
    p.alignment = PP_ALIGN.CENTER
    
    # Línea vacía
    tf.add_paragraph()
    _llenar_text_frame_flexible(tf, content)

def _poner_titulo_contenido_manual(slide, x, y, w, h, title, content):
    """Helper para Proposal Value Canvas (Textboxes encima de formas complejas)"""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    p = tf.paragraphs[0]
    p.text = title.upper()
    p.font.bold = True
    p.font.size = Pt(10)
    p.alignment = PP_ALIGN.CENTER
    
    tf.add_paragraph()
    _llenar_text_frame_flexible(tf, content)
