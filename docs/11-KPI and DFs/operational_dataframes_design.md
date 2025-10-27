# Operational Efficiency Dataframes Design

## Encounter-wise Upload Processing Metrics

Based on your requirements, here's the detailed structure for the encounter-wise dataframe:

### DataFrame: `encounter_upload_metrics_df`

```python
encounter_upload_metrics_df = pd.DataFrame(columns=[
    'encounter_id',              # PatientEncounters.id
    'patient_id',                # Patient ID from encounter

    'capture_date_dt',           # Processed capture date (datetime)
    'zip_file_id',              # Associated zip file ID
    'zip_filename',              # Zip file name
    'zip_upload_date',           # ZipFile.upload_date
    'lab_unit_id',              # Lab unit ID
    'lab_unit_name',            # Lab unit name
    'hospital_id',              # Hospital ID
    'hospital_name',            # Hospital name
    'total_images',             # Count of images in encounter
    'verified_images',             # Count of images in encounter that have been right left laterality marked

    # DR Report Fields
    'has_dr_report',            # Boolean: has DR report
    'dr_report_id',             # DiabeticRetinopathyReport.id
    'dr_result',               # DR report result
    'dr_qualitative_result',     # DR qualitative result
    'dr_report_filename',       # DR report file name
    
    # Glaucoma Report Fields from cleaned glacuaom resulkts table
    'has_glaucoma_report',      # Boolean: has glaucoma report
    'glaucoma_vcdr_right_num',  # Cleaned VCDR right eye
    'glaucoma_vcdr_left_num',   # Cleaned VCDR left eye
    'glaucoma_report_id',       # GlaucomaReport.id
    'glaucoma_result',          # Glaucoma report result
    'glaucoma_qualitative_result', # Glaucoma qualitative result
    'glaucoma_report_filename',  # Glaucoma report file name
    
    # Verification Status Fields
    'encounter_verified_status',  # Encounter verification status
    'encounter_verified_by',     # Who verified encounter
    'encounter_verified_at',     # When encounter was verified
    'dr_verified_status',        # DR verification status
    'dr_verified_by',           # Who verified DR
    'dr_verified_at',           # When DR was verified
    'glaucoma_verified_status',  # Glaucoma verification status
    'glaucoma_verified_by',     # Who verified glaucoma
    'glaucoma_verified_at',     # When glaucoma was verified
     'compleley_verifeid',     # if DR rport present then Dr is verifed and if galcuam is present then glaucoa is verfied and if no rpeor is present than encounter is verfied
      'coompletely_verfied_date' # last date when dr / galcupoma/ encounter verfioed  as per need of verification

    # Timing Metrics
    'upload_to_processing_hours',    # Time from zip upload to processing start
    'processing_completion_hours',   # Total processing time
    'verification_hours',           # Time to complete verification
    
    # Date Groupings for Analysis
    'upload_date'             # Date for grouping (from zip_upload_date)
])
```

### Key Data Sources

**Primary Models:**
- [`PatientEncounters`](models.py:190) - Main encounter data
- [`ZipFile`](models.py:182) - Upload information
- [`DiabeticRetinopathyReport`](models.py:252) - DR reports
- [`GlaucomaReport`](models.py:262) - Glaucoma reports  
- [`GlaucomaResultsCleaned`](models.py:274) - Cleaned glaucoma data
- [`EncounterFile`](models.py:217) - Image files within encounters

**Key Relationships:**
- PatientEncounters → ZipFile (1:1)
- PatientEncounters → EncounterFile (1:N) - for images
- PatientEncounters → EncounterFilePDF (1:1) - for overall PDF
- PatientEncounters → DiabeticRetinopathyReport (1:1)
- PatientEncounters → GlaucomaReport (1:1) → GlaucomaResultsCleaned (1:1)

### Operational Metrics Enabled

This dataframe enables analysis of:

1. **Upload Processing Efficiency:**
   - Time from upload to processing completion
   - Success rates of image processing
   - Processing bottlenecks

2. **Report Generation Analysis:**
   - DR vs Glaucoma report generation rates
   - Report completeness by encounter
   - Verification status tracking

3. **Temporal Analysis:**
   - Daily/weekly/monthly upload patterns
   - Processing time trends
   - Seasonal variations

4. **Quality Metrics:**
   - Verification success rates
   - Data completeness indicators
   - Report accuracy tracking

### Example Usage

```python
# Basic efficiency analysis
avg_processing_time = encounter_upload_metrics_df['processing_completion_hours'].mean()
success_rate = encounter_upload_metrics_df['processing_success_rate'].mean()

# Report generation analysis
dr_report_rate = encounter_upload_metrics_df['has_dr_report'].mean()
glaucoma_report_rate = encounter_upload_metrics_df['has_glaucoma_report'].mean()

# Time-based analysis
daily_uploads = encounter_upload_metrics_df.groupby('upload_date').size()
weekly_processing = encounter_upload_metrics_df.groupby('week_of_year')['processing_completion_hours'].mean()
```

## DB Context Manager Guidance

When implementing dataframes for operational metrics, always follow database context manager patterns established in project:

### Preferred Method: Use Context Managers

**Always use context managers from `utils.utils` or `db_transaction_manager`:**

```python
from utils.utils import with_session
# OR
from db_transaction_manager import transaction_scope, get_db_session

# Method 1: Using @with_session decorator (preferred for utility functions)
@with_session()
def generate_encounter_upload_metrics_df(db, start_date=None, end_date=None):
    # Use db session here
    encounters = db.query(PatientEncounters).all()
    # No need to commit/close - handled automatically
    return df

# Method 2: Using context manager in routes
@bp.route("/encounter-files")
def encounter_files():
    with get_db_session() as db:
        df = generate_encounter_upload_metrics_df(db, start_date, end_date)
        # Process and return data
```

### Key Principles

1. **Never create sessions directly in utility functions**
   - Always pass session from route to utilities (dependency injection)
   - Context manager handles commit/rollback/cleanup automatically

2. **Route handlers manage transaction context**
   ```python
   @bp.route("/analytics-route")
   @roles_required("admin", "data_manager")
   def analytics_route():
       with transaction_scope() as db:  # For write operations
           try:
               df = utility_function(db, params)
               # Transaction automatically committed on success
               return render_template("analytics.html", data=df)
           except Exception as e:
               # Transaction automatically rolled back
               flash(f"Error: {str(e)}", "error")
   ```

3. **For read-only operations, use `get_db_session()`**
   ```python
   with get_db_session() as db:
       df = generate_dataframe(db, filters)
       # No commit needed for read operations
   ```

4. **Utility functions should accept db session as first parameter**
   ```python
   def utility_function(db, param1, param2):
       # Use passed session, don't create new ones
       query = db.query(SomeModel).filter(SomeModel.field == param1)
       return query.all()
   ```

### Benefits

- **Automatic resource management**: No need to remember to close sessions
- **Transaction safety**: Automatic rollback on errors
- **Cleaner code**: Eliminates boilerplate session handling
- **Consistency**: Standardized pattern across the codebase

### Common Anti-Patterns to Avoid

❌ **Don't do this:**
```python
def bad_function():
    db = Session()  # Creating session directly
    try:
        data = db.query(Model).all()
        return data
    finally:
        db.close()  # Manual cleanup
```

✅ **Do this instead:**
```python
@with_session()
def good_function(db):
    data = db.query(Model).all()
    return data
```

## Next Steps

After implementing this encounter-wise dataframe, we can proceed with:

1. **Image-wise Upload Processing Metrics** - Individual image level analysis
2. **Grading Efficiency Metrics** - Grader performance analysis
3. **Consensus Completion Metrics** - Consensus process efficiency
4. **End-to-End Workflow Analysis** - Complete workflow visibility

Would you like me to proceed with implementing this encounter-wise dataframe structure?