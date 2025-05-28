import streamlit as st
import pdfplumber
import pandas as pd
import io
from unstract.llmwhisperer import LLMWhispererClientV2
from unstract.llmwhisperer.client_v2 import LLMWhispererClientException
import time

# --- Page setup ---
st.set_page_config(page_title="PDF Table Extractor", layout="centered")
st.title("📄 PDF Table Extractor")

# --- Upload ---
uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")

# --- Mode selection ---
mode = st.radio("Choose extraction mode:", ["Standard (Code-based)", "LLM (via LLMWhisperer)"])

# --- Load API key ---
LLM_API_KEY = st.secrets.get("LLM_API_KEY")  # Or hardcode for local testing

# --- Helper function: LLM Extraction ---
def extract_with_llmwhisperer(file_bytes, filename):
    client = LLMWhispererClientV2(api_key=LLM_API_KEY, logging_level="DEBUG")
    
    try:
        # Step 1: Submit document
        whisper_hash = client.whisper(
            file_bytes=file_bytes,
            filename=filename,
            mode="form",
            output_mode="structured"  # Better chance of Excel output
        )
        
        # Step 2: Poll status
        with st.spinner("⏳ Waiting for LLMWhisperer to process..."):
            status = None
            for _ in range(20):  # Poll for 20 seconds
                result = client.whisper_status(whisper_hash)
                status = result.get("status")
                if status == "processed":
                    break
                elif status in ("failed", "error"):
                    raise RuntimeError(f"Processing failed: {result}")
                time.sleep(1)

        if status != "processed":
            raise TimeoutError("Processing took too long.")

        # Step 3: Retrieve result
        output = client.whisper_retrieve(whisper_hash)
        return output

    except LLMWhispererClientException as e:
        st.error(f"❌ Whisperer API Error: {e}")
    except Exception as e:
        st.error(f"❌ Unexpected error: {e}")

    return None

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
            st.error("❌ Missing LLMWhisperer API key.")
        else:
            file_bytes = uploaded_file.read()
            output = extract_with_llmwhisperer(file_bytes, uploaded_file.name)

            # Show Excel link if available
            if output:
                excel_url = output.get("excel_file_url")
                if excel_url:
                    st.success("✅ LLM extraction complete.")
                    st.markdown(f"[📥 Download Excel File]({excel_url})", unsafe_allow_html=True)
                else:
                    st.warning("⚠️ No Excel file returned by LLMWhisperer.")
