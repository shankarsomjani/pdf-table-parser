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
LLM_API_KEY = st.secrets.get("LLM_API_KEY")  # Should be set in Streamlit secrets

# --- Function to extract tables using LLMWhisperer ---
def extract_with_llmwhisperer(file_bytes, filename):
    try:
        client = LLMWhispererClientV2(api_key=LLM_API_KEY)
        response = client.process_document(
            file_name=filename,
            file_bytes=file_bytes,
            output_format="excel",
            mode="form",
            output_mode="layout_preserving"
        )

        # Display raw response for debugging (optional)
        st.subheader("LLMWhisperer Raw Response")
        st.json(response)

        # Try to extract Excel URL
        excel_url = response.get("excel_url") or response.get("data", {}).get("excel_url")
        return excel_url

    except LLMWhispererClientException as e:
        st.error(f"❌ LLMWhisperer client error: {e}")
    except Exception as e:
        st.error(f"❌ Unexpected error: {e}")
    return None

# --- Main Logic ---
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
            with st.spinner("🔄 Uploading to LLMWhisperer and extracting tables..."):
                file_bytes = uploaded_file.read()
                excel_url = extract_with_llmwhisperer(file_bytes, uploaded_file.name)

                if excel_url:
                    st.success("✅ LLM extraction complete.")
                    st.markdown(f"[📥 Download Excel File]({excel_url})", unsafe_allow_html=True)
                else:
                    st.warning("⚠️ No Excel file returned by LLMWhisperer.")
