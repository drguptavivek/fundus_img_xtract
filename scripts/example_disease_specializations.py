"""
Example usage of the disease specialization system.

This script demonstrates how to programmatically manage ophthalmologist disease specializations.
"""

# Import from the new location (disease_specialzation_utils)
from disease_specialzation_utils import (
    get_all_diseases, 
    get_all_ophthalmologists, 
    add_user_disease_specialization,
    remove_user_disease_specialization,
    set_user_disease_specializations,
    get_user_disease_specializations,
    get_disease_specialists
)


def setup_example_specializations():
    """Setup example disease specializations for demonstration."""
    print("Setting up example disease specializations...")
    
    # Get all diseases and ophthalmologists
    diseases = get_all_diseases()
    ophthalmologists = get_all_ophthalmologists()
    
    if not diseases or not ophthalmologists:
        print("No diseases or ophthalmologists found.")
        return
    
    # Assign some example specializations
    # Dr. John Smith specializes in Glaucoma and Diabetic Retinopathy
    dr_smith = next((u for u in ophthalmologists if u.username == 'dr_smith'), None)
    if dr_smith:
        glaucoma = next((d for d in diseases if d.name == 'Glaucoma'), None)
        dr_disease = next((d for d in diseases if d.name == 'Diabetic Retinopathy'), None)
        
        if glaucoma:
            add_user_disease_specialization(dr_smith.id, glaucoma.id)
        if dr_disease:
            add_user_disease_specialization(dr_smith.id, dr_disease.id)
        print(f"Assigned Glaucoma and Diabetic Retinopathy to {dr_smith.username}")
    
    # Dr. Sarah Johnson specializes in AMD and Diabetic Retinopathy
    dr_johnson = next((u for u in ophthalmologists if u.username == 'dr_johnson'), None)
    if dr_johnson:
        amd = next((d for d in diseases if d.name == 'AMD'), None)
        dr_disease = next((d for d in diseases if d.name == 'Diabetic Retinopathy'), None)
        
        if amd:
            add_user_disease_specialization(dr_johnson.id, amd.id)
        if dr_disease:
            add_user_disease_specialization(dr_johnson.id, dr_disease.id)
        print(f"Assigned AMD and Diabetic Retinopathy to {dr_johnson.username}")
    
    # Dr. Michael Williams specializes in all diseases
    dr_williams = next((u for u in ophthalmologists if u.username == 'dr_williams'), None)
    if dr_williams:
        disease_ids = [d.id for d in diseases]
        set_user_disease_specializations(dr_williams.id, disease_ids)
        print(f"Assigned all diseases to {dr_williams.username}")


def show_specializations():
    """Display all current specializations."""
    print("\nCurrent Disease Specializations:")
    print("=" * 50)
    
    ophthalmologists = get_all_ophthalmologists()
    
    for ophth in ophthalmologists:
        specializations = get_user_disease_specializations(ophth.id)
        if specializations:
            print(f"{ophth.username}:")
            for disease in specializations:
                print(f"  - {disease.name}")
        else:
            print(f"{ophth.username}: No specializations")


def check_if_user_can_grade_disease(username: str, disease_name: str):
    """Check if a user can grade a specific disease."""
    ophthalmologists = get_all_ophthalmologists()
    user = next((u for u in ophthalmologists if u.username == username), None)
    
    if user:
        can_grade = user.can_grade_disease_name(disease_name)
        status = "CAN" if can_grade else "CANNOT"
        print(f"{username} {status} grade {disease_name}")
        return can_grade
    else:
        print(f"User {username} not found")
        return False


if __name__ == "__main__":
    # Setup example data
    setup_example_specializations()
    
    # Show all specializations
    show_specializations()
    
    # Check some examples
    print("\nChecking specific permissions:")
    print("=" * 50)
    check_if_user_can_grade_disease("dr_smith", "Glaucoma")
    check_if_user_can_grade_disease("dr_smith", "AMD")
    check_if_user_can_grade_disease("dr_johnson", "AMD")
    check_if_user_can_grade_disease("dr_williams", "Glaucoma")