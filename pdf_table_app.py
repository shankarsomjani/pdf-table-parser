import streamlit as st
import pdfplumber
import pandas as pd
import io
import os
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
            st.download_button("📅 Download Excel File", output.getvalue(), "tables.xlsx")
        else:
            st.warning("⚠️ No tables found using standard method.")

    elif mode == "LLM (via LLMWhisperer)":
        if not LLM_API_KEY:
            st.error("❌ Missing LLMWhisperer API key. Please set it in Streamlit secrets.")
        else:
            try:
                with st.spinner("🔄 Sending file to LLMWhisperer..."):
                    whisperer = LLMWhispererClientV2(api_key=LLM_API_KEY, logging_level="DEBUG")

                    temp_path = "/tmp/uploaded_llm.pdf"
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_file.read())

                    job_info = whisperer.whisper(
                        file_path=temp_path,
                        filename=uploaded_file.name,
                        mode="form",
                        output_mode="layout_preserving"
                    )

                    whisper_hash = job_info.get("whisper_hash")
                    if not whisper_hash:
                        st.error("❌ Failed to initiate LLMWhisperer job.")
                        st.stop()

                    # Polling until status is processed
                    st.info("⏳ Waiting for LLMWhisperer to process the file...")
                    status = None
                    for _ in range(20):  # Max ~40 seconds
                        status_info = whisperer.whisper_status(whisper_hash=whisper_hash)
                        status = status_info.get("status")
                        if status == "processed":
                            break
                        elif status == "error":
                            st.error("❌ LLMWhisperer reported an error while processing the document.")
                            st.stop()
                        time.sleep(2)

                    if status != "processed":
                        st.warning("⚠️ Timed out waiting for LLMWhisperer to finish processing.")
                        st.stop()

                    result = whisperer.whisper_retrieve(whisper_hash=whisper_hash)
                    st.success("✅ LLMWhisperer processing complete.")
                    st.subheader("LLMWhisperer Extracted Output:")
                    st.json(result)

            except LLMWhispererClientException as e:
                st.error(f"❌ LLMWhisperer API error: {str(e)}")
            except Exception as e:
                st.error(f"❌ Unexpected error: {str(e)}")
