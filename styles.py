import streamlit as st

TABS_CSS = """
<style>
     /* Contenedor principal de las pestañas */
     div[data-testid="stTabs"] > div[role="tablist"] {
         border-bottom: 1px solid #e0e0e0; /* Línea base */
         gap: 5px; /* Espacio entre pestañas */
         padding-bottom: 0px; /* Eliminar padding inferior si existe */
     }

     /* Botones individuales de las pestañas (inactivas) */
     button[data-baseweb="tab"] {
         border: 1px solid #e0e0e0;
         border-bottom: none; /* Sin borde inferior para conectar */
         border-radius: 8px 8px 0 0; /* Bordes redondeados arriba */
         padding: 10px 18px !important;
         margin: 0px; /* Resetear margen */
         background-color: #f0f0f0; /* Fondo gris claro inactivo */
         color: #555; /* Texto gris oscuro */
         transition: background-color 0.2s ease, color 0.2s ease;
         position: relative; /* Para el posicionamiento del :after */
         bottom: -1px; /* Bajar 1px para alinearse con la línea base */
     }

      /* Efecto hover en pestañas inactivas */
     button[data-baseweb="tab"]:not([aria-selected="true"]):hover {
         background-color: #e5e5e5;
         color: #333;
     }

     /* Pestaña activa */
     button[data-baseweb="tab"][aria-selected="true"] {
         background-color: white; /* Fondo blanco (color del contenido) */
         border-color: #e0e0e0; /* Mismo color de borde */
         color: #0068c9; /* Color de texto principal */
         font-weight: 600; /* Un poco más grueso */
         /* La clave: el borde inferior es blanco para 'ocultar' la línea base */
         border-bottom-color: white !important;
         z-index: 1; /* Ponerla por encima de la línea base */
     }

     /* Ocultar la línea azul indicadora por defecto */
      div[data-baseweb="tab-highlight"] {
         display: none;
     }

     /* Contenido debajo de las pestañas (asegurar que no haya doble borde) */
     div[data-testid="stTabContent"] {
         padding-top: 20px; /* Ajustar según sea necesario */
         border-top: none; /* Asegurar que no haya doble borde */
     }
</style>
"""

HIDE_ST_STYLE = """
     <style>
     /* Oculta el menú de hamburguesa */
     #MainMenu {visibility: hidden;}

     /* Oculta el encabezado de la app */
     header {visibility: hidden;}

     /* Oculta el "Made with Streamlit" footer */
     footer {visibility: hidden;}

     /* Oculta la barra de estado inferior (iconos) */
     [data-testid="stStatusWidget"] {visibility: hidden;}
     </style>
"""

def apply_styles():
    st.markdown(TABS_CSS, unsafe_allow_html=True)
    st.markdown(HIDE_ST_STYLE, unsafe_allow_html=True)