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

  8. Database Transaction Issues
   - Multiple database sessions are opened and closed in different parts of the flow, which could lead to
     consistency issues
   - Rollback behavior might not be consistent across the entire submission process
   - The application uses different approaches to handle database transactions across different modules:
     * Some functions use direct db.session.commit() calls followed by db.session.close()
     * Other functions rely on context managers (with db.session.begin()) for transaction management
     * Some routes open multiple sessions in sequence without clear boundaries between operations
   - Potential race conditions could occur when multiple operations modify the same database records
     simultaneously, especially during:
     * Task state updates during grade submissions
     * Updates to TaskTracker records
     * Changes to user role eligibility during grading
   - The current transaction boundaries might not encompass all related operations:
     * A grade submission might succeed while a related TaskTracker cleanup fails
     * State updates might be committed while subsequent operations that depend on them fail
     * Cross-module operations (e.g., updating both grade and task state) might not share the same
       transaction boundary
   - If a transaction fails partway through, there's no consistent mechanism to revert all related changes
     that might have already been committed in earlier operations
   - Potential issues with connection pooling when many concurrent transactions occur during high load:
     * Database connections might not be properly returned to the pool
     * Transactions might be delayed or timeout under high load conditions
     * Deadlock situations might occur when multiple transactions compete for the same resources
   - The TaskTracker cleanup and state update operations are not atomic with the grade submission,
     creating a potential inconsistency window where grades are saved but tracking information is stale
   - Specific examples from the codebase showing the transaction handling issues:
     * In dual_grading.py, the dual_grading_submit function creates a session at the start and calls
       update_task_state_based_on_grades(task.id, db) which operates on the same session object, then
       later closes the session. This follows correct patterns for the main operation.
     * However, in the same function, when action is \"save_next\", it closes the current session and
       opens a new one to call get_next_eligible_*_task_atomic functions. This creates two separate
       transactions where there should ideally be one atomic operation.
     * The utility functions in utils/dualGradingConsensusUtils.py have a pattern where they accept
       optional db sessions (db=None) and create their own if none is provided, with different
       transaction boundaries. This can lead to inconsistencies if the calling function expects
       operations to be part of a larger transaction.
     * The TaskTracker operations in utils/dualGradingStuckTaskCleanup.py manage their own sessions
       and transactions independently from the main grading operations, creating potential race conditions
       where a grade is saved but the corresponding TaskTracker cleanup fails.
     * In mark_task_started function, there's specific handling for IntegrityError that manually
       performs rollbacks, but other functions might not have this level of error handling.
   - SOLUTION: Implement comprehensive transaction management using database sessions that encompass all
     related operations in a single atomic unit. Use SQLAlchemy's transaction context managers to ensure
     that either all operations succeed or all are rolled back. Specifically:
     1. Wrap grade submission and related state updates (including TaskTracker updates) in a single transaction
     2. Implement proper exception handling that triggers rollbacks when any part of the transaction fails
     3. Use database-level locking mechanisms (SELECT FOR UPDATE) when updating critical state that might
        be accessed concurrently
     4. Ensure that all database sessions are properly closed even in error conditions
     5. Consider implementing retry mechanisms for failed transactions due to deadlock or timeout
     6. Refactor utility functions to consistently accept external sessions when used as part of larger
        transactions, rather than creating their own session when one is already active
     7. Ensure that operations that must be atomic (like grade submission and task tracker cleanup)
        happen within the same transaction boundary

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