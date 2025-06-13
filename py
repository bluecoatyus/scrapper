import requests
import json
import pandas as pd
import time
import streamlit as st

# --- CORE FUNCTIONS ---

def get_part_data(mpn_group, api_key):
    """Makes a single API call to Mouser with a group of up to 10 MPNs."""
    MOUSER_API_URL = f'https://api.mouser.com/api/v1.0/search/partnumber?apiKey={api_key}'
    try:
        payload = {'searchByPartRequest': {'mouserPartNumber': mpn_group}}
        headers = {'Content-Type': 'application/json'}
        response = requests.post(MOUSER_API_URL, headers=headers, json=payload)
        
        if response.status_code == 200:
            return response.json()
        else:
            # Simple retry for common intermittent issues
            if response.status_code == 403 or response.status_code == 503:
                st.warning(f"Warning: Received status code {response.status_code}. Retrying in 5 seconds...")
                time.sleep(5)
                response = requests.post(MOUSER_API_URL, headers=headers, json=payload)
                if response.status_code == 200:
                    return response.json()
            
            st.error(f"Error: Received status code {response.status_code} after retry. Body: {response.text}")
            return None
    except requests.RequestException as e:
        st.error(f"Request failed: {e}")
        return None

def group_mpns(mpns, max_per_group=10, low=None, high=None, limit_rows=False):
    """Groups MPNs into pipe-delimited strings for API-level batching."""
    grouped_mpns = []
    current_group = []
    
    # Use slicing if row limits are enabled
    if limit_rows:
        mpns = mpns[low:high]

    for mpn in mpns:
        # Ensure MPN is a string and has no extra whitespace
        current_group.append(str(mpn).strip())
        if len(current_group) == max_per_group:
            grouped_mpns.append("|".join(current_group))
            current_group = []

    # Add any remaining MPNs in the last group
    if current_group:
        grouped_mpns.append("|".join(current_group))

    return grouped_mpns

def read_mpn_csv(uploaded_file):
    """Reads the first column of an uploaded CSV file, ensuring MPNs are treated as text."""
    try:
        # Use dtype='str' to prevent Excel from misinterpreting MPNs as numbers
        df = pd.read_csv(uploaded_file, header=None, dtype=str)
        mpns = df.iloc[:, 0].dropna().tolist() # Get first column, drop empty rows
        return mpns
    except Exception as e:
        st.error(f"Failed to read the uploaded CSV file: {e}")
        return []

def process_api_requests(grouped_mpn_strings, api_key):
    """Processes the list of grouped MPNs, extracts desired data, and shows progress."""
    all_parts_data = []
    total_groups = len(grouped_mpn_strings)
    
    if total_groups == 0:
        st.warning("No MPN groups to process.")
        return []

    progress_bar = st.progress(0, text="Request progress...")
    
    for i, mpn_group in enumerate(grouped_mpn_strings):
        # The 2-second delay helps respect API limits and avoids overwhelming the server
        time.sleep(2) 
        
        response = get_part_data(mpn_group, api_key)
        
        if response and response.get('Errors') == [] and 'SearchResults' in response:
            if response['SearchResults'] is not None:
                for part in response['SearchResults']['Parts']:
                    # --- MODIFICATION ---
                    # Here we extract only the specific fields you want
                    all_parts_data.append({
                        'MPN': part.get('ManufacturerPartNumber', 'N/A'),
                        'Manufacturer': part.get('Manufacturer', 'N/A'),
                        'ImageURL': part.get('ImagePath', 'N/A')
                    })
        
        # Update the progress bar
        progress_text = f"Processing group {i+1} of {total_groups}..."
        progress_bar.progress((i + 1) / total_groups, text=progress_text)
        
    progress_bar.empty() # Clear the progress bar after completion
    return all_parts_data

# --- STREAMLIT UI ---

st.set_page_config(
    page_title="Mouser Data Tool",
    page_icon="🐭",
    layout="centered"
)

st.title("🐭 Mouser MPN Data Extractor")
st.write("This tool uses the Mouser API's batch search to efficiently retrieve the Manufacturer and Image URL for a list of Manufacturer Part Numbers (MPNs).")

with st.expander("Instructions"):
    st.markdown("""
    1.  **Get a Mouser API Key:** You need a free key from Mouser to use this tool.
    2.  **Prepare Your CSV:** Create a CSV file with a single column of your MPNs. There should be no header row.
    3.  **Upload:** Use the uploader below to select your CSV file.
    4.  **Enter API Key:** Paste your key into the text field.
    5.  **Set Range (Optional):** If you have a list larger than 10,000, use the start/stop index to process it in batches over multiple days.
    6.  **Run Request:** Click the button and wait for the process to complete.
    7.  **Download:** Once finished, a download button will appear for your results.
    """)

input_file = st.file_uploader("Upload your MPN list (.csv)", type="csv")

if input_file:
    with st.container(border=True):
        api_key = st.text_input("Mouser API Key", placeholder="Enter your free API key here", type="password")
        st.link_button("Get a free API Key from Mouser", url="https://www.mouser.com/api-search/#signup")
        
        st.subheader("Batching Options")
        limit_rows = st.toggle("Limit range of rows to read from file", value=False, help="Enable this to process a large file in smaller chunks (e.g., 0-9999 on day 1, 10000-19999 on day 2).")
        
        col1, col2 = st.columns(2)
        with col1:
            start_row = st.number_input("Start row index", step=1, min_value=0, disabled=not limit_rows)
        with col2:
            stop_row = st.number_input("Stop row index", step=1, min_value=start_row + 1, value=9999, disabled=not limit_rows)

        # Main logic starts when the button is pressed
        if st.button("▶️ Run Request", use_container_width=True, type="primary"):
            if len(api_key) < 20: # Basic check for a valid key format
                st.error("Please enter a valid Mouser API key to continue.")
            else:
                with st.spinner("Processing... please wait."):
                    mpns = read_mpn_csv(input_file)
                    grouped_mpn_strings = group_mpns(mpns, low=start_row, high=stop_row, limit_rows=limit_rows)

                    st.info(f"Prepared {len(grouped_mpn_strings)} API requests for {stop_row - start_row if limit_rows else len(mpns)} MPNs.")
                    
                    # Process the requests and get the data
                    final_data = process_api_requests(grouped_mpn_strings, api_key)

                if not final_data:
                    st.error("Failed to fetch any results. Please check your API key, MPN list, and range settings.")
                else:
                    st.success(f"Successfully retrieved data for {len(final_data)} parts!")
                    df = pd.DataFrame(final_data)

                    st.dataframe(df, use_container_width=True)

                    # Prepare data for download
                    csv_output = df.to_csv(index=False).encode('utf-8')
                    
                    st.download_button(
                        label="⬇️ Download Results as CSV",
                        data=csv_output,
                        file_name="mouser_output_data.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
