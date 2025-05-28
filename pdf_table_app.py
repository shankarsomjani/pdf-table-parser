import os
import pandas as pd
import streamlit as st
import io
import re

# --- Utility Functions ---
def sanitize_text(text):
    """
    Sanitize the text by removing non-UTF-8 characters, including problematic characters.
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
    Normalize the text by:
    - Removing line breaks, tabs
    - Replacing multiple spaces with a single space
    - Stripping leading/trailing spaces
    """
    text = str(text).strip()
    
    # Remove all line breaks, tabs, and multiple spaces between words
    text = re.sub(r'\s+', ' ', text)  # Replace any whitespace (newlines, tabs, multiple spaces) with a single space
    text = text.replace('\n', ' ').replace('\r', '').replace('\t', ' ')  # Remove line breaks and tabs
    
    # Remove any non-printable characters, just in case
    text = ''.join(char for char in text if char.isprintable())
    
    # Finally, sanitize the text and normalize it
    text = sanitize_text(text)  # Apply sanitization here
    return text.lower()

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
        # Load the uploaded Excel file
        df = pd.read_excel(uploaded_file, sheet_name=None)  # Read all sheets
        sheet_names = df.keys()
        
        # Select the sheet to process
        selected_sheet = st.selectbox("Select the sheet to update:", sheet_names)
        
        # Get the selected sheet's dataframe
        df = df[selected_sheet]
        
        if selected_company and not mapping_df.empty:
            # Apply company-specific mappings to the dataframe (replace items in column A)
            df = apply_company_mappings(df, selected_company, mapping_df)
            
            st.success(f"✅ Table updated with mappings for {selected_company}")
        
        # Allow user to download the updated file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name=selected_sheet)
        
        output.seek(0)
        st.download_button("📊 Download Updated Excel", output, f"updated_{selected_sheet}.xlsx")
    
    except Exception as e:
        st.error(f"❌ Error processing the file: {str(e)}")
