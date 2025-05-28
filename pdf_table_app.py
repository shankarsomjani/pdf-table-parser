import streamlit as st
import pdfplumber
import pandas as pd
import io
from unstract.llmwhisperer import LLMWhispererClientV2
from unstract.llmwhisperer.client_v2 import LLMWhispererClientException

# --- Page setup ---
st.set_page_config(page_title="PDF Table Extractor", layout="centered")
st.title("📄 PDF Table Extractor")

# --- Upload ---
uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")

# --- Mode selection ---
mode = st.radio("Choose extraction mode:", ["Standard (Code-based)", "LLM (via LLMWhisperer)"])

# --- Load API key ---
LLM_API_KEY = st.secrets.get("LLM_API_KEY")  # Add this to .streamlit/secrets.toml

# --- Helper: Convert tables to Excel ---
def convert_tables_to_excel(tables: list[pd.DataFrame]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for idx, df in enumerate(tables, start=1):
            sheet_name = f"Table{idx}"
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return output.getvalue()

# --- Process Uploaded File ---
if uploaded_file:
    if mode == "Standard (Code-based)":
        with pdfplumber.open(uploaded_file) as pdf:
            all_tables = []
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()
                for idx, table in enumerate(tables):
                    if table:
                        df = pd.DataFrame(table[1:], columns=table[0]) if len(table) > 1 else pd.DataFrame(table)
                        all_tables.append(df)

        if all_tables:
            st.success(f"✅ Extracted {len(all_tables)} table(s)")
            for df in all_tables:
                st.dataframe(df)
            excel_data = convert_tables_to_excel(all_tables)
            st.download_button("📥 Download Excel File", excel_data, file_name="tables.xlsx")
        else:
            st.warning("⚠️ No tables found using standard method.")

    elif mode == "LLM (via LLMWhisperer)":
        if not LLM_API_KEY:
            st.error("❌ Missing LLMWhisperer API key. Please set it in Streamlit secrets.")
        else:
            try:
                client = LLMWhispererClientV2(api_key=LLM_API_KEY)
                st.info("🔄 Uploading and processing with LLMWhisperer...")
                with st.spinner("Processing..."):
                    result = client.whisper(
                        uploaded_file.name,
                        uploaded_file.getvalue(),
                        mode="form",
                        output_mode="layout_preserving",
                    )
                    if not result or not result.extraction:
                        st.warning("⚠️ No data returned by LLMWhisperer.")
                    else:
                        # Convert extraction dict to DataFrames
                        tables = []
                        for block in result.extraction.get("tables", []):
                            try:
                                df = pd.DataFrame(block["data"])
                                tables.append(df)
                                st.dataframe(df)
                            except Exception as e:
                                st.warning(f"⚠️ Failed to render a table: {e}")

                        if tables:
                            excel_data = convert_tables_to_excel(tables)
                            st.download_button("📥 Download Excel File", excel_data, file_name="llm_tables.xlsx")
                        else:
                            st.warning("⚠️ No tables found in LLMWhisperer output.")

            except LLMWhispererClientException as e:
                st.error(f"❌ LLMWhisperer API error: {e}")
            except Exception as e:
                st.error(f"❌ Unexpected error: {e}")
