from flask import render_template, request, current_app, url_for, Response
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from db_transaction_manager import get_db_session
from models import Hospital, LabUnit, User, EncounterFile, DirectImageUpload, ZipFile, PatientEncounters, user_lab_units, Disease, Area, GlaucomaResultsCleaned, GlaucomaReport, Grade, GradingTask, DiseaseGrading
from auth.roles import roles_required
import pandas as pd
import io
from pathlib import Path


def hospital_dashboard():
    """Show overview of all hospitals with user counts and image contributions"""
    with get_db_session() as db:
        # Get all hospitals
        hospitals = db.execute(
            select(Hospital).order_by(Hospital.name.asc())
        ).scalars().all()
        
        # Get user counts per hospital
        user_counts = {}
        image_counts = {}
        
        for hospital in hospitals:
            # Count users associated with this hospital through lab units
            user_count = db.execute(
                select(func.count(func.distinct(User.id)))
                .select_from(User)
                .join(user_lab_units, User.id == user_lab_units.c.user_id)
                .join(LabUnit, LabUnit.id == user_lab_units.c.lab_unit_id)
                .where(LabUnit.hospital_id == hospital.id)
            ).scalar_one() or 0
            user_counts[hospital.id] = user_count
            
            # Count images contributed by users from this hospital
            # For now, we'll count direct image uploads since they have a clear hospital relationship
            direct_image_count = db.execute(
                select(func.count(DirectImageUpload.id))
                .where(DirectImageUpload.hospital_id == hospital.id)
            ).scalar_one() or 0
            
            # TODO: Add encounter file counting once we establish the relationship
            # For now, we'll just use direct uploads
            image_counts[hospital.id] = direct_image_count

        # Render template within the same session to avoid detached instance errors
        return render_template(
            "dashboard/hospitals.html",
            hospitals=hospitals,
            user_counts=user_counts,
            image_counts=image_counts
        )


def hospital_detail(hospital_id):
    """Show detailed information for a specific hospital."""
    with get_db_session() as db:
        hospital = db.get(Hospital, hospital_id)
        if not hospital:
            # Handle hospital not found
            return render_template("dashboard/hospital_not_found.html"), 404
            
        # Get all lab units for this hospital
        lab_units = db.execute(
            select(LabUnit)
            .where(LabUnit.hospital_id == hospital_id)
            .order_by(LabUnit.name.asc())
        ).scalars().all()
        
        # Get users associated with this hospital, grouped by lab unit
        users_by_lab_unit = {}
        user_roles = {}
        
        for lab_unit in lab_units:
            users = db.execute(
                select(User)
                .select_from(User)
                .join(user_lab_units, User.id == user_lab_units.c.user_id)
                .where(user_lab_units.c.lab_unit_id == lab_unit.id)
                .options(selectinload(User.roles))
                .order_by(User.username.asc())
            ).scalars().all()
            
            users_by_lab_unit[lab_unit.id] = users
            
            # Get roles for each user
            for user in users:
                user_roles[user.id] = [role.name for role in user.roles]

        # Render template within the same session to avoid detached instance errors
        return render_template(
            "dashboard/hospital_detail.html",
            hospital=hospital,
            lab_units=lab_units,
            users_by_lab_unit=users_by_lab_unit,
            user_roles=user_roles
        )


from flask import render_template, request, current_app, url_for, Response
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from models import Hospital, LabUnit, User, EncounterFile, DirectImageUpload, ZipFile, PatientEncounters, user_lab_units, Disease, Area, GlaucomaResultsCleaned, GlaucomaReport
from auth.roles import roles_required
import pandas as pd
import io


def image_list():
    """Show paginated list of all images (direct and ZIP) with detailed information."""
    # Get page number from request, default to 1
    page = request.args.get('page', 1, type=int)
    per_page = 50  # 50 items per page
    
    # Check if this is an export request
    export_format = request.args.get('export', None)
    search_query = request.args.get('search', '').strip()
    
    with get_db_session() as db:
        # Build base queries for both image types
        direct_query = select(DirectImageUpload).options(
                selectinload(DirectImageUpload.hospital),
                selectinload(DirectImageUpload.lab_unit),
                selectinload(DirectImageUpload.disease),
                selectinload(DirectImageUpload.area)
            )
        
        encounter_query = select(EncounterFile).options(
                selectinload(EncounterFile.patient_encounter).selectinload(PatientEncounters.glaucoma_reports),
                selectinload(EncounterFile.patient_encounter).selectinload(PatientEncounters.glaucoma_results_cleaned)
            )
        
        # Apply search filter if provided
        if search_query:
            direct_query = direct_query.where(
                or_(
                    DirectImageUpload.uuid.contains(search_query),
                    DirectImageUpload.filename.contains(search_query)
                )
            )
            encounter_query = encounter_query.where(
                or_(
                    EncounterFile.uuid.contains(search_query),
                    EncounterFile.filename.contains(search_query)
                )
            )
        
        # Handle export requests
        if export_format in ['csv', 'excel']:
            # Get all matching images for export
            direct_images = db.execute(direct_query.order_by(DirectImageUpload.uuid.asc())).scalars().all()
            encounter_images = db.execute(encounter_query.order_by(EncounterFile.uuid.asc())).scalars().all()
            
            # Prepare data for dataframe
            data = []
            
            # Add direct images
            for img in direct_images:
                # Use UUID for filename in export to avoid PII
                ext = Path(img.filename).suffix.lower() if img.filename else '.jpg'
                renamed_filename = f"{img.uuid}{ext}"
                
                data.append({
                    'UUID': img.uuid or '',
                    'Image Type': 'Direct',
                    'Hospital': img.hospital.name if img.hospital else '',
                    'Lab Unit': img.lab_unit.name if img.lab_unit else '',
                    'Disease': img.disease.name if img.disease else '',
                    'Area': img.area.name if img.area else '',
                    'Encounter Date': img.created_at.strftime('%Y-%m-%d') if img.created_at else '',
                    'Filename': renamed_filename,
                    'Eye Side': 'N/A (Direct)',
                    'VCDR Right': 'N/A (Direct)',
                    'VCDR Left': 'N/A (Direct)',
                    'Original VCDR Right': 'N/A (Direct)',
                    'Original VCDR Left': 'N/A (Direct)',
                    'Is Arbitration': 'Unknown'
                })
            
            # Add encounter files
            for img in encounter_images:
                # Extract VCDR values
                vcdr_right = None
                vcdr_left = None
                original_vcdr_right = None
                original_vcdr_left = None
                
                if img.patient_encounter and img.patient_encounter.glaucoma_results_cleaned:
                    # Use cleaned results
                    cleaned_result = img.patient_encounter.glaucoma_results_cleaned[0]
                    vcdr_right = cleaned_result.vcdr_right_num
                    vcdr_left = cleaned_result.vcdr_left_num
                    original_vcdr_right = cleaned_result.original_vcdr_right
                    original_vcdr_left = cleaned_result.original_vcdr_left
                elif img.patient_encounter and img.patient_encounter.glaucoma_reports:
                    # Fallback to raw report
                    report = img.patient_encounter.glaucoma_reports[0]
                    vcdr_right = report.vcdr_right
                    vcdr_left = report.vcdr_left
                    original_vcdr_right = report.vcdr_right
                    original_vcdr_left = report.vcdr_left
                
                # Use UUID for filename in export to avoid PII
                ext = Path(img.filename).suffix.lower() if img.filename else '.jpg'
                renamed_filename = f"{img.uuid}{ext}"

                data.append({
                    'UUID': img.uuid or '',
                    'Image Type': 'ZIP',
                    'Hospital': 'N/A (ZIP)',
                    'Lab Unit': 'N/A (ZIP)',
                    'Disease': 'N/A (ZIP)',
                    'Area': 'N/A (ZIP)',
                    'Encounter Date': img.patient_encounter.capture_date_dt.strftime('%Y-%m-%d') if img.patient_encounter and img.patient_encounter.capture_date_dt else (img.patient_encounter.capture_date if img.patient_encounter else ''),
                    'Filename': renamed_filename,
                    'Eye Side': img.eye_side or 'N/A',
                    'VCDR Right': vcdr_right or 'N/A',
                    'VCDR Left': vcdr_left or 'N/A',
                    'Original VCDR Right': original_vcdr_right or 'N/A',
                    'Original VCDR Left': original_vcdr_left or 'N/A',
                    'Is Arbitration': 'Unknown'
                })
            
            # Sort by UUID
            data.sort(key=lambda x: x['UUID'])
            
            # Create dataframe
            df = pd.DataFrame(data)
            
            # Export based on format
            if export_format == 'csv':
                output = io.StringIO()
                df.to_csv(output, index=False)
                csv_data = output.getvalue()
                output.close()
                
                return Response(
                    csv_data,
                    mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=image_list.csv'}
                )
            elif export_format == 'excel':
                output = io.BytesIO()
                df.to_excel(output, index=False, engine='openpyxl')
                excel_data = output.getvalue()
                output.close()
                
                return Response(
                    excel_data,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename=image_list.xlsx'}
                )
        
        # Count total images for pagination
        direct_count = db.execute(select(func.count()).select_from(direct_query.subquery())).scalar_one()
        encounter_count = db.execute(select(func.count()).select_from(encounter_query.subquery())).scalar_one()
        total_images = direct_count + encounter_count
        
        # Calculate offset for pagination
        offset = (page - 1) * per_page
        
        # Get images for current page
        direct_images = db.execute(direct_query.order_by(DirectImageUpload.uuid.asc()).offset(offset).limit(per_page)).scalars().all()
        
        # If we need more images to fill the page, get encounter files
        images_to_show = []
        image_types = []  # To track whether each image is direct or encounter
        
        # Add direct images first
        for img in direct_images:
            images_to_show.append(img)
            image_types.append('direct')
        
        # If we haven't filled the page and there might be more images, get encounter files
        if len(images_to_show) < per_page:
            remaining_slots = per_page - len(images_to_show)
            encounter_images = db.execute(
                encounter_query
                .order_by(EncounterFile.uuid.asc())
                .offset(max(0, offset - direct_count))
                .limit(remaining_slots)
            ).scalars().all()
            
            # Add encounter images
            for img in encounter_images:
                images_to_show.append(img)
                image_types.append('encounter')
        
        # Sort all images by UUID for consistent display
        # We need to create a unified list with UUID information
        unified_images = []
        image_vcdr_values = {}  # To store VCDR values for encounter files
        
        for i, img in enumerate(images_to_show):
            if image_types[i] == 'direct':
                unified_images.append({
                    'image': img,
                    'type': 'direct',
                    'uuid': img.uuid,
                    'sort_key': img.uuid
                })
            else:  # encounter
                unified_images.append({
                    'image': img,
                    'type': 'encounter',
                    'uuid': img.uuid,
                    'sort_key': img.uuid
                })
                
                # Extract VCDR values for encounter files
                if img.patient_encounter and img.patient_encounter.glaucoma_results_cleaned:
                    # Get the first glaucoma results cleaned record (assuming there's only one per encounter)
                    cleaned_result = img.patient_encounter.glaucoma_results_cleaned[0]
                    image_vcdr_values[img.id] = {
                        'vcdr_right': cleaned_result.vcdr_right_num,
                        'vcdr_left': cleaned_result.vcdr_left_num,
                        'original_vcdr_right': cleaned_result.original_vcdr_right,
                        'original_vcdr_left': cleaned_result.original_vcdr_left
                    }
                elif img.patient_encounter and img.patient_encounter.glaucoma_reports:
                    # Fallback to raw glaucoma report if no cleaned results
                    report = img.patient_encounter.glaucoma_reports[0]
                    image_vcdr_values[img.id] = {
                        'vcdr_right': report.vcdr_right,
                        'vcdr_left': report.vcdr_left,
                        'original_vcdr_right': report.vcdr_right,
                        'original_vcdr_left': report.vcdr_left
                    }
        
        # Sort by UUID
        unified_images.sort(key=lambda x: x['sort_key'])
        
        # Limit to per_page
        unified_images = unified_images[:per_page]
        
        # Get gradings for all images - using Grade model instead of ImageGrading
        image_gradings = {}
        image_vcdr_values = {}  # To store VCDR values for encounter files
        direct_ids = [item['image'].id for item in unified_images if item['type'] == 'direct']
        encounter_ids = [item['image'].id for item in unified_images if item['type'] == 'encounter']

        if direct_ids or encounter_ids:
            # Build conditions for GradingTask which links to images via Grade model
            task_conditions = []
            if direct_ids:
                task_conditions.append(GradingTask.direct_image_upload_id.in_(direct_ids))
            if encounter_ids:
                task_conditions.append(GradingTask.encounter_file_id.in_(encounter_ids))

            # Combine conditions with OR
            if len(task_conditions) == 1:
                grade_query = select(Grade).join(GradingTask).where(task_conditions[0])
            else:
                grade_query = select(Grade).join(GradingTask).where(or_(*task_conditions))

            # Include relationships for grader info and disease grading
            grade_query = grade_query.options(
                selectinload(Grade.grader),
                selectinload(Grade.label),
                selectinload(Grade.task).selectinload(GradingTask.disease)
            )

            grades = db.execute(grade_query).scalars().all()

            # Group grades by image ID and role
            for grade in grades:
                task = grade.task
                img_id = task.direct_image_upload_id or task.encounter_file_id

                if img_id not in image_gradings:
                    image_gradings[img_id] = {}

                # Map role_slot to grader_role for template compatibility
                role = grade.role_slot or 'unknown'
                # For display purposes, map role_slot names to what the template expects
                if role == 'resident':
                    role = 'resident'
                elif role == 'resident2':
                    role = 'resident'  # Both residents show as 'resident' in template
                elif role == 'arbitrator':
                    role = 'ophthalmologist'  # Arbitrators show as 'ophthalmologist'
                elif role == 'ai':
                    role = 'ai'

                if role not in image_gradings[img_id]:
                    image_gradings[img_id][role] = []

                # Create a grading object compatible with template expectations
                # using grade attributes to match ImageGrading structure
                image_gradings[img_id][role].append({
                    'id': grade.id,
                    'impression': grade.label.impression if grade.label else 'Unknown',
                    'remarks': grade.comment,
                    'graded_for': task.disease.name if task.disease else 'unknown',
                    'grader': grade.grader,
                    'created_at': grade.created_at,
                    'updated_at': grade.updated_at
                })
        
        # Extract VCDR values for encounter files
        if encounter_ids:
            # Get encounter files with their patient encounter IDs
            encounter_files = db.query(EncounterFile).filter(
                EncounterFile.id.in_(encounter_ids)
            ).all()
            
            # Get patient encounter IDs
            patient_encounter_ids = [ef.patient_encounter_id for ef in encounter_files if ef.patient_encounter_id]
            
            if patient_encounter_ids:
                # Query for cleaned results
                cleaned_results = db.query(GlaucomaResultsCleaned).filter(
                    GlaucomaResultsCleaned.patient_encounter_id.in_(patient_encounter_ids)
                ).all()
                
                # Create a mapping of patient_encounter_id to cleaned results
                cleaned_results_map = {cr.patient_encounter_id: cr for cr in cleaned_results}
                
                # Query for raw reports as fallback
                raw_reports = db.query(GlaucomaReport).filter(
                    GlaucomaReport.patient_encounter_id.in_(patient_encounter_ids)
                ).all()
                
                # Create a mapping of patient_encounter_id to raw reports
                raw_reports_map = {rr.patient_encounter_id: rr for rr in raw_reports}
                
                # Map VCDR values to encounter file IDs
                for ef in encounter_files:
                    if ef.patient_encounter_id in cleaned_results_map:
                        # Use cleaned results
                        cleaned_result = cleaned_results_map[ef.patient_encounter_id]
                        image_vcdr_values[ef.id] = {
                            'vcdr_right': cleaned_result.vcdr_right_num,
                            'vcdr_left': cleaned_result.vcdr_left_num,
                            'original_vcdr_right': cleaned_result.original_vcdr_right,
                            'original_vcdr_left': cleaned_result.original_vcdr_left
                        }
                    elif ef.patient_encounter_id in raw_reports_map:
                        # Fallback to raw report
                        report = raw_reports_map[ef.patient_encounter_id]
                        image_vcdr_values[ef.id] = {
                            'vcdr_right': report.vcdr_right,
                            'vcdr_left': report.vcdr_left,
                            'original_vcdr_right': report.vcdr_right,
                            'original_vcdr_left': report.vcdr_left
                        }
        
        # Calculate total pages
        total_pages = (total_images + per_page - 1) // per_page

        return render_template(
                "dashboard/image_list.html",
                images=unified_images,
                image_gradings=image_gradings,
                image_vcdr_values=image_vcdr_values,
                page=page,
                total_pages=total_pages,
                total_images=total_images,
                search_query=search_query
        )