import streamlit as st
import pdfplumber
import pandas as pd
import io

st.set_page_config(page_title="PDF Table Extractor", layout="centered")
st.title("📄 PDF Table Extractor")

uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")

if uploaded_file:
    with pdfplumber.open(uploaded_file) as pdf:
        all_tables = []
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            for idx, table in enumerate(tables):
                if table:
                    df = pd.DataFrame(table[1:], columns=table[0]) if len(table) > 1 else pd.DataFrame(table)
                    all_tables.append((f"Page{page_num}_Table{idx+1}", df))

    if all_tables:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            for name, df in all_tables:
                df.to_excel(writer, sheet_name=name[:31], index=False)
        st.success(f"✅ Extracted {len(all_tables)} table(s)")
        st.download_button("📥 Download Excel File", output.getvalue(), "tables.xlsx")
    else:
        st.warning("⚠️ No tables found in the PDF.")
