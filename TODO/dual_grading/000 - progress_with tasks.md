I have added the new models to models.py.
I've updated scripts/setup_db.py with the --migrate-dual-grading flag.
With the data models and initial migration script in place, the next step from the plan is to build the admin-managed eligibility matrix.
However, before starting on the CRUD endpoints and UI, I'll first update the scripts/migrations.md file to document the changes, as outlined in the plan.
I've updated scripts/migrations.md, completing the data model and migration phase.
Next, I'll implement the "Eligibility Matrix (Admin-Managed)" phase. This requires creating CRUD endpoints, an admin page for assignments, and a seeding
  utility.

I'll start with the API, using the stubs from 010-eligibility-api-stubs.md to create a new api/grading_eligibility.py file. 
I'll create api/grading_eligibility.py, populate it with the code from 010-eligibility-api-stubs.md, and then import it in api/routes.py. I'll start with
  file creation.
I've built the eligibility API. Now I'll create the corresponding admin page for managing user grading eligibility, as planned.
 I will create a new file admin/grading_eligibility.py to house the views for managing grading eligibility. I will also need to create a corresponding
  template file.
   I'll start by creating the view function in a new file admin/grading_eligibility.py. This view will initially just list users, and clicking on a user will
  take the admin to a page to manage their eligibility.


  Plan:
  1.  Create admin/grading_eligibility.py.
  2.  In this file, create a view function manage_eligibility_users that lists all users. This will be the entry point.
  3.  Create another view function edit_eligibility(user_id) that will handle displaying and updating the eligibility for a specific user.
  4.  Create the corresponding templates: admin/templates/admin/grading_eligibility_users.html and admin/templates/admin/edit_grading_eligibility.html.
  5.  Register the new routes in admin/__init__.py.

I will create the file admin/grading_eligibility.py.I've reviewed the admin section and will create admin/grading_eligibility.py to manage user grading
  eligibility. I'll start with a manage_eligibility_users view to list users, linking to an edit_eligibility(user_id) view for managing individual
  permissions. The edit_eligibility view will fetch the user, diseases, and lab units, and I'll create corresponding templates for both views. I'll begin by
  creating the admin/grading_eligibility.py file.
I'll create the admin view templates. I'll assume the path is templates/admin/ and start with grading_eligibility_users.html.
I'll create the edit_grading_eligibility.html template. It will display the user's name and a table of diseases and lab units. Each cell will contain
  checkboxes for can_grade_resident, can_grade_faculty, and can_arbitrate. I'll use Javascript to fetch the user's current eligibility, populate the
  checkboxes, and then POST any changes back to the API on form submission. I'll start writing the template now.
  Okay, admin templates are done. Registering routes in admin/__init__.py now.

I've created the admin pages and routes. Now, I'll build a seeding utility for the eligibility matrix. I'll create scripts/seed_grading_eligibility.py to
  assign default UserDiseaseUnitRole permissions. The script will iterate through all 'resident' and 'ophthalmologist' users, diseases, and lab units,
  creating default eligibility entries if they don't already exist, based on the user's role. The script will be idempotent. I'll start writing it now

 Okay, seeding script's done. Now, I'll add a command to setup_db.py to execute it.

   ### Work Completed
1. Database Schema: The new data models for the dual grading system (GradingTask, Grade, Consensus, UserDiseaseUnitRole) have been successfully added to
      models.py. The database migration script (scripts/setup_db.py) has been updated to recognize and create these new tables.
  After that, we will move to the next major phase of the implementation plan: Task Creation Services. This involves building the core logic that will
  automatically create GradingTask entries whenever an image is officially verified, which is a critical part of the automated workflow.



 ✦ Based on our progress with the dual grading plan, here is a summary of the work completed:


   * Database Schema: The new data models (GradingTask, Grade, etc.) have been added to models.py, and the migration script has been updated to create these
     tables in the database.
  The next immediate step is to finish wiring up the seeding script into the main setup_db.py utility. After that, we will proceed to the next major phase
  of the plan: implementing the Task Creation Services. This involves building the core logic that automatically creates grading tasks when images are
  verified.

   Shall I proceed with updating the setup_db.py script to include the seeder?
 