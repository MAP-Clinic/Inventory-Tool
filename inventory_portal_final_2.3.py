import streamlit as st
import pandas as pd
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import os
import requests

# --- FIELD DEFINITIONS (GLOBAL) ---
manual_entry_fields = [
    ("Department", "Department", ["Manassas", "FCPS", "Culmore"]),
    ("Vendor", "Vendor", None),
    ("Item", "Item Name", None),
    ("Location", "Location", ["Cabinet", "Front Desk", "Hall Bathroom", "Lab", "Kitchen Cabinet", "Team Room", "Other"]),
    ("Unit", "Unit (e.g., Box, Bottle)", None),
    ("Qty", "Qty", None),
    ("Par Level", "Par Level", None),
    ("Value", "Value per Unit ($)", None),
    ("Frequency", "Frequency (e.g., Monthly, Weekly)", None),
    ("Date Ordered", "Date Ordered", None),
    ("Total Cost", "Total Cost", None)
]

# --- LOGIN PAGE ---
def login():
    st.title("MAP Inventory Portal Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username == "MAP" and password == "P01!12":
            st.session_state.logged_in = True
        else:
            st.error("Invalid credentials")

# --- INVENTORY ENTRY FORM ---
def inventory_form():
    st.header("📋 Add Inventory Item")
    file_type = st.selectbox("What type of file are you uploading?", ["Select...", "Inventory Report", "Amazon Report", "Mckesson Report"], key="file_type_select")
    st.caption("You can upload .xlsx, .xls, or .csv files.")
    uploaded_report = st.file_uploader("Upload a file to continue (Excel or CSV)", type=["xlsx", "xls", "csv"], key="inv_excel_upload")
    # --- Amazon Report robust upload/merge logic ---
    if uploaded_report is not None and file_type == "Amazon Report":
        if 'upload_review_idx' not in st.session_state:
            st.session_state.upload_review_idx = 0
        if 'upload_review_rows' not in st.session_state:
            st.session_state.upload_review_rows = []
        if st.session_state.upload_review_idx == 0:
            try:
                if uploaded_report.name.endswith('.csv'):
                    df_upload = pd.read_csv(uploaded_report)
                else:
                    df_upload = pd.read_excel(uploaded_report, header=1)
                df_upload.columns = df_upload.columns.str.strip()
                csv_to_manual = {
                    "Department": "Department Name",
                    "Vendor": "Brand",
                    "Item": "Title",
                    "Location": None,
                    "Unit": "Brand",
                    "Qty": "Item Quantity",
                    "Par Level": None,
                    "Value": "Item Price",
                    "Frequency": None,
                    "Date Ordered": "Order Date",
                    "Total Cost": "Order Subtotal"
                }
                st.session_state.upload_review_rows = []
                for _, row in df_upload.iterrows():
                    entry = {}
                    for field, label, options in manual_entry_fields:
                        csv_col = csv_to_manual.get(field)
                        val = None
                        if csv_col and csv_col in df_upload.columns:
                            val = row.get(csv_col, "")
                        if field == "Qty":
                            try:
                                val = int(val)
                            except:
                                val = None
                        if field == "Value" or field == "Total Cost":
                            try:
                                val = float(val)
                            except:
                                val = 0.0
                        if field == "Par Level":
                            val = 0
                        if field == "Date Ordered":
                            if val:
                                try:
                                    val = pd.to_datetime(val).date()
                                except:
                                    val = datetime.today().date()
                            else:
                                val = datetime.today().date()
                        entry[field] = val
                    if (entry["Total Cost"] is None or entry["Total Cost"] == 0.0):
                        qty = entry.get("Qty", None)
                        value = entry.get("Value", 0.0)
                        if qty is not None:
                            entry["Total Cost"] = qty * value
                        else:
                            entry["Total Cost"] = value
                    st.session_state.upload_review_rows.append(entry)
            except Exception as e:
                st.error(f"❌ Error reading uploaded file: {e}")
        # Step-by-step review UI
        if st.session_state.upload_review_rows and st.session_state.upload_review_idx < len(st.session_state.upload_review_rows):
            idx = st.session_state.upload_review_idx
            entry = st.session_state.upload_review_rows[idx]
            with st.form(f"review_row_form_{idx}"):
                for field, label, options in manual_entry_fields:
                    val = entry[field]
                    if isinstance(val, str) and len(val) > 60:
                        val = val[:60] + '...'
                    if options:
                        val = st.selectbox(label, options, index=options.index(val) if val in options else 0, key=f"review_{field}_{idx}")
                    elif field == "Date Ordered":
                        val = st.date_input(label, value=val, key=f"review_{field}_{idx}")
                    elif field == "Qty":
                        val = st.number_input(label, min_value=0, step=1, value=val if val is not None else 0, key=f"review_{field}_{idx}")
                    elif field == "Par Level":
                        val = st.number_input(label, min_value=0, step=1, value=val if val is not None else 0, key=f"review_{field}_{idx}")
                    elif field == "Value" or field == "Total Cost":
                        val = st.number_input(label, min_value=0.0, step=0.01, value=val if val is not None else 0.0, key=f"review_{field}_{idx}")
                    else:
                        val = st.text_input(label, value=val if val is not None else "", key=f"review_{field}_{idx}")
                    entry[field] = val
                submitted = st.form_submit_button("Submit Entry")
                if submitted:
                    if isinstance(entry["Date Ordered"], (datetime, pd.Timestamp)):
                        entry["Date Ordered"] = entry["Date Ordered"].strftime("%Y-%m-%d")
                    elif isinstance(entry["Date Ordered"], str):
                        entry["Date Ordered"] = pd.to_datetime(entry["Date Ordered"]).strftime("%Y-%m-%d")
                        entry["Date Ordered"] = str(entry["Date Ordered"])
                    st.session_state.inventory_data.append(entry)
                    st.session_state.upload_review_idx += 1
                    st.session_state.need_rerun = True
        elif st.session_state.upload_review_rows:
            st.success("All uploaded entries have been reviewed and added.")
            st.session_state.upload_review_rows = []
            st.session_state.upload_review_idx = 0
    # --- Inventory Report robust upload/merge logic ---
    elif uploaded_report is not None and file_type == "Inventory Report":
        if 'upload_review_idx' not in st.session_state:
            st.session_state.upload_review_idx = 0
        if 'upload_review_rows' not in st.session_state:
            st.session_state.upload_review_rows = []
        if st.session_state.upload_review_idx == 0:
            try:
                if uploaded_report.name.endswith('.csv'):
                    df_upload = pd.read_excel(uploaded_report, header=1)
                else:
                    df_upload = pd.read_excel(uploaded_report, header=1)
                df_upload.columns = df_upload.columns.str.strip()
                # --- Column mapping UI ---
                manual_fields = [f[0] for f in manual_entry_fields]
                st.write('### Map columns from your file to inventory fields:')
                col_map = {}
                for field in manual_fields:
                    options = [None] + list(df_upload.columns)
                    default_idx = options.index(field) if field in options else 0
                    col_map[field] = st.selectbox(f"Map for '{field}'", options, index=default_idx, key=f"inv_map_{field}")
                if st.button("Confirm Column Mapping", key="inv_confirm_mapping"):
                    st.session_state.inv_col_map = col_map
                    st.session_state.inv_mapping_confirmed = True
                if st.session_state.get('inv_mapping_confirmed', False):
                    st.session_state.upload_review_rows = []
                    for _, row in df_upload.iterrows():
                        entry = {}
                        for field, label, options in manual_entry_fields:
                            file_col = st.session_state.inv_col_map.get(field)
                            val = row.get(file_col, "") if file_col else ""
                            if field == "Qty":
                                try:
                                    val = int(val)
                                except:
                                    val = None
                            if field == "Value" or field == "Total Cost":
                                try:
                                    val = float(val)
                                except:
                                    val = 0.0
                            if field == "Par Level":
                                val = 0
                            if field == "Date Ordered":
                                if val:
                                    try:
                                        val = pd.to_datetime(val).date()
                                    except:
                                        val = datetime.today().date()
                                else:
                                    val = datetime.today().date()
                            entry[field] = val
                        if (entry["Total Cost"] is None or entry["Total Cost"] == 0.0):
                            qty = entry.get("Qty", None)
                            value = entry.get("Value", 0.0)
                            if qty is not None:
                                entry["Total Cost"] = qty * value
                            else:
                                entry["Total Cost"] = value
                        st.session_state.upload_review_rows.append(entry)
            except Exception as e:
                st.error(f"❌ Error reading uploaded file: {e}")
        # Step-by-step review UI (same as Amazon Report)
        if st.session_state.upload_review_rows and st.session_state.upload_review_idx < len(st.session_state.upload_review_rows):
            idx = st.session_state.upload_review_idx
            entry = st.session_state.upload_review_rows[idx]
            with st.form(f"review_row_form_{idx}"):
                for field, label, options in manual_entry_fields:
                    val = entry[field]
                    if isinstance(val, str) and len(val) > 60:
                        val = val[:60] + '...'
                    if options:
                        val = st.selectbox(label, options, index=options.index(val) if val in options else 0, key=f"review_{field}_{idx}")
                    elif field == "Date Ordered":
                        val = st.date_input(label, value=val, key=f"review_{field}_{idx}")
                    elif field == "Qty":
                        val = st.number_input(label, min_value=0, step=1, value=val if val is not None else 0, key=f"review_{field}_{idx}")
                    elif field == "Par Level":
                        val = st.number_input(label, min_value=0, step=1, value=val if val is not None else 0, key=f"review_{field}_{idx}")
                    elif field == "Value" or field == "Total Cost":
                        val = st.number_input(label, min_value=0.0, step=0.01, value=val if val is not None else 0.0, key=f"review_{field}_{idx}")
                    else:
                        val = st.text_input(label, value=val if val is not None else "", key=f"review_{field}_{idx}")
                    entry[field] = val
                submitted = st.form_submit_button("Submit Entry")
                if submitted:
                    if isinstance(entry["Date Ordered"], (datetime, pd.Timestamp)):
                        entry["Date Ordered"] = entry["Date Ordered"].strftime("%Y-%m-%d")
                    elif isinstance(entry["Date Ordered"], str):
                        entry["Date Ordered"] = pd.to_datetime(entry["Date Ordered"]).strftime("%Y-%m-%d")
                        entry["Date Ordered"] = str(entry["Date Ordered"])
                    st.session_state.inventory_data.append(entry)
                    st.session_state.upload_review_idx += 1
                    st.session_state.need_rerun = True
        elif st.session_state.upload_review_rows:
            st.success("All uploaded entries have been reviewed and added.")
            st.session_state.upload_review_rows = []
            st.session_state.upload_review_idx = 0
            st.session_state.inv_mapping_confirmed = False
            st.session_state.inv_col_map = {}
    # --- Mckesson Report logic ---
    elif uploaded_report is not None and file_type == "Mckesson Report":
        if 'mckesson_review_idx' not in st.session_state:
            st.session_state.mckesson_review_idx = 0
        if 'mckesson_review_rows' not in st.session_state:
            st.session_state.mckesson_review_rows = []
        if 'mckesson_cost_left' not in st.session_state:
            st.session_state.mckesson_cost_left = []
        if st.session_state.mckesson_review_idx == 0 and not st.session_state.mckesson_review_rows:
            try:
                if uploaded_report.name.endswith('.csv'):
                    df_upload = pd.read_csv(uploaded_report)
                elif uploaded_report.name.endswith('.xls'):
                    df_upload = pd.read_excel(uploaded_report, engine='xlrd')
                else:
                    df_upload = pd.read_excel(uploaded_report, header=1)
                # Assume column F is index 5, column H is index 7
                for _, row in df_upload.iterrows():
                    date_val = row.iloc[5] if len(row) > 5 else ''
                    total_cost = row.iloc[7] if len(row) > 7 else 0.0
                    try:
                        date_val = pd.to_datetime(date_val).date()
                    except:
                        date_val = datetime.today().date()
                    try:
                        total_cost = float(total_cost)
                    except:
                        total_cost = 0.0
                    st.session_state.mckesson_review_rows.append({
                        'Date Ordered': date_val,
                        'Total Cost': total_cost
                    })
                    st.session_state.mckesson_cost_left.append(total_cost)
            except Exception as e:
                st.error(f"❌ Error reading uploaded file: {e}")
        # Step-by-step manual entry and cost allocation
        if st.session_state.mckesson_review_rows and st.session_state.mckesson_review_idx < len(st.session_state.mckesson_review_rows):
            idx = st.session_state.mckesson_review_idx
            entry = st.session_state.mckesson_review_rows[idx]
            cost_left = st.session_state.mckesson_cost_left[idx]
            st.info(f"Row {idx+1}: Total Cost to allocate: ${cost_left:,.2f}")
            with st.form(f"mckesson_row_form_{idx}"):
                st.write(f"Date Ordered: {entry['Date Ordered']}")
                manual_fields = [f for f in manual_entry_fields if f[0] not in ["Date Ordered", "Total Cost"]]
                manual_entry = {}
                for field, label, options in manual_fields:
                    if options:
                        val = st.selectbox(label, options, key=f"mckesson_{field}_{idx}")
                    elif field == "Qty" or field == "Par Level":
                        val = st.number_input(label, min_value=0, step=1, key=f"mckesson_{field}_{idx}")
                    elif field == "Value":
                        val = st.number_input(label, min_value=0.0, step=0.01, key=f"mckesson_{field}_{idx}")
                    else:
                        val = st.text_input(label, key=f"mckesson_{field}_{idx}")
                    manual_entry[field] = val
                alloc_cost = st.number_input("Allocate Cost for this entry", min_value=0.0, max_value=cost_left, step=0.01, key=f"mckesson_alloc_cost_{idx}")
                submitted = st.form_submit_button("Submit Entry")
                if submitted:
                    if alloc_cost > 0:
                        new_row = {**manual_entry,
                                   "Date Ordered": entry['Date Ordered'],
                                   "Total Cost": alloc_cost}
                        st.session_state.inventory_data.append(new_row)
                        st.session_state.mckesson_cost_left[idx] -= alloc_cost
                        st.success(f"Allocated ${alloc_cost} of cost.")
                    else:
                        st.warning("Allocated cost must be greater than 0.")
        elif st.session_state.mckesson_review_rows:
            st.success("All Mckesson report entries have been reviewed and added.")
            st.session_state.mckesson_review_rows = []
            st.session_state.mckesson_review_idx = 0

    # --- MANUAL ENTRY FORM ---
    with st.form("manual_entry_form"):
        department = st.selectbox("Department", ["Manassas", "FCPS", "Culmore"])
        vendor = st.text_input("Vendor")
        item = st.text_input("Item Name")
        location = st.selectbox(
            "Location", ["Cabinet", "Front Desk", "Hall Bathroom", "Lab", "Kitchen Cabinet", "Team Room", "Other"]
        )
        if location == "Other":
            location = st.text_input("Specify Other Location")
        unit = st.text_input("Unit (e.g., Box, Bottle)")
        qty = st.number_input("Qty", min_value=0, step=1)
        par_level = st.number_input("Par Level", min_value=0, step=1)
        value = st.number_input("Value per Unit ($)", min_value=0.0, step=0.01)
        frequency = st.text_input("Frequency (e.g., Monthly, Weekly)")
        date_ordered = st.date_input("Date Ordered", datetime.today())
        total_cost = st.number_input("Total Cost", min_value=0.0, step=0.01)
        submitted = st.form_submit_button("Submit")
        if submitted:
            new_row = {
                "Department": department,
                "Vendor": vendor,
                "Item": item,
                "Location": location,
                "Unit": unit,
                "Qty": qty,
                "Par Level": par_level,
                "Value": value,
                "Frequency": frequency,
                "Date Ordered": date_ordered.strftime("%Y-%m-%d"),
                "Total Cost": total_cost
            }
            st.session_state.inventory_data.append(new_row)
            st.success("✅ Inventory item submitted successfully.")

# --- DISPLAY INVENTORY TABLE + METRICS ---
def display_inventory_table():
    df = pd.DataFrame(st.session_state.inventory_data)

    # Ensure 'Total Cost' column exists and is numeric
    if 'Total Cost' not in df.columns:
        df['Total Cost'] = 0.0
    else:
        df['Total Cost'] = pd.to_numeric(df['Total Cost'], errors='coerce').fillna(0.0)
    # Optionally recalculate if Qty and Value are present but Total Cost is missing/zero
    if 'Qty' in df.columns and 'Value' in df.columns:
        mask = (df['Total Cost'] == 0) & (df['Qty'].notnull()) & (df['Value'].notnull())
        df.loc[mask, 'Total Cost'] = df.loc[mask, 'Qty'].astype(float) * df.loc[mask, 'Value'].astype(float)

    st.subheader("📊 Inventory Metrics")
    st.metric("Total Inventory Items", len(df))
    st.metric("Total Estimated Cost", f"${df['Total Cost'].sum():,.2f}")

    st.subheader("📦 Inventory Table")

    # Undo delete button (always show if a row was deleted, even if table is empty)
    if 'last_deleted_row' in st.session_state and st.session_state.last_deleted_row is not None:
        st.warning("Last row deleted. You can undo this action.")
        if st.button("Undo Delete", key="undo_delete"):
            idx = st.session_state.get('last_deleted_idx', len(st.session_state.inventory_data))
            st.session_state.inventory_data.insert(idx, st.session_state.last_deleted_row)
            st.session_state.last_deleted_row = None
            st.session_state.last_deleted_idx = None
            st.session_state.need_rerun = True

    # --- Streamlit columns for single-line, inline buttons ---
    if not df.empty:
        col_names = list(df.columns) + ["Edit", "Delete"]
        header_cols = st.columns(len(col_names))
        for i, col in enumerate(col_names):
            header_cols[i].markdown(f"**{col}**")
        for idx, row in df.iterrows():
            row_cols = st.columns(len(col_names))
            for i, col in enumerate(df.columns):
                val = row[col]
                val_disp = str(val)
                if isinstance(val, str) and len(val) > 15:
                    val_disp = val[:15] + '...'
                row_cols[i].markdown(f'<span title="{str(val)}">{val_disp}</span>', unsafe_allow_html=True)
            if row_cols[-2].button("✏️", key=f"edit_{idx}", help="Edit this row"):
                st.session_state.edit_row_idx = idx
            if row_cols[-1].button("🗑️", key=f"delete_{idx}", help="Delete this row"):
                # Save deleted row and index for undo
                st.session_state.last_deleted_row = row.to_dict()
                st.session_state.last_deleted_idx = idx
                st.session_state.inventory_data.pop(idx)
                st.session_state.need_rerun = True
    else:
        st.info("No inventory data to display.")

    # Edit form
    if 'edit_row_idx' in st.session_state:
        edit_idx = st.session_state.edit_row_idx
        edit_row = st.session_state.inventory_data[edit_idx]
        with st.form(f"edit_row_form_{edit_idx}"):
            for field, label, options in manual_entry_fields:
                val = edit_row.get(field, "")
                if isinstance(val, str) and len(val) > 60:
                    val = val[:60] + '...'
                if options:
                    val = st.selectbox(label, options, index=options.index(val) if val in options else 0, key=f"edit_{field}_{edit_idx}")
                elif field == "Date Ordered":
                    val = st.date_input(label, value=pd.to_datetime(val).date() if val else datetime.today().date(), key=f"edit_{field}_{edit_idx}")
                elif field == "Qty" or field == "Par Level":
                    val = st.number_input(label, min_value=0, step=1, value=val if val != '' else 0, key=f"edit_{field}_{edit_idx}")
                elif field == "Value" or field == "Total Cost":
                    val = st.number_input(label, min_value=0.0, step=0.01, value=val if val != '' else 0.0, key=f"edit_{field}_{edit_idx}")
                else:
                    val = st.text_input(label, value=val if val is not None else "", key=f"edit_{field}_{edit_idx}")
                edit_row[field] = val
            total_cost = edit_row["Qty"] * edit_row["Value"]
            submitted = st.form_submit_button("Save Changes")
            if submitted:
                edit_row["Total Cost"] = total_cost
                if isinstance(edit_row["Date Ordered"], (datetime, pd.Timestamp)):
                    edit_row["Date Ordered"] = edit_row["Date Ordered"].strftime("%Y-%m-%d")
                elif isinstance(edit_row["Date Ordered"], str):
                    edit_row["Date Ordered"] = pd.to_datetime(edit_row["Date Ordered"]).strftime("%Y-%m-%d")
                    edit_row["Date Ordered"] = str(edit_row["Date Ordered"])
                st.session_state.inventory_data[edit_idx] = edit_row
                del st.session_state.edit_row_idx
                st.success("Entry updated.")
                st.experimental_rerun()
                st.session_state.need_rerun = True
    # Add rerun trigger at the end of the function
    if st.session_state.get("need_rerun", False):
        st.session_state.need_rerun = False
        if hasattr(st, "experimental_rerun"):
            try:
                st.experimental_rerun()
            except Exception:
                pass
    # Download button for inventory report with highlight
    import io
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventory')
        workbook = writer.book
        worksheet = writer.sheets['Inventory']
        # Find the column index for 'Par Level' if it exists
        if 'Par Level' in df.columns:
            par_col_idx = df.columns.get_loc('Par Level')
            highlight_format = workbook.add_format({'bg_color': '#FFCCCC'})
            for row_idx, par_value in enumerate(df['Par Level'], start=1):  # start=1 to skip header
                if par_value <= 2:
                    worksheet.set_row(row_idx, None, highlight_format)
    output.seek(0)
    st.download_button(
        label="📥 Download Inventory Report (Excel)",
        data=output,
        file_name="inventory_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# --- METRICS TAB ---
def calculate_metrics(df):
    metrics = {}
    metrics['total_cost'] = df['Price'].sum()
    cost_per_location = df.groupby('Client #')['Price'].sum().reset_index()
    metrics['total_cost_per_location'] = cost_per_location.to_dict(orient='records')
    ordering_per_provider_labtype = df.groupby(['Ref. Phy.', 'Description of Service']).size().reset_index(name='Order_Count')
    metrics['ordering_per_provider_labtype'] = ordering_per_provider_labtype.to_dict(orient='records')
    cost_per_provider = df.groupby('Ref. Phy.')['Price'].sum().reset_index()
    metrics['total_cost_per_provider'] = cost_per_provider.to_dict(orient='records')
    lab_type_count = df['Description of Service'].value_counts().reset_index()
    lab_type_count.columns = ['Description of Service', 'count']
    metrics['lab_type_count'] = lab_type_count.to_dict(orient='records')
    return metrics

def metrics_tab():
    st.header("📊 Upload Metrics Excel (De-identified)")
    metrics_file = st.file_uploader("Upload Excel file for Metrics (de-identified only)", type=["xlsx"], key="metrics_excel")
    if metrics_file is not None:
        df = pd.read_excel(metrics_file)
        df.columns = df.columns.str.strip()
        st.write("Data Preview", df.head())
        required_columns = ['Price', 'Client #', 'Ref. Phy.', 'Description of Service']
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            st.error(f"❌ Missing required column(s): {missing}")
        else:
            metrics = calculate_metrics(df)
            st.write("💰 Total Cost", metrics['total_cost'])
            st.write("🏥 Cost per Client", metrics['total_cost_per_location'])
            st.write("📦 Orders per Provider and Lab Type", metrics['ordering_per_provider_labtype'])
            st.write("🧾 Total Cost per Provider", metrics['total_cost_per_provider'])
            st.write("🧪 Lab Type Count", metrics['lab_type_count'])
            import io
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                pd.DataFrame([{'total_cost': metrics['total_cost']}]).to_excel(writer, sheet_name='Total Cost', index=False)
                pd.DataFrame(metrics['total_cost_per_location']).to_excel(writer, sheet_name='Cost per Client', index=False)
                pd.DataFrame(metrics['ordering_per_provider_labtype']).to_excel(writer, sheet_name='Ordering per Provider', index=False)
                pd.DataFrame(metrics['total_cost_per_provider']).to_excel(writer, sheet_name='Cost per Provider', index=False)
                pd.DataFrame(metrics['lab_type_count']).to_excel(writer, sheet_name='Lab Type Count', index=False)
            output.seek(0)
            st.download_button(
                label="📥 Download Metrics Excel",
                data=output,
                file_name="metrics_output.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# --- DRIVE UPLOAD TAB ---
def drive_upload_tab():
    st.header("Upload File to Google Drive")
    st.markdown("""
    Upload a file to the clinic's shared Google Drive folder. Only authorized staff can access uploaded files.
    """)
    uploaded_file = st.file_uploader("Choose a file to upload to Drive")
    folder_id = "1cuvahUyju2zXLnvyeOYvLMRU6cwxJLPP"  # <-- Clinic's shared folder ID
    if uploaded_file is not None:
        # Authenticate with service account
        credentials = service_account.Credentials.from_service_account_file(
            "inventory-project-465214-529cdd128db9.json",
            scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        service = build("drive", "v3", credentials=credentials)
        # Prepare file for upload
        file_metadata = {"name": uploaded_file.name, "parents": [folder_id]}
        media = MediaIoBaseUpload(uploaded_file, mimetype=uploaded_file.type)
        try:
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id"
            ).execute()
            st.success(f"✅ File uploaded successfully to Google Drive! File ID: {file.get('id')}")
        except Exception as e:
            st.error(f"❌ Upload failed: {e}")

# --- HEALTH AI TAB ---
def healthai_tab():
    st.header("🤖 HealthAI: LLM-Powered Health Data Analysis")
    st.markdown("""
    Upload a health data file (CSV, XLSX, or TXT) and enter a question or prompt for Claude (Anthropic LLM).
    **Note:** For privacy, do not upload PHI/PII. Usage is billed to your Anthropic account.
    
    **Use this prompt for best results:**
    
    *Analyze the uploaded health data and provide your results as a CSV table. Please format your output as a CSV inside a Markdown code block (using triple backticks and 'csv' after the first three backticks). Include column headers and ensure the table is suitable for Excel import.*
    """)
    uploaded_file = st.file_uploader("Upload health data file", type=["csv", "xlsx", "txt"], key="healthai_file")
    prompt = st.text_area("Enter your question or analysis prompt for the AI:")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "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")
    if st.button("Analyze with Claude"):
        if not api_key:
            st.error("Claude API key not set. Set ANTHROPIC_API_KEY env variable or paste in code (not recommended for production).")
            return
        if not uploaded_file or not prompt:
            st.warning("Please upload a file and enter a prompt.")
            return
        # Read file content (limit size for demo)
        try:
            if uploaded_file.type in ["text/csv", "text/plain"]:
                file_content = uploaded_file.read().decode("utf-8")
            elif uploaded_file.type in ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel"]:
                df = pd.read_excel(uploaded_file)
                file_content = df.to_csv(index=False)
            else:
                st.error("Unsupported file type.")
                return
        except Exception as e:
            st.error(f"Error reading file: {e}")
            return
        # Truncate file_content if too large (Claude has context limits)
        max_chars = 12000
        file_content = file_content[:max_chars]
        user_message = f"Health data file contents:\n{file_content}\n\nUser prompt: {prompt}"
        st.info("Sending request to Claude using the official SDK...")
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-opus-4-20250514",
                max_tokens=1024,
                messages=[{"role": "user", "content": user_message}]
            )
            ai_reply = ""
            if hasattr(response, "content") and response.content:
                ai_reply = response.content[0].text if hasattr(response.content[0], "text") else str(response.content[0])
            else:
                ai_reply = str(response)
            st.success("Claude's Analysis:")
            import io
            import re
            import pandas as pd
            from pandas.errors import ParserError
            # Extract CSV from code block if present
            csv_text = ai_reply
            code_block_match = re.search(r"```(?:csv|text)?\\n([\s\S]+?)```", ai_reply, re.IGNORECASE)
            if not code_block_match:
                code_block_match = re.search(r"```([\s\S]+?)```", ai_reply, re.IGNORECASE)
            if code_block_match:
                csv_text = code_block_match.group(1).strip()
            # Heuristic: if reply has multiple commas and at least 2 lines, treat as CSV
            csv_detected = False
            csv_data = None
            if csv_text.count(',') > 2 and '\n' in csv_text:
                try:
                    csv_data = pd.read_csv(io.StringIO(csv_text))
                    csv_detected = True
                except (ParserError, Exception):
                    csv_detected = False
            if csv_detected and csv_data is not None:
                st.write("Detected a table result. Preview:")
                st.dataframe(csv_data)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    csv_data.to_excel(writer, index=False)
                output.seek(0)
                st.download_button(
                    label="📥 Download Claude Result as Excel",
                    data=output,
                    file_name="claude_result.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.write(ai_reply)
        except Exception as e:
            st.error(f"Claude API request failed: {e}")

# --- MAIN APP CONTROLLER ---
def main():
    # ✅ Safe initialization for session_state
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'inventory_data' not in st.session_state:
        st.session_state.inventory_data = []

    if not st.session_state.logged_in:
        login()
    else:
        st.sidebar.title("MAP Inventory Portal")
        tab = st.sidebar.radio("Navigate", ["Add Inventory", "Quest_Metrics", "Drive_Upload", "HealthAI"])

        if tab == "Add Inventory":
            inventory_form()
            display_inventory_table()
        elif tab == "Quest_Metrics":
            metrics_tab()
        elif tab == "Drive_Upload":
            drive_upload_tab()
        elif tab == "HealthAI":
            healthai_tab()

if __name__ == "__main__":
    main()