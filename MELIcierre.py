# streamlit_app.py
# -*- coding: utf-8 -*-

import re
import io
import unicodedata
import pandas as pd
import streamlit as st

# -----------------------------
# Helpers de texto
# -----------------------------
def fix_mojibake(text: str) -> str:
    """
    Intenta corregir textos con mala decodificación tipo:
    'FÃ³rmula' -> 'Fórmula', 'BebÃ©' -> 'Bebé'
    """
    if text is None:
        return ""
    s = str(text)
    # Heurística: si aparecen marcadores típicos de mojibake, intenta latin1->utf8
    if any(x in s for x in ["Ã", "Â", "�"]):
        try:
            return s.encode("latin1").decode("utf-8")
        except Exception:
            return s
    return s

def strip_accents_upper(text: str) -> str:
    """
    Corrige mojibake, quita acentos y pone en MAYÚSCULAS.
    """
    s = fix_mojibake(text)
    s = s.strip()
    # Normaliza unicode y elimina diacríticos
    s_norm = unicodedata.normalize("NFD", s)
    s_no_accents = "".join(ch for ch in s_norm if unicodedata.category(ch) != "Mn")
    return s_no_accents.upper()

def normalize_key(text: str) -> str:
    """
    Normalización para comparar títulos de productos:
    - corrige mojibake
    - mayúsculas sin acentos
    - espacios colapsados
    """
    s = strip_accents_upper(text)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def parse_gramaje_grams(text: str):
    """
    Extrae gramaje en gramos desde un texto.
    Soporta ejemplos: 340gr, 800g, 360 GR, 1.5kg, 1,5 kg, 1500gr, etc.
    Regresa int o None.
    """
    if text is None:
        return None
    s = strip_accents_upper(text)

    # 1) Buscar KG (ej 1.5KG, 1,5 KG)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*KG\b", s)
    if m:
        val = m.group(1).replace(",", ".")
        try:
            grams = int(round(float(val) * 1000))
            return grams
        except Exception:
            pass

    # 2) Buscar GR / G (ej 800GR, 800 G)
    m = re.search(r"\b(\d{2,5})\s*(GR|G)\b", s)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass

    return None

def safe_int(x, default=0):
    """
    Convierte a int de forma segura (acepta strings con comas, espacios).
    """
    if x is None or x == "":
        return default
    s = str(x).strip()
    s = s.replace(",", "")  # por si vienen miles
    try:
        return int(float(s))
    except Exception:
        return default

# -----------------------------
# Mapeo de equivalencias
# Key: titulo (normalizado) -> (multiplicador_pack, upc, descripcion)
# -----------------------------
EQUIV_LIST = [
    ("LecheLak - Leche de Cabra en Polvo 340gr La Mejor Opción Para Toda la Familia Calidad y Frescura en Cada Porción",
     1, "7501468144501", "LECHELAK LECHE DE CABRA 340 G"),
    ("6 Pack Fórmula Crecelac Bebé 0-12 Meses 800gr",
     6, "7501468140442", "CRECELAC 0-12 M 800 GR"),
    ("6 Pack Fórmula Crecelac Firstep 1-3 Años 1500gr",
     6, "7501468140947", "CRECELAC FIRSTEP 1-3 AÑOS 1.5 KG"),
    ("6 Pack Fórmula Crecelac Firstep 1-3 Años 800gr",
     6, "7501468148301", "CRECELAC FIRSTEP 1-3 AÑOS 800 GR"),
    ("LecheLak - Leche de Cabra en Polvo 340gr La Mejor Opción Para Toda la Familia Calidad y Frescura en Cada Porción - 12 pack",
     12, "7501468144501", "LECHELAK LECHE DE CABRA 340 G"),
    ("FÃ³rmula Crecelac Firstep 1-3 AÃ±os 360gr",
     1, "7501468148103", "CRECELAC FIRSTEP 1-3 AÑOS 360 GR"),
    ("FÃ³rmula Crecelac Firstep 1-3 AÃ±os 800gr",
     1, "7501468140442", "CRECELAC 0-12 M 800 GR"),
    ("FÃ³rmula Crecelac BebÃ© 0-12 Meses 400gr",
     1, "7501468145508", "CRECELAC 0-12 M 400 GR"),
    ("12 Pack Crecelac BebÃ© 0-12 Meses 400gr",
     12, "7501468145508", "CRECELAC 0-12 M 400 GR"),
    ("Fórmula Crecelac Firstep 1-3 Años 1500gr",
     1, "7501468140947", "CRECELAC FIRSTEP 1-3 AÑOS 1.5 KG"),
    ("Crecelac 2 Pack Fórmula Para Lactante Firstep 1-3 Años 800gr Natural",
     2, "7501468148301", "CRECELAC FIRSTEP 1-3 AÑOS 800 GR"),
    ("Crecelac 6 Pack Fórmula Para Lactante Firstep 1-3 Años 1500g Natural",
     6, "7501468140947", "CRECELAC FIRSTEP 1-3 AÑOS 1.5 KG"),
    ("Dm Mexicana Fórmula Crecelac Bebé 0-12 Meses 400gr  Natural",
     1, "7501468145508", "CRECELAC 0-12 M 400 GR"),
    ("Dm Mexicana Fórmula Crecelac Firstep 1-3 Años 800gr  Natural",
     1, "7501468148301", "CRECELAC FIRSTEP 1-3 AÑOS 800 GR"),
    ("Leche En Polvo Crecelac Bebé Natural Para 0 A 1 Año 800g 6 Latas",
     6, "7501468140442", "CRECELAC 0-12 M 800 GR"),
    ("Leche Entera De Cabra En Polvo 340gr Fácil Digestión 2 Pack",
     1, "7501468144501", "LECHELAK LECHE DE CABRA 340 G"),
    ("Lechelack Leche Entera De Cabra En Polvo 340gr 12 Pack",
     12, "7501468144501", "LECHELAK LECHE DE CABRA 340 G"),
    # Ejemplo que pusiste al inicio:
    ("Fórmula Crecelac Bebé 0-12 Meses 1500gr",
     1, "7501468141043", "CRECELAC 0-12 M 1.5 KG"),
]

EQUIV_MAP = {normalize_key(k): (mult, upc, desc) for (k, mult, upc, desc) in EQUIV_LIST}

# -----------------------------
# Lectura de archivo
# -----------------------------
def read_uploaded_file(uploaded_file, has_header=True, sep_guess="auto"):
    name = uploaded_file.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        # Excel
        df = pd.read_excel(uploaded_file, dtype=str, header=0 if has_header else None)
        return df
    else:
        # CSV / TXT
        raw = uploaded_file.getvalue()
        # Intentar detectar encoding básico
        for enc in ["utf-8-sig", "utf-8", "latin1"]:
            try:
                text = raw.decode(enc)
                break
            except Exception:
                text = None
        if text is None:
            # fallback
            text = raw.decode("latin1", errors="replace")

        if sep_guess == "auto":
            # Heurística simple
            sep = "," if text.count(",") >= text.count(";") else ";"
        else:
            sep = sep_guess

        df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, header=0 if has_header else None, keep_default_na=False)
        return df

# -----------------------------
# Procesamiento principal
# -----------------------------
def process_df(df: pd.DataFrame):
    # Columnas por letra (posicional):
    # F = 6ta col -> index 5
    # G = 7ma col -> index 6
    # AH = 34ta col -> index 33
    # AI = 35ta col -> index 34
    required_max_index = 34
    if df.shape[1] <= required_max_index:
        raise ValueError(
            f"El archivo tiene {df.shape[1]} columnas, pero necesito al menos 35 (hasta la columna AI)."
        )

    # Asegurar strings
    df = df.copy()
    for c in df.columns:
        df[c] = df[c].astype(str).fillna("")

    # AH y AI -> mayusculas sin acentos (y corrige mojibake)
    col_AH = df.columns[33]
    col_AI = df.columns[34]
    df[col_AH] = df[col_AH].apply(strip_accents_upper)
    df[col_AI] = df[col_AI].apply(strip_accents_upper)

    # F y G
    col_F = df.columns[5]
    col_G = df.columns[6]

    # Nuevas columnas
    cantidad_out = []
    upc_out = []
    desc_out = []
    gramaje_out = []

    for _, row in df.iterrows():
        title = row[col_F]
        units_sold = safe_int(row[col_G], default=0)

        key = normalize_key(title)
        mult, upc, desc = EQUIV_MAP.get(key, (1, "", ""))

        cantidad = units_sold * mult

        # Gramaje: preferimos extraer del título; si no, de la descripción
        grams = parse_gramaje_grams(title)
        if grams is None and desc:
            grams = parse_gramaje_grams(desc)

        cantidad_out.append(cantidad if cantidad != 0 else ("" if units_sold == 0 else cantidad))
        upc_out.append(upc)
        desc_out.append(desc)
        gramaje_out.append("" if grams is None else grams)

    df["Cantidad"] = cantidad_out
    df["UPC"] = upc_out
    df["Descripcion"] = desc_out
    df["Gramaje"] = gramaje_out

    return df

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Procesador Excel/CSV (Crecelac/LecheLak)", layout="wide")
st.title("Procesador de Excel/CSV — Normalización + Packs + UPC/Descripción + Gramaje")

with st.expander("Qué hace este procesador", expanded=True):
    st.markdown(
        """
- **AH** y **AI** → **MAYÚSCULAS sin acentos** (y corrige textos raros tipo `FÃ³rmula`, `BebÃ©`, etc.)
- **F** = Título del producto, **G** = Unidades vendidas (del listing)
- Detecta si el producto es **individual / 2 pack / 6 pack / 12 pack**
- Crea:
  - `Cantidad` = **G × multiplicador_pack**
  - `UPC`
  - `Descripcion`
  - `Gramaje` (en **gramos**, ejemplo `1.5kg` → `1500`)
        """
    )

uploaded = st.file_uploader("Sube tu archivo (.xlsx, .xls, .csv)", type=["xlsx", "xls", "csv"])
col1, col2, col3 = st.columns(3)
with col1:
    has_header = st.checkbox("Mi archivo tiene encabezados (headers)", value=True)
with col2:
    csv_sep = st.selectbox("Separador CSV", ["auto", ",", ";"], index=0)
with col3:
    show_mapping = st.checkbox("Mostrar equivalencias cargadas", value=False)

if show_mapping:
    st.write("Equivalencias (normalizadas) cargadas:", len(EQUIV_MAP))
    st.dataframe(
        pd.DataFrame(
            [
                {"Titulo (original)": k, "Multiplicador": v[0], "UPC": v[1], "Descripcion": v[2]}
                for (k, v) in zip([x[0] for x in EQUIV_LIST], [EQUIV_MAP[normalize_key(x[0])] for x in EQUIV_LIST])
            ]
        ),
        use_container_width=True,
        height=250,
    )

if uploaded:
    try:
        df_in = read_uploaded_file(uploaded, has_header=has_header, sep_guess=csv_sep)
        st.success(f"Archivo cargado: {uploaded.name} — Filas: {df_in.shape[0]:,} | Columnas: {df_in.shape[1]:,}")

        df_out = process_df(df_in)

        st.subheader("Vista previa (resultado)")
        st.dataframe(df_out.head(50), use_container_width=True, height=420)

        # Descarga CSV
        csv_bytes = df_out.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Descargar CSV",
            data=csv_bytes,
            file_name="procesado.csv",
            mime="text/csv",
        )

        # Descarga Excel (intenta xlsxwriter u openpyxl; si falla, no rompe la app)
        xlsx_buffer = io.BytesIO()
        xlsx_ok = True
        try:
            with pd.ExcelWriter(xlsx_buffer, engine="xlsxwriter") as writer:
                df_out.to_excel(writer, index=False, sheet_name="Procesado")
        except Exception:
            try:
                xlsx_buffer = io.BytesIO()
                with pd.ExcelWriter(xlsx_buffer, engine="openpyxl") as writer:
                    df_out.to_excel(writer, index=False, sheet_name="Procesado")
            except Exception:
                xlsx_ok = False

        if xlsx_ok:
            st.download_button(
                "Descargar Excel (.xlsx)",
                data=xlsx_buffer.getvalue(),
                file_name="procesado.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.warning("No pude generar .xlsx en este entorno. Usa la descarga CSV (sí funciona).")

        # Reporte de no encontrados
        st.subheader("Diagnóstico: productos no mapeados")
        col_F = df_in.columns[5]
        keys = df_in[col_F].astype(str).apply(normalize_key)
        not_found_mask = ~keys.isin(EQUIV_MAP.keys())
        not_found = df_in.loc[not_found_mask, col_F].astype(str)

        if len(not_found) == 0:
            st.success("Todos los productos en columna F se mapearon correctamente ✅")
        else:
            st.warning(f"Se encontraron {len(not_found):,} filas con productos NO mapeados (se deja UPC/Descripción en blanco).")
            st.dataframe(
                not_found.value_counts().reset_index().rename(columns={"index": "Producto (F)", col_F: "Conteo"}),
                use_container_width=True,
                height=300,
            )

    except Exception as e:
        st.error(f"Error procesando el archivo: {e}")
        st.info("Tip: verifica que tu archivo tenga al menos hasta la columna AI (35 columnas).")
