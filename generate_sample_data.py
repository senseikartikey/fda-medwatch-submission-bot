import json
import os
import random
import datetime
import time
import uuid

# --- Configuration ---
OUTPUT_DIR = './submitted_reports'
NUM_FILES_TO_GENERATE = 15 # You might want to increase this for a denser graph over a year
SUBMISSION_DATE_RANGE_DAYS = 365 # <<< CHANGED: Spread submissions over the last year

# --- Sample Data Options ---
# (Keep the sample data lists as they were)
PROBLEM_DESCRIPTIONS = [
    "Developed a severe rash after using the cream for 3 days.",
    "Experienced headache and nausea shortly after taking the tablet.",
    "The product seemed ineffective, no change in symptoms.",
    "Noticed swelling and redness around the application area.",
    "The packaging was damaged upon arrival, seal broken.",
    "Felt dizzy and lightheaded about an hour after consumption.",
    "Device gave inconsistent readings compared to doctor's office.",
    "Mild skin irritation occurred after first use.",
    "Product had an unusual smell, different from previous purchases.",
    "Caused unexpected drowsiness.",
    "Ok", # Include simple placeholders too
    "No effect observed.",
    "Slight itching reported.",
    "Blood pressure reading seemed unusually high.",
    "Supplement caused stomach upset."
]
PROBLEM_CAUSES = ["ProductRelated", "UserError", "Unknown", "Interaction", "QualityIssue"]
REPORT_IS_ABOUT = ["Cosmetic", "Drug", "Device", "Supplement", "Food"]
PRODUCT_NAMES = [
    "PainRelief X", "SkinCalm Cream", "VitaBoost D3", "BP Monitor Pro", "AllergyEase Syrup",
    "DermaCare Lotion", "EnergyUp Capsule", "SleepWell Tablet", "AccuCheck Meter", "NutriPlus Shake",
    "SunBlock SPF50", "ColdFix Syrup", "JointFlex Caplet", "FocusAid Drink", "HairGrow Serum"
]
LOCATIONS = ["Local Pharmacy", "Online Retailer", "Supermarket", "Doctor's Office", "Direct from Manufacturer", "Unknown", ""]
GENDERS = ["Male", "Female", "Non-binary", "Prefer not to say", "Unknown"]
CONDITIONS_ALLERGIES = [
    "Yes", "No", "None reported", "Allergic to penicillin", "Hypertension",
    "Diabetes Type 2", "Asthma", "Seasonal allergies", "None", "", "Unknown",
    "Patient reports sensitivity to adhesives.", "Lactose intolerant.", "Gluten sensitive.",
    "History of migraines."
]
SPECIFICATIONS = [
    "LOT: A1234BC", "LOT: X9876YZ", "50mg tablets", "100ml bottle", "Model X-100",
    "Serial #: SN098765", "250mcg spray", "EXP: See bottom", "Batch: 052024A", "", "Ok",
    "Regular Strength", "Extra Strength Formula", "Size L Cuff", "Version 2.1 Software"
]
FIRST_NAMES = ["Jane", "John", "Alex", "Maria", "Sam", "Priya", "Chris", "Mei", "Kenji", "Fatima", "Ok"]
LAST_NAMES = ["Doe", "Smith", "Lee", "Garcia", "Chen", "Patel", "Kim", "Jones", "Ok"]


# --- Helper Functions ---
def generate_random_date(start_date, end_date):
    """Generates a random date between start_date and end_date."""
    # Ensure start_date is not after end_date
    if start_date > end_date:
        start_date = end_date # Avoid error if dates are inverted

    time_between_dates = end_date - start_date
    # Handle case where start and end date are the same
    if time_between_dates.days < 0:
         days_between_dates = 0
    else:
         days_between_dates = time_between_dates.days

    random_number_of_days = random.randrange(days_between_dates + 1) # Include end date
    random_date = start_date + datetime.timedelta(days=random_number_of_days)
    return random_date

def generate_report_data():
    """Generates a dictionary representing a single report."""
    now = datetime.datetime.now(datetime.timezone.utc)

    # --- MODIFIED: Generate submittedAt over a wider range (e.g., last 365 days) ---
    submitted_at_dt = now - datetime.timedelta(days=random.uniform(0, SUBMISSION_DATE_RANGE_DAYS), hours=random.uniform(0, 24))
    submitted_at_iso = submitted_at_dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    # problemDate: Still before submittedAt (up to 1 year *before the new submission date*)
    # Ensure problem date is not after submission date
    max_problem_date = submitted_at_dt
    min_problem_date = submitted_at_dt - datetime.timedelta(days=365)
    problem_date_dt = generate_random_date(min_problem_date, max_problem_date)
    problem_date_str = problem_date_dt.strftime('%m/%d/%Y')


    # productExpirationDate: Logic remains relative to the *new* problemDate and submittedAt
    exp_scenario = random.choice(['valid', 'expired_before_problem', 'expired_after_problem', 'far_future', 'past_but_valid', 'unknown'])
    exp_date_dt = None
    exp_date_str = ""

    # Define potential start/end dates for expiration based on scenario
    valid_start = submitted_at_dt + datetime.timedelta(days=30)
    valid_end = submitted_at_dt + datetime.timedelta(days=730)
    expired_before_start = problem_date_dt - datetime.timedelta(days=730)
    expired_before_end = problem_date_dt - datetime.timedelta(days=30)
    expired_after_start = problem_date_dt + datetime.timedelta(days=1)
    expired_after_end = submitted_at_dt - datetime.timedelta(days=1)
    far_future_start = submitted_at_dt + datetime.timedelta(days=731)
    far_future_end = submitted_at_dt + datetime.timedelta(days=1500)

    try:
        if exp_scenario == 'valid':
            exp_date_dt = generate_random_date(valid_start, valid_end)
        elif exp_scenario == 'expired_before_problem':
            # Ensure end date is before start date is handled by generate_random_date
            if expired_before_end > expired_before_start:
                 exp_date_dt = generate_random_date(expired_before_start, expired_before_end)
            else: # Fallback if problem date is too recent
                 exp_date_dt = generate_random_date(valid_start, valid_end) # Make it valid instead
        elif exp_scenario == 'expired_after_problem':
            # Ensure there's at least a day between problem and submission
            if expired_after_end > expired_after_start:
                 exp_date_dt = generate_random_date(expired_after_start, expired_after_end)
            else: # Fallback if problem date is too close to submission
                 if expired_before_end > expired_before_start:
                     exp_date_dt = generate_random_date(expired_before_start, expired_before_end) # Expire before problem
                 else:
                      exp_date_dt = generate_random_date(valid_start, valid_end) # Or make it valid
        elif exp_scenario == 'far_future':
            exp_date_dt = generate_random_date(far_future_start, far_future_end)
        elif exp_scenario == 'past_but_valid': # Expired after problem but before submission
             if expired_after_end > expired_after_start:
                 exp_date_dt = generate_random_date(expired_after_start, expired_after_end)
             else: # Fallback if problem date is very recent
                 exp_date_dt = generate_random_date(valid_start, valid_end) # Make it valid instead

        # Format if date was generated
        if exp_date_dt:
            exp_date_str = exp_date_dt.strftime('%m/%d/%Y')
        elif exp_scenario == 'unknown':
             exp_date_str = random.choice(["", "Not specified", "Illegible"])

    except ValueError as e:
         print(f"Date generation error for expiration: {e}. Setting to Unknown.")
         exp_date_str = "Unknown" # Fallback on error
    except Exception as e: # Catch other potential errors
         print(f"Unexpected date generation error: {e}. Setting to Unknown.")
         exp_date_str = "Unknown" # Fallback on error


    reporter_first = random.choice(FIRST_NAMES)
    reporter_last = random.choice(LAST_NAMES)

    report = {
        "problemDescription": random.choice(PROBLEM_DESCRIPTIONS),
        "problemDate": problem_date_str,
        "problemCause": random.choice(PROBLEM_CAUSES),
        "productPurchaseLocation": random.choice(LOCATIONS),
        "reportIsAbout": random.choice(REPORT_IS_ABOUT),
        "productName": random.choice(PRODUCT_NAMES),
        "productExpirationDate": exp_date_str,
        "patientInitials": f"{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}",
        "patientSex": random.choice(GENDERS),
        "patientKnownMedicalConditionsOrAllergies": random.choice(CONDITIONS_ALLERGIES),
        "specifications": random.choice(SPECIFICATIONS),
        "reporterFirstName": reporter_first,
        "reporterLastName": reporter_last,
        "reporterEmail": f"{reporter_first.lower()}.{reporter_last.lower()}{random.randint(1,99)}@example.com",
        "userId": f"user_{uuid.uuid4().hex[:25]}", # Generate a unique-ish ID
        "phoneNumberVerified": f"+1{random.randint(200, 999)}{random.randint(200, 999)}{random.randint(1000, 9999)}",
        "attested": random.choices([True, False], weights=[0.9, 0.1], k=1)[0], # Mostly true
        "submittedAt": submitted_at_iso
    }
    return report

# --- Main Script ---
if __name__ == "__main__":
    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Ensuring output directory exists: {OUTPUT_DIR}")

    generated_files = []
    print(f"Generating {NUM_FILES_TO_GENERATE} files with submission dates spread over ~{SUBMISSION_DATE_RANGE_DAYS} days...")
    for i in range(NUM_FILES_TO_GENERATE):
        # Generate report data
        report_content = generate_report_data()

        # Create filename
        # Use the submission date for the filename date part for consistency
        try:
            submission_dt_obj = datetime.datetime.fromisoformat(report_content['submittedAt'].replace('Z', '+00:00'))
            date_str = submission_dt_obj.strftime('%Y-%m-%d')
            timestamp_ms = int(time.time() * 1000) + i # Add index to ensure uniqueness even if run fast
            filename = f"report_{date_str}_{timestamp_ms}.json"
            filepath = os.path.join(OUTPUT_DIR, filename)

            # Write JSON data to file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report_content, f, indent=2) # Use indent=2 for readability
            generated_files.append(filename)
            # print(f"Generated: {filename}") # Print progress for each file
        except IOError as e:
            print(f"Error writing file {filename}: {e}")
        except Exception as e:
             print(f"An unexpected error occurred while generating report {i+1}: {e}")
             # Optional: print the problematic data
             # print(f"Problematic data: {report_content}")


    print(f"\nSuccessfully generated {len(generated_files)} sample report files in '{OUTPUT_DIR}'.")
    # print("\nGenerated filenames:")
    # for fname in generated_files:
    #     print(f"- {fname}")

