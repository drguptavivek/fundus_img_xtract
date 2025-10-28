# DirectImages KPI Definitions

## Overview
This document defines Key Performance Indicators (KPIs) for DirectImages analysis in the Fundus Image Manager system.

---

## KPI 1: DirectImages Upload Metrics

### Primary Metrics

#### 1.1 Total DirectImages Uploads
- **Description**: Total count of direct image uploads in the filtered period
- **Calculation**: `COUNT(DISTINCT image_id)`
- **Dimensions**: By hospital, lab unit, camera, disease, area, uploader
- **Time Period**: Daily, Weekly, Monthly, Yearly

#### 1.2 Upload Volume by Uploader
- **Description**: Number of images uploaded by each user
- **Calculation**: `COUNT(image_id) GROUP BY uploader_username`
- **Use Case**: Identify active uploaders and upload patterns

#### 1.3 Upload Volume by Camera
- **Description**: Distribution of uploads across different cameras
- **Calculation**: `COUNT(image_id) GROUP BY camera_name`
- **Use Case**: Camera usage analysis and equipment planning

#### 1.4 Upload Volume by Disease
- **Description**: Distribution of uploads by disease type
- **Calculation**: `COUNT(image_id) GROUP BY disease_name`
- **Use Case**: Disease-specific data collection analysis

#### 1.5 Upload Volume by Hospital/Lab Unit
- **Description**: Upload distribution across locations
- **Calculation**: `COUNT(image_id) GROUP BY hospital_name, lab_unit_name`
- **Use Case**: Site performance comparison

#### 1.6 Mydriatic vs Non-Mydriatic Uploads
- **Description**: Comparison of mydriatic and non-mydriatic image uploads
- **Calculation**: `COUNT(image_id) GROUP BY is_mydriatic`
- **Use Case**: Imaging protocol compliance analysis

#### 1.7 Pregraded Uploads
- **Description**: Percentage of uploads marked as pregraded
- **Calculation**: `SUM(is_pregraded) / COUNT(image_id) * 100`
- **Use Case**: Pregrading workflow efficiency

### Secondary Metrics

#### 1.8 Upload Trend Analysis
- **Description**: Upload volume trends over time
- **Calculation**: Time series analysis of upload_date
- **Visualization**: Line chart with trend line

#### 1.9 Average Uploads per Day
- **Description**: Daily average upload volume
- **Calculation**: `COUNT(image_id) / DATEDIFF(MAX(upload_date), MIN(upload_date))`
- **Use Case**: Capacity planning

#### 1.10 Peak Upload Days/Times
- **Description**: Identify patterns in upload timing
- **Calculation**: Extract day of week and hour from upload_datetime
- **Use Case**: Resource allocation

---

## KPI 2: DirectImages Verification Status

### Primary Metrics

#### 2.1 Verification Rate
- **Description**: Percentage of images that have been verified
- **Calculation**: `SUM(has_verification) / COUNT(image_id) * 100`
- **Dimensions**: By hospital, lab unit, verifier, disease
- **Time Period**: Daily, Weekly, Monthly

#### 2.2 Verification Status Distribution
- **Description**: Distribution of verification statuses
- **Calculation**: `COUNT(image_id) GROUP BY verification_status`
- **Statuses**: verified, unverified, pending
- **Use Case**: Verification workflow analysis

#### 2.3 Time to Verification
- **Description**: Average time from upload to verification
- **Calculation**: `AVG(verified_at - upload_datetime)` in days/hours
- **Use Case**: Verification efficiency measurement

#### 2.4 Verification by Verifier
- **Description**: Number of verifications performed by each user
- **Calculation**: `COUNT(image_id) GROUP BY verified_by_username`
- **Use Case**: Verifier workload analysis

#### 2.5 Verification Rate by Disease
- **Description**: Verification completion rate by disease type
- **Calculation**: `SUM(has_verification) / COUNT(image_id) GROUP BY disease_name`
- **Use Case**: Disease-specific verification priorities

### Secondary Metrics

#### 2.6 Verification Trend
- **Description**: Verification completion trends over time
- **Calculation**: Time series of verification completion
- **Visualization**: Line chart showing verification backlog

#### 2.7 Unverified Images Aging
- **Description**: How long unverified images have been waiting
- **Calculation**: `CURRENT_DATE - upload_date` for unverified images
- **Use Case**: Backlog management

#### 2.8 Verification Remarks Analysis
- **Description**: Common issues noted during verification
- **Calculation**: Text analysis of verification_remarks
- **Use Case**: Quality improvement insights

---

## KPI 3: DirectImages Grading Metrics

### Primary Metrics

#### 3.1 Grading Coverage Rate
- **Description**: Percentage of images that have been graded
- **Calculation**: `SUM(has_grading) / COUNT(image_id) * 100`
- **Dimensions**: By hospital, lab unit, grader, disease
- **Time Period**: Daily, Weekly, Monthly

#### 3.2 Average Gradings per Image
- **Description**: Average number of gradings per image
- **Calculation**: `SUM(grading_count) / COUNT(has_grading)`
- **Use Case**: Grading workflow analysis

#### 3.3 Grading by Role
- **Description**: Distribution of gradings by role type
- **Calculation**: `COUNT(grading_id) GROUP BY grader_role`
- **Roles**: resident, resident2, arbitrator, ai
- **Use Case**: Role-specific workload analysis

#### 3.4 Grading Completion Time
- **Description**: Average time from upload to first grading
- **Calculation**: `AVG(latest_grading_date - upload_datetime)`
- **Use Case**: Grading efficiency measurement

#### 3.5 Disease-Specific Grading Coverage
- **Description**: Grading completion rate by disease
- **Calculation**: `SUM(has_grading) / COUNT(image_id) GROUP BY disease_name`
- **Use Case**: Disease-specific grading priorities

### Secondary Metrics

#### 3.6 Multi-Disease Grading
- **Description**: Images graded for multiple diseases
- **Calculation**: `COUNT(image_id) WHERE grading_count > 1`
- **Use Case**: Comprehensive assessment analysis

#### 3.7 Grading Quality Metrics
- **Description**: Consistency metrics for gradings
- **Calculation**: Variance analysis for multiple gradings
- **Use Case**: Quality assurance

#### 3.8 AI vs Human Grading Comparison
- **Description**: Comparison of AI and human grading patterns
- **Calculation**: Separate metrics for AI and human gradings
- **Use Case**: AI model performance analysis

---

## KPI 4: DirectImages Camera and Disease Analysis

### Primary Metrics

#### 4.1 Camera Usage Distribution
- **Description**: Usage patterns across different cameras
- **Calculation**: `COUNT(image_id) GROUP BY camera_name`
- **Dimensions**: By hospital, lab unit, disease
- **Use Case**: Equipment utilization analysis

#### 4.2 Disease Distribution by Camera
- **Description**: Which cameras are used for which diseases
- **Calculation**: `COUNT(image_id) GROUP BY camera_name, disease_name`
- **Use Case**: Camera-disease compatibility analysis

#### 4.3 Area-Specific Uploads
- **Description**: Distribution of uploads by imaging area
- **Calculation**: `COUNT(image_id) GROUP BY area_name`
- **Areas**: Anterior segment, Fundus, etc.
- **Use Case**: Imaging protocol analysis

#### 4.4 Camera Performance Metrics
- **Description**: Image quality metrics by camera
- **Calculation**: Verification and grading rates by camera
- **Use Case**: Camera performance evaluation

### Secondary Metrics

#### 4.5 Camera-Disease-Area Combinations
- **Description**: Usage patterns for specific combinations
- **Calculation**: Multi-dimensional analysis
- **Use Case**: Protocol optimization

#### 4.6 New Camera Adoption
- **Description**: Uptake of new cameras over time
- **Calculation**: Time series analysis by camera
- **Use Case**: Equipment rollout analysis

---

## KPI 5: DirectImages Time-Based Analysis

### Primary Metrics

#### 5.1 Upload Volume Trends
- **Description**: Upload volume changes over time
- **Calculation**: Time series analysis of upload_date
- **Granularity**: Hourly, Daily, Weekly, Monthly
- **Use Case**: Growth analysis and capacity planning

#### 5.2 Seasonal Patterns
- **Description**: Seasonal variations in uploads
- **Calculation**: Month-over-month and year-over-year analysis
- **Use Case**: Resource planning

#### 5.3 Processing Time Analysis
- **Description**: Time from upload to various milestones
- **Calculation**: 
  - Upload to verification time
  - Upload to grading time
  - Upload to final consensus time
- **Use Case**: Workflow efficiency analysis

#### 5.4 Workflow Bottleneck Analysis
- **Description**: Identify stages with longest delays
- **Calculation**: Compare times between workflow stages
- **Use Case**: Process optimization

### Secondary Metrics

#### 5.5 Day-of-Week Patterns
- **Description**: Upload patterns by day of week
- **Calculation**: `COUNT(image_id) GROUP BY DAYOFWEEK(upload_date)`
- **Use Case**: Staffing optimization

#### 5.6 Time-of-Day Patterns
- **Description**: Upload patterns by time of day
- **Calculation**: `COUNT(image_id) GROUP BY HOUR(upload_datetime)`
- **Use Case**: System load planning

---

## Implementation Notes

### Data Requirements
- Enhanced DataFrame with all required fields
- Efficient query optimization for large datasets
- Proper indexing on date and status fields

### Performance Considerations
- Use database-level aggregations where possible
- Implement caching for frequently accessed metrics
- Consider materialized views for complex calculations

### Visualization Recommendations
- Use appropriate chart types for each metric
- Implement interactive filters for drill-down analysis
- Provide export capabilities for detailed analysis

### API Structure
- Follow existing KPI API patterns
- Use consistent parameter naming
- Implement proper error handling and validation