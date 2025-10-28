# Tasks DataFrame Implementation with Upload Date

## Updated Requirements

Based on additional requirement, the DataFrame now includes:

✅ **Upload date of image** - Sourced from DirectImageUpload.created_at for direct images or ZipFile.upload_date for encounter files

## Updated Database Query Strategy

The DataFrame will need to efficiently join:
1. **GradingTask** (main table)
2. **DirectImageUpload** OR **EncounterFile** (image source)
3. **ZipFile** (for encounter file upload dates)
4. **Disease** (for disease information)
5. **LabUnit** and **Hospital** (location information)
6. **Consensus** (for final results)
7. **Grade** (for grading analytics)
8. **AdHocTaskCreation** (for ad-hoc identification)

## Enhanced Implementation: utils/dataFrameTasks.py

```python
@with_session()
def generate_tasks_dataframe(db, start_date: Optional[datetime] = None,
                          end_date: Optional[datetime] = None) -> pd.DataFrame:
    """
    Generate comprehensive Tasks KPI dataframe with grading, consensus, and workflow information.
    
    Args:
        db: Database session (handled by context manager)
        start_date: Optional start date filter for tasks (based on created_at)
        end_date: Optional end date filter for tasks (based on created_at)
        
    Returns:
        pandas.DataFrame with comprehensive Tasks KPI metrics
    """
    import logging
    logger = logging.getLogger(__name__)
    error_logger = logging.getLogger('runtime_error')
    
    try:
        # Query for tasks with all required relationships
        tasks_query = db.query(GradingTask).options(
            # Core relationships
            joinedload(GradingTask.disease),
            joinedload(GradingTask.lab_unit).joinedload(LabUnit.hospital),
            joinedload(GradingTask.encounter_file).joinedload(EncounterFile.patient_encounter).joinedload(PatientEncounters.zip_file),
            joinedload(GradingTask.direct_image),
            joinedload(GradingTask.consensus).joinedload(Consensus.final_label),
            joinedload(GradingTask.ad_hoc),
            
            # Collections for analytics
            selectinload(GradingTask.grades).joinedload(Grade.grader),
            selectinload(GradingTask.grades).joinedload(Grade.label)
        )
        
        # Apply date filters based on created_at
        if start_date:
            tasks_query = tasks_query.filter(GradingTask.created_at >= start_date)
        
        if end_date:
            tasks_query = tasks_query.filter(GradingTask.created_at <= end_date)
        
        tasks = tasks_query.all()
        
        logger.info(f"Retrieved {len(tasks)} tasks from database")
        if start_date or end_date:
            logger.info(f"Date filters applied: start_date={start_date}, end_date={end_date}")
        
        data = []
        
        # Process each task
        for task in tasks:
            # Determine image source type and get image information
            image_source_type = None
            image_id = None
            image_uuid = None
            image_filename = None
            upload_date = None  # NEW: Upload date from appropriate source
            
            if task.direct_image_upload_id:
                image_source_type = 'direct'
                image_id = task.direct_image_upload_id
                image_uuid = task.direct_image.uuid if task.direct_image else None
                image_filename = task.direct_image.filename if task.direct_image else None
                upload_date = task.direct_image.created_at.date() if task.direct_image else None  # From DirectImageUpload.created_at
            elif task.encounter_file_id:
                image_source_type = 'zip'
                image_id = task.encounter_file_id
                image_uuid = task.encounter_file.uuid if task.encounter_file else None
                image_filename = task.encounter_file.filename if task.encounter_file else None
                # From ZipFile.upload_date via PatientEncounters
                if task.encounter_file and task.encounter_file.patient_encounter and task.encounter_file.patient_encounter.zip_file:
                    upload_date = task.encounter_file.patient_encounter.zip_file.upload_date
            
            # Core task information
            task_data = {
                # Task Identification
                'task_id': task.id,
                'task_uuid': task.uuid,
                
                # Image Source Information
                'image_source_type': image_source_type,
                'image_id': image_id,
                'image_uuid': image_uuid,
                'image_filename': image_filename,
                
                # NEW: Upload Date Information
                'upload_date': upload_date,  # From DirectImageUpload.created_at or ZipFile.upload_date
                
                # Task Metadata
                'disease_id': task.disease_id,
                'disease_name': task.disease.name if task.disease else None,
                'lab_unit_id': task.lab_unit_id,
                'lab_unit_name': task.lab_unit.name if task.lab_unit else None,
                'hospital_id': task.lab_unit.hospital_id if task.lab_unit and task.lab_unit.hospital else None,
                'hospital_name': task.lab_unit.hospital.name if task.lab_unit and task.lab_unit.hospital else None,
                
                # Timing Information
                'created_date': task.created_at.date(),
                'created_datetime': task.created_at,
                'updated_datetime': task.updated_at,
                'is_ad_hoc_task': task.ad_hoc_id is not None,
                'ad_hoc_id': task.ad_hoc_id,
                
                # State and Workflow
                'state': task.state,
                'has_consensus': task.consensus is not None,
            }
            
            # Consensus information (if available)
            if task.consensus:
                task_data.update({
                    'consensus_method': task.consensus.method,
                    'consensus_decided_at': task.consensus.decided_at,
                    'final_disease_grading_id': task.consensus.final_disease_grading_id,
                    'final_disease_name': task.consensus.final_disease_name,
                    'final_disease_grade': task.consensus.final_grade_name,
                })
            else:
                task_data.update({
                    'consensus_method': None,
                    'consensus_decided_at': None,
                    'final_disease_grading_id': None,
                    'final_disease_name': None,
                    'final_disease_grade': None,
                })
            
            # Grading analytics
            grades = task.grades if task.grades else []
            grading_count = len(grades)
            unique_graders = len(set(g.grader_user_id for g in grades if g.grader_user_id))
            
            # Check for arbitration need
            has_arbitration = any(g.role_slot == 'arbitrator' for g in grades)
            
            # Calculate timing metrics
            task_age_days = (datetime.now(task.created_at.tzinfo) - task.created_at).days
            completion_time_hours = None
            
            if task.state == 'final' and task.consensus and task.consensus.decided_at:
                completion_time_hours = (task.consensus.decided_at - task.created_at).total_seconds() / 3600
            
            # Calculate upload-to-task-creation lag if both dates available
            upload_to_task_days = None
            if upload_date and task.created_at:
                upload_datetime = datetime.combine(upload_date, datetime.min.time())
                upload_to_task_days = (task.created_at.date() - upload_date).days
            
            task_data.update({
                # Analytics fields
                'task_age_days': task_age_days,
                'completion_time_hours': completion_time_hours,
                'upload_to_task_days': upload_to_task_days,  # NEW: Lag from upload to task creation
                'grading_count': grading_count,
                'unique_graders_count': unique_graders,
                'has_arbitration': has_arbitration,
            })
            
            data.append(task_data)
        
        df = pd.DataFrame(data)
        
        # Debug: Log columns being generated
        if not df.empty:
            logger.info(f"DEBUG DATAFRAME: Generated columns: {list(df.columns)}")
        
        # Convert date columns to proper datetime objects
        if not df.empty:
            date_columns = ['created_datetime', 'updated_datetime', 'consensus_decided_at', 'upload_date']
            for col in date_columns:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col])
        
        return df
        
    except Exception as e:
        error_logger.error(f"Error in generate_tasks_dataframe: {str(e)}")
        error_logger.error(f"Parameters: start_date={start_date}, end_date={end_date}")
        raise
```

## Updated DataFrame Structure

### Core Fields (Required)
| Field | Type | Source | Description |
|-------|------|--------|-------------|
| task_id | int | GradingTask.id | Primary identifier |
| task_uuid | str | GradingTask.uuid | Unique identifier |
| image_source_type | str | Conditional | 'direct' or 'zip' |
| image_id | int | Conditional | Image ID from source |
| image_uuid | str | Conditional | Image UUID from source |
| image_filename | str | Conditional | Image filename from source |
| **upload_date** | date | **NEW** | **From DirectImageUpload.created_at or ZipFile.upload_date** |
| disease_id | int | GradingTask.disease_id | Disease FK |
| disease_name | str | Disease.name | Disease name |
| lab_unit_id | int | GradingTask.lab_unit_id | Lab unit FK |
| lab_unit_name | str | LabUnit.name | Lab unit name |
| created_date | date | GradingTask.created_at | Task creation date |
| created_datetime | datetime | GradingTask.created_at | Full timestamp |
| state | str | GradingTask.state | Current state |
| is_ad_hoc_task | bool | GradingTask.ad_hoc_id | Ad-hoc flag |
| has_consensus | bool | Consensus existence | Consensus flag |
| consensus_method | str | Consensus.method | Match/adjudication |
| consensus_decided_at | datetime | Consensus.decided_at | Consensus timing |
| final_disease_grading | str | Consensus.final_grade_name | Final grade |
| final_disease_name | str | Consensus.final_disease_name | Final disease |

### Analytics Fields (Enhanced)
| Field | Type | Description |
|-------|------|-------------|
| task_age_days | int | Days since task creation |
| completion_time_hours | float | Hours to completion |
| **upload_to_task_days** | int | **NEW: Days from image upload to task creation** |
| grading_count | int | Number of grades |
| unique_graders_count | int | Unique grader count |
| has_arbitration | bool | Arbitration needed |

## Enhanced Database Relationships

### For Direct Images:
```
GradingTask → DirectImageUpload.created_at (as upload_date)
```

### For Encounter Files:
```
GradingTask → EncounterFile → PatientEncounters → ZipFile.upload_date (as upload_date)
```

## Updated KPI Endpoint Enhancements

The workflow metrics endpoint can now provide additional analytics:

```python
# Upload-to-task creation lag analysis
upload_to_task_stats = {
    "avg_upload_to_task_days": df['upload_to_task_days'].mean(),
    "median_upload_to_task_days": df['upload_to_task_days'].median(),
    "max_upload_to_task_days": df['upload_to_task_days'].max()
}

# Upload date distribution analysis
upload_by_month = df.groupby(df['upload_date'].dt.to_period('M')).agg({
    'task_id': 'count'
}).reset_index()
upload_by_month.columns = ['month', 'task_count']
```

## Performance Considerations for Upload Date

### Additional Joins Required
1. **For Direct Images**: No additional joins needed (DirectImageUpload already loaded)
2. **For Encounter Files**: Need to join through PatientEncounters to get ZipFile

### Optimized Query Pattern
```python
# Enhanced relationship loading for encounter files to get upload date
joinedload(GradingTask.encounter_file)
.joinedload(EncounterFile.patient_encounter)
.joinedload(PatientEncounters.zip_file)
```

### Index Utilization
- `DirectImageUpload.created_at` - For direct image upload dates
- `ZipFile.upload_date` - For encounter file upload dates
- `EncounterFile.patient_encounter_id` - For encounter to patient relationship

## Updated Testing Strategy

### Test Upload Date Logic
```python
def test_upload_date_sources():
    # Test direct image upload date
    direct_task = create_task_with_direct_image()
    df = generate_tasks_dataframe()
    direct_row = df[df['task_id'] == direct_task.id].iloc[0]
    assert direct_row['upload_date'] == direct_task.direct_image.created_at.date()
    
    # Test encounter file upload date
    encounter_task = create_task_with_encounter_file()
    df = generate_tasks_dataframe()
    encounter_row = df[df['task_id'] == encounter_task.id].iloc[0]
    expected_upload_date = encounter_task.encounter_file.patient_encounter.zip_file.upload_date
    assert encounter_row['upload_date'] == expected_upload_date

def test_upload_to_task_lag():
    # Test calculation of upload-to-task creation lag
    task = create_task_with_known_dates()
    df = generate_tasks_dataframe()
    row = df[df['task_id'] == task.id].iloc[0]
    expected_lag = (task.created_at.date() - row['upload_date']).days
    assert row['upload_to_task_days'] == expected_lag
```

## Benefits of Upload Date Inclusion

1. **Workflow Analysis**: Understand lag between image upload and task creation
2. **Performance Metrics**: Identify bottlenecks in task generation process
3. **Trend Analysis**: Correlate upload patterns with task completion
4. **Resource Planning**: Better understanding of end-to-end workflow timing
5. **Quality Control**: Track aging of images before task assignment

## Implementation Priority

1. **High Priority**: Core upload_date field implementation
2. **Medium Priority**: Upload-to-task lag analytics
3. **Low Priority**: Advanced upload trend analysis

This enhancement provides valuable insights into the complete workflow from image upload to task completion, enabling better operational efficiency analysis.