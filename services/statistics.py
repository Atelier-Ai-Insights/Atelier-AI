import pandas as pd
import scipy.stats as stats
import numpy as np
import io

def get_dataframe_snapshot(df):
    """Genera un resumen textual técnico del DataFrame para enviarlo a la IA."""
    snapshot_buffer = io.StringIO()
    snapshot_buffer.write(f"Total Filas: {len(df)}\n\n")
    df.info(buf=snapshot_buffer, verbose=False)
    
    numeric_cols = df.select_dtypes(include=['number']).columns
    if not numeric_cols.empty:
        snapshot_buffer.write("\nMétricas Numéricas:\n")
        snapshot_buffer.write(df[numeric_cols].describe().to_string(float_format="%.2f"))
        
    cat_cols = df.select_dtypes(include=['object', 'category']).columns
    if not cat_cols.empty:
        snapshot_buffer.write("\nDistribución Categórica (Top 5):\n")
        for col in cat_cols:
            if df[col].nunique() < 50: 
                snapshot_buffer.write(f"\n{col}:\n")
                snapshot_buffer.write(df[col].value_counts(normalize=True).head(5).to_string(float_format="%.1f%%"))
    
    return snapshot_buffer.getvalue()

def calculate_chi_squared(pivot_table):
    """Calcula Chi2 para una tabla dinámica (crosstab)."""
    if pivot_table.size > 1:
        chi2, p, dof, ex = stats.chi2_contingency(pivot_table + 1) # +1 corrección básica de ceros
        residuals = (pivot_table - ex) / np.sqrt(ex)
        return p, residuals
    return None, None

def calculate_group_comparison(df, num_col, cat_col):
    """Realiza ANOVA o T-Test según la cantidad de grupos."""
    groups = [df[num_col][df[cat_col] == g].dropna() for g in df[cat_col].unique()]
    
    if len(groups) < 2:
        return None, None, 0
        
    if len(groups) > 2:
        stat, p = stats.f_oneway(*groups)
        test_type = "ANOVA"
    else:
        stat, p = stats.ttest_ind(groups[0], groups[1])
        test_type = "T-Test"
        
    return test_type, p, len(groups)
