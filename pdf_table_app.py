import streamlit as st
import pdfplumber
import pandas as pd
import io
import tempfile
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
LLM_API_KEY = st.secrets.get("LLM_API_KEY")

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
                whisperer = LLMWhispererClientV2(api_key=LLM_API_KEY)

                # Save uploaded file temporarily
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(uploaded_file.read())
                    temp_file_path = tmp_file.name

                with st.spinner("📤 Uploading to LLMWhisperer..."):
                    job = whisperer.whisper(
                        file_path=temp_file_path,
                        mode="form",
                        output_mode="layout_preserving"
                    )

                with st.spinner("⏳ Waiting for LLMWhisperer to finish processing..."):
                    result = whisperer.wait_for_completion(job)

                if result.status_code == 200 and result.extraction:
                    tables = []
                    for block in result.extraction.get("tables", []):
                        try:
                            data = block.get("data")
                            if isinstance(data, list) and all(isinstance(row, list) for row in data):
                                df = pd.DataFrame(data[1:], columns=data[0]) if len(data) > 1 else pd.DataFrame(data)
                                tables.append(df)
                                st.dataframe(df)
                            else:
                                st.warning(f"⚠️ Skipped a table with invalid structure.")
                        except Exception as e:
                            st.warning(f"⚠️ Failed to render a table: {e}")

                    if tables:
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            for idx, df in enumerate(tables):
                                df.to_excel(writer, sheet_name=f"Table{idx+1}", index=False)
                        st.download_button("📥 Download Excel File", output.getvalue(), "llm_tables.xlsx")
                    else:
                        st.warning("⚠️ No structured tables found in LLMWhisperer response.")
                else:
                    st.warning("⚠️ No extraction results returned by LLMWhisperer.")

            except LLMWhispererClientException as e:
                st.error(f"❌ LLMWhisperer error: {str(e)}")
            except Exception as e:
                st.error(f"❌ Unexpected error: {str(e)}")
