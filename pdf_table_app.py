import streamlit as st
import pdfplumber
import pandas as pd
import io
import requests
import base64

st.set_page_config(page_title="PDF Table Extractor", layout="centered")
st.title("📄 PDF Table Extractor")

# Upload PDF
uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")

# Select extraction mode
mode = st.radio("Choose extraction mode:", ["Standard (Code-based)", "LLM (via LLMWhisperer)"])

LLM_API_KEY = st.secrets.get("LLM_API_KEY", "GR0D-WnPVqT-6Sxg3c-ACBVmlCR4SpubugygvKvwWMM")  # or replace with real key during dev

if uploaded_file:
    if mode == "Standard (Code-based)":
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
            st.warning("⚠️ No tables found using standard method.")

    elif mode == "LLM (via LLMWhisperer)":
        if not LLM_API_KEY or LLM_API_KEY == "GR0D-WnPVqT-6Sxg3c-ACBVmlCR4SpubugygvKvwWMM":
            st.error("❌ Missing or invalid LLMWhisperer API key. Add it to Streamlit secrets or code.")
        else:
            with st.spinner("Uploading to LLMWhisperer..."):
                file_bytes = uploaded_file.read()
                file_b64 = base64.b64encode(file_bytes).decode()

                response = requests.post(
                    "https://llmwhisperer-api.us-central.unstract.com/api/v2/extract",
                    headers={"Authorization": f"Bearer {LLM_API_KEY}"},
                    json={
                        "file_name": uploaded_file.name,
                        "file_data": file_b64,
                        "output_format": "excel"
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    excel_url = result.get("data", {}).get("excel_file_url")
                    if excel_url:
                        st.success("✅ LLM extraction complete.")
                        st.markdown(f"[📥 Download Excel File]({excel_url})", unsafe_allow_html=True)
                    else:
                        st.warning("No Excel file returned by LLMWhisperer.")
                else:
                    st.error(f"❌ LLMWhisperer API error: {response.status_code}")
