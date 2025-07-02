import streamlit as st
import pandas as pd
import numpy as np
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import hashlib

# Page configuration
st.set_page_config(
    page_title="Dog Walking Map",
    page_icon="🐕",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
SHEET_ID = "1mg8d5CLxSR54KhNUL8SpL5jzrGN-bghTsC9vxSK8lR0"
WORKSHEET_NAME = "Map"

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_sheet_data():
    """Load data from Google Sheet"""
    try:
        # Load credentials from Streamlit secrets
        credentials = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        
        # Connect to Google Sheets
        gc = gspread.authorize(credentials)
        sheet = gc.open_by_key(SHEET_ID)
        worksheet = sheet.worksheet(WORKSHEET_NAME)
        
        # Get data using values method to avoid header issues
        all_values = worksheet.get_all_values()
        
        # Define expected headers (based on your sheet structure)
        expected_headers = ['Address', 'Dog Name', 'District', 'Latitude', 'Longitude', 
                          'Number of dogs', 'Filter', 'Today', 'Group', 'Dog ID', 'New Assignment']
        
        if len(all_values) > 0:
            # Use only the columns we need (A through K)
            headers = all_values[0][:len(expected_headers)]
            data_rows = [row[:len(expected_headers)] for row in all_values[1:]]
            
            # Create DataFrame with expected headers
            df = pd.DataFrame(data_rows, columns=expected_headers)
        else:
            df = pd.DataFrame(columns=expected_headers)
        
        # Clean and process data
        if not df.empty:
            # Remove completely empty rows
            df = df[df['Address'].astype(str).str.strip() != '']
            
            # Filter out rows with missing coordinates
            df = df[(df['Latitude'].astype(str).str.strip() != '') & 
                   (df['Longitude'].astype(str).str.strip() != '') & 
                   (df['Latitude'].astype(str) != '0') & 
                   (df['Longitude'].astype(str) != '0')]
            
            # Convert coordinates to numeric
            df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
            df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')
            
            # Convert Number of dogs to numeric, default to 1
            df['Number of dogs'] = pd.to_numeric(df['Number of dogs'], errors='coerce').fillna(1)
            
            # Remove rows with invalid coordinates
            df = df.dropna(subset=['Latitude', 'Longitude'])
            
            # Fill empty strings with appropriate defaults
            df = df.fillna('')
            
        return df, worksheet
        
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        return pd.DataFrame(), None

def generate_colors(unique_values, base_hue=0):
    """Generate distinct, vibrant colors for different categories"""
    # Predefined vibrant colors for better visibility
    vibrant_colors = [
        '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', 
        '#DDA0DD', '#98D8C8', '#FFD93D', '#6C5CE7', '#A29BFE',
        '#FD79A8', '#FDCB6E', '#6C5CE7', '#00B894', '#E17055',
        '#81ECEC', '#FF7675', '#74B9FF', '#00CEC9', '#FDCB6E',
        '#E84393', '#00B894', '#0984E3', '#6C5CE7', '#FD79A8',
        '#FDCB6E', '#55A3FF', '#FF6348', '#26DE81', '#FC427B',
        '#FD79A8', '#FDCB6E', '#55A3FF', '#FF6348', '#26DE81',
        '#FF9F43', '#70A1FF', '#5352ED', '#FF3838', '#2ED573',
        '#1E90FF', '#FF6B35', '#F7931E', '#FFD23F', '#EE5A24',
        '#009432', '#006BA6', '#0582CA', '#00A8CC', '#F18F01'
    ]
    
    colors = {}
    for i, value in enumerate(unique_values):
        if i < len(vibrant_colors):
            colors[value] = vibrant_colors[i]
        else:
            # Fallback to generated colors for more than 50 categories
            hue = (base_hue + (i * 137.508)) % 360
            colors[value] = f"hsl({hue:.0f}, 85%, 55%)"
    
    return colors

def update_sheet_cell(worksheet, row_idx, col_name, new_value, df):
    """Update a single cell in the Google Sheet"""
    try:
        # Column mapping for A through K
        col_map = {
            'Address': 1, 'Dog Name': 2, 'District': 3, 'Latitude': 4, 'Longitude': 5,
            'Number of dogs': 6, 'Filter': 7, 'Today': 8, 'Group': 9, 'Dog ID': 10, 'New Assignment': 11
        }
        
        if col_name in col_map:
            col_idx = col_map[col_name]
            # Add 2 to row_idx: 1 for header row, 1 for 0-based to 1-based indexing
            # But we need to account for the original row position in the sheet
            sheet_row = row_idx + 2  # row_idx is 0-based from our filtered DataFrame
            worksheet.update_cell(sheet_row, col_idx, new_value)
            return True
        return False
        
    except Exception as e:
        st.error(f"Error updating sheet: {str(e)}")
        return False

def main():
    st.title("🐕 Dog Walking Interactive Map")
    
    # Load data
    with st.spinner("Loading data from Google Sheet..."):
        df, worksheet = load_sheet_data()
    
    if df.empty:
        st.error("No data found or unable to connect to Google Sheet")
        st.info("Make sure your service account has access to the Google Sheet")
        return
    
    # Sidebar controls
    st.sidebar.header("Map Controls")
    
    # Color coding options
    color_by = st.sidebar.selectbox(
        "Color markers by:",
        options=["Filter", "District", "Number of dogs"],
        index=0
    )
    
    # Search functionality
    search_term = st.sidebar.text_input("Search dogs/addresses:")
    
    # Filter data based on search
    display_df = df.copy()
    if search_term:
        mask = (df['Dog Name'].astype(str).str.contains(search_term, case=False, na=False) |
                df['Address'].astype(str).str.contains(search_term, case=False, na=False) |
                df['Filter'].astype(str).str.contains(search_term, case=False, na=False))
        display_df = df[mask]
    
    # Map column to use for coloring
    color_col_map = {
        "Filter": "Filter",
        "District": "District", 
        "Number of dogs": "Number of dogs"
    }
    color_column = color_col_map[color_by]
    
    # Generate colors
    unique_values = display_df[color_column].unique()
    color_map = generate_colors(unique_values)
    
    # Create the map
    st.subheader(f"Map View - {len(display_df)} locations")
    
    if not display_df.empty:
        # Create hover text
        display_df['hover_text'] = (
            "<b>" + display_df['Dog Name'].astype(str) + "</b><br>" +
            display_df['Address'].astype(str) + "<br>" +
            "District: " + display_df['District'].astype(str) + "<br>" +
            "Filter: " + display_df['Filter'].astype(str) + "<br>" +
            "Dogs: " + display_df['Number of dogs'].astype(str)
        )
        
        # Create map
        fig = go.Figure()
        
        # Add markers for each category
        for category in unique_values:
            category_data = display_df[display_df[color_column] == category]
            
            fig.add_trace(go.Scattermapbox(
                lat=category_data['Latitude'],
                lon=category_data['Longitude'],
                mode='markers',
                marker=dict(
                    size=12,  # Larger markers
                    color=color_map[category],
                    opacity=0.9
                ),
                text=category_data['hover_text'],
                hovertemplate='%{text}<extra></extra>',
                name=str(category),
                customdata=category_data.index  # Store row indices for editing
            ))
        
        # Update map layout
        fig.update_layout(
            mapbox=dict(
                style="open-street-map",
                center=dict(
                    lat=display_df['Latitude'].mean(),
                    lon=display_df['Longitude'].mean()
                ),
                zoom=11  # Slightly zoomed in for better detail
            ),
            height=700,  # Taller map for better visibility
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=True,
            legend=dict(
                orientation="v",
                yanchor="top",
                y=1,
                xanchor="left",
                x=1.02,
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor="rgba(0,0,0,0.2)",
                borderwidth=1
            )
        )
        
        # Display the map
        map_data = st.plotly_chart(fig, use_container_width=True, key="main_map")
        
        # Legend
        st.subheader("Legend")
        legend_cols = st.columns(min(len(unique_values), 4))
        for i, (category, color) in enumerate(color_map.items()):
            with legend_cols[i % 4]:
                st.markdown(f'<div style="display: flex; align-items: center;"><div style="width: 20px; height: 20px; background-color: {color}; border-radius: 50%; margin-right: 10px; border: 2px solid #333;"></div><span>{category}</span></div>', unsafe_allow_html=True)
    
    # Data editing section
    st.subheader("Edit Dog Information")
    
    if not display_df.empty:
        # Select a dog to edit
        dog_options = [f"{row['Dog Name']} - {row['Address']}" for _, row in display_df.iterrows()]
        selected_dog = st.selectbox("Select a dog to edit:", options=dog_options)
        
        if selected_dog:
            # Find the selected row
            dog_name = selected_dog.split(" - ")[0]
            selected_row = display_df[display_df['Dog Name'] == dog_name].iloc[0]
            selected_idx = selected_row.name
            
            # Create editing form
            with st.form("edit_form"):
                st.write(f"Editing: **{selected_row['Dog Name']}**")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    new_dog_name = st.text_input("Dog Name:", value=selected_row['Dog Name'])
                    new_address = st.text_input("Address:", value=selected_row['Address'])
                    new_district = st.text_input("District:", value=selected_row['District'])
                
                with col2:
                    new_filter = st.text_input("Filter Assignment:", value=selected_row['Filter'])
                    new_num_dogs = st.number_input("Number of Dogs:", value=int(selected_row['Number of dogs']) if pd.notna(selected_row['Number of dogs']) else 1, min_value=1)
                    new_today = st.text_input("Today's Notes:", value=selected_row.get('Today', ''))
                
                # Submit button
                if st.form_submit_button("Update Google Sheet"):
                    if worksheet:
                        success_count = 0
                        updates = [
                            ('Dog Name', new_dog_name),
                            ('Address', new_address),
                            ('District', new_district),
                            ('Filter', new_filter),
                            ('Number of dogs', new_num_dogs),
                            ('Today', new_today)
                        ]
                        
                        for col_name, new_value in updates:
                            if update_sheet_cell(worksheet, selected_idx, col_name, new_value, df):
                                success_count += 1
                        
                        if success_count > 0:
                            st.success(f"Successfully updated {success_count} fields!")
                            st.info("Refresh the page to see changes reflected in the map")
                            # Clear cache to force reload
                            st.cache_data.clear()
                        else:
                            st.error("Failed to update sheet")
                    else:
                        st.error("No connection to Google Sheet")
    
    # Statistics
    st.subheader("Summary Statistics")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Locations", len(df))
    with col2:
        st.metric("Total Dogs", df['Number of dogs'].sum() if 'Number of dogs' in df.columns else 0)
    with col3:
        st.metric("Districts", df['District'].nunique() if 'District' in df.columns else 0)
    with col4:
        st.metric("Showing", len(display_df))
    
    # Refresh button
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

if __name__ == "__main__":
    main()
