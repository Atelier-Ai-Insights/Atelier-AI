import matplotlib.pyplot as plt
import matplotlib.patches as patches
import textwrap
import io

# ==========================================
# UTILIDADES DE VISUALIZACIÓN (FACTORY)
# ==========================================

def generar_visualizacion_onepager(template_name, data_json):
    """
    Función maestra que decide qué gráfico dibujar según el nombre de la plantilla.
    Retorna: BytesIO object (imagen PNG)
    """
    # Normalizamos el nombre para evitar errores por mayúsculas
    name = template_name.lower().strip()
    
    if "matriz" in name or "matrix" in name:
        return _dibujar_matriz_2x2(data_json)
    elif "foda" in name or "swot" in name:
        return _dibujar_foda(data_json)
    elif "embudo" in name or "funnel" in name or "conversion" in name:
        return _dibujar_embudo(data_json)
    else:
        # Fallback: Visualización genérica de lista/tarjetas para otros tipos
        return _dibujar_generico(data_json)

# --- 1. MATRIZ 2x2 ---
def _dibujar_matriz_2x2(data):
    plt.figure(figsize=(10, 8), dpi=150)
    fig, ax = plt.subplots(figsize=(12, 9))
    ax.set_xlim(-1, 1); ax.set_ylim(-1, 1); ax.axis('off')

    colors = ['#E3F2FD', '#E8F5E9', '#FFF3E0', '#F3E5F5']
    rects = [(-1, 0, 1, 1), (0, 0, 1, 1), (-1, -1, 1, 1), (0, -1, 1, 1)]
    
    for (x, y, w, h), color in zip(rects, colors):
        ax.add_patch(plt.Rectangle((x, y), w, h, color=color, alpha=0.5))

    ax.axhline(0, color='#333', lw=2); ax.axvline(0, color='#333', lw=2)

    # Etiquetas Ejes
    props = dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='#CCC')
    ax.text(0, 1.02, data.get('eje_y_positivo', 'Alto'), ha='center', bbox=props)
    ax.text(0, -1.02, data.get('eje_y_negativo', 'Bajo'), ha='center', va='top', bbox=props)
    ax.text(-1.02, 0, data.get('eje_x_negativo', 'Bajo'), ha='right', bbox=props)
    ax.text(1.02, 0, data.get('eje_x_positivo', 'Alto'), ha='left', bbox=props)

    # Textos Cuadrantes
    _poner_texto(ax, -0.5, 0.5, data.get('items_cuadrante_sup_izq', []))
    _poner_texto(ax, 0.5, 0.5, data.get('items_cuadrante_sup_der', []))
    _poner_texto(ax, -0.5, -0.5, data.get('items_cuadrante_inf_izq', []))
    _poner_texto(ax, 0.5, -0.5, data.get('items_cuadrante_inf_der', []))

    plt.title(data.get('titulo_diapositiva', 'Matriz'), fontsize=14, fontweight='bold', pad=20)
    return _guardar_buffer()

# --- 2. FODA / SWOT ---
def _dibujar_foda(data):
    plt.figure(figsize=(10, 8), dpi=150)
    fig, ax = plt.subplots(figsize=(12, 9))
    ax.set_xlim(0, 2); ax.set_ylim(0, 2); ax.axis('off')

    # Colores FODA: Verde (F), Rojo (D), Azul (O), Naranja (A)
    configs = [
        (0, 1, 'Fortalezas', '#C8E6C9', data.get('fortalezas', [])),
        (1, 1, 'Debilidades', '#FFCDD2', data.get('debilidades', [])),
        (0, 0, 'Oportunidades', '#BBDEFB', data.get('oportunidades', [])),
        (1, 0, 'Amenazas', '#FFE0B2', data.get('amenazas', []))
    ]

    for x, y, title, color, items in configs:
        # Fondo
        ax.add_patch(plt.Rectangle((x, y), 1, 1, color=color, alpha=0.6))
        # Título Sección
        ax.text(x + 0.5, y + 0.9, title.upper(), ha='center', fontweight='bold', fontsize=12, color='#333')
        # Contenido
        _poner_texto(ax, x + 0.5, y + 0.5, items)

    plt.title(data.get('titulo_diapositiva', 'Análisis FODA'), fontsize=16, fontweight='bold', pad=20)
    return _guardar_buffer()

# --- 3. EMBUDO / FUNNEL ---
def _dibujar_embudo(data):
    plt.figure(figsize=(8, 10), dpi=150)
    fig, ax = plt.subplots(figsize=(10, 12))
    ax.axis('off'); ax.set_xlim(0, 10); ax.set_ylim(0, 10)

    # Extraemos pasos del JSON (asumiendo lista de strings o claves especificas)
    # Intentamos buscar una lista 'pasos' o 'etapas'
    pasos = data.get('pasos', []) or data.get('etapas', [])
    if not pasos:
        # Fallback si el JSON viene plano
        pasos = [v for k, v in data.items() if 'paso' in k or 'etapa' in k]

    num_pasos = len(pasos)
    if num_pasos == 0: return _dibujar_generico(data) # Si falla, usa generico

    height = 9 / num_pasos
    top_width = 8
    bottom_width = 2
    
    colors = ['#1565C0', '#1976D2', '#1E88E5', '#2196F3', '#42A5F5', '#64B5F6'] # Gradiente Azul

    for i, texto in enumerate(pasos):
        y_top = 9.5 - (i * height)
        y_bot = y_top - height + 0.1 # gap
        
        # Calcular anchos trapezoidales
        w_top = top_width - (i * (top_width - bottom_width) / num_pasos)
        w_bot = top_width - ((i + 1) * (top_width - bottom_width) / num_pasos)
        
        x_left_top = 5 - (w_top / 2)
        x_right_top = 5 + (w_top / 2)
        x_left_bot = 5 - (w_bot / 2)
        x_right_bot = 5 + (w_bot / 2)

        # Dibujar Trapecio
        poly = [[x_left_top, y_top], [x_right_top, y_top], [x_right_bot, y_bot], [x_left_bot, y_bot]]
        color = colors[i % len(colors)]
        ax.add_patch(patches.Polygon(poly, closed=True, color=color, alpha=0.8))
        
        # Texto dentro
        wrapped = textwrap.fill(str(texto), width=30)
        ax.text(5, (y_top + y_bot)/2, wrapped, ha='center', va='center', color='white', fontweight='bold', fontsize=10)

    plt.title(data.get('titulo_diapositiva', 'Embudo'), fontsize=16, fontweight='bold')
    return _guardar_buffer()

# --- 4. GENÉRICO (LISTA) ---
def _dibujar_generico(data):
    """Renderiza cualquier JSON como una lista de tarjetas limpia"""
    plt.figure(figsize=(10, 10), dpi=150)
    fig, ax = plt.subplots(figsize=(12, 10))
    ax.axis('off'); ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    # Filtrar claves que no sean titulo
    items = {k: v for k, v in data.items() if k not in ['titulo_diapositiva', 'template_type', 'conclusion_clave']}
    keys = list(items.keys())
    
    y_pos = 0.9
    for k in keys:
        val = items[k]
        if isinstance(val, list): val = "\n".join([f"• {x}" for x in val])
        
        # Título de la sección
        ax.text(0.05, y_pos, k.replace('_', ' ').upper(), fontsize=10, fontweight='bold', color='#1565C0')
        y_pos -= 0.03
        
        # Contenido
        wrapped = textwrap.fill(str(val), width=90)
        ax.text(0.05, y_pos, wrapped, fontsize=10, va='top', color='#333')
        
        # Calcular cuánto bajamos (aprox)
        lines = wrapped.count('\n') + 1
        y_pos -= (lines * 0.04) + 0.05 # Espacio extra

    plt.title(data.get('titulo_diapositiva', 'Resumen Estratégico'), fontsize=16, fontweight='bold', pad=20)
    return _guardar_buffer()

# --- HELPERS ---
def _poner_texto(ax, x, y, lista_items):
    if not lista_items: return
    if isinstance(lista_items, str): lista_items = [lista_items]
    texto = ""
    for item in lista_items:
        wrapped = textwrap.fill(item, width=30)
        texto += f"• {wrapped}\n"
    ax.text(x, y, texto, fontsize=9, va='center', ha='center')

def _guardar_buffer():
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.close()
    buf.seek(0)
    return buf
