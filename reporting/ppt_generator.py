from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_AUTO_SIZE
import io

def crear_ppt_desde_json(data_json, image_stream=None):
    """
    Genera un PowerPoint con formas NATIVAS y EDITABLES basado en el JSON.
    Soporta: Matriz 2x2, FODA/DOFA, Embudo, Customer Journey Map (Tabla) y Listas.
    """
    
    # 1. Cargar Plantilla Base
    try:
        # Ajusta el nombre si tu archivo se llama diferente
        prs = Presentation("Plantilla_PPT_ATL.pptx")
    except:
        # Fallback si no encuentra el archivo
        prs = Presentation()

    # Usamos un layout vacío o de título y contenido (normalmente índice 6 es Blank)
    slide_layout = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[-1]
    slide = prs.slides.add_slide(slide_layout)

    # 2. Configurar Título
    titulo_texto = data_json.get('titulo_diapositiva', 'Resumen Estratégico')
    
    if slide.shapes.title:
        slide.shapes.title.text = titulo_texto
    else:
        # Crear cuadro de título manual si el layout no tiene
        title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.2), Inches(9), Inches(1))
        tf = title_box.text_frame
        tf.text = titulo_texto
        tf.paragraphs[0].font.size = Pt(24)
        tf.paragraphs[0].font.bold = True
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER

    # 3. Router de Plantillas (Detectar Tipo y Dibujar)
    template_type = data_json.get('template_type', '').lower()
    
    if "matriz" in template_type or "2x2" in template_type:
        _dibujar_matriz_nativa(slide, data_json)
        
    elif "foda" in template_type or "swot" in template_type or "dofa" in template_type:
        _dibujar_foda_nativo(slide, data_json)
        
    elif "embudo" in template_type or "funnel" in template_type:
        _dibujar_embudo_nativo(slide, data_json)
        
    elif "journey" in template_type or "viaje" in template_type or "map" in template_type:
        _dibujar_journey_nativo(slide, data_json)
        
    else:
        _dibujar_lista_generica(slide, data_json)

    # 4. Agregar Conclusión (Común a todos)
    if 'conclusion_clave' in data_json:
        # Caja de fondo
        bg = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.5), Inches(6.6), Inches(9), Inches(0.8))
        bg.fill.solid()
        bg.fill.fore_color.rgb = RGBColor(245, 245, 245)
        bg.line.color.rgb = RGBColor(220, 220, 220)
        
        # Texto
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
# FUNCIONES DE DIBUJO ESPECÍFICAS
# ==============================================================================

def _dibujar_matriz_nativa(slide, data):
    """Dibuja 4 cuadrantes editables y ejes."""
    center_x, center_y = 5.0, 3.5
    width, height = 4.0, 2.2
    margin = 0.05

    quads = [
        (center_x - width - margin, center_y - height - margin, (227, 242, 253), 'items_cuadrante_sup_izq'), # Azul claro
        (center_x + margin,         center_y - height - margin, (232, 245, 233), 'items_cuadrante_sup_der'), # Verde claro
        (center_x - width - margin, center_y + margin,          (255, 243, 224), 'items_cuadrante_inf_izq'), # Naranja claro
        (center_x + margin,         center_y + margin,          (243, 229, 245), 'items_cuadrante_inf_der')  # Morado claro
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

    # Etiquetas de Ejes
    _crear_etiqueta(slide, center_x, center_y - height - 0.3, data.get('eje_y_positivo', 'Alto'), bold=True)
    _crear_etiqueta(slide, center_x, center_y + height + 0.3, data.get('eje_y_negativo', 'Bajo'), bold=True)
    _crear_etiqueta(slide, center_x - width - 0.3, center_y, data.get('eje_x_negativo', 'Bajo'), bold=True, vertical=True)
    _crear_etiqueta(slide, center_x + width + 0.3, center_y, data.get('eje_x_positivo', 'Alto'), bold=True, vertical=True)


def _dibujar_foda_nativo(slide, data):
    """Dibuja matriz DOFA/FODA robusta a mayúsculas/minúsculas."""
    center_x, center_y = 5.0, 3.5
    width, height = 4.0, 2.2
    margin = 0.1

    # Búsqueda insensible a mayúsculas
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

        # Título del cuadrante
        p = tf.paragraphs[0]
        p.text = title
        p.font.bold = True
        p.font.color.rgb = RGBColor(50, 50, 50)
        
        # Items
        for item in items:
            p = tf.add_paragraph()
            p.text = f"• {item}"
            p.level = 0
            p.font.color.rgb = RGBColor(50, 50, 50)


def _dibujar_journey_nativo(slide, data):
    """Construye una TABLA para el Customer Journey Map."""
    # 1. Extraer Etapas
    etapas = []
    # Buscar claves que contengan 'etapa' o 'stage'
    sorted_keys = sorted([k for k in data.keys() if "etapa" in k.lower() or "stage" in k.lower()])
    
    for k in sorted_keys:
        val = data[k]
        if isinstance(val, dict):
            etapas.append(val)
        else:
            etapas.append({"nombre_etapa": k, "descripcion": str(val)})

    # Fallback: buscar lista 'etapas' o 'pasos'
    if not etapas:
        list_etapas = data.get('etapas', []) or data.get('pasos', [])
        if list_etapas and isinstance(list_etapas, list):
            etapas = list_etapas

    if not etapas:
        # Si falla todo, usar lista genérica
        _dibujar_lista_generica(slide, data)
        return

    # 2. Configurar Tabla
    num_etapas = len(etapas)
    rows = 5 # Header + Acciones + Emociones + Puntos Dolor + Oportunidades
    cols = num_etapas + 1 # +1 para la columna de títulos izquierda
    
    left = Inches(0.5)
    top = Inches(1.2)
    width = Inches(9.0)
    height = Inches(5.0)

    shape = slide.shapes.add_table(rows, cols, left, top, width, height)
    table = shape.table

    # 3. Encabezados de Fila (Izquierda)
    row_headers = ["Fases", "Acciones", "Emociones", "Puntos de Dolor", "Oportunidades"]
    colors_rows = [(0, 51, 102), (245, 245, 245), (255, 255, 255), (255, 235, 238), (232, 245, 233)]
    
    for i, header in enumerate(row_headers):
        cell = table.cell(i, 0)
        cell.text = header
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(*colors_rows[i]) if i > 0 else RGBColor(0, 51, 102)
        
        p = cell.text_frame.paragraphs[0]
        p.font.bold = True
        p.font.size = Pt(10)
        p.font.color.rgb = RGBColor(255, 255, 255) if i == 0 else RGBColor(0, 0, 0)

    # 4. Llenar Datos
    keys_map = ["nombre_etapa", "acciones", "emociones", "puntos_dolor", "oportunidades"]

    for col_idx, etapa_data in enumerate(etapas):
        real_col = col_idx + 1
        
        for row_idx, key_part in enumerate(keys_map):
            cell = table.cell(row_idx, real_col)
            cell.fill.solid()
            # Color de fondo igual a la fila, o header azul para la primera fila
            bg_color = colors_rows[row_idx] if row_idx > 0 else (33, 150, 243)
            cell.fill.fore_color.rgb = RGBColor(*bg_color)
            
            # Obtener contenido (búsqueda flexible)
            if row_idx == 0 and isinstance(etapa_data, dict) and "nombre_etapa" in etapa_data:
                 content = etapa_data["nombre_etapa"]
            elif row_idx == 0:
                 content = f"Etapa {col_idx+1}"
            else:
                 content = _get_case_insensitive_val(etapa_data, key_part)

            # Escribir en celda
            tf = cell.text_frame
            tf.word_wrap = True
            
            if row_idx == 0:
                p = tf.paragraphs[0]
                p.text = str(content).upper()
                p.font.bold = True
                p.font.color.rgb = RGBColor(255, 255, 255)
                p.alignment = PP_ALIGN.CENTER
                p.font.size = Pt(10)
            else:
                _llenar_text_frame_tabla(tf, content)


def _dibujar_embudo_nativo(slide, data):
    """Dibuja trapecios/rectángulos apilados."""
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

        tf.text = str(paso)
        tf.paragraphs[0].font.color.rgb = RGBColor(255, 255, 255)
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        tf.paragraphs[0].font.bold = True


def _dibujar_lista_generica(slide, data):
    """Fallback para listas."""
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


# ==============================================================================
# HELPERS AUXILIARES
# ==============================================================================

def _get_case_insensitive(data, key):
    """Busca una clave exacta ignorando mayúsculas."""
    key = key.lower()
    for k, v in data.items():
        if k.lower() == key:
            return v
    return []

def _get_case_insensitive_val(data, key_part):
    """Busca valor si la clave contiene el string parcial (ej: 'acciones' -> 'acciones_usuario')."""
    if not isinstance(data, dict): return "-"
    # Intento directo
    if key_part in data: return data[key_part]
    # Intento parcial
    for k, v in data.items():
        if key_part in k.lower():
            return v
    return "-"

def _llenar_text_frame_flexible(text_frame, lista_items):
    """Llena bullets."""
    if not lista_items: return
    
    # Usar el párrafo existente
    p = text_frame.paragraphs[0]
    p.text = f"• {lista_items[0]}"
    p.font.color.rgb = RGBColor(40, 40, 40)
    
    for item in lista_items[1:]:
        p = text_frame.add_paragraph()
        p.text = f"• {item}"
        p.font.color.rgb = RGBColor(40, 40, 40)

def _llenar_text_frame_tabla(text_frame, content):
    """Llena celdas de tabla con letra pequeña."""
    text_frame.clear() 
    
    if isinstance(content, list):
        for item in content:
            p = text_frame.add_paragraph()
            p.text = f"• {item}"
            p.font.size = Pt(9)
            p.font.color.rgb = RGBColor(0, 0, 0)
            p.space_after = Pt(2)
    else:
        p = text_frame.add_paragraph()
        p.text = str(content)
        p.font.size = Pt(9)
        p.font.color.rgb = RGBColor(0, 0, 0)

def _crear_etiqueta(slide, x, y, texto, bold=False, vertical=False):
    """Crea etiquetas de ejes."""
    w, h = (Inches(2), Inches(0.5)) if not vertical else (Inches(0.5), Inches(2))
    x_pos = Inches(x) - w/2
    y_pos = Inches(y) - h/2
    
    tb = slide.shapes.add_textbox(x_pos, y_pos, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    
    p = tf.paragraphs[0]
    p.text = str(texto)
    p.alignment = PP_ALIGN.CENTER
    p.font.bold = bold
    p.font.color.rgb = RGBColor(80, 80, 80)
    if vertical:
         tb.rotation = -90
