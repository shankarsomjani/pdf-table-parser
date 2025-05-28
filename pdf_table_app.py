import os
import streamlit as st
import pandas as pd
import io
import openpyxl
from openpyxl.utils.dataframe import dataframe_to_rows

# --- Function to replace _x000D_ and other unwanted characters ---
def replace_x000d(excel_file):
    # Load the workbook and the active sheet
    wb = openpyxl.load_workbook(excel_file)
    sheet = wb.active
    
    # Iterate through all rows and columns to clean the data
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value and isinstance(cell.value, str):
                # Replace _x000D_ and other unwanted characters
                cleaned_value = cell.value.replace('_x000D_', '').replace('\r', ' ').replace('\n', ' ').strip()
                cell.value = cleaned_value
    
    # Return the cleaned workbook
    return wb

# --- Function to apply company-specific mappings ---
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
    
    replace_dict = {}
    for _, row in company_map.iterrows():
        original = row['Original']
        mapped = row['Mapped']
        
        # Handle None or NaN values safely
        if original and isinstance(original, str) and mapped:
            replace_dict[original.lower()] = mapped
    
    # Apply the mapping replacement, ensure we handle None or NaN properly
    df.iloc[:, 0] = df.iloc[:, 0].apply(lambda x: replace_dict.get(str(x).lower(), x) if pd.notna(x) else x)

    return df

# --- Page setup ---
st.set_page_config(page_title="Excel Table Updater", layout="centered")
st.title("\U0001F4C4 Excel Table Updater")

# --- Load company mapping CSV ---
mapping_df = pd.read_csv("company_mappings.csv") if os.path.exists("company_mappings.csv") else pd.DataFrame(columns=['Company', 'Original', 'Mapped'])
companies = sorted(mapping_df['Company'].unique()) if not mapping_df.empty else []

# --- Company selection ---
selected_company = st.selectbox("Select the company:", companies) if companies else None

# --- Upload processed Excel file ---
uploaded_file = st.file_uploader("Upload the processed Adobe Excel file", type="xlsx")

# --- Process Uploaded Excel File ---
if uploaded_file:
    try:
        # Step 1: Clean the Excel file by removing _x000D_ and other unwanted characters
        wb = replace_x000d(uploaded_file)
        
        # Convert the cleaned workbook back to a dataframe for further processing
        # Extracting the sheet into a dataframe using openpyxl
        sheet = wb.active
        data = sheet.values
        columns = next(data)[0:]  # Get the header
        df = pd.DataFrame(data, columns=columns)

        # Step 2: Handle null values in the Excel dataframe
        # We ensure that any `None` or `NaN` values are handled properly in the Excel data
        df = df.fillna('')  # Fill missing values with empty strings for consistent processing

        # Step 3: Apply company-specific mappings
        if selected_company and not mapping_df.empty:
            df = apply_company_mappings(df, selected_company, mapping_df)

        # Step 4: Save the cleaned and mapped workbook into a BytesIO object
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name=sheet.title)
        
        output.seek(0)

        # Allow user to download the cleaned and mapped Excel file
        st.download_button("📊 Download Cleaned and Updated Excel", output, "cleaned_and_updated.xlsx")
        
        st.success("✅ Excel file cleaned and updated successfully!")

    except Exception as e:
        st.error(f"❌ Error processing the file: {str(e)}")
