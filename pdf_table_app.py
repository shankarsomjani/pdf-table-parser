import os
import time
import streamlit as st
import pandas as pd
import io
import zipfile
from datetime import datetime
import openpyxl
from openpyxl.styles import Font
from openpyxl.utils.dataframe import dataframe_to_rows
import re

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

# --- Function to replace _x000D_ and other unwanted characters ---
def replace_x000d(excel_file):
    wb = openpyxl.load_workbook(excel_file)
    sheet = wb.active
    
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value and isinstance(cell.value, str):
                # Replace unwanted characters and line breaks
                cleaned_value = cell.value.replace('_x000D_', '').replace('\r', ' ').replace('\n', ' ').strip()
                cell.value = cleaned_value
    
    return wb

# --- Function to clean prefixes like "a)", "b)" and similar ---
def clean_prefixes(text):
    text = str(text).strip()  # Convert to string and remove leading/trailing spaces
    text = re.sub(r"^[a-zA-Z\)\-\.\s]+", "", text)  # Remove any leading 'a)', 'b)', '-', etc.
    return text

# --- Function to apply company-specific mappings ---
def apply_company_mappings(df, company, mapping_df):
    if df.empty or df.columns.empty:
        return df
    
    company_map = mapping_df[mapping_df['Company'].str.lower() == company.lower()]
    
    if company_map.empty:
        return df  # If no mappings found for the selected company, return the original dataframe
    
    replace_dict = {}
    for _, row in company_map.iterrows():
        original = row['Original']
        mapped = row['Mapped']
        
        if original and isinstance(original, str) and mapped:
            replace_dict[original.lower()] = mapped
    
    # Apply the mapping replacement after cleaning prefixes
    df.iloc[:, 0] = df.iloc[:, 0].apply(lambda x: replace_dict.get(str(x).lower(), x) if pd.notna(x) else x)

    return df

# --- Adobe Table Formatter ---
def merge_adobe_tables(zip_path: str) -> bytes:
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')
    wb = openpyxl.Workbook()
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
                ws.append([f"Table {table_count}"])
                ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=12)
                for r in dataframe_to_rows(df, index=False, header=True):
                    ws.append(r)
                ws.append([])
                ws.append([])
                table_count += 1

    wb.save(output)
    output.seek(0)
    return output.getvalue()

# --- Function to Extract PDF using Adobe PDF Services ---
def extract_pdf_with_adobe(uploaded_pdf):
    credentials = ServicePrincipalCredentials(client_id=os.getenv("PDF_SERVICES_CLIENT_ID"), client_secret=os.getenv("PDF_SERVICES_CLIENT_SECRET"))
    pdf_services = PDFServices(credentials=credentials)
    input_asset = pdf_services.upload(input_stream=uploaded_pdf, mime_type=PDFServicesMediaType.PDF)

    extract_pdf_params = ExtractPDFParams(
        elements_to_extract=[ExtractElementType.TEXT, ExtractElementType.TABLES],
        elements_to_extract_renditions=[ExtractRenditionsElementType.TABLES],
        add_char_info=True,
    )

    extract_pdf_job = ExtractPDFJob(input_asset=input_asset, extract_pdf_params=extract_pdf_params)
    location = pdf_services.submit(extract_pdf_job)
    
    try:
        pdf_services_response = pdf_services.get_job_result(location, ExtractPDFResult)
        # Check if the response is valid
        if pdf_services_response is None or pdf_services_response.get_result() is None:
            raise ValueError("Adobe PDF Services did not return valid results.")

        result_asset = pdf_services_response.get_result().get_resource()
        stream_asset: StreamAsset = pdf_services.get_content(result_asset)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        zip_path = f"/tmp/output_adobe_{timestamp}.zip"
        with open(zip_path, "wb") as out_file:
            out_file.write(stream_asset.get_input_stream())

        return zip_path
    
    except Exception as e:
        raise ValueError(f"Error occurred while extracting PDF using Adobe API: {str(e)}")

# --- Streamlit Page Setup ---
st.set_page_config(page_title="PDF Table Extractor & Excel Updater", layout="centered")
st.title("\U0001F4C4 PDF Table Extractor & Excel Updater")

# --- Upload PDF file ---
uploaded_pdf = st.file_uploader("Upload a PDF file", type="pdf")

# --- Mode selection ---
mode = st.radio("Choose extraction mode:", ["Standard (Code-based)", "LLM (via LLMWhisperer)", "Adobe PDF Services"])

# --- Company Mapping CSV File ---
mapping_df = pd.read_csv("company_mappings.csv") if os.path.exists("company_mappings.csv") else pd.DataFrame(columns=['Company', 'Original', 'Mapped'])
companies = sorted(mapping_df['Company'].unique()) if not mapping_df.empty else []

selected_company = st.selectbox("Select the company:", companies) if companies else None

# --- Process Uploaded PDF File ---
if uploaded_pdf:
    if mode == "Adobe PDF Services":
        try:
            st.info("⏳ Extracting using Adobe PDF Services...")
            zip_path = extract_pdf_with_adobe(uploaded_pdf)

            # Step 2: Merge Excel files from ZIP and clean them
            excel_bytes = merge_adobe_tables(zip_path)

            # Step 3: Process the merged Excel file (This is where cleaning happens)
            wb = replace_x000d(io.BytesIO(excel_bytes))
            sheet = wb.active
            data = sheet.values
            columns = next(data)[0:]
            df = pd.DataFrame(data, columns=columns)

            # Step 4: Handle null values
            df = df.fillna('')

            # Step 5: Clean up prefixes in the first column
            df.iloc[:, 0] = df.iloc[:, 0].apply(lambda x: clean_prefixes(str(x)) if pd.notna(x) else x)

            # Step 6: Apply company mappings (replace strings in the first column)
            if selected_company and not mapping_df.empty:
                df = apply_company_mappings(df, selected_company, mapping_df)

            # Step 7: Save and allow download
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name=sheet.title)

            output.seek(0)
            st.download_button("📊 Download Cleaned and Updated Excel", output, "cleaned_and_updated.xlsx")

            st.success("✅ Excel file cleaned and updated successfully!")

        except Exception as e:
            st.error(f"❌ Error processing the file: {str(e)}")
