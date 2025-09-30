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
     they become available to other users. The reset_stuck_tasks function identifies tasks in the TaskTracker 
     table where started_at is older than the time threshold and deletes those tracker records.
   - TASK TRACKER MODEL: A new TaskTracker model was introduced to store task access information including:
     * task_id: The ID of the grading task
     * user_id: The ID of the user who started the task
     * role_slot: The role slot ('resident', 'faculty', or 'arbitrator')
     * started_at: The timestamp when the user started working on the task
     * created_at: The timestamp when the tracker record was created
   - IMMEDIATE TASK CLEANUP: When a user successfully submits a grade for a task and role slot, the corresponding
     TaskTracker record is immediately cleaned up, eliminating the need to wait for the periodic cleanup.
     This cleanup only occurs for new task submissions, not for revisions.
   - TASK TRACKER FOR REVISIONS: TaskTracker records are NOT created when a user accesses a task for revision
     (when they are revising a grade they previously submitted). This prevents unnecessary tracking of revision
     tasks that don't need stuck task monitoring.
   - STUCK TASK CLEANUP THREAD: A background thread runs in app.py that periodically executes the
     reset_stuck_tasks function every 30 minutes to detect and reset tasks that have been in progress
     for more than 60 minutes without completion. This serves as a safety net for any edge cases where
     immediate cleanup might not occur.

  4. Session Management Issues [RESOLVED]
   - The grading start time was stored in the Flask session, which could be problematic if the user refreshed
     the page or if the session expired during grading
   - SOLVED: The start time is now passed as a hidden field in the form, so it persists even if the page
     is refreshed or the session expires. The system first tries to retrieve the start time from the form
     data, and falls back to the session only if needed.

  5. Role Changes During Grading Process [ACCEPTABLE]
   - A user might have the required role when accessing a task but lose that role before submitting
   - The system checks role eligibility during submission, which could result in a user losing work if their
     role changes mid-task
  However, this issue is marked as extremely unlikely since most users complete grading within seconds, 
  and the eligibility check is already implemented as a security measure during submission. 
  The security check during submission is necessary to ensure that only authorized users can submit grades, 
  even if they had access initially but lost permissions during the task. This is an accepted
  limitation given the low probability of role changes occurring during the brief grading window.



  6. Task State Transitions Edge Cases [RESOLVED]
   - If a faculty member grades a task that's already in "final" state (after an arbitrator has decided), the
     system should prevent this but there could be a race condition
   - If both resident and faculty grades are submitted nearly simultaneously to a pending task, the state may
     transition directly from pending to final without going through resident_done
   - If an arbitrator grades and then both resident and faculty submit matching grades, the state might be
     incorrectly updated
   - SOLUTION: Implemented proper state validation at task assignment and at faculty submission to ensure:
     1. When assigning task to faculty, verify the task is still in 'pending' or 'resident_done' state
     2. At faculty submission, validate that the task is still in expected state before accepting the grade
     3. Additional validation re-checks the state at submission time to prevent race conditions
     4. The system now checks task availability based on user role and current state at assignment time
     5. Database-level constraints and atomic operations help prevent invalid state transitions

These edge cases were addressed by implementing comprehensive state validation checks at both assignment and submission time, ensuring that the task state transitions follow the correct sequence and that race conditions are handled properly.

  7. Arbitrator Exclusion Logic Conflicts [RESOLVED]
   - The 2-week exclusion between role slots could prevent a qualified arbitrator from arbitrating if they
     recently graded as faculty or resident
   - There's complexity in the exclusion logic during submission that checks whether it's a revision of an
     existing arbitrator grade, which could have edge cases
   - The logic should work at both allocation and submission time:
     * At allocation time, the system uses _has_user_graded_task_2weeks() to filter out tasks the arbitrator
       has graded in the past 2 weeks across any role slot
     * At submission time, the system performs an additional check specifically for arbitrator exclusion:
       - It verifies if the user has graded as resident or faculty within the last 2 weeks before allowing
         them to arbitrate (unless they're revising their own arbitrator grade)
       - This provides more granular control than the general 2-week exclusion
     * However, there's a potential race condition where the state of the task or user permissions might
       change between allocation and submission time, creating inconsistencies
     * The current implementation handles this with checks at both phases, but there might be edge cases
       where the allocation and submission time checks are not in sync
     * Example scenario: An arbitrator gets allocated a task (passes 2-week check at allocation time), 
       but before they submit their arbitration grade, they submit a grade as a faculty member on the
       same task. The submission-time check should prevent them from arbitrating, but this creates a
       confusing experience for the arbitrator who was initially allowed to access the task.
       - Detailed scenario: An arbitrator with permissions for both faculty and arbitrator roles
         gets allocated an arbitration task for Task X. At allocation time, they haven't graded this 
         task in the past 2 weeks in any role, so allocation is allowed. However, before submitting
         their arbitration grade, they also grade the same task X in their faculty role (perhaps on
         a different day or as part of different workflow). When they return to submit their 
         arbitrator grade, the submission will be blocked because they now have a faculty grade for
         the same task within the 2-week window. This creates a confusing experience as the 
         arbitrator was initially granted access to the task but then denied at the point of 
         submission. 
       - Another scenario: Multiple users with arbitrator permissions access the same task 
         simultaneously (before race condition fixes), and one user might submit a grade in a 
         different role between the time the task was allocated and when they attempt to submit
         their arbitrator grade. 
       - This scenario highlights the importance of having validation at both allocation and 
         submission time, as it ensures the integrity of the dual grading system's rules even 
         when external changes occur between task assignment and grade submission.

  SOLUTION: The arbitrator exclusion logic has been implemented to work at both allocation and submission time:
    1. During task allocation: The _has_user_graded_task_2weeks() function prevents arbitrators from being
       assigned tasks they've graded in the past 2 weeks across any role slot
    2. During grade submission: Additional specific checks ensure arbitrators haven't graded as resident or
       faculty within the past 2 weeks unless they're revising their own arbitrator grade
    3. This dual-layer approach ensures that even if there are race conditions between allocation and
       submission, the system maintains the integrity of the arbitrator exclusion rule at the critical
       moment of grade submission
    4. The TaskTracker mechanism also helps ensure that if changes happen between access and submission,
       tasks that are no longer eligible can be identified and handled appropriately
    5. To improve the user experience and reduce confusion when arbitrators are blocked at submission:
       - Consider adding a warning message when users access a task that might have potential conflicts
       - Implement real-time eligibility checks that update if the task state changes while the user is working
       - Provide more informative messaging during the task allocation process about potential conflicts
       - Possibly implement a pre-check during allocation that also considers other recent role activities
       - Show a notification to arbitrators if a task becomes unavailable due to system state changes

  8. Database Transaction Issues [RESOLVED]
   - Multiple database sessions were opened and closed in different parts of the flow, which led to
     consistency issues
   - Rollback behavior was not consistent across the entire submission process
   - The application used different approaches to handle database transactions across different modules:
     * Some functions used direct db.session.commit() calls followed by db.session.close()
     * Other functions relied on context managers (with db.session.begin()) for transaction management
     * Some routes opened multiple sessions in sequence without clear boundaries between operations
   - Potential race conditions occurred when multiple operations modified the same database records
     simultaneously, especially during:
     * Task state updates during grade submissions
     * Updates to TaskTracker records
     * Changes to user role eligibility during grading
   - The previous transaction boundaries did not encompass all related operations:
     * A grade submission might succeed while a related TaskTracker cleanup failed
     * State updates might be committed while subsequent operations that depend on them failed
     * Cross-module operations (e.g., updating both grade and task state) did not share the same
       transaction boundary
   - If a transaction failed partway through, there was no consistent mechanism to revert all related changes
     that might have already been committed in earlier operations
   - Potential issues with connection pooling when many concurrent transactions occurred during high load:
     * Database connections might not be properly returned to the pool
     * Transactions might be delayed or timeout under high load conditions
     * Deadlock situations might occur when multiple transactions competed for the same resources
   - The TaskTracker cleanup and state update operations were not atomic with the grade submission,
     creating a potential inconsistency window where grades were saved but tracking information was stale
   - Specific examples from the codebase showing the transaction handling issues:
     * In dual_grading.py, the dual_grading_submit function created a session at the start and called
       update_task_state_based_on_grades(task.id, db) which operated on the same session object, then
       later closed the session. This followed correct patterns for the main operation.
     * However, in the same function, when action was "save_next", it closed the current session and
       opened a new one to call get_next_eligible_*_task_atomic functions. This created two separate
       transactions where there should ideally be one atomic operation.
     * The utility functions in utils/dualGradingConsensusUtils.py had a pattern where they accepted
       optional db sessions (db=None) and created their own if none was provided, with different
       transaction boundaries. This could lead to inconsistencies if the calling function expected
       operations to be part of a larger transaction.
     * The TaskTracker operations in utils/dualGradingStuckTaskCleanup.py managed their own sessions
       and transactions independently from the main grading operations, creating potential race conditions
       where a grade was saved but the corresponding TaskTracker cleanup failed.
     * In mark_task_started function, there was specific handling for IntegrityError that manually
       performed rollbacks, but other functions might not have had this level of error handling.

      SOLUTION IMPLEMENTED:
      1. Created a db_transaction_manager.py with consistent transaction handling utilities:
          - get_db_session() context manager for standard session management
          - transaction_scope() context manager for atomic operations
          - execute_in_transaction() function for executing functions in a transaction scope

      2. Updated all utility functions to accept external database sessions:
          - Modified functions in utils/dualGradingStuckTaskCleanup.py to accept optional db sessions
          - Modified functions in utils/dualGradingConsensusUtils.py to accept optional db sessions
          - Modified functions in utils/dualGradingGetNextTasks.py to accept optional db sessions

      3. Refactored the dual grading workflow routes in grading/dual_grading.py to use transaction scopes:
          - dual_grading_submit now uses transaction_scope() context manager
          - grade creation, task state updates, and task tracker cleanup now happen within the same transaction
          - dual_grading_task and revise_grading functions also now use transaction_scope()

      4. Implemented proper exception handling that ensures:
          - Automatic rollback on any exception within the transaction scope
          - Proper error propagation to trigger rollbacks when needed
          - Consistent session closing in all code paths (success and error)

      5. The TaskTracker cleanup is now part of the same transaction as the grade submission,
          ensuring atomicity of the entire operation

      The solution addresses all the identified transaction issues by ensuring that related operations
      happen within the same database transaction boundary, with proper rollbacks when any part of the
      operation fails. This maintains data consistency and prevents partial updates to the database.

  9. Environment Variable Dependencies [ACCEPTABLE]
   - The ARBITRATOR_REVISION_HOURS environment variable has a default of 6 hours, but if it's set to a
     negative or very small value, it could cause unexpected behavior
   - If the environment variable is set to a very large value, arbitrators might be able to revise their
     decisions much longer than intended

  10. Task Availability After Assignment [RESOLVED]
   - Previously: When a user submitted a grade and requested "save and next task", there was a brief window where a new session
      was opened to find the next task, potentially causing a race condition where multiple users could be
     assigned the same next task
   - Current: This issue is now resolved with the new transaction management and task reservation system.
     The get_next_task function now reserves tasks atomically within the same transaction, preventing race conditions.

  11. Concurrent Grade Submissions [RESOLVED]
   - Previously: Multiple users could theoretically submit grades for the same task at the same time, potentially causing
     state transition conflicts. The state update happened after the grade was saved, which could create a race condition.
   - Current: This issue is now resolved with the new transaction management system. The task state is revalidated 
     within the same transaction as the grade submission, so if multiple users try to submit grades for the same task 
     concurrently, only one will succeed - others will fail the state validation check. All operations happen atomically.

  12. Grade Deletion/Modification Scenarios [UNRESOLVED - Design Consideration]
   - The system doesn't appear to handle cases where grades might be deleted externally from the UI workflow
   - There's no mechanism to handle corrupted or inconsistent grade data
   - This remains a potential issue as our transaction management system only ensures consistency during normal
     application operations, but doesn't protect against external database modifications or data corruption.
     Addressing this would require additional database constraints, data validation layers, and audit trails.

  13. Revision of Finalized Tasks [RESOLVED - Application Logic Handling]
   - Only arbitrators can revise finalized tasks, and only within the time window
   - Previously: The logic to determine if an arbitrator is revising their own grade could fail in certain conditions,
     especially if multiple grades exist from the same arbitrator
   - Current: The application now handles potential data integrity issues where multiple grades might exist 
     for the same user/task/slot combination. If a new grade submission is attempted when an existing grade 
     is found for the same user/task/slot, the system treats it as a revision of the existing grade rather 
     than creating a duplicate. This prevents the creation of multiple grades per user per task per slot.

  14. User Eligibility Changes [MINIMAL RISK - Short Session Duration]
   - A user might become eligible for a task based on role permissions when it's assigned but lose
     eligibility during the grading process if their permissions change
   - Lab unit or disease permissions could change while a user is in the middle of grading
   - Current: This is generally not an issue in practice, as grading sessions are typically short
     (a few seconds to minutes), making it unlikely that permissions would change during the process.
     Additionally, all grade submission operations occur within a single transaction boundary, which
     provides additional consistency protection.

  15. Data Integrity Issues [RESOLVED - Denormalization Implemented]
   - If the DiseaseGrading reference in a grade becomes invalid (e.g., if a label is deleted), it could cause
     critical issues in displaying or processing grades
   - If a task's disease or lab unit is changed after grades have been submitted, it could affect task state
     calculations and create inconsistent data states
   - This issue has been resolved by implementing denormalization. The following columns have been added
     to the database tables to make records self-contained and preserve historical accuracy:
     - Grade table: disease_name, grade_name, grade_description
     - Consensus table: final_disease_name, final_grade_name, final_grade_description
   - Migration scripts (migrate_denormalized_columns.py and populate_denormalized_columns.py) have been
     created and executed to add these columns to the existing database and populate existing records
     with the corresponding denormalized values.
   - The application code (in grading/dual_grading.py and utils/dualGradingConsensusUtils.py) has been
     updated to populate these denormalized fields when creating or updating grades and consensus records.
   - This approach ensures that even if referenced DiseaseGrading records are modified or deleted, the
     historical grade information remains intact and accessible, at the cost of increased database size.

  16. Missing Data Handling
   - If a task doesn't have associated images (neither encounter_file nor direct_image), the image_uuid will
     be None, potentially breaking the UI
   - Missing or invalid disease_gradings could prevent users from accessing tasks
   - Detailed Analysis:
     * Image Handling:
       - When encounter.image_uuid is None, the image display components may fail
       - The UI might not gracefully handle missing image references
       - Need to implement fallback for image display when image_uuid is None
       - Solution: Show a Flash error to the user and create a notification for the admin [IMPLEMENTED]
     * Disease Grading Handling:
       - If disease_gradings are missing or invalid for a task, the grading interface may break
       - Need to validate disease_gradings exist before rendering grading interface
       - Should implement fallback grading options when primary gradings are unavailable
       - Solution: If original disease and gradings do not exist, show Flash error, notify admin about 
         missing disease and disease gradings, and redirect to dashboard. No fallback grading. [IMPLEMENTED]
     * Task Access:
       - Users might be unable to access tasks with incomplete data
       - Need to implement graceful degradation for tasks with missing dependencies
       - Should show meaningful error messages rather than application crashes
       - Solution: If task has incomplete data preventing access, show Flash error, notify admin about 
         the incomplete task data, and redirect to dashboard. [IMPLEMENTED]

  These edge cases should be considered and potentially addressed in the system design to ensure robustness
  and consistency of the dual grading workflow.