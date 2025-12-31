from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
import io

def crear_ppt_desde_json(data_json, image_stream=None):
    """
    Genera un PowerPoint con formas NATIVAS y EDITABLES basado en el JSON.
    El argumento 'image_stream' se mantiene por compatibilidad pero NO se usa,
    priorizando la creación de objetos editables.
    """
    
    # 1. Cargar Plantilla Base
    # Asegúrate de que el nombre del archivo coincida con el que tienes en tu carpeta
    try:
        prs = Presentation("Plantilla_PPT_ATL.pptx")
    except:
        # Fallback si no encuentra la plantilla: crea una en blanco
        prs = Presentation()

    # Usamos un layout vacío o de título y contenido (normalmente índice 1 o 6)
    # Ajusta este índice según tu plantilla maestra. El 6 suele ser "Blank".
    slide_layout = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[-1]
    slide = prs.slides.add_slide(slide_layout)

    # 2. Configurar Título
    # Si el layout no tiene título, creamos uno manual arriba
    if slide.shapes.title:
        slide.shapes.title.text = data_json.get('titulo_diapositiva', 'Resumen Estratégico')
    else:
        # Crear cuadro de título manual
        title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(9), Inches(1))
        tf = title_box.text_frame
        tf.text = data_json.get('titulo_diapositiva', 'Resumen Estratégico')
        tf.paragraphs[0].font.size = Pt(24)
        tf.paragraphs[0].font.bold = True
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER

    # 3. Detectar Tipo y Dibujar
    template_type = data_json.get('template_type', '').lower()
    
    # Lógica de Fábrica de Formas
    if "matriz" in template_type or "2x2" in template_type:
        _dibujar_matriz_nativa(slide, data_json)
    elif "foda" in template_type or "swot" in template_type:
        _dibujar_foda_nativo(slide, data_json)
    elif "embudo" in template_type or "funnel" in template_type:
        _dibujar_embudo_nativo(slide, data_json)
    else:
        _dibujar_lista_generica(slide, data_json)

    # 4. Agregar Conclusión (Común a todos)
    if 'conclusion_clave' in data_json:
        # Cuadro de fondo para la conclusión
        bg = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.5), Inches(6.5), Inches(9), Inches(0.8))
        bg.fill.solid()
        bg.fill.fore_color.rgb = RGBColor(240, 240, 240) # Gris muy claro
        bg.line.color.rgb = RGBColor(200, 200, 200)
        
        # Texto de conclusión
        tf = bg.text_frame
        tf.text = "💡 " + data_json['conclusion_clave']
        p = tf.paragraphs[0]
        p.font.size = Pt(11)
        p.font.color.rgb = RGBColor(50, 50, 50)
        p.alignment = PP_ALIGN.LEFT

    # 5. Guardar y Retornar
    output = io.BytesIO()
    prs.save(output)
    output.seek(0)
    return output

# ==============================================================================
# FUNCIONES DE DIBUJO (HELPERS)
# ==============================================================================

def _dibujar_matriz_nativa(slide, data):
    """Dibuja 4 cuadrantes editables y ejes."""
    # Coordenadas base (Centro aprox: 5, 3.5 pulgadas)
    center_x, center_y = 5.0, 3.5
    width, height = 4.0, 2.2  # Tamaño de cada cuadrante
    margin = 0.05 # Espacio pequeño entre cuadros

    # Configuración de los 4 cuadrantes: (Left, Top, ColorRGB, KeyData)
    quads = [
        (center_x - width - margin, center_y - height - margin, (227, 242, 253), 'items_cuadrante_sup_izq'), # Sup Izq (Azul claro)
        (center_x + margin,         center_y - height - margin, (232, 245, 233), 'items_cuadrante_sup_der'), # Sup Der (Verde claro)
        (center_x - width - margin, center_y + margin,          (255, 243, 224), 'items_cuadrante_inf_izq'), # Inf Izq (Naranja claro)
        (center_x + margin,         center_y + margin,          (243, 229, 245), 'items_cuadrante_inf_der')  # Inf Der (Morado claro)
    ]

    for left, top, color, key in quads:
        # Crear forma rectangular
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
        # Estilo
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(*color)
        shape.line.color.rgb = RGBColor(200, 200, 200)
        
        # Llenar texto
        items = data.get(key, [])
        _llenar_text_frame(shape.text_frame, items)

    # Etiquetas de Ejes (Cajas de texto flotantes)
    # Eje Y (Arriba/Abajo)
    _crear_etiqueta(slide, center_x, center_y - height - 0.4, data.get('eje_y_positivo', 'Alto'), bold=True)
    _crear_etiqueta(slide, center_x, center_y + height + 0.4, data.get('eje_y_negativo', 'Bajo'), bold=True)
    # Eje X (Izq/Der)
    _crear_etiqueta(slide, center_x - width - 0.4, center_y, data.get('eje_x_negativo', 'Bajo'), bold=True)
    _crear_etiqueta(slide, center_x + width + 0.4, center_y, data.get('eje_x_positivo', 'Alto'), bold=True)


def _dibujar_foda_nativo(slide, data):
    """Dibuja matriz FODA clásica editable."""
    # Similar a la matriz pero con etiquetas fijas
    center_x, center_y = 5.0, 3.5
    width, height = 4.0, 2.2
    margin = 0.1

    configs = [
        (center_x - width - margin, center_y - height - margin, (200, 230, 201), 'FORTALEZAS', data.get('fortalezas', [])),
        (center_x + margin,         center_y - height - margin, (255, 205, 210), 'DEBILIDADES', data.get('debilidades', [])),
        (center_x - width - margin, center_y + margin,          (187, 222, 251), 'OPORTUNIDADES', data.get('oportunidades', [])),
        (center_x + margin,         center_y + margin,          (255, 224, 178), 'AMENAZAS', data.get('amenazas', []))
    ]

    for left, top, color, title, items in configs:
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(*color)
        shape.line.color.rgb = RGBColor(150, 150, 150)
        
        # Texto: Primero el título en negrita
        tf = shape.text_frame
        p = tf.paragraphs[0]
        p.text = title
        p.font.bold = True
        p.font.size = Pt(12)
        
        # Luego los items
        for item in items:
            p = tf.add_paragraph()
            p.text = f"• {item}"
            p.font.size = Pt(10)
            p.level = 0


def _dibujar_embudo_nativo(slide, data):
    """Dibuja trapecios invertidos apilados."""
    pasos = data.get('pasos', []) or data.get('etapas', [])
    if not pasos: return # Fallback
    
    num = len(pasos)
    start_y = 1.5
    total_h = 4.5
    step_h = total_h / num
    max_w = 8.0
    min_w = 2.0
    
    center_x = 5.0 # Centro de la diapositiva

    for i, paso in enumerate(pasos):
        # Calculamos ancho superior e inferior para simular embudo
        top_w = max_w - (i * (max_w - min_w) / num)
        
        # Dibujamos un trapecio
        shape = slide.shapes.add_shape(
            MSO_SHAPE.TRAPEZOID, 
            Inches(center_x - top_w/2), 
            Inches(start_y + (i * step_h)), 
            Inches(top_w), 
            Inches(step_h - 0.1)
        )
        # Invertimos el trapecio (flip vertical no siempre funciona bien con texto, 
        # así que usamos el trapecio estándar pero reducimos el ancho progresivamente)
        # Nota: MSO_SHAPE.TRAPEZOID por defecto es base ancha abajo. 
        # Para embudo visual simple, rectángulos de ancho decreciente es más seguro para texto.
        
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(33, 150, 243) # Azul corporativo
        
        # Texto
        tf = shape.text_frame
        tf.text = paso
        tf.paragraphs[0].font.color.rgb = RGBColor(255, 255, 255)
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER

def _dibujar_lista_generica(slide, data):
    """Lista simple para otros casos."""
    left = Inches(1)
    top = Inches(1.5)
    width = Inches(8)
    height = Inches(4.5)
    
    textbox = slide.shapes.add_textbox(left, top, width, height)
    tf = textbox.text_frame
    tf.word_wrap = True
    
    excluded_keys = ['titulo_diapositiva', 'template_type', 'conclusion_clave']
    
    for k, v in data.items():
        if k in excluded_keys: continue
        
        # Título sección
        p = tf.add_paragraph()
        p.text = k.replace('_', ' ').upper()
        p.font.bold = True
        p.font.size = Pt(12)
        p.font.color.rgb = RGBColor(0, 51, 102)
        
        # Contenido
        if isinstance(v, list):
            for item in v:
                p = tf.add_paragraph()
                p.text = f"• {item}"
                p.level = 1
                p.font.size = Pt(11)
        else:
            p = tf.add_paragraph()
            p.text = str(v)
            p.level = 1
            p.font.size = Pt(11)
        
        # Espacio
        p = tf.add_paragraph()
        p.text = ""
        p.font.size = Pt(6)

def _llenar_text_frame(text_frame, lista_items):
    """Helper para llenar listas de bullets."""
    text_frame.word_wrap = True
    # Limpiar párrafo inicial vacío si es necesario, o usarlo
    p = text_frame.paragraphs[0]
    if lista_items:
        p.text = f"• {lista_items[0]}"
        p.font.size = Pt(10)
        p.font.color.rgb = RGBColor(50, 50, 50)
        
        for item in lista_items[1:]:
            p = text_frame.add_paragraph()
            p.text = f"• {item}"
            p.font.size = Pt(10)
            p.font.color.rgb = RGBColor(50, 50, 50)

def _crear_etiqueta(slide, x, y, texto, bold=False):
    """Helper para etiquetas de ejes."""
    tb = slide.shapes.add_textbox(Inches(x) - Inches(1), Inches(y) - Inches(0.3), Inches(2), Inches(0.6))
    p = tb.text_frame.paragraphs[0]
    p.text = texto
    p.alignment = PP_ALIGN.CENTER
    p.font.size = Pt(11)
    p.font.bold = bold
    p.font.color.rgb = RGBColor(80, 80, 80)
