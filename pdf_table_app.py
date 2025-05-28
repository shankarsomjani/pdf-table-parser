import os
import streamlit as st
import pandas as pd
import io
import re

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

def clean_escape_sequences(text):
    """
    Clean out any HTML/XML escape sequences like "_x000D_", "_x0009_", etc.
    This is specifically to remove unwanted characters like carriage returns, tabs, etc.
    """
    text = re.sub(r'_x000D_|_x0009_|_x000A_|_x0020_|_x000A', ' ', text)  # Replace known escape sequences with spaces
    return text

def normalize_item(text):
    """
    Normalize the text by:
    - Stripping leading/trailing spaces
    - Removing line breaks, tabs, and extra spaces
    - Removing invisible characters
    - Handling escape sequences like "_x000D_"
    """
    text = str(text).strip()
    
    # Clean out escape sequences like _x000D_, _x0009_, etc.
    text = clean_escape_sequences(text)

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
    
    # Debugging: Log the replace dictionary to see the cleaned "Original" and mapped values
    st.write("Replace Dictionary:", replace_dict)

    # Debugging: Log row 139 from the Excel file before replacement
    st.write("Row 139 from Excel data before replacement:", df.iloc[138])  # Remember, DataFrame is 0-indexed

    # Iterate through column A and apply the mappings
    df.iloc[:, 0] = df.iloc[:, 0].apply(lambda x: replace_dict.get(normalize_item(x), x))

    # Log the first few rows after replacement
    st.write("First few rows of Excel data after replacement:", df.head())
    
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
