import matplotlib.pyplot as plt
import seaborn as sns
from wordcloud import WordCloud
import io
import pandas as pd
from utils import get_stopwords

def generate_wordcloud_img(text):
    """Genera una imagen de nube de palabras y retorna el buffer y las frecuencias."""
    if not text: return None, None
    
    # Generar Nube
    wc = WordCloud(width=800, height=400, background_color='white', stopwords=get_stopwords()).generate(text)
    
    # Crear Figura
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.imshow(wc, interpolation='bilinear')
    ax.axis('off')
    
    # Guardar en Buffer
    img_stream = io.BytesIO()
    fig.savefig(img_stream, format='png', bbox_inches='tight')
    plt.close(fig) # Importante cerrar para liberar memoria
    
    # Calcular frecuencias para tabla
    freqs = pd.DataFrame(list(wc.words_.items()), columns=['Palabra', 'Freq']).sort_values('Freq', ascending=False)
    
    return img_stream, freqs

def generate_correlation_heatmap(df, columns):
    """Genera un mapa de calor de correlación."""
    if len(columns) < 2: return None, None
    
    corr = df[columns].corr()
    
    fig, ax = plt.subplots()
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", ax=ax)
    
    return fig, corr
