## UV
Uses Python Virtual environment. Use "uv run app.py" or ""uv run -c" etc for running the app

## DATE TIME
Date Time:
   - The application avoids legacy options like naive datetime storage
   - All datetime fields use the timezone-aware approach
   - The application correctly uses datetime.now(timezone.utc) instead of datetime.utcnow() (which is deprecated as of Python 3.12)
   - Resolves the appropriate timezone based on:
        - User's profile timezone setting (if user is logged in)
        - Application's DEFAULT_DISPLAY_TIMEZONE configuration
        - Fallback to DEFAULT_TIMEZONE if not configured
   - Use format_user_datetime for display: {{ some_datetime_value | format_user_datetime }} or  {{ some_datetime_value | format_user_datetime("%B %d, %Y at %I:%M %p") }}

## JINJA

Templates in /templates with route specific subfolders and /templates/partials for resusalble Jinja code


## DB SESSIONS - Database Context Manager

  - Never create database sessions directly in utility functions
  - Always pass the session from the route/endpoint to utilities
  - The context manager will handle commit/rollback/cleanup automatically 
  - Always use the database context manager from db_transaction_manager.py for database operations
  - Three context managers are available:
      a) get_db_session() - for standard database operations
      b) transaction_scope() - for atomic operations that need transaction boundaries
      c) execute_in_transaction() - for executing functions within a transaction scope
  
  - Usage in routes that call utility functions:
      - Routes should not directly manage database sessions when calling utility functions
      - Utility functions should accept database session as parameter (dependency injection)
      - Routes should manage the transaction context, passing the session to utilities
    
    - See examples in grading/dual_grading.py, notifications/notifications.py, and utils/notifications.py)
    
    - Example:
        ```python
        from db_transaction_manager import transaction_scope
        
        @bp.route('/submit-grade', methods=['POST'])
        @login_required
        def submit_grade():
            # Get form data
            grade_data = request.form
            
            with transaction_scope() as db:
                try:
                    # Call utility function, passing the database session
                    result = process_grade_submission(db, grade_data, current_user.id)
                    flash('Grade submitted successfully', 'success')
                    return redirect(url_for('grading.index'))
                except Exception as e:
                    flash(f'Error submitting grade: {str(e)}', 'error')
                    # Transaction automatically rolled back
        ```
      
      - Utility functions should expect a database session parameter:
        ```python
        # In utils/grading_utils.py
        def process_grade_submission(db, grade_data, user_id):
            # Create grade record
            grade = Grade(
                disease_id=grade_data['disease_id'],
                grader_user_id=user_id,
                disease_grading_id=grade_data['grading_id'],
                comment=grade_data.get('comment')
            )
            db.add(grade)
            
            # Update related task status
            task = db.query(GradingTask).filter(GradingTask.id == grade_data['task_id']).first()
            if task:
                task.state = 'graded'
            
            return grade
        ```
      
    - When multiple utilities need to be called in a single transaction:
        ```python
        @bp.route('/complex-operation', methods=['POST'])
        @login_required
        def complex_operation():
            with transaction_scope() as db:
                try:
                    # Multiple utility functions in one transaction
                    result1 = utility_function_1(db, param1, param2)
                    result2 = utility_function_2(db, result1, param3)
                    utility_function_3(db, result2)
                    
                    flash('Operation completed successfully', 'success')
                    return redirect(url_for('dashboard.index'))
                except Exception as e:
                    flash(f'Error in operation: {str(e)}', 'error')
                    # All operations automatically rolled back
        ```
      
    - For simple read-only operations:
        ```python
        from db_transaction_manager import get_db_session
        
        @bp.route('/get-user-stats')
        @login_required
        def get_user_stats():
            with get_db_session() as db:
                stats = get_user_statistics(db, current_user.id)
                return render_template('user/stats.html', stats=stats)
        ```

5. 
