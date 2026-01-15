# Dataset Curation User Guide

## Overview

The Dataset Curation feature allows you to create custom datasets from graded fundus images for research, AI training, and quality assurance purposes. You can filter tasks using multiple criteria, manually review images, and export curated collections.

**Key Features:**
- Filter by disease, grades, lab units, AI models, and consensus status
- Auto-select tasks or manually review each image
- Collaborative dataset creation and management
- Secure export with access control

## Getting Started

### Access Requirements

You must have one of the following roles:
- **Administrator** - Full access to all datasets
- **Local Administrator** - Access within your hospital
- **Data Manager** - Create and manage datasets
- **Data Exporter** - Export datasets
- **Dataset Creator** - Create new datasets
- **Analytics Viewer** - View existing datasets

### Navigation

**Main Page:** Analytics → Dataset Curation

---

## Creating a Dataset

### Step 1: Access Dataset Creation

1. Click **"Analytics"** in the main navigation
2. Select **"Dataset Curation"**
3. Click **"Create New Dataset"** (or scroll to the creation form)

### Step 2: Define Dataset Properties

| Field | Description | Required |
|-------|-------------|----------|
| **Dataset Name** | A descriptive name for your dataset | Yes |
| **Purpose** | Explain why you're creating this dataset | Yes |
| **Disease** | Select the disease to filter (Glaucoma, DR, AMD) | Yes |
| **Auto-Select Count** | Number of tasks to automatically include (0 for manual) | No |
| **Randomize Selection** | Check to randomly sample instead of taking first N | No |
| **Random Seed** | Optional seed for reproducible random selection | No |

**Example:**
```
Name: Glaucoma Training Set v2
Purpose: AI model training for glaucoma detection - balanced grades
Disease: Glaucoma
Auto-Select Count: 0  (We'll manually review each task)
```

### Step 3: Apply Filters

Use the filter options to narrow down which grading tasks to include in your dataset.

#### Basic Filters

**Lab Unit:** Select specific lab units or leave blank for all available units

**Grade Filters:** Choose one or more grades for each role:
- **Resident Grade:** First grader's assessment
- **Resident2 Grade:** Second grader's assessment
- **Arbitrator Grade:** Arbiter's final decision (if applicable)
- **Final Grade:** Consensus grade stored in the system

#### AI & Consensus Filters

**Has AI Grade:**
- **Yes** - Only include tasks with AI predictions
- **No/Blank** - Include all tasks regardless of AI status

**AI Model:** Select specific AI models (only active if "Has AI Grade = Yes")

**AI Grade:** Filter by AI-predicted grades

**AI Review Status:** Include/exclude based on AI review flags:
- Needs Review
- Reviewed - Accept
- Reviewed - Override
- Reviewed - Confirm

**Has Review:** Filter by whether human review occurred

**Has Consensus:**
- **has_consensus** - Both graders agreed
- **no_consensus** - Graders disagreed (went to arbitration)

### Random Selection

When you enter an **Auto-Select Count**, additional options appear:

**Randomize Selection:**
- **Unchecked (default)** - Selects the first N tasks by task ID (sequential)
- **Checked** - Selects N tasks randomly from matching results

**Random Seed (Optional):**
- Leave blank for true random (different each time)
- Enter a number (e.g., 42) for reproducible selection
- Same seed + same filters = same dataset (useful for research)

**When to Use Random Selection:**
- **AI Training** - Avoid bias from temporal ordering
- **Statistical Sampling** - Get representative samples
- **Cross-Validation** - Create reproducible train/test splits
- **Quality Assurance** - Random audit of cases

**Example: Creating a Balanced Random Dataset**
```
Disease: Diabetic Retinopathy
Has Consensus: has_consensus
Final Grade: No DR, Mild NPDR, Moderate NPDR, Severe NPDR, PDR
Auto-Select Count: 1000
Randomize Selection: ✓ Checked
Random Seed: 42
```

This creates a reproducible random sample of 1000 consensus DR cases.

### Step 4: Create and Review

1. Click **"Create Dataset"**
2. You'll be redirected to the dataset detail page
3. The system shows:
   - Total tasks matching your filters
   - Tasks included/excluded so far
   - Next image to review (if any)

---

## Manual Screening (Reviewing Tasks)

### The Screening Interface

After creating a dataset, you'll see the manual screening page:

```
┌─────────────────────────────────────────────────────────────┐
│  Dataset: Glaucoma Training Set v2                          │
│  Progress: 15 included / 3 excluded / 112 remaining         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  [Fundus Image Display Area]                                  │
│                                                               │
│  Task ID: 12345  |  Lab Unit: Eye Clinic Main               │
│  Final Grade: Moderate Glaucoma                              │
│                                                               │
│  AI Summary: Mild Glaucoma ; p=0.72 ; Model v3.2             │
│                                                               │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Grade Details:                                               │
│  • Resident: Severe Glaucoma                                 │
│  • Resident2: Moderate Glaucoma                              │
│  • Arbitrator: Moderate Glaucoma                             │
│                                                               │
│  [INCLUDE]  [EXCLUDE]                                        │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Making Decisions

For each task, decide whether to **include** or **exclude** it:

**Include** - Add to final export
- Image quality is good
- Grades are reliable
- Meets your dataset criteria

**Exclude** - Remove from export
- Image quality issues
- Unreliable grades
- Doesn't meet criteria
- Duplicate or corrupted data

### Navigation

- After making a decision, the page refreshes with the next task
- Use the **"Included Tasks"** and **"Excluded Tasks"** lists to review previous decisions
- Click any task ID in the lists to see its details

---

## Exporting Your Dataset

### Step 1: Finalize Selection

1. Complete reviewing all tasks (or export at any point)
2. Verify your include/exclude counts look correct
3. Note: Only **included** tasks will be exported

### Step 2: Initiate Export

1. Click **"Export Dataset"** button
2. System validates you have permission to export
3. A background job is created to process your export

### Step 3: Download Export

1. You'll be redirected to the job status page
2. Wait for processing to complete (shows "Completed")
3. Click the download link to get your file

**Export Contents:**
- Images (fundus photographs)
- Metadata (grades, AI predictions, demographics - de-identified)
- Dataset description file

**Retention:** Export files are kept for 24 hours (configurable)

---

## Managing Existing Datasets

### Viewing Recent Datasets

The main Dataset Curation page shows up to 20 recent datasets:

| Column | Description |
|--------|-------------|
| **Name** | Dataset name (click to view details) |
| **Created** | Creation date and time |
| **Included** | Number of tasks marked for export |
| **Excluded** | Number of tasks excluded |
| **Status** | Export job status (if applicable) |

### Dataset Actions

**View/Edit** - Click dataset name to open screening page
- Continue reviewing tasks
- Change previous decisions
- Export when ready

**Export** - Click export button (if you have permission)
- Triggers background job
- Provides download link when complete

---

## Filter Examples

### Example 1: High-Quality Training Set

**Goal:** Create a balanced dataset for AI training

**Filters:**
```
Disease: Diabetic Retinopathy
Has AI Grade: Yes
AI Review Status: Reviewed - Accept
Has Consensus: has_consensus
Final Grade: No DR, Mild NPDR, Moderate NPDR, Severe NPDR, PDR
```

**Result:** Only cases where human review confirmed AI predictions, with consensus between graders.

### Example 2: Disagreement Analysis

**Goal:** Study cases where graders disagreed

**Filters:**
```
Disease: Glaucoma
Has Consensus: no_consensus
Has Review: Yes
```

**Result:** All cases that went to arbitration due to grader disagreement.

### Example 3: AI Model Comparison

**Goal:** Compare two AI model versions

**Filters:**
```
Disease: AMD
Has AI Grade: Yes
AI Model: [select v3.1 and v3.2]
```

**Result:** All tasks with predictions from both models for comparison.

### Example 4: Quality Assurance Dataset

**Goal:** Find cases needing review

**Filters:**
```
Disease: Any
AI Review Status: Needs Review
Has AI Grade: Yes
```

**Result:** Flagged cases requiring human review.

---

## Best Practices

### Dataset Naming

Use clear, descriptive names:
- **Good:** "Glaucoma-Training-Balanced-v3", "DR-QA-2026-Q1"
- **Bad:** "dataset1", "test", "my stuff"

Include:
- Disease type
- Purpose (training, QA, research)
- Version number
- Date or quarter

### Purpose Descriptions

Write clear purposes for future reference:
```
Good: "Balanced training set for v4 model - 500 cases per grade
       from Q1 2026, only consensus cases with confirmed AI"

Bad: "for training"
```

### Review Strategy

1. **Start Small:** Test filters with small auto-select counts first
2. **Iterate:** Create initial dataset, review sample, adjust filters
3. **Document:** Note your selection criteria in the purpose field
4. **Validate:** Have a colleague review a sample for quality

### Performance Tips

- **Specific Filters:** More specific = faster queries
- **Limit Scope:** Use lab unit filters to reduce dataset size
- **Batch Exports:** Export periodically instead of one giant export

---

## Permissions and Access Control

### What You Can Do by Role

| Role | Create | View | Edit | Export |
|------|--------|------|------|--------|
| Administrator | ✓ | ✓ | ✓ | ✓ |
| Local Admin | ✓ | ✓ | ✓ | ✓ |
| Data Manager | ✓ | ✓ | ✓ | ✓ |
| Data Exporter | ✗ | ✓ | ✓ | ✓ |
| Dataset Creator | ✓ | ✓ | ✓ | ✓ |
| Analytics Viewer | ✗ | ✓ | ✗ | ✗ |

### Lab Unit Restrictions

Your access is automatically scoped to lab units you're assigned to:
- **Creators:** Can only use lab units they have access to
- **Viewers:** Can only see datasets for their lab units
- **Exporters:** Can only export datasets they have access to

---

## Troubleshooting

### Common Issues

#### "No lab units are available for dataset curation"

**Cause:** Your account isn't assigned to any lab units with dataset creation permission.

**Solution:** Contact your administrator to assign appropriate lab units.

#### "Dataset is missing a disease filter"

**Cause:** The dataset was created before disease validation was added.

**Solution:** Recreate the dataset with a disease specified.

#### "No tasks selected for export"

**Cause:** You haven't included any tasks yet.

**Solution:** Review some tasks and mark them for inclusion before exporting.

#### Export download link expired

**Cause:** Export files are retained for 24 hours only.

**Solution:** Re-run the export to generate a fresh download link.

#### "You do not have access to the lab units for this dataset"

**Cause:** Dataset was created by someone in a different lab unit/hospital.

**Solution:** Contact the dataset creator or administrator for access.

---

## Tips and Tricks

### Keyboard Shortcuts
- **Tab** - Navigate between form fields
- **Enter** - Submit decisions (on screening page)

### Quick Actions
- **Click dataset stats** to jump to included/excluded lists
- **Click task ID** in lists to see full details

### Bulk Operations
- Use **Auto-Select Count** to pre-populate dataset
- Then manually review and adjust selections

### Collaboration
- Multiple users can work on the same dataset
- Last decision wins (consider coordination for large datasets)

---

## Glossary

| Term | Definition |
|------|------------|
| **Curated Dataset** | A collection of grading tasks selected for specific purposes |
| **Filters** | Criteria used to select which tasks to include |
| **Auto-Select** | Automatically include N matching tasks without manual review |
| **Manual Screening** | Review each task individually and decide include/exclude |
| **Consensus** | When graders agree on the same grade |
| **Arbitration** | Process to resolve disagreements between graders |
| **AI Review Status** | Flag indicating whether AI prediction was reviewed |
| **Export** | Generate a downloadable file with images and metadata |

---

## Related Features

- **Advanced Image Viewer:** Enhanced viewing with filters and loupe
- **Discrepancy Reports:** Find grading disagreements
- **Direct Image Uploads:** Single image workflow
- **Task Review:** Standard grading workflow

---

## FAQ

**Q: Can I edit a dataset after creating it?**
A: Yes! Open the dataset detail page to change include/exclude decisions. You cannot change the original filters, but you can modify selections.

**Q: What happens if I exclude a task that was auto-selected?**
A: It's removed from the export. The "Auto" selection method just records how it was initially added - you can change any decision.

**Q: Can I combine datasets?**
A: Not directly, but you can create a new dataset with broader filters and manually select tasks from multiple existing datasets.

**Q: How long are exports kept?**
A: 24 hours by default. Re-export if you need it again after that.

**Q: Can I export just the metadata without images?**
A: Currently not supported, but planned for future versions.

**Q: What image formats are exported?**
A: Original format from the upload (typically JPEG or PNG).

---

## Support

For additional help:
1. Check the **Advanced Image Viewer Guide** for image viewing tips
2. Contact your **system administrator** for access issues
3. Submit a **support ticket** for bugs or feature requests

---

**Last Updated:** January 15, 2026
**Version:** 1.0
**Compatible With:** Fundus Image Manager v2.0+
