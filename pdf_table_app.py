import streamlit as st
import pdfplumber
import pandas as pd
import io
import time
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
                st.spinner("🔄 Uploading to LLMWhisperer and extracting...")
                client = LLMWhispererClientV2(api_key=LLM_API_KEY)
                response = client.whisper(
                    file=uploaded_file,
                    mode="form",
                    output_mode="layout_preserving",
                    filename=uploaded_file.name
                )
                whisper_hash = response.get("whisper_hash")
                if not whisper_hash:
                    st.error("❌ No whisper_hash returned by API.")
                else:
                    st.info("⏳ Waiting for processing to complete...")
                    for _ in range(10):
                        time.sleep(5)
                        status = client.whisper_status(whisper_hash=whisper_hash)
                        if status.get("status") == "processed":
                            break
                    else:
                        st.warning("⚠️ Processing timed out. Try again later.")
                        st.stop()

                    result = client.whisper_retrieve(whisper_hash=whisper_hash)
                    if result:
                        st.success("✅ LLM extraction complete.")
                        st.json(result)
                    else:
                        st.warning("⚠️ No result returned by LLMWhisperer.")

            except LLMWhispererClientException as e:
                st.error(f"❌ API error: {str(e)}")
            except Exception as ex:
                st.error(f"❌ Unexpected error: {str(ex)}")
