import streamlit as st
import pdfplumber
import pandas as pd
import io
import tempfile
import os
from unstract.llmwhisperer import LLMWhispererClientV2
from unstract.llmwhisperer.client_v2 import LLMWhispererClientException

# --- Setup ---
st.set_page_config(page_title="PDF Table Extractor", layout="centered")
st.title("📄 PDF Table Extractor")

# --- Upload PDF ---
uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")
mode = st.radio("Choose extraction mode:", ["Standard (Code-based)", "LLM (via LLMWhisperer)"])

# --- API Key ---
LLM_API_KEY = st.secrets.get("LLM_API_KEY")

# --- Process File ---
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
        if not LLM_API_KEY:
            st.error("❌ Missing LLMWhisperer API key in Streamlit secrets.")
        else:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(uploaded_file.read())
                    tmp_path = tmp_file.name

                st.info("🔁 Uploading to LLMWhisperer and extracting tables...")
                client = LLMWhispererClientV2(api_key=LLM_API_KEY)
                result = client.whisper(
                    tmp_path,  # Pass file path here
                    mode="form",
                    output_mode="layout_preserving"
                )

                excel_url = result.get("excel_file_url")
                if excel_url:
                    st.success("✅ LLM extraction complete.")
                    st.markdown(f"[📥 Download Excel File]({excel_url})", unsafe_allow_html=True)
                else:
                    st.warning("⚠️ No Excel file returned by LLMWhisperer.")
            except LLMWhispererClientException as e:
                st.error(f"❌ LLMWhisperer error: {str(e)}")
            except Exception as e:
                st.error(f"❌ Unexpected error: {str(e)}")
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
