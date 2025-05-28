import streamlit as st
import pdfplumber
import pandas as pd
import io
import os
import time
import zipfile
import re
from datetime import datetime
from openpyxl import load_workbook
from openpyxl.styles import Font
from openpyxl.utils.dataframe import dataframe_to_rows

from unstract.llmwhisperer import LLMWhispererClientV2
from unstract.llmwhisperer.client_v2 import LLMWhispererClientException

from adobe.pdfservices.operation.auth.service_principal_credentials import ServicePrincipalCredentials
from adobe.pdfservices.operation.exception.exceptions import ServiceApiException, ServiceUsageException, SdkException
from adobe.pdfservices.operation.io.stream_asset import StreamAsset
from adobe.pdfservices.operation.pdf_services import PDFServices
from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
from adobe.pdfservices.operation.pdfjobs.jobs.extract_pdf_job import ExtractPDFJob
from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_element_type import ExtractElementType
from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_pdf_params import ExtractPDFParams
from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_renditions_element_type import ExtractRenditionsElementType
from adobe.pdfservices.operation.pdfjobs.result.extract_pdf_result import ExtractPDFResult

# --- Utility Functions ---
def sanitize_text(text):
    """
    This function replaces any problematic characters with a placeholder or removes them.
    Specifically designed to handle surrogate pairs and non-UTF-8 characters.
    """
    try:
        # Remove any surrogate pairs or problematic sequences
        text = text.encode('utf-8', 'ignore').decode('utf-8')
    except UnicodeDecodeError:
        # If still problematic, return an empty string or placeholder
        text = ''.join([c if ord(c) < 128 else '' for c in text])
    return text

def normalize_item(text):
    """
    Normalize the text by stripping and removing unwanted characters.
    """
    text = str(text).strip()
    text = sanitize_text(text)  # Apply sanitization here
    return re.sub(r"^\s*[\(\[\-]?\s*[a-zA-Z0-9]+\s*[\)\.\-]?\s*", "", text).strip().lower()

def apply_company_mappings(df, company, mapping_df):
    """
    Apply company-specific mappings to the dataframe.
    This will replace items in column A based on the CSV mappings.
    """
    if df.empty or df.columns.empty:
        return df
    
    # Get the mappings for the selected company
    company_map = mapping_df[mapping_df['Company'].str.lower() == company.lower()]
    
    if company_map.empty:
        return df  # If no mappings found for the selected company, return the original dataframe
    
    replace_dict = {
        normalize_item(row['Original']): row['Mapped']
        for _, row in company_map.iterrows()
    }
    
    # Iterate through column A and apply the mappings
    df.iloc[:, 0] = df.iloc[:, 0].apply(lambda x: replace_dict.get(normalize_item(x), x))
    
    return df

# --- Page setup ---
st.set_page_config(page_title="PDF Table Extractor", layout="centered")
st.title("\U0001F4C4 PDF Table Extractor")

# --- Load company mapping CSV ---
mapping_df = pd.read_csv("company_mappings.csv") if os.path.exists("company_mappings.csv") else pd.DataFrame(columns=['Company', 'Original', 'Mapped'])
companies = sorted(mapping_df['Company'].unique()) if not mapping_df.empty else []

# --- Company selection ---
selected_company = st.selectbox("Select the company:", companies) if companies else None

# --- Upload ---
uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")

# --- Mode selection ---
mode = st.radio("Choose extraction mode:", ["Standard (Code-based)", "LLM (via LLMWhisperer)", "Adobe PDF Services"])

# --- Load API key ---
LLM_API_KEY = st.secrets.get("LLM_API_KEY")

# --- Adobe credentials ---
ADOBE_CLIENT_ID = os.getenv("PDF_SERVICES_CLIENT_ID")
ADOBE_CLIENT_SECRET = os.getenv("PDF_SERVICES_CLIENT_SECRET")

# --- Adobe Table Formatter ---
def merge_adobe_tables(zip_path: str, selected_company=None) -> bytes:
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Combined Tables"

    table_count = 1
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        file_names = sorted([f for f in zip_ref.namelist() if f.endswith(".xlsx")])
        for file in file_names:
            with zip_ref.open(file) as f:
                df = pd.read_excel(f)
                if df.empty:
                    continue
                
                # Apply company-specific mappings to the dataframe (replace items in column A)
                if selected_company and not mapping_df.empty:
                    df = apply_company_mappings(df, selected_company, mapping_df)
                
                # Add section title
                ws.append([f"Table {table_count}"])
                ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=12)
                # Write the table
                for r in dataframe_to_rows(df, index=False, header=True):
                    ws.append(r)
                # Add 2 blank rows
                ws.append([])
                ws.append([])
                table_count += 1

    wb.save(output)
    output.seek(0)
    return output.getvalue()

# --- Process Uploaded File ---
if uploaded_file:
    if mode == "Adobe PDF Services":
        try:
            st.info("⏳ Extracting using Adobe PDF Services...")
            credentials = ServicePrincipalCredentials(client_id=ADOBE_CLIENT_ID, client_secret=ADOBE_CLIENT_SECRET)
            pdf_services = PDFServices(credentials=credentials)
            input_asset = pdf_services.upload(input_stream=uploaded_file.read(), mime_type=PDFServicesMediaType.PDF)

            extract_pdf_params = ExtractPDFParams(
                elements_to_extract=[ExtractElementType.TEXT, ExtractElementType.TABLES],
                elements_to_extract_renditions=[ExtractRenditionsElementType.TABLES],
                add_char_info=True,
            )

            extract_pdf_job = ExtractPDFJob(input_asset=input_asset, extract_pdf_params=extract_pdf_params)
            location = pdf_services.submit(extract_pdf_job)
            pdf_services_response = pdf_services.get_job_result(location, ExtractPDFResult)

            result_asset = pdf_services_response.get_result().get_resource()
            stream_asset: StreamAsset = pdf_services.get_content(result_asset)

            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            zip_path = f"/tmp/output_adobe_{timestamp}.zip"
            with open(zip_path, "wb") as out_file:
                out_file.write(stream_asset.get_input_stream())

            excel_bytes = merge_adobe_tables(zip_path, selected_company)
            st.success("✅ Adobe PDF Services extraction complete.")
            st.download_button("📊 Download Formatted Excel", excel_bytes, f"adobe_tables_{timestamp}.xlsx")

        except (ServiceApiException, ServiceUsageException, SdkException) as e:
            st.error(f"❌ Adobe API error: {str(e)}")
        except Exception as e:
            st.error(f"❌ Unexpected error: {str(e)}")
