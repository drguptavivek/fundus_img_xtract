✦ Edge Cases in the Dual Grading System

  Based on my analysis of the code and documentation, here are the identified edge cases in the dual
  grading system:

  1. Time Zone Handling Issues
   - The system has inconsistent timezone handling approaches which could cause calculation errors:
     * Database datetime fields are configured with timezone=True (e.g., DateTime(timezone=True))
     * The utcnow() function properly creates timezone-aware UTC datetimes
     * However, when datetimes are retrieved from the database and used in Python code, they may become
       timezone-naive depending on how the database driver handles them
     * The code explicitly handles this by checking for tzinfo and replacing naive datetimes with
       timezone-aware versions using: grade_created_at = grade_created_at.replace(tzinfo=timezone.utc)
   
   - If the system is running entirely in UTC and all datetime comparisons are based on server time,
     this reduces but doesn't completely eliminate the issue:
     * The core assumption remains that all timezone-naive datetimes should be treated as UTC
     * If the server's timezone setting changes, it could affect how datetimes are interpreted
     * Datetime serialization/deserialization might still cause timezone information loss
     * When deployed across multiple servers, if any server is not in UTC, inconsistencies could arise
     * Daylight saving time transitions might still affect systems if timezone settings change

   - Specific areas of concern:
     * _has_user_graded_task_2weeks function in dualGradingEligibility.py uses 2-week comparison
     * Revision utilities in dualGradingRevisionUtils.py use 6-hour window for arbitrator revisions
     * Task assignment functions use time-based exclusions
     * Time tracking calculations in dual_grading.py

   - When using UTC server time consistently, the user timezone issue is largely mitigated since
     all calculations happen in the same timezone. However, the inconsistent handling (timezone-aware
     vs naive datetimes) remains a potential source of bugs and makes the code harder to maintain.

   - Additional inconsistency discovered: There were several places in the application that used
     datetime.now() without timezone specification:
     * auth/routes.py: Used for email callback timestamps
     * remedio_zip_uploads/routes.py: Used for date-based directory naming
     * utils/fileUtils.py: Used for creating date-based folder names
     * utils/utils2.py: Used for generating current timestamps
     * These inconsistent usages could lead to different behavior depending on server timezone settings.

   - The system previously had inconsistent datetime handling across different modules, with some
     parts using timezone-aware datetimes and others using naive datetimes.

   - All timezone-naive datetime operations have now been updated to use timezone-aware datetime 
     operations (datetime.now(timezone.utc)) for consistency across the application.

   - The dual grading system now consistently uses proper timezone-aware datetimes throughout the 
     application.

  2. Race Condition in Task Assignment [RESOLVED]
   - The get_next_eligible_*_task functions previously used random selection from available tasks, which could result in
     the same task being offered to multiple users simultaneously
   - There was no locking mechanism to prevent concurrent users from grabbing the same task
   - SOLVED: Implemented atomic task assignment using SELECT FOR UPDATE to lock tasks during selection, ensuring
     that only one user can claim a given task. New atomic functions (get_next_eligible_*_task_atomic) have been
     implemented to prevent race conditions.

  3. Stuck Task Cleanup [NEWLY IMPLEMENTED]
   - When users access a grading task but disconnect or abandon it without submitting, the task may remain
     unavailable to other users indefinitely
   - This situation can occur when users close their browsers, lose network connectivity, or experience other
     disruptions during the grading process
   - SOLVED: Implemented a stuck task cleanup mechanism that runs every 30 minutes and identifies tasks that 
     have been in progress for more than 60 minutes without submission. The system resets these tasks so 
     they become available to other users. The reset_stuck_tasks function identifies grades with a start_time 
     but no time_taken (indicating the task was never completed) and resets the start_time to None.

  4. Session Management Issues
   - The grading start time is stored in the Flask session, which could be problematic if the user refreshes
     the page or if the session expires during grading
   - Time tracking could fail if the session key is lost, leading to incorrect time_taken calculations

  5. Role Changes During Grading Process
   - A user might have the required role when accessing a task but lose that role before submitting
   - The system checks role eligibility during submission, which could result in a user losing work if their
     role changes mid-task

  6. Task State Transitions Edge Cases
   - If a faculty member grades a task that's already in "final" state (after an arbitrator has decided), the
     system should prevent this but there could be a race condition
   - If both resident and faculty grades are submitted nearly simultaneously to a pending task, the state may
     transition directly from pending to final without going through resident_done
   - If an arbitrator grades and then both resident and faculty submit matching grades, the state might be
     incorrectly updated

  7. Arbitrator Exclusion Logic Conflicts
   - The 2-week exclusion between role slots could prevent a qualified arbitrator from arbitrating if they
     recently graded as faculty or resident
   - There's complexity in the exclusion logic during submission that checks whether it's a revision of an
     existing arbitrator grade, which could have edge cases

  8. Database Transaction Issues
   - Multiple database sessions are opened and closed in different parts of the flow, which could lead to
     consistency issues
   - Rollback behavior might not be consistent across the entire submission process

  9. Environment Variable Dependencies
   - The ARBITRATOR_REVISION_HOURS environment variable has a default of 6 hours, but if it's set to a
     negative or very small value, it could cause unexpected behavior
   - If the environment variable is set to a very large value, arbitrators might be able to revise their
     decisions much longer than intended

  10. Task Availability After Assignment
   - When a user submits a grade and requests "save and next task", there's a brief window where a new session
      is opened to find the next task, potentially causing a race condition where multiple users could be
     assigned the same next task

  11. Concurrent Grade Submissions
   - Multiple users could theoretically submit grades for the same task at the same time, potentially causing
     state transition conflicts
   - The state update happens after the grade is saved, which could create a race condition

  12. Grade Deletion/Modification Scenarios
   - The system doesn't appear to handle cases where grades might be deleted externally from the UI workflow
   - There's no mechanism to handle corrupted or inconsistent grade data

  13. Revision of Finalized Tasks
   - Only arbitrators can revise finalized tasks, and only within the time window
   - The logic to determine if an arbitrator is revising their own grade could fail in certain conditions,
     especially if multiple grades exist from the same arbitrator

  14. User Eligibility Changes
   - A user might become eligible for a task based on role permissions when it's assigned but lose
     eligibility during the grading process if their permissions change
   - Lab unit or disease permissions could change while a user is in the middle of grading

  15. Data Integrity Issues
   - If the DiseaseGrading reference in a grade becomes invalid (e.g., if a label is deleted), it could cause
     issues in displaying or processing grades
   - If a task's disease or lab unit is changed after grades have been submitted, it could affect task state
     calculations

  16. Missing Data Handling
   - If a task doesn't have associated images (neither encounter_file nor direct_image), the image_uuid will
     be None, potentially breaking the UI
   - Missing or invalid disease_gradings could prevent users from accessing tasks

  These edge cases should be considered and potentially addressed in the system design to ensure robustness
  and consistency of the dual grading workflow.