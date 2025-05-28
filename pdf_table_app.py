import streamlit as st
import pdfplumber
import pandas as pd
import io
from unstract.llmwhisperer import LLMWhispererClientV2
from unstract.llmwhisperer.client_v2 import LLMWhispererClientException

# --- Streamlit page setup ---
st.set_page_config(page_title="PDF Table Extractor", layout="centered")
st.title("📄 PDF Table Extractor")

# --- File uploader ---
uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")

# --- Extraction mode ---
mode = st.radio("Choose extraction mode:", ["Standard (Code-based)", "LLM (via LLMWhisperer)"])

# --- API Key ---
LLM_API_KEY = st.secrets.get("LLM_API_KEY")  # Set this in .streamlit/secrets.toml

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
            st.error("❌ Missing LLMWhisperer API key. Please set it in Streamlit secrets.")
        else:
            try:
                client = LLMWhispererClientV2(api_key=LLM_API_KEY, logging_level="DEBUG")

                with st.spinner("🔄 Uploading to LLMWhisperer and extracting tables..."):
                    whisper_response = client.whisper(
                        file_obj=uploaded_file,
                        filename=uploaded_file.name,
                        mode="form",
                        output_mode="layout_preserving",
                    )

                    result = client.whisper_retrieve(whisper_response.whisper_hash)
                    st.write("🔍 Raw LLM Response:", result)

                    excel_url = result.get("data", {}).get("excel_file_url")
                    if excel_url:
                        st.success("✅ LLM extraction complete.")
                        st.markdown(f"[📥 Download Excel File]({excel_url})", unsafe_allow_html=True)
                    else:
                        st.warning("⚠️ No Excel file returned by LLMWhisperer.")

            except LLMWhispererClientException as e:
                st.error(f"❌ LLMWhisperer error: {str(e)}")
            except Exception as ex:
                st.error(f"❌ Unexpected error: {str(ex)}")
