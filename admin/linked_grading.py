import logging

from flask import render_template, request, redirect, url_for, flash
from flask.typing import ResponseReturnValue
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from db_transaction_manager import transaction_scope, get_db_session
from models import Disease, DiseaseGrading, LinkedDiseaseGrading
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("admin.audit")


from flask import render_template, request, redirect, url_for, flash, jsonify
from flask.typing import ResponseReturnValue
from flask_login import current_user
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from db_transaction_manager import transaction_scope, get_db_session
from models import Disease, DiseaseGrading, LinkedDiseaseGrading
from utils.log_sanitize import sanitize_log_value
from utils.linkedGradingUtils import validate_acyclic

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("admin.audit")


@roles_required("admin")
def linked_disease_gradings_list() -> ResponseReturnValue:
    """Render the Drag-and-Drop UI for Linked Disease Grading."""
    return render_template("admin/linked_disease_gradings_drag.html")


@roles_required("admin")
def get_linked_disease_hierarchy() -> ResponseReturnValue:
    """API to fetch the current disease hierarchy."""
    with get_db_session() as db:
        diseases = db.execute(select(Disease).order_by(Disease.name)).scalars().all()
        links = db.execute(
            select(LinkedDiseaseGrading)
            .where(LinkedDiseaseGrading.is_active == True)
            .order_by(LinkedDiseaseGrading.display_order)
        ).scalars().all()

        # Build adjacency list
        children_map = {}
        for link in links:
            if link.primary_disease_id not in children_map:
                children_map[link.primary_disease_id] = []
            children_map[link.primary_disease_id].append(link.linked_disease_id)

        # Identify roots: Diseases that are not children of any other disease
        linked_children = {link.linked_disease_id for link in links}
        
        # Also need to know which diseases are part of a tree vs "pool"
        # A disease is in the pool if it has no parent AND no children.
        # A disease is a Root if it has no parent but HAS children.
        
        # Actually, simpler:
        # 1. Pool: All diseases not in `linked_children` AND not in `children_map` keys?
        #    No, a root has children.
        #    Pool = {d for d in diseases if d.id not in linked_children and d.id not in children_map}
        
        # Let's just return all diseases and the links. The frontend can build the tree.
        # This is easier for the frontend library to handle "Available" vs "Linked".
        
        disease_list = [{"id": d.id, "name": d.name} for d in diseases]
        link_list = [{"parent_id": l.primary_disease_id, "child_id": l.linked_disease_id} for l in links]
        
        return jsonify({"diseases": disease_list, "links": link_list})


@roles_required("admin")
def update_linked_disease_hierarchy() -> ResponseReturnValue:
    """API to update the hierarchy (full sync)."""
    data = request.get_json()
    if not data or "links" not in data:
        return jsonify({"error": "Invalid data format"}), 400

    new_links = data["links"]  # List of {parent_id, child_id}
    
    # Validate format
    edges = []
    for link in new_links:
        try:
            pid = int(link["parent_id"])
            cid = int(link["child_id"])
            if pid == cid:
                return jsonify({"error": f"Self-link detected for disease ID {pid}"}), 400
            edges.append((pid, cid))
        except (ValueError, KeyError):
            return jsonify({"error": "Invalid link data"}), 400

    # Validate cycles
    if not validate_acyclic(edges):
        return jsonify({"error": "Cycle detected in hierarchy"}), 400

    with transaction_scope() as db:
        # 1. Clear existing active links? 
        # Or mark inactive? The requirement implied full sync.
        # Let's delete all active links and recreate. 
        # Hard delete is fine for configuration if we don't need history of "what was linked 5 mins ago".
        # But `LinkedDiseaseGrading` has no history tracking other than audit logs.
        
        # Fetch existing
        existing = db.execute(select(LinkedDiseaseGrading)).scalars().all()
        existing_map = {(l.primary_disease_id, l.linked_disease_id): l for l in existing}
        
        seen_pairs = set()
        
        # Process new links
        for idx, (pid, cid) in enumerate(edges):
            pair = (pid, cid)
            if pair in seen_pairs:
                continue # Duplicate in input
            seen_pairs.add(pair)
            
            if pair in existing_map:
                # Update existing
                link = existing_map[pair]
                link.is_active = True
                link.display_order = idx # Simple ordering based on list position
                # Remove from map so we know what's left
                del existing_map[pair]
            else:
                # Create new
                new_link = LinkedDiseaseGrading(
                    primary_disease_id=pid,
                    linked_disease_id=cid,
                    display_order=idx,
                    is_active=True
                )
                db.add(new_link)
        
        # Deactivate/Delete remaining
        for link in existing_map.values():
            # We can either delete or set inactive. 
            # If we set inactive, they might clutter the DB. 
            # Given the previous code allowed delete, let's delete to keep it clean.
            db.delete(link)
            
        audit_logger.info(
            "Linked grading hierarchy updated by '%s' with %d links",
            sanitize_log_value(getattr(current_user, "username", "unknown")),
            len(edges)
        )
        
    return jsonify({"success": True})


@roles_required("admin")
def edit_linked_disease_grading(link_id: int) -> ResponseReturnValue:
    with get_db_session() as db:
        link = db.execute(
            select(LinkedDiseaseGrading)
            .options(
                selectinload(LinkedDiseaseGrading.primary_disease),
                selectinload(LinkedDiseaseGrading.linked_disease),
            )
            .where(LinkedDiseaseGrading.id == link_id)
        ).scalar_one_or_none()

        if not link:
            flash("Linked grading not found.", "danger")
            return redirect(url_for("admin.linked_disease_gradings_list"))

        if request.method == "GET":
            diseases = db.execute(select(Disease).order_by(Disease.name)).scalars().all()
            return render_template(
                "admin/linked_disease_grading_edit.html",
                link=link,
                diseases=diseases,
            )

    if request.method == "POST":
        primary_id_raw = request.form.get("primary_disease_id", str(link.primary_disease_id)).strip()
        linked_id_raw = request.form.get("linked_disease_id", str(link.linked_disease_id)).strip()
        display_order_raw = request.form.get("display_order", "0").strip()
        is_active = request.form.get("is_active") == "1"

        try:
            primary_id = int(primary_id_raw)
            linked_id = int(linked_id_raw)
        except ValueError:
            flash("Disease selection is invalid.", "danger")
            return redirect(url_for("admin.edit_linked_disease_grading", link_id=link_id))

        if primary_id != link.primary_disease_id or linked_id != link.linked_disease_id:
            flash("Delink first before relinking to a different disease.", "danger")
            return redirect(url_for("admin.edit_linked_disease_grading", link_id=link_id))

        try:
            display_order = int(display_order_raw)
        except ValueError:
            flash("Display order must be a number.", "danger")
            return redirect(url_for("admin.edit_linked_disease_grading", link_id=link_id))

        with transaction_scope() as db:
            link = db.get(LinkedDiseaseGrading, link_id)
            if not link:
                flash("Linked grading not found.", "danger")
                return redirect(url_for("admin.linked_disease_gradings_list"))

            link.display_order = display_order
            link.is_active = is_active

            primary = db.get(Disease, link.primary_disease_id)
            linked = db.get(Disease, link.linked_disease_id)

            try:
                audit_logger.info(
                    "Linked grading updated by '%s': primary='%s' linked='%s' order='%s' active='%s'",
                    sanitize_log_value(getattr(current_user, "username", "unknown")),
                    sanitize_log_value(primary.name if primary else link.primary_disease_id),
                    sanitize_log_value(linked.name if linked else link.linked_disease_id),
                    sanitize_log_value(display_order),
                    sanitize_log_value(is_active),
                )
            except Exception as exc:
                logger.warning("Failed to audit linked grading update: %s", sanitize_log_value(exc))

            flash("Linked grading updated successfully.", "success")
            return redirect(url_for("admin.linked_disease_gradings_list"))


@roles_required("admin")
def delete_linked_disease_grading(link_id: int) -> ResponseReturnValue:
    with transaction_scope() as db:
        link = db.execute(
            select(LinkedDiseaseGrading)
            .options(
                selectinload(LinkedDiseaseGrading.primary_disease),
                selectinload(LinkedDiseaseGrading.linked_disease),
            )
            .where(LinkedDiseaseGrading.id == link_id)
        ).scalar_one_or_none()

        if not link:
            flash("Linked grading not found.", "danger")
            return redirect(url_for("admin.linked_disease_gradings_list"))

        primary_name = link.primary_disease.name if link.primary_disease else link.primary_disease_id
        linked_name = link.linked_disease.name if link.linked_disease else link.linked_disease_id

        db.delete(link)

        try:
            audit_logger.info(
                "Linked grading deleted by '%s': primary='%s' linked='%s'",
                sanitize_log_value(getattr(current_user, "username", "unknown")),
                sanitize_log_value(primary_name),
                sanitize_log_value(linked_name),
            )
        except Exception as exc:
            logger.warning("Failed to audit linked grading delete: %s", sanitize_log_value(exc))

        flash("Linked grading deleted successfully.", "success")

        return redirect(url_for("admin.linked_disease_gradings_list"))
