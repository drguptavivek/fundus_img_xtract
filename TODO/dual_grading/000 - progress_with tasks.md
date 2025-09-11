I have added the new models to models.py.
Next,  implemented the "Eligibility Matrix (Admin-Managed)" phase. This requires creating CRUD endpoints, an admin page for assignments, and a seeding
  utility. I've created the admin pages and routes.
  1.  admin/grading_eligibility.py.
  2.  In this file, create a view function manage_eligibility_users that lists all users. This will be the entry point.
  3.  Create another view function edit_eligibility(user_id) that will handle displaying and updating the eligibility for a specific user.
  4.  Create the corresponding templates: admin/templates/admin/grading_eligibility_users.html and admin/templates/admin/edit_grading_eligibility.html.
  5.  Register the new routes in admin/__init__.py.

 Now, built a idempotent seeding script utility  -  scripts/seed_grading_eligibility.py to   assign default UserDiseaseUnitRole permissions for the eligibility matrix. The script  iterate through all 'resident' and 'ophthalmologist' users, diseases, and lab units,   creating default eligibility entries if they don't already exist, based on the user's role. 

 
### WORK  DONE TILL NOW
Database Schema: The new data models for the dual grading system (GradingTask, Grade, Consensus, UserDiseaseUnitRole) have been successfully added to
      models.py. 
      
The database migration script (scripts/setup_db.py) has been updated to recognize and create these new tables.
  
  
### Error noted
This led to  SAWarning-  Both GradingTask.consensus and Consensus.task point at the same FK pair (consensus.task_id -> grading_tasks.id) without explicitly linking them. SQLAlchemy warns because it can’t know they’re two sides of the same relationship, so it suspects overlapping write paths.  
Applied  fix to remove the SAWarning and updated the draft docs to match. 
Changed models.py - 
    - GradingTask.consensus: added back_populates and single_parent to correctly pair the one-to-one and support delete-orphan.
    consensus: relationship('Consensus', back_populates='task', uselist=False, cascade="all, delete-orphan", single_parent=True)
    - Consensus.task: added back_populates to point back to GradingTask.consensus. task: relationship('GradingTask', back_populates='consensus')
TODO/dual_grading/007-models-sqlalchemy.md - Mirrored the back_populates changes in the draft definitions and noted why (avoid SAWarning on overlapping relationships).

Additionally fixed mapper pairing error (sqlalchemy.exc.ArgumentError)
- Cause: Grade.task and Consensus.task were implicitly pairing to the wrong reverse sides (GradingTask.consensus and GradingTask.grades respectively).
- Fixes applied in models.py:
  - Grade.task now pairs with GradingTask.grades via `back_populates='grades'`.
  - GradingTask.grades pairs back via `back_populates='task'`.
  - Consensus.task pairs with GradingTask.consensus via `back_populates='consensus'`.
  - GradingTask.consensus pairs back via `back_populates='task'` and `single_parent=True`.
-
Verification
- Models import cleanly without SAWarnings/ArgumentError.
- Roles seeding/ensure works (auth/roles.py) without mapper errors.
- App factory creates and initializes schema successfully.

The error was occurring because of incorrect relationship definitions in the dual grading models:

   1. In the Grade model, the task relationship was incorrectly pointing to GradingTask.consensus
   2. In the Consensus model, the task relationship was incorrectly pointing to GradingTask.grades

  Fixes Applied

   1. Fixed the `Grade` model relationship:
      - Changed task: Mapped['GradingTask'] = relationship('GradingTask', back_populates='consensus')
      - To: task: Mapped['GradingTask'] = relationship('GradingTask', back_populates='grades')

   2. Fixed the `Consensus` model relationship:
      - Changed task: Mapped['GradingTask'] = relationship('GradingTask', back_populates='grades')
      - To: task: Mapped['GradingTask'] = relationship('GradingTask', back_populates='consensus')

  The relationship definitions now correctly match:
   - GradingTask.grades ↔ Grade.task
   - GradingTask.consensus ↔ Consensus.task

  This resolves the sqlalchemy.exc.ArgumentError you were experiencing when trying to ensure roles in the database.

 ### NERXT STEP
 
 
 
 
 
  After that, we will move to the next major phase of the implementation plan: Task Creation Services. This involves building the core logic that will
  automatically create GradingTask entries whenever an image is officially verified, which is a critical part of the automated workflow.
   After that, we will proceed to the next major phase   of the plan: implementing the Task Creation Services. This involves building the core logic that automatically creates grading tasks when images are
  verified.


 


     

