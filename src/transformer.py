# src/transformer.py
import pandas as pd

from src.mapping import normalizar


def _es_nota_credito(serie: pd.Series) -> pd.Series:
    """True donde el tipo de documento es una nota crédito (no débito)."""
    norm = serie.astype("string").map(normalizar)
    return norm.str.contains("nota de credito", na=False)


def aplicar_transformaciones(df: pd.DataFrame) -> pd.DataFrame:
    """
    Crea las columnas ajustadas a partir de 'valor' (Total) e 'iva' crudos:

      valor_ajustado  = valor,  en negativo si es nota crédito
      iva_ajustado    = iva,    en negativo si es nota crédito
      valor_bruto     = valor_ajustado - iva_ajustado

    (El origen ya trae estas columnas calculadas a mano; aquí se ignoran
    y se recalculan por código.)
    """
    df = df.copy()  # nunca modifiques el df original

    es_nc = _es_nota_credito(df["tipo_documento"])

    # NC → fuerza negativo (-abs); el resto se deja tal cual viene.
    df["valor_ajustado"] = df["valor"].where(~es_nc, -df["valor"].abs())
    df["iva_ajustado"]   = df["iva"].where(~es_nc,   -df["iva"].abs())
    df["valor_bruto"]    = df["valor_ajustado"] - df["iva_ajustado"]

    print(f"🔄 Notas crédito ajustadas a negativo: {int(es_nc.sum()):,} registros")
    return df
