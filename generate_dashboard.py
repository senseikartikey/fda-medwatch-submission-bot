# --- generate_dashboard.py ---
import os
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter
import re
import datetime
import nltk # Optional: for better text analysis
import numpy as np # Import numpy for np.select

# --- Configuration ---
REPORTS_DIR = './submitted_reports' # Assumes script is run from fda-automation-backend or similar relative path
OUTPUT_HTML_FILE = 'report_dashboard_v2.html' # Changed output filename
COMMON_WORDS_COUNT = 15 # Number of top words/products to show

# --- Optional: NLTK Setup ---
# (Keep the NLTK setup code as it was in the original script)
# Try to load stopwords, download if necessary
try:
    nltk_stopwords = set(nltk.corpus.stopwords.words('english'))
    # Add custom words to ignore if necessary
    nltk_stopwords.update(['product', 'use', 'used', 'using', 'problem', 'issue', 'report', 'fda', 'medwatch', 'patient', 'consumer', 'box', 'bottle', 'package', 'ok', 'yes', 'day', 'date', 'time', 'also', 'got', 'took', 'take', 'felt', 'feel', 'started', 'like', 'since', 'get', 'mg', 'ml', 'tablet', 'pill', 'cream', 'ointment', 'na', 'n/a'])
except LookupError:
    print("NLTK stopwords not found. Attempting download...")
    try:
        nltk.download('stopwords', quiet=True)
        nltk.download('punkt', quiet=True)
        nltk_stopwords = set(nltk.corpus.stopwords.words('english'))
        nltk_stopwords.update(['product', 'use', 'used', 'using', 'problem', 'issue', 'report', 'fda', 'medwatch', 'patient', 'consumer', 'box', 'bottle', 'package', 'ok', 'yes', 'day', 'date', 'time', 'also', 'got', 'took', 'take', 'felt', 'feel', 'started', 'like', 'since', 'get', 'mg', 'ml', 'tablet', 'pill', 'cream', 'ointment', 'na', 'n/a'])
        print("NLTK stopwords downloaded.")
    except Exception as e:
        print(f"Warning: Failed to download NLTK data ({e}). Keyword analysis might be less accurate.")
        nltk_stopwords = set() # Use empty set if download fails


# --- Data Loading ---
def load_reports(directory):
    """Loads all JSON report files from the specified directory."""
    all_data = []
    if not os.path.exists(directory):
        print(f"Error: Directory not found - {directory}")
        return None
    print(f"Loading reports from: {directory}")
    count = 0
    expected_keys = {'problemDescription', 'submittedAt', 'problemDate', 'productExpirationDate'} # Add more essential keys if needed
    for filename in os.listdir(directory):
        if filename.endswith(".json"):
            filepath = os.path.join(directory, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Check if *all* expected keys are present before appending
                    # Note: Adapt this check based on truly essential fields for your core analysis
                    if 'submittedAt' in data: # Make 'submittedAt' the minimum requirement
                         all_data.append(data)
                         count += 1
                    else:
                         print(f"Warning: Skipping file {filename} due to missing 'submittedAt' key.")
            except json.JSONDecodeError:
                print(f"Warning: Could not decode JSON from file: {filename}")
            except Exception as e:
                print(f"Warning: Error reading file {filename}: {e}")
    print(f"Successfully loaded {count} reports (based on 'submittedAt' presence).")
    return all_data


# --- Data Processing ---
def process_data(reports):
    """Converts loaded report data into a pandas DataFrame and cleans/formats it."""
    if not reports: return pd.DataFrame()

    df = pd.DataFrame(reports)
    print(f"Initial DataFrame shape: {df.shape}")
    print(f"Columns available: {df.columns.tolist()}") # Log available columns

    # --- Date Conversions (UTC Aware) ---
    date_cols_formats = {
        'submittedAt': None, # Assumes ISO 8601 format
        'problemDate': '%m/%d/%Y',
        'productExpirationDate': '%m/%d/%Y'
    }

    for col, fmt in date_cols_formats.items():
        dt_col = f"{col}_dt"
        if col in df.columns:
            # Parse to datetime objects, coercing errors to NaT (Not a Time)
            df[dt_col] = pd.to_datetime(df[col], format=fmt, errors='coerce')
            # Localize naive datetimes (like those from %m/%d/%Y) to UTC
            # Dates parsed from ISO 8601 with timezone info (like submittedAt) should already be aware
            if df[dt_col].dt.tz is None:
                 # Check if there are any non-NaT values before trying to localize
                 if df[dt_col].notna().any():
                     try:
                        df[dt_col] = df[dt_col].dt.tz_localize('UTC', ambiguous='NaT', nonexistent='NaT')
                     except Exception as e:
                        print(f"Warning: Could not localize column {col} to UTC: {e}. Leaving as naive or NaT.")
                 else:
                     print(f"Info: Column {col} contains only NaT values after parsing.")
            # Ensure the final column is timezone-aware (UTC) or NaT
            df[dt_col] = df[dt_col].dt.tz_convert('UTC') # Convert existing aware times to UTC if needed
        else:
            print(f"Warning: Column '{col}' missing.")
            df[dt_col] = pd.NaT # Assign NaT if column missing

    # --- Expiration Status ---
    now = pd.Timestamp.now(tz='UTC') # Aware (UTC)

    # Define conditions for expiration status calculation
    # Check if necessary date columns exist and are of datetime type
    if 'productExpirationDate_dt' in df.columns and pd.api.types.is_datetime64_any_dtype(df['productExpirationDate_dt']):
        # Use problemDate_dt if available and valid, otherwise compare expiration to 'now'
        comparison_date = df['problemDate_dt'] if 'problemDate_dt' in df.columns and pd.api.types.is_datetime64_any_dtype(df['problemDate_dt']) else now

        conditions = [
            df['productExpirationDate_dt'].isnull(),
            # Expired *before* the problem occurred (if problem date is valid)
            df['problemDate_dt'].notnull() & (df['productExpirationDate_dt'] < df['problemDate_dt']),
             # Expired *before* now (used if problem date is invalid/missing)
            df['problemDate_dt'].isnull() & (df['productExpirationDate_dt'] < now),
             # General case: Expired before now (covers cases where problem date is after expiration but before now)
            df['productExpirationDate_dt'] < now
        ]
        choices = [
            'Unknown Expiration',
            'Expired Before Problem',
            'Expired (Problem Date Missing)',
            'Expired'
        ]
        df['expirationStatus'] = np.select(conditions, choices, default='Valid')

        # Refine: Ensure 'Expired Before Problem' takes precedence if problem date is known
        df.loc[df['problemDate_dt'].notnull() & (df['productExpirationDate_dt'] < df['problemDate_dt']), 'expirationStatus'] = 'Expired Before Problem'

    else:
        print("Warning: Cannot calculate expiration status due to missing or invalid 'productExpirationDate_dt' column.")
        df['expirationStatus'] = 'Unknown' # Default if dates are missing


    # --- Clean/Standardize Categorical and Text Fields ---
    categorical_cols = {
        'problemCause': 'Unknown',
        'reportIsAbout': 'Unknown',
        'patientSex': 'Unknown',
        'patientKnownMedicalConditionsOrAllergies': 'Unknown' # Treat this as categorical for the simple plot
    }
    for col, fill_value in categorical_cols.items():
         if col in df.columns:
             df[col] = df[col].fillna(fill_value).astype(str).str.strip()
             # Specific standardization for conditions/allergies for plotting
             if col == 'patientKnownMedicalConditionsOrAllergies':
                 df[col] = df[col].str.lower()
                 # Map common variations to 'Yes' or 'No'
                 conditions_map = {
                     'yes': 'Yes',
                     'true': 'Yes',
                     'no': 'No',
                     'false': 'No',
                     'none': 'No',
                     '': 'Unknown', # Map empty strings to Unknown
                     # Keep 'Unknown' as 'Unknown'
                 }
                 # Apply mapping, keep original if not in map keys (and not already 'Unknown')
                 df[col] = df[col].apply(lambda x: conditions_map.get(x, 'Other/Specified' if x != 'unknown' else 'Unknown'))

         else:
             print(f"Warning: Column '{col}' not found. Filling with '{fill_value}'.")
             df[col] = fill_value

    text_cols = ['problemDescription', 'productName', 'productPurchaseLocation', 'specifications']
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].fillna('').astype(str).str.lower().str.strip()
        else:
            print(f"Warning: Column '{col}' not found. Adding as empty column.")
            df[col] = '' # Add empty column if missing

    print("Data processed. Final DataFrame shape:", df.shape)
    # print("\nSample processed data:")
    # print(df[['submittedAt_dt', 'problemDate_dt', 'productExpirationDate_dt', 'expirationStatus', 'patientKnownMedicalConditionsOrAllergies']].head())
    # print("\nExpiration Status Counts:")
    # print(df['expirationStatus'].value_counts())
    # print("\nKnown Conditions Counts:")
    # print(df['patientKnownMedicalConditionsOrAllergies'].value_counts())


    return df

# --- Text Analysis ---
def get_common_words(text_series, top_n=20):
    """Extracts common words from a pandas Series of text, excluding stopwords."""
    if text_series.empty or text_series.isnull().all():
        return Counter()

    # Combine all non-null text, convert to lowercase
    all_text = ' '.join(text_series.dropna().astype(str).tolist())
    # Find word sequences using regex, more robust than simple split
    words = re.findall(r'\b\w+\b', all_text.lower())

    # Filter out stopwords and short words (adjust length filter if needed)
    filtered_words = [word for word in words if word not in nltk_stopwords and len(word) > 2]

    return Counter(filtered_words).most_common(top_n)

# --- Visualization Functions ---

def plot_reports_over_time(df, time_col='submittedAt_dt', freq='M'):
    """Plots the number of reports over time."""
    if time_col not in df.columns or not pd.api.types.is_datetime64_any_dtype(df[time_col]) or df[time_col].isnull().all():
        print(f"Warning: Cannot plot reports over time. Column '{time_col}' is missing, invalid, or empty.")
        return None

    # Ensure the column is datetime and drop NaT values for resampling
    df_time = df[[time_col]].dropna()
    if df_time.empty:
         print(f"Warning: No valid date entries found in column '{time_col}'.")
         return None

    # Set the date column as index for resampling
    df_time = df_time.set_index(time_col)

    # Resample and count
    try:
        # 'ME' for Month End frequency
        report_counts = df_time.resample('ME').size().reset_index()
        report_counts.columns = ['Date', 'Count']
    except Exception as e:
        print(f"Error during resampling: {e}")
        return None


    fig = px.line(report_counts, x='Date', y='Count',
                  title='Reports Submitted Over Time (Monthly)',
                  markers=True,
                  labels={'Date': 'Month', 'Count': 'Number of Reports'})
    fig.update_layout(xaxis_title="Month", yaxis_title="Number of Reports")
    return fig

def plot_problem_cause(df):
    """Plots the distribution of problem causes."""
    if 'problemCause' not in df.columns or df['problemCause'].isnull().all():
        print("Warning: 'problemCause' column missing or empty. Cannot generate plot.")
        return None
    counts = df['problemCause'].value_counts().reset_index()
    counts.columns = ['cause', 'count']
    fig = px.pie(counts, names='cause', values='count',
                 title='Distribution of Reported Problem Causes', hole=0.4,
                 color_discrete_sequence=px.colors.qualitative.Set2)
    fig.update_traces(textposition='inside', textinfo='percent+label', pull=[0.05] * len(counts))
    fig.update_layout(legend_title_text='Cause')
    return fig

def plot_report_types_donut(df):
    """Plots the distribution of report categories (e.g., Cosmetic, Drug)."""
    if 'reportIsAbout' not in df.columns or df['reportIsAbout'].isnull().all():
        print("Warning: 'reportIsAbout' column missing or empty. Cannot generate plot.")
        return None
    counts = df['reportIsAbout'].value_counts().reset_index()
    counts.columns = ['type', 'count']
    fig = px.pie(counts, names='type', values='count',
                 title='Reports by Product Category', hole=0.4,
                 color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_traces(textposition='inside', textinfo='percent+label', pull=[0.05] * len(counts))
    fig.update_layout(legend_title_text='Category')
    return fig

def plot_patient_gender_donut(df):
    """Plots the distribution of patient genders."""
    if 'patientSex' not in df.columns or df['patientSex'].isnull().all():
        print("Warning: 'patientSex' column missing or empty. Cannot generate plot.")
        return None
    counts = df['patientSex'].value_counts().reset_index()
    counts.columns = ['gender', 'count']
    fig = px.pie(counts, names='gender', values='count',
                 title='Reports by Patient Gender', hole=0.4,
                 color_discrete_sequence=px.colors.qualitative.Safe)
    fig.update_traces(textposition='inside', textinfo='percent+label', pull=[0.05] * len(counts))
    fig.update_layout(legend_title_text='Gender')
    return fig

def plot_known_conditions_bar(df):
    """Plots the distribution of known conditions/allergies status."""
    col = 'patientKnownMedicalConditionsOrAllergies'
    if col not in df.columns or df[col].isnull().all():
         print(f"Warning: '{col}' column missing or empty. Cannot generate plot.")
         return None
    counts = df[col].value_counts().reset_index()
    counts.columns = ['status', 'count']
    fig = px.bar(counts, x='status', y='count',
                 title='Patient Known Conditions/Allergies Reported',
                 labels={'status': 'Status Reported', 'count': 'Number of Reports'},
                 color='status', color_discrete_map={'Yes': '#EF553B', 'No': '#636EFA', 'Unknown': '#BDBDBD', 'Other/Specified': '#FFA15A'}, # Example colors
                 text='count')
    fig.update_traces(textposition='outside')
    fig.update_layout(xaxis_title="Reported Status", yaxis_title="Number of Reports")
    return fig


def plot_common_products_bar(df, top_n=COMMON_WORDS_COUNT):
    """Plots the top N most frequently reported products."""
    if 'productName' not in df.columns or df['productName'].isnull().all():
        print("Warning: 'productName' column missing or empty. Cannot generate plot.")
        return None
    # Exclude generic/placeholder names more carefully
    exclude_list = ['unknown', '', 'n/a', 'yes', 'no', 'none']
    valid_products = df[~df['productName'].isin(exclude_list)]
    if valid_products.empty:
        print("Warning: No valid product names found after filtering.")
        return None
    counts = valid_products['productName'].value_counts().nlargest(top_n).reset_index()
    counts.columns = ['product', 'count']
    fig = px.bar(counts.sort_values('count'), x='count', y='product', orientation='h',
                 title=f'Top {top_n} Reported Products',
                 labels={'product': 'Product Name', 'count': 'Number of Reports'},
                 text='count', color='count', color_continuous_scale=px.colors.sequential.Viridis)
    fig.update_traces(textposition='outside')
    fig.update_layout(yaxis={'categoryorder':'total ascending'}, margin=dict(l=150)) # Add left margin for long labels
    return fig

def plot_expiration_status_bar(df):
    """Plots the distribution of product expiration statuses."""
    if 'expirationStatus' not in df.columns or df['expirationStatus'].isnull().all():
        print("Warning: 'expirationStatus' column missing or empty. Cannot generate plot.")
        return None
    counts = df['expirationStatus'].value_counts().reset_index()
    counts.columns = ['status', 'count']
    # Define a specific color map for better visual distinction
    color_map = {
        'Valid': '#636EFA', # Blue
        'Expired': '#EF553B', # Red
        'Expired Before Problem': '#AB63FA', # Purple
        'Expired (Problem Date Missing)': '#FFA15A', # Orange
        'Unknown Expiration': '#BDBDBD' # Grey
    }
    fig = px.bar(counts, x='status', y='count',
                 title='Product Expiration Status (Relative to Problem Date/Now)',
                 labels={'status': 'Expiration Status', 'count': 'Number of Reports'},
                 color='status', color_discrete_map=color_map,
                 text='count')
    fig.update_traces(textposition='outside')
    fig.update_layout(xaxis_title="Status", yaxis_title="Number of Reports")
    return fig

def plot_common_keywords_bar(word_counts, title, color_scale=px.colors.sequential.Blues):
    """Plots a bar chart of common keywords."""
    if not word_counts:
        print(f"Warning: No keywords to plot for '{title}'.")
        return None
    df_words = pd.DataFrame(word_counts, columns=['word', 'count'])
    fig = px.bar(df_words.sort_values('count'), x='count', y='word', orientation='h',
                 title=title, text='count', color='count',
                 color_continuous_scale=color_scale)
    fig.update_traces(textposition='outside')
    fig.update_layout(yaxis={'categoryorder':'total ascending'},
                      xaxis_title="Frequency", yaxis_title="Keyword", margin=dict(l=120)) # Add left margin
    return fig


# --- HTML Generation (Updated Layout) ---
def generate_html_dashboard(figs):
    """Generates a single HTML file containing all plots."""
    plot_divs = {name: fig.to_html(full_html=False, include_plotlyjs='cdn')
                 for name, fig in figs.items() if fig} # Only include divs for successfully generated figures

    # Start HTML with updated styling
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Medical Product Report Dashboard</title>
        <script src='https://cdn.plot.ly/plotly-latest.min.js'></script>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; background-color: #f4f7fa; color: #333; display: flex; flex-direction: column; min-height: 100vh; }
            header { background-color: #1a5f7a; /* Darker Blue */ color: white; padding: 18px 35px; text-align: center; box-shadow: 0 3px 6px rgba(0,0,0,0.1); }
            h1 { margin: 0; font-weight: 400; font-size: 2.2em; }
            main { flex: 1; padding: 30px; max-width: 1600px; margin: 0 auto; width: 100%; box-sizing: border-box; }
            section { margin-bottom: 35px; background-color: #fff; border-radius: 8px; padding: 25px; box-shadow: 0 2px 5px rgba(0,0,0,0.07); }
            .dashboard-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(450px, 1fr)); /* Slightly larger min width */
                gap: 30px;
                margin-top: 20px;
            }
            .chart-container {
                /* background-color: #fff; */ /* Section provides background now */
                /* padding: 20px; */ /* Padding handled by section */
                /* border-radius: 8px; */ /* Rounded corners on section */
                /* box-shadow: 0 4px 8px rgba(0,0,0,0.08); */ /* Shadow on section */
                transition: transform 0.2s ease-in-out;
                min-height: 420px; /* Increased min height */
                display: flex;
                flex-direction: column; /* Stack title and chart */
                justify-content: flex-start; /* Align title top */
                align-items: center; /* Center chart horizontally */
                overflow: hidden;
            }
            /* .chart-container:hover { transform: translateY(-5px); } */ /* Optional hover effect */
            h2 { color: #1a5f7a; border-bottom: 3px solid #57a0c4; /* Lighter blue accent */ padding-bottom: 10px; margin-top: 0; margin-bottom: 25px; font-weight: 500; font-size: 1.6em; }
            /* Ensure Plotly divs are responsive within their container */
            .plotly-graph-div {
                width: 100% !important;
                min-height: 380px; /* Ensure chart has some minimum height */
                flex-grow: 1; /* Allow chart to take available space */
            }
            footer { background-color: #e1e8f0; color: #555; text-align: center; padding: 12px; font-size: 0.85em; margin-top: auto; }
            /* Responsive adjustments */
            @media (max-width: 1000px) { .dashboard-grid { grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); } } /* Adjust breakpoint */
            @media (max-width: 600px) {
                h1 { font-size: 1.8em; }
                h2 { font-size: 1.4em; }
                main { padding: 20px; }
                .dashboard-grid { grid-template-columns: 1fr; gap: 20px; } /* Stack charts */
                .chart-container { min-height: 380px; }
                .plotly-graph-div { min-height: 340px; }
            }
             @media (max-width: 480px) {
                 header { padding: 15px 20px; }
                 h1 { font-size: 1.5em; }
                 h2 { font-size: 1.3em; }
                 main { padding: 15px; }
             }
        </style>
    </head>
    <body>
        <header><h1>Medical Product Report Dashboard</h1></header>
        <main>
    """

    # Define the structure and order of plots
    sections = {
        "Reporting Trends & Overview": ['time_trend', 'causes', 'types'],
        "Patient Demographics": ['gender', 'conditions'],
        "Product Insights": ['products', 'expiration'],
        "Keyword Analysis": ['problem_keywords'] # Removed condition keywords plot as 'plot_known_conditions_bar' is better
    }

    # Add Sections and Plots
    for title, plot_keys in sections.items():
        # Check if at least one plot for this section exists
        section_has_plots = any(key in plot_divs for key in plot_keys)
        if section_has_plots:
            html_content += f"<section><h2>{title}</h2><div class='dashboard-grid'>"
            for key in plot_keys:
                if key in plot_divs:
                    html_content += f"<div class='chart-container'>{plot_divs[key]}</div>"
                # else: # Optional: Add placeholder if a plot is missing
                #     html_content += f"<div class='chart-container'><p>Plot '{key}' could not be generated.</p></div>"
            html_content += "</div></section>"
        else:
             print(f"Skipping section '{title}' as no valid plots were generated for it.")


    # End HTML
    html_content += f"""
        </main>
        <footer>Generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</footer>
    </body>
    </html>
    """

    # Write to file
    try:
        with open(OUTPUT_HTML_FILE, 'w', encoding='utf-8') as f: f.write(html_content)
        print(f"\nDashboard successfully generated: {OUTPUT_HTML_FILE}")
    except Exception as e: print(f"\nError writing HTML file: {e}")


# --- Main Execution ---
if __name__ == "__main__":
    report_data = load_reports(REPORTS_DIR)
    if report_data:
        df_reports = process_data(report_data)
        if not df_reports.empty:
            # --- Generate Data for Keywords ---
            # (Keep keyword generation as before, but we might only display problem keywords)
            common_problem_words = get_common_words(df_reports['problemDescription'], COMMON_WORDS_COUNT) if 'problemDescription' in df_reports.columns else []
            # common_condition_words = get_common_words(df_reports['patientKnownMedicalConditionsOrAllergies'], COMMON_WORDS_COUNT) if 'patientKnownMedicalConditionsOrAllergies' in df_reports.columns else [] # Less useful now

            # --- Create Figures ---
            figures = {
                # Reporting Trends & Overview
                'time_trend': plot_reports_over_time(df_reports, time_col='submittedAt_dt', freq='ME'), # Use Month End freq
                'causes': plot_problem_cause(df_reports),
                'types': plot_report_types_donut(df_reports),
                # Patient Demographics
                'gender': plot_patient_gender_donut(df_reports),
                'conditions': plot_known_conditions_bar(df_reports),
                # Product Insights
                'products': plot_common_products_bar(df_reports, COMMON_WORDS_COUNT),
                'expiration': plot_expiration_status_bar(df_reports),
                # Keyword Analysis
                'problem_keywords': plot_common_keywords_bar(common_problem_words, f'Top Keywords in Problem Descriptions', px.colors.sequential.Oranges),
                # 'condition_keywords': plot_common_keywords_bar(common_condition_words, f'Top Keywords in Conditions/Allergies', px.colors.sequential.Greens) # Removed as less useful
            }
            # --- Generate HTML ---
            generate_html_dashboard(figures) # Pass the dictionary of figures
        else: print("No valid data available in DataFrame to generate dashboard.")
    else: print("Failed to load report data or no reports found.")

